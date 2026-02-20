# New Project (RayViewsLab Ops Workspace)

This workspace contains the `market_scout` agent runtime contract, policy docs, and local safety/quality tooling.

## Main area

- `agents/market_scout/AGENTS.md`
- `agents/market_scout/skill_graph/`
- `agents/market_scout/scripts/`

## Quality checks

Run from repo root:

```bash
bash agents/market_scout/scripts/preflight_checks.sh "gate1 review for top5 pipeline" --with-tests
```

## CI

GitHub Actions workflow:

- `.github/workflows/market_scout_checks.yml`

It runs compile checks + skill graph preflight + Python unit tests.

## Mission Control (visual dashboard)

Run a local visual panel to see OpenClaw agents, heartbeat state, channels, and recent activity:

```bash
python3 tools/mission_control.py
```

Then open:

```text
http://127.0.0.1:8788
```

What it shows:

- Office grid with one card per agent (`active`, `scheduled`, `idle`, `cold`, `error`)
- Gateway/channel health KPIs
- Recent session activity feed (model, token usage, recency)
- Last Supabase sync snapshot if `tmp/supabase_sync.out.log` exists
- Pipeline control board (manual stages): gateway start/restart/stop/probe, graph lint, skill scan, ops tier, injection guard, preflight, tests
- Firecrawl stages (search/scrape) from the same board when `FIRECRAWL_API_KEY` is configured
- Job history with output/error log paths under `tmp/mission_control_jobs/`

## Firecrawl adapter (optional)

Set key:

```bash
export FIRECRAWL_API_KEY=...
```

Quick examples:

```bash
python3 agents/market_scout/scripts/firecrawl_adapter.py search --query "best portable monitors reviews" --json
python3 agents/market_scout/scripts/firecrawl_adapter.py scrape --url "https://www.amazon.com" --allow-domain amazon.com --json
```

Safety defaults:

- blocks localhost/private IP scrape targets
- enforces `http/https` only
- supports allowlist via `--allow-domain`

## Deep Amazon product intelligence (OpenClaw Browser)

For better scripts and visual planning, collect product-page evidence (features + review signals + image refs) directly from Amazon page UI via OpenClaw Browser:

```bash
python3 agents/market_scout/scripts/amazon_product_intel.py \
  --category "portable monitors" \
  --products-json tmp/top5_products.json \
  --out-dir tmp/amazon_intel \
  --download-image-count 3 \
  --browser-profiles "openclaw-test" \
  --json
```

or with direct URLs:

```bash
python3 agents/market_scout/scripts/amazon_product_intel.py \
  --category "portable monitors" \
  --product-url "https://www.amazon.com/dp/B0AAAAAA01" \
  --product-url "https://www.amazon.com/dp/B0AAAAAA02" \
  --product-url "https://www.amazon.com/dp/B0AAAAAA03" \
  --product-url "https://www.amazon.com/dp/B0AAAAAA04" \
  --product-url "https://www.amazon.com/dp/B0AAAAAA05" \
  --out-dir tmp/amazon_intel \
  --download-image-count 3 \
  --json
```

What this produces:

- `tmp/amazon_intel/<run_id>/amazon_product_intel.json` (full extraction contract)
- `tmp/amazon_intel/<run_id>/script_input_compact.json` (token-efficient script brief)
- `tmp/amazon_intel/<run_id>/product_text/<ASIN>.txt` (human-readable per-product brief)
- `tmp/amazon_intel/<run_id>/assets/ref/*` (multiple downloaded image refs per product)
- `agents/market_scout/memory/amazon_intel/<YYYY-MM-DD>/*.md` (Obsidian-ready notes)
- `agents/market_scout/memory/amazon_intel/learning_loop.jsonl` (structured learning loop)

Affiliate link behavior:

- For each product, collector tries SiteStripe `Get Link` and stores `affiliate.sitestripe_short_url` (`amzn.to/...`).
- Default is strict: product fails if short link is missing.
- To debug without blocking, pass `--allow-missing-sitestripe-shortlink`.

Behavior defaults:

- Cleans stale Amazon tabs before run (to reduce browser instability)
- Scrolls each product page to reach review areas before extraction
- Captures buyer sentiment (positive + critical) and evidence snippets
- Closes Amazon tab after each product (use `--keep-product-tabs` only for debugging)
- If Amazon shows robot check/captcha, run once with `--wait-on-robot-check-sec 90`, solve manually in the opened page, then extraction resumes

In Mission Control, run the stage `Amazon Product Intel` to execute the same flow from the dashboard.

## Narration script chain (ChatGPT UI -> Claude review -> specialist review)

Use the compact intel pack to create spoken narration text via your logged-in ChatGPT browser session:

```bash
python3 tools/narration_script_pipeline.py \
  --compact-json tmp/amazon_intel/<run_id>/script_input_compact.json \
  --run-dir tmp/script_pipeline \
  --duration-minutes 10 \
  --json
```

Outputs include:

- `00_chatgpt_prompt.txt` (exact prompt used in browser)
- `01_chatgpt_draft_narration.md` (spoken script draft)
- `02_claude_review_prompt.txt` (prompt to review/refine in Claude)
- `03_specialist_review_contract.json` (agent checklist for final script QA)

This keeps script generation strictly on ChatGPT browser UI (no API generation), then passes through layered review.
