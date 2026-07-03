from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, Optional, Tuple

import pandas as pd


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"


@dataclass
class Signal:
    direction: Direction
    entry_price: float
    stop_loss: float
    take_profit: float
    reason: str = ""


# Type aliases
StrategyFn = Callable[[pd.DataFrame, int, dict], Optional[Signal]]
MTFStrategyFn = Callable[[Dict[str, pd.DataFrame], int, dict], Optional[Signal]]


def _get_pip_size(instrument: str) -> float:
    if "JPY" in instrument:
        return 0.01
    if instrument.startswith("XAU"):
        return 0.1
    return 0.0001


def atr_based_levels(
    df: pd.DataFrame,
    index: int,
    direction: Direction,
    atr_multiplier: float = 1.5,
    rr_ratio: float = 2.0,
) -> Tuple[float, float]:
    """Compute SL and TP from ATR."""
    close = df["close"].iloc[index]
    atr = df["atr_14"].iloc[index]

    if pd.isna(atr) or atr <= 0:
        # Fallback: use a percentage-based stop
        atr = close * 0.005

    risk = atr * atr_multiplier
    reward = risk * rr_ratio

    if direction == Direction.LONG:
        return close - risk, close + reward
    else:
        return close + risk, close - reward


# --------------------------------------------------------------------------
# Strategy 1: EMA Crossover (20/50)
# --------------------------------------------------------------------------

def ema_crossover_strategy(df: pd.DataFrame, index: int, params: dict) -> Optional[Signal]:
    """Buy when EMA20 crosses above EMA50, sell when crosses below."""
    if index < 1:
        return None

    ema20 = df["ema_20"].iloc[index]
    ema50 = df["ema_50"].iloc[index]
    prev_ema20 = df["ema_20"].iloc[index - 1]
    prev_ema50 = df["ema_50"].iloc[index - 1]

    if pd.isna(ema20) or pd.isna(ema50) or pd.isna(prev_ema20) or pd.isna(prev_ema50):
        return None

    close = df["close"].iloc[index]

    # Bullish crossover
    if prev_ema20 <= prev_ema50 and ema20 > ema50:
        sl, tp = atr_based_levels(df, index, Direction.LONG)
        return Signal(Direction.LONG, close, sl, tp, "EMA20 crossed above EMA50")

    # Bearish crossover
    if prev_ema20 >= prev_ema50 and ema20 < ema50:
        sl, tp = atr_based_levels(df, index, Direction.SHORT)
        return Signal(Direction.SHORT, close, sl, tp, "EMA20 crossed below EMA50")

    return None


# --------------------------------------------------------------------------
# Strategy 2: RSI Mean Reversion
# --------------------------------------------------------------------------

def rsi_mean_reversion_strategy(df: pd.DataFrame, index: int, params: dict) -> Optional[Signal]:
    """Buy when RSI drops below 30 (just entered oversold), sell when above 70."""
    if index < 1:
        return None

    rsi = df["rsi_14"].iloc[index]
    prev_rsi = df["rsi_14"].iloc[index - 1]

    if pd.isna(rsi) or pd.isna(prev_rsi):
        return None

    close = df["close"].iloc[index]

    # Just entered oversold — buy
    if rsi < 30 and prev_rsi >= 30:
        sl, tp = atr_based_levels(df, index, Direction.LONG, atr_multiplier=2.0)
        return Signal(Direction.LONG, close, sl, tp, f"RSI entered oversold ({rsi:.1f})")

    # Just entered overbought — sell
    if rsi > 70 and prev_rsi <= 70:
        sl, tp = atr_based_levels(df, index, Direction.SHORT, atr_multiplier=2.0)
        return Signal(Direction.SHORT, close, sl, tp, f"RSI entered overbought ({rsi:.1f})")

    return None


# --------------------------------------------------------------------------
# Strategy 3: MACD Momentum
# --------------------------------------------------------------------------

