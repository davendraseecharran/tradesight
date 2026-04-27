from __future__ import annotations

import json
import logging
from typing import Any

import anthropic
import pandas as pd
from sqlalchemy.orm import Session

from backend.app.config import OANDA_GRANULARITIES, TIMEFRAMES, get_settings
from backend.app.models.signal import Signal
from backend.app.models.trade import Trade
from backend.app.services.historical import load_candles_as_dataframe
from backend.app.services.indicators import (
    compute_fibonacci_levels,
    compute_indicators,
    compute_support_resistance,
)
from backend.app.services.token_tracker import log_api_call

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

# ── System prompt (≥2048 tokens required for Sonnet caching) ─────────────────
SYSTEM_PROMPT = """You are an elite forex analyst specializing in multi-timeframe confluence analysis and Smart Money Concepts (SMC). Your analysis is used by a trading algorithm to generate high-probability trade signals.

## Your Analysis Framework

### Smart Money Concepts (SMC)
- **Order Blocks (OB)**: Identify the last opposing candle before a significant move. Bullish OB = last bearish candle before bullish impulse. Bearish OB = last bullish candle before bearish impulse. Price frequently returns to OBs for mitigation.
- **Fair Value Gaps (FVG)**: A 3-candle pattern where candle 3's shadow doesn't overlap candle 1's shadow, leaving an imbalance. Bullish FVG = gap above candle 1 high. Price tends to fill FVGs.
- **Break of Structure (BOS)**: When price breaks and closes beyond a significant swing high (bullish BOS) or swing low (bearish BOS), confirming trend continuation.
- **Change of Character (CHOCH)**: A BOS in the opposite direction of the current trend, signaling a potential reversal.
- **Liquidity Sweeps**: Price wicks beyond obvious swing highs/lows (equal highs/lows, previous session highs/lows) to grab stop-loss orders before reversing. This is a high-probability reversal signal.
- **Premium/Discount Zones**: Above the equilibrium (50% of a range) is premium — ideal for shorts. Below equilibrium is discount — ideal for longs.

### Multi-Timeframe Confluence (MTF)
- **Weekly**: Macro trend direction, major support/resistance zones — primary bias
- **Daily**: Swing structure, trend confirmation, key levels — confirmation bias
- **4H**: Setup formation, entry trigger zone
- **1H**: Entry refinement, precise entry price

Analyze top-down: Weekly → Daily → 4H → 1H. **The trade direction MUST align with BOTH the Weekly AND Daily timeframes** (the higher-timeframe bias). The 4H and 1H are used only for entry timing within that bias. If Weekly and Daily disagree, do NOT take the trade — return no_setup.

### Entry Criteria (minimum for a valid signal)
1. **Weekly AND Daily must agree on direction** (this is non-negotiable)
2. Identifiable entry zone: OB, FVG, or key S/R level that price is approaching or at
3. Clear invalidation level (stop loss placement): below swing low (long) or above swing high (short)
4. Minimum 1:2.5 risk/reward to first target — prefer 1:3 when structure supports it
5. Confluence from at least 2 SMC concepts or 3 technical indicators
6. Stop loss must accommodate normal market volatility (use ATR — at least 1× ATR beyond invalidation)

### Confidence Score (1–10)
- 9-10: All 4 timeframes perfectly aligned, textbook SMC setup, strong momentum, perfect entry zone
- 7-8: Weekly + Daily aligned, good SMC confluence on 4H, clean entry trigger
- 5-6: Mixed signals or weak alignment — DO NOT recommend
- Below 5: Insufficient — return no_setup
- You MUST provide a score of 7 or higher to recommend a trade

### Learning From Past Trades
You will receive a history of recent closed trades for this instrument. **Use it as feedback on your own past analysis**:
- If multiple recent trades hit SL within 24h: your stops are too tight — widen them next time
- If trades exited at breakeven or hit TP1 only: TP2 may be too far — consider tighter targets or trail more aggressively
- If wins came from a specific zone type (OB vs FVG vs S/R retest): bias future entries toward that pattern for this pair
- If you took a recent loss in the same direction: question whether the bias has actually flipped
- Be critical — the goal is to learn and adapt, not repeat mistakes

### Risk Levels
- Stop Loss: Place 5–15 pips beyond the invalidation level (beyond swing high/low or OB)
- Take Profit 1: 1:2 R:R minimum, logical target (next S/R, FVG fill, opposing OB)
- Take Profit 2 (optional): 1:3 R:R, larger target if trend momentum supports it

## Output Format
Return ONLY a JSON object (no prose, no markdown):

{
  "instrument": "EUR_USD",
  "direction": "long",
  "entry_price": 1.08450,
  "stop_loss": 1.08200,
  "take_profit_1": 1.08950,
  "take_profit_2": 1.09450,
  "confidence": 8,
  "session": "London",
  "reasoning": "Detailed multi-paragraph analysis covering: (1) Weekly/Daily trend context, (2) 4H setup identification with SMC concepts, (3) Entry trigger and zone, (4) Risk levels with justification, (5) Confluence factors, (6) Key risks to this trade.",
  "screener_reason": "Brief reason from the screener that triggered this analysis"
}

If you cannot find a valid setup with confidence ≥ 6, return:
{"instrument": "EUR_USD", "direction": null, "confidence": 0, "reasoning": "Brief explanation of why no setup was found"}

Critical rules:
- entry_price must be at or very near current price (not deep in future)
- stop_loss must be a clear structural level, not arbitrary
- take_profit_1 must represent a realistic target within current market structure
- All prices must be logical (stop loss for long BELOW entry, for short ABOVE entry)
- Return ONLY the JSON object"""


