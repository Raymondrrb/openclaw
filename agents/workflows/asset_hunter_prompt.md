# Prompt Template: Asset Hunter

Use this with OpenClaw:

openclaw agent --agent asset_hunter --message "Read <script_path> and create an asset pack for <slug>. Output files: content/<slug>/shot_list.md, content/<slug>/asset_manifest.md. For each scene, provide approved asset candidates with source_url, license_or_usage_note, and local_path. Then run /usr/bin/python3 /Users/ray/Documents/Rayviews/tools/build_video_safe_assets.py --content-dir /Users/ray/Documents/Rayviews/content/<slug> --overwrite and prefer assets/video_safe/\*\_16x9.jpg in shot list. Flag uncertain assets as REVIEW_REQUIRED."

Example:
openclaw agent --agent asset_hunter --message "Read /Users/ray/Documents/Rayviews/content/open_ear_top5_2026-02-07/script_long.md and create an asset pack for open_ear_top5_2026-02-07. Output files: /Users/ray/Documents/Rayviews/content/open_ear_top5_2026-02-07/shot_list.md and /Users/ray/Documents/Rayviews/content/open_ear_top5_2026-02-07/asset_manifest.md."
