#!/bin/bash
# TradeSight — Watchdog: restarts services if they crash
# Designed to run via LaunchAgent every 5 minutes

DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG="/tmp/tradesight-watchdog.log"

check_and_restart() {
    local svc=$1
    local pidfile="/tmp/tradesight-${svc}.pid"

    if [ -f "$pidfile" ]; then
        local pid=$(cat "$pidfile")
        if kill -0 "$pid" 2>/dev/null; then
            return 0  # Running fine
        fi
    fi

    # Not running — restart
    echo "$(date): $svc is down, restarting..." >> "$LOG"
    cd "$DIR"

    if [ -f "$DIR/.venv/bin/activate" ]; then
        source "$DIR/.venv/bin/activate"
    elif [ -f "$DIR/venv/bin/activate" ]; then
        source "$DIR/venv/bin/activate"
    fi

    if [ "$svc" = "backend" ]; then
        nohup python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload \
            > /tmp/tradesight-backend.log 2>&1 &
        echo $! > "$pidfile"
    elif [ "$svc" = "frontend" ]; then
        cd "$DIR/frontend"
        nohup npm run dev -- --host 0.0.0.0 \
            > /tmp/tradesight-frontend.log 2>&1 &
        echo $! > "$pidfile"
    fi

    echo "$(date): $svc restarted (PID $(cat $pidfile))" >> "$LOG"
}

check_and_restart backend
check_and_restart frontend
