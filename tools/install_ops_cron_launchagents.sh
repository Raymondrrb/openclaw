#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Install macOS LaunchAgents for the n8n-replacement ops scripts:
#   1. daily_go_nogo.py          — 09:05 (America/Sao_Paulo ≈ UTC-3 → 12:05 UTC)
#   2. failure_alert.py          — every 10 minutes
#   3. daily_executive_summary.py — 21:30 (America/Sao_Paulo ≈ UTC-3 → 00:30 UTC+1)
#
# Usage:
#   bash tools/install_ops_cron_launchagents.sh --env-file ~/.config/newproject/ops.env
#
# Required env vars in the env file:
#   CONTROL_PLANE_URL, OPS_READ_SECRET, OPS_GATE_SECRET, OPS_GO_SECRET,
#   TELEGRAM_CHAT_ID
#
# Optional:
#   OPENCLAW_TELEGRAM_ACCOUNT (default: tg_main)
# ---------------------------------------------------------------------------

BASE_DIR="${PROJECT_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="${BASE_DIR}/tmp"

ENV_FILE=""
FAILURE_INTERVAL=600  # 10 minutes

usage() {
  echo "Usage: $0 --env-file <path> [--failure-interval <seconds>]" >&2
  echo "" >&2
  echo "Options:" >&2
  echo "  --env-file <path>           Path to env file with secrets (required)" >&2
  echo "  --failure-interval <secs>   Polling interval for failure alerts (default: 600)" >&2
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file) ENV_FILE="$2"; shift 2;;
    --failure-interval) FAILURE_INTERVAL="$2"; shift 2;;
    -h|--help) usage;;
    *) echo "Unknown argument: $1" >&2; usage;;
  esac
done

[[ -n "$ENV_FILE" ]] || { echo "ERROR: --env-file is required" >&2; usage; }
[[ -f "$ENV_FILE" ]] || { echo "ERROR: env file not found: $ENV_FILE" >&2; exit 2; }

# Verify scripts exist
for script in daily_go_nogo.py failure_alert.py daily_executive_summary.py; do
  [[ -f "${BASE_DIR}/tools/${script}" ]] || {
    echo "ERROR: script not found: ${BASE_DIR}/tools/${script}" >&2
    exit 2
  }
done

mkdir -p "$LAUNCH_DIR" "$LOG_DIR"

# ---------------------------------------------------------------------------
# Helper: install one LaunchAgent
# ---------------------------------------------------------------------------
install_agent() {
  local label="$1"
  local script="$2"
  local plist="${LAUNCH_DIR}/${label}.plist"
  local out_log="${LOG_DIR}/${script%.py}.out.log"
  local err_log="${LOG_DIR}/${script%.py}.err.log"
  local plist_body="$3"

  /bin/cat > "$plist" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>set -a; source ${ENV_FILE}; set +a; /usr/bin/python3 "${BASE_DIR}/tools/${script}"</string>
  </array>
${plist_body}
  <key>StandardOutPath</key>
  <string>${out_log}</string>
  <key>StandardErrorPath</key>
  <string>${err_log}</string>
  <key>ProcessType</key>
  <string>Background</string>
  <key>LimitLoadToSessionType</key>
  <array>
    <string>Aqua</string>
  </array>
</dict>
</plist>
PLISTEOF

  launchctl bootout "gui/$(id -u)/${label}" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$plist"
  launchctl enable "gui/$(id -u)/${label}"

  echo "  Installed: ${label}"
  echo "    Plist:   ${plist}"
  echo "    Stdout:  ${out_log}"
  echo "    Stderr:  ${err_log}"
}

echo "Installing ops LaunchAgents..."
echo ""

# ---------------------------------------------------------------------------
# 1. Daily GO/NO-GO — 09:05 Sao Paulo (12:05 UTC)
# ---------------------------------------------------------------------------
install_agent "ai.newproject.daily-go-nogo" "daily_go_nogo.py" "$(cat <<'INNER'
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>12</integer>
    <key>Minute</key>
    <integer>5</integer>
  </dict>
  <key>RunAtLoad</key>
  <false/>
INNER
)"

echo ""

# ---------------------------------------------------------------------------
# 2. Failure alert — every N seconds (default 600 = 10 min)
# ---------------------------------------------------------------------------
install_agent "ai.newproject.failure-alert" "failure_alert.py" "$(cat <<INNER
  <key>StartInterval</key>
  <integer>${FAILURE_INTERVAL}</integer>
  <key>RunAtLoad</key>
  <true/>
INNER
)"

echo ""

# ---------------------------------------------------------------------------
# 3. Executive summary — 21:30 Sao Paulo (00:30 UTC next day)
# ---------------------------------------------------------------------------
install_agent "ai.newproject.daily-executive-summary" "daily_executive_summary.py" "$(cat <<'INNER'
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>0</integer>
    <key>Minute</key>
    <integer>30</integer>
  </dict>
  <key>RunAtLoad</key>
  <false/>
INNER
)"

echo ""
echo "All 3 LaunchAgents installed."
echo ""
echo "To check status:"
echo "  launchctl list | grep ai.newproject"
echo ""
echo "To uninstall all:"
echo "  for l in daily-go-nogo failure-alert daily-executive-summary; do"
echo "    launchctl bootout \"gui/\$(id -u)/ai.newproject.\$l\" 2>/dev/null"
echo "    rm -f \"$LAUNCH_DIR/ai.newproject.\$l.plist\""
echo "  done"
echo ""
echo "Env file: $ENV_FILE"
echo "Logs: $LOG_DIR/"
