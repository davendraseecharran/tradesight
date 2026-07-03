"""Market structure detection — step 1 of the 3-step strategy.

Implements top-down analysis from the strategy spec (REHAUL_PLAN.md):
- Swing highs/lows via pivot detection (confirmed only after `k` later bars,
  so there is no look-ahead when evaluating historically).
- Trend state: bullish while price holds above the current Higher Low,
  bearish while below the current Lower High. The state only flips when a
  candle BODY (close) breaks the level — wicks don't count.
- "Snake trick": after a new extreme confirms, the opposing level updates to
  the most recent turn (the swing between the old extreme and the new one).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import pandas as pd

Trend = Literal["bullish", "bearish"]


@dataclass
class Swing:
    index: int
    price: float
    kind: Literal["high", "low"]


@dataclass
class StructureState:
    trend: Optional[Trend]          # None until enough swings exist
    high: Optional[Swing]           # HH when bullish / LH when bearish
    low: Optional[Swing]            # HL when bullish / LL when bearish
    swings: list[Swing]

    @property
    def is_bullish(self) -> bool:
        return self.trend == "bullish"

    @property
    def is_bearish(self) -> bool:
        return self.trend == "bearish"


def find_swings(df: pd.DataFrame, k: int = 2, upto: Optional[int] = None) -> list[Swing]:
    """Detect alternating swing highs/lows with a k-bar pivot rule.

    A bar is a swing high if its high is the strict maximum of the 2k+1 bars
    centred on it. A swing at bar i is only *confirmed* once bar i+k has
    closed, so passing `upto` (exclusive end index) never leaks future data.

    Consecutive same-kind swings are collapsed to the more extreme one so the
    result strictly alternates high/low.
    """
    end = len(df) if upto is None else min(upto, len(df))
    highs = df["high"].values
    lows = df["low"].values

    raw: list[Swing] = []
    # Last confirmable pivot centre is end-1-k. Ties (equal highs/lows, e.g.
    # double tops) are attributed to the LAST bar of the flat: >= vs the left
    # window, strictly > vs the right window.
    for i in range(k, end - k):
        left_h, right_h = highs[i - k: i], highs[i + 1: i + k + 1]
        left_l, right_l = lows[i - k: i], lows[i + 1: i + k + 1]
        if highs[i] >= left_h.max() and highs[i] > right_h.max():
            raw.append(Swing(i, float(highs[i]), "high"))
        if lows[i] <= left_l.min() and lows[i] < right_l.min():
            raw.append(Swing(i, float(lows[i]), "low"))

    # Collapse to strictly alternating swings, keeping the more extreme
    swings: list[Swing] = []
    for s in raw:
        if swings and swings[-1].kind == s.kind:
            prev = swings[-1]
            better = (s.price > prev.price) if s.kind == "high" else (s.price < prev.price)
            if better:
                swings[-1] = s
        else:
            swings.append(s)
    return swings


def analyze_structure(df: pd.DataFrame, k: int = 2, upto: Optional[int] = None) -> StructureState:
    """Walk closed bars and return the current structure state.

    Rules (from the spec):
    - Initial trend: first pair of consecutive same-kind swings that makes a
      higher-high+higher-low (bullish) or lower-low+lower-high (bearish).
    - While bullish: body close below the current HL flips to bearish; the
      broken HL becomes the reference for the new bearish leg. A confirmed
      swing high above the current HH updates HH, and HL moves up to the
      lowest confirmed swing low between old HH and new HH.
    - Bearish is symmetric.
    """
    end = len(df) if upto is None else min(upto, len(df))
    swings = find_swings(df, k=k, upto=end)
    if len(swings) < 3:
        return StructureState(None, None, None, swings)

    closes = df["close"].values

    trend: Optional[Trend] = None
    cur_high: Optional[Swing] = None
    cur_low: Optional[Swing] = None

    # Seed trend from the first three alternating swings
    def _seed(idx: int) -> Optional[tuple[Trend, Swing, Swing]]:
        if idx + 2 >= len(swings):
            return None
        a, b, c = swings[idx], swings[idx + 1], swings[idx + 2]
        # high-low-high: c vs a decides direction; low between = reference low
        if a.kind == "high":
            if c.price > a.price:
                return "bullish", c, b
            return "bearish", a, b  # failing to make a higher high; treat prior high as LH
        else:
            if c.price < a.price:
                return "bearish", b, c
            return "bullish", b, a
    seeded = _seed(0)
    if seeded is None:
        return StructureState(None, None, None, swings)
    trend, cur_high, cur_low = seeded

    # Confirmation bar for a swing at index i is bar i + k
    confirmed: list[Swing] = []

    # Walk every bar; at each bar, first absorb any swings that confirm here,
    # then apply the body-close flip rule.
    si = 0
    start_bar = min(cur_high.index, cur_low.index)
    for bar in range(start_bar, end):
        # 1. Swing confirmations at this bar. The HL/LH reference only moves
        #    when a NEW extreme confirms ("if we have a new higher high, you
        #    have to have a new higher low") — never tightened in between.
        while si < len(swings) and swings[si].index + k <= bar:
            s = swings[si]
            confirmed.append(s)
            if trend == "bullish":
                if s.kind == "high" and s.price > cur_high.price:
                    # New HH — HL becomes the lowest confirmed low between the two highs
                    between = [c for c in confirmed
                               if c.kind == "low" and cur_high.index < c.index <= s.index]
                    if between:
                        cur_low = min(between, key=lambda c: c.price)
                    cur_high = s
            elif trend == "bearish":
                if s.kind == "low" and s.price < cur_low.price:
                    between = [c for c in confirmed
                               if c.kind == "high" and cur_low.index < c.index <= s.index]
                    if between:
                        cur_high = max(between, key=lambda c: c.price)
                    cur_low = s
            si += 1

        # 2. Body-close flip rule
        close = closes[bar]
        if trend == "bullish" and close < cur_low.price:
            trend = "bearish"
            # Broken HL is the last structure low; the high of the leg down
            # starts from the most recent swing high
            recent_highs = [c for c in confirmed if c.kind == "high"]
            if recent_highs:
                cur_high = recent_highs[-1]
        elif trend == "bearish" and close > cur_high.price:
            trend = "bullish"
            recent_lows = [c for c in confirmed if c.kind == "low"]
            if recent_lows:
                cur_low = recent_lows[-1]

    return StructureState(trend, cur_high, cur_low, swings)


def nearest_structure_target(
    state: StructureState,
    entry: float,
    direction: Trend,
) -> Optional[float]:
    """Take-profit at the nearest structure point ("next checkpoint").

    For a long: the nearest confirmed swing high above entry.
    For a short: the nearest confirmed swing low below entry.
    """
    if direction == "bullish":
        candidates = [s.price for s in state.swings if s.kind == "high" and s.price > entry]
        return min(candidates) if candidates else None
    candidates = [s.price for s in state.swings if s.kind == "low" and s.price < entry]
    return max(candidates) if candidates else None
