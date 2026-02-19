# Workflow: Affiliate Linker

Goal: produce valid Amazon affiliate links for every ranked product before publish artifacts are created.

## Inputs

- `content/<slug>/research.md`
- `content/<slug>/script_long.md` (optional, for ranked-product cross-check)
- `content/<slug>/seo_package.md` (optional, for description sync)

## Output

- `content/<slug>/affiliate_links.md`

## Required output format

1. Timestamp (`Generated at`)
2. Product count target
3. Markdown table with columns:
   - `product`
   - `listing_url`
   - `affiliate_url`
   - `source_method` (`SiteStripe` or `Amazon Associates extension`)
   - `status` (`OK` or `BLOCKER`)
4. `Blockers` section (only when any row is not `OK`)
5. Paste-ready block for YouTube description

## Operating rules

- Use Amazon US links only.
- Use OpenClaw managed browser session as primary (no relay dependency).
- Preflight: verify Amazon Associates is logged in on this managed browser profile.
- If not logged in, write `LOGIN_REQUIRED` in `Blockers` and stop.
- Prefer SiteStripe or Associates links from the exact product listing URL.
- For each product, run exact sequence:
  - open listing URL in a new tab
  - click yellow `Get link` on SiteStripe
  - capture URL from popup and validate `tag=` exists
  - save row in output table
  - close the product tab immediately
- For slow pages/popups, use browser actions with `timeoutMs=60000`.
- If short link generation fails, use full affiliate URL.
- Never invent links.

## Hard gates

- Fail if fewer affiliate links than ranked products.
- Fail if any URL is placeholder (`[ADD_LINK]`, `TODO`, `TBD`).
- Fail if any affiliate URL is not a URL.
- If blocked by auth/session/captcha, output blockers with exact next action and stop.
