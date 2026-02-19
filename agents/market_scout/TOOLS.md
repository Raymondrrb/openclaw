# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: <ssh_user>

### TTS

- Preferred voice: "Thomas Louis" (YouTube narration default, consistent brand voice)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.

## Runtime Commands (Market Scout)

```bash
python3 scripts/injection_guard.py --source "web" --input-file /tmp/external.txt --json
python3 scripts/ops_tier.py --daily-budget-usd 30 --spent-usd 9.8 --consecutive-failures 1 --worker-healthy 1 --json
python3 scripts/skill_graph_scan.py --task "affiliate compliance for youtube description" --json
python3 scripts/graph_lint.py --graph-root skill_graph --json
bash scripts/preflight_checks.sh "gate1 review for top5 run" --with-tests
```
