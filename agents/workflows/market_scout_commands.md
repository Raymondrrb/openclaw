# Market Scout Commands

## Run now (manual)

```bash
openclaw agent --agent market_scout --message "Run today's Amazon US market pulse and save report to /Users/ray/Documents/Rayviews/reports/market/TODAY_market_pulse.md with source links and confidence."
```

## Generate seed from local trends

```bash
/usr/bin/python3 "/Users/ray/Documents/Rayviews/tools/market_pulse_from_trends.py" --date "$(date +%F)"
```

## Auto-dispatch to researcher + scriptwriter (threshold-based)

```bash
/usr/bin/python3 "/Users/ray/Documents/Rayviews/tools/market_auto_dispatch.py" --date "$(date +%F)" --notify-agents --max-long-videos-per-day 1
```

- Default threshold: `4.10`
- Default daily long cap: `1`
- Behavior: opens tasks + runs full execution in sequence:
- researcher writes `research.md`
- scriptwriter waits for `research.md` then writes `script_long.md`
- seo waits for `script_long.md` then writes `seo_package.md`
- reviewer waits for `seo_package.md` then writes `review_final.md`
- asset_hunter waits for `review_final.md` and runs only if decision is `GO`, then writes `shot_list.md` and `asset_manifest.md`

## Cron jobs configured

1. Morning pulse:

- ID: `97c0cf8b-2ff4-4468-9468-3bb504d59e2a`
- Name: `Market Scout 09:10 Daily Pulse`
- Schedule: `10 9 * * *` (`America/Sao_Paulo`)

2. Evening delta:

- ID: `10ba2e44-ec16-4d33-a02a-134596920ba7`
- Name: `Market Scout 18:10 Delta Check`
- Schedule: `10 18 * * *` (`America/Sao_Paulo`)

## Useful cron management

```bash
openclaw cron list --json
openclaw cron run 97c0cf8b-2ff4-4468-9468-3bb504d59e2a
openclaw cron disable 10ba2e44-ec16-4d33-a02a-134596920ba7
openclaw cron enable 10ba2e44-ec16-4d33-a02a-134596920ba7
```
