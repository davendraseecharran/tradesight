"""The 3-step strategy engine — deterministic, zero AI calls.

Checklist (all must pass, in order):
  1. Top-down: Weekly AND Daily structure agree on direction.
  2. AOI: price is inside/at the nearest valid (>=3 touch) AOI on the 4H,
     and the AOI sits inside the current 4H structure range.
  3. Confirmation: the last CLOSED 4H candle is an engulfing / star / wick
     rejection in the top-down direction, formed at the AOI.
Then: SL 5-10 pips beyond the AOI far edge, TP at the nearest structure
point, minimum 1:2 risk/reward or no trade.

Exposed in two forms:
  - evaluate_setup(...)          → live pipeline (returns a rich dict)
  - three_step_mtf_strategy(...) → plugs into BacktestEngine.run_multi_timeframe
"""
from __future__ import annotations

from datetime import timedelta
from typing import Dict, Optional

import pandas as pd

from backend.app.services.strategies import Direction, Signal
from backend.app.services.strategy.aoi import AOI, _atr as _aoi_atr, find_aois, nearest_aoi
from backend.app.services.strategy.patterns import bearish_confirmation, bullish_confirmation
from backend.app.services.strategy.structure import (
    StructureState,
    analyze_structure,
    nearest_structure_target,
)

TF_DURATION = {
    "H1": timedelta(hours=1),
    "H4": timedelta(hours=4),
    "D": timedelta(days=1),
    "W": timedelta(days=7),
}

DEFAULTS = {
    "swing_k": 2,             # pivot confirmation bars
    "sl_buffer_pips": 7.0,    # 5-10 pips beyond the AOI ("if hit, you are wrong")
    "sl_atr_fraction": 0.15,  # volatility floor for the SL buffer
    "min_rr": 2.0,            # minimum 1:2 risk/reward, always
    "min_touches": 3,         # no 3 touches, no AOI
}


def get_pip_size(instrument: str) -> float:
    if "JPY" in instrument:
        return 0.01
    if instrument.startswith("XAU"):
        return 0.1
    return 0.0001


# Structure results are cached per dataframe fingerprint — daily/weekly
# states only change every few primary bars, so backtests hit this hard.
# Keyed by content (length + first/last timestamps + last close), never by
# id(), which Python reuses after garbage collection.
_structure_cache: dict[tuple, StructureState] = {}


def _cached_structure(
    df: pd.DataFrame, k: int, upto: Optional[int], cache: bool = True
) -> StructureState:
    if not cache:
        return analyze_structure(df, k=k, upto=upto)
    end = upto if upto is not None else len(df)
    key = (
        len(df),
        str(df["timestamp"].iloc[0]),
        str(df["timestamp"].iloc[-1]),
        float(df["close"].iloc[-1]),
        end,
        k,
    )
    if key not in _structure_cache:
        if len(_structure_cache) > 20_000:
            _structure_cache.clear()
        _structure_cache[key] = analyze_structure(df, k=k, upto=upto)
    return _structure_cache[key]


def _closed_upto(df: pd.DataFrame, tf: str, eval_time) -> int:
    """Number of bars of `df` that have fully CLOSED at `eval_time`.

    A bar stamped ts covers [ts, ts + duration); it is closed when
    ts + duration <= eval_time. Prevents look-ahead in backtests.
    """
    dur = TF_DURATION[tf]
    ts = df["timestamp"]
    return int((ts + dur <= eval_time).sum())


