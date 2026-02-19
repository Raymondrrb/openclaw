#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
NODES_FILE="${NODES_FILE:-$REPO_ROOT/state/cluster/nodes.json}"

if [[ ! -f "$NODES_FILE" ]]; then
  echo "nodes file not found: $NODES_FILE" >&2
  exit 1
fi

# Rotation-friendly env fallback.
if [[ -z "${RAYVAULT_CLUSTER_SECRET:-}" && -n "${RAYVAULT_CLUSTER_SECRET_CURRENT:-}" ]]; then
  export RAYVAULT_CLUSTER_SECRET="${RAYVAULT_CLUSTER_SECRET_CURRENT}"
fi

if [[ -z "${RAYVAULT_CLUSTER_SECRET:-}" ]]; then
  echo "RAYVAULT_CLUSTER_SECRET is not set (or define RAYVAULT_CLUSTER_SECRET_CURRENT)" >&2
  exit 1
fi

cd "$REPO_ROOT"
if [[ "$#" -eq 0 ]]; then
  set -- health
fi
python3 -m rayvault.agent.controller --nodes-file "$NODES_FILE" "$@"
