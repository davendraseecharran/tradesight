#!/bin/bash
# TradeSight — Watchdog: restarts services if they crash OR hang
# Designed to run via LaunchAgent every 5 minutes (see install_watchdog.sh)

DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG="/tmp/tradesight-watchdog.log"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S'): $1" >> "$LOG"; }

restart_service() {
    local svc=$1
    local pidfile="/tmp/tradesight-${svc}.pid"

    # Kill any lingering process first
    if [ -f "$pidfile" ]; then
        local old_pid=$(cat "$pidfile")
        kill "$old_pid" 2>/dev/null
        sleep 1
        kill -9 "$old_pid" 2>/dev/null
    fi

    cd "$DIR"
    if [ -f "$DIR/.venv/bin/activate" ]; then
        source "$DIR/.venv/bin/activate"
    elif [ -f "$DIR/venv/bin/activate" ]; then
        source "$DIR/venv/bin/activate"
    fi

    if [ "$svc" = "backend" ]; then
        nohup python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 \
            > /tmp/tradesight-backend.log 2>&1 &
        echo $! > "$pidfile"
    elif [ "$svc" = "frontend" ]; then
        cd "$DIR/frontend"
        nohup npm run dev -- --host 0.0.0.0 \
            > /tmp/tradesight-frontend.log 2>&1 &
        echo $! > "$pidfile"
    fi
    log "$svc restarted (PID $(cat $pidfile))"
}

# ── Backend: process must be alive AND /health must answer ──────────────────
backend_ok=false
pidfile="/tmp/tradesight-backend.pid"
if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    # Alive — but is it responsive? A hung event loop passes kill -0.
    if curl -sf -m 10 http://localhost:8000/health > /dev/null 2>&1; then
        backend_ok=true
    else
        log "backend PID alive but /health unresponsive — restarting"
    fi
else
    log "backend is down"
fi
[ "$backend_ok" = false ] && restart_service backend

# ── Frontend: process alive is sufficient ────────────────────────────────────
pidfile="/tmp/tradesight-frontend.pid"
if ! { [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; }; then
    log "frontend is down"
    restart_service frontend
fi
