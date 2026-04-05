from __future__ import annotations

import math

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from backend.app.config import (
    BINANCE_INTERVALS,
    CRYPTO_PAIRS,
    FOREX_PAIRS,
    OANDA_GRANULARITIES,
    TIMEFRAMES,
)
from backend.app.database import get_db
from backend.app.models.candle import Candle
from backend.app.models.indicator import Indicator
from backend.app.schemas import CandleResponse, CandleWithIndicators, IndicatorResponse
from backend.app.services.binance import BinanceClient
from backend.app.services.indicators import compute_indicators
from backend.app.services.oanda import OandaClient

router = APIRouter(prefix="/candles", tags=["Market Data"])


def _safe_float(val) -> float | None:
    """Convert a value to float, returning None for NaN."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    return float(val)


async def _fetch_candles(source: str, instrument: str, granularity: str, count: int) -> list[dict]:
    if source == "oanda":
        oanda_gran = OANDA_GRANULARITIES.get(granularity, granularity)
        async with OandaClient() as client:
            return await client.get_candles(instrument, oanda_gran, count)
    elif source == "binance":
        binance_interval = BINANCE_INTERVALS.get(granularity, granularity)
        async with BinanceClient() as client:
            return await client.get_klines(instrument, binance_interval, count)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown source: {source}")


def _store_candles(db: Session, candles: list[dict], instrument: str, source: str, granularity: str) -> list[Candle]:
    """Upsert candles into the database and return the ORM objects."""
    oanda_gran = OANDA_GRANULARITIES.get(granularity, granularity)
    stored = []
    for c in candles:
        stmt = sqlite_insert(Candle).values(
            instrument=instrument,
            source=source,
            granularity=oanda_gran if source == "oanda" else granularity,
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

    # Fetch back the stored candles
    oanda_gran_val = oanda_gran if source == "oanda" else granularity
    stored = (
        db.query(Candle)
        .filter(
            Candle.instrument == instrument,
            Candle.granularity == oanda_gran_val,
        )
        .order_by(Candle.timestamp.desc())
        .limit(len(candles))
        .all()
    )
    stored.reverse()
    return stored


@router.get("/{source}/{instrument}", response_model=list[CandleResponse])
async def get_candles(
    source: str,
    instrument: str,
    granularity: str = Query(default="4H", description="Timeframe: 1H, 4H, D, W"),
    count: int = Query(default=100, ge=1, le=5000),
    db: Session = Depends(get_db),
):
    raw_candles = await _fetch_candles(source, instrument, granularity, count)
    stored = _store_candles(db, raw_candles, instrument, source, granularity)
    return stored


@router.get("/indicators/{source}/{instrument}", response_model=list[CandleWithIndicators])
async def get_indicators(
    source: str,
    instrument: str,
    granularity: str = Query(default="4H"),
    count: int = Query(default=100, ge=1, le=5000),
    db: Session = Depends(get_db),
):
    raw_candles = await _fetch_candles(source, instrument, granularity, count)
    stored = _store_candles(db, raw_candles, instrument, source, granularity)

    # Build DataFrame for indicator computation
    df = pd.DataFrame([{
        "open": c.open, "high": c.high, "low": c.low,
        "close": c.close, "volume": c.volume,
    } for c in stored])

    df = compute_indicators(df, timeframe=granularity)

    # Store indicators
    results = []
    indicator_cols = [
        "rsi_14", "macd_line", "macd_signal", "macd_histogram",
        "ema_20", "ema_50", "ema_200",
        "bb_upper", "bb_middle", "bb_lower",
        "atr_14", "vwap",
        "ichimoku_tenkan", "ichimoku_kijun", "ichimoku_senkou_a", "ichimoku_senkou_b",
    ]

    for i, candle in enumerate(stored):
        row = df.iloc[i] if i < len(df) else None
        ind_data = {}
        if row is not None:
            for col in indicator_cols:
                ind_data[col] = _safe_float(row.get(col))

        # Upsert indicator
        existing = db.query(Indicator).filter(Indicator.candle_id == candle.id).first()
        if existing:
            for k, v in ind_data.items():
                setattr(existing, k, v)
        else:
            existing = Indicator(candle_id=candle.id, **ind_data)
            db.add(existing)

        results.append(CandleWithIndicators(
            candle=CandleResponse.model_validate(candle),
            indicators=IndicatorResponse(**ind_data) if ind_data else None,
        ))

    db.commit()
    return results


async def _fetch_all_task(db: Session):
    """Background task to fetch all pairs across all timeframes."""
    for instrument in FOREX_PAIRS:
        for tf in TIMEFRAMES:
            try:
                raw = await _fetch_candles("oanda", instrument, tf, 200)
                _store_candles(db, raw, instrument, "oanda", tf)
            except Exception as e:
                print(f"Error fetching {instrument} {tf}: {e}")

    for instrument in CRYPTO_PAIRS:
        for tf in TIMEFRAMES:
            try:
                raw = await _fetch_candles("binance", instrument, tf, 200)
                _store_candles(db, raw, instrument, "binance", tf)
            except Exception as e:
                print(f"Error fetching {instrument} {tf}: {e}")


@router.post("/fetch-all", status_code=202)
async def fetch_all(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    background_tasks.add_task(_fetch_all_task, db)
    return {"message": "Fetching all pairs and timeframes in background"}
