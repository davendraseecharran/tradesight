"""Claude validator — second opinion on candidates the Python engine found.

The mechanical 3-step engine (backend/app/services/strategy/) does ALL the
setup detection deterministically and for free. Claude is only called when a
candidate exists (typically 0-3 times/day) to sanity-check it against
context the rules can't see: momentum quality, news risk, and the pair's
recent trade history (the learning loop).

Deliberately compact prompts: at a 4-hour cadence, prompt caching (5-min
TTL) never survives between runs, so small payloads are what controls cost
(~$0.01-0.03 per validation).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import anthropic
import pandas as pd
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.models.news_event import NewsEvent
from backend.app.models.trade import Trade
from backend.app.services.token_tracker import log_api_call

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You are the final reviewer for an automated forex trading system.

A deterministic engine has already found a candidate trade using a strict 3-step strategy:
1. Top-down analysis: Weekly AND Daily market structure agree on direction (higher highs + higher lows = bullish; lower lows + lower highs = bearish).
2. Area of Interest: price is at a support/resistance zone with >= 3 historical touches, inside the current structure range.
3. Confirmation: the last CLOSED 4H candle formed an engulfing / morning-evening star / wick rejection at the zone, in the trend direction. Stop loss is beyond the zone; take profit is the nearest structure point; risk/reward is at least 1:2.

The rules have passed. Your job is to catch what rules cannot:
- Momentum quality: is the confirmation candle backed by momentum, or is price grinding into the zone with conviction against the trade?
- News risk: high-impact events for the pair's currencies within the next 24h can invalidate clean technicals.
- History: this pair's recent trades are provided. If the same setup type keeps losing here, or a same-direction trade just stopped out at this level, be skeptical. If it keeps winning, be confident.
- Exhaustion: entries after extended runs without pullback have worse odds even when structure agrees.

Return ONLY a JSON object:
{"approve": true|false, "confidence": <1-10>, "reasoning": "<3-6 sentences: your assessment of momentum, news, history, and overall quality>"}

Scoring: 9-10 exceptional (clean trend, fresh zone, momentum aligned, no news, history favorable); 7-8 solid; 5-6 doubtful — set approve=false; <=4 clear problems — approve=false. Approve only at confidence >= 7. Be genuinely critical: vetoing a mediocre setup costs nothing; approving a bad one loses money."""


def _trade_history(db: Session, instrument: str, limit: int = 10) -> str:
    """Compact recent-outcomes block for the learning loop."""
    trades = (
        db.query(Trade)
        .filter(Trade.instrument == instrument, Trade.status == "closed")
        .order_by(Trade.closed_at.desc())
        .limit(limit)
        .all()
    )
    if not trades:
        return "No closed trades yet for this pair."
    wins = sum(1 for t in trades if (t.actual_pnl or 0) > 0)
    lines = [f"Last {len(trades)} closed trades — {wins} wins, {len(trades) - wins} losses:"]
    for t in trades:
        when = t.closed_at.strftime("%m-%d") if t.closed_at else "?"
        lines.append(
            f"- {when} {t.direction} @ {t.entry_price}: "
            f"{'WIN' if (t.actual_pnl or 0) > 0 else 'LOSS'} ${t.actual_pnl or 0:+.0f} ({t.exit_reason or '?'})"
        )
    return "\n".join(lines)


def _upcoming_news(db: Session, instrument: str, hours: int = 24) -> str:
    """High-impact calendar events for the pair's currencies."""
    currencies = instrument.replace("XAU", "USD").split("_")
    now = datetime.now(timezone.utc)
    events = (
        db.query(NewsEvent)
        .filter(
            NewsEvent.currency.in_(currencies),
            NewsEvent.impact == "high",
            NewsEvent.event_datetime >= now,
            NewsEvent.event_datetime <= now + timedelta(hours=hours),
        )
        .order_by(NewsEvent.event_datetime.asc())
        .all()
    )
    if not events:
        return "No high-impact news for these currencies in the next 24h."
    return "\n".join(
        f"- {e.event_datetime.strftime('%m-%d %H:%M UTC')} {e.currency}: {e.event}"
        for e in events
    )


def _momentum_snapshot(df: Optional[pd.DataFrame]) -> str:
    """One-line indicator context from a computed dataframe."""
    if df is None or len(df) == 0:
        return "n/a"
    last = df.iloc[-1]

    def g(col, nd=5):
        v = last.get(col)
        return round(float(v), nd) if v is not None and pd.notna(v) else None

    return json.dumps({
        "close": g("close"),
        "rsi_14": g("rsi_14", 1),
        "macd_hist": g("macd_histogram", 6),
        "ema_20": g("ema_20"),
        "ema_50": g("ema_50"),
        "ema_200": g("ema_200"),
        "atr_14": g("atr_14"),
    })


async def run_validator(
    db: Session,
    setup: dict,
    indicator_frames: Optional[dict] = None,
) -> dict:
    """Validate an engine candidate. Returns the setup dict enriched with
    validator verdict fields (approve, confidence, reasoning)."""
    settings = get_settings()
    instrument = setup["instrument"]

    momentum = ""
    if indicator_frames:
        for tf in ("D", "H4", "1H"):
            if tf in indicator_frames:
                momentum += f"\n{tf}: {_momentum_snapshot(indicator_frames[tf])}"

    user_msg = (
        f"Candidate trade from the engine:\n{json.dumps(setup, indent=1, default=str)}\n\n"
        f"Momentum snapshot:{momentum or ' n/a'}\n\n"
        f"Upcoming news:\n{_upcoming_news(db, instrument)}\n\n"
        f"Trade history for {instrument}:\n{_trade_history(db, instrument)}\n\n"
        f"Validate this candidate."
    )

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=MODEL,
        max_tokens=600,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    log_api_call(db, agent="validator", model=MODEL, response=response, instrument=instrument)

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        verdict = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Validator: JSON parse failed for %s: %s\nRaw: %s", instrument, exc, raw[:300])
        # Unparseable verdict = no approval (fail safe)
        verdict = {"approve": False, "confidence": 0,
                   "reasoning": f"Validator output unparseable: {raw[:200]}"}

    # Threshold comes from ANALYST_MIN_CONFIDENCE (.env), default 7
    approve = (
        bool(verdict.get("approve"))
        and int(verdict.get("confidence", 0)) >= settings.analyst_min_confidence
    )

    result = dict(setup)
    result["validator_approve"] = approve
    result["confidence"] = int(verdict.get("confidence", 0))
    result["reasoning"] = verdict.get("reasoning", "")
    logger.info(
        "Validator: %s %s — approve=%s confidence=%d",
        instrument, setup.get("direction"), approve, result["confidence"],
    )
    return result
