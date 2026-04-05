from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from backend.app.services.backtester import BacktestConfig, BacktestEngine, BacktestResult
from backend.app.services.strategies import StrategyFn


def compute_metrics(result: BacktestResult) -> dict:
    """Compute all performance metrics from a BacktestResult."""
    trades = result.trades
    total = len(trades)

    if total == 0:
        return _empty_metrics(result)

    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / total) * 100

    avg_win = np.mean(wins) if wins else 0.0
    avg_loss = np.mean(losses) if losses else 0.0
    avg_win_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    total_return = ((result.final_balance - result.initial_balance) / result.initial_balance) * 100

    # Expectancy per trade
    wr = win_count / total
    expectancy = (wr * avg_win) + ((1 - wr) * avg_loss)

    # Max drawdown from equity curve
    max_dd_pct, max_dd_dollar = _max_drawdown(result.equity_curve)

    # Sharpe ratio (annualized)
    sharpe = _sharpe_ratio(result.equity_curve)

    # Consecutive wins/losses
    max_consec_wins, max_consec_losses = _max_consecutive(trades)

    # Average trade duration
    durations = []
    for t in trades:
        if t.entry_time and t.exit_time:
            durations.append((t.exit_time - t.entry_time).total_seconds() / 3600)
    avg_duration_hours = np.mean(durations) if durations else 0.0

    # Trades per month
    if result.start_date and result.end_date:
        days = (result.end_date - result.start_date).days
        months = max(days / 30.0, 1.0)
        trades_per_month = total / months
    else:
        trades_per_month = 0.0

    return {
        "total_trades": total,
        "winning_trades": win_count,
        "losing_trades": loss_count,
        "win_rate": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2),
        "total_return": round(total_return, 2),
        "final_balance": round(result.final_balance, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "max_drawdown_dollar": round(max_dd_dollar, 2),
        "sharpe_ratio": round(sharpe, 2),
        "expectancy": round(expectancy, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "avg_win_loss_ratio": round(avg_win_loss_ratio, 2),
        "max_consecutive_wins": max_consec_wins,
        "max_consecutive_losses": max_consec_losses,
        "avg_trade_duration_hours": round(avg_duration_hours, 1),
        "trades_per_month": round(trades_per_month, 1),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
    }


def _empty_metrics(result: BacktestResult) -> dict:
    return {
        "total_trades": 0, "winning_trades": 0, "losing_trades": 0,
        "win_rate": 0.0, "profit_factor": 0.0, "total_return": 0.0,
        "final_balance": result.final_balance,
        "max_drawdown_pct": 0.0, "max_drawdown_dollar": 0.0,
        "sharpe_ratio": 0.0, "expectancy": 0.0,
        "avg_win": 0.0, "avg_loss": 0.0, "avg_win_loss_ratio": 0.0,
        "max_consecutive_wins": 0, "max_consecutive_losses": 0,
        "avg_trade_duration_hours": 0.0, "trades_per_month": 0.0,
        "gross_profit": 0.0, "gross_loss": 0.0,
    }


def _max_drawdown(equity_curve: list[dict]) -> tuple[float, float]:
    """Return (max_drawdown_percent, max_drawdown_dollars)."""
    if not equity_curve:
        return 0.0, 0.0

    peak = equity_curve[0]["equity"]
    max_dd_pct = 0.0
    max_dd_dollar = 0.0

    for point in equity_curve:
        equity = point["equity"]
        if equity > peak:
            peak = equity
        dd_dollar = peak - equity
        dd_pct = (dd_dollar / peak) * 100 if peak > 0 else 0.0
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
            max_dd_dollar = dd_dollar

    return max_dd_pct, max_dd_dollar


def _sharpe_ratio(equity_curve: list[dict]) -> float:
    """Annualized Sharpe ratio from equity curve."""
    if len(equity_curve) < 2:
        return 0.0

    equities = [p["equity"] for p in equity_curve]
    returns = []
    for i in range(1, len(equities)):
        if equities[i - 1] > 0:
            returns.append((equities[i] - equities[i - 1]) / equities[i - 1])

    if not returns:
        return 0.0

    mean_r = np.mean(returns)
    std_r = np.std(returns)

    if std_r == 0:
        return 0.0

    # Annualize: assume ~252 trading days, ~6 bars/day for H4
    # Use sqrt(N) where N = approximate bars per year
    bars_per_year = 252 * 6  # H4 bars
    return float((mean_r / std_r) * np.sqrt(bars_per_year))


def _max_consecutive(trades: list) -> tuple[int, int]:
    """Return (max_consecutive_wins, max_consecutive_losses)."""
    max_wins = max_losses = 0
    curr_wins = curr_losses = 0

    for t in trades:
        if t.pnl > 0:
            curr_wins += 1
            curr_losses = 0
            max_wins = max(max_wins, curr_wins)
        else:
            curr_losses += 1
            curr_wins = 0
            max_losses = max(max_losses, curr_losses)

    return max_wins, max_losses


# --------------------------------------------------------------------------
# Walk-Forward Validation
# --------------------------------------------------------------------------

def walk_forward_split(
    df: pd.DataFrame,
    train_ratio: float = 0.7,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split DataFrame chronologically into train and test sets."""
    split_idx = int(len(df) * train_ratio)
    train_df = df.iloc[:split_idx].reset_index(drop=True)
    test_df = df.iloc[split_idx:].reset_index(drop=True)
    return train_df, test_df


def run_walk_forward(
    df: pd.DataFrame,
    strategy: StrategyFn,
    config: BacktestConfig,
    strategy_params: Optional[dict] = None,
    train_ratio: float = 0.7,
) -> dict:
    """Run walk-forward validation: train on 70%, test on 30%."""
    train_df, test_df = walk_forward_split(df, train_ratio)

    # Train
    train_engine = BacktestEngine(BacktestConfig(
        instrument=config.instrument,
        granularity=config.granularity,
        initial_balance=config.initial_balance,
        risk_percent=config.risk_percent,
        min_rr_ratio=config.min_rr_ratio,
        warmup_bars=config.warmup_bars,
    ))
    train_result = train_engine.run(train_df, strategy, strategy_params)
    train_result.strategy_name = (strategy_params or {}).get("strategy_name", "Unknown")
    train_metrics = compute_metrics(train_result)

    # Test
    test_engine = BacktestEngine(BacktestConfig(
        instrument=config.instrument,
        granularity=config.granularity,
        initial_balance=config.initial_balance,
        risk_percent=config.risk_percent,
        min_rr_ratio=config.min_rr_ratio,
        warmup_bars=config.warmup_bars,
    ))
    test_result = test_engine.run(test_df, strategy, strategy_params)
    test_result.strategy_name = (strategy_params or {}).get("strategy_name", "Unknown")
    test_metrics = compute_metrics(test_result)

    # Validation checks
    validation_passed = (
        test_metrics["total_return"] > 0
        and test_metrics["profit_factor"] > 1.0
        and test_metrics["win_rate"] > 40
    )

    train_sharpe = train_metrics["sharpe_ratio"]
    test_sharpe = test_metrics["sharpe_ratio"]
    overfit_warning = (
        test_sharpe > 0
        and train_sharpe / test_sharpe > 2.0
    ) if test_sharpe != 0 else False

    return {
        "train": {"metrics": train_metrics, "trades": len(train_result.trades)},
        "test": {"metrics": test_metrics, "trades": len(test_result.trades)},
        "validation_passed": validation_passed,
        "overfit_warning": overfit_warning,
    }


# --------------------------------------------------------------------------
# Strategy Comparison
# --------------------------------------------------------------------------

def compare_strategies(results: dict[str, dict]) -> list[dict]:
    """Compare multiple strategy metrics. Returns sorted by Sharpe ratio."""
    rows = []
    for name, metrics in results.items():
        rows.append({
            "strategy": name,
            "total_return": metrics["total_return"],
            "win_rate": metrics["win_rate"],
            "profit_factor": metrics["profit_factor"],
            "sharpe_ratio": metrics["sharpe_ratio"],
            "max_drawdown_pct": metrics["max_drawdown_pct"],
            "total_trades": metrics["total_trades"],
            "expectancy": metrics["expectancy"],
        })

    rows.sort(key=lambda x: x["sharpe_ratio"], reverse=True)
    return rows


# --------------------------------------------------------------------------
# Report Formatting
# --------------------------------------------------------------------------

def format_report(result: BacktestResult, metrics: dict) -> str:
    """Generate a formatted text report."""
    start = result.start_date.strftime("%Y-%m-%d") if result.start_date else "N/A"
    end = result.end_date.strftime("%Y-%m-%d") if result.end_date else "N/A"

    return (
        f"\n{'=' * 50}\n"
        f"  TradeSight Backtest Report\n"
        f"{'=' * 50}\n"
        f"  Strategy:        {result.strategy_name}\n"
        f"  Instrument:      {result.config.instrument}\n"
        f"  Timeframe:       {result.config.granularity}\n"
        f"  Period:          {start} to {end}\n"
        f"  Bars Tested:     {result.total_bars}\n"
        f"{'-' * 50}\n"
        f"  Total Return:    {metrics['total_return']:.2f}%\n"
        f"  Final Balance:   ${metrics['final_balance']:,.2f}\n"
        f"  Total Trades:    {metrics['total_trades']}\n"
        f"  Win Rate:        {metrics['win_rate']:.1f}%\n"
        f"  Profit Factor:   {metrics['profit_factor']:.2f}\n"
        f"  Max Drawdown:    -{metrics['max_drawdown_pct']:.2f}%  (${metrics['max_drawdown_dollar']:,.2f})\n"
        f"  Sharpe Ratio:    {metrics['sharpe_ratio']:.2f}\n"
        f"  Expectancy:      ${metrics['expectancy']:.2f}/trade\n"
        f"{'-' * 50}\n"
        f"  Avg Win:         ${metrics['avg_win']:,.2f}\n"
        f"  Avg Loss:        ${metrics['avg_loss']:,.2f}\n"
        f"  Win/Loss Ratio:  {metrics['avg_win_loss_ratio']:.2f}\n"
        f"  Max Consec Wins: {metrics['max_consecutive_wins']}\n"
        f"  Max Consec Loss: {metrics['max_consecutive_losses']}\n"
        f"  Avg Duration:    {metrics['avg_trade_duration_hours']:.1f} hours\n"
        f"  Trades/Month:    {metrics['trades_per_month']:.1f}\n"
        f"{'=' * 50}\n"
    )


def result_to_json(result: BacktestResult, metrics: dict) -> dict:
    """Serialize BacktestResult + metrics into a JSON-friendly dict."""
    equity = [
        {
            "timestamp": p["timestamp"].isoformat() if p.get("timestamp") else None,
            "equity": round(p["equity"], 2),
        }
        for p in result.equity_curve
    ]

    trade_list = [
        {
            "direction": t.direction.value,
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "stop_loss": t.stop_loss,
            "take_profit": t.take_profit,
            "position_size": round(t.position_size, 2),
            "pnl": t.pnl,
            "pnl_pips": t.pnl_pips,
            "entry_time": t.entry_time.isoformat() if t.entry_time else None,
            "exit_time": t.exit_time.isoformat() if t.exit_time else None,
            "exit_reason": t.exit_reason,
            "signal_reason": t.signal_reason,
        }
        for t in result.trades
    ]

    return {
        "strategy": result.strategy_name,
        "instrument": result.config.instrument,
        "timeframe": result.config.granularity,
        "start_date": result.start_date.isoformat() if result.start_date else None,
        "end_date": result.end_date.isoformat() if result.end_date else None,
        "metrics": metrics,
        "equity_curve": equity,
        "trades": trade_list,
    }
