from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

import pandas as pd

from backend.app.services.strategies import Direction, MTFStrategyFn, Signal, StrategyFn

# Typical OANDA practice spreads in pips
SPREADS_PIPS: dict[str, float] = {
    "EUR_USD": 1.2,
    "GBP_USD": 1.6,
    "USD_JPY": 1.2,
    "GBP_JPY": 2.5,
    "AUD_USD": 1.4,
    "USD_CAD": 1.6,
    "XAU_USD": 4.0,   # ~$0.40 spread, pip = 0.1
}


def _get_pip_size(instrument: str) -> float:
    if "JPY" in instrument:
        return 0.01
    if instrument.startswith("XAU"):
        return 0.1
    return 0.0001


def _get_spread(instrument: str) -> float:
    """Return spread in price terms."""
    pip_size = _get_pip_size(instrument)
    return SPREADS_PIPS.get(instrument, 1.5) * pip_size


@dataclass
class BacktestTrade:
    entry_index: int
    exit_index: Optional[int]
    direction: Direction
    entry_price: float
    exit_price: Optional[float]
    stop_loss: float
    take_profit: float
    position_size: float
    pnl: Optional[float]
    pnl_pips: Optional[float]
    entry_time: datetime
    exit_time: Optional[datetime]
    exit_reason: str  # "tp_hit", "sl_hit", "signal_exit", "end_of_data"
    signal_reason: str


@dataclass
class BacktestConfig:
    instrument: str
    granularity: str
    initial_balance: float = 100_000.0
    risk_percent: float = 0.02
    min_rr_ratio: float = 2.0
    warmup_bars: int = 200
    # When True, keep the strategy's take-profit (e.g. structure-based
    # targets) instead of recomputing TP as exactly min_rr_ratio x risk.
    respect_signal_tp: bool = False


@dataclass
class BacktestResult:
    config: BacktestConfig
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)
    initial_balance: float = 100_000.0
    final_balance: float = 100_000.0
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    total_bars: int = 0
    strategy_name: str = ""


