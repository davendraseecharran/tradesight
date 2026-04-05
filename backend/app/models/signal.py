from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text

from backend.app.database import Base


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    instrument = Column(String(20), index=True, nullable=False)
    direction = Column(String(5), nullable=False)        # "long" / "short"
    entry_price = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    take_profit_1 = Column(Float, nullable=False)
    take_profit_2 = Column(Float, nullable=True)
    confidence = Column(Integer, nullable=False)          # Analyst score 1–10
    session = Column(String(20), nullable=True)          # e.g. "London"
    valid_until = Column(DateTime, nullable=True)
    reasoning = Column(Text, nullable=True)
    screener_reason = Column(Text, nullable=True)
    position_size = Column(Float, nullable=True)         # in lots
    risk_amount = Column(Float, nullable=True)           # in USD
    risk_reward_ratio = Column(Float, nullable=True)
    risk_approved = Column(Boolean, default=False)
    risk_rejection_reasons = Column(Text, nullable=True) # JSON array string
    status = Column(String(20), default="active")        # active/expired/cancelled/executed/rejected
    is_news_blackout = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Phase 5: Execution tracking
    execution_status = Column(String(20), nullable=True)  # pending_approval/approved/rejected/executed
    approved_at = Column(DateTime, nullable=True)
    rejected_at = Column(DateTime, nullable=True)
    trade_id = Column(Integer, nullable=True)  # FK to trades table
