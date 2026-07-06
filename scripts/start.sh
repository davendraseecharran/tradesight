#!/bin/bash
# TradeSight — Start all services
set -e

DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"

echo "=== TradeSight Startup ==="

# Activate virtual environment
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
elif [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# Start backend (no --reload: dev-mode file watching is unstable for a
# long-running production server). Refuse to double-start: after a reboot
# the watchdog may already own port 8000 — spawning a second uvicorn would
# overwrite the PID file with a dead process and send the watchdog into a
# kill/restart flap.
existing=$(lsof -ti :8000 2>/dev/null | head -1)
if [ -n "$existing" ]; then
    echo "[1/2] Backend already running on port 8000 (PID $existing) — not starting a second one."
    echo "$existing" > /tmp/tradesight-backend.pid
else
    echo "[1/2] Starting backend (port 8000)..."
    nohup python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 \
        > /tmp/tradesight-backend.log 2>&1 &
    echo $! > /tmp/tradesight-backend.pid
    echo "  Backend PID: $(cat /tmp/tradesight-backend.pid)"
fi

# Start frontend — only needed in dev. When a production build exists
# (frontend/dist, created by `npm run build`), the backend serves the UI
# on port 8000 and no vite process is needed at all.
if [ -d "$DIR/frontend/dist" ]; then
    echo "[2/2] Frontend: production build found — served by backend on :8000"
else
    echo "[2/2] Starting frontend dev server (port 5173)..."
    cd "$DIR/frontend"
    nohup npm run dev -- --host 0.0.0.0 \
        > /tmp/tradesight-frontend.log 2>&1 &
    echo $! > /tmp/tradesight-frontend.pid
    echo "  Frontend PID: $(cat /tmp/tradesight-frontend.pid)"
fi

cd "$DIR"

echo ""
echo "=== TradeSight Running ==="
if [ -d "$DIR/frontend/dist" ]; then
    echo "  Dashboard: http://localhost:8000  (also http://<this-mac-ip>:8000 from other devices)"
else
    echo "  Backend:  http://localhost:8000"
    echo "  Frontend: http://localhost:5173"
fi
echo "  Health:   http://localhost:8000/health"
echo ""
echo "Logs:"
echo "  tail -f /tmp/tradesight-backend.log"
echo "  tail -f /tmp/tradesight-frontend.log"
echo ""
echo "Stop with: ./scripts/stop.sh"
