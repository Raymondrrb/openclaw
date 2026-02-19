#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-$HOME/.config/newproject/supabase.env}"
WORKER_ID="${WORKER_ID:-mac-terminal-1}"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-60}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "env file not found: $ENV_FILE" >&2
  exit 2
fi

set -a
source "$ENV_FILE"
set +a

echo "[worker] starting (worker_id=$WORKER_ID interval=${INTERVAL_SECONDS}s env=$ENV_FILE)"
while true; do
  BASE_DIR="${PROJECT_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
  /usr/bin/python3 "${BASE_DIR}/tools/ops_video_runs_worker.py" \
    --worker-id "$WORKER_ID" \
    --limit 25 \
    --timeout-sec 900 || true
  sleep "$INTERVAL_SECONDS"
done

