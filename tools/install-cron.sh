#!/usr/bin/env bash
# Install Rayviews daily launchd job.
#
# Usage:
#   bash tools/install-cron.sh
#
# Uninstall:
#   launchctl unload ~/Library/LaunchAgents/com.rayviewslab.daily.plist
#   rm ~/Library/LaunchAgents/com.rayviewslab.daily.plist

set -euo pipefail

PLIST_SRC="$(cd "$(dirname "$0")" && pwd)/rayviews-daily.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.rayviewslab.daily.plist"
LOG_DIR="$HOME/Library/Logs/rayviewslab"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Unload if already loaded
if launchctl list | grep -q com.rayviewslab.daily 2>/dev/null; then
    echo "Unloading existing job..."
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
fi

# Copy plist
cp "$PLIST_SRC" "$PLIST_DEST"
echo "Copied plist to $PLIST_DEST"

# Load
launchctl load "$PLIST_DEST"
echo "Loaded com.rayviewslab.daily"

# Verify
if launchctl list | grep -q com.rayviewslab.daily; then
    echo "OK: Job is registered. Next run at 06:00 daily."
    echo "Logs: $LOG_DIR/daily.log"
else
    echo "ERROR: Job not found after loading."
    exit 1
fi
