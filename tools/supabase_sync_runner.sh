#!/bin/zsh
set -euo pipefail

BASE_DIR="${PROJECT_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
SYNC_PY="${BASE_DIR}/tools/supabase_sync_ops.py"
DEFAULT_ENV_FILE="$HOME/.config/newproject/supabase.env"

ENV_FILE="$DEFAULT_ENV_FILE"

if [[ "${1:-}" == "--env-file" ]]; then
  if [[ -z "${2:-}" ]]; then
    echo "Missing value for --env-file"
    exit 2
  fi
  ENV_FILE="$2"
  shift 2
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Env file not found: $ENV_FILE"
  echo "Create it with:"
  echo "  SUPABASE_URL=..."
  echo "  SUPABASE_SERVICE_ROLE_KEY=...   # sb_secret_... or service_role key"
  echo "  SUPABASE_SCHEMA=public"
  exit 2
fi

set -a
source "$ENV_FILE"
set +a

python3 "$SYNC_PY" "$@"
