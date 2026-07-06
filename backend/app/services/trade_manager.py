from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.models.trade import Trade
from backend.app.services.order_manager import OrderManager

logger = logging.getLogger(__name__)


class TradeManager:
    """
    Monitors open trades and manages their lifecycle:
    - Breakeven stop: when price moves 1x risk in profit, move SL to entry
    - Trailing stop: when price moves 2x risk in profit, trail SL at 1x risk distance
    - Partial take profit: close 50% at TP1, let rest run to TP2
    """

    def __init__(self, db: Session):
        self.db = db
        self.order_mgr = OrderManager()

    async def check_and_manage_trades(self) -> dict:
        """
        Main lifecycle check. Called every 5 minutes by the scheduler.
        Queries OANDA for current state, updates local DB, applies rules.
        """
        summary = {"checked": 0, "breakeven_applied": 0, "trailing_applied": 0, "partial_closes": 0, "closed": 0, "errors": []}

        open_trades = self.db.query(Trade).filter(Trade.status.in_(["open", "partial_close"])).all()
        if not open_trades:
            return summary

        for trade in open_trades:
            summary["checked"] += 1
            try:
                await self._manage_single_trade(trade, summary)
            except Exception as exc:
                logger.error("TradeManager: error managing trade %s: %s", trade.oanda_trade_id, exc)
                summary["errors"].append(f"trade {trade.oanda_trade_id}: {exc}")

        self.db.commit()
        return summary

    async def _manage_single_trade(self, trade: Trade, summary: dict):
        """Apply lifecycle rules to a single trade."""
        if not trade.oanda_trade_id:
            return

        # Fetch current state from OANDA
        try:
            oanda_trade = await self.order_mgr.get_trade(trade.oanda_trade_id)
        except Exception:
            # Trade might have been closed by SL/TP
            await self._check_if_closed(trade, summary)
            return

        state = oanda_trade.get("state", "OPEN")
        if state == "CLOSED":
            await self._handle_closed_trade(trade, oanda_trade, summary)
            return

        current_units = abs(float(oanda_trade.get("currentUnits", 0)))
        if current_units == 0:
            await self._handle_closed_trade(trade, oanda_trade, summary)
            return

        unrealized_pl = float(oanda_trade.get("unrealizedPL", 0))
        current_price = float(oanda_trade.get("price", trade.entry_price or 0))

        # Calculate risk distance
        if not trade.entry_price or not trade.recommended_sl:
            return
        risk_distance = abs(trade.entry_price - trade.recommended_sl)
        if risk_distance == 0:
            return

        # Calculate how far price has moved in profit direction
        if trade.direction == "long":
            profit_distance = current_price - trade.entry_price
        else:
            profit_distance = trade.entry_price - current_price

        profit_ratio = profit_distance / risk_distance if risk_distance > 0 else 0

        # ── Rule 1: Partial close at TP1 (50%) ──────────────────────────────
        if (
            not trade.partial_close_done
            and trade.recommended_tp1
            and profit_ratio >= 1.0
        ):
            await self._apply_partial_close(trade, summary)

        # ── Rule 2: Breakeven stop at 1x risk ───────────────────────────────
        if not trade.breakeven_applied and profit_ratio >= 1.0:
            await self._apply_breakeven(trade, summary)

        # ── Rule 3: Trailing stop at 2x risk ────────────────────────────────
        if trade.breakeven_applied and profit_ratio >= 2.0:
            await self._apply_trailing_stop(trade, current_price, risk_distance, summary)

    async def _apply_partial_close(self, trade: Trade, summary: dict):
        """Close 50% of position at TP1."""
        try:
            result = await self.order_mgr.close_trade_partial(trade.oanda_trade_id, 0.5)
            trade.partial_close_done = True
            trade.status = "partial_close"
            trade.notes = (trade.notes or "") + f"\nPartial close 50% @ {result['price']:.5f}, PL: ${result['realized_pl']:.2f}"
            summary["partial_closes"] += 1
            logger.info("TradeManager: partial close for trade %s @ %.5f", trade.oanda_trade_id, result["price"])

            # Update TP to TP2 for remaining position
            if trade.recommended_tp2:
                await self.order_mgr.modify_trade(trade.oanda_trade_id, take_profit=trade.recommended_tp2)
        except Exception as exc:
            logger.error("TradeManager: partial close failed for %s: %s", trade.oanda_trade_id, exc)

    async def _apply_breakeven(self, trade: Trade, summary: dict):
        """Move SL to entry price."""
        try:
            await self.order_mgr.move_sl_to_breakeven(trade.oanda_trade_id, trade.entry_price)
            trade.breakeven_applied = True
            trade.stop_loss = trade.entry_price
            trade.notes = (trade.notes or "") + f"\nBreakeven SL applied @ {trade.entry_price:.5f}"
            summary["breakeven_applied"] += 1
            logger.info("TradeManager: breakeven applied for trade %s", trade.oanda_trade_id)
        except Exception as exc:
            logger.error("TradeManager: breakeven failed for %s: %s", trade.oanda_trade_id, exc)

    async def _apply_trailing_stop(self, trade: Trade, current_price: float, risk_distance: float, summary: dict):
        """Trail SL at 1x risk distance behind current price."""
        if trade.direction == "long":
            new_sl = current_price - risk_distance
        else:
            new_sl = current_price + risk_distance

        # Only move SL if it improves (closer to current price)
        current_sl = trade.stop_loss or trade.recommended_sl
        if current_sl:
            if trade.direction == "long" and new_sl <= current_sl:
                return
            if trade.direction == "short" and new_sl >= current_sl:
                return

        try:
            await self.order_mgr.set_trailing_stop(trade.oanda_trade_id, new_sl)
            trade.trailing_stop_applied = True
            trade.stop_loss = new_sl
            trade.notes = (trade.notes or "") + f"\nTrailing SL updated to {new_sl:.5f}"
            summary["trailing_applied"] += 1
        except Exception as exc:
            logger.error("TradeManager: trailing stop failed for %s: %s", trade.oanda_trade_id, exc)

    async def _check_if_closed(self, trade: Trade, summary: dict):
        """Check if a trade was closed by SL/TP hit on OANDA side."""
        try:
            oanda_trade = await self.order_mgr.get_trade(trade.oanda_trade_id)
            if oanda_trade.get("state") == "CLOSED":
                await self._handle_closed_trade(trade, oanda_trade, summary)
        except Exception:
            pass  # Trade might not exist anymore

    async def _handle_closed_trade(self, trade: Trade, oanda_trade: dict, summary: dict):
        """Mark a trade as closed in our DB."""
        realized_pl = float(oanda_trade.get("realizedPL", 0))

        trade.status = "closed"
        trade.actual_pnl = realized_pl
        trade.closed_at = datetime.now(timezone.utc)

        # Determine exit reason from close price
        close_price = float(oanda_trade.get("averageClosePrice", 0))
        trade.actual_exit_price = close_price

        if trade.recommended_sl and close_price:
            sl_dist = abs(close_price - trade.recommended_sl)
            if trade.recommended_tp1:
                tp1_dist = abs(close_price - trade.recommended_tp1)
            else:
                tp1_dist = float("inf")
            if trade.recommended_tp2:
                tp2_dist = abs(close_price - trade.recommended_tp2)
            else:
                tp2_dist = float("inf")

            if trade.breakeven_applied and trade.entry_price and abs(close_price - trade.entry_price) < sl_dist:
                trade.exit_reason = "breakeven"
            elif trade.trailing_stop_applied and realized_pl > 0:
                trade.exit_reason = "trailing_stop"
            elif tp1_dist < sl_dist and tp1_dist < tp2_dist:
                trade.exit_reason = "tp1_hit"
            elif tp2_dist < sl_dist:
                trade.exit_reason = "tp2_hit"
            elif sl_dist <= tp1_dist:
                trade.exit_reason = "sl_hit"
            else:
                trade.exit_reason = "manual_close"
        else:
            trade.exit_reason = "manual_close"

        # Calculate slippage
        if trade.entry_price and trade.recommended_entry:
            trade.slippage = trade.entry_price - trade.recommended_entry

        summary["closed"] += 1
        logger.info(
            "TradeManager: trade %s closed — reason=%s, PL=$%.2f",
            trade.oanda_trade_id, trade.exit_reason, realized_pl,
        )


