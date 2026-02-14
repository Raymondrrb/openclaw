#!/usr/bin/env python3
"""RayVault QR/Overlay Builder — deterministic affiliate visual assets.

Reads manifest affiliate data and generates overlay PNGs (lower-third + QR)
for each eligible product, respecting episode_truth_tier policy.

Golden rules:
  1. NEVER generate a link. Only consume manifest.affiliate.short_link.
  2. RED tier = no overlays at all. AMBER = link-only (no QR by default).
  3. Deterministic: same inputs (manifest + metadata) = same outputs (PNGs).

Output:
    publish/overlays/
        p01_lowerthird.png   (1920x1080 RGBA, lower-left)
        p01_qr.png           (380x380, when enabled)
        overlays_index.json

Dependencies (graceful degradation):
    - Pillow: required for PNG rendering. Without it, dry-run only.
    - qrcode: required for QR generation. Without it, LINK_ONLY mode.

Usage:
    python3 -m rayvault.qr_overlay_builder --run-dir state/runs/RUN_2026_02_14_A --apply
    python3 -m rayvault.qr_overlay_builder --run-dir state/runs/RUN_2026_02_14_A --force-qr

Exit codes:
    0: success
    1: runtime error
    2: validation error (missing run dir, manifest)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants / Layout
# ---------------------------------------------------------------------------

CANVAS_W = 1920
CANVAS_H = 1080
MARGIN = 80
QR_SIZE = 380
QR_QUIET_ZONE = 4

# Default overlay positions (bottom-left for lower-third, bottom-right for QR)
LT_X = MARGIN
LT_Y = None  # computed at render time (bottom-aligned)
QR_X = CANVAS_W - MARGIN - QR_SIZE
QR_Y = CANVAS_H - MARGIN - QR_SIZE

# Lower-third: bottom-left, semi-transparent background
LT_BG_ALPHA = int(255 * 0.70)
LT_BG_COLOR = (20, 20, 20, LT_BG_ALPHA)
LT_TEXT_COLOR = (255, 255, 255, 255)
LT_SHADOW_COLOR = (0, 0, 0, 180)
LT_PADDING_X = 28
LT_PADDING_Y = 16
LT_LINE_SPACING = 8

# Display modes
DISPLAY_HIDE = "HIDE"
DISPLAY_LINK_ONLY = "LINK_ONLY"
DISPLAY_LINK_PLUS_QR = "LINK_PLUS_QR"


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "\u2026"


# Separator tokens for smart truncation (ordered by priority)
_TITLE_SEPARATORS = [" - ", " \u2014 ", " | ", ", ", ": "]


def smart_title(text: str, max_chars: int = 52) -> str:
    """Smart truncation: cut at natural separators before the limit.

    Prefers cutting at " - ", " | ", ",", ":" within max_chars.
    Falls back to word-boundary truncation with ellipsis.
    Never returns empty string.
    """
    text = text.strip()
    if not text:
        return ""
    if len(text) <= max_chars:
        return text

    # Try cutting at separators within limit
    best_cut = -1
    for sep in _TITLE_SEPARATORS:
        idx = text.rfind(sep, 0, max_chars)
        if idx > 10 and idx > best_cut:  # min 10 chars to avoid too-short titles
            best_cut = idx

    if best_cut > 0:
        return text[:best_cut].rstrip()

    # Fallback: cut at last space before limit
    space_idx = text.rfind(" ", 0, max_chars - 1)
    if space_idx > 10:
        return text[:space_idx].rstrip() + "\u2026"

    # Last resort: hard cut
    return text[: max_chars - 1].rstrip() + "\u2026"


# ---------------------------------------------------------------------------
# Check optional dependencies
# ---------------------------------------------------------------------------


def _has_pillow() -> bool:
    try:
        from PIL import Image, ImageDraw, ImageFont  # noqa: F401
        return True
    except ImportError:
        return False


def _has_qrcode() -> bool:
    try:
        import qrcode  # noqa: F401
        return True
    except ImportError:
        return False


def _has_pyzbar() -> bool:
    try:
        from pyzbar.pyzbar import decode  # noqa: F401
        return True
    except ImportError:
        return False


def _canon_url(url: str) -> str:
    """Canonicalize URL for comparison: strip whitespace + trailing slash."""
    url = url.strip()
    if url.endswith("/"):
        url = url[:-1]
    return url


def validate_qr_content(qr_path: Path, expected_link: str) -> Optional[str]:
    """Decode QR from PNG and verify it matches expected_link.

    Returns None on success, error string on failure.
    Requires pyzbar + Pillow. Uses canonical URL comparison.
    """
    if not _has_pyzbar() or not _has_pillow():
        return "QR_VALIDATE_SKIPPED_NO_PYZBAR"
    try:
        from PIL import Image
        from pyzbar.pyzbar import decode
        img = Image.open(qr_path)
        results = decode(img)
        if not results:
            return "QR_DECODE_EMPTY"
        decoded = results[0].data.decode("utf-8", errors="replace")
        if _canon_url(decoded) != _canon_url(expected_link):
            return f"QR_CONTENT_MISMATCH: got={decoded[:60]}"
        return None
    except Exception as e:
        return f"QR_DECODE_ERROR: {type(e).__name__}"


# ---------------------------------------------------------------------------
# Display mode policy
# ---------------------------------------------------------------------------


@dataclass
class OverlayFlags:
    allow_qr_amber: bool = False
    no_qr: bool = False
    force_qr: bool = False
    validate_qr: bool = True
    max_title_chars: int = 52
    include_price: bool = True
    include_rank_badge: bool = True
    amber_warning_text: str = ""  # e.g. "Prices may vary"


def resolve_display_mode(
    tier: str,
    eligible: bool,
    short_link: Optional[str],
    flags: OverlayFlags,
) -> str:
    """Determine overlay display mode for a product.

    Policy:
      RED → HIDE (no overlays)
      no link or not eligible → HIDE
      AMBER → LINK_ONLY (no QR unless --allow-qr-amber or --force-qr)
      GREEN → LINK_PLUS_QR (unless --no-qr)
    """
    if not eligible or not short_link:
        return DISPLAY_HIDE
    if tier == "RED":
        return DISPLAY_HIDE
    if flags.force_qr:
        return DISPLAY_LINK_PLUS_QR
    if flags.no_qr:
        return DISPLAY_LINK_ONLY
    if tier == "AMBER":
        return DISPLAY_LINK_PLUS_QR if flags.allow_qr_amber else DISPLAY_LINK_ONLY
    return DISPLAY_LINK_PLUS_QR


# ---------------------------------------------------------------------------
# Product metadata resolution
# ---------------------------------------------------------------------------


def _load_product_meta(
    run_dir: Path, rank: int, asin: str, library_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Load product metadata from best available source."""
    pdir = run_dir / "products" / f"p{rank:02d}"

    # Priority 1: per-product metadata in run dir
    pm = pdir / "product_metadata.json"
    if pm.exists():
        try:
            return read_json(pm)
        except Exception:
            pass

    # Priority 2: product.json in run dir
    pj = pdir / "product.json"
    if pj.exists():
        try:
            return read_json(pj)
        except Exception:
            pass

    # Priority 3: library cache
    if library_dir and asin:
        lib_meta = library_dir / "products" / asin / "product_metadata.json"
        if lib_meta.exists():
            try:
                return read_json(lib_meta)
            except Exception:
                pass

    # Priority 4: products.json
    plist = run_dir / "products" / "products.json"
    if plist.exists():
        try:
            data = read_json(plist)
            for item in data.get("items", []):
                if item.get("rank") == rank or item.get("asin") == asin:
                    return item
        except Exception:
            pass

    return {}


