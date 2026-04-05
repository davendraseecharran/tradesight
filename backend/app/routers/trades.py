from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.trade import Trade
from backend.app.services.order_manager import OrderManager, lots_to_units

router = APIRouter(prefix="/api/v1/trade", tags=["trade"])


class ManualTradeRequest(BaseModel):
    instrument: str
    direction: str  # "long" or "short"
    lots: float = 0.01
    stop_loss: float
    take_profit: float


# ── Execute a manual trade ─────────────────────────────────────────────────

@router.post("/execute")
async def execute_manual_trade(req: ManualTradeRequest, db: Session = Depends(get_db)):
    """Manually execute a trade (pair, direction, lots, SL, TP)."""
    instrument = req.instrument.upper().replace("-", "_")
    if req.direction not in ("long", "short"):
        raise HTTPException(400, "direction must be 'long' or 'short'")
    if req.lots < 0.001 or req.lots > 1.0:
        raise HTTPException(400, "lots must be between 0.001 and 1.0")

    order_mgr = OrderManager()

    try:
        acct = await order_mgr.get_account_summary()
    except Exception as exc:
        raise HTTPException(502, f"OANDA account error: {exc}")

    units = lots_to_units(req.lots)
    if req.direction == "short":
        units = -units

    try:
        result = await order_mgr.place_market_order(
            instrument=instrument,
            units=units,
            stop_loss=req.stop_loss,
            take_profit=req.take_profit,
        )
    except Exception as exc:
        raise HTTPException(502, f"Order placement failed: {exc}")

    from datetime import datetime, timezone

    trade = Trade(
        instrument=instrument,
        direction=req.direction,
        recommended_entry=None,
        recommended_sl=req.stop_loss,
        recommended_tp1=req.take_profit,
        oanda_trade_id=result["trade_id"],
        entry_price=result["price"],
        stop_loss=req.stop_loss,
        take_profit=req.take_profit,
        units=abs(units),
        position_size=req.lots,
        status="open",
        opened_at=datetime.now(timezone.utc),
        account_balance_at_open=acct["balance"],
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)

    return _trade_to_dict(trade)


# ── Open trades from OANDA ─────────────────────────────────────────────────

@router.get("/open")
async def get_open_trades():
    """List open trades from OANDA."""
    order_mgr = OrderManager()
    try:
        trades = await order_mgr.get_open_trades()
    except Exception as exc:
        raise HTTPException(502, f"OANDA error: {exc}")
    return trades


# ── Trade history from OANDA ───────────────────────────────────────────────

@router.get("/history")
async def get_trade_history(count: int = 50, db: Session = Depends(get_db)):
    """Get closed trades from local database."""
    trades = (
        db.query(Trade)
        .filter(Trade.status == "closed")
        .order_by(Trade.closed_at.desc())
        .limit(count)
        .all()
    )
    return [_trade_to_dict(t) for t in trades]


# ── Close a trade ──────────────────────────────────────────────────────────

@router.post("/{trade_id}/close")
async def close_trade(trade_id: str, db: Session = Depends(get_db)):
    """Close a specific trade by OANDA trade ID."""
    order_mgr = OrderManager()
    try:
        result = await order_mgr.close_trade(trade_id)
    except Exception as exc:
        raise HTTPException(502, f"Close failed: {exc}")

    # Update local DB if we have this trade
    trade = db.query(Trade).filter(Trade.oanda_trade_id == trade_id).first()
    if trade:
        from datetime import datetime, timezone
        trade.status = "closed"
        trade.actual_exit_price = result["price"]
        trade.actual_pnl = result["realized_pl"]
        trade.exit_reason = "manual_close"
        trade.closed_at = datetime.now(timezone.utc)
        db.commit()

    return result


# ── Move SL to breakeven ──────────────────────────────────────────────────

@router.post("/{trade_id}/breakeven")
async def move_to_breakeven(trade_id: str, db: Session = Depends(get_db)):
    """Move stop loss to entry price (breakeven) for a trade."""
    trade = db.query(Trade).filter(Trade.oanda_trade_id == trade_id).first()
    if not trade:
        raise HTTPException(404, f"Trade {trade_id} not found in local DB")
    if not trade.entry_price:
        raise HTTPException(400, "No entry price recorded for this trade")

    order_mgr = OrderManager()
    try:
        result = await order_mgr.move_sl_to_breakeven(trade_id, trade.entry_price)
    except Exception as exc:
        raise HTTPException(502, f"Breakeven failed: {exc}")

    trade.breakeven_applied = True
    trade.stop_loss = trade.entry_price
    db.commit()
    return {"trade_id": trade_id, "breakeven_price": trade.entry_price, "status": "applied"}


def _trade_to_dict(t: Trade) -> dict:
    return {
        "id": t.id,
        "signal_id": t.signal_id,
        "oanda_trade_id": t.oanda_trade_id,
        "instrument": t.instrument,
        "direction": t.direction,
        "entry_price": t.entry_price,
        "stop_loss": t.stop_loss,
        "take_profit": t.take_profit,
        "units": t.units,
        "position_size": t.position_size,
        "risk_amount": t.risk_amount,
        "status": t.status,
        "exit_reason": t.exit_reason,
        "actual_exit_price": t.actual_exit_price,
        "actual_pnl": t.actual_pnl,
        "slippage": t.slippage,
        "breakeven_applied": t.breakeven_applied,
        "trailing_stop_applied": t.trailing_stop_applied,
        "partial_close_done": t.partial_close_done,
        "opened_at": t.opened_at.isoformat() if t.opened_at else None,
        "closed_at": t.closed_at.isoformat() if t.closed_at else None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }
