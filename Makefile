.PHONY: health replay doctor stress test clean logs quarantine purge_spool worker

# --- Morning routine ---
doctor:
	python3 -m tools.lib.doctor --all

health:
	python3 -m tools.lib.doctor --health

replay:
	python3 -m tools.lib.doctor --replay-spool

# --- Worker ---
worker:
	python3 tools/worker.py --worker-id Mac-Ray-01

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
