from __future__ import annotations

import json
import logging
from typing import Any

import anthropic
import pandas as pd
from sqlalchemy.orm import Session

from backend.app.config import FOREX_PAIRS, OANDA_GRANULARITIES, get_settings
from backend.app.services.historical import load_candles_as_dataframe
from backend.app.services.indicators import compute_indicators
from backend.app.services.token_tracker import log_api_call

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You are a professional forex screener. You analyze technical indicator snapshots for multiple currency pairs and identify which ones have a potential trade setup forming.

Your job is to quickly scan each pair's current indicator state and flag ONLY the pairs with a clear directional bias and setup potential. Be selective — flag 0–2 pairs per cycle, not every pair.

A setup is worth flagging if ANY of these conditions are met:
- RSI is oversold (<30) or overbought (>70) on 4H or Daily
- Price is approaching/touching a key EMA (20, 50, or 200) with directional momentum
- MACD shows a recent crossover (histogram changing sign)
- Price is near Bollinger Band extremes with momentum divergence
- Ichimoku shows a clear kumo breakout or tenkan/kijun cross
- Multiple timeframes agree on the same direction (4H + Daily bias matching)

Output format (JSON array only, no prose, no markdown):
[
  {
    "pair": "EUR_USD",
    "potential_setup": true,
    "direction": "long",
    "reason": "Brief 1-2 sentence explanation of the setup"
  }
]

Rules:
- Return ALL 6 pairs in the array (potential_setup: false for pairs with no setup)
- direction must be "long" or "short" (or null if potential_setup is false)
- reason must be concise (≤2 sentences)
- Be conservative: when in doubt, set potential_setup: false
- Return ONLY the JSON array"""


def _build_indicator_snapshot(db: Session, pair: str) -> dict[str, Any] | None:
    """Build a compact indicator snapshot for a single pair across key timeframes."""
    snapshot: dict[str, Any] = {"pair": pair, "timeframes": {}}

    for tf in ["4H", "D"]:
        granularity = OANDA_GRANULARITIES.get(tf, "H4")
        df = load_candles_as_dataframe(db, pair, granularity)
        if df is None or len(df) < 50:
            continue

        df = compute_indicators(df, tf)
        last = df.iloc[-1]
        prev = df.iloc[-2]

        snapshot["timeframes"][tf] = {
            "close": round(float(last["close"]), 5),
            "rsi_14": round(float(last["rsi_14"]), 1) if pd.notna(last["rsi_14"]) else None,
            "macd_hist": round(float(last["macd_histogram"]), 6) if pd.notna(last["macd_histogram"]) else None,
            "macd_hist_prev": round(float(prev["macd_histogram"]), 6) if pd.notna(prev["macd_histogram"]) else None,
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
        }

    if not snapshot["timeframes"]:
        return None

    return snapshot


def _build_all_snapshots(db: Session) -> list[dict]:
    """Build indicator snapshots for all 6 forex pairs."""
    snapshots = []
    for pair in FOREX_PAIRS:
        snap = _build_indicator_snapshot(db, pair)
        if snap:
            snapshots.append(snap)
        else:
            logger.warning("Screener: no data for %s, skipping", pair)
    return snapshots


async def run_screener(db: Session) -> dict:
    """
    Batch-screen all 6 forex pairs in ONE Haiku call.
    Returns list of flagged pairs (potential_setup=True).
    """
    settings = get_settings()
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    logger.info("Screener: building indicator snapshots for %d pairs...", len(FOREX_PAIRS))
    snapshots = _build_all_snapshots(db)

    if not snapshots:
        logger.warning("Screener: no snapshots available, aborting")
        return {"status": "no_data", "flagged": [], "all_results": []}

    user_msg = (
        f"Screen these {len(snapshots)} forex pairs and identify any with a potential setup:\n\n"
        + json.dumps(snapshots, indent=2)
    )

    response = await client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_msg}],
    )

    log_api_call(db, agent="screener", model=MODEL, response=response)

    raw_text = response.content[0].text.strip()

    # Strip markdown fences if present
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    try:
        all_results = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.error("Screener: JSON parse failed: %s\nRaw: %s", exc, raw_text[:500])
        return {"status": "error", "error": str(exc), "flagged": [], "all_results": []}

    flagged = [r for r in all_results if r.get("potential_setup")]

    logger.info(
        "Screener: %d/%d pairs flagged: %s",
        len(flagged),
        len(all_results),
        [r["pair"] for r in flagged],
    )

    return {
        "status": "ok",
        "pairs_screened": len(snapshots),
        "flagged": flagged,
        "all_results": all_results,
        "model": MODEL,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "cache_read_tokens": getattr(response.usage, "cache_read_input_tokens", 0),
        "cache_write_tokens": getattr(response.usage, "cache_creation_input_tokens", 0),
    }
