#!/usr/bin/env bash
set -euo pipefail

RAYVIEWS_ROOT="/Users/ray/Documents/Rayviews"
OPENCLAW_ROOT="/Users/ray/Documents/openclaw"
MODE="to-openclaw"
APPLY=0

usage() {
  cat <<USAGE
Usage: $(basename "$0") [--to-openclaw|--to-rayviews] [--apply]

Sync a small controlled set of shared files between the Rayviews and OpenClaw repos.
Default is dry-run.

Examples:
  $(basename "$0") --to-openclaw
  $(basename "$0") --to-openclaw --apply
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --to-openclaw) MODE="to-openclaw" ;;
    --to-rayviews) MODE="to-rayviews" ;;
    --apply) APPLY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

FILES=(
  "tools/chatgpt_ui.py"
  "tests/test_chatgpt_ui.py"
  "tools/openclaw_recover.sh"
)

if [[ "$MODE" == "to-openclaw" ]]; then
  SRC_ROOT="$RAYVIEWS_ROOT"
  DST_ROOT="$OPENCLAW_ROOT"
else
  SRC_ROOT="$OPENCLAW_ROOT"
  DST_ROOT="$RAYVIEWS_ROOT"
fi

echo "mode=$MODE"
echo "source=$SRC_ROOT"
echo "target=$DST_ROOT"
echo "apply=$APPLY"

for rel in "${FILES[@]}"; do
  src="$SRC_ROOT/$rel"
  dst="$DST_ROOT/$rel"

  if [[ ! -f "$src" ]]; then
    echo "[skip] missing source: $rel"
    continue
  fi

  if [[ -f "$dst" ]] && cmp -s "$src" "$dst"; then
    echo "[ok] already synced: $rel"
    continue
  fi

  echo "[diff] $rel"
  if [[ "$APPLY" -eq 1 ]]; then
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
    if [[ "$rel" == *.sh ]]; then chmod +x "$dst"; fi
    echo "      -> copied"
  fi
done

if [[ "$APPLY" -eq 1 ]]; then
  echo "Done. Run validation in target repo."
fi
