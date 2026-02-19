#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/ray/Documents/openclaw"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$SCRIPT_DIR/rayviews_lock.sh" -- true

echo "pwd: $(pwd)"
echo "branch: $(git branch --show-current)"
echo "remotes:"
git remote -v | sed -n '1,12p'

if ! git remote | grep -q '^rayviewslab$'; then
  echo "ERROR: remote 'rayviewslab' not configured" >&2
  exit 3
fi

echo "Fetching rayviewslab..."
git fetch rayviewslab --quiet || true

echo "Preflight OK."
