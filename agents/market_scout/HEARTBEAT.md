# HEARTBEAT.md - Market Scout Checklist

On wake:

- Read `/Users/ray/Documents/Rayviews/agents/workflows/market_scout_daily.md`.
- Check latest files in `/Users/ray/Documents/Rayviews/reports/trends/`.
- Create today's report in `/Users/ray/Documents/Rayviews/reports/market/`.
- If yesterday report exists, include explicit deltas.
- If no relevant movement found, report `HEARTBEAT_OK` with one-line status.

Daily integrity checks:

- Run `python3 /Users/ray/Documents/Rayviews/agents/market_scout/scripts/graph_lint.py --graph-root /Users/ray/Documents/Rayviews/agents/market_scout/skill_graph`.
- If lint fails, stop workflow edits and surface reason codes.
