#!/bin/bash
# TradeSight — Stop all services
echo "=== TradeSight Shutdown ==="

for svc in backend frontend; do
    pidfile="/tmp/tradesight-${svc}.pid"
    if [ -f "$pidfile" ]; then
        pid=$(cat "$pidfile")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid"
            echo "  Stopped $svc (PID $pid)"
        else
            echo "  $svc was not running (stale PID $pid)"
        fi
        rm -f "$pidfile"
    else
        echo "  No PID file for $svc"
    fi
done

# Kill any remaining uvicorn/vite processes for tradesight
pkill -f "uvicorn backend.app.main" 2>/dev/null && echo "  Cleaned up lingering uvicorn" || true
pkill -f "tradesight/frontend.*vite" 2>/dev/null && echo "  Cleaned up lingering vite" || true

echo "=== TradeSight Stopped ==="
