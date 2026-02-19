#!/bin/bash
# Set up QMD (tobi/qmd) collections for Rayviews.
# Requires: bun (https://bun.sh)
# Run once after installing bun: bash scripts/setup_qmd.sh

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Fail closed: do not auto-install executables from remote sources.
if ! command -v qmd &>/dev/null; then
  cat <<'EOF'
ERROR: qmd is not installed.

For security, this script does not auto-install qmd from a remote URL.
Install qmd manually from a trusted source, then rerun this script.
EOF
  exit 1
fi

echo "Setting up QMD collections for Rayviews..."

# Reports: daily market pulses, trend data, category selections
qmd collection add "$PROJECT_ROOT/reports/market" --name market-reports --mask "**/*.md"
qmd collection add "$PROJECT_ROOT/reports/trends" --name trend-data --mask "**/*.json"

# Agent knowledge base and workflows
qmd collection add "$PROJECT_ROOT/agents/knowledge" --name agent-knowledge --mask "**/*.md"
qmd collection add "$PROJECT_ROOT/agents/workflows" --name workflows --mask "**/*.md"

# Config docs (for reference)
qmd collection add "$PROJECT_ROOT/config" --name config --mask "**/*.json"

# Add context to help search understand the collections
qmd context add qmd://market-reports "Daily market pulse reports with product opportunities, category rankings, and Amazon US intelligence for review video production"
qmd context add qmd://trend-data "YouTube and Brave Search trend JSON files with views/hour velocity and web mention scores per product category"
qmd context add qmd://agent-knowledge "Operator manuals, competitor patterns, and reference docs for Rayviews pipeline agents"
qmd context add qmd://workflows "Agent playbooks and workflow templates for market scouting, video production, editing, and publishing"
qmd context add qmd://config "Category definitions, trend query configs, and threshold settings"

# Generate embeddings for semantic search
echo "Generating embeddings (first run downloads models ~2GB)..."
qmd embed

echo ""
echo "QMD setup complete. Try:"
echo "  qmd search 'portable monitor trending'"
echo "  qmd query 'which categories had highest velocity this week'"
echo "  qmd search -c market-reports 'robot vacuum'"

qmd status
