# Lessons Learned

## 2026-02-18

### Affiliate link policy

- Pattern: treating all short links as unsafe blocks valid Amazon SiteStripe links.
- Rule: allow first-party `amzn.to`, block only external shorteners (`bit.ly`, `tinyurl`, etc.).

### Pipeline execution imports

- Pattern: CLI step modules failed with `ModuleNotFoundError` when run from tool entrypoint.
- Rule: ensure `BASE_DIR` is included in `sys.path` for script-mode execution.

### Secrets handling

- Pattern: copying secrets between systems through ad-hoc channels is error-prone.
- Rule: rotate secrets immediately after accidental exposure and avoid passing secrets in URLs.

### Execution discipline for non-trivial tasks

- Pattern: implementation without explicit plan/checklist increases drift and rework.
- Rule: for multi-step infra/orchestration changes, create/update `tasks/todo.md` first, then execute and verify against that checklist.

## 2026-02-19

### OpenClaw process storms

- Pattern: high-frequency polling implemented as repeated CLI subprocess calls (`openclaw browser`) can exhaust CPU and leave orphaned processes.
- Rule: prefer single `wait` calls over polling loops, serialize browser CLI calls with a lock, enforce command timeouts, and keep an explicit recovery script for orphan cleanup.

### Multi-repo drift (Rayviews vs OpenClaw)

- Pattern: treating two related repos as one workspace causes duplicated patches and conflicting agent behavior.
- Rule: declare source-of-truth repo at session start, enforce boundary file, and only sync the approved shared-file set via scripted sync.
