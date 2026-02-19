# Tasks TODO

## Current

- [x] Mapear pontos de spawn OpenClaw e identificar riscos de storm/zombie.
- [x] Reduzir polling agressivo de ChatGPT UI (OpenClaw browser) para espera única com timeout.
- [x] Serializar chamadas `openclaw browser` com lock local para evitar concorrência acidental.
- [x] Criar script de recuperação operacional para limpar processos OpenClaw órfãos.
- [x] Documentar runbook curto para o Claude Code não repetir esse padrão.
- [x] Validar com testes/smoke local e registrar resultados.

## Review

- Root cause principal confirmado: `tools/chatgpt_ui.py` fazia polling por subprocesso `openclaw browser` em loop (alto churn quando múltiplas rotinas rodavam).
- Hardening aplicado: lock local + throttle mínimo + timeout explícito por comando OpenClaw browser.
- Espera de resposta no ChatGPT UI agora usa `wait --fn` único (com fallback compatível).
- `tools/pipeline.py` agora faz preflight de pressão de processos OpenClaw e bloqueia execução em nível crítico.
- Script operacional novo `tools/openclaw_recover.sh` para diagnóstico/recuperação de processos órfãos.
- Runbook atualizado no README com comandos de recuperação e regras para evitar regressão.
- Testes executados: `python3 -m unittest tests/test_chatgpt_ui.py -v`, `python3 -m unittest tests.test_pipeline.TestEnsureQualityGates -v`, `python3 -m unittest tests.test_pipeline.TestOpenClawProcessGuard -v`.
