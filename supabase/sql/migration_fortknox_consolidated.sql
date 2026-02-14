-- ==========================================================================
-- RayVault FortKnox v0.1 — Consolidated Go-Live Migration
-- ==========================================================================
--
-- Single-file migration for fresh Supabase environments.
-- Consolidates: 007 + 008 + 009 + 010 + 011 + 012
--
-- Assumes 005_pipeline_schema.sql already ran (tables exist).
-- 100% idempotent: safe to re-run.
--
-- Schema contract:
--   - Table: pipeline_runs (NOT "runs")
--   - RPCs: rpc_claim_next_run (returns uuid), cas_heartbeat_run,
--           rpc_release_run, rpc_force_unlock_run, cas_claim_run,
--           cas_run_status
--   - Views: incidents_last_24h, incidents_critical_open
--
-- Ignition ritual after running:
--   1. make check-contract  (verifies all RPCs are callable)
--   2. make worker           (start worker)
--   3. Quick Cockpit query   (see section 10)
--   4. kill -TERM test       (verify safe_stop_async)
--   5. kill -9 test          (verify stale detection)
--   6. SELECT * FROM incidents_critical_open  (should be empty)
--
-- ==========================================================================

-- 0) EXTENSIONS
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ==========================================================================
-- 1) UTILITY: auto-update updated_at trigger function
-- ==========================================================================

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

-- ==========================================================================
-- 2) PIPELINE_RUNS: state machine + approval gate + worker lease lock
-- ==========================================================================

-- 2a. Expand allowed statuses
ALTER TABLE public.pipeline_runs
    DROP CONSTRAINT IF EXISTS pipeline_runs_status_check;
ALTER TABLE public.pipeline_runs
    ADD CONSTRAINT pipeline_runs_status_check
    CHECK (status IN (
        'pending', 'running', 'in_progress',
        'waiting_approval', 'approved',
        'complete', 'done', 'failed', 'aborted', 'cancelled'
    ));

-- 2b. Approval gate + context columns (from 007)
ALTER TABLE public.pipeline_runs
    ADD COLUMN IF NOT EXISTS approval_nonce text NOT NULL DEFAULT '';
ALTER TABLE public.pipeline_runs
    ADD COLUMN IF NOT EXISTS context_snapshot jsonb NOT NULL DEFAULT '{}';
ALTER TABLE public.pipeline_runs
    ADD COLUMN IF NOT EXISTS policy_version text NOT NULL DEFAULT '';
ALTER TABLE public.pipeline_runs
    ADD COLUMN IF NOT EXISTS ranking_model text NOT NULL DEFAULT '';
ALTER TABLE public.pipeline_runs
    ADD COLUMN IF NOT EXISTS tone_authority_level text NOT NULL DEFAULT 'balanced';
ALTER TABLE public.pipeline_runs
    ADD COLUMN IF NOT EXISTS variant_id text NOT NULL DEFAULT '';
ALTER TABLE public.pipeline_runs
    ADD COLUMN IF NOT EXISTS token_cost_est integer NOT NULL DEFAULT 0;
ALTER TABLE public.pipeline_runs
    ADD COLUMN IF NOT EXISTS evidence_score_bucket text NOT NULL DEFAULT '';

-- 2c. Worker lease lock columns (from 009)
ALTER TABLE public.pipeline_runs
    ADD COLUMN IF NOT EXISTS worker_id text NOT NULL DEFAULT '';
ALTER TABLE public.pipeline_runs
    ADD COLUMN IF NOT EXISTS locked_at timestamptz;
ALTER TABLE public.pipeline_runs
    ADD COLUMN IF NOT EXISTS lock_expires_at timestamptz;
ALTER TABLE public.pipeline_runs
    ADD COLUMN IF NOT EXISTS lock_token text NOT NULL DEFAULT '';

-- 2d. Worker health telemetry columns (from 010)
ALTER TABLE public.pipeline_runs
    ADD COLUMN IF NOT EXISTS last_heartbeat_at timestamptz;
ALTER TABLE public.pipeline_runs
    ADD COLUMN IF NOT EXISTS worker_state text NOT NULL DEFAULT 'idle';
ALTER TABLE public.pipeline_runs
    ADD COLUMN IF NOT EXISTS worker_last_error text NOT NULL DEFAULT '';
