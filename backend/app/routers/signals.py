from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.agents.orchestrator import run_single_pair
from backend.app.config import FOREX_PAIRS, get_settings
from backend.app.database import get_db
from backend.app.models.signal import Signal
from backend.app.scheduler import get_market_status

router = APIRouter(prefix="/api/v1/signals", tags=["signals"])


@router.post("/analyze/{pair}")
async def analyze_pair(pair: str, db: Session = Depends(get_db)):
    """Manually trigger deep analysis for a single forex pair."""
    pair = pair.upper().replace("-", "_")
    if pair not in FOREX_PAIRS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown pair '{pair}'. Valid pairs: {FOREX_PAIRS}",
        )
    result = await run_single_pair(db, pair)
    return result


@router.get("/")
def get_active_signals(db: Session = Depends(get_db)):
    """Return all currently active trade recommendations."""
    signals = (
        db.query(Signal)
        .filter(Signal.status.in_(["active", "executed"]))
        .order_by(Signal.created_at.desc())
        .all()
    )
    return [_signal_to_dict(s) for s in signals]


@router.get("/history")
def get_signal_history(
    limit: int = 50,
    instrument: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Return historical signals with optional instrument filter."""
    query = db.query(Signal).order_by(Signal.created_at.desc())
    if instrument:
        query = query.filter(Signal.instrument == instrument.upper())
    signals = query.limit(limit).all()
    return [_signal_to_dict(s) for s in signals]


@router.get("/schedule")
def get_schedule():
    """Return current market status and scheduled scan info."""
    status = get_market_status()
    settings = get_settings()
    return {
        **status,
        "execution_mode": settings.execution_mode,
        "scan_schedule": "Every 4 hours at :00 UTC (00, 04, 08, 12, 16, 20)",
        "news_sentinel_schedule": "Daily at 6:00 AM ET and 4:00 PM ET",
        "valid_pairs": FOREX_PAIRS,
    }


@router.post("/settings/mode")
def set_execution_mode(mode: str, db: Session = Depends(get_db)):
    """Switch execution mode (ALERT_ONLY / SEMI_AUTO / FULL_AUTO)."""
    valid_modes = ("ALERT_ONLY", "SEMI_AUTO", "FULL_AUTO")
    mode = mode.upper()
    if mode not in valid_modes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{mode}'. Valid: {valid_modes}",
        )
    settings = get_settings()
    settings.execution_mode = mode  # type: ignore[attr-defined]
    return {"execution_mode": mode, "note": "Mode updated for this session only. Update .env for persistence."}


# ── Approve / Reject endpoints ────────────────────────────────────────────────

@router.post("/{signal_id}/approve")
async def approve_signal(signal_id: int, db: Session = Depends(get_db)):
    """Approve a signal for execution (SEMI_AUTO mode). Places the trade on OANDA."""
    signal = db.query(Signal).filter(Signal.id == signal_id).first()
    if not signal:
        raise HTTPException(404, f"Signal {signal_id} not found")

    if signal.status not in ("active",):
        raise HTTPException(400, f"Signal {signal_id} is not active (status={signal.status})")

    if not signal.risk_approved:
        raise HTTPException(400, f"Signal {signal_id} was not risk-approved")

    from backend.app.services.trade_manager import execute_signal_trade

    try:
        trade = await execute_signal_trade(db, signal_id)
    except ValueError as exc:
        raise HTTPException(502, str(exc))

    signal.execution_status = "approved"
    signal.approved_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "status": "executed",
        "signal_id": signal_id,
        "trade_id": trade.id,
        "oanda_trade_id": trade.oanda_trade_id,
        "instrument": trade.instrument,
        "direction": trade.direction,
        "entry_price": trade.entry_price,
        "units": trade.units,
    }


@router.post("/{signal_id}/reject")
def reject_signal(signal_id: int, db: Session = Depends(get_db)):
    """Reject/dismiss a signal (SEMI_AUTO mode)."""
    signal = db.query(Signal).filter(Signal.id == signal_id).first()
    if not signal:
        raise HTTPException(404, f"Signal {signal_id} not found")

    signal.status = "rejected"
    signal.execution_status = "rejected"
    signal.rejected_at = datetime.now(timezone.utc)
    db.commit()

    return {"status": "rejected", "signal_id": signal_id}


def _signal_to_dict(s: Signal) -> dict:
    rejection_reasons = []
    if s.risk_rejection_reasons:
        try:
            rejection_reasons = json.loads(s.risk_rejection_reasons)
        except Exception:
            rejection_reasons = [s.risk_rejection_reasons]

    return {
        "id": s.id,
        "instrument": s.instrument,
        "direction": s.direction,
        "entry_price": s.entry_price,
        "stop_loss": s.stop_loss,
        "take_profit_1": s.take_profit_1,
        "take_profit_2": s.take_profit_2,
        "confidence": s.confidence,
        "session": s.session,
        "position_size": s.position_size,
        "risk_amount": s.risk_amount,
        "risk_reward_ratio": s.risk_reward_ratio,
        "risk_approved": s.risk_approved,
        "rejection_reasons": rejection_reasons,
        "status": s.status,
        "execution_status": s.execution_status,
        "is_news_blackout": s.is_news_blackout,
        "reasoning": s.reasoning,
        "screener_reason": s.screener_reason,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "trade_id": s.trade_id,
    }
