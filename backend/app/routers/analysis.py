from __future__ import annotations

import math

import pandas as pd
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.config import BINANCE_INTERVALS, OANDA_GRANULARITIES, TIMEFRAMES
from backend.app.database import get_db
from backend.app.schemas import AnalysisResponse
from backend.app.services.analyzer import MarketAnalyzer
from backend.app.services.binance import BinanceClient
from backend.app.services.indicators import compute_indicators
from backend.app.services.oanda import OandaClient

router = APIRouter(prefix="/analyze", tags=["Analysis"])


def _safe(val) -> float | None:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    return float(val)


async def _fetch_and_compute(source: str, instrument: str, granularity: str, count: int = 200):
    """Fetch candles and compute indicators, returning both."""
    if source == "oanda":
        gran = OANDA_GRANULARITIES.get(granularity, granularity)
        async with OandaClient() as client:
            candles = await client.get_candles(instrument, gran, count)
    else:
        interval = BINANCE_INTERVALS.get(granularity, granularity)
        async with BinanceClient() as client:
            candles = await client.get_klines(instrument, interval, count)

    df = pd.DataFrame(candles)
    df = compute_indicators(df, timeframe=granularity)

    # Get the latest indicator values
    last = df.iloc[-1]
    indicators = {col: _safe(last.get(col)) for col in df.columns if col not in ("timestamp", "open", "high", "low", "close", "volume", "complete")}

    return candles, indicators


def _detect_source(instrument: str) -> str:
    return "binance" if instrument.endswith("USDT") else "oanda"


@router.post("/{instrument}", response_model=AnalysisResponse)
async def analyze_instrument(
    instrument: str,
    timeframe: str = Query(default="4H"),
    model: str = Query(default="sonnet", description="'sonnet' or 'opus'"),
):
    source = _detect_source(instrument)
    candles, indicators = await _fetch_and_compute(source, instrument, timeframe)

    model_id = (
        "claude-opus-4-6-20250514" if model == "opus"
        else "claude-sonnet-4-6-20250514"
    )

    analyzer = MarketAnalyzer()
    result = await analyzer.analyze_instrument(
        instrument=instrument,
        candle_data=candles,
        indicators=indicators,
        timeframe=timeframe,
        model=model_id,
    )

    return AnalysisResponse(
        instrument=instrument,
        timeframe=timeframe,
        bias=result.get("bias"),
        confidence=result.get("confidence"),
        key_levels=result.get("key_levels"),
        entry_suggestion=result.get("entry_suggestion"),
        stop_loss_suggestion=result.get("stop_loss_suggestion"),
        take_profit_suggestion=result.get("take_profit_suggestion"),
        reasoning=result.get("reasoning"),
        risk_warning=result.get("risk_warning", "This is educational analysis, not financial advice."),
        raw_response=result.get("raw_response"),
    )


@router.post("/deep/{instrument}", response_model=AnalysisResponse)
async def deep_analysis(instrument: str):
    source = _detect_source(instrument)
    multi_tf_data = {}

    for tf in TIMEFRAMES:
        candles, indicators = await _fetch_and_compute(source, instrument, tf)
        multi_tf_data[tf] = {"candles": candles, "indicators": indicators}

    analyzer = MarketAnalyzer()
    result = await analyzer.deep_analysis(instrument, multi_tf_data)

    return AnalysisResponse(
        instrument=instrument,
        timeframe="multi",
        bias=result.get("bias"),
        confidence=result.get("confidence"),
        key_levels=result.get("key_levels"),
        entry_suggestion=result.get("entry_suggestion"),
        stop_loss_suggestion=result.get("stop_loss_suggestion"),
        take_profit_suggestion=result.get("take_profit_suggestion"),
        reasoning=result.get("reasoning"),
        risk_warning=result.get("risk_warning", "This is educational analysis, not financial advice."),
        raw_response=result.get("raw_response"),
    )
