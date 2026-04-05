from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String

from backend.app.database import Base


class ApiCall(Base):
    __tablename__ = "api_calls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent = Column(String(50), nullable=False)           # screener, analyst, news_sentinel
    model = Column(String(60), nullable=False)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cache_read_tokens = Column(Integer, default=0)       # usage.cache_read_input_tokens
    cache_write_tokens = Column(Integer, default=0)      # usage.cache_creation_input_tokens
    cost_usd = Column(Float, nullable=False)
    instrument = Column(String(20), nullable=True)
    timestamp = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
