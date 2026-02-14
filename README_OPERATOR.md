# RayVault Operator Manual

Daily operations guide for the RayviewsLab pipeline.

## 1. Worker States

| State | Meaning | Action |
|-------|---------|--------|
| `active` | Processing normally | None |
| `waiting` | Gate active (awaiting human approval) | Check Telegram / dashboard |
| `panic` | Worker stopped for safety | Investigate before resuming |
| `idle` | No active processing | Normal between runs |

## 2. Panic Taxonomy

| Panic | Cause | Action |
|-------|-------|--------|
| `panic_lost_lock` | Another worker claimed the run, or lease expired | Check for duplicate workers / short lease |
| `panic_heartbeat_uncertain` | Network/Supabase unreachable after 3 retries | Check Wi-Fi/router; look at `last_heartbeat_latency_ms`; wait 2-5 min |
| `panic_browser_frozen` | Playwright/Dzine not responding | Restart browser; check RAM/GPU; resume via `claim_next` |
| `panic_integrity_failure` | Irreconcilable evidence conflict | Open dashboard and decide (approve/refetch/abort) |

## 3. Morning Routine (2 minutes)

```bash
# 1. Health check
rayvault doctor --health

# 2. Replay any spooled events from previous panics
rayvault replay-spool
```

**Reading doctor output:**

- `[PASS|PASS|PASS]` — all clear, let it run
- `INGESTION_STALLED` — check scraper crons/logs before generating more runs
- `STALE_GATE` — open dashboard, decide pending approvals (refetch/abort)
- `NICHO_VOLUME` — low data but ingestion alive, no action needed

## 4. Telegram Alerts

### Gate Active (waiting_approval)

Buttons on the message:

| Button | Effect |
|--------|--------|
| **Approve** | Sets status=`approved`, worker resumes pipeline |
| **Refetch** | Sets status=`running` + `force_refetch:true` in event, worker re-collects evidence |
| **Abort** | Sets status=`aborted`, run is killed |
| **Unlock** | Force-clears lock via `rpc_force_unlock_run` |

### Panic Alert

- `panic_heartbeat_uncertain` — wait 2-5 min, run `doctor --health`
- `panic_lost_lock` — do NOT retry; check if another worker is active
- `panic_browser_frozen` — restart Playwright/Dzine, worker auto-resumes via `claim_next` recovery

## 5. Emergency: Force Unlock

Use **only** when:
- Run is stuck with expired or active lease and worker is dead
- Worker crashed and won't restart

```bash
rayvault unlock --run <uuid> --force --reason "worker crashed during Dzine render"
```

**Rules:**
- Never unlock `done`/`failed`/`aborted` runs (the RPC blocks this without `--force`)
- The unlock writes a forensic event to `run_events` with full prev snapshot
- Dashboard shows the reason in `worker_last_error`

## 6. Checkpoint Recovery

If the worker restarts:
1. `claim_next` automatically recovers the worker's own active run (Phase 1 recovery)
2. Checkpoint file (`checkpoints/<run_id>.json`) tells it which stages are already done
3. Worker skips completed stages and resumes from where it stopped

If checkpoint file is lost:
- `claim_next` still recovers the run (from DB state)
- Worker re-runs all stages (idempotent — stages check for existing artifacts)

## 7. Critical Rule

If there's a conflict between Tier 4/5 sources on **critical claims** (price, voltage, compatibility, model_id/ean):

> The system MUST gate (pause) before publishing anything.

This is enforced by the circuit breaker. Never override without reading the evidence diff in the dashboard.

## 8. Common Commands

```bash
# Start worker (continuous)
python3 tools/worker.py --worker-id Mac-Ray-01

# Single run mode
python3 tools/worker.py --worker-id Mac-Ray-01 --once

# Health check
rayvault doctor --health

# Replay spooled events
python3 tools/worker.py --replay-spool

# Force unlock
python3 tools/rayvault_unlock.py --run <uuid> --operator ray --force --reason "stuck"
```
