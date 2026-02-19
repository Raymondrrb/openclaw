# HEARTBEAT.md - YouTube Uploader

On heartbeat:

1. Find latest episode folder in `/Users/ray/Documents/Rayviews/content/`.
2. If `publish_package.md` exists and `youtube_upload_payload.md` is missing, generate upload payload.
3. If blockers exist (NO-GO/FAIL), write `youtube_upload_blockers.md`.
4. If nothing actionable, reply `HEARTBEAT_OK`.