# ---------------------------------------------------------------------------
# Rendering (requires Pillow)
# ---------------------------------------------------------------------------


def render_lowerthird(
    rank: int,
    title: str,
    short_link: str,
    price: Optional[str],
    out_path: Path,
    width: int = CANVAS_W,
    height: int = CANVAS_H,
    font_size: int = 44,
    flags: Optional[OverlayFlags] = None,
) -> bool:
    """Render lower-third overlay PNG with transparency.

    Returns True on success, False if Pillow unavailable.
    """
    if not _has_pillow():
        return False

    from PIL import Image, ImageDraw, ImageFont

    flags = flags or OverlayFlags()

    # Build text lines
    lines = []
    rank_prefix = f"TOP #{rank}" if flags.include_rank_badge else ""
    title_trunc = smart_title(title, flags.max_title_chars) if title else ""
    if rank_prefix and title_trunc:
        lines.append(f"{rank_prefix}  \u2014  {title_trunc}")
    elif rank_prefix:
        lines.append(rank_prefix)
    elif title_trunc:
        lines.append(title_trunc)

    line2_parts = []
    if price and flags.include_price:
        line2_parts.append(str(price))
    if short_link:
        line2_parts.append(short_link)
    if line2_parts:
        lines.append("    ".join(line2_parts))

    # AMBER warning text (optional extra line)
    if flags.amber_warning_text:
        lines.append(flags.amber_warning_text)

    if not lines:
        return False

    # Load font (fallback to default)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", font_size)
    except (OSError, IOError):
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
        except (OSError, IOError):
            try:
                font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
            except (OSError, IOError):
                font = ImageFont.load_default()

    # Measure text
    dummy = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(dummy)
    line_heights = []
    line_widths = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])

    max_w = max(line_widths)
    total_h = sum(line_heights) + LT_LINE_SPACING * (len(lines) - 1)

    # Background rect dimensions
    bg_w = max_w + LT_PADDING_X * 2
    bg_h = total_h + LT_PADDING_Y * 2

    # Position: bottom-left with margin
    bg_x = MARGIN
    bg_y = height - MARGIN - bg_h

    # Create canvas
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw background rectangle
    draw.rectangle(
        [bg_x, bg_y, bg_x + bg_w, bg_y + bg_h],
        fill=LT_BG_COLOR,
    )

    # Draw text lines
    y_cursor = bg_y + LT_PADDING_Y
    for i, line in enumerate(lines):
        # Shadow
        draw.text(
            (bg_x + LT_PADDING_X + 2, y_cursor + 2),
            line, font=font, fill=LT_SHADOW_COLOR,
        )
        # Text
        draw.text(
            (bg_x + LT_PADDING_X, y_cursor),
            line, font=font, fill=LT_TEXT_COLOR,
        )
        y_cursor += line_heights[i] + LT_LINE_SPACING

    # Atomic write
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".tmp.png")
    img.save(tmp, "PNG")
    os.replace(tmp, out_path)
    return True