ALTER TABLE public.pipeline_runs
    ADD COLUMN IF NOT EXISTS last_heartbeat_latency_ms int;

-- 2e. Task type for filtered claims
ALTER TABLE public.pipeline_runs
    ADD COLUMN IF NOT EXISTS task_type text NOT NULL DEFAULT '';

-- 2f. worker_state CHECK constraint (from 012)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'pipeline_runs_worker_state_chk'
  ) THEN
    ALTER TABLE public.pipeline_runs
      ADD CONSTRAINT pipeline_runs_worker_state_chk
      CHECK (worker_state IN ('idle', 'active', 'waiting', 'panic'));
  END IF;
END$$;

-- 2g. updated_at trigger
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_pipeline_runs_updated_at'
          AND tgrelid = 'public.pipeline_runs'::regclass
    ) THEN
        CREATE TRIGGER trg_pipeline_runs_updated_at
            BEFORE UPDATE ON public.pipeline_runs
            FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
    END IF;
END$$;

-- ==========================================================================
-- 3) RUN_EVENTS: audit trail + idempotency + severity
-- ==========================================================================

-- 3a. Create table (if not exists — 007 creates it)
CREATE TABLE IF NOT EXISTS public.run_events (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id          uuid        NOT NULL
                    REFERENCES public.pipeline_runs(id) ON DELETE CASCADE,
    action_id       text        NOT NULL DEFAULT '',
    event_type      text        NOT NULL DEFAULT '',
    payload         jsonb       NOT NULL DEFAULT '{}',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- 3b. Drop old restrictive event_type CHECK if it exists
-- (original 007 had a narrow whitelist; we need to allow worker_panic, etc.)
ALTER TABLE public.run_events
    DROP CONSTRAINT IF EXISTS run_events_event_type_check;

-- 3c. SRE columns (from 011)
ALTER TABLE public.run_events
    ADD COLUMN IF NOT EXISTS event_id uuid;
ALTER TABLE public.run_events
    ADD COLUMN IF NOT EXISTS severity text;
ALTER TABLE public.run_events
    ADD COLUMN IF NOT EXISTS reason_key text;
ALTER TABLE public.run_events
    ADD COLUMN IF NOT EXISTS source text;
ALTER TABLE public.run_events
    ADD COLUMN IF NOT EXISTS occurred_at timestamptz;

-- 3d. Severity CHECK constraint
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'run_events_severity_check'
  ) THEN
    ALTER TABLE public.run_events
      ADD CONSTRAINT run_events_severity_check
      CHECK (severity IS NULL OR severity IN ('DEBUG', 'INFO', 'WARN', 'CRITICAL'));
  END IF;
END$$;

-- 3e. Backfill existing rows
UPDATE run_events SET occurred_at = COALESCE(occurred_at, created_at, now())
WHERE occurred_at IS NULL;

UPDATE run_events SET event_id = COALESCE(event_id, gen_random_uuid())
WHERE event_id IS NULL;

-- 3f. Auto-fill trigger (event_id + occurred_at)
CREATE OR REPLACE FUNCTION trg_run_events_fill_defaults()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.occurred_at IS NULL THEN NEW.occurred_at := now(); END IF;
  IF NEW.event_id IS NULL THEN NEW.event_id := gen_random_uuid(); END IF;
  RETURN NEW;
END;
$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'run_events_fill_defaults'
  ) THEN
    CREATE TRIGGER run_events_fill_defaults
    BEFORE INSERT ON run_events
    FOR EACH ROW EXECUTE FUNCTION trg_run_events_fill_defaults();
  END IF;
END$$;

-- 3g. RLS: deny anon + authenticated
ALTER TABLE public.run_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "deny anon run_events" ON public.run_events;
CREATE POLICY "deny anon run_events" ON public.run_events
    FOR ALL TO anon USING (false) WITH CHECK (false);
DROP POLICY IF EXISTS "deny authenticated run_events" ON public.run_events;
CREATE POLICY "deny authenticated run_events" ON public.run_events
    FOR ALL TO authenticated USING (false) WITH CHECK (false);

-- ==========================================================================
-- 4) EVIDENCE + FINGERPRINTS + RUN_EVIDENCE (from 007 + 008)
-- ==========================================================================

