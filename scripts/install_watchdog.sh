#!/bin/bash
# TradeSight — One-command watchdog install
# Installs two LaunchAgents:
#   1. com.tradesight.watchdog  — restarts backend/frontend every 5 min if dead/hung
#   2. com.tradesight.caffeinate — keeps the Mac awake while on AC power
# Both survive reboots (RunAtLoad) so TradeSight recovers automatically.
set -e

DIR="$(cd "$(dirname "$0")/.." && pwd)"
AGENTS="$HOME/Library/LaunchAgents"
mkdir -p "$AGENTS"

echo "=== TradeSight Watchdog Install ==="
echo "Project dir: $DIR"

# ── 1. Watchdog agent (paths templated to this machine) ─────────────────────
cat > "$AGENTS/com.tradesight.watchdog.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.tradesight.watchdog</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$DIR/scripts/watchdog.sh</string>
    </array>
    <key>StartInterval</key>
    <integer>300</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/tradesight-watchdog.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/tradesight-watchdog.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>
</dict>
</plist>
EOF

# ── 2. Keep-awake agent ───────────────────────────────────────────────────────
cat > "$AGENTS/com.tradesight.caffeinate.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.tradesight.caffeinate</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/caffeinate</string>
        <string>-s</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
EOF

# ── 3. (Re)load both ──────────────────────────────────────────────────────────
for label in com.tradesight.watchdog com.tradesight.caffeinate; do
    launchctl unload "$AGENTS/$label.plist" 2>/dev/null || true
    launchctl load "$AGENTS/$label.plist"
done

echo ""
echo "Verifying..."
sleep 2
if launchctl list | grep -q com.tradesight.watchdog; then
    echo "  ✓ watchdog loaded (runs every 5 min + on boot)"
else
    echo "  ✗ watchdog FAILED to load"
    exit 1
fi
if launchctl list | grep -q com.tradesight.caffeinate; then
    echo "  ✓ keep-awake loaded (Mac stays awake on AC power)"
else
    echo "  ✗ keep-awake FAILED to load"
    exit 1
fi
echo ""
echo "=== Install complete — TradeSight now self-heals and survives reboots ==="