async def execute_signal_trade(db: Session, signal_id: int) -> Trade:
    """
    Execute a trade for an approved signal. Creates a Trade record and
    places the order on OANDA.
    """
    from backend.app.models.signal import Signal

    signal = db.query(Signal).filter(Signal.id == signal_id).first()
    if not signal:
        raise ValueError(f"Signal {signal_id} not found")
    if signal.status not in ("active",):
        raise ValueError(f"Signal {signal_id} is not active (status={signal.status})")

    order_mgr = OrderManager()

    # Get account balance for snapshot
    acct = await order_mgr.get_account_summary()

    # Determine lots and units
    lots = signal.position_size or 0.01
    from backend.app.services.order_manager import lots_to_units
    units = lots_to_units(lots, signal.instrument)
    if signal.direction == "short":
        units = -units

    # Create trade record (pending)
    trade = Trade(
        signal_id=signal.id,
        instrument=signal.instrument,
        direction=signal.direction,
        recommended_entry=signal.entry_price,
        recommended_sl=signal.stop_loss,
        recommended_tp1=signal.take_profit_1,
        recommended_tp2=signal.take_profit_2,
        units=abs(units),
        position_size=lots,
        risk_amount=signal.risk_amount,
        risk_reward_ratio=signal.risk_reward_ratio,
        status="pending",
        account_balance_at_open=acct["balance"],
    )
    db.add(trade)
    db.flush()

    # Place the order on OANDA
    try:
        result = await order_mgr.place_market_order(
            instrument=signal.instrument,
            units=units,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit_1,  # Initial TP at TP1
        )

        trade.oanda_trade_id = result["trade_id"]
        trade.entry_price = result["price"]
        trade.stop_loss = signal.stop_loss
        trade.take_profit = signal.take_profit_1
        trade.status = "open"
        trade.opened_at = datetime.now(timezone.utc)
        trade.slippage = result["price"] - signal.entry_price if signal.entry_price else None

        # Update signal
        signal.status = "executed"
        signal.execution_status = "executed"
        signal.trade_id = trade.id

        db.commit()
        db.refresh(trade)

        logger.info(
            "TradeManager: executed signal %d → trade %s @ %.5f (slippage: %.5f)",
            signal.id, trade.oanda_trade_id, trade.entry_price,
            trade.slippage or 0,
        )
        return trade

    except Exception as exc:
        trade.status = "failed"
        trade.notes = f"Order placement failed: {exc}"
        db.commit()
        raise ValueError(f"Order placement failed: {exc}") from exc
