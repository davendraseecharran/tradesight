from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from backend.app.models.news_event import NewsEvent

logger = logging.getLogger(__name__)

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

# Currencies we care about (matches our 6 forex pairs)
TRACKED_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "AUD", "CAD"}


async def fetch_ff_raw() -> list[dict]:
    """Fetch raw ForexFactory calendar JSON with retry on rate-limit."""
    import asyncio

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=15, headers=headers) as client:
        for attempt in range(3):
            resp = await client.get(FF_URL)
            if resp.status_code == 429:
                wait = (attempt + 1) * 5
                logger.warning("FF rate-limited, retrying in %ds...", wait)
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        raise httpx.HTTPStatusError(
            "ForexFactory rate-limited after 3 retries", request=resp.request, response=resp
        )


def _parse_ff_time(date_str: str, time_str: str | None) -> datetime | None:
    """Parse ForexFactory date/time strings into UTC datetime.

    FF dates: "MM-DD-YYYY" (or similar)
    FF times: "8:30am", "10:00pm", "All Day", "Tentative", or empty
    FF times are in US Eastern (EST/EDT).
    """
    if not date_str:
        return None

    # Parse date
    try:
        base_date = datetime.strptime(date_str.strip(), "%m-%d-%Y")
    except ValueError:
        try:
            base_date = datetime.strptime(date_str.strip(), "%Y-%m-%dT%H:%M:%S%z")
            return base_date.astimezone(timezone.utc)
        except ValueError:
            logger.warning("Cannot parse FF date: %s", date_str)
            return None

    # Parse time
    if not time_str or time_str.strip().lower() in ("", "all day", "tentative"):
        hour, minute = 12, 0  # Default to noon ET
    else:
        t = time_str.strip().lower().replace(" ", "")
        try:
            parsed_t = datetime.strptime(t, "%I:%M%p")
            hour, minute = parsed_t.hour, parsed_t.minute
        except ValueError:
            hour, minute = 12, 0

    # Build naive datetime in Eastern
    naive_et = base_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # Determine if DST applies (rough: Mar 2nd Sun – Nov 1st Sun)
    year = naive_et.year
    mar_second_sun = _nth_weekday(year, 3, 6, 2)  # 2nd Sunday in March
    nov_first_sun = _nth_weekday(year, 11, 6, 1)  # 1st Sunday in November
    is_dst = mar_second_sun <= naive_et.replace(hour=2) < nov_first_sun.replace(hour=2)
    offset = timedelta(hours=-4 if is_dst else -5)

    return (naive_et - offset).replace(tzinfo=timezone.utc)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> datetime:
    """Return the n-th occurrence of weekday (0=Mon, 6=Sun) in the given month."""
    first = datetime(year, month, 1)
    day_offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=day_offset + (n - 1) * 7)


def _classify_impact(raw_impact: str) -> str | None:
    """Normalize FF impact string to high/medium/low or None if unrecognized."""
    val = raw_impact.lower().strip()
    if "high" in val:
        return "high"
    if "medium" in val or "moderate" in val:
        return "medium"
    if "low" in val:
        return "low"
    return None


# Blackout windows by impact level (only high gets a real blackout)
_BLACKOUT_MINUTES = {"high": 30, "medium": 0, "low": 0}


def _parse_ff_events(raw_events: list[dict]) -> list[dict]:
    """Filter and parse ForexFactory events in pure Python (no AI needed).

    Stores high, medium, and low impact events. Only high-impact events
    get blackout windows that block trading.
    """
    parsed = []
    for ev in raw_events:
        currency = (ev.get("country") or ev.get("currency") or "").upper()
        if currency not in TRACKED_CURRENCIES:
            continue

        raw_impact = (ev.get("impact") or ev.get("impactTitle") or "").lower()
        impact = _classify_impact(raw_impact)
        if impact is None:
            continue

        title = ev.get("title") or ev.get("event") or "Unknown Event"
        date_str = ev.get("date") or ""
        time_str = ev.get("time") or ""

        event_dt = _parse_ff_time(date_str, time_str)
        if event_dt is None:
            continue

        blackout_mins = _BLACKOUT_MINUTES[impact]
        parsed.append({
            "event": title,
            "currency": currency,
            "impact": impact,
            "event_datetime": event_dt.isoformat(),
            "blackout_start": (event_dt - timedelta(minutes=blackout_mins)).isoformat(),
            "blackout_end": (event_dt + timedelta(minutes=blackout_mins)).isoformat(),
        })

    return parsed


