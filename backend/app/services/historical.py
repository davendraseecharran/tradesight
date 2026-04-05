from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from backend.app.config import FOREX_PAIRS, OANDA_GRANULARITIES, TIMEFRAMES
from backend.app.models.candle import Candle
from backend.app.services.oanda import OandaClient


async def fetch_historical_candles(
    instrument: str,
    granularity: str,
    months: int = 6,
    client: Optional[OandaClient] = None,
) -> list[dict]:
    """Fetch `months` of historical candles with pagination for OANDA's 5000-candle limit."""
    oanda_gran = OANDA_GRANULARITIES.get(granularity, granularity)
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=months * 30)

    own_client = client is None
    if own_client:
        client = OandaClient()

    all_candles = []
    chunk_start = start

    try:
        while chunk_start < now:
            candles = await client.get_candles(
                instrument=instrument,
                granularity=oanda_gran,
                count=5000,
                from_time=chunk_start.isoformat(),
                to_time=now.isoformat(),
            )
            if not candles:
                break

            all_candles.extend(candles)

            # Advance past the last candle's timestamp
            last_ts = candles[-1]["timestamp"]
            chunk_start = last_ts + timedelta(seconds=1)

            # If we got fewer than 5000, we've reached the end
            if len(candles) < 5000:
                break
    finally:
        if own_client:
            await client.close()

    # Deduplicate by timestamp (in case of overlap)
    seen = set()
    deduped = []
    for c in all_candles:
        ts = c["timestamp"]
        if ts not in seen:
            seen.add(ts)
            deduped.append(c)

    return deduped


def store_candles_bulk(
    db: Session,
    candles: list[dict],
    instrument: str,
    granularity: str,
) -> int:
    """Upsert candles into the Candle table. Returns count stored."""
    oanda_gran = OANDA_GRANULARITIES.get(granularity, granularity)
    for c in candles:
        stmt = sqlite_insert(Candle).values(
            instrument=instrument,
            source="oanda",
            granularity=oanda_gran,
            timestamp=c["timestamp"],
            open=c["open"],
            high=c["high"],
            low=c["low"],
            close=c["close"],
            volume=c["volume"],
            complete=c.get("complete", True),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["instrument", "granularity", "timestamp"],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
                "complete": stmt.excluded.complete,
            },
        )
        db.execute(stmt)
    db.commit()
    return len(candles)


async def fetch_all_historical(
    pairs: Optional[list[str]] = None,
    timeframes: Optional[list[str]] = None,
    months: int = 6,
) -> dict[str, int]:
    """Fetch historical data for all pairs x timeframes. Returns {pair_tf: count}."""
    pairs = pairs or FOREX_PAIRS
    timeframes = timeframes or TIMEFRAMES
    results = {}

    from backend.app.database import SessionLocal

    db = SessionLocal()
    try:
        async with OandaClient() as client:
            for pair in pairs:
                for tf in timeframes:
                    key = f"{pair}_{tf}"
                    print(f"  Fetching {key}...")
                    candles = await fetch_historical_candles(pair, tf, months, client)
                    count = store_candles_bulk(db, candles, pair, tf)
                    results[key] = count
                    print(f"  {key}: {count} candles stored")
                    await asyncio.sleep(0.5)  # Rate limit courtesy
    finally:
        db.close()

    return results


def load_candles_as_dataframe(
    db: Session,
    instrument: str,
    granularity: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> pd.DataFrame:
    """Query Candle table and return as a sorted DataFrame."""
    oanda_gran = OANDA_GRANULARITIES.get(granularity, granularity)
    query = (
        db.query(Candle)
        .filter(
            Candle.instrument == instrument,
            Candle.granularity == oanda_gran,
            Candle.complete == True,  # noqa: E712
        )
    )
    if start_date:
        query = query.filter(Candle.timestamp >= start_date)
    if end_date:
        query = query.filter(Candle.timestamp <= end_date)

    rows = query.order_by(Candle.timestamp.asc()).all()

    if not rows:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    data = [
        {
            "timestamp": r.timestamp,
            "open": r.open,
            "high": r.high,
            "low": r.low,
            "close": r.close,
            "volume": r.volume,
        }
        for r in rows
    ]
    return pd.DataFrame(data)
