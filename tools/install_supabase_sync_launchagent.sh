#!/bin/zsh
set -euo pipefail

LABEL="ai.newproject.supabase-sync"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
BASE_DIR="${PROJECT_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
RUNNER="${BASE_DIR}/tools/supabase_sync_runner.sh"
SYNC_PY="${BASE_DIR}/tools/supabase_sync_ops.py"
STATE_DIR="$HOME/.config/newproject"
SYNC_PY_LOCAL="${STATE_DIR}/supabase_sync_ops.py"
OPS_DIR="${STATE_DIR}/ops"
LEGACY_OPS_DIR="${BASE_DIR}/ops"
DEFAULT_ENV_FILE="$HOME/.config/newproject/supabase.env"
ENV_FILE="$DEFAULT_ENV_FILE"
INTERVAL=600

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      ENV_FILE="$2"
      shift 2
      ;;
    --interval-seconds)
      INTERVAL="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1"
      exit 2
      ;;
  esac
done

if [[ ! -x "$RUNNER" ]]; then
  echo "Runner not executable: $RUNNER"
  exit 2
fi

if [[ ! -f "$SYNC_PY" ]]; then
  echo "Sync script missing: $SYNC_PY"
  exit 2
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Env file missing: $ENV_FILE"
  echo "Create it first, then rerun this installer."
  exit 2
fi

mkdir -p "$HOME/Library/LaunchAgents"
mkdir -p "${BASE_DIR}/tmp"
mkdir -p "${STATE_DIR}"
mkdir -p "${OPS_DIR}"

cp "$SYNC_PY" "$SYNC_PY_LOCAL"
chmod 700 "$SYNC_PY_LOCAL"

for f in policies.json proposals.json missions.json events.jsonl reactions.json; do
  if [[ -f "${LEGACY_OPS_DIR}/${f}" && ! -f "${OPS_DIR}/${f}" ]]; then
    cp "${LEGACY_OPS_DIR}/${f}" "${OPS_DIR}/${f}"
  fi
done

RUNNER_Q=$(printf '%q' "$RUNNER")
SYNC_PY_Q=$(printf '%q' "$SYNC_PY_LOCAL")
ENV_FILE_Q=$(printf '%q' "$ENV_FILE")
OPS_DIR_Q=$(printf '%q' "$OPS_DIR")
RUN_CMD="set -a; source ${ENV_FILE_Q}; set +a; /usr/bin/python3 ${SYNC_PY_Q} --ops-dir ${OPS_DIR_Q}"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>${RUN_CMD}</string>
  </array>

  <key>RunAtLoad</key>
  <true/>

  <key>StartInterval</key>
  <integer>${INTERVAL}</integer>

  <key>StandardOutPath</key>
  <string>${BASE_DIR}/tmp/supabase_sync.out.log</string>

  <key>StandardErrorPath</key>
  <string>${BASE_DIR}/tmp/supabase_sync.err.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/${LABEL}"
launchctl kickstart -k "gui/$(id -u)/${LABEL}"

echo "Installed and started: ${LABEL}"
echo "Plist: ${PLIST}"
echo "Out log: ${BASE_DIR}/tmp/supabase_sync.out.log"
echo "Err log: ${BASE_DIR}/tmp/supabase_sync.err.log"
