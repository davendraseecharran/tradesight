# TradeSight — Deployment MacBook Reload Guide

Follow these steps in order on the deployment MacBook. Total time: ~15 min.
Do NOT fund the Anthropic API until step 6 verifies everything else.

## 1. Stop the old version
```bash
cd ~/tradesight
./scripts/stop.sh
# Also remove any old LaunchAgents from previous attempts
launchctl unload ~/Library/LaunchAgents/com.tradesight.watchdog.plist 2>/dev/null
```

## 2. Pull the rehaul
```bash
git pull
source .venv/bin/activate
pip install -r backend/requirements.txt   # no new deps expected, but cheap
cd frontend && npm install && cd ..
```

## 3. Update .env
Keep your existing keys and add/change these lines:
```
EXECUTION_MODE=FULL_AUTO
VALIDATOR_MODE=required
ANALYST_MIN_CONFIDENCE=7
MAX_RISK_PER_TRADE=0.02
DAILY_LOSS_LIMIT=0.03
MAX_OPEN_POSITIONS=2
MIN_RISK_REWARD_RATIO=2.5
```
Notes:
- `VALIDATOR_MODE=required` means: engine finds a setup -> Claude must
  approve it -> risk manager must approve it -> trade. If the API is
  unfunded/down, NO trades happen and you get an alert email after 3
  failed pipeline runs.
- The engine itself enforces R:R >= 2.0 at detection; the risk manager
  enforces 2.5 at execution.

## 4. Reload data + validate (free, no AI)
```bash
python refresh_data.py        # ~5 min: 7 pairs x 4 timeframes, incl. XAU_USD
python test_strategy.py       # strategy engine unit tests (32 asserts)
python validate_system.py     # env / OANDA / SMTP / DB checks
python test_oanda_refresh.py  # OANDA credential check
python test_email.py          # SMTP check — expect an email in your inbox
```
All must pass before continuing.

## 5. Install the self-healing layer (fixes "not always running")
```bash
chmod +x scripts/*.sh
./scripts/install_watchdog.sh
```
This installs TWO LaunchAgents and verifies they loaded:
- `com.tradesight.watchdog` — every 5 min: restarts the backend if the
  process is dead OR /health hangs; restarts the frontend if dead. Also
  starts everything on boot.
- `com.tradesight.caffeinate` — keeps the Mac awake while on AC power.

Plug the Mac into power. You no longer need to run `caffeinate` manually.

## 6. Start and verify
```bash
./scripts/start.sh
sleep 5
curl -s http://localhost:8000/health | python3 -m json.tool
```
Expect: `"status": "ok"`, `"scheduler_running": true`, `"problems": []`.
Open http://localhost:5173 — charts should render and the Dashboard should
show a **Download Report** button (top right).

## 7. Fund the API and confirm the validator
Buy Anthropic API credits ($10-20 covers 2-3 months at the new call rate),
then confirm the trade path end-to-end:
```bash
curl -s -X POST http://localhost:8000/api/v1/signals/analyze/XAU_USD | python3 -m json.tool
```
- `"status": "no_setup"` with a rules explanation = everything working
  (setups are rare by design — often 0 on any given day).
- `"status": "error"` mentioning the validator = API key/credits problem.

## 8. Weekly review loop
Once a week (or whenever something looks wrong):
1. Click **Download Report** on the Dashboard (7 days) — or fetch
   `http://localhost:8000/api/v1/report/export?days=7`.
2. Upload the JSON file to Claude with: "Here's this week's TradeSight
   report. Review performance and errors, and recommend fixes."
The report contains signals, trades, P&L by pair, AI costs, job health,
candle freshness, and error-log excerpts — everything needed to diagnose
remotely.

## How the new system trades (summary)
- Every hour: candle refresh from OANDA (also before every pipeline run).
- At 01:05, 05:05, 09:05, 13:05, 17:05, 21:05 UTC (just after each 4H
  candle closes): the mechanical 3-step engine scans all 7 markets —
  Weekly+Daily structure agreement, 3-touch Area of Interest, and a
  closed-candle confirmation pattern at the zone, minimum 1:2 R:R.
- Engine candidates (typically 0-3/week) go to the Claude validator
  (momentum, news, and the pair's own trade history — the learning loop),
  then the risk manager (2% risk, 3% daily stop, max 2 positions, news
  blackouts), then auto-execution with SL/TP attached.
- Every 5 min: trade lifecycle (breakeven at 1R, 50% off at TP1, trail at 2R).
- Failures: any job failing 3x in a row emails you automatically.
