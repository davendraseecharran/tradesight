from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.models.trade import Trade


def _get_pip_size(instrument: str) -> float:
    """Return pip size: JPY pairs 0.01, gold (XAU) 0.1, others 0.0001."""
    if "JPY" in instrument:
        return 0.01
    if instrument.startswith("XAU"):
        return 0.1
    return 0.0001


def _is_crypto(instrument: str) -> bool:
    return instrument.endswith("USDT")


class RiskManager:
    def __init__(self, db: Session, settings=None):
        self._db = db
        self._s = settings or get_settings()

    def calculate_position_size(
        self,
        account_balance: float,
        entry_price: float,
        stop_loss_price: float,
        risk_percent: Optional[float] = None,
    ) -> float:
        risk_pct = risk_percent or self._s.max_risk_per_trade
        risk_amount = account_balance * risk_pct
        distance = abs(entry_price - stop_loss_price)
        if distance == 0:
            return 0.0
        return risk_amount / distance

    def check_daily_loss_limit(self, account_balance: float, starting_balance: float) -> bool:
        """Return True if within the daily loss limit."""
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        daily_loss = (
            self._db.query(func.sum(Trade.actual_pnl))
            .filter(Trade.closed_at >= today_start, Trade.actual_pnl < 0)
            .scalar()
        ) or 0.0
        max_loss = starting_balance * self._s.daily_loss_limit
        return abs(daily_loss) < max_loss

    def check_max_positions(self) -> bool:
        """Return True if we can open another position."""
        open_count = self._db.query(Trade).filter(Trade.status == "open").count()
        return open_count < self._s.max_open_positions

    def check_risk_reward(
        self, entry: float, stop_loss: float, take_profit: float
    ) -> tuple[bool, float]:
        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)
        if risk == 0:
            return False, 0.0
        ratio = round(reward / risk, 2)
        return ratio >= self._s.min_risk_reward_ratio, ratio

    def check_news_blackout(self, trade_time: Optional[datetime] = None) -> bool:
        """Stub — always passes in Phase 1. TODO: integrate economic calendar."""
        return True

    def validate_trade(
        self,
        account_balance: float,
        starting_balance: float,
        entry: float,
        stop_loss: float,
        take_profit: float,
        instrument: str = "",
    ) -> dict:
        rejection_reasons = []

        # Risk-reward check
        rr_ok, rr_ratio = self.check_risk_reward(entry, stop_loss, take_profit)
        if not rr_ok:
            rejection_reasons.append(
                f"Risk-reward ratio {rr_ratio} below minimum {self._s.min_risk_reward_ratio}"
            )

        # Daily loss limit
        if not self.check_daily_loss_limit(account_balance, starting_balance):
            rejection_reasons.append("Daily loss limit reached")

        # Max positions
        if not self.check_max_positions():
            rejection_reasons.append(
                f"Max open positions ({self._s.max_open_positions}) reached"
            )

        # News blackout
        if not self.check_news_blackout():
            rejection_reasons.append("Within news blackout window")

        # Position size
        position_size = self.calculate_position_size(account_balance, entry, stop_loss)
        risk_amount = account_balance * self._s.max_risk_per_trade

        return {
            "approved": len(rejection_reasons) == 0,
            "position_size": round(position_size, 4),
            "risk_amount": round(risk_amount, 2),
            "risk_reward_ratio": rr_ratio,
            "rejection_reasons": rejection_reasons,
        }