def _build_trade_history(db: Session, instrument: str, limit: int = 10) -> str:
    """Fetch recent closed trade outcomes for an instrument as a learning signal.

    Returns a human-readable summary the AI can use to refine future setups.
    """
    trades = (
        db.query(Trade)
        .filter(Trade.instrument == instrument, Trade.status == "closed")
        .order_by(Trade.closed_at.desc())
        .limit(limit)
        .all()
    )

    # Also pull recent un-executed signals (from ALERT_ONLY history) so we have
    # context even before any trades have run.
    recent_signals = (
        db.query(Signal)
        .filter(Signal.instrument == instrument)
        .order_by(Signal.created_at.desc())
        .limit(limit)
        .all()
    )

    lines = [f"## Recent Trade Outcomes for {instrument} (most recent first)"]

    if trades:
        wins = sum(1 for t in trades if (t.actual_pnl or 0) > 0)
        losses = sum(1 for t in trades if (t.actual_pnl or 0) <= 0)
        total_pnl = sum((t.actual_pnl or 0) for t in trades)
        win_rate = (wins / len(trades) * 100) if trades else 0
        lines.append(
            f"\n### Closed Trades: {len(trades)} total — Wins {wins}, Losses {losses}, "
            f"Win Rate {win_rate:.0f}%, Net P&L ${total_pnl:+.2f}"
        )
        for t in trades:
            opened = t.opened_at.strftime("%Y-%m-%d %H:%M") if t.opened_at else "?"
            closed = t.closed_at.strftime("%Y-%m-%d %H:%M") if t.closed_at else "?"
            outcome = "WIN" if (t.actual_pnl or 0) > 0 else "LOSS"
            duration_h = (
                (t.closed_at - t.opened_at).total_seconds() / 3600
                if t.opened_at and t.closed_at else 0
            )
            lines.append(
                f"- {opened} → {closed} ({duration_h:.1f}h)  "
                f"{t.direction.upper()} @ {t.entry_price:.5f} "
                f"SL {t.stop_loss:.5f} TP {t.take_profit:.5f}  "
                f"→ {outcome} ${t.actual_pnl or 0:+.2f}  "
                f"exit={t.exit_reason or 'unknown'}"
            )
    else:
        lines.append("\n### Closed Trades: NONE — no execution history yet for this pair.")

    if recent_signals:
        lines.append(f"\n### Recent Signals Generated (whether executed or not):")
        for s in recent_signals[:5]:
            created = s.created_at.strftime("%Y-%m-%d %H:%M") if s.created_at else "?"
            approved = "APPROVED" if s.risk_approved else "REJECTED"
            reasons = ""
            if s.risk_rejection_reasons:
                try:
                    r = json.loads(s.risk_rejection_reasons)
                    reasons = f" reasons={r}"
                except Exception:
                    pass
            lines.append(
                f"- {created} {s.direction or 'none'} conf={s.confidence} "
                f"entry={s.entry_price} SL={s.stop_loss} TP1={s.take_profit_1} "
                f"R:R={s.risk_reward_ratio} → {approved}{reasons}"
            )

    lines.append(
        "\n**Use this history to improve**: avoid repeating mistakes, double-down on what worked."
    )
    return "\n".join(lines)


