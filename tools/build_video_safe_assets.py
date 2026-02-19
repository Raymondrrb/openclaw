#!/usr/bin/env python3
import argparse
import datetime as dt
import os
import subprocess
from pathlib import Path
from typing import List, Tuple

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Create 16:9 video-safe stills from source assets using ffmpeg."
    )
    p.add_argument("--content-dir", required=True, help="Episode content dir (contains assets/)" )
    p.add_argument("--width", type=int, default=1920)
    p.add_argument("--height", type=int, default=1080)
    p.add_argument("--overwrite", action="store_true")
    return p.parse_args()


def ffprobe_dims(path: Path) -> Tuple[int, int]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0:s=x",
        str(path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        return (0, 0)
    txt = (res.stdout or "").strip()
    if "x" not in txt:
        return (0, 0)
    w, h = txt.split("x", 1)
    try:
        return (int(w), int(h))
    except ValueError:
        return (0, 0)


def collect_images(assets_dir: Path) -> List[Path]:
    out: List[Path] = []
    for root, _, files in os.walk(assets_dir):
        if f"{os.sep}video_safe" in root:
            continue
        for name in files:
            ext = Path(name).suffix.lower()
            if ext in IMAGE_EXTS:
                out.append(Path(root) / name)
    out.sort()
    return out


def video_safe_path(src: Path, assets_dir: Path) -> Path:
    rel = src.relative_to(assets_dir)
    stem = src.stem
    out_name = f"{stem}_16x9.jpg"
    return assets_dir / "video_safe" / rel.parent / out_name


def build_filter(width: int, height: int) -> str:
    fg_w = int(width * 0.78)
    fg_h = int(height * 0.78)
    return (
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},boxblur=28:8[bg];"
        f"[0:v]scale={fg_w}:{fg_h}:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2[out]"
    )


def convert_image(src: Path, dst: Path, width: int, height: int) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)
    vf = build_filter(width, height)
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(src),
        "-filter_complex",
        vf,
        "-map",
        "[out]",
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(dst),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return res.returncode == 0 and dst.exists() and dst.stat().st_size > 0


def ratio_label(w: int, h: int) -> str:
    if w <= 0 or h <= 0:
        return "unknown"
    ratio = w / h
    if ratio < 0.9:
        return "portrait"
    if ratio < 1.5:
        return "near-square"
    if ratio < 2.0:
        return "landscape"
    return "ultra-wide"


def main() -> int:
    args = parse_args()
    content_dir = Path(args.content_dir).expanduser().resolve()
    assets_dir = content_dir / "assets"
    if not assets_dir.exists():
        print(f"Missing assets dir: {assets_dir}")
        return 2

    images = collect_images(assets_dir)
    if not images:
        print(f"No images found under: {assets_dir}")
        return 2

    created = 0
    skipped = 0
    failed = 0
    rows: List[Tuple[str, str, str, str]] = []

    for src in images:
        src_w, src_h = ffprobe_dims(src)
        dst = video_safe_path(src, assets_dir)
        if dst.exists() and not args.overwrite:
            skipped += 1
            status = "SKIPPED"
        else:
            ok = convert_image(src, dst, args.width, args.height)
            if ok:
                created += 1
                status = "CREATED"
            else:
                failed += 1
                status = "FAILED"

        out_w, out_h = ffprobe_dims(dst) if dst.exists() else (0, 0)
        rows.append(
            (
                str(src),
                f"{src_w}x{src_h} ({ratio_label(src_w, src_h)})",
                str(dst),
                f"{out_w}x{out_h} ({status})",
            )
        )

    report = content_dir / "video_safe_manifest.md"
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with report.open("w", encoding="utf-8") as f:
        f.write("# Video-Safe Asset Manifest\n\n")
        f.write(f"Generated: {now}\n\n")
        f.write("Style: 16:9 (1920x1080), blurred background + centered product\n\n")
        f.write("| source_path | source_dims | video_safe_path | output |\n")
        f.write("|---|---|---|---|\n")
        for src_path, src_dims, dst_path, output in rows:
            f.write(f"| {src_path} | {src_dims} | {dst_path} | {output} |\n")

        f.write("\n## Summary\n")
        f.write(f"- created: {created}\n")
        f.write(f"- skipped: {skipped}\n")
        f.write(f"- failed: {failed}\n")

    print(f"Wrote: {report}")
    print(f"created={created} skipped={skipped} failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
