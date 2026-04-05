#!/usr/bin/env python3
"""TradeSight Phase 2 Checkpoint — Backtest EMA Crossover on EUR/USD 4H (6 months)."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.app.database import SessionLocal, init_db
from backend.app.services.backtester import BacktestConfig, BacktestEngine
from backend.app.services.historical import (
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
    run_walk_forward,
)
from backend.app.services.strategies import (
    STRATEGY_REGISTRY,
    ema_crossover_strategy,
    macd_momentum_strategy,
    rsi_mean_reversion_strategy,
)


async def main():
    init_db()
    db = SessionLocal()

    instrument = "EUR_USD"
    granularity = "H4"
    months = 6

    # ------------------------------------------------------------------
    # Step 1: Fetch 6 months of historical data
    # ------------------------------------------------------------------
    print("=" * 55)
    print("  Phase 2: Fetching 6 months of EUR_USD H4 data")
    print("=" * 55)

    async with OandaClient() as client:
        candles = await fetch_historical_candles(instrument, granularity, months, client)
    count = store_candles_bulk(db, candles, instrument, granularity)
    print(f"  Stored {count} candles")

    # Load and compute indicators
    df = load_candles_as_dataframe(db, instrument, granularity)
    df = compute_indicators(df, timeframe=granularity)
    print(f"  DataFrame: {len(df)} rows, {len(df.columns)} columns")
    print(f"  Date range: {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}")

    # ------------------------------------------------------------------
    # Step 2: Run EMA Crossover backtest
    # ------------------------------------------------------------------
    print(f"\n{'=' * 55}")
    print("  Running EMA Crossover (20/50) backtest")
    print("=" * 55)

    config = BacktestConfig(instrument=instrument, granularity=granularity)
    engine = BacktestEngine(config)
    result = engine.run(df, ema_crossover_strategy, {
        "instrument": instrument,
        "strategy_name": "EMA Crossover (20/50)",
    })

    metrics = compute_metrics(result)
    print(format_report(result, metrics))

    # Print some individual trades
    if result.trades:
        print("  Sample trades (first 5):")
        for t in result.trades[:5]:
            direction = "LONG " if t.direction.value == "long" else "SHORT"
            print(f"    {direction} {t.entry_time} -> {t.exit_time}  "
                  f"PnL: ${t.pnl:+,.2f} ({t.pnl_pips:+.1f} pips)  [{t.exit_reason}]")

    # ------------------------------------------------------------------
    # Step 3: Walk-Forward Validation
    # ------------------------------------------------------------------
    print(f"\n{'=' * 55}")
    print("  Walk-Forward Validation (70/30 split)")
    print("=" * 55)

    wf = run_walk_forward(
        df, ema_crossover_strategy, config,
        {"instrument": instrument, "strategy_name": "EMA Crossover (20/50)"},
    )

    print(f"\n  Training Set ({wf['train']['trades']} trades):")
    tm = wf["train"]["metrics"]
    print(f"    Return: {tm['total_return']:+.2f}%  |  Win Rate: {tm['win_rate']:.1f}%  |  "
          f"Sharpe: {tm['sharpe_ratio']:.2f}  |  Max DD: -{tm['max_drawdown_pct']:.2f}%")

    print(f"\n  Test Set ({wf['test']['trades']} trades):")
    testm = wf["test"]["metrics"]
    print(f"    Return: {testm['total_return']:+.2f}%  |  Win Rate: {testm['win_rate']:.1f}%  |  "
          f"Sharpe: {testm['sharpe_ratio']:.2f}  |  Max DD: -{testm['max_drawdown_pct']:.2f}%")

    status = "PASSED" if wf["validation_passed"] else "FAILED"
    print(f"\n  Validation: {status}")
    if wf["overfit_warning"]:
        print("  WARNING: Possible overfitting detected (train >> test)")

    # ------------------------------------------------------------------
    # Step 4: Strategy Comparison
    # ------------------------------------------------------------------
    print(f"\n{'=' * 55}")
    print("  Strategy Comparison (all single-TF strategies)")
    print("=" * 55)

    strategies = [
        ("ema_crossover", ema_crossover_strategy, "EMA Crossover (20/50)"),
        ("rsi_reversion", rsi_mean_reversion_strategy, "RSI Mean Reversion"),
        ("macd_momentum", macd_momentum_strategy, "MACD Momentum"),
    ]

    all_metrics = {}
    for key, strat_fn, display_name in strategies:
        eng = BacktestEngine(BacktestConfig(instrument=instrument, granularity=granularity))
        res = eng.run(df, strat_fn, {"instrument": instrument, "strategy_name": display_name})
        m = compute_metrics(res)
        all_metrics[display_name] = m
        print(f"\n  {display_name}:")
        print(f"    Trades: {m['total_trades']}  |  Win Rate: {m['win_rate']:.1f}%  |  "
              f"Return: {m['total_return']:+.2f}%  |  Sharpe: {m['sharpe_ratio']:.2f}")

    comparison = compare_strategies(all_metrics)
    print(f"\n  {'Strategy':<25} {'Sharpe':>8} {'Return':>10} {'Win Rate':>10} {'Trades':>8}")
    print(f"  {'-' * 61}")
    for row in comparison:
        print(f"  {row['strategy']:<25} {row['sharpe_ratio']:>8.2f} {row['total_return']:>9.2f}% "
              f"{row['win_rate']:>9.1f}% {row['total_trades']:>8}")

    # ------------------------------------------------------------------
    print(f"\n{'=' * 55}")
    print("  Phase 2 checkpoint complete!")
    print("=" * 55)

    db.close()


if __name__ == "__main__":
    asyncio.run(main())
