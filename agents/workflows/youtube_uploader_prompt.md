# Prompt Template: YouTube Uploader

Use this with OpenClaw:

openclaw agent --agent youtube_uploader --message "Read /Users/ray/Documents/Rayviews/agents/workflows/youtube_uploader_playbook.md and episode files for <slug>. Generate: (1) youtube_upload_payload.md, (2) youtube_upload_checklist.md, (3) youtube_publish_hold.md in /Users/ray/Documents/Rayviews/content/<slug>/. Stop before publish and require Ray approval. Block if affiliate links are missing or placeholders."