class BacktestEngine:
    def __init__(self, config: BacktestConfig):
        self.config = config
        self.trades: list[BacktestTrade] = []
        self.equity_curve: list[dict] = []
        self.balance = config.initial_balance
        self.position: Optional[BacktestTrade] = None
        self._spread = _get_spread(config.instrument)
        self._pip_size = _get_pip_size(config.instrument)

    def run(
        self,
        df: pd.DataFrame,
        strategy: StrategyFn,
        strategy_params: Optional[dict] = None,
    ) -> BacktestResult:
        """Run a single-timeframe backtest."""
        params = strategy_params or {}
        params.setdefault("instrument", self.config.instrument)
        params.setdefault("pip_size", self._pip_size)

        warmup = min(self.config.warmup_bars, len(df) - 1)

        for i in range(warmup, len(df)):
            # 1. Check open position for SL/TP hits
            if self.position is not None:
                self._check_exit(df, i)

            # 2. If no position, check for new signal
            if self.position is None:
                signal = strategy(df, i, params)
                if signal is not None:
                    self._open_position(df, i, signal)

            # 3. Record equity
            equity = self._current_equity(df, i)
            ts = df["timestamp"].iloc[i] if "timestamp" in df.columns else None
            self.equity_curve.append({"index": i, "timestamp": ts, "equity": equity})

        # Close any open position at end of data
        if self.position is not None:
            self._close_position(df, len(df) - 1, df["close"].iloc[-1], "end_of_data")

        start = df["timestamp"].iloc[warmup] if "timestamp" in df.columns else None
        end = df["timestamp"].iloc[-1] if "timestamp" in df.columns else None

        return BacktestResult(
            config=self.config,
            trades=self.trades,
            equity_curve=self.equity_curve,
            initial_balance=self.config.initial_balance,
            final_balance=self.balance,
            start_date=start,
            end_date=end,
            total_bars=len(df) - warmup,
            strategy_name=params.get("strategy_name", "Unknown"),
        )

    def run_multi_timeframe(
        self,
        dataframes: Dict[str, pd.DataFrame],
        strategy: MTFStrategyFn,
        primary_timeframe: str = "H1",
        strategy_params: Optional[dict] = None,
    ) -> BacktestResult:
        """Run a multi-timeframe backtest, iterating on the primary timeframe."""
        params = strategy_params or {}
        params.setdefault("instrument", self.config.instrument)
        params.setdefault("pip_size", self._pip_size)
        params.setdefault("primary_timeframe", primary_timeframe)

        df_primary = dataframes[primary_timeframe]
        warmup = min(self.config.warmup_bars, len(df_primary) - 1)

        for i in range(warmup, len(df_primary)):
            if self.position is not None:
                self._check_exit(df_primary, i)

            if self.position is None:
                signal = strategy(dataframes, i, params)
                if signal is not None:
                    self._open_position(df_primary, i, signal)

            equity = self._current_equity(df_primary, i)
            ts = df_primary["timestamp"].iloc[i] if "timestamp" in df_primary.columns else None
            self.equity_curve.append({"index": i, "timestamp": ts, "equity": equity})

        if self.position is not None:
            self._close_position(df_primary, len(df_primary) - 1,
                                 df_primary["close"].iloc[-1], "end_of_data")

        start = df_primary["timestamp"].iloc[warmup] if "timestamp" in df_primary.columns else None
        end = df_primary["timestamp"].iloc[-1] if "timestamp" in df_primary.columns else None

        return BacktestResult(
            config=self.config,
            trades=self.trades,
            equity_curve=self.equity_curve,
            initial_balance=self.config.initial_balance,
            final_balance=self.balance,
            start_date=start,
            end_date=end,
            total_bars=len(df_primary) - warmup,
            strategy_name=params.get("strategy_name", "Unknown"),
        )

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    def _open_position(self, df: pd.DataFrame, index: int, signal: Signal):
        """Validate and open a new position."""
        entry = signal.entry_price
        sl = signal.stop_loss
        tp = signal.take_profit

        # Apply spread and adjust TP to maintain target R:R from adjusted entry
        if signal.direction == Direction.LONG:
            entry += self._spread / 2  # buy at ask
        else:
            entry -= self._spread / 2  # sell at bid

        risk = abs(entry - sl)
        if risk == 0:
            return

        # Recalculate TP from spread-adjusted entry to guarantee target R:R,
        # unless the strategy sets structure-based targets it wants kept.
        if not self.config.respect_signal_tp:
            if signal.direction == Direction.LONG:
                tp = entry + risk * self.config.min_rr_ratio
            else:
                tp = entry - risk * self.config.min_rr_ratio

        # Position sizing: risk_amount / distance
        position_size = (self.balance * self.config.risk_percent) / risk

        ts = df["timestamp"].iloc[index] if "timestamp" in df.columns else None

        self.position = BacktestTrade(
            entry_index=index,
            exit_index=None,
            direction=signal.direction,
            entry_price=entry,
            exit_price=None,
            stop_loss=sl,
            take_profit=tp,
            position_size=position_size,
            pnl=None,
            pnl_pips=None,
            entry_time=ts,
            exit_time=None,
            exit_reason="",
            signal_reason=signal.reason,
        )

    def _check_exit(self, df: pd.DataFrame, index: int):
        """Check if current bar hits SL or TP."""
        pos = self.position
        high = df["high"].iloc[index]
        low = df["low"].iloc[index]

        if pos.direction == Direction.LONG:
            # Check SL first (conservative)
            if low <= pos.stop_loss:
                self._close_position(df, index, pos.stop_loss, "sl_hit")
            elif high >= pos.take_profit:
                self._close_position(df, index, pos.take_profit, "tp_hit")
        else:  # SHORT
            if high >= pos.stop_loss:
                self._close_position(df, index, pos.stop_loss, "sl_hit")
            elif low <= pos.take_profit:
                self._close_position(df, index, pos.take_profit, "tp_hit")

    def _close_position(self, df: pd.DataFrame, index: int, exit_price: float, reason: str):
        """Close the current position and record PnL."""
        pos = self.position

        if pos.direction == Direction.LONG:
            pnl = (exit_price - pos.entry_price) * pos.position_size
        else:
            pnl = (pos.entry_price - exit_price) * pos.position_size

        pnl_pips = abs(exit_price - pos.entry_price) / self._pip_size
        if pnl < 0:
            pnl_pips = -pnl_pips

        pos.exit_index = index
        pos.exit_price = exit_price
        pos.pnl = round(pnl, 2)
        pos.pnl_pips = round(pnl_pips, 1)
        pos.exit_time = df["timestamp"].iloc[index] if "timestamp" in df.columns else None
        pos.exit_reason = reason

        self.balance += pnl
        self.trades.append(pos)
        self.position = None

    def _current_equity(self, df: pd.DataFrame, index: int) -> float:
        """Calculate current equity (balance + unrealized PnL)."""
        if self.position is None:
            return self.balance

        pos = self.position
        current_close = df["close"].iloc[index]

        if pos.direction == Direction.LONG:
            unrealized = (current_close - pos.entry_price) * pos.position_size
        else:
            unrealized = (pos.entry_price - current_close) * pos.position_size

        return self.balance + unrealized
