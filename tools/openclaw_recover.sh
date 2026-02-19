#!/usr/bin/env bash
set -euo pipefail

MAX_PROC="${RAYVIEWS_OPENCLAW_MAX_PROCS:-40}"
APPLY=0
RESTART_BROWSER=0
FORCE=0

usage() {
  cat <<USAGE
Usage: $(basename "$0") [--apply] [--restart-browser] [--force] [--max N]

Detects abnormal OpenClaw process storms and optionally recovers by killing
orphaned OpenClaw processes (PPID=1).

Options:
  --apply            Apply recovery actions (default: report only)
  --restart-browser  Run 'openclaw browser stop/start' after cleanup
  --force            Apply cleanup even when process count <= max
  --max N            Process threshold before cleanup (default: ${MAX_PROC})
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --restart-browser) RESTART_BROWSER=1 ;;
    --force) FORCE=1 ;;
    --max)
      shift
      MAX_PROC="${1:-}"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 2
      ;;
  esac
  shift
done

if ! [[ "$MAX_PROC" =~ ^[0-9]+$ ]]; then
  echo "Invalid --max value: $MAX_PROC" >&2
  exit 2
fi

PROC_LINES="$(ps -axo pid=,ppid=,state=,etime=,command= | awk '
  /openclaw(-channels)?([[:space:]]|$)/ && $0 !~ /openclaw_recover\.sh/ {
    print
  }
')"

COUNT=0
if [[ -n "$PROC_LINES" ]]; then
  COUNT="$(printf '%s\n' "$PROC_LINES" | wc -l | tr -d ' ')"
fi

echo "openclaw_process_count=${COUNT} threshold=${MAX_PROC}"

if [[ -n "$PROC_LINES" ]]; then
  echo "--- openclaw processes ---"
  printf '%s\n' "$PROC_LINES"
fi

ORPHAN_PIDS=""
if [[ -n "$PROC_LINES" ]]; then
  ORPHAN_PIDS="$(printf '%s\n' "$PROC_LINES" | awk '$2 == 1 {print $1}' | xargs)"
fi

if [[ -n "$ORPHAN_PIDS" ]]; then
  echo "orphan_pids=${ORPHAN_PIDS}"
else
  echo "orphan_pids=<none>"
fi

if [[ "$APPLY" -ne 1 ]]; then
  echo "dry_run=1 (re-run with --apply to recover)"
  exit 0
fi

if [[ "$FORCE" -ne 1 && "$COUNT" -le "$MAX_PROC" ]]; then
  echo "No cleanup needed (count <= threshold)."
  exit 0
fi

if [[ -z "$ORPHAN_PIDS" ]]; then
  echo "No orphan OpenClaw processes found; skipping kill step."
else
  echo "Killing orphan OpenClaw processes (SIGTERM)..."
  kill ${ORPHAN_PIDS} || true
  sleep 1

  STILL="$(ps -o pid= -p ${ORPHAN_PIDS} 2>/dev/null | xargs || true)"
  if [[ -n "$STILL" ]]; then
    echo "Escalating to SIGKILL for: ${STILL}"
    kill -9 ${STILL} || true
  fi
fi

if [[ "$RESTART_BROWSER" -eq 1 ]]; then
  if command -v openclaw >/dev/null 2>&1; then
    echo "Restarting OpenClaw browser service..."
    openclaw browser stop --json >/dev/null 2>&1 || true
    openclaw browser start --json >/dev/null 2>&1 || true
    openclaw browser status --json || true
  else
    echo "openclaw binary not found; skipped browser restart." >&2
  fi
fi

echo "Recovery completed."
