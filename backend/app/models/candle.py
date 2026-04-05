from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, UniqueConstraint

from backend.app.database import Base


class Candle(Base):
    __tablename__ = "candles"
    __table_args__ = (
        UniqueConstraint("instrument", "granularity", "timestamp", name="uq_candle"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    instrument = Column(String(20), index=True, nullable=False)
    source = Column(String(10), nullable=False)  # "oanda" or "binance"
    granularity = Column(String(5), nullable=False)  # H1, H4, D, W
    timestamp = Column(DateTime, index=True, nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    complete = Column(Boolean, default=True)
