-- 011 — run_events SRE hardening: idempotency + severity + triage indexes.
-- Run in Supabase SQL Editor after 010_claim_next_and_unlock.sql.
--
-- Adds:
--   - event_id (uuid) + unique index → prevents duplicate events from spool replay
--   - severity (DEBUG/INFO/WARN/CRITICAL) + CHECK constraint
--   - reason_key, source, occurred_at for telemetry/triage
--   - Performance indexes for Doctor and dashboard queries
--   - Lightweight trigger to auto-fill event_id + occurred_at if app forgets
--
-- Idempotent: safe to run multiple times.

-- ==========================================================================
-- 0. Prerequisites
-- ==========================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ==========================================================================
-- 1. New columns
-- ==========================================================================

ALTER TABLE run_events
  ADD COLUMN IF NOT EXISTS event_id uuid,
  ADD COLUMN IF NOT EXISTS severity text,
  ADD COLUMN IF NOT EXISTS reason_key text,
  ADD COLUMN IF NOT EXISTS source text,
  ADD COLUMN IF NOT EXISTS occurred_at timestamptz;

-- ==========================================================================
-- 2. Backfill existing rows (safe, idempotent)
-- ==========================================================================

UPDATE run_events
SET occurred_at = COALESCE(occurred_at, created_at, now())
WHERE occurred_at IS NULL;

UPDATE run_events
SET event_id = COALESCE(event_id, gen_random_uuid())
WHERE event_id IS NULL;

-- ==========================================================================
-- 3. Severity CHECK constraint
-- ==========================================================================

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'run_events_severity_check'
  ) THEN
    ALTER TABLE run_events
      ADD CONSTRAINT run_events_severity_check
      CHECK (severity IS NULL OR severity IN ('DEBUG', 'INFO', 'WARN', 'CRITICAL'));
  END IF;
END$$;

-- ==========================================================================
-- 4. Idempotency: unique index on event_id (partial — only non-null)
-- ==========================================================================

CREATE UNIQUE INDEX IF NOT EXISTS idx_run_events_idempotency
ON run_events (event_id)
WHERE event_id IS NOT NULL;

-- ==========================================================================
-- 5. Doctor/dashboard performance indexes
-- ==========================================================================

CREATE INDEX IF NOT EXISTS idx_run_events_run_id_occurred
ON run_events (run_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_run_events_severity_occurred
ON run_events (severity, occurred_at DESC)
WHERE severity IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_run_events_reason_key_occurred
ON run_events (reason_key, occurred_at DESC)
WHERE reason_key IS NOT NULL;

-- ==========================================================================
-- 6. Auto-fill trigger for event_id + occurred_at
-- ==========================================================================

CREATE OR REPLACE FUNCTION trg_run_events_fill_defaults()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.occurred_at IS NULL THEN
    NEW.occurred_at := now();
  END IF;

  IF NEW.event_id IS NULL THEN
    NEW.event_id := gen_random_uuid();
  END IF;

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
    FOR EACH ROW
    EXECUTE FUNCTION trg_run_events_fill_defaults();
  END IF;
END$$;
