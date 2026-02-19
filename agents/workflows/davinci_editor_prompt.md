# Prompt Template: DaVinci Editor

Use this with OpenClaw:

openclaw agent --agent davinci_editor --message "Read /Users/ray/Documents/Rayviews/agents/workflows/davinci_editor_playbook.md, /Users/ray/Documents/Rayviews/agents/workflows/davinci_mcp_safe_profile.md, /Users/ray/Documents/Rayviews/agents/knowledge/davinci_operator_manual.md and episode files for <slug>. Generate: (1) davinci_edit_plan.md, (2) davinci_timeline_map.md, (3) davinci_export_preset.md, (4) davinci_qc_checklist.md in /Users/ray/Documents/Rayviews/content/<slug>/. If a required action is outside MCP allowlist, mark REVIEW_REQUIRED and stop. Keep output concise and production-ready for DaVinci Resolve."
