.PHONY: doctor health replay check-contract worker worker-test stop stop_force test stress clean logs quarantine purge_spool cockpit

# --- Morning routine ---
doctor:
	python3 rayvault_cli.py doctor

health:
	python3 rayvault_cli.py health

replay:
	python3 rayvault_cli.py replay-spool

check-contract:
	python3 rayvault_cli.py check-contract

# --- Worker (caffeinate keeps Mac awake during processing) ---
worker:
	caffeinate -dimsu python3 rayvault_cli.py worker

# Short lease for kill-test: stale appears in ~4min instead of ~30min
worker-test:
	RAYVAULT_LEASE_MINUTES=2 RAYVAULT_HEARTBEAT_INTERVAL_SEC=30 RAYVAULT_HEARTBEAT_TIMEOUT_SEC=10 \
		caffeinate -dimsu python3 rayvault_cli.py worker

# --- Stop worker safely (PID file, SIGTERM) ---
stop:
	python3 rayvault_cli.py stop

stop_force:
	python3 rayvault_cli.py stop --force

# --- Testing ---
test:
	python3 tools/test_run_manager.py -v

stress:
	python3 tools/stress_test_claim.py

# --- Observability ---
# Quick Cockpit: fleet status from pipeline_runs (no incidents view needed)
cockpit:
	@echo "=== Fleet Cockpit ==="
	@echo "Run in Supabase SQL Editor:"
	@echo ""
	@echo "SELECT worker_state, status, count(*) AS total,"
	@echo "  sum(CASE WHEN last_heartbeat_at IS NULL THEN 1 ELSE 0 END) AS no_hb,"
	@echo "  round(avg(CASE WHEN worker_state='active' THEN last_heartbeat_latency_ms END)) AS avg_lat_ms,"
	@echo "  max(last_heartbeat_at) AS last_hb_max"
	@echo "FROM pipeline_runs"
	@echo "WHERE status IN ('running','approved','waiting_approval')"
	@echo "GROUP BY worker_state, status"
	@echo "ORDER BY worker_state, status;"
	@echo ""
	@echo "=== Open Incidents ==="
	@echo "SELECT * FROM incidents_critical_open ORDER BY last_heartbeat_at DESC NULLS LAST LIMIT 50;"

# --- Maintenance ---
# Safe: only cleans temp files and old logs (never touches spool)
clean:
	find state/tmp -type f -mtime +1 -delete 2>/dev/null || true
	find state/logs -type f -mtime +30 -delete 2>/dev/null || true

logs:
	ls -lt state/logs 2>/dev/null | head -n 30 || echo "No logs directory"

# Show quarantined spool files
quarantine:
	@echo "=== Quarantined spool files ==="
	@ls -la spool/quarantine/ 2>/dev/null || echo "No quarantined files"
	@echo ""
	@echo "=== Bad spool files ==="
	@ls -la spool/bad/ 2>/dev/null || echo "No bad files"

# DANGEROUS: purge all spool files. Requires confirm=YES.
purge_spool:
	@if [ "$(confirm)" != "YES" ]; then \
		echo "Refusing. Use: make purge_spool confirm=YES"; exit 1; \
	fi
	rm -f spool/*.json spool/quarantine/*.json spool/bad/*.json 2>/dev/null || true
	@echo "Spool purged."
