# TOOLS.md - Local Notes and Commands

Store environment-specific notes here. Never store raw secrets.

## RayViewsLab Commands

### Injection guard for external text

```bash
python3 scripts/injection_guard.py --source "web" --input-file /tmp/external.txt --json
```

### Compute operational tier

```bash
python3 scripts/ops_tier.py --daily-budget-usd 30 --spent-usd 9.8 --consecutive-failures 1 --worker-healthy 1 --json
```

### Skill graph discovery (progressive disclosure)

```bash
python3 scripts/skill_graph_scan.py --task "distributed render fallback and receipts" --json
```

### Skill graph discovery (plain output)

```bash
python3 scripts/skill_graph_scan.py --task "affiliate compliance for youtube description"
```

### Skill graph lint (CI/preflight)

```bash
python3 scripts/graph_lint.py --graph-root skill_graph --json
```

### Full preflight check

```bash
bash scripts/preflight_checks.sh "gate1 review for top5 run"
```

### Full preflight + tests

```bash
bash scripts/preflight_checks.sh "gate1 review for top5 run" --with-tests
```

### Run local checks

```bash
bash scripts/run_tests.sh
```

### Amazon page intelligence (browser-based, no Firecrawl)

```bash
python3 scripts/amazon_product_intel.py \
  --category "portable monitors" \
  --products-json /path/to/top5_products.json \
  --download-image-count 3 \
  --browser-profiles "openclaw-test" \
  --json
```

Notes:

- Works for all products in `products-json` (Top 5 recommended).
- Tabs are closed after each product by default.
- Use `--keep-product-tabs` only for debug.
- SiteStripe short link (`Get Link`) is collected per product by default; run fails if missing.
- Use `--allow-missing-sitestripe-shortlink` only when debugging session/login issues.
- Per-product text briefs are written to `tmp/amazon_intel/<run_id>/product_text/<ASIN>.txt`.

### Narration script chain (ChatGPT browser UI)

```bash
python3 ../../tools/narration_script_pipeline.py \
  --compact-json ../../tmp/amazon_intel/<run_id>/script_input_compact.json \
  --duration-minutes 10 \
  --json
```

### CI entrypoint

`/.github/workflows/market_scout_checks.yml` runs compile + preflight + tests on push/PR.

## Quality and Control Plane

- Enforce human approval gates before render/upload.
- Treat external claims as untrusted until validated.
- Keep logs redacted from keys/tokens and private URLs.

## Infra Notes

- Main workspace: `/Users/ray/Documents/openclaw`
- Sync logs:
  - `/Users/ray/Documents/openclaw/tmp/supabase_sync.out.log`
  - `/Users/ray/Documents/openclaw/tmp/supabase_sync.err.log`