def evaluate_setup(
    dataframes: Dict[str, pd.DataFrame],
    instrument: str,
    params: Optional[dict] = None,
    eval_time=None,
) -> Optional[dict]:
    """Run the full 3-step checklist. Returns a setup dict or None.

    `dataframes` is keyed by OANDA granularity: "W", "D", "H4" (closed
    candles only, ascending). If `eval_time` is given, every timeframe is
    truncated to bars closed at that moment (for backtesting); otherwise all
    provided bars are used (live mode — DB already stores closed candles).
    """
    p = {**DEFAULTS, **(params or {})}
    k = p["swing_k"]

    for tf in ("W", "D", "H4"):
        if tf not in dataframes or len(dataframes[tf]) < (k * 2 + 10):
            return None

    if eval_time is not None:
        upto = {tf: _closed_upto(dataframes[tf], tf, eval_time) for tf in ("W", "D", "H4")}
    else:
        upto = {tf: len(dataframes[tf]) for tf in ("W", "D", "H4")}

    if min(upto.values()) < (k * 2 + 10):
        return None

    # ── Step 1: Top-down — Weekly AND Daily must agree ────────────────────────
    w_state = _cached_structure(dataframes["W"], k, upto["W"])
    d_state = _cached_structure(dataframes["D"], k, upto["D"])

    if w_state.trend is None or d_state.trend is None or w_state.trend != d_state.trend:
        return None
    direction = w_state.trend  # "bullish" | "bearish"

    # ── Step 2: AOI on the 4H, inside the 4H structure range ─────────────────
    h4 = dataframes["H4"]
    h4_end = upto["H4"]
    # H4 upto advances every evaluation, so each state is used exactly once —
    # caching it would only evict the hot Daily/Weekly entries.
    h4_state = _cached_structure(h4, k, h4_end, cache=False)
    if h4_state.trend is None:
        return None

    aois = find_aois(h4, h4_state, upto=h4_end, min_touches=p["min_touches"])
    if not aois:
        return None

    last = h4.iloc[h4_end - 1]  # last closed 4H candle
    aoi = nearest_aoi(aois, float(last["close"]))
    if aoi is None or not aoi.candle_at_or_inside(float(last["high"]), float(last["low"])):
        return None  # not at the area of interest — no entry, ever

    # AOI must be HOLDING at entry: the confirmation candle itself must close
    # back inside/beyond the zone on the trade side. Earlier wick-throughs are
    # allowed (a sweep-and-reclaim is a strong entry), but entering while the
    # close is still beyond the zone means the area is broken — "wait for the
    # next one".
    last_close = float(last["close"])
    if direction == "bullish" and last_close < aoi.bottom:
        return None
    if direction == "bearish" and last_close > aoi.top:
        return None

    # ── Step 3: Confirmation candle at the AOI, in the top-down direction ─────
    idx = h4_end - 1
    if direction == "bullish":
        pattern = bullish_confirmation(h4.iloc[:h4_end], idx)
    else:
        pattern = bearish_confirmation(h4.iloc[:h4_end], idx)
    if pattern is None:
        return None

    # ── Risk levels ───────────────────────────────────────────────────────────
    # SL buffer: at least 5-10 pips beyond the AOI, but scaled up to a
    # fraction of ATR on volatile instruments so the stop sits outside noise.
    pip = get_pip_size(instrument)
    atr = _aoi_atr(h4, upto=h4_end)
    buffer = max(p["sl_buffer_pips"] * pip, atr * p["sl_atr_fraction"])
    entry = float(last["close"])

    if direction == "bullish":
        stop_loss = aoi.bottom - buffer
        target = nearest_structure_target(h4_state, entry, "bullish")
        if target is None:
            target = nearest_structure_target(d_state, entry, "bullish")
    else:
        stop_loss = aoi.top + buffer
        target = nearest_structure_target(h4_state, entry, "bearish")
        if target is None:
            target = nearest_structure_target(d_state, entry, "bearish")

    if target is None:
        return None

    # Structural sanity: SL must be on the losing side of entry. If not, the
    # confirmation candle closed beyond the zone and the setup is invalid.
    if direction == "bullish" and entry <= stop_loss:
        return None
    if direction == "bearish" and entry >= stop_loss:
        return None

    risk = abs(entry - stop_loss)
    reward = abs(target - entry)
    if risk <= 0:
        return None
    rr = reward / risk
    if rr < p["min_rr"]:
        return None  # minimum 1:2 or walk away

    return {
        "instrument": instrument,
        "direction": "long" if direction == "bullish" else "short",
        "entry_price": round(entry, 5),
        "stop_loss": round(stop_loss, 5),
        "take_profit_1": round(target, 5),
        "risk_reward_ratio": round(rr, 2),
        "pattern": pattern,
        "aoi": {"top": round(aoi.top, 5), "bottom": round(aoi.bottom, 5),
                "touches": aoi.touches},
        "structure": {
            "weekly": w_state.trend,
            "daily": d_state.trend,
            "h4": h4_state.trend,
        },
        "reason": (
            f"W+D {direction}; 4H {h4_state.trend}; {pattern} at AOI "
            f"[{aoi.bottom:.5f}-{aoi.top:.5f}] ({aoi.touches} touches); RR 1:{rr:.1f}"
        ),
    }


def three_step_mtf_strategy(
    dataframes: Dict[str, pd.DataFrame],
    i: int,
    params: dict,
) -> Optional[Signal]:
    """BacktestEngine adapter. `i` indexes the primary (H4) dataframe."""
    h4 = dataframes[params.get("primary_timeframe", "H4")]
    ts = h4["timestamp"].iloc[i]
    eval_time = ts + TF_DURATION["H4"]  # bar i has just closed

    setup = evaluate_setup(
        dataframes,
        instrument=params.get("instrument", ""),
        params=params,
        eval_time=eval_time,
    )
    if setup is None:
        return None

    return Signal(
        direction=Direction.LONG if setup["direction"] == "long" else Direction.SHORT,
        entry_price=setup["entry_price"],
        stop_loss=setup["stop_loss"],
        take_profit=setup["take_profit_1"],
        reason=setup["reason"],
    )
