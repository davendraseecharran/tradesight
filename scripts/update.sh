#!/bin/bash
# TradeSight — One-command update for the deployment Mac.
#   ./scripts/update.sh
# Stops services, pulls the latest code, refreshes dependencies, reinstalls
# the LaunchAgents (so plist fixes actually land), restarts, and verifies
# health. Prints PASS/FAIL at the end — no other commands needed.
set -e

DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"

echo "=== TradeSight Update ==="

echo "[1/6] Stopping services..."
"$DIR/scripts/stop.sh" || true

echo "[2/6] Pulling latest code..."
git pull --ff-only

echo "[3/6] Refreshing Python dependencies..."
if [ -f ".venv/bin/pip" ]; then
    .venv/bin/pip install -q -r backend/requirements.txt
fi

echo "[4/6] Reinstalling self-healing LaunchAgents (picks up plist fixes)..."
bash "$DIR/scripts/install_watchdog.sh"

echo "[5/6] Starting services..."
"$DIR/scripts/start.sh"

echo "[6/6] Verifying health (waiting up to 30s)..."
ok=false
for i in $(seq 1 15); do
    sleep 2
    body=$(curl -sf -m 5 http://localhost:8000/health 2>/dev/null) || continue
    if echo "$body" | grep -q '"scheduler_running": *true'; then
        ok=true
        break
    fi
done

echo ""
if [ "$ok" = true ]; then
    version=$(echo "$body" | python3 -c "import json,sys; print(json.load(sys.stdin).get('version','?'))" 2>/dev/null || echo "?")
    echo "=== UPDATE PASSED — TradeSight v$version running, scheduler active ==="
    echo "$body" | python3 -m json.tool 2>/dev/null | head -14
else
    echo "=== UPDATE FAILED — backend not healthy after 30s ==="
    echo "Last 20 log lines:"
    tail -20 /tmp/tradesight-backend.log 2>/dev/null
    exit 1
fi
