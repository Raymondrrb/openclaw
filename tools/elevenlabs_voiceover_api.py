#!/usr/bin/env python3
"""
Generate episode voiceover chunks with ElevenLabs API using a named voice.

Usage example:
  ELEVENLABS_API_KEY=... \
  python3 tools/elevenlabs_voiceover_api.py \
    --script "<PROJECT_ROOT>/content/open_ear_top5_2026-02-07/script_long.md" \
    --voice-name "Thomas Louis" \
    --output-dir "<PROJECT_ROOT>/content/open_ear_top5_2026-02-07/voiceover_ray1_v2" \
    --report "<PROJECT_ROOT>/content/open_ear_top5_2026-02-07/voiceover_ray1_v2_report.md"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


VOICE_API_BASE = "https://api.elevenlabs.io/v1"


@dataclass
class ChunkResult:
    key: str
    filename: str
    status: str
    notes: str
    bytes_size: int = 0
    duration_sec: float = 0.0
    mean_db: float = 0.0
    peak_db: float = 0.0


def api_get(path: str, api_key: str) -> dict:
    req = Request(
        f"{VOICE_API_BASE}{path}",
        headers={"xi-api-key": api_key},
        method="GET",
    )
    with urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_post_tts(
    voice_id: str,
    text: str,
    api_key: str,
    model_id: str,
    stability: float,
    similarity_boost: float,
    style: float,
    speaker_boost: bool,
) -> bytes:
    body = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "style": style,
            "use_speaker_boost": speaker_boost,
        },
    }
    raw = json.dumps(body).encode("utf-8")
    req = Request(
        f"{VOICE_API_BASE}/text-to-speech/{voice_id}",
        data=raw,
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )
    with urlopen(req, timeout=120) as resp:
        return resp.read()


def resolve_voice_id(api_key: str, voice_name: str) -> str:
    payload = api_get("/voices", api_key)
    voices = payload.get("voices", [])
    exact = None
    ci_match = None
    for v in voices:
        name = (v.get("name") or "").strip()
        if name == voice_name:
            exact = v
            break
        if name.lower() == voice_name.lower():
            ci_match = v
    chosen = exact or ci_match
    if not chosen:
        available = ", ".join(sorted(v.get("name", "") for v in voices if v.get("name")))
        raise ValueError(f'Voice "{voice_name}" not found. Available voices: {available}')
    return chosen["voice_id"]


def normalize_text(md: str) -> str:
    text = md
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = text.replace("**", "")
    text = re.sub(r"^\s*###\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def slug(value: str, max_len: int = 32) -> str:
    if not value:
        return "scene"
    x = value.lower().strip()
    x = re.sub(r"[^a-z0-9]+", "_", x)
    x = re.sub(r"_+", "_", x).strip("_")
    if not x:
        x = "scene"
    return x[:max_len].strip("_")


def classify_heading(title: str) -> str:
    if not title:
        return "other"
    t = title.lower()
    if "hook" in t or "intro" in t:
        return "hook"
    if "criteria" in t or "methodology" in t:
        return "criteria"
    if "cta" in t or "call to action" in t:
        return "cta"
    if "disclosure" in t or "description block" in t:
        return "disclosure"
    if "recap" in t or "summary" in t or "verdict" in t:
        return "recap"
    if re.search(r"#\s*\d+\b", title) or re.search(r"\btop\s*\d+\b", t) or re.search(r"\brank\b", t):
        return "rank"
    return "other"


def build_section_plan(script_text: str) -> List[Tuple[str, str, str]]:
    lines = script_text.splitlines()
    heading_re = re.compile(r"^\s*##+\s*(.+?)\s*$")
    starts: List[Tuple[int, str]] = []

    for idx, line in enumerate(lines):
        m = heading_re.search(line)
        if m:
            starts.append((idx, m.group(1).strip()))

    if not starts:
        body = normalize_text(script_text)
        if not body:
            return []
        return [("full_script", "vo_01_full_script.mp3", body)]

    sections: List[Dict[str, str]] = []
    for i, (start_idx, title) in enumerate(starts):
        end_idx = starts[i + 1][0] if i + 1 < len(starts) else len(lines)
        body = normalize_text("\n".join(lines[start_idx + 1 : end_idx]).strip())
        if not body:
            continue
        kind = classify_heading(title)
        sections.append({"kind": kind, "title": title, "body": body})

    order = ["hook", "criteria", "rank", "recap", "cta", "disclosure", "other"]
    ordered: List[Dict[str, str]] = []
    for kind in order:
        ordered.extend([s for s in sections if s["kind"] == kind])

    out: List[Tuple[str, str, str]] = []
    used_keys: Dict[str, int] = {}
    rank_counter = 0
    for idx, sec in enumerate(ordered, start=1):
        base = sec["kind"]
        if sec["kind"] == "rank":
            rank_counter += 1
            base = f"rank_{rank_counter}"
        title_slug = slug(sec["title"], 24)
        key = f"{base}_{title_slug}" if title_slug else base
        used_keys[key] = used_keys.get(key, 0) + 1
        if used_keys[key] > 1:
            key = f"{key}_{used_keys[key]}"
        filename = f"vo_{idx:02d}_{key}.mp3"
        out.append((key, filename, sec["body"]))

    return out


def ffprobe_duration(path: Path) -> float:
    try:
        p = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return float((p.stdout or "0").strip())
    except Exception:
        return 0.0


def ffmpeg_volume_stats(path: Path) -> Tuple[float, float]:
    try:
        p = subprocess.run(
            ["ffmpeg", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
            check=False,
            capture_output=True,
            text=True,
        )
        text = (p.stderr or "") + "\n" + (p.stdout or "")
        mean_m = re.search(r"mean_volume:\s*(-?\d+(\.\d+)?)\s*dB", text)
        max_m = re.search(r"max_volume:\s*(-?\d+(\.\d+)?)\s*dB", text)
        mean_db = float(mean_m.group(1)) if mean_m else 0.0
        peak_db = float(max_m.group(1)) if max_m else 0.0
        return mean_db, peak_db
    except Exception:
        return 0.0, 0.0


def write_report(
    report_path: Path,
    voice_name: str,
    voice_id: str,
    model_id: str,
    results: List[ChunkResult],
) -> None:
    lines = []
    lines.append("# ElevenLabs Voiceover Report")
    lines.append("")
    lines.append(f"- Voice: `{voice_name}`")
    lines.append(f"- Voice ID: `{voice_id}`")
    lines.append(f"- Model: `{model_id}`")
    lines.append("")
    lines.append("| Chunk | File | Status | Size (bytes) | Duration (s) | Mean (dB) | Peak (dB) | Notes |")
    lines.append("|---|---|---|---:|---:|---:|---:|---|")
    for r in results:
        lines.append(
            f"| `{r.key}` | `{r.filename}` | `{r.status}` | {r.bytes_size} | {r.duration_sec:.2f} | {r.mean_db:.1f} | {r.peak_db:.1f} | {r.notes} |"
        )
    lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", required=True, help="Path to script_long.md")
    parser.add_argument("--voice-name", required=True, help='ElevenLabs voice name (e.g. "Thomas Louis")')
    parser.add_argument("--output-dir", required=True, help="Output directory for mp3 chunks")
    parser.add_argument("--report", required=True, help="Output markdown report path")
    parser.add_argument("--model-id", default="eleven_multilingual_v2", help="ElevenLabs model id")
    parser.add_argument("--stability", type=float, default=0.40)
    parser.add_argument("--similarity-boost", type=float, default=0.82)
    parser.add_argument("--style", type=float, default=0.28)
    parser.add_argument("--speaker-boost", action="store_true", default=True)
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing files")
    args = parser.parse_args()

    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        print("ERROR: Missing ELEVENLABS_API_KEY in environment.", file=sys.stderr)
        return 2

    script_path = Path(args.script)
    output_dir = Path(args.output_dir)
    report_path = Path(args.report)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    script_text = script_path.read_text(encoding="utf-8")
    plan = build_section_plan(script_text)
    if not plan:
        print("ERROR: no readable script sections found.", file=sys.stderr)
        return 5

    try:
        voice_id = resolve_voice_id(api_key, args.voice_name)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3
    except (HTTPError, URLError) as e:
        print(f"ERROR: voice lookup failed: {e}", file=sys.stderr)
        return 4

    results: List[ChunkResult] = []
    for key, filename, text in plan:
        text = text.strip()
        target = output_dir / filename

        if target.exists() and not args.overwrite:
            size = target.stat().st_size
            dur = ffprobe_duration(target)
            mean_db, peak_db = ffmpeg_volume_stats(target)
            results.append(
                ChunkResult(
                    key,
                    filename,
                    "KEEP",
                    "File exists (use --overwrite to regenerate)",
                    bytes_size=size,
                    duration_sec=dur,
                    mean_db=mean_db,
                    peak_db=peak_db,
                )
            )
            continue

        try:
            audio = api_post_tts(
                voice_id=voice_id,
                text=text,
                api_key=api_key,
                model_id=args.model_id,
                stability=args.stability,
                similarity_boost=args.similarity_boost,
                style=args.style,
                speaker_boost=args.speaker_boost,
            )
            target.write_bytes(audio)
            size = target.stat().st_size
            dur = ffprobe_duration(target)
            mean_db, peak_db = ffmpeg_volume_stats(target)
            note = "OK"
            status = "OK"
            if dur and dur < 8:
                note = "Short duration, review needed"
                status = "WARN"
            if mean_db and mean_db < -27:
                note = f"{note}; low average volume"
                status = "WARN"
            if peak_db and peak_db > -1:
                note = f"{note}; peak too high (possible clipping)"
                status = "WARN"
            results.append(ChunkResult(key, filename, status, note, size, dur, mean_db, peak_db))
        except HTTPError as e:
            try:
                msg = e.read().decode("utf-8", errors="ignore")
            except Exception:
                msg = str(e)
            results.append(ChunkResult(key, filename, "FAIL", f"HTTP {e.code}: {msg[:180]}"))
        except Exception as e:
            results.append(ChunkResult(key, filename, "FAIL", str(e)[:180]))

    write_report(report_path, args.voice_name, voice_id, args.model_id, results)
    print(f"Wrote report: {report_path}")
    for r in results:
        print(f"{r.status:4} {r.filename} {r.bytes_size} bytes {r.duration_sec:.2f}s {r.notes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
