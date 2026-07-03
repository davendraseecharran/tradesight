#!/usr/bin/env python3
"""
TradeSight — 3-Step Strategy Engine Tests
Synthetic-data tests for structure, AOI, patterns, and the full engine.
Zero API calls, zero cost.
"""
import sys
import os

venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "python")
if os.path.exists(venv_python) and os.path.realpath(sys.executable) != os.path.realpath(venv_python):
    os.execv(venv_python, [venv_python] + sys.argv)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta, timezone

import pandas as pd

from backend.app.services.strategy.structure import analyze_structure, find_swings, nearest_structure_target
from backend.app.services.strategy.aoi import AOI, find_aois, nearest_aoi
from backend.app.services.strategy import patterns
from backend.app.services.strategy.engine import evaluate_setup, get_pip_size

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
results = {"passed": 0, "failed": 0}


def check(name, ok, detail=""):
    if ok:
        print(f"  {PASS} {name}")
        results["passed"] += 1
    else:
        print(f"  {FAIL} {name}{' — ' + str(detail) if detail else ''}")
        results["failed"] += 1


def zigzag(points, bars_per_leg=5, start_time=None, hours=4, wick=0.05):
    """Build an OHLC dataframe interpolating linearly between turn prices."""
    closes = []
    for a, b in zip(points[:-1], points[1:]):
        for j in range(1, bars_per_leg + 1):
            closes.append(a + (b - a) * j / bars_per_leg)
    opens = [points[0]] + closes[:-1]
    t0 = start_time or datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for idx, (o, c) in enumerate(zip(opens, closes)):
        rows.append({
            "timestamp": t0 + timedelta(hours=hours * idx),
            "open": o,
            "high": max(o, c) + wick,
            "low": min(o, c) - wick,
            "close": c,
        })
    return pd.DataFrame(rows)


def candles(rows, start_time=None, hours=4):
    """Build a dataframe from explicit (o, h, l, c) tuples."""
    t0 = start_time or datetime(2026, 1, 1, tzinfo=timezone.utc)
    return pd.DataFrame([
        {"timestamp": t0 + timedelta(hours=hours * i),
         "open": o, "high": h, "low": l, "close": c}
        for i, (o, h, l, c) in enumerate(rows)
    ])


# ═══ 1. Swing detection ═══════════════════════════════════════════════════
print("\n[1] Swing detection")
df = zigzag([100, 110, 95, 108, 97])
swings = find_swings(df, k=2)
kinds = [s.kind for s in swings]
check("finds interior turns", len(swings) == 3, f"got {len(swings)}")
check("swings alternate", all(a != b for a, b in zip(kinds, kinds[1:])), kinds)
check("first is the 110 high", swings and swings[0].kind == "high" and abs(swings[0].price - 110.05) < 0.2,
      swings[0] if swings else "none")

# ═══ 2. Structure classification ══════════════════════════════════════════
print("\n[2] Market structure (top-down analysis)")
up = zigzag([90, 100, 95, 105, 98, 110, 103, 112])
st = analyze_structure(up, k=2)
check("rising zigzag → bullish", st.trend == "bullish", st.trend)

down = zigzag([112, 103, 110, 98, 105, 95, 100, 90])
st_d = analyze_structure(down, k=2)
check("falling zigzag → bearish", st_d.trend == "bearish", st_d.trend)

# Body-close flip: uptrend, then a leg that closes below the HL
flip = zigzag([90, 100, 95, 105, 98, 110, 88])
st_f = analyze_structure(flip, k=2)
check("body close below HL flips to bearish", st_f.trend == "bearish", st_f.trend)

# TP helper: nearest structure point above entry
tgt = nearest_structure_target(st, entry=104.0, direction="bullish")
check("nearest structure target above entry", tgt is not None and 104.5 < tgt < 106, tgt)

# ═══ 3. AOI detection ══════════════════════════════════════════════════════
print("\n[3] Area of Interest (3-touch rule)")
# Bullish market bouncing 3x near 100 with rising highs
aoi_df = zigzag([94, 106, 100.0, 107, 100.2, 108, 100.35, 109])
aoi_state = analyze_structure(aoi_df, k=2)
check("AOI fixture stays bullish", aoi_state.trend == "bullish", aoi_state.trend)
aois = find_aois(aoi_df, aoi_state)
check("triple-bounce → valid AOI found", len(aois) >= 1, f"{len(aois)} zones")
if aois:
    z = nearest_aoi(aois, 100.5)
    check("AOI has >= 3 touches", z.touches >= 3, z.touches)
    check("AOI zone brackets the bounce level", z.bottom < 100.0 and z.top > 100.35,
          f"[{z.bottom:.2f}, {z.top:.2f}]")

# Only 2 touches → no AOI
two_touch = zigzag([94, 106, 100.0, 107, 100.2, 108, 104.5, 109])
tt_state = analyze_structure(two_touch, k=2)
tt_aois = find_aois(two_touch, tt_state)
near_100 = [a for a in tt_aois if a.contains(100.1)]
check("no 3 touches, no AOI", len(near_100) == 0, f"{len(near_100)} zones at level")

# ═══ 4. Confirmation patterns ═══════════════════════════════════════════════
print("\n[4] Confirmation candles (closed-candle entry signals)")
be = candles([(101.5, 101.6, 100.2, 100.3),   # bear candle
              (100.2, 102.0, 100.0, 101.9)])  # bull engulfs it