def render_qr(
    short_link: str,
    out_path: Path,
    size: int = QR_SIZE,
) -> bool:
    """Render QR code PNG (black on white, with quiet zone).

    Returns True on success, False if qrcode/Pillow unavailable.
    """
    if not _has_qrcode() or not _has_pillow():
        return False

    import qrcode

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=QR_QUIET_ZONE,
    )
    qr.add_data(short_link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img = img.resize((size, size))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".tmp.png")
    img.save(tmp, "PNG")
    os.replace(tmp, out_path)
    return True


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------


@dataclass
class OverlayResult:
    ok: bool
    generated: int = 0
    skipped: int = 0
    hidden: int = 0
    warnings: List[str] = field(default_factory=list)
    items: List[Dict[str, Any]] = field(default_factory=list)


def build_overlays(
    run_dir: Path,
    flags: Optional[OverlayFlags] = None,
    apply: bool = False,
    width: int = CANVAS_W,
    height: int = CANVAS_H,
    font_size: int = 44,
    library_dir: Optional[Path] = None,
) -> OverlayResult:
    """Build overlay PNGs for eligible products in a run.

    Reads manifest for affiliate data, resolves display_mode per tier policy,
    generates lower-third + QR PNGs, writes overlays_index.json and updates manifest.
    """
    run_dir = run_dir.resolve()
    flags = flags or OverlayFlags()
    result = OverlayResult(ok=True)

    manifest_path = run_dir / "00_manifest.json"
    if not manifest_path.exists():
        return OverlayResult(ok=False, warnings=["manifest not found"])

    manifest = read_json(manifest_path)

    # Resolve episode truth tier
    tier = (
        manifest.get("affiliate_policy", {}).get("episode_truth_tier")
        or manifest.get("products", {}).get("episode_truth_tier")
        or "GREEN"
    )

    # Get products summary
    products = manifest.get("products_summary", [])
    if not products:
        return OverlayResult(ok=True, warnings=["no products_summary in manifest"])

    has_pil = _has_pillow()
    has_qr = _has_qrcode()
    if not has_pil:
        result.warnings.append("Pillow not installed — dry-run only (no PNG rendering)")
    if not has_qr:
        result.warnings.append("qrcode not installed — QR generation disabled")

    overlays_dir = run_dir / "publish" / "overlays"
    index_items: List[Dict[str, Any]] = []
    overlay_assets: List[Dict[str, Any]] = []

    for p in products:
        rank = p.get("rank", 0)
        asin = p.get("asin", "")
        aff = p.get("affiliate", {})
        eligible = aff.get("eligible", False)
        short_link = aff.get("short_link")

        display_mode = resolve_display_mode(tier, eligible, short_link, flags)

        # Update product affiliate display_mode
        if "affiliate" in p:
            p["affiliate"]["display_mode"] = display_mode

        if display_mode == DISPLAY_HIDE:
            result.hidden += 1
            index_items.append({
                "rank": rank,
                "asin": asin,
                "display_mode": display_mode,
                "lowerthird_path": None,
                "qr_path": None,
                "warnings": [],
            })
            continue

        # Load product metadata for title/price
        meta = _load_product_meta(run_dir, rank, asin, library_dir)
        title = meta.get("title") or p.get("title", "")
        price = meta.get("price_text") or meta.get("price")
        if price is not None:
            price = str(price)

        item_warnings: List[str] = []
        lt_path_rel = f"publish/overlays/p{rank:02d}_lowerthird.png"
        lt_path = run_dir / lt_path_rel
        qr_path_rel = f"publish/overlays/p{rank:02d}_qr.png"
        qr_path = run_dir / qr_path_rel

        # Render lower-third
        lt_ok = False
        if apply and has_pil:
            lt_ok = render_lowerthird(
                rank=rank,
                title=title,
                short_link=short_link or "",
                price=price,
                out_path=lt_path,
                width=width,
                height=height,
                font_size=font_size,
                flags=flags,
            )
            if lt_ok:
                h = sha1_file(lt_path)
                overlay_assets.append({
                    "rank": rank, "type": "lowerthird",
                    "path": lt_path_rel, "sha1": h,
                    "x": 0, "y": 0, "w": width, "h": height,
                    "display_mode": display_mode,
                })
        elif not apply:
            item_warnings.append("dry-run: would generate lower-third")
        else:
            item_warnings.append("Pillow missing: cannot render lower-third")

        # Render QR
        qr_ok = False
        want_qr = display_mode == DISPLAY_LINK_PLUS_QR
        if want_qr and apply and has_qr and has_pil and short_link:
            qr_ok = render_qr(short_link, qr_path)
            if qr_ok and flags.validate_qr:
                # Self-healing: generate → decode → verify
                validation_err = validate_qr_content(qr_path, short_link)
                if validation_err and validation_err != "QR_VALIDATE_SKIPPED_NO_PYZBAR":
                    # QR content doesn't match — degrade to LINK_ONLY
                    item_warnings.append(f"QR_INVALID_DECODE: {validation_err}")
                    try:
                        qr_path.unlink()
                    except OSError:
                        pass
                    qr_ok = False
                    display_mode = DISPLAY_LINK_ONLY
                    if "affiliate" in p:
                        p["affiliate"]["display_mode"] = display_mode
                elif validation_err == "QR_VALIDATE_SKIPPED_NO_PYZBAR":
                    item_warnings.append("QR_VALIDATE_SKIPPED_NO_PYZBAR")
            if qr_ok:
                h = sha1_file(qr_path)
                overlay_assets.append({
                    "rank": rank, "type": "qr",
                    "path": qr_path_rel, "sha1": h,
                    "x": QR_X, "y": QR_Y, "w": QR_SIZE, "h": QR_SIZE,
                    "display_mode": display_mode,
                })
        elif want_qr and not has_qr:
            item_warnings.append("qrcode missing: degraded to LINK_ONLY")
            display_mode = DISPLAY_LINK_ONLY
            if "affiliate" in p:
                p["affiliate"]["display_mode"] = display_mode

        result.generated += 1
        index_items.append({
            "rank": rank,
            "asin": asin,
            "display_mode": display_mode,
            "lowerthird_path": lt_path_rel if lt_ok else None,
            "qr_path": qr_path_rel if qr_ok else None,
            "coords": {
                "lowerthird": {"x": 0, "y": 0, "w": width, "h": height} if lt_ok else None,
                "qr": {"x": QR_X, "y": QR_Y, "w": QR_SIZE, "h": QR_SIZE} if qr_ok else None,
            },
            "warnings": item_warnings,
        })

    result.items = index_items
    result.skipped = sum(1 for i in index_items if not i["lowerthird_path"] and i["display_mode"] != DISPLAY_HIDE)

    # Write overlays index (always when --apply, even for RED/empty — deterministic state)
    if apply:
        index = {
            "run_id": manifest.get("run_id", run_dir.name),
            "episode_truth_tier": tier,
            "generated_at_utc": utc_now_iso(),
            "pillow_available": has_pil,
            "qrcode_available": has_qr,
            "items": index_items,
        }
        atomic_write_json(overlays_dir / "overlays_index.json", index)

        # Update manifest
        render = manifest.setdefault("render", {})
        render["overlays_ready"] = result.generated > 0 and has_pil
        render["overlays_dir"] = "publish/overlays"
        render["overlays_tier"] = tier

        assets = manifest.setdefault("assets", {})
        assets["overlays"] = overlay_assets

        # Update products_summary with display_mode
        manifest["products_summary"] = products

        atomic_write_json(manifest_path, manifest)

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description="RayVault QR/Overlay Builder — affiliate visual assets",
    )
    ap.add_argument("--run-dir", required=True)
    ap.add_argument(
        "--apply", action="store_true",
        help="Generate PNGs and update manifest (default: dry-run)",
    )
    ap.add_argument("--allow-qr-amber", action="store_true", default=False)
    ap.add_argument("--no-qr", action="store_true", default=False)
    ap.add_argument("--force-qr", action="store_true", default=False)
    ap.add_argument("--max-title-chars", type=int, default=52)
    ap.add_argument("--include-price", action="store_true", default=True)
    ap.add_argument("--include-rank-badge", action="store_true", default=True)
    ap.add_argument("--validate-qr", action="store_true", default=True,
                    help="Validate QR content after generation (requires pyzbar)")
    ap.add_argument("--no-validate-qr", action="store_true", default=False,
                    help="Skip QR content validation")
    ap.add_argument("--amber-warning-text", default="",
                    help="Warning text to show on AMBER-tier overlays")
    ap.add_argument("--width", type=int, default=CANVAS_W)
    ap.add_argument("--height", type=int, default=CANVAS_H)
    ap.add_argument("--font-size", type=int, default=44)
    ap.add_argument("--library-dir", default="state/library")
    args = ap.parse_args(argv)

    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.exists():
        print(f"Run dir not found: {run_dir}", file=sys.stderr)
        return 2

    flags = OverlayFlags(
        allow_qr_amber=args.allow_qr_amber,
        no_qr=args.no_qr,
        force_qr=args.force_qr,
        validate_qr=not args.no_validate_qr,
        max_title_chars=args.max_title_chars,
        include_price=args.include_price,
        include_rank_badge=args.include_rank_badge,
        amber_warning_text=args.amber_warning_text,
    )

    lib_dir = Path(args.library_dir).expanduser().resolve() if args.library_dir else None

    result = build_overlays(
        run_dir,
        flags=flags,
        apply=args.apply,
        width=args.width,
        height=args.height,
        font_size=args.font_size,
        library_dir=lib_dir,
    )

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(
        f"qr_overlay_builder [{mode}]: "
        f"generated={result.generated} hidden={result.hidden} "
        f"skipped={result.skipped}"
    )
    for w in result.warnings:
        print(f"  WARN: {w}")
    for item in result.items:
        if item["warnings"]:
            for w in item["warnings"]:
                print(f"  p{item['rank']:02d}: {w}")

    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
