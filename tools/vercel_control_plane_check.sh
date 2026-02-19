#!/bin/zsh
set -euo pipefail

BASE_URL="${1:-https://new-project-control-plane.vercel.app}"
ENV_FILE="${2:-$HOME/.config/newproject/vercel_control_plane.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE" >&2
  exit 1
fi

source "$ENV_FILE"

CRON="${CRON_SECRET:-${OPS_CRON_SECRET:-}}"
if [[ -z "${CRON:-}" || -z "${OPS_READ_SECRET:-}" ]]; then
  echo "Missing CRON_SECRET (or OPS_CRON_SECRET) or OPS_READ_SECRET in $ENV_FILE" >&2
  exit 1
fi

echo "Base URL: $BASE_URL"
echo "--- health"
curl -s "${BASE_URL%/}/api/health"
echo
echo "--- heartbeat"
curl -s -H "Authorization: Bearer $CRON" "${BASE_URL%/}/api/ops/heartbeat"
echo
echo "--- summary"
curl -s -H "Authorization: Bearer $OPS_READ_SECRET" "${BASE_URL%/}/api/ops/summary"
echo