def _upsert_events(db: Session, events: list[dict]) -> int:
    """Upsert parsed events into the news_events table. Returns count inserted/updated."""
    if not events:
        return 0

    now = datetime.now(timezone.utc)
    count = 0
    for ev in events:
        try:
            bs = datetime.fromisoformat(ev["blackout_start"].replace("Z", "+00:00"))
            be = datetime.fromisoformat(ev["blackout_end"].replace("Z", "+00:00"))
            ed = datetime.fromisoformat(ev["event_datetime"].replace("Z", "+00:00"))
            stmt = (
                sqlite_insert(NewsEvent)
                .values(
                    event=ev["event"],
                    currency=ev["currency"],
                    impact=ev["impact"],
                    event_datetime=ed,
                    blackout_start=bs,
                    blackout_end=be,
                    source="forexfactory",
                    fetched_at=now,
                )
                .on_conflict_do_update(
                    index_elements=["event", "currency", "event_datetime"],
                    set_={"blackout_start": bs, "blackout_end": be, "fetched_at": now},
                )
            )
            db.execute(stmt)
            count += 1
        except Exception as exc:
            logger.warning("Skipping malformed event %s: %s", ev, exc)

    db.commit()
    return count


async def run_news_sentinel(db: Session) -> dict:
    """
    Fetch ForexFactory calendar, parse high-impact events in pure Python,
    upsert to DB. Returns summary dict.
    """
    logger.info("News Sentinel: fetching ForexFactory calendar...")
    try:
        raw_events = await fetch_ff_raw()
    except Exception as exc:
        logger.error("News Sentinel: FF fetch failed: %s", exc)
        return {"status": "error", "error": str(exc), "events_stored": 0}

    parsed_events = _parse_ff_events(raw_events)
    count = _upsert_events(db, parsed_events)
    logger.info("News Sentinel: stored %d events from %d raw", count, len(raw_events))

    return {
        "status": "ok",
        "raw_events_fetched": len(raw_events),
        "events_parsed": len(parsed_events),
        "events_stored": count,
    }


def get_active_blackouts(db: Session, instrument: str) -> list[NewsEvent]:
    """Return any active blackout windows for the given instrument's currencies."""
    now = datetime.now(timezone.utc)

    # Map instrument to relevant currencies (e.g. EUR_USD → [EUR, USD])
    parts = instrument.replace("-", "_").split("_")
    currencies = [p[:3].upper() for p in parts if len(p) >= 3]

    if not currencies:
        return []

    return (
        db.query(NewsEvent)
        .filter(
            NewsEvent.currency.in_(currencies),
            NewsEvent.blackout_start <= now,
            NewsEvent.blackout_end >= now,
        )
        .all()
    )


def get_upcoming_events(
    db: Session,
    hours_ahead: int = 168,
    impact_filter: str | None = None,
) -> list[NewsEvent]:
    """Return events within a time window (past week + hours_ahead into future).

    Args:
        impact_filter: If set, only return events with this impact level (high/medium/low).
                       If None, return all impact levels.
    """
    now = datetime.now(timezone.utc)
    lookback = now - timedelta(days=7)
    cutoff = now + timedelta(hours=hours_ahead)

    q = db.query(NewsEvent).filter(
        NewsEvent.event_datetime >= lookback,
        NewsEvent.event_datetime <= cutoff,
    )
    if impact_filter:
        q = q.filter(NewsEvent.impact == impact_filter)

    return q.order_by(NewsEvent.event_datetime).all()