def _build_mtf_data(db: Session, instrument: str) -> dict[str, Any]:
    """Build full multi-timeframe data package for the analyst."""
    mtf: dict[str, Any] = {"instrument": instrument, "timeframes": {}}

    for tf in TIMEFRAMES:
        granularity = OANDA_GRANULARITIES.get(tf)
        if not granularity:
            continue

        df = load_candles_as_dataframe(db, instrument, granularity)
        if df is None or len(df) < 50:
            logger.warning("Analyst: insufficient data for %s %s", instrument, tf)
            continue

        df = compute_indicators(df, tf)

        # Use last 30 candles for context (enough for SMC pattern recognition)
        recent = df.tail(30)

        candles = []
        for _, row in recent.iterrows():
            candles.append({
                "ts": str(row.name) if hasattr(row.name, '__str__') else str(row.get("timestamp", "")),
                "o": round(float(row["open"]), 5),
                "h": round(float(row["high"]), 5),
                "l": round(float(row["low"]), 5),
                "c": round(float(row["close"]), 5),
            })

        last = df.iloc[-1]

        # Support/Resistance and Fibonacci (on full df)
        sr_levels = compute_support_resistance(df)
        fib_levels = compute_fibonacci_levels(df)

        mtf["timeframes"][tf] = {
            "candles": candles,
            "indicators": {
                "rsi_14": round(float(last["rsi_14"]), 1) if pd.notna(last["rsi_14"]) else None,
                "macd_line": round(float(last["macd_line"]), 6) if pd.notna(last["macd_line"]) else None,
                "macd_signal": round(float(last["macd_signal"]), 6) if pd.notna(last["macd_signal"]) else None,
                "macd_hist": round(float(last["macd_histogram"]), 6) if pd.notna(last["macd_histogram"]) else None,
                "ema_20": round(float(last["ema_20"]), 5) if pd.notna(last["ema_20"]) else None,
                "ema_50": round(float(last["ema_50"]), 5) if pd.notna(last["ema_50"]) else None,
                "ema_200": round(float(last["ema_200"]), 5) if pd.notna(last["ema_200"]) else None,
                "bb_upper": round(float(last["bb_upper"]), 5) if pd.notna(last["bb_upper"]) else None,
                "bb_lower": round(float(last["bb_lower"]), 5) if pd.notna(last["bb_lower"]) else None,
                "atr_14": round(float(last["atr_14"]), 5) if pd.notna(last["atr_14"]) else None,
                "ichi_tenkan": round(float(last["ichimoku_tenkan"]), 5) if pd.notna(last["ichimoku_tenkan"]) else None,
                "ichi_kijun": round(float(last["ichimoku_kijun"]), 5) if pd.notna(last["ichimoku_kijun"]) else None,
                "ichi_senkou_a": round(float(last["ichimoku_senkou_a"]), 5) if pd.notna(last["ichimoku_senkou_a"]) else None,
                "ichi_senkou_b": round(float(last["ichimoku_senkou_b"]), 5) if pd.notna(last["ichimoku_senkou_b"]) else None,
            },
            "support_levels": [round(float(s), 5) for s in sr_levels.get("support", [])[:5]],
            "resistance_levels": [round(float(r), 5) for r in sr_levels.get("resistance", [])[:5]],
            "fibonacci": {k: round(float(v), 5) for k, v in fib_levels.items() if pd.notna(v)},
        }

    return mtf


async def run_analyst(
    db: Session,
    instrument: str,
    screener_reason: str = "",
    screener_direction: str = "",
) -> dict:
    """
    Run deep MTF confluence analysis on a flagged instrument via Sonnet.
    Returns structured trade recommendation or no-setup signal.
    """
    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    logger.info("Analyst: building MTF data for %s...", instrument)
    mtf_data = _build_mtf_data(db, instrument)

    if not mtf_data["timeframes"]:
        return {
            "status": "no_data",
            "instrument": instrument,
            "confidence": 0,
            "reasoning": "Insufficient historical data for analysis",
        }

    # Pull trade history for this pair — the feedback loop that lets the AI
    # learn from its previous calls (both successful and failed).
    trade_history = _build_trade_history(db, instrument, limit=10)

    user_msg = (
        f"Perform a complete multi-timeframe confluence analysis for {instrument}.\n\n"
        f"Screener flagged this pair with direction bias: {screener_direction or 'unspecified'}\n"
        f"Screener reason: {screener_reason or 'N/A'}\n\n"
        f"{trade_history}\n\n"
        f"## Current Market Data\n{json.dumps(mtf_data, indent=2)}"
    )

    response = await client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_msg}],
    )

    log_api_call(db, agent="analyst", model=MODEL, response=response, instrument=instrument)

    raw_text = response.content[0].text.strip()

    # Strip markdown fences if present
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.error("Analyst: JSON parse failed for %s: %s\nRaw: %s", instrument, exc, raw_text[:500])
        return {
            "status": "error",
            "instrument": instrument,
            "error": str(exc),
            "confidence": 0,
        }

    # Enforce minimum confidence
    confidence = result.get("confidence", 0)
    if confidence < settings.analyst_min_confidence:
        logger.info(
            "Analyst: %s confidence %d < minimum %d, no signal",
            instrument, confidence, settings.analyst_min_confidence,
        )
        result["direction"] = None

    result["screener_reason"] = screener_reason
    result["status"] = "ok" if result.get("direction") else "no_setup"
    result["model"] = MODEL
    result["input_tokens"] = response.usage.input_tokens
    result["output_tokens"] = response.usage.output_tokens
    result["cache_read_tokens"] = getattr(response.usage, "cache_read_input_tokens", 0)
    result["cache_write_tokens"] = getattr(response.usage, "cache_creation_input_tokens", 0)

    logger.info(
        "Analyst: %s → direction=%s confidence=%d",
        instrument,
        result.get("direction"),
        confidence,
    )

    return result
