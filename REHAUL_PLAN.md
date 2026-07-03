# TradeSight Rehaul Plan — July 2026

Working checkpoint doc for the strategy pivot. If a Claude Code session is
interrupted, the next session resumes from the **Status** column here.
Main chat is the hub; this file is the durable state.

## Context
- ~2 months of paper trading on the old SMC/Claude-led strategy was not
  consistently profitable. Pivoting to the mechanical 3-step system from
  https://www.youtube.com/watch?v=MhWSZp4yS2c (transcript reviewed 2026-07-03).
- Anthropic API for the app is UNFUNDED. Nothing in dev/backtest may require
  live AI calls. User funds (~$10-20) only after the readiness report.
- Decisions made: Python engine + Claude validator; markets = 6 forex pairs
  + XAU_USD; profitable backtest is a HARD GATE before deployment.

## The 3-Step Strategy (spec)
1. **Top-down**: Weekly + Daily structure must agree (HH/HL = bullish,
   LL/LH = bearish; flip only on candle BODY close beyond the last HL/HH).
   Direction = their shared bias; disagree = no trade.
2. **AOI**: zone between current HH and HL with >= 3 touches (any mix of
   support/resistance). No 3 touches = no AOI = no trade. Enter only when
   price is inside/at the nearest AOI.
3. **Confirmation entry** (closed candles only, 4H primary): bullish/bearish
   engulfing, morning/evening star, or doji/wick rejection AT the AOI, in
   the top-down direction.
- SL: 5-10 pips beyond the AOI far edge ("if hit, you are wrong").
- TP: nearest structure point in profit direction; require >= 1:2 R:R else skip.

## Phases

| # | Phase | Status | Notes |
|---|-------|--------|-------|
| 1 | Mechanical strategy engine (`backend/app/services/strategy/`) + tests | DONE | structure.py, aoi.py, patterns.py, engine.py; test_strategy.py passes 37 asserts |
| 2 | Backtest over stored 6-month candles (free, no AI) — HARD GATE | IN PROGRESS | backtest_strategy.py; needs XAU_USD data fetched via refresh |
| 3 | Reliability fixes | TODO | caching (system prompt < 2048 tok = never cached), watchdog LaunchAgent never installed, remove uvicorn --reload, unfunded-API graceful handling + alerting, staleness alarm |
| 4 | Rewire live pipeline: Python engine finds setups, Claude validates | TODO | screener becomes free; analyst becomes validator w/ fixed caching |
| 5 | Report button (backend endpoint + UI download) | TODO | packages signals/trades/P&L/errors/scheduler history into one file |
| 6 | Review pass, readiness report, deployment-Mac reload instructions | TODO | then user funds API and deploys |

## Known bugs (evidence gathered 2026-07-03)
1. Prompt caching: 95 AI calls, 0 cache hits — analyst system prompt ~1,233
   tokens is below Sonnet's 2,048 minimum, so cache_control was ignored.
2. Watchdog LaunchAgent never installed (launchctl empty) → app doesn't
   restart after crash/reboot ("not always running").
3. `uvicorn --reload` in scripts/start.sh + watchdog.sh (dev mode in prod).
4. Pipeline failures (e.g. unfunded API) are logged but invisible to user.
5. Candle refresh lives inside backend process — dies with it silently.
