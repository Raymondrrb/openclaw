# Workflow: Asset Sourcing

Goal: Build an edit-ready asset pack with clear source and usage notes.

Output files (per video slug):

- content/<slug>/asset_manifest.md
- content/<slug>/shot_list.md
- content/<slug>/assets/

Source priority:

1. Official product pages / brand press media
2. Amazon listing images (for review/commentary context)
3. Licensed stock (Pexels/Pixabay/Storyblocks etc.)
4. AI-generated supporting visuals (clearly tagged)

Required fields per asset:

- asset_id
- scene_ref (timestamp or section)
- asset_type (image/video)
- local_path
- source_url
- license_or_usage_note
- claim_supported

Steps:

1. Read script and map scenes to required visuals.
2. Build shot_list.md (one line per scene).
3. Collect candidate assets by source priority.
4. Save files under content/<slug>/assets/ with stable names.
5. Write asset_manifest.md with required fields.
6. Flag any uncertain license items as REVIEW_REQUIRED.
7. Hand off to editor with only APPROVED assets.

Hard rules:

- No copyrighted clips/music without explicit license.
- No unknown-source media in final export.
- Keep screenshot references factual and non-deceptive.
- Do not use full-page vertical screenshots as primary visual assets.
- Primary stills must be video-safe (16:9) before handoff.

Quality gates (must pass):

1. Prefer product hero media over search/listing screenshots.
2. Minimum recommended still size: 1280x720 before transforms.
3. If source is portrait/narrow, generate 16:9 replacements via:
   - `/usr/bin/python3 /Users/ray/Documents/Rayviews/tools/build_video_safe_assets.py --content-dir <episode_dir> --overwrite`
4. Final shot list should reference `assets/video_safe/*_16x9.jpg` whenever possible.
