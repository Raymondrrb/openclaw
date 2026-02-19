#!/usr/bin/env python3
"""
Upload a video to YouTube using YouTube Data API v3.

Requirements:
  pip install google-api-python-client google-auth-oauthlib google-auth-httplib2

Usage:
  python3 tools/youtube_upload_api.py \
    --client-secrets /abs/path/client_secret.json \
    --video-file /abs/path/video.mp4 \
    --metadata-json /abs/path/youtube_upload_metadata.json \
    --thumbnail /abs/path/thumb.jpg \
    --privacy-status private
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Dict, List

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def load_metadata(path: Path) -> Dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    required = ["title", "description", "tags"]
    for key in required:
        if key not in data:
            raise ValueError(f"Missing required metadata field: {key}")
    if not isinstance(data["tags"], list):
        raise ValueError("metadata.tags must be a JSON array")
    return data


def get_youtube_service(client_secrets: Path, token_path: Path):
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds)


def upload_video(
    youtube,
    video_file: Path,
    title: str,
    description: str,
    tags: List[str],
    category_id: str,
    privacy_status: str,
):
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(video_file), chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        _, response = request.next_chunk()
    return response


def upload_thumbnail(youtube, video_id: str, thumbnail: Path):
    media = MediaFileUpload(str(thumbnail))
    return youtube.thumbnails().set(videoId=video_id, media_body=media).execute()


def main() -> int:
    parser = argparse.ArgumentParser(description="YouTube uploader via Data API.")
    parser.add_argument("--client-secrets", required=True, help="Path to OAuth client secrets JSON")
    parser.add_argument("--video-file", required=True, help="Path to rendered MP4/MOV")
    parser.add_argument("--metadata-json", required=True, help="Path to metadata JSON")
    parser.add_argument("--token-file", default="", help="Path to cached OAuth token JSON")
    parser.add_argument("--thumbnail", default="", help="Optional thumbnail image path")
    parser.add_argument("--privacy-status", default="private", choices=["private", "public", "unlisted"])
    parser.add_argument("--category-id", default="28", help="YouTube category ID (default 28: Science & Tech)")
    args = parser.parse_args()

    client_secrets = Path(args.client_secrets).expanduser()
    video_file = Path(args.video_file).expanduser()
    metadata_json = Path(args.metadata_json).expanduser()
    token_file = Path(args.token_file).expanduser() if args.token_file else metadata_json.with_name("youtube_token.json")
    thumbnail = Path(args.thumbnail).expanduser() if args.thumbnail else None

    if not client_secrets.exists():
        raise SystemExit(f"Client secrets not found: {client_secrets}")
    if not video_file.exists():
        raise SystemExit(f"Video file not found: {video_file}")
    if not metadata_json.exists():
        raise SystemExit(f"Metadata file not found: {metadata_json}")

    meta = load_metadata(metadata_json)
    youtube = get_youtube_service(client_secrets, token_file)

    try:
        response = upload_video(
            youtube=youtube,
            video_file=video_file,
            title=meta["title"],
            description=meta["description"],
            tags=meta["tags"],
            category_id=args.category_id,
            privacy_status=args.privacy_status,
        )
    except HttpError as exc:
        raise SystemExit(f"YouTube upload failed: {exc}") from exc

    video_id = response.get("id")
    out = {
        "ok": bool(video_id),
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else "",
        "privacy_status": args.privacy_status,
    }

    if video_id and thumbnail and thumbnail.exists():
        try:
            upload_thumbnail(youtube, video_id, thumbnail)
            out["thumbnail_set"] = True
        except HttpError as exc:
            out["thumbnail_set"] = False
            out["thumbnail_error"] = str(exc)
    else:
        out["thumbnail_set"] = False

    report_path = metadata_json.with_name("youtube_upload_report.json")
    _tmp = report_path.with_suffix(".tmp")
    _payload = json.dumps(out, indent=2).encode("utf-8")
    _fd = os.open(str(_tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(_fd, _payload)
        os.fsync(_fd)
    finally:
        os.close(_fd)
    os.replace(str(_tmp), str(report_path))
    print(json.dumps(out, indent=2))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

