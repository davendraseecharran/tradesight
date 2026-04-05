from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint

from backend.app.database import Base


class NewsEvent(Base):
    __tablename__ = "news_events"
    __table_args__ = (
        UniqueConstraint("event", "currency", "event_datetime", name="uq_news_event"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    event = Column(String(200), nullable=False)
    currency = Column(String(10), nullable=False)
    impact = Column(String(10), nullable=False)          # "high" / "medium" / "low"
    event_datetime = Column(DateTime, nullable=False, index=True)
    blackout_start = Column(DateTime, nullable=False)
    blackout_end = Column(DateTime, nullable=False)
    source = Column(String(20), default="forexfactory")
    fetched_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
