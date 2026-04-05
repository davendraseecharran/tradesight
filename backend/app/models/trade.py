from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text

from backend.app.database import Base


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_id = Column(Integer, nullable=True, index=True)  # FK to signals table

    # OANDA trade info
    oanda_trade_id = Column(String(30), nullable=True, unique=True, index=True)
    instrument = Column(String(20), nullable=False, index=True)
    direction = Column(String(5), nullable=False)  # "long" / "short"

    # Recommended prices (from signal)
    recommended_entry = Column(Float, nullable=True)
    recommended_sl = Column(Float, nullable=True)
    recommended_tp1 = Column(Float, nullable=True)
    recommended_tp2 = Column(Float, nullable=True)

    # Actual fill prices
    entry_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)

    # Position
    units = Column(Float, nullable=False)  # OANDA units (not lots)
    position_size = Column(Float, nullable=True)  # in lots
    risk_amount = Column(Float, nullable=True)  # in USD
    risk_reward_ratio = Column(Float, nullable=True)

    # Status tracking
    status = Column(String(20), default="pending", nullable=False)
    # pending → open → partial_close → closed
    exit_reason = Column(String(30), nullable=True)
    # tp1_hit / tp2_hit / sl_hit / trailing_stop / manual_close / breakeven

    # Actual P&L
    actual_exit_price = Column(Float, nullable=True)
    actual_pnl = Column(Float, nullable=True)
    slippage = Column(Float, nullable=True)  # entry slippage in price

    # Lifecycle flags
    breakeven_applied = Column(Boolean, default=False)
    trailing_stop_applied = Column(Boolean, default=False)
    partial_close_done = Column(Boolean, default=False)
    partial_close_trade_id = Column(String(30), nullable=True)  # OANDA ID of remaining half

    # Account snapshot
    account_balance_at_open = Column(Float, nullable=True)

    # Timestamps
    opened_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Notes / log
    notes = Column(Text, nullable=True)
