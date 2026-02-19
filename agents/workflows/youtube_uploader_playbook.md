# Workflow: YouTube Uploader (Manual Assisted)

Goal: produce a final upload-ready package and stop before final publish click.

## Inputs

- `content/<slug>/publish_package.md`
- `content/<slug>/seo_package.md`
- `content/<slug>/review_final.md`
- `content/<slug>/quality_gate.md`
- `content/<slug>/davinci_qc_checklist.md`
- `content/<slug>/affiliate_links.md`

## Outputs

- `content/<slug>/youtube_upload_payload.md`
- `content/<slug>/youtube_upload_checklist.md`
- `content/<slug>/youtube_publish_hold.md`

## Required sections in youtube_upload_payload.md

1. Final title
2. Final description
3. Tags + hashtags
4. Chapters/timestamps
5. Pinned comment
6. Category/audience settings
7. Affiliate links block (ready to paste in description)
8. Scheduling recommendation (America/Sao_Paulo)

## Hard gates

- Block if review is NO-GO.
- Block if quality gate is FAIL.
- Block if disclosures are missing.
- Block if `affiliate_links.md` is missing.
- Block if affiliate links include placeholders or unresolved tokens.
- Add explicit HOLD instruction: wait for Ray approval before Publish.