-- 4a. evidence_items
CREATE TABLE IF NOT EXISTS public.evidence_items (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    normalized_id   text        NOT NULL DEFAULT '',
    asin            text        NOT NULL DEFAULT '',
    claim_type      text        NOT NULL DEFAULT '',
    trust_tier      integer     NOT NULL DEFAULT 3
                    CHECK (trust_tier BETWEEN 1 AND 5),
    confidence      numeric(4,3) NOT NULL DEFAULT 0,
    value           jsonb       NOT NULL DEFAULT '{}',
    value_hash      text        NOT NULL DEFAULT '',
    source_url      text        NOT NULL DEFAULT '',
    source_name     text        NOT NULL DEFAULT '',
    source_type     text        NOT NULL DEFAULT '',
    reason_flags    text[]      NOT NULL DEFAULT '{}',
    fetched_at      timestamptz NOT NULL DEFAULT now(),
    expires_at      timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.evidence_items ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "deny anon evidence_items" ON public.evidence_items;
CREATE POLICY "deny anon evidence_items" ON public.evidence_items
    FOR ALL TO anon USING (false) WITH CHECK (false);
DROP POLICY IF EXISTS "deny authenticated evidence_items" ON public.evidence_items;
CREATE POLICY "deny authenticated evidence_items" ON public.evidence_items
    FOR ALL TO authenticated USING (false) WITH CHECK (false);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_evidence_items_updated_at'
          AND tgrelid = 'public.evidence_items'::regclass
    ) THEN
        CREATE TRIGGER trg_evidence_items_updated_at
            BEFORE UPDATE ON public.evidence_items
            FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
    END IF;
END$$;

-- 4b. product_fingerprints
CREATE TABLE IF NOT EXISTS public.product_fingerprints (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    asin            text        NOT NULL,
    normalized_id   text        NOT NULL DEFAULT '',
    brand           text        NOT NULL DEFAULT '',
    model_number    text        NOT NULL DEFAULT '',
    ean_upc         text        NOT NULL DEFAULT '',
    variant_attrs   jsonb       NOT NULL DEFAULT '{}',
    title_hash      text        NOT NULL DEFAULT '',
    fingerprint_hash text       NOT NULL DEFAULT '',
    first_seen_at   timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_product_fingerprints_asin
    ON public.product_fingerprints (asin);

ALTER TABLE public.product_fingerprints ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "deny anon product_fingerprints" ON public.product_fingerprints;
CREATE POLICY "deny anon product_fingerprints" ON public.product_fingerprints
    FOR ALL TO anon USING (false) WITH CHECK (false);
DROP POLICY IF EXISTS "deny authenticated product_fingerprints" ON public.product_fingerprints;
CREATE POLICY "deny authenticated product_fingerprints" ON public.product_fingerprints
    FOR ALL TO authenticated USING (false) WITH CHECK (false);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_product_fingerprints_updated_at'
          AND tgrelid = 'public.product_fingerprints'::regclass
    ) THEN
        CREATE TRIGGER trg_product_fingerprints_updated_at
            BEFORE UPDATE ON public.product_fingerprints
            FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
    END IF;
END$$;

-- 4c. run_evidence (per-run forensic scoring)
CREATE TABLE IF NOT EXISTS public.run_evidence (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id          uuid        NOT NULL
                    REFERENCES public.pipeline_runs(id) ON DELETE CASCADE,
    evidence_id     bigint      NOT NULL,
    CONSTRAINT run_evidence_evidence_id_restrict
                    FOREIGN KEY (evidence_id)
                    REFERENCES public.evidence_items(id) ON DELETE RESTRICT,
    score_at_run    numeric(6,2) NOT NULL DEFAULT 0,
    freshness_at_run numeric(4,3) NOT NULL DEFAULT 0,
    policy_version  text        NOT NULL DEFAULT '',
    used_for_claim_type text    NOT NULL DEFAULT '',
    manual_override boolean     NOT NULL DEFAULT false,
    override_reason text        NOT NULL DEFAULT '',
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_run_evidence_unique
    ON public.run_evidence (run_id, evidence_id);

ALTER TABLE public.run_evidence ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "deny anon run_evidence" ON public.run_evidence;
CREATE POLICY "deny anon run_evidence" ON public.run_evidence
    FOR ALL TO anon USING (false) WITH CHECK (false);
DROP POLICY IF EXISTS "deny authenticated run_evidence" ON public.run_evidence;
CREATE POLICY "deny authenticated run_evidence" ON public.run_evidence
    FOR ALL TO authenticated USING (false) WITH CHECK (false);

-- ==========================================================================
-- 5) INDEXES (consolidated from 009 + 010 + 011 + 012)
-- ==========================================================================

