#!/usr/bin/env python3
"""YouTube Video Verifier — external verifier for RayVault verify_visibility.

Checks a YouTube video's processing status, privacy, and basic metadata
using the YouTube Data API v3.

Requirements:
    pip install google-api-python-client google-auth google-auth-oauthlib

Auth:
    1. Create OAuth Client in Google Cloud Console
    2. Download client_secret.json
    3. First run opens browser login, stores token

Usage:
    python3 tools/yt_verify.py VIDEO_ID
    python3 tools/yt_verify.py VIDEO_ID --client-secret path/to/client_secret.json

Env:
    YOUTUBE_CLIENT_SECRET: path to client_secret.json
    YOUTUBE_TOKEN_PATH: path to stored OAuth token
    RAY_YT_VERIFY_CMD='python3 tools/yt_verify.py {video_id}'

Output (JSON to stdout):
    {"ok": true, "privacy": "unlisted", "processing": "succeeded", "claims": []}

Note: YouTube Data API v3 does NOT expose Content ID claims for normal
channels. Claims are always [] (safe audio mode) or ["UNKNOWN_API_LIMIT"].
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


def _try_import():
    """Import Google API client libraries, with clear error on missing."""
    try:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        return build, HttpError, Credentials, InstalledAppFlow, Request
    except ImportError as e:
        result = {
            "ok": False,
            "error": {
                "code": "MISSING_DEPENDENCY",
                "detail": f"pip install google-api-python-client google-auth google-auth-oauthlib ({e})",
            },
        }
        print(json.dumps(result))
        sys.exit(2)


SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


def load_creds(client_secret: Path, token_path: Path):
    _, _, Credentials, InstalledAppFlow, Request = _try_import()

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(client_secret), SCOPES
            )
            creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def normalize_privacy(status: str | None) -> str:
    if not status:
        return "unknown"
    s = status.lower()
    if s in ("public", "unlisted", "private"):
        return s
    return "unknown"


def normalize_processing(proc: str | None) -> str:
    if not proc:
        return "unknown"
    s = proc.lower()
    if s in ("processing", "succeeded", "failed"):
        return s
    return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="YouTube Video Verifier for RayVault",
    )
    ap.add_argument("video_id")
    ap.add_argument(
        "--client-secret",
        default=os.getenv("YOUTUBE_CLIENT_SECRET", "client_secret.json"),
    )
    ap.add_argument(
        "--token",
        default=os.getenv(
            "YOUTUBE_TOKEN_PATH",
            str(Path.home() / ".rayvault" / "youtube_token.json"),
        ),
    )
    ap.add_argument("--safe-audio", action="store_true", default=True)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--backoff", type=float, default=1.5)
    args = ap.parse_args()

    build, HttpError, _, _, _ = _try_import()

    client_secret = Path(args.client_secret).resolve()
    token_path = Path(args.token).resolve()

    if not client_secret.exists():
        result = {
            "ok": False,
            "error": {"code": "MISSING_CLIENT_SECRET", "detail": str(client_secret)},
        }
        print(json.dumps(result))
        return 2

    try:
        creds = load_creds(client_secret, token_path)
        youtube = build("youtube", "v3", credentials=creds)

        last_err = None
        for i in range(args.retries):
            try:
                resp = youtube.videos().list(
                    part="status,processingDetails,contentDetails,snippet",
                    id=args.video_id,
                    maxResults=1,
                ).execute()
                items = resp.get("items", [])
                if not items:
                    result = {"ok": False, "error": {"code": "VIDEO_NOT_FOUND"}}
                    print(json.dumps(result))
                    return 2

                v = items[0]
                privacy = normalize_privacy(
                    v.get("status", {}).get("privacyStatus")
                )
                processing = normalize_processing(
                    v.get("processingDetails", {}).get("processingStatus")
                )

                # Data API can't see Content ID claims for normal channels
                claims = [] if args.safe_audio else ["UNKNOWN_API_LIMIT"]

                result = {
                    "ok": True,
                    "privacy": privacy,
                    "processing": processing,
                    "claims": claims,
                }
                print(json.dumps(result))
                return 0

            except HttpError as e:
                last_err = str(e)
                time.sleep(args.backoff ** i)

        result = {
            "ok": False,
            "error": {"code": "YOUTUBE_HTTP_ERROR", "detail": last_err},
        }
        print(json.dumps(result))
        return 2

    except Exception as e:
        result = {
            "ok": False,
            "error": {"code": "VERIFY_TOOL_EXCEPTION", "detail": str(e)[:500]},
        }
        print(json.dumps(result))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
