#!/usr/bin/env bash
set -euo pipefail

CANONICAL_ROOT="/Users/ray/Documents/openclaw"
CANONICAL_REMOTE="rayviewslab"

usage() {
  cat <<USAGE
Usage: $(basename "$0") [--] [command ...]

Hard guard for RayViews work. It aborts unless all checks pass:
- running inside /Users/ray/Documents/openclaw
- git toplevel is /Users/ray/Documents/openclaw
- remote 'rayviewslab' exists

If a command is provided after '--', it executes only when checks pass.
Examples:
  $(basename "$0")
  $(basename "$0") -- git status --short
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ ! -d "$CANONICAL_ROOT/.git" ]]; then
  echo "LOCK_FAIL: canonical repo missing at $CANONICAL_ROOT" >&2
  exit 10
fi

CUR_PWD="$(pwd)"
if [[ "$CUR_PWD" != "$CANONICAL_ROOT"* ]]; then
  echo "LOCK_FAIL: wrong working directory: $CUR_PWD" >&2
  echo "Expected under: $CANONICAL_ROOT" >&2
  exit 11
fi

TOP="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ "$TOP" != "$CANONICAL_ROOT" ]]; then
  echo "LOCK_FAIL: wrong git root: ${TOP:-<none>}" >&2
  echo "Expected: $CANONICAL_ROOT" >&2
  exit 12
fi

if ! git remote | grep -q "^${CANONICAL_REMOTE}$"; then
  echo "LOCK_FAIL: missing remote '$CANONICAL_REMOTE'" >&2
  exit 13
fi

BRANCH="$(git branch --show-current 2>/dev/null || true)"
if [[ -z "$BRANCH" ]]; then
  echo "LOCK_FAIL: detached HEAD is not allowed for normal work" >&2
  exit 14
fi

echo "LOCK_OK root=$TOP branch=$BRANCH remote=$CANONICAL_REMOTE"

if [[ "${1:-}" == "--" ]]; then
  shift
fi

if [[ $# -gt 0 ]]; then
  exec "$@"
fi
