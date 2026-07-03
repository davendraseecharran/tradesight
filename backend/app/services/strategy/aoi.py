"""Area of Interest (AOI) detection — step 2 of the 3-step strategy.

An AOI is a horizontal zone between the current structure high and low that
price has *reacted* to at least 3 times (any mix of support/resistance
touches). No 3 touches = no AOI = no trade.

Touches are counted from confirmed swing points: a swing high or low whose
price falls inside the zone is one reaction. Zones are built by clustering
swing prices within a tolerance derived from ATR, so zone width adapts to
each instrument's volatility.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from backend.app.services.strategy.structure import StructureState, Swing


@dataclass
class AOI:
    top: float
    bottom: float
    touches: int
    support_touches: int      # touches from swing lows (price bounced up)
    resistance_touches: int   # touches from swing highs (price rejected down)

    @property
    def mid(self) -> float:
        return (self.top + self.bottom) / 2

    def contains(self, price: float) -> bool:
        return self.bottom <= price <= self.top

    def candle_at_or_inside(self, high: float, low: float) -> bool:
        """True if the candle traded inside or at the zone (any overlap)."""
        return low <= self.top and high >= self.bottom


def _atr(df: pd.DataFrame, period: int = 14, upto: Optional[int] = None) -> float:
    """Simple ATR on the last `period` closed bars (no indicator deps)."""
    end = len(df) if upto is None else min(upto, len(df))
    if end < 2:
        return 0.0
    sl = df.iloc[max(0, end - period - 1): end]
    prev_close = sl["close"].shift(1)
    tr = pd.concat([
        sl["high"] - sl["low"],
        (sl["high"] - prev_close).abs(),
        (sl["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    val = tr.dropna().mean()
    return float(val) if pd.notna(val) else 0.0


def find_aois(
    df: pd.DataFrame,
    state: StructureState,
    upto: Optional[int] = None,
    min_touches: int = 3,
    zone_atr_fraction: float = 0.5,
    lookback_swings: int = 40,
) -> list[AOI]:
    """Find valid AOIs inside the current structure range.

    Only zones strictly inside [structure low, structure high] qualify —
    "you would draw the zone anywhere in between the higher high and the
    higher low. Nothing below, nothing on top."

    Returns AOIs sorted by touch count (strongest first).
    """
    if state.high is None or state.low is None:
        return []

    range_top = max(state.high.price, state.low.price)
    range_bottom = min(state.high.price, state.low.price)

    atr = _atr(df, upto=upto)
    if atr <= 0:
        return []
    zone_half_width = atr * zone_atr_fraction / 2

    # Candidate anchor prices: recent swing points inside the range. The
    # range is expanded by one zone width so touches sitting exactly at the
    # HL/HH boundary still count (the final zone must overlap the strict
    # range, checked below).
    margin = zone_half_width * 2
    swings: list[Swing] = [
        s for s in state.swings[-lookback_swings:]
        if range_bottom - margin <= s.price <= range_top + margin
    ]
    if len(swings) < min_touches:
        return []

    # Greedy clustering: sort by price, group swings within the zone width
    by_price = sorted(swings, key=lambda s: s.price)
    clusters: list[list[Swing]] = []
    for s in by_price:
        if clusters and s.price - clusters[-1][0].price <= zone_half_width * 2:
            clusters[-1].append(s)
        else:
            clusters.append([s])

    aois: list[AOI] = []
    for cluster in clusters:
        if len(cluster) < min_touches:
            continue
        prices = [s.price for s in cluster]
        # Zone must overlap the structure range ("nothing below, nothing on top")
        if max(prices) + zone_half_width < range_bottom or min(prices) - zone_half_width > range_top:
            continue
        aois.append(AOI(
            top=max(prices) + zone_half_width,
            bottom=min(prices) - zone_half_width,
            touches=len(cluster),
            support_touches=sum(1 for s in cluster if s.kind == "low"),
            resistance_touches=sum(1 for s in cluster if s.kind == "high"),
        ))

    aois.sort(key=lambda a: a.touches, reverse=True)
    return aois


def nearest_aoi(aois: list[AOI], price: float) -> Optional[AOI]:
    """The AOI nearest to current price — 'always treat the nearest one to
    price as the first area'."""
    if not aois:
        return None
    return min(aois, key=lambda a: abs(a.mid - price))
