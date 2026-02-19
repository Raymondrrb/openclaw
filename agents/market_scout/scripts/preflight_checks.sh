#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TASK_DESC="${1:-gate1 review package quality and compliance}"
WITH_TESTS="${2:-}"

python3 "$ROOT_DIR/scripts/graph_lint.py" --graph-root "$ROOT_DIR/skill_graph"
python3 "$ROOT_DIR/scripts/skill_graph_scan.py" --graph-root "$ROOT_DIR/skill_graph" --task "$TASK_DESC" --top 6 >/dev/null

if [[ "$WITH_TESTS" == "--with-tests" ]]; then
  bash "$ROOT_DIR/scripts/run_tests.sh"
fi

echo "PREFLIGHT_OK: skill graph lint + discovery checks passed"
