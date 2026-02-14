# Run Manager Integration Guide

Production-grade pipeline infrastructure: state machine, circuit breaker, Telegram approval gate, forensic snapshots.

## Architecture

```
Evidence Collection
        │
        ▼
┌─────────────────┐
│ Circuit Breaker  │──── Tier B alert (log only) ──→ continue
│ (tier-based)     │
└────────┬────────┘
         │ Tier A weak?
         ▼
    ┌────────────┐     auto-refetch     ┌──────────────┐
    │ Auto-refetch│──── healed? yes ──→ │   continue    │
    │ (once only) │                     └──────────────┘
    └────────┬───┘
             │ still weak
             ▼
    ┌────────────────┐
    │ waiting_approval│──→ Telegram Gate
    └────────┬───────┘     (Refetch / Ignore / Abort)
             │
             ▼
    ┌────────────────┐
    │  CAS Update     │──→ approved / aborted
    │  (atomic+idem)  │
    └────────────────┘
```

## Files

| Module | Purpose |
|--------|---------|
| `tools/lib/circuit_breaker.py` | Evidence scoring + gate decision (tier-based) |
| `tools/lib/run_manager.py` | State machine + cost controls + CB integration |
| `tools/lib/telegram_gate.py` | Atomic, idempotent Telegram button handler |
| `tools/lib/context_builder.py` | Filesystem-first context pack selection |
| `supabase/sql/007_run_manager_schema.sql` | DB schema (runs, run_events, evidence_items, fingerprints) |
| `tools/test_run_manager.py` | 65 unit tests covering all modules |

## Quick Start

### 1. Apply SQL Migration

Run `supabase/sql/007_run_manager_schema.sql` in Supabase SQL Editor. This:
- Extends `pipeline_runs` with `approval_nonce`, `context_snapshot`, `policy_version`, `ranking_model`
- Creates `run_events` with `UNIQUE(run_id, action_id)` for idempotency
- Creates `evidence_items` for scored evidence storage
- Creates `product_fingerprints` for SKU consistency tracking
- Creates `cas_run_status()` PL/pgSQL function for atomic transitions

### 2. Basic Run Lifecycle

```python
from tools.lib.run_manager import RunManager

# Create manager (use_supabase=True for production)
rm = RunManager(run_id="your-uuid", policy_version="v1.0")

# Start run
rm.start(context_pack={"notes": ["sop_research"]})

# Before ANY expensive operation:
if not rm.check_status():
    return  # blocked (waiting_approval, done, etc.)

# ... do expensive work ...

# Complete
rm.complete(final_evidence={"products": 5})
```

### 3. Wire Circuit Breaker

```python
from tools.lib.circuit_breaker import evaluate_evidence

# Collect evidence from research
evidence = [
    {"claim_type": "price", "confidence": 0.95, "fetched_at": "2026-02-13T...",
     "trust_tier": 4, "value": 29.99, "source_name": "Amazon"},
    {"claim_type": "voltage", "confidence": 0.9, "fetched_at": "2026-02-13T...",
     "trust_tier": 5, "value": "127V", "source_name": "Official"},
    # ... more evidence
]

# Evaluate with refetch capability
def refetch_evidence():
    """Re-fetch stale evidence and return new list."""
    # Your fetch logic here
    return new_evidence

result = rm.evaluate_and_gate(
    evidence,
    refetch_fn=refetch_evidence,
    notify_fn=lambda run_id, nonce, reason: send_gate_message(
        run_id, nonce, reason, video_id="20260213"
    ),
)

if result.should_gate:
    # Run is now waiting_approval — Telegram message sent
    return
```

### 4. Handle Telegram Callbacks

```python
from tools.lib.telegram_gate import handle_gate_callback

# In your webhook/polling handler:
callback_data = update.callback_query.data  # e.g. "ignore:run-id:nonce:action-id"

result = handle_gate_callback(
    callback_data,
    run_manager,
    refetch_fn=refetch_evidence,  # only needed for "refetch" button
)

if result["ok"]:
    print(f"Action {result['action']}: {result['message']}")
```

### 5. SKU Fingerprint Tracking

```python
from tools.lib.circuit_breaker import compute_fingerprint, needs_refresh

# Compute fingerprint for a product
fp = compute_fingerprint(
    "B0TEST1",
    brand="Sony",
    model_number="WF-1000XM5",
    ean_upc="4548736130654",
    variant_attrs={"color": "black"},
)

# Check if fingerprint changed (compare with stored)
old_fp = "abc123..."  # from product_fingerprints table
fingerprint_changed = fp != old_fp

# Check if claim needs refresh
if needs_refresh("core_specs", fingerprint_changed=fingerprint_changed):
    # Re-fetch specs evidence
    pass
```

