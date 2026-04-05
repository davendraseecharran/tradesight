from __future__ import annotations

import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, IchimokuIndicator, MACD
from ta.volatility import AverageTrueRange, BollingerBands
from ta.volume import VolumeWeightedAveragePrice


def compute_indicators(df: pd.DataFrame, timeframe: str = "H4") -> pd.DataFrame:
    """Compute all technical indicators on an OHLCV DataFrame.

    Expects columns: open, high, low, close, volume.
    Returns the same DataFrame with indicator columns added.
    """
    df = df.copy()

    # RSI (14)
    df["rsi_14"] = RSIIndicator(close=df["close"], window=14).rsi()

    # MACD (12, 26, 9)
    macd = MACD(close=df["close"], window_slow=26, window_fast=12, window_sign=9)
    df["macd_line"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_histogram"] = macd.macd_diff()

    # EMAs
    for period in [20, 50, 200]:
        df[f"ema_{period}"] = EMAIndicator(close=df["close"], window=period).ema_indicator()

    # Bollinger Bands (20, 2)
    bb = BollingerBands(close=df["close"], window=20, window_dev=2)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_middle"] = bb.bollinger_mavg()
    df["bb_lower"] = bb.bollinger_lband()

    # ATR (14)
    df["atr_14"] = AverageTrueRange(
        high=df["high"], low=df["low"], close=df["close"], window=14
    ).average_true_range()

    # VWAP — only meaningful for intraday timeframes
    if timeframe in ("H1", "H4", "1H"):
        try:
            df["vwap"] = VolumeWeightedAveragePrice(
                high=df["high"], low=df["low"], close=df["close"], volume=df["volume"]
            ).volume_weighted_average_price()
        except Exception:
            df["vwap"] = np.nan
    else:
        df["vwap"] = np.nan

    # Ichimoku Cloud
    ichimoku = IchimokuIndicator(high=df["high"], low=df["low"])
    df["ichimoku_tenkan"] = ichimoku.ichimoku_conversion_line()
    df["ichimoku_kijun"] = ichimoku.ichimoku_base_line()
    df["ichimoku_senkou_a"] = ichimoku.ichimoku_a()
    df["ichimoku_senkou_b"] = ichimoku.ichimoku_b()

    return df


def compute_fibonacci_levels(df: pd.DataFrame, lookback: int = 100) -> dict:
    """Compute Fibonacci retracement levels from swing high/low."""
    recent = df.tail(lookback)
    swing_high = recent["high"].max()
    swing_low = recent["low"].min()
    diff = swing_high - swing_low

    return {
        "swing_high": swing_high,
        "swing_low": swing_low,
        "level_0": swing_high,
        "level_236": swing_high - diff * 0.236,
        "level_382": swing_high - diff * 0.382,
        "level_500": swing_high - diff * 0.5,
        "level_618": swing_high - diff * 0.618,
        "level_786": swing_high - diff * 0.786,
        "level_100": swing_low,
    }


def compute_support_resistance(df: pd.DataFrame, lookback: int = 50, tolerance: float = 0.002) -> dict:
    """Detect support/resistance zones using local min/max clustering."""
    recent = df.tail(lookback)
    highs = recent["high"].values
    lows = recent["low"].values

    # Find local maxima (resistance) and minima (support)
    resistance_levels = []
    support_levels = []

    for i in range(2, len(highs) - 2):
        if highs[i] > highs[i - 1] and highs[i] > highs[i - 2] and highs[i] > highs[i + 1] and highs[i] > highs[i + 2]:
            resistance_levels.append(float(highs[i]))
        if lows[i] < lows[i - 1] and lows[i] < lows[i - 2] and lows[i] < lows[i + 1] and lows[i] < lows[i + 2]:
            support_levels.append(float(lows[i]))

    # Cluster nearby levels
    resistance = _cluster_levels(resistance_levels, tolerance)
    support = _cluster_levels(support_levels, tolerance)

    return {"support": support, "resistance": resistance}


def _cluster_levels(levels: list[float], tolerance: float) -> list[float]:
    """Merge nearby price levels into zones."""
    if not levels:
        return []
    levels = sorted(levels)
    clustered = [levels[0]]
    for level in levels[1:]:
        if abs(level - clustered[-1]) / clustered[-1] < tolerance:
            clustered[-1] = (clustered[-1] + level) / 2  # average the cluster
        else:
            clustered.append(level)
    return clustered
