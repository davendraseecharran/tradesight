from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.config import FOREX_PAIRS, TIMEFRAMES
from backend.app.database import get_db
from backend.app.services.backtester import BacktestConfig, BacktestEngine
from backend.app.services.historical import (
    fetch_all_historical,
    fetch_historical_candles,
    load_candles_as_dataframe,
    store_candles_bulk,
)
from backend.app.services.indicators import compute_indicators
from backend.app.services.oanda import OandaClient
from backend.app.services.report import (
    compare_strategies,
    compute_metrics,
    format_report,
    result_to_json,
    run_walk_forward,
)
from backend.app.services.strategies import STRATEGY_REGISTRY

router = APIRouter(prefix="/backtest", tags=["Backtesting"])


async def _ensure_data(db: Session, instrument: str, granularity: str, months: int) -> int:
    """Fetch historical data if DB doesn't have enough."""
    df = load_candles_as_dataframe(db, instrument, granularity)
    if len(df) >= 200:
        return len(df)
    # Fetch from OANDA
    async with OandaClient() as client:
        candles = await fetch_historical_candles(instrument, granularity, months, client)
    return store_candles_bulk(db, candles, instrument, granularity)


@router.post("/run")
async def run_backtest(
    instrument: str = Query(default="EUR_USD"),
    strategy_name: str = Query(default="ema_crossover"),
    granularity: str = Query(default="4H"),
    months: int = Query(default=6, ge=1, le=24),
    initial_balance: float = Query(default=100_000.0),
    risk_percent: float = Query(default=0.02),
    db: Session = Depends(get_db),
):
    """Run a single strategy backtest."""
    if strategy_name not in STRATEGY_REGISTRY:
        raise HTTPException(400, f"Unknown strategy: {strategy_name}. Available: {list(STRATEGY_REGISTRY.keys())}")

    strategy_fn, display_name = STRATEGY_REGISTRY[strategy_name]

    await _ensure_data(db, instrument, granularity, months)
    df = load_candles_as_dataframe(db, instrument, granularity)
    df = compute_indicators(df, timeframe=granularity)

    config = BacktestConfig(
        instrument=instrument,
        granularity=granularity,
        initial_balance=initial_balance,
        risk_percent=risk_percent,
    )
    engine = BacktestEngine(config)
    result = engine.run(df, strategy_fn, {
        "instrument": instrument,
        "strategy_name": display_name,
    })

    metrics = compute_metrics(result)
    return result_to_json(result, metrics)


@router.post("/walk-forward")
async def run_walk_forward_endpoint(
    instrument: str = Query(default="EUR_USD"),
    strategy_name: str = Query(default="ema_crossover"),
    granularity: str = Query(default="4H"),
    months: int = Query(default=6),
    train_ratio: float = Query(default=0.7),
    db: Session = Depends(get_db),
):
    """Run walk-forward validation (70/30 split)."""
    if strategy_name not in STRATEGY_REGISTRY:
        raise HTTPException(400, f"Unknown strategy: {strategy_name}")

    strategy_fn, display_name = STRATEGY_REGISTRY[strategy_name]

    await _ensure_data(db, instrument, granularity, months)
    df = load_candles_as_dataframe(db, instrument, granularity)
    df = compute_indicators(df, timeframe=granularity)

    config = BacktestConfig(instrument=instrument, granularity=granularity)
    wf = run_walk_forward(
        df, strategy_fn, config,
        {"instrument": instrument, "strategy_name": display_name},
        train_ratio,
    )
    return wf


@router.post("/compare")
async def compare_strategies_endpoint(
    instrument: str = Query(default="EUR_USD"),
    granularity: str = Query(default="4H"),
    months: int = Query(default=6),
    db: Session = Depends(get_db),
):
    """Run all single-timeframe strategies and compare them."""
    await _ensure_data(db, instrument, granularity, months)
    df = load_candles_as_dataframe(db, instrument, granularity)
    df = compute_indicators(df, timeframe=granularity)

    all_metrics = {}
    for name, (strategy_fn, display_name) in STRATEGY_REGISTRY.items():
        if name == "mtf_confluence":
            continue  # Skip multi-timeframe strategy in single-tf comparison
        config = BacktestConfig(instrument=instrument, granularity=granularity)
        engine = BacktestEngine(config)
        result = engine.run(df, strategy_fn, {
            "instrument": instrument,
            "strategy_name": display_name,
        })
        all_metrics[display_name] = compute_metrics(result)

    return {
        "instrument": instrument,
        "granularity": granularity,
        "comparison": compare_strategies(all_metrics),
    }


@router.post("/fetch-historical")
async def fetch_historical_endpoint(
    instrument: str = Query(default=None),
    granularity: str = Query(default=None),
    months: int = Query(default=6),
    db: Session = Depends(get_db),
):
    """Fetch historical data from OANDA. Omit params to fetch all pairs/timeframes."""
    if instrument and granularity:
        async with OandaClient() as client:
            candles = await fetch_historical_candles(instrument, granularity, months, client)
        count = store_candles_bulk(db, candles, instrument, granularity)
        return {"message": f"Fetched {count} candles for {instrument} {granularity}"}
    else:
        results = await fetch_all_historical(months=months)
        total = sum(results.values())
        return {"message": f"Fetched {total} candles across {len(results)} pair/timeframe combinations", "details": results}
