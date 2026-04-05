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

# Start backend
echo "[1/2] Starting backend (port 8000)..."
nohup python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload \
    > /tmp/tradesight-backend.log 2>&1 &
echo $! > /tmp/tradesight-backend.pid
echo "  Backend PID: $(cat /tmp/tradesight-backend.pid)"

# Start frontend
echo "[2/2] Starting frontend (port 5173)..."
cd "$DIR/frontend"
nohup npm run dev -- --host 0.0.0.0 \
    > /tmp/tradesight-frontend.log 2>&1 &
echo $! > /tmp/tradesight-frontend.pid
echo "  Frontend PID: $(cat /tmp/tradesight-frontend.pid)"

cd "$DIR"

echo ""
echo "=== TradeSight Running ==="
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:5173"
echo "  Health:   http://localhost:8000/health"
echo ""
echo "Logs:"
echo "  tail -f /tmp/tradesight-backend.log"
echo "  tail -f /tmp/tradesight-frontend.log"
echo ""
echo "Stop with: ./scripts/stop.sh"
