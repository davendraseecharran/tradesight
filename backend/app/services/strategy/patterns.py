"""Confirmation entry signals — step 3 of the 3-step strategy.

All patterns are evaluated on CLOSED candles only ("you always want to enter
off of a confirmation candlestick closure, not an anticipation"). Index `i`
must point at a closed bar; callers are responsible for never passing the
still-forming candle.

Patterns from the spec: bullish/bearish engulfing, morning/evening star,
and doji/wick rejection (hammer / shooting star).
"""
from __future__ import annotations

from typing import Optional

import pandas as pd


def _body(o: float, c: float) -> float:
    return abs(c - o)


def _is_bull(o: float, c: float) -> bool:
    return c > o


def bullish_engulfing(df: pd.DataFrame, i: int) -> bool:
    """Bull candle whose body engulfs the previous (bear) candle's body."""
    if i < 1:
        return False
    o1, c1 = df["open"].iloc[i - 1], df["close"].iloc[i - 1]
    o2, c2 = df["open"].iloc[i], df["close"].iloc[i]
    return (
        not _is_bull(o1, c1)
        and _is_bull(o2, c2)
        and o2 <= c1
        and c2 >= o1
        and _body(o2, c2) > _body(o1, c1)
    )


def bearish_engulfing(df: pd.DataFrame, i: int) -> bool:
    if i < 1:
        return False
    o1, c1 = df["open"].iloc[i - 1], df["close"].iloc[i - 1]
    o2, c2 = df["open"].iloc[i], df["close"].iloc[i]
    return (
        _is_bull(o1, c1)
        and not _is_bull(o2, c2)
        and o2 >= c1
        and c2 <= o1
        and _body(o2, c2) > _body(o1, c1)
    )


def morning_star(df: pd.DataFrame, i: int) -> bool:
    """Down candle, small indecision candle, then a bull candle that engulfs
    (closes above the open of) the first candle's body midpoint."""
    if i < 2:
        return False
    o1, c1 = df["open"].iloc[i - 2], df["close"].iloc[i - 2]
    o2, c2 = df["open"].iloc[i - 1], df["close"].iloc[i - 1]
    o3, c3 = df["open"].iloc[i], df["close"].iloc[i]
    body1, body2 = _body(o1, c1), _body(o2, c2)
    if body1 == 0:
        return False
    return (
        not _is_bull(o1, c1)
        and body2 < body1 * 0.5
        and _is_bull(o3, c3)
        and c3 > (o1 + c1) / 2
    )


def evening_star(df: pd.DataFrame, i: int) -> bool:
    if i < 2:
        return False
    o1, c1 = df["open"].iloc[i - 2], df["close"].iloc[i - 2]
    o2, c2 = df["open"].iloc[i - 1], df["close"].iloc[i - 1]
    o3, c3 = df["open"].iloc[i], df["close"].iloc[i]
    body1, body2 = _body(o1, c1), _body(o2, c2)
    if body1 == 0:
        return False
    return (
        _is_bull(o1, c1)
        and body2 < body1 * 0.5
        and not _is_bull(o3, c3)
        and c3 < (o1 + c1) / 2
    )


def bullish_rejection(df: pd.DataFrame, i: int, wick_body_ratio: float = 2.0) -> bool:
    """Hammer / dragonfly doji: long lower wick shows price tried to break
    down and was pushed back up. 'The bigger the wick, the better.'"""
    o = df["open"].iloc[i]
    h = df["high"].iloc[i]
    l = df["low"].iloc[i]
    c = df["close"].iloc[i]
    body = _body(o, c)
    lower_wick = min(o, c) - l
    upper_wick = h - max(o, c)
    rng = h - l
    if rng == 0:
        return False
    if body == 0:
        return lower_wick > rng * 0.6
    return (
        lower_wick >= body * wick_body_ratio
        and lower_wick > upper_wick * 2
        and c >= (h + l) / 2  # closes in the upper half
    )


def bearish_rejection(df: pd.DataFrame, i: int, wick_body_ratio: float = 2.0) -> bool:
    """Shooting star / gravestone doji: long upper wick rejection."""
    o = df["open"].iloc[i]
    h = df["high"].iloc[i]
    l = df["low"].iloc[i]
    c = df["close"].iloc[i]
    body = _body(o, c)
    lower_wick = min(o, c) - l
    upper_wick = h - max(o, c)
    rng = h - l
    if rng == 0:
        return False
    if body == 0:
        return upper_wick > rng * 0.6
    return (
        upper_wick >= body * wick_body_ratio
        and upper_wick > lower_wick * 2
        and c <= (h + l) / 2  # closes in the lower half
    )


def bullish_confirmation(df: pd.DataFrame, i: int) -> Optional[str]:
    """Return the name of the strongest bullish confirmation at bar i, or None."""
    if morning_star(df, i):
        return "morning_star"
    if bullish_engulfing(df, i):
        return "bullish_engulfing"
    if bullish_rejection(df, i):
        return "bullish_rejection"
    return None


def bearish_confirmation(df: pd.DataFrame, i: int) -> Optional[str]:
    if evening_star(df, i):
        return "evening_star"
    if bearish_engulfing(df, i):
        return "bearish_engulfing"
    if bearish_rejection(df, i):
        return "bearish_rejection"
    return None