check("bullish engulfing detected", patterns.bullish_engulfing(be, 1))
check("...and is not bearish", not patterns.bearish_engulfing(be, 1))

not_engulf = candles([(101.5, 101.6, 100.2, 100.3),
                      (100.4, 101.2, 100.2, 101.0)])  # bull but smaller body
check("small bull candle is NOT engulfing", not patterns.bullish_engulfing(not_engulf, 1))

ms = candles([(103.0, 103.1, 100.9, 101.0),   # big bear
              (101.0, 101.3, 100.7, 100.9),   # small indecision
              (100.9, 103.4, 100.8, 103.3)])  # strong bull
check("morning star detected", patterns.morning_star(ms, 2))

es = candles([(101.0, 103.2, 100.9, 103.0),
              (103.0, 103.4, 102.8, 103.1),
              (103.1, 103.2, 100.6, 100.8)])
check("evening star detected", patterns.evening_star(es, 2))

hammer = candles([(101.0, 101.2, 98.5, 100.9)])  # long lower wick, closes high
check("bullish rejection (hammer) detected", patterns.bullish_rejection(hammer, 0))

star = candles([(101.0, 103.5, 100.9, 101.1)])  # long upper wick
check("bearish rejection (shooting star) detected", patterns.bearish_rejection(star, 0))

check("bullish_confirmation names the pattern",
      patterns.bullish_confirmation(be, 1) == "bullish_engulfing",
      patterns.bullish_confirmation(be, 1))

# ═══ 5. Full engine ════════════════════════════════════════════════════════
print("\n[5] Engine — full 3-step checklist")

# H4: bullish, triple-tested AOI ~100, price returns and prints an engulfing
# close to the zone (entry must be near the AOI or R:R degrades below 1:2)
h4 = zigzag([94, 106, 100.0, 107, 100.2, 108, 100.35, 109, 101.6])
extra = candles([(101.2, 101.3, 100.55, 100.7),   # bear candle dipping to zone
                 (100.6, 101.4, 100.5, 101.3)],   # bullish engulfing AT the AOI
                start_time=h4["timestamp"].iloc[-1] + timedelta(hours=4))
h4_full = pd.concat([h4, extra], ignore_index=True)

weekly = zigzag([80, 100, 90, 110, 100, 120], hours=168)
daily = zigzag([85, 100, 92, 108, 98, 115], hours=24)
frames = {"W": weekly, "D": daily, "H4": h4_full}

setup = evaluate_setup(frames, "EUR_USD")
check("W+D bullish + AOI retest + engulfing → LONG setup", setup is not None and setup["direction"] == "long",
      setup["reason"] if setup else "no setup returned")
if setup:
    check("SL sits below the AOI", setup["stop_loss"] < 100.0, setup["stop_loss"])
    check("TP at nearest structure point above entry",
          setup["take_profit_1"] > setup["entry_price"], setup["take_profit_1"])
    check("R:R >= 1:2", setup["risk_reward_ratio"] >= 2.0, setup["risk_reward_ratio"])
    check("pattern is the engulfing", setup["pattern"] == "bullish_engulfing", setup["pattern"])

# Gate 1: Weekly and Daily disagree → no trade
frames_conflict = {"W": zigzag([120, 100, 110, 90, 100, 80], hours=168), "D": daily, "H4": h4_full}
check("W bearish vs D bullish → NO trade", evaluate_setup(frames_conflict, "EUR_USD") is None)

# Gate 3: at the AOI but no confirmation candle → no trade
no_confirm = candles([(101.6, 101.7, 100.55, 100.7),
                      (100.7, 100.9, 100.4, 100.5)],  # weak bear drift, no signal
                     start_time=h4["timestamp"].iloc[-1] + timedelta(hours=4))
frames_nc = {"W": weekly, "D": daily, "H4": pd.concat([h4, no_confirm], ignore_index=True)}
check("at AOI without confirmation → NO trade", evaluate_setup(frames_nc, "EUR_USD") is None)

# Gate 2: price away from the AOI (on the way) → no trade even with a bull candle
away = candles([(105.0, 105.1, 104.2, 104.3),
                (104.2, 106.0, 104.0, 105.9)],  # engulfing but nowhere near AOI
               start_time=h4["timestamp"].iloc[-1] + timedelta(hours=4))
frames_away = {"W": weekly, "D": daily, "H4": pd.concat([h4, away], ignore_index=True)}
check("confirmation NOT at the AOI → NO trade", evaluate_setup(frames_away, "EUR_USD") is None)

# R:R gate
setup_tight = evaluate_setup(frames, "EUR_USD", params={"min_rr": 50.0})
check("R:R below minimum → NO trade", setup_tight is None)

# ═══ 6. Pip sizes ═══════════════════════════════════════════════════════════
print("\n[6] Pip sizes")
check("EUR_USD pip 0.0001", get_pip_size("EUR_USD") == 0.0001)
check("USD_JPY pip 0.01", get_pip_size("USD_JPY") == 0.01)
check("XAU_USD pip 0.1", get_pip_size("XAU_USD") == 0.1)

# ═══ Verdict ═══════════════════════════════════════════════════════════════
total = results["passed"] + results["failed"]
print(f"\n{'=' * 50}\n  {results['passed']}/{total} passed, {results['failed']} failed")
sys.exit(0 if results["failed"] == 0 else 1)
