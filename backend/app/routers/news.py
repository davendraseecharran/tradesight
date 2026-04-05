from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.agents.news_sentinel import get_upcoming_events, run_news_sentinel
from backend.app.database import get_db
from backend.app.models.news_event import NewsEvent

router = APIRouter(prefix="/api/v1/news", tags=["news"])


@router.get("/calendar")
def get_calendar(hours_ahead: int = 48, db: Session = Depends(get_db)):
    """Return upcoming high-impact news events within the next N hours."""
    events = get_upcoming_events(db, hours_ahead=hours_ahead)
    return [_event_to_dict(e) for e in events]


@router.post("/refresh")
async def refresh_calendar(db: Session = Depends(get_db)):
    """Manually trigger News Sentinel to refresh the economic calendar."""
    result = await run_news_sentinel(db)
    return result


def _event_to_dict(e: NewsEvent) -> dict:
    return {
        "id": e.id,
        "event": e.event,
        "currency": e.currency,
        "impact": e.impact,
        "event_datetime": e.event_datetime.isoformat() if e.event_datetime else None,
        "blackout_start": e.blackout_start.isoformat() if e.blackout_start else None,
        "blackout_end": e.blackout_end.isoformat() if e.blackout_end else None,
        "source": e.source,
        "fetched_at": e.fetched_at.isoformat() if e.fetched_at else None,
    }
