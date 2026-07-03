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
| 1 | Mechanical strategy engine (`backend/app/services/strategy/`) + tests | DONE | structure.py, aoi.py, patterns.py, engine.py; test_strategy.py 32/32 |
| 2 | Backtest (free, no AI) — HARD GATE | DONE — PASS | 48mo, sl_atr_fraction=0.20: 29 trades, 31% win, +$13,956, PF 1.35. Sweep monotonic + all-positive (0.05→0.20: PF 1.11→1.35) = robust. Watch-list: GBP_JPY (0/4, -$7.8K in every config) and XAU_USD (PF 0.71 at this setting) |
| 3 | Reliability fixes | DONE | watchdog rewritten (health-check restart), install_watchdog.sh (one command, + keep-awake agent), --reload removed, system_status.py job tracking + failure emails, /health shows problems |
| 4 | Engine-first pipeline | DONE | scan_setups() free; validator.py (compact Sonnet second-opinion, ~$0.01-0.03/call); VALIDATOR_MODE=required/optional/off; old screener.py+analyst.py deleted; pipeline cron moved to H4 closes (1,5,9,13,17,21 UTC +5min) |
| 5 | Report button | DONE | diagnostics.py build_report(); GET /api/v1/report/export?days=N; Download Report button on Dashboard (verified in browser) |
| 6 | Review pass, readiness report, deployment-Mac reload instructions | DONE | code-review subagent: no money-path bugs; DEPLOYMENT.md written; readiness report delivered 2026-07-03. Next: user funds API ($10-20), follows DEPLOYMENT.md |

## Known bugs (evidence gathered 2026-07-03)
1. Prompt caching: 95 AI calls, 0 cache hits — analyst system prompt ~1,233
   tokens is below Sonnet's 2,048 minimum, so cache_control was ignored.
2. Watchdog LaunchAgent never installed (launchctl empty) → app doesn't
   restart after crash/reboot ("not always running").
3. `uvicorn --reload` in scripts/start.sh + watchdog.sh (dev mode in prod).
4. Pipeline failures (e.g. unfunded API) are logged but invisible to user.
5. Candle refresh lives inside backend process — dies with it silently.