### 6. Conflict Detection

```python
from tools.lib.circuit_breaker import detect_conflicts

conflicts = detect_conflicts(evidence, min_trust_tier=4)
for c in conflicts:
    if c["severity"] == "critical":
        # e.g. voltage: Official says 127V, Marketplace says 220V
        # This should ALWAYS gate, even if scores are high
        rm._log_event("conflict_detected", c)
```

## Claim Tiers

| Tier | Claims | Behavior | TTL |
|------|--------|----------|-----|
| **A (Critical)** | price, voltage, compatibility, core_specs | Gates run if weak | 12h-120d |
| **B (Important)** | availability, shipping, promo_badge, review_sentiment | Alert only | 6h-30d |
| **C (Informative)** | material, color, box_contents, warranty | Ignored | 180d-365d |

## Context Snapshots

Every run writes a forensic `context_snapshot` (JSONB) with phase markers:

```json
{
    "phase": "approved",
    "policy_version": "v1.0",
    "ranking_model": "haiku-4.5",
    "started_at": "2026-02-13T14:00:00Z",
    "context_pack": {"notes": ["sop_research", "skill_pricing"]},
    "cb_result": {"should_gate": false, "threshold": 0.6, "scores": [...]},
    "updated_at": "2026-02-13T14:05:00Z"
}
```

Phase progression: `started → paused → refetch → approved → final`

## Safety Guarantees

1. **Every expensive step checks status** — `rm.check_status()` returns False if blocked
2. **CAS updates** — Telegram buttons use `WHERE status='waiting_approval' AND approval_nonce=?`
3. **Idempotent events** — `UNIQUE(run_id, action_id)` prevents double-click duplication
4. **Auto-refetch limit** — max 1 silent refetch, then mandatory human gate
5. **SKU fingerprint** — model/variant change invalidates specs evidence regardless of TTL
6. **Conflict detection** — high-trust sources disagreeing triggers gate

## Forensic Hardening (008)

After running `007_run_manager_schema.sql`, apply `008_forensic_hardening.sql` for production hardening:

| Fix | Why |
|-----|-----|
| `UNIQUE(run_id, evidence_id)` | Prevents duplicate evidence per run (inflated scores, misleading stats) |
| `ON DELETE RESTRICT` on `evidence_id` FK | Prevents deleting evidence that sustained a published video |
| `WITH CHECK(false)` on all RLS policies | Blocks both reads AND writes for anon/authenticated |
| `pg_trigger` check for triggers | No error-swallowing `EXCEPTION WHEN OTHERS` |
| `idx_evidence_tier4plus` partial index | Fast Tier 4/5 conflict detection queries |

### Evidence Cleanup (RESTRICT implications)

With `ON DELETE RESTRICT`, you **cannot** delete evidence that was used in any run. This is intentional — forensic trail.

**Safe cleanup** (only deletes unreferenced expired evidence):

```sql
-- Preview first:
SELECT e.id, e.asin, e.claim_type, e.expires_at
FROM public.evidence_items e
WHERE e.expires_at < now()
  AND NOT EXISTS (
      SELECT 1 FROM public.run_evidence re WHERE re.evidence_id = e.id
  );

-- Then delete:
DELETE FROM public.evidence_items e
WHERE e.expires_at < now()
  AND NOT EXISTS (
      SELECT 1 FROM public.run_evidence re WHERE re.evidence_id = e.id
  );
```

**Alternative**: soft-archive instead of deleting:
```sql
UPDATE evidence_items SET source_type = 'archived'
WHERE expires_at < now();
```

### Health Check

```bash
# Full check (all sections)
python3 tools/rayvault_doctor.py

# Surgical modes
python3 tools/rayvault_doctor.py --quick            # forensics + indexes only
python3 tools/rayvault_doctor.py --security          # RLS lockdown probes only
python3 tools/rayvault_doctor.py --health            # data health only
python3 tools/rayvault_doctor.py --health --days 14  # custom window

# Machine-readable
python3 tools/rayvault_doctor.py --json
```

**Required env vars:**
- `DATABASE_URL` or `SUPABASE_DB_URL` — admin DB for catalog checks
- `SUPABASE_URL` + `SUPABASE_ANON_KEY` — RLS lockdown probes

**Exit codes:** 0 = all pass, 1 = failures, 2 = warnings only

