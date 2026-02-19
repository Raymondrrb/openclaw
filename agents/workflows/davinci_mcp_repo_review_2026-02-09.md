# DaVinci MCP Repo Review (2026-02-09)

## Scope

Useful extraction for OpenClaw-based video editing automation in DaVinci Resolve.

Reviewed repos:

- https://github.com/samuelgursky/davinci-resolve-mcp
- https://github.com/apvlv/davinci-resolve-mcp
- https://github.com/tooflex/davinci-resolve-mcp
- https://github.com/Positronikal/davinci-mcp-professional

## What Is Most Useful

1. `samuelgursky`:

- Broad tool surface (83 MCP tools).
- Good install and verification scripts.
- Practical docs for batch automation and benchmarking.

2. `apvlv`:

- Compact implementation to understand architecture quickly.
- Useful as a minimal reference for Fusion operations.

3. `tooflex`:

- Mid-size tool set with timeline/audio helpers.
- Useful to inspect specific function ideas.

4. `Positronikal`:

- Cleaner server architecture and organized modules.
- Good reference for maintainable code layout.

## Critical Caveats

1. `samuelgursky` feature matrix states many items are implemented but not fully verified on macOS.
2. `apvlv` includes arbitrary code execution tools (`execute_python`, `execute_lua`) which are unsafe for autonomous production.
3. `tooflex` README quality is inconsistent; validate behavior by source/tests, not README claims.
4. `Positronikal` currently exposes a smaller tool set (about 13 core tools), so use it for architecture ideas, not full automation coverage.

## Practical Recommendation for Ray's Stack

1. Use `samuelgursky` as primary MCP base.
2. Enforce strict allowlist and denylist (see `davinci_mcp_safe_profile.md`).
3. Run one long-video pipeline first; no autopublish.
4. Keep cloud/account-changing tools manual-only.
5. Add small validation runs before every new feature/tool activation.

## Suggested Adoption Plan

1. Phase 1 (now):

- planning + timeline assembly + export only
- one episode per day

2. Phase 2:

- controlled color/audio automation
- QC auto-rechecks

3. Phase 3:

- optional advanced tools after repeated pass rate

## Pass/Fail Rule

A tool is promoted to production only if:

- passed in at least 5 real episodes
- produced no destructive side effects
- has rollback path documented