def macd_momentum_strategy(df: pd.DataFrame, index: int, params: dict) -> Optional[Signal]:
    """Buy when MACD histogram crosses > 0 with price above EMA200.
    Sell when histogram crosses < 0 with price below EMA200."""
    if index < 1:
        return None

    hist = df["macd_histogram"].iloc[index]
    prev_hist = df["macd_histogram"].iloc[index - 1]
    ema200 = df["ema_200"].iloc[index]

    if pd.isna(hist) or pd.isna(prev_hist) or pd.isna(ema200):
        return None

    close = df["close"].iloc[index]

    # Bullish: histogram crosses above 0 + price above EMA200
    if prev_hist <= 0 and hist > 0 and close > ema200:
        sl, tp = atr_based_levels(df, index, Direction.LONG)
        return Signal(Direction.LONG, close, sl, tp, "MACD histogram turned positive, price > EMA200")

    # Bearish: histogram crosses below 0 + price below EMA200
    if prev_hist >= 0 and hist < 0 and close < ema200:
        sl, tp = atr_based_levels(df, index, Direction.SHORT)
        return Signal(Direction.SHORT, close, sl, tp, "MACD histogram turned negative, price < EMA200")

    return None


# --------------------------------------------------------------------------
# Strategy 4: Multi-Timeframe Confluence
# --------------------------------------------------------------------------

def _find_latest_row(df: pd.DataFrame, current_ts) -> Optional[int]:
    """Find the index of the most recent row with timestamp <= current_ts."""
    mask = df["timestamp"] <= current_ts
    if not mask.any():
        return None
    return df.loc[mask].index[-1]


def multi_timeframe_confluence_strategy(
    dataframes: Dict[str, pd.DataFrame],
    index: int,
    params: dict,
) -> Optional[Signal]:
    """
    Daily: trend direction (price vs EMA50)
    H4: signal confirmation (MACD histogram direction)
    H1: entry timing (RSI pullback zone)
    """
    primary_tf = params.get("primary_timeframe", "H1")
    df_h1 = dataframes.get(primary_tf)
    df_h4 = dataframes.get("H4") or dataframes.get("4H")
    df_d = dataframes.get("D")

    if df_h1 is None or df_h4 is None or df_d is None:
        return None
    if index < 1 or index >= len(df_h1):
        return None

    current_ts = df_h1["timestamp"].iloc[index]
    close_h1 = df_h1["close"].iloc[index]
    rsi_h1 = df_h1["rsi_14"].iloc[index]

    # Find corresponding daily and H4 rows
    d_idx = _find_latest_row(df_d, current_ts)
    h4_idx = _find_latest_row(df_h4, current_ts)

    if d_idx is None or h4_idx is None:
        return None

    ema50_d = df_d["ema_50"].iloc[d_idx]
    close_d = df_d["close"].iloc[d_idx]
    macd_hist_h4 = df_h4["macd_histogram"].iloc[h4_idx]

    if pd.isna(ema50_d) or pd.isna(macd_hist_h4) or pd.isna(rsi_h1):
        return None

    # Daily trend
    daily_bullish = close_d > ema50_d
    daily_bearish = close_d < ema50_d

    # H4 confirmation
    h4_bullish = macd_hist_h4 > 0
    h4_bearish = macd_hist_h4 < 0

    # H1 entry timing — look for RSI pullback
    # Bullish: all align + RSI in 40-50 (pullback zone)
    if daily_bullish and h4_bullish and 40 <= rsi_h1 <= 50:
        sl, tp = atr_based_levels(df_h1, index, Direction.LONG)
        return Signal(Direction.LONG, close_h1, sl, tp,
                      f"MTF confluence: Daily bullish, H4 MACD+, H1 RSI pullback ({rsi_h1:.1f})")

    # Bearish: all align + RSI in 50-60 (pullback zone)
    if daily_bearish and h4_bearish and 50 <= rsi_h1 <= 60:
        sl, tp = atr_based_levels(df_h1, index, Direction.SHORT)
        return Signal(Direction.SHORT, close_h1, sl, tp,
                      f"MTF confluence: Daily bearish, H4 MACD-, H1 RSI pullback ({rsi_h1:.1f})")

    return None


# --------------------------------------------------------------------------
# Strategy Registry
# --------------------------------------------------------------------------

STRATEGY_REGISTRY: dict[str, tuple] = {
    "ema_crossover": (ema_crossover_strategy, "EMA Crossover (20/50)"),
    "rsi_reversion": (rsi_mean_reversion_strategy, "RSI Mean Reversion"),
    "macd_momentum": (macd_momentum_strategy, "MACD Momentum"),
    "mtf_confluence": (multi_timeframe_confluence_strategy, "Multi-TF Confluence"),
}