**When it fails:**
- `rls_*` FAIL → run `008_forensic_hardening.sql` in Supabase SQL Editor
- `fk_evidence_restrict` FAIL → same migration fixes it
- `ghost_runs` WARN → check Telegram bot, approve/abort stuck runs
- `[INGESTION STALLED]` → scraper/collector cron is down — check logs
- `[CACHE STALE]` → collectors running but TTL too short — run more frequently or tune TTL
- `evidence_price` FAIL → pipeline operating on junk prices — stop publishing

### Operational Rule

> If you need to open the Supabase dashboard more than 2x/day, there's too much complexity. `rayvault doctor` + `rayvault stats` should cover 95% of monitoring.

## Worker Lease Lock (009)

After running `008_forensic_hardening.sql`, apply `009_worker_lease_lock.sql` for multi-worker support:

### Why

Prevents 2+ workers from claiming the same run. Uses a **lease pattern** (lock with expiration) so crashed workers don't hold runs forever.

### Columns Added to `pipeline_runs`

| Column | Type | Purpose |
|--------|------|---------|
| `worker_id` | text | Which worker holds the lock ("RayMac-01") |
| `locked_at` | timestamptz | When the lock was acquired |
| `lock_expires_at` | timestamptz | When the lease expires (heartbeat renews) |
| `lock_token` | text | UUID per claim session (prevents wrong-worker unlock) |

### RPC Functions

| Function | Purpose |
|----------|---------|
| `cas_claim_run(run_id, worker_id, lock_token, lease_minutes)` | Atomic CAS claim (only if free/expired or same worker) |
| `cas_heartbeat_run(run_id, worker_id, lock_token, lease_minutes)` | Renew lease (includes waiting_approval) |
| `cas_release_run(run_id, worker_id, lock_token)` | Release lock (terminal states) |
| `force_release_expired_run(run_id)` | Dashboard force-release (only if expired) |

### Worker Protocol

```python
from tools.lib.run_manager import RunManager

rm = RunManager(run_id="your-uuid", worker_id="RayMac-01", use_supabase=True)
rm.start()

# 1. Claim the run (CAS-safe)
if not rm.claim(lease_minutes=10):
    print("Already claimed by another worker")
    return

# 2. Heartbeat every 2-3 minutes while processing
rm.heartbeat()  # renews lease for another 10 min

# 3. If resuming from crash, use persisted token
rm.claim(existing_token="saved-uuid-from-disk")

# 4. Auto-release on complete/fail/abort
rm.complete()  # lock released automatically
```

### SRE Guardrails

| Guardrail | DB-side | Python-side |
|-----------|---------|-------------|
| `SET search_path = public` | All 4 RPCs | N/A |
| Lease clamp 1-30 min | `GREATEST(1, LEAST(p_lease_minutes, 30))` | `_clamp_lease()` |
| Worker_id min 3 chars | `RAISE EXCEPTION` if `< 3` | Returns `False` |
| Token renewal on reclaim | `CASE WHEN worker_id = p_worker_id THEN lock_token ELSE p_lock_token END` | Heartbeat-first reclaim |
| Lock lost logging | N/A | `lock_lost` event on heartbeat failure |
| Partial indexes | `idx_runs_lock_expiry`, `idx_runs_unclaimed` | N/A |

### Safety Rules

1. **Heartbeat < lease/3** — heartbeat every 2-3 min with 10 min lease
2. **Auto-release on terminal** — `complete()`, `fail()`, `abort()` release the lock
3. **Reclaim support** — persist `lock_token` to disk; on restart, pass to `claim(existing_token=...)`
4. **Force release** — dashboard can only force-release if `lock_expires_at < now()`
5. **Heartbeat during gate** — worker keeps heartbeating during `waiting_approval` to retain ownership
6. **Lock lost panic** — on `heartbeat() → False`, worker stops immediately and logs `lock_lost` event

## Testing

```bash
# Run all 91 tests
python3 tools/test_run_manager.py

# Tests cover:
# - Circuit breaker tier gating (7 tests)
# - Auto-refetch logic (3 tests)
# - Conflict detection (4 tests)
# - SKU fingerprint (4 tests)
# - Refresh logic (5 tests)
# - Hedge annotations (9 tests)
# - Run manager state machine (7 tests)
# - Status checks (3 tests)
# - CAS approval flow (5 tests)
# - CB integration (3 tests)
# - Snapshot integrity (2 tests)
# - Worker lease + SRE guardrails (17 tests)
# - Telegram callback parsing (5 tests)
# - Telegram gate handler (5 tests)
# - Context builder (8 tests)
# - YAML parser (3 tests)
# - End-to-end gate flow (2 tests)
```