-- pipeline_runs: claim-next queue
CREATE INDEX IF NOT EXISTS idx_runs_claim_next
    ON public.pipeline_runs (status, created_at ASC)
    WHERE status IN ('running', 'in_progress', 'approved');

-- pipeline_runs: lock audit
CREATE INDEX IF NOT EXISTS idx_runs_lock_audit
    ON public.pipeline_runs (status, lock_expires_at)
    WHERE status IN ('running', 'in_progress', 'approved', 'waiting_approval');

-- pipeline_runs: worker health dashboard
CREATE INDEX IF NOT EXISTS idx_runs_worker_health
    ON public.pipeline_runs (worker_state, last_heartbeat_at DESC)
    WHERE worker_state IN ('active', 'panic', 'waiting');

-- pipeline_runs: health focus (Doctor/dashboard)
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_health_focus
    ON public.pipeline_runs (worker_state, last_heartbeat_at DESC)
    WHERE worker_state IN ('active', 'waiting', 'panic');

-- pipeline_runs: locking
CREATE INDEX IF NOT EXISTS idx_runs_locking
    ON public.pipeline_runs (status, lock_expires_at, created_at DESC);

-- pipeline_runs: expired lock cleanup
CREATE INDEX IF NOT EXISTS idx_runs_lock_expiry
    ON public.pipeline_runs (lock_expires_at)
    WHERE lock_expires_at IS NOT NULL;

-- pipeline_runs: unclaimed runs
CREATE INDEX IF NOT EXISTS idx_runs_unclaimed
    ON public.pipeline_runs (status, created_at DESC)
    WHERE worker_id = '';

-- pipeline_runs: approval nonce lookup
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_approval_nonce
    ON public.pipeline_runs (approval_nonce)
    WHERE approval_nonce != '';

-- run_events: idempotency (event_id unique, partial)
CREATE UNIQUE INDEX IF NOT EXISTS idx_run_events_idempotency
    ON public.run_events (event_id)
    WHERE event_id IS NOT NULL;

-- run_events: action_id idempotency (from 007)
CREATE UNIQUE INDEX IF NOT EXISTS idx_run_events_idempotent
    ON public.run_events (run_id, action_id)
    WHERE action_id != '';

-- run_events: timeline by run
CREATE INDEX IF NOT EXISTS idx_run_events_run_id_occurred
    ON public.run_events (run_id, occurred_at DESC);

-- run_events: severity triage
CREATE INDEX IF NOT EXISTS idx_run_events_severity_occurred
    ON public.run_events (severity, occurred_at DESC)
    WHERE severity IS NOT NULL;

-- run_events: reason_key lookup
CREATE INDEX IF NOT EXISTS idx_run_events_reason_key_occurred
    ON public.run_events (reason_key, occurred_at DESC)
    WHERE reason_key IS NOT NULL;

-- run_events: recent events
CREATE INDEX IF NOT EXISTS idx_run_events_recent
    ON public.run_events (occurred_at DESC)
    WHERE occurred_at IS NOT NULL;

-- run_events: functional severity priority (dashboard ORDER BY)
CREATE INDEX IF NOT EXISTS idx_run_events_severity_priority
    ON public.run_events (
      CASE upper(COALESCE(severity, 'INFO'))
        WHEN 'CRITICAL' THEN 4
        WHEN 'ERROR'    THEN 3
        WHEN 'WARN'     THEN 2
        ELSE 1
      END DESC,
      occurred_at DESC
    );

-- evidence_items: core lookups
CREATE INDEX IF NOT EXISTS idx_evidence_items_asin_claim
    ON public.evidence_items (asin, claim_type);
