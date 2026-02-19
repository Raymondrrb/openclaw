# GitHub-Driven Setup Optimizations (2026-02-09)

Goal: optimize Ray's current stack for one long video/day using OpenClaw + Dzine + ElevenLabs + DaVinci Studio.

## Sources (GitHub)

- https://github.com/openclaw/openclaw
- https://github.com/samuelgursky/davinci-resolve-mcp
- https://github.com/apvlv/davinci-resolve-mcp
- https://github.com/nobphotographr/davinci-resolve-automation

## What Was Applied

1. Browser session stability (OpenClaw)

- Use OpenClaw managed logged sessions for strict sites (Dzine/Amazon/YouTube).
- Keep one persistent authenticated session to reduce repeated login/captcha.
- Avoid relay dependency for normal automation flow.

2. Context overflow reduction (OpenClaw)

- Enabled context pruning with TTL strategy in agent defaults.
- Purpose: reduce long tool-output accumulation and avoid context-window failures.

3. DaVinci MCP risk reduction

- Updated safe profile with strict Tier A/Tier B tool policy.
- Blocked high-risk commands (cloud mutation, app shutdown/restart, raw code execution) for autonomous mode.
- Added hard requirement: Studio scripting preflight must pass before automation.

4. Pipeline reliability in dispatcher

- Added ElevenLabs generation gate before Dzine/DaVinci steps.
- Added DaVinci smoke preflight gate before `davinci_editor`.
- If voiceover or preflight fails, downstream publish chain is skipped with explicit reason.

5. Generalized ElevenLabs script chunking

- Voiceover generator no longer depends on one fixed Top-5 script structure.
- Works with generic section headings for Top 3/Top 5 scripts across niches.

## Operational Rules for This Stack

1. Run one long-video chain/day (`--max-long-videos-per-day 1`).
2. Keep publishing manual approval only.
3. For Dzine and Amazon links, maintain active logged browser session.
4. Promote any new DaVinci MCP tool only after repeated pass rate in real episodes.

## Quick Command

```bash
python3 "/Users/ray/Documents/Rayviews/tools/market_auto_dispatch.py" \
  --date TODAY \
  --notify-agents \
  --wait-seconds 420 \
  --max-long-videos-per-day 1 \
  --voice-name "Thomas Louis"
```
