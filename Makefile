.PHONY: doctor health replay check-contract worker stop stop_force test stress clean logs quarantine purge_spool

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
