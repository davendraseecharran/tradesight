from __future__ import annotations

from sqlalchemy import Column, Float, ForeignKey, Integer
from sqlalchemy.orm import relationship

from backend.app.database import Base


class Indicator(Base):
    __tablename__ = "indicators"

    id = Column(Integer, primary_key=True, autoincrement=True)
    candle_id = Column(Integer, ForeignKey("candles.id"), unique=True, index=True, nullable=False)

    # Momentum
    rsi_14 = Column(Float, nullable=True)

    # MACD
    macd_line = Column(Float, nullable=True)
    macd_signal = Column(Float, nullable=True)
    macd_histogram = Column(Float, nullable=True)

    # EMAs
    ema_20 = Column(Float, nullable=True)
    ema_50 = Column(Float, nullable=True)
    ema_200 = Column(Float, nullable=True)

    # Bollinger Bands
    bb_upper = Column(Float, nullable=True)
    bb_middle = Column(Float, nullable=True)
    bb_lower = Column(Float, nullable=True)

    # Volatility
    atr_14 = Column(Float, nullable=True)

    # Volume
    vwap = Column(Float, nullable=True)

    # Ichimoku
    ichimoku_tenkan = Column(Float, nullable=True)
    ichimoku_kijun = Column(Float, nullable=True)
    ichimoku_senkou_a = Column(Float, nullable=True)
    ichimoku_senkou_b = Column(Float, nullable=True)

    candle = relationship("Candle", backref="indicators")