CREATE INDEX IF NOT EXISTS idx_evidence_nid_claim_fetched
    ON public.evidence_items (normalized_id, claim_type, fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_evidence_items_expires
    ON public.evidence_items (expires_at)
    WHERE expires_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_evidence_tier4plus
    ON public.evidence_items (normalized_id, claim_type, fetched_at DESC)
    WHERE trust_tier >= 4;

-- ==========================================================================
-- 6) RPCs — FortKnox contract (SECURITY DEFINER, SET search_path)
-- ==========================================================================

-- 6a. cas_run_status: atomic CAS update for approval gate
CREATE OR REPLACE FUNCTION public.cas_run_status(
    p_run_id         uuid,
    p_expected_status text,
    p_expected_nonce  text,
    p_new_status      text,
    p_new_snapshot    jsonb DEFAULT NULL,
    p_approved_by     text DEFAULT ''
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE rows_affected int;
BEGIN
    UPDATE public.pipeline_runs
    SET status           = p_new_status,
        approval_nonce   = CASE WHEN p_new_status = 'waiting_approval'
                                THEN p_expected_nonce ELSE '' END,
        context_snapshot = COALESCE(p_new_snapshot, context_snapshot)
    WHERE id = p_run_id
      AND status = p_expected_status
      AND (p_expected_nonce = '' OR approval_nonce = p_expected_nonce);
    GET DIAGNOSTICS rows_affected = ROW_COUNT;
    RETURN rows_affected > 0;
END;
$$;

-- 6b. cas_claim_run: CAS claim a specific run
CREATE OR REPLACE FUNCTION public.cas_claim_run(
    p_run_id         uuid,
    p_worker_id      text,
    p_lock_token     text,
    p_lease_minutes  int DEFAULT 10
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE rows_affected int;
BEGIN
    IF length(trim(p_worker_id)) < 3 THEN
        RAISE EXCEPTION 'worker_id must be at least 3 characters, got "%"', trim(p_worker_id);
    END IF;
    p_lease_minutes := GREATEST(1, LEAST(p_lease_minutes, 30));

    UPDATE public.pipeline_runs
    SET worker_id       = p_worker_id,
        locked_at       = CASE
            WHEN worker_id = p_worker_id AND lock_expires_at >= now()
                THEN locked_at
            ELSE now()
        END,
        lock_expires_at = now() + make_interval(mins => p_lease_minutes),
        lock_token      = CASE
            WHEN worker_id = p_worker_id AND lock_expires_at >= now()
                THEN lock_token
            ELSE p_lock_token
        END
    WHERE id = p_run_id
      AND status IN ('running', 'in_progress', 'approved')
      AND (worker_id = '' OR lock_expires_at IS NULL OR lock_expires_at < now()
           OR worker_id = p_worker_id);
    GET DIAGNOSTICS rows_affected = ROW_COUNT;
    RETURN rows_affected > 0;
END;
$$;

-- 6c. rpc_claim_next_run: recovery-first atomic queue consumer
--
-- Two-phase priority:
--   Phase 1 (recovery): reclaim own active run with valid lease
--   Phase 2 (fresh claim): next free/expired run via FOR UPDATE SKIP LOCKED
--
-- Returns: uuid (run_id) or NULL. NOT SETOF — scalar return.
-- Token + locked_at stability: only rotated on ownership change.
CREATE OR REPLACE FUNCTION public.rpc_claim_next_run(
    p_worker_id      text,
    p_lock_token     text,
    p_lease_minutes  int DEFAULT 10,
    p_task_type      text DEFAULT NULL
) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE
    v_run_id uuid;
    v_now    timestamptz := now();
    v_lease  int := GREATEST(1, LEAST(p_lease_minutes, 30));
BEGIN
    IF length(trim(p_worker_id)) < 3 THEN
        RAISE EXCEPTION 'worker_id must be at least 3 characters, got "%"', trim(p_worker_id);
    END IF;

    -- Phase 1: Recovery — reclaim own active run
    SELECT r.id INTO v_run_id
    FROM public.pipeline_runs r
    WHERE r.worker_id = p_worker_id
      AND r.lock_expires_at >= v_now
      AND r.status IN ('running', 'in_progress', 'approved', 'waiting_approval')
    ORDER BY r.locked_at DESC NULLS LAST
    LIMIT 1
    FOR UPDATE OF r;

    IF v_run_id IS NOT NULL THEN
        UPDATE public.pipeline_runs
        SET lock_expires_at   = v_now + make_interval(mins => v_lease),
            last_heartbeat_at = v_now,
            worker_state      = CASE WHEN status = 'waiting_approval'
                                     THEN 'waiting' ELSE 'active' END,
            worker_last_error = ''
        WHERE id = v_run_id;
        RETURN v_run_id;
    END IF;

    -- Phase 2: Fresh claim — next eligible run
    SELECT r.id INTO v_run_id
    FROM public.pipeline_runs r
    WHERE r.status IN ('running', 'in_progress', 'approved')
      AND (r.worker_id IS NULL OR r.worker_id = ''
           OR r.lock_expires_at IS NULL OR r.lock_expires_at < v_now)
      AND (p_task_type IS NULL OR r.task_type = p_task_type)
    ORDER BY
        CASE WHEN r.status = 'approved' THEN 1 ELSE 2 END,
        r.created_at ASC
    LIMIT 1
    FOR UPDATE OF r SKIP LOCKED;

    IF v_run_id IS NULL THEN
        RETURN NULL;
    END IF;

    UPDATE public.pipeline_runs
    SET worker_id         = p_worker_id,
        locked_at         = v_now,
        lock_expires_at   = v_now + make_interval(mins => v_lease),
        lock_token        = p_lock_token,
        worker_state      = 'active',
        last_heartbeat_at = v_now,
        worker_last_error = ''
    WHERE id = v_run_id;

    RETURN v_run_id;
END;
$$;

-- 6d. cas_heartbeat_run: renew lease + telemetry + lock verification
--
-- Returns false if lock/token mismatch → worker must panic (lost_lock).
-- p_latency_ms: piggybacked from previous heartbeat measurement.
CREATE OR REPLACE FUNCTION public.cas_heartbeat_run(
    p_run_id         uuid,
    p_worker_id      text,
    p_lock_token     text,
    p_lease_minutes  int DEFAULT 10,
    p_latency_ms     int DEFAULT NULL
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE
    rows_affected int;
    v_status text;
BEGIN
    p_lease_minutes := GREATEST(1, LEAST(p_lease_minutes, 30));

    SELECT status INTO v_status
    FROM public.pipeline_runs
    WHERE id = p_run_id
      AND worker_id = p_worker_id
      AND lock_token = p_lock_token;

    IF v_status IS NULL THEN
        RETURN false;  -- Token/worker mismatch
    END IF;

    IF v_status NOT IN ('running', 'in_progress', 'approved', 'waiting_approval') THEN
        RETURN false;  -- Terminal state
    END IF;

    UPDATE public.pipeline_runs
    SET lock_expires_at           = now() + make_interval(mins => p_lease_minutes),
        last_heartbeat_at         = now(),
        last_heartbeat_latency_ms = COALESCE(p_latency_ms, last_heartbeat_latency_ms),
        worker_state              = CASE
            WHEN v_status = 'waiting_approval' THEN 'waiting'
            ELSE 'active'
        END
    WHERE id = p_run_id
      AND worker_id = p_worker_id
      AND lock_token = p_lock_token;

    GET DIAGNOSTICS rows_affected = ROW_COUNT;
    RETURN rows_affected > 0;
END;
$$;

-- 6e. rpc_release_run: clean lock release on completion
CREATE OR REPLACE FUNCTION public.rpc_release_run(
    p_run_id         uuid,
    p_worker_id      text,
    p_lock_token     text
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE rows_affected int;
BEGIN
    UPDATE public.pipeline_runs
    SET worker_id                 = '',
        locked_at                 = NULL,
        lock_expires_at           = NULL,
        lock_token                = '',
        worker_state              = 'idle',
        last_heartbeat_latency_ms = NULL,
        worker_last_error         = ''
    WHERE id = p_run_id
      AND worker_id = p_worker_id
      AND lock_token = p_lock_token;
    GET DIAGNOSTICS rows_affected = ROW_COUNT;
    RETURN rows_affected > 0;
END;
$$;

-- 6f. rpc_force_unlock_run: operator intervention with forensic snapshot
CREATE OR REPLACE FUNCTION public.rpc_force_unlock_run(
    p_run_id       uuid,
    p_operator_id  text,
    p_reason       text,
    p_force        boolean DEFAULT false
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE
    v_rows int;
    v_prev record;
BEGIN
    IF length(trim(p_operator_id)) < 3 THEN
        RAISE EXCEPTION 'operator_id must be at least 3 characters, got "%"', trim(p_operator_id);
    END IF;

    SELECT worker_id, lock_token, locked_at, lock_expires_at, status, worker_state
    INTO v_prev
    FROM public.pipeline_runs WHERE id = p_run_id;

    IF NOT FOUND THEN RETURN false; END IF;

    IF NOT p_force AND v_prev.status NOT IN (
        'running', 'in_progress', 'approved', 'waiting_approval'
    ) THEN
        RETURN false;
    END IF;

    UPDATE public.pipeline_runs
    SET worker_id         = '',
        locked_at         = NULL,
        lock_expires_at   = NULL,
        lock_token        = '',
        worker_state      = 'idle',
        worker_last_error = left('manual_unlock: ' || COALESCE(p_reason, ''), 500)
    WHERE id = p_run_id
      AND (p_force = true OR lock_expires_at IS NULL OR lock_expires_at < now());

    GET DIAGNOSTICS v_rows = ROW_COUNT;

    IF v_rows > 0 THEN
        INSERT INTO public.run_events
            (run_id, action_id, event_type, event_id, severity,
             reason_key, source, occurred_at, payload)
        VALUES (
            p_run_id,
            gen_random_uuid()::text,
            'manual_unlock',
            gen_random_uuid(),
            'WARN',
            'manual_unlock',
            p_operator_id,
            now(),
            jsonb_build_object(
                'operator_id',       p_operator_id,
                'reason',            p_reason,
                'force',             p_force,
                'prev_worker_id',    COALESCE(v_prev.worker_id, ''),
                'prev_lock_token',   COALESCE(v_prev.lock_token, ''),
                'prev_locked_at',    v_prev.locked_at,
                'prev_expires_at',   v_prev.lock_expires_at,
                'prev_status',       COALESCE(v_prev.status, ''),
                'prev_worker_state', COALESCE(v_prev.worker_state, '')
            )
        );
        RETURN true;
    END IF;
    RETURN false;
END;
$$;

-- 6g. force_release_expired_run: dashboard convenience (expired only)
CREATE OR REPLACE FUNCTION public.force_release_expired_run(
    p_run_id uuid
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE rows_affected int;
BEGIN
    UPDATE public.pipeline_runs
    SET worker_id = '', locked_at = NULL, lock_expires_at = NULL,
        lock_token = ''
    WHERE id = p_run_id AND lock_expires_at < now();
    GET DIAGNOSTICS rows_affected = ROW_COUNT;
    RETURN rows_affected > 0;
END;
$$;

-- ==========================================================================
-- 7) ACCESS CONTROL — RPCs only via service_role
-- ==========================================================================

REVOKE EXECUTE ON FUNCTION public.rpc_claim_next_run(text, text, int, text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.rpc_force_unlock_run(uuid, text, text, boolean) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.cas_heartbeat_run(uuid, text, text, int, int) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.rpc_release_run(uuid, text, text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.cas_claim_run(uuid, text, text, int) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION public.rpc_claim_next_run(text, text, int, text) TO service_role;
GRANT EXECUTE ON FUNCTION public.rpc_force_unlock_run(uuid, text, text, boolean) TO service_role;
GRANT EXECUTE ON FUNCTION public.cas_heartbeat_run(uuid, text, text, int, int) TO service_role;
GRANT EXECUTE ON FUNCTION public.rpc_release_run(uuid, text, text) TO service_role;
GRANT EXECUTE ON FUNCTION public.cas_claim_run(uuid, text, text, int) TO service_role;

-- ==========================================================================
-- 8) VIEWS — Incidents (mini-Prometheus in Postgres)
-- ==========================================================================

-- 8a. incidents_last_24h: full dashboard view
CREATE OR REPLACE VIEW incidents_last_24h AS
WITH
e24 AS (
  SELECT
    re.run_id,
    re.event_id,
    COALESCE(re.occurred_at, re.created_at, now()) AS occurred_at,
    COALESCE(re.severity, 'INFO') AS severity,
    re.event_type,
    re.reason_key,
    re.payload
  FROM run_events re
  WHERE COALESCE(re.occurred_at, re.created_at, now()) >= now() - interval '24 hours'
),
sev_rank AS (
  SELECT run_id,
    MAX(CASE upper(severity)
      WHEN 'CRITICAL' THEN 4 WHEN 'ERROR' THEN 3
      WHEN 'WARN' THEN 2 ELSE 1
    END) AS top_sev_rank
  FROM e24 GROUP BY run_id
),
last_event AS (
  SELECT DISTINCT ON (run_id)
    run_id,
    occurred_at AS last_event_at,
    severity    AS last_event_severity,
    event_type  AS last_event_type,
    reason_key  AS last_reason_key
  FROM e24
  ORDER BY run_id, occurred_at DESC
),
stale AS (
  SELECT r.id AS run_id,
    CASE
      WHEN r.worker_state = 'active'
       AND r.last_heartbeat_at IS NOT NULL
       AND r.lock_expires_at IS NOT NULL
       AND r.last_heartbeat_at < (
         now() - (GREATEST(
           2 * EXTRACT(EPOCH FROM (r.lock_expires_at - r.locked_at)) / 60, 10
         ) || ' minutes')::interval)
      THEN true ELSE false
    END AS is_stale
  FROM pipeline_runs r
)
SELECT
  r.id AS run_id, r.status, r.task_type,
  r.worker_id, r.worker_state,
  r.last_heartbeat_at, r.last_heartbeat_latency_ms,
  r.lock_expires_at,
  CASE sev.top_sev_rank
    WHEN 4 THEN 'CRITICAL' WHEN 3 THEN 'ERROR'
    WHEN 2 THEN 'WARN' ELSE 'INFO'
  END AS top_severity,
  le.last_event_at, le.last_event_severity,
  le.last_event_type, le.last_reason_key,
  COALESCE(st.is_stale, false) AS is_stale,
  (SELECT count(*) FROM e24 WHERE e24.run_id = r.id) AS event_count_24h
FROM pipeline_runs r
LEFT JOIN sev_rank sev ON sev.run_id = r.id
LEFT JOIN last_event le ON le.run_id = r.id
LEFT JOIN stale st ON st.run_id = r.id
WHERE sev.run_id IS NOT NULL
   OR COALESCE(st.is_stale, false) = true
ORDER BY
  CASE sev.top_sev_rank
    WHEN 4 THEN 1 WHEN 3 THEN 2 WHEN 2 THEN 3 ELSE 4
  END,
  le.last_event_at DESC NULLS LAST,
  r.updated_at DESC;

-- 8b. incidents_critical_open: Doctor source of truth
CREATE OR REPLACE VIEW incidents_critical_open AS
SELECT
    run_id, worker_id, worker_state, status,
    top_severity, last_reason_key, is_stale,
    last_heartbeat_at, last_heartbeat_latency_ms, lock_expires_at
FROM incidents_last_24h
WHERE (top_severity IN ('CRITICAL', 'ERROR')
       OR is_stale = true
       OR worker_state = 'panic')
  AND status NOT IN ('done', 'failed', 'aborted', 'cancelled');

-- ==========================================================================
-- 9) DONE — Verification queries
-- ==========================================================================
--
-- After running, verify with:
--
-- a) Contract check (all RPCs callable):
--    make check-contract
--
-- b) RLS enabled on all tables:
--    SELECT schemaname, tablename, rowsecurity
--    FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
--
-- c) Grants (should only show service_role):
--    SELECT grantee, table_name, privilege_type
--    FROM information_schema.table_privileges
--    WHERE table_schema = 'public' AND grantee IN ('anon', 'authenticated')
--    ORDER BY table_name, grantee;
--
-- ==========================================================================
-- 10) QUICK COCKPIT (reference — run ad-hoc after make worker)
-- ==========================================================================
--
-- SELECT worker_state, status, count(*) AS total,
--   sum(CASE WHEN last_heartbeat_at IS NULL THEN 1 ELSE 0 END) AS no_hb,
--   round(avg(CASE WHEN worker_state='active'
--     THEN last_heartbeat_latency_ms END)) AS avg_lat_active_ms,
--   max(last_heartbeat_at) AS last_hb_max
-- FROM pipeline_runs
-- WHERE status IN ('running','approved','waiting_approval')
-- GROUP BY worker_state, status
-- ORDER BY worker_state, status;
