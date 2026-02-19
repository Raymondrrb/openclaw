#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="${PROJECT_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"

usage() {
  echo "Usage: $0 --env-file <path> [--interval-seconds <n>] [--worker-id <id>]" >&2
  exit 2
}

ENV_FILE=""
INTERVAL_SECONDS="120"
WORKER_ID="mac-local-1"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file) ENV_FILE="$2"; shift 2;;
    --interval-seconds) INTERVAL_SECONDS="$2"; shift 2;;
    --worker-id) WORKER_ID="$2"; shift 2;;
    *) usage;;
  esac
done

[[ -n "$ENV_FILE" ]] || usage
[[ -f "$ENV_FILE" ]] || { echo "env file not found: $ENV_FILE" >&2; exit 2; }

PLIST="$HOME/Library/LaunchAgents/ai.newproject.ops-video-runs-worker.plist"
OUT_LOG="${BASE_DIR}/tmp/ops_video_runs_worker.out.log"
ERR_LOG="${BASE_DIR}/tmp/ops_video_runs_worker.err.log"

mkdir -p "${BASE_DIR}/tmp"

/bin/cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>ai.newproject.ops-video-runs-worker</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>set -a; source ${ENV_FILE}; set +a; /usr/bin/python3 "${BASE_DIR}/tools/ops_video_runs_worker.py" --worker-id "${WORKER_ID}"</string>
  </array>
  <key>StartInterval</key>
  <integer>${INTERVAL_SECONDS}</integer>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${OUT_LOG}</string>
  <key>StandardErrorPath</key>
  <string>${ERR_LOG}</string>
  <key>ProcessType</key>
  <string>Background</string>
  <key>LimitLoadToSessionType</key>
  <array>
    <string>Aqua</string>
  </array>
</dict>
</plist>
EOF

launchctl unload "$PLIST" >/dev/null 2>&1 || true
launchctl load "$PLIST"
launchctl start "ai.newproject.ops-video-runs-worker" || true

echo "Installed and started: ai.newproject.ops-video-runs-worker"
echo "Plist: $PLIST"
echo "Out log: $OUT_LOG"
echo "Err log: $ERR_LOG"
