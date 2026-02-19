#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/ray/Documents/openclaw"

if [[ "$(pwd)" != "$ROOT"* ]]; then
  echo "ERROR: wrong workspace. Use: $ROOT" >&2
  exit 2
fi

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
