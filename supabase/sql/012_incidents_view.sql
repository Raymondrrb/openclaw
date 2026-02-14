-- 012 — incidents views + worker_state constraint + health indexes.
-- Run in Supabase SQL Editor after 011_run_events_sre_hardening.sql.
--
-- Adds:
--   - incidents_last_24h VIEW: actionable dashboard in one SELECT
--   - incidents_critical_open VIEW: only CRITICAL/ERROR/stale/panic (Doctor source of truth)
--   - worker_state CHECK constraint (prevents typos: idle/active/waiting/panic)
--   - idx_runs_health_focus: partial index for active/waiting/panic workers
--   - idx_run_events_recent: general recent-events index
--   - idx_run_events_severity_priority: functional index for severity-first ordering
--
-- Idempotent: safe to run multiple times.

-- ==========================================================================
-- 1. worker_state constraint (prevents "actve" typos in dashboard)
-- ==========================================================================

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'pipeline_runs_worker_state_chk'
  ) THEN
    ALTER TABLE public.pipeline_runs
      ADD CONSTRAINT pipeline_runs_worker_state_chk
      CHECK (worker_state IN ('idle', 'active', 'waiting', 'panic'));
  END IF;
END$$;

-- ==========================================================================
-- 2. Health-focus index (makes dashboard/Doctor queries fast)
-- ==========================================================================

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_health_focus
ON public.pipeline_runs (worker_state, last_heartbeat_at DESC)
WHERE worker_state IN ('active', 'waiting', 'panic');

-- ==========================================================================
-- 3. Recent events index (general time-based lookup)
-- ==========================================================================

CREATE INDEX IF NOT EXISTS idx_run_events_recent
ON public.run_events (occurred_at DESC)
WHERE occurred_at IS NOT NULL;

-- ==========================================================================
-- 4. incidents_last_24h VIEW
-- ==========================================================================
--
-- One SELECT gives you:
--   - Which runs had incidents in the last 24h
--   - Top severity (CRITICAL > ERROR > WARN > INFO)
--   - Last event details (type, reason_key, time)
--   - Stale worker detection (silent death)
--   - Latency info
--   - Worker identity
--
-- Ordering: worst severity first, then most recent events.

CREATE OR REPLACE VIEW incidents_last_24h AS
WITH
-- 1) 24-hour event window
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

-- 2) Top severity rank per run
sev_rank AS (
  SELECT
    run_id,
    MAX(
      CASE upper(severity)
        WHEN 'CRITICAL' THEN 4
        WHEN 'ERROR'    THEN 3
        WHEN 'WARN'     THEN 2
        ELSE 1
      END
    ) AS top_sev_rank
  FROM e24
  GROUP BY run_id
),

-- 3) Most recent event per run
last_event AS (
  SELECT DISTINCT ON (run_id)
    run_id,
    occurred_at AS last_event_at,
    severity    AS last_event_severity,
    event_type  AS last_event_type,
    reason_key  AS last_reason_key,
    payload     AS last_payload
  FROM e24
  ORDER BY run_id, occurred_at DESC
),

-- 4) Stale worker detection (silent death — no heartbeat for 2x lease interval)
stale AS (
  SELECT
    r.id AS run_id,
    CASE
      WHEN r.worker_state = 'active'
       AND r.last_heartbeat_at IS NOT NULL
       AND r.lock_expires_at IS NOT NULL
       AND r.last_heartbeat_at < (
         now() - (
           GREATEST(
             2 * EXTRACT(EPOCH FROM (r.lock_expires_at - r.locked_at)) / 60,
             10
           ) || ' minutes'
         )::interval
       )
      THEN true
      ELSE false
    END AS is_stale
  FROM pipeline_runs r
)

SELECT
  r.id AS run_id,
  r.status,
  r.task_type,
  r.worker_id,
  r.worker_state,
  r.last_heartbeat_at,
  r.last_heartbeat_latency_ms,
  r.lock_expires_at,

  -- Top severity (human-readable)
  CASE sev.top_sev_rank
    WHEN 4 THEN 'CRITICAL'
    WHEN 3 THEN 'ERROR'
    WHEN 2 THEN 'WARN'
    ELSE 'INFO'
  END AS top_severity,

  le.last_event_at,
  le.last_event_severity,
  le.last_event_type,
  le.last_reason_key,

  -- Stale flag
  COALESCE(st.is_stale, false) AS is_stale,

  -- Event count in window
  (SELECT count(*) FROM e24 WHERE e24.run_id = r.id) AS event_count_24h

FROM pipeline_runs r
LEFT JOIN sev_rank sev ON sev.run_id = r.id
LEFT JOIN last_event le ON le.run_id = r.id
LEFT JOIN stale st ON st.run_id = r.id

-- Only show runs with incidents in the last 24h OR stale workers
WHERE sev.run_id IS NOT NULL
   OR COALESCE(st.is_stale, false) = true

ORDER BY
  -- Worst severity first
  CASE sev.top_sev_rank
    WHEN 4 THEN 1
    WHEN 3 THEN 2
    WHEN 2 THEN 3
    ELSE 4
  END,
  le.last_event_at DESC NULLS LAST,
  r.updated_at DESC;

-- ==========================================================================
-- 5. incidents_critical_open VIEW (Doctor source of truth for exit code)
-- ==========================================================================
--
-- Only actionable items: CRITICAL, ERROR, stale, or panic.
-- Excludes terminal runs (done/failed/aborted/cancelled).
-- Perfect for: Doctor exit code, Telegram daily summary, mobile triage.

CREATE OR REPLACE VIEW incidents_critical_open AS
SELECT
    run_id,
    worker_id,
    worker_state,
    status,
    top_severity,
    last_reason_key,
    is_stale,
    last_heartbeat_at,
    last_heartbeat_latency_ms,
    lock_expires_at
FROM incidents_last_24h
WHERE (
        top_severity IN ('CRITICAL', 'ERROR')
        OR is_stale = true
        OR worker_state = 'panic'
      )
  AND status NOT IN ('done', 'failed', 'aborted', 'cancelled');

-- ==========================================================================
-- 6. Functional index: severity priority ordering
-- ==========================================================================
--
-- Speeds up ORDER BY severity-rank queries (dashboard, Doctor).
-- COALESCE handles NULL severity gracefully.

CREATE INDEX IF NOT EXISTS idx_run_events_severity_priority
ON run_events (
  CASE upper(COALESCE(severity, 'INFO'))
    WHEN 'CRITICAL' THEN 4
    WHEN 'ERROR'    THEN 3
    WHEN 'WARN'     THEN 2
    ELSE 1
  END DESC,
  occurred_at DESC
);
