from __future__ import annotations

import math

import pandas as pd
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.config import FOREX_PAIRS, OANDA_GRANULARITIES
from backend.app.database import get_db
from backend.app.services.historical import load_candles_as_dataframe
from backend.app.services.indicators import compute_indicators

router = APIRouter(prefix="/api/v1/chart", tags=["chart"])

_GRAN_MAP = {**OANDA_GRANULARITIES, "H1": "H1", "H4": "H4"}


def _safe(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


@router.get("/candles/{instrument}")
def get_chart_candles(
    instrument: str,
    timeframe: str = Query(default="4H", description="1H, 4H, D, W"),
    count: int = Query(default=200, ge=10, le=1000),
    db: Session = Depends(get_db),
):
    """
    Return stored candle data formatted for TradingView Lightweight Charts.
    Reads from the local SQLite database — no live OANDA call.
    """
    instrument = instrument.upper()
    granularity = OANDA_GRANULARITIES.get(timeframe, timeframe)

    df = load_candles_as_dataframe(db, instrument, granularity)
    if df is None or df.empty:
        return {"candles": [], "instrument": instrument, "timeframe": timeframe}

    df = df.tail(count)

    candles = []
    for _, row in df.iterrows():
        # Lightweight Charts expects Unix timestamp (seconds)
        ts = row["timestamp"]
        if hasattr(ts, "timestamp"):
            time = int(ts.timestamp())
        else:
            time = int(pd.Timestamp(ts).timestamp())

        candles.append({
            "time": time,
            "open": _safe(row["open"]),
            "high": _safe(row["high"]),
            "low": _safe(row["low"]),
            "close": _safe(row["close"]),
            "volume": _safe(row.get("volume", 0)),
        })

    return {
        "instrument": instrument,
        "timeframe": timeframe,
        "granularity": granularity,
        "count": len(candles),
        "candles": candles,
    }


@router.get("/indicators/{instrument}")
def get_chart_indicators(
    instrument: str,
    timeframe: str = Query(default="4H"),
    db: Session = Depends(get_db),
):
    """Return the latest indicator values for the selected pair/timeframe."""
    instrument = instrument.upper()
    granularity = OANDA_GRANULARITIES.get(timeframe, timeframe)

    df = load_candles_as_dataframe(db, instrument, granularity)
    if df is None or df.empty:
        return {"instrument": instrument, "timeframe": timeframe, "indicators": None}

    df = compute_indicators(df, timeframe)
    last = df.iloc[-1]

    return {
        "instrument": instrument,
        "timeframe": timeframe,
        "price": _safe(last["close"]),
        "indicators": {
            "rsi_14": _safe(last.get("rsi_14")),
            "macd_line": _safe(last.get("macd_line")),
            "macd_signal": _safe(last.get("macd_signal")),
            "macd_histogram": _safe(last.get("macd_histogram")),
            "ema_20": _safe(last.get("ema_20")),
            "ema_50": _safe(last.get("ema_50")),
            "ema_200": _safe(last.get("ema_200")),
            "bb_upper": _safe(last.get("bb_upper")),
            "bb_middle": _safe(last.get("bb_middle")),
            "bb_lower": _safe(last.get("bb_lower")),
            "atr_14": _safe(last.get("atr_14")),
            "vwap": _safe(last.get("vwap")),
            "ichimoku_tenkan": _safe(last.get("ichimoku_tenkan")),
            "ichimoku_kijun": _safe(last.get("ichimoku_kijun")),
        },
    }
