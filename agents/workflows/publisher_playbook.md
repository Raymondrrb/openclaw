# Workflow: Publisher

Goal: prepare a safe, monetization-ready upload package for YouTube Studio.

## Inputs

- `content/<slug>/script_long.md`
- `content/<slug>/seo_package.md`
- `content/<slug>/review_final.md`
- `content/<slug>/quality_gate.md`
- `content/<slug>/davinci_qc_checklist.md`
- `content/<slug>/davinci_export_preset.md`
- `content/<slug>/affiliate_links.md`

## Outputs

- `content/<slug>/publish_package.md`
- `content/<slug>/upload_checklist.md`
- `content/<slug>/youtube_studio_steps.md`

## Required sections in publish_package.md

1. Final title (chosen from SEO package)
2. Final description (with affiliate + AI disclosure)
3. Tags and hashtags
4. Chapters/timestamps
5. Pinned comment draft
6. Affiliate links block (one verified link per ranked product)
7. Scheduling recommendation (America/Sao_Paulo)
8. Risk flags and mitigations

## Hard gates

- If review is NO-GO, stop and output blockers only.
- If quality gate is FAIL, stop and output blockers only.
- If disclosure is missing, fail the package.
- If `affiliate_links.md` is missing, fail the package.
- If any affiliate URL is placeholder (e.g., `[ADD_LINK]`, `TODO`, `TBD`), fail the package.
- If affiliate links are fewer than ranked products, fail the package.
