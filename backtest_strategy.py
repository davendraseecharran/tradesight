#!/usr/bin/env python3
"""
TradeSight — 3-Step Strategy Backtest (HARD GATE for deployment)

Fetches 24 months of W/D/H4 candles per pair directly from OANDA (free,
no AI calls), runs the mechanical 3-step engine through the backtester,
and prints per-pair + aggregate stats with a PASS/FAIL verdict.

Usage:
    python backtest_strategy.py               # all pairs, 24 months
    python backtest_strategy.py --months 12
    python backtest_strategy.py --pairs EUR_USD,XAU_USD
"""
import argparse
import asyncio
import os
import sys
from typing import Optional

venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "python")
if os.path.exists(venv_python) and os.path.realpath(sys.executable) != os.path.realpath(venv_python):
    os.execv(venv_python, [venv_python] + sys.argv)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for key in ["ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"]:
    os.environ.pop(key, None)

import pandas as pd

from backend.app.config import FOREX_PAIRS, get_settings
from backend.app.services.backtester import BacktestConfig, BacktestEngine
from backend.app.services.historical import fetch_historical_candles
from backend.app.services.oanda import OandaClient
from backend.app.services.strategy import three_step_mtf_strategy

get_settings.cache_clear()

GRANULARITIES = ("W", "D", "H4")

# Hard-gate thresholds
GATE_MIN_TRADES = 10
GATE_MIN_PROFIT_FACTOR = 1.3


def _to_df(candles: list[dict]) -> pd.DataFrame:
    rows = [c for c in candles if c.get("complete", True)]
    df = pd.DataFrame(rows)[["timestamp", "open", "high", "low", "close"]]
    return df.sort_values("timestamp").reset_index(drop=True)


async def fetch_frames(pairs: list[str], months: int) -> dict[str, dict[str, pd.DataFrame]]:
    frames: dict[str, dict[str, pd.DataFrame]] = {}
    async with OandaClient() as client:
        for pair in pairs:
            frames[pair] = {}
            for gran in GRANULARITIES:
                candles = await fetch_historical_candles(pair, gran, months, client)
                frames[pair][gran] = _to_df(candles)
                print(f"  {pair} {gran}: {len(frames[pair][gran])} candles")
                await asyncio.sleep(0.3)
    return frames


def max_drawdown(equity_curve: list[dict]) -> float:
    peak, worst = float("-inf"), 0.0
    for point in equity_curve:
        eq = point["equity"]
        peak = max(peak, eq)
        if peak > 0:
            worst = max(worst, (peak - eq) / peak)
    return worst


