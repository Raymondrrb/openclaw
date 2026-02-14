# RayVault Operator Guide (v0.1)

## 1) Setup rapido
- Copie `.env.example` -> `.env`
- Garanta:
  - `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`
  - `RAYVAULT_WORKER_ID`
  - `DZINE_CREDIT_PRICE_USD` (ex: 1.50)
  - `USD_BRL` (ex: 5.00) [opcional, fixo]
- Dependencias locais:
  - `ffprobe` disponivel no PATH (via ffmpeg)

## 2) Boot do sistema
```bash
make worker WID=Mac-Ray-01
```

## 3) Batismo (Primeiro voo / pos-deploy)

Duas camadas — A valida sem queimar creditos, B valida recuperacao real.

### Batismo A (dry — sem worker)
Valida infra, index, skip, orfaos. Nao inicia worker.
```bash
make baptism
```

### Batismo B (full — pos-kill)
Rode depois de ter feito um ciclo completo com kill test:
1. `make worker` — deixe processar
2. `kill -TERM <PID>` — testa shutdown gracioso
3. `make worker` — retoma e completa
4. `kill -9 <PID>` — testa crash
5. `make worker` — retoma via checkpoint
6. Valida:
```bash
make baptism-full CONFIRM=YES
```

O script verifica: checkpoints, spool, PID stale, index, skip, orfaos.
Relatorio salvo em `state/baptism/`.

### Ritual rapido (5 min)
```bash
make doctor          # diagnostico geral
make status          # preflight + QC
```

## 4) Quando der alerta no Telegram
- **STALE WORKER**
  - `make doctor`
  - se persistir: `make stop` + `make worker`
- **LOST LOCK**
  - verifique colisao de worker_id e PIDs
- **CONTRACT FAIL**
  - `python3 -m rayvault.cli check-contract`

## 5) Pre-edit Validation (antes do Resolve)

Gera CSV da timeline com Start/End acumulado e status de videos:

```bash
make timeline ID=RAY-99
```

Voce deve ver:
- segmentos READY/MISSING
- drift por segmento (se habilitado no report)
- duracao total

## 6) Auditoria de ativos (custodia)
- Relatorio financeiro + qualidade + creditos:
```bash
make report ID=RAY-99
```

- Orfaos (arquivos em /final que nao estao no index):
```bash
make orphans
```

## 7) Limpeza
- segura:
```bash
make clean
```

- agressiva (cuidado):
```bash
make clean-hard
```

- quarentena de orfaos (>6h):
```bash
make clean-zombies
```

- delete de orfaos antigos (>48h, perigoso):
```bash
make clean-zombies-delete
```

## 8) Worker States

| State | Meaning | Action |
|-------|---------|--------|
| `active` | Processing normally | None |
| `waiting` | Gate active (awaiting human approval) | Check Telegram / dashboard |
| `panic` | Worker stopped for safety | Investigate before resuming |
| `idle` | No active processing | Normal between runs |

## 9) Panic Taxonomy

| Panic | Cause | Action |
|-------|-------|--------|
| `panic_lost_lock` | Another worker claimed the run, or lease expired | Check for duplicate workers / short lease |
| `panic_heartbeat_uncertain` | Network/Supabase unreachable after 3 retries | Check Wi-Fi/router; look at `last_heartbeat_latency_ms`; wait 2-5 min |
| `panic_browser_frozen` | Playwright/Dzine not responding | Restart browser; check RAM/GPU; resume via `claim_next` |
| `panic_integrity_failure` | Irreconcilable evidence conflict | Open dashboard and decide (approve/refetch/abort) |
| `panic_voice_contract_drift` | Audio duration can't match target after repair loop | Check voice script segment durations; may need text edit |
| `panic_dzine_ui_failure` | Dzine render failed or probe rejected video | Check Dzine credits; inspect staging dir for partial exports |

## 10) Telegram Alert Buttons

| Button | Effect |
|--------|--------|
| **Approve** | Sets status=`approved`, worker resumes pipeline |
| **Refetch** | Sets status=`running` + `force_refetch:true`, worker re-collects evidence |
| **Abort** | Sets status=`aborted`, run is killed |
| **Unlock** | Force-clears lock via `rpc_force_unlock_run` |

## 11) Checkpoint Recovery

If the worker restarts:
1. `claim_next` automatically recovers the worker's own active run
2. Checkpoint file (`checkpoints/<run_id>.json`) tells it which stages are done
3. Worker skips completed stages and resumes from where it stopped

If checkpoint file is lost:
- Worker re-runs all stages (idempotent — stages check for existing artifacts)

## 12) Critical Rule

If there's a conflict between Tier 4/5 sources on **critical claims** (price, voltage, compatibility, model_id/ean):

> The system MUST gate (pause) before publishing anything.

Never override without reading the evidence diff in the dashboard.

## 13) Disaster Recovery

### Cenario 1 — Worker morreu (kill -9) no meio
```bash
make status                    # confere missing e warnings
make maintenance               # refresh index + detectar orfaos (dry-run)
make worker                    # deve SKIP nos prontos e completar
```

### Cenario 2 — Index parece estranho (paths invalidos / meta ausente)
```bash
python3 scripts/video_index_refresh.py --state-dir state --force
# se tiver legado sem sha8 no nome:
python3 scripts/video_index_refresh.py --state-dir state --force --allow-missing-sha8
make status
```

### Cenario 3 — Muitos probe_failed seguidos
```bash
ffprobe -version               # verifica se ffprobe esta acessivel
make maintenance               # re-probe (se for corrida de IO, resolve)
# se persistir: o problema e export/codec do Dzine, nao bug do RayVault
```

### Checklist pos-recovery
```bash
make baptism                   # Level A: valida tudo sem worker
make baptism-full CONFIRM=YES  # Level B: valida checkpoints + spool + PID
```

## 14) Common Commands

```bash
# Start worker (continuous)
make worker WID=Mac-Ray-01

# Single run mode
python3 tools/worker.py --worker-id Mac-Ray-01 --once

# Health + replay
make doctor

# Doctor report (credits + finance + quality)
make report

# Timeline CSV (pre-Resolve validation)
make timeline

# Orphan audit
make orphans

# Preflight (credits readiness)
make preflight

# Force unlock (emergency only)
python3 tools/rayvault_unlock.py --run <uuid> --operator ray --force --reason "stuck"

# Quick status (preflight + QC)
make status

# Baptism (pre-first-run validation)
make baptism
make baptism-full CONFIRM=YES

# Maintenance (safe: refresh + dry-run cleanup + report)
make maintenance

# Run tests
make test
```
