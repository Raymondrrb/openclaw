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

## 3) Ritual de 5 minutos (Primeiro voo / pos-deploy)
1. Rodar diagnostico:
```bash
make doctor
```

2. Abrir cockpit (SQL view) e observar 5 min:
   - `incidents_last_24h`
   - `incidents_critical_open`

3. Batismo de fogo:
   - SIGTERM (shutdown limpo): `make stop`
   - KILL -9 (infra/stale): `kill -9 <PID>`
   - Confirmar que `is_stale = true` aparece quando apropriado.

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

## 13) Common Commands

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

# Run tests
make test
```