def run_pair(pair: str, dataframes: dict, extra_params: Optional[dict] = None) -> dict:
    config = BacktestConfig(
        instrument=pair,
        granularity="H4",
        initial_balance=100_000.0,
        risk_percent=0.02,
        min_rr_ratio=2.0,
        warmup_bars=200,
        respect_signal_tp=True,   # keep structure-based targets
    )
    engine = BacktestEngine(config)
    result = engine.run_multi_timeframe(
        dataframes,
        three_step_mtf_strategy,
        primary_timeframe="H4",
        strategy_params={"instrument": pair, "strategy_name": "3-step", **(extra_params or {})},
    )

    trades = result.trades
    wins = [t for t in trades if (t.pnl or 0) > 0]
    losses = [t for t in trades if (t.pnl or 0) <= 0]
    gross_win = sum(t.pnl for t in wins) if wins else 0.0
    gross_loss = abs(sum(t.pnl for t in losses)) if losses else 0.0

    return {
        "pair": pair,
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(trades) * 100 if trades else 0.0,
        "net_pnl": result.final_balance - result.initial_balance,
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0),
        "max_drawdown_pct": max_drawdown(result.equity_curve) * 100,
        "start": result.start_date,
        "end": result.end_date,
        "trade_log": [
            {
                "entry_time": str(t.entry_time), "exit_time": str(t.exit_time),
                "direction": t.direction.value, "entry": t.entry_price,
                "sl": t.stop_loss, "tp": t.take_profit,
                "exit_reason": t.exit_reason, "pnl": t.pnl,
                "reason": t.signal_reason,
            }
            for t in trades
        ],
    }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--months", type=int, default=24)
    parser.add_argument("--pairs", type=str, default="")
    parser.add_argument("--sweep", action="store_true",
                        help="sweep sl_atr_fraction values and report each aggregate")
    args = parser.parse_args()

    pairs = args.pairs.split(",") if args.pairs else FOREX_PAIRS

    print("=" * 70)
    print(f"  TradeSight — 3-Step Strategy Backtest ({args.months} months, {len(pairs)} pairs)")
    print("=" * 70)

    print("\n[1] Fetching history from OANDA (free, no AI)...")
    frames = await fetch_frames(pairs, args.months)

    if args.sweep:
        print("\n[2] Sweeping SL buffer (sl_atr_fraction)...")
        for frac in (0.05, 0.10, 0.15, 0.20):
            agg_trades, agg_wins, agg_net, g_win, g_loss = 0, 0, 0.0, 0.0, 0.0
            for pair in pairs:
                if any(len(frames[pair][g]) < 60 for g in GRANULARITIES):
                    continue
                r = run_pair(pair, frames[pair], {"sl_atr_fraction": frac})
                agg_trades += r["trades"]
                agg_wins += r["wins"]
                agg_net += r["net_pnl"]
                g_win += sum(max(t["pnl"], 0) for t in r["trade_log"] if t["pnl"] is not None)
                g_loss += abs(sum(min(t["pnl"], 0) for t in r["trade_log"] if t["pnl"] is not None))
            pf = (g_win / g_loss) if g_loss > 0 else 0.0
            wr = agg_wins / agg_trades * 100 if agg_trades else 0.0
            print(f"  frac={frac:.2f}: {agg_trades:3} trades, {wr:4.1f}% win, "
                  f"net ${agg_net:+10,.0f}, PF {pf:.2f}")
        return True

    print("\n[2] Running backtests...")
    results = []
    for pair in pairs:
        if any(len(frames[pair][g]) < 60 for g in GRANULARITIES):
            print(f"  {pair}: SKIPPED — insufficient data")
            continue
        r = run_pair(pair, frames[pair])
        results.append(r)
        print(
            f"  {pair}: {r['trades']} trades, {r['win_rate']:.0f}% win rate, "
            f"net ${r['net_pnl']:+,.0f}, PF {r['profit_factor']:.2f}, "
            f"maxDD {r['max_drawdown_pct']:.1f}%"
        )

    # ── Aggregate + verdict ────────────────────────────────────────────────
    total_trades = sum(r["trades"] for r in results)
    total_wins = sum(r["wins"] for r in results)
    total_net = sum(r["net_pnl"] for r in results)
    gross_win = sum(max(t["pnl"], 0) for r in results for t in r["trade_log"] if t["pnl"] is not None)
    gross_loss = abs(sum(min(t["pnl"], 0) for r in results for t in r["trade_log"] if t["pnl"] is not None))
    pf = (gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)

    print("\n" + "=" * 70)
    print("  AGGREGATE")
    print("=" * 70)
    print(f"  Trades:        {total_trades}")
    print(f"  Win rate:      {total_wins / total_trades * 100:.1f}%" if total_trades else "  Win rate:      n/a")
    print(f"  Net P&L:       ${total_net:+,.0f} (per-pair $100K accounts)")
    print(f"  Profit factor: {pf:.2f}")

    gate_pass = total_trades >= GATE_MIN_TRADES and total_net > 0 and pf >= GATE_MIN_PROFIT_FACTOR
    print("\n  HARD GATE: " + ("\033[92mPASS — strategy may be deployed\033[0m" if gate_pass
                               else "\033[91mFAIL — do NOT deploy; tune rules first\033[0m"))
    print(f"  (requires >= {GATE_MIN_TRADES} trades, positive net P&L, profit factor >= {GATE_MIN_PROFIT_FACTOR})")

    # Full trade log for review
    print("\n[3] Trade log")
    for r in results:
        for t in r["trade_log"]:
            print(f"  {r['pair']} {t['direction']:5} {t['entry_time'][:16]} -> {t['exit_time'][:16]} "
                  f"{t['exit_reason']:12} ${t['pnl']:+,.0f}  | {t['reason'][:70]}")

    return gate_pass


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
