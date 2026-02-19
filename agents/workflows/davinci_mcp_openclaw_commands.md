# OpenClaw Commands - DaVinci MCP Daily Run

## 1) Build DaVinci Production Pack (per episode)

```bash
openclaw agent --agent davinci_editor --message "Read /Users/ray/Documents/Rayviews/agents/workflows/davinci_editor_playbook.md, /Users/ray/Documents/Rayviews/agents/workflows/davinci_mcp_safe_profile.md, /Users/ray/Documents/Rayviews/agents/knowledge/davinci_operator_manual.md and episode files in /Users/ray/Documents/Rayviews/content/<slug>/. Generate: (1) davinci_edit_plan.md, (2) davinci_timeline_map.md, (3) davinci_export_preset.md, (4) davinci_qc_checklist.md. If any hard gate fails, output NO-GO with exact blocker." --json
```

## 2) Run DaVinci Study Cycle (optional, improvement loop)

```bash
/Users/ray/Documents/Rayviews/tools/run_davinci_training_cycle.sh https://www.youtube.com/watch?v=MCDVcQIA3UM
```

## 3) Daily Orchestration (market -> content -> editing docs)

```bash
/usr/bin/python3 /Users/ray/Documents/Rayviews/tools/market_auto_dispatch.py --date TODAY --notify-agents --wait-seconds 120
```

## 4) Important Rule

Publishing remains manual approval by Ray.
