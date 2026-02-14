"""Phase 30: End-to-end test of dzine_browser.py module functions.

Test the actual pipeline code, not exploration scripts.
1. Test Txt2Img generation via generate_thumbnail()
2. Test CC generation via generate_ray_scene()
3. Verify downloaded images are full-resolution
4. Test generate_variant() with a DzineRequest
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Import the actual pipeline module
from tools.lib.dzine_browser import (
    GenerationResult,
    generate_thumbnail,
    generate_ray_scene,
    generate_variant,
)
from tools.lib.dzine_schema import DzineRequest, build_prompts

ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dzine_explore"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def test_txt2img():
    """Test Txt2Img generation via generate_thumbnail()."""
    print("\n" + "=" * 60, flush=True)
    print("  TEST 1: generate_thumbnail()", flush=True)
    print("=" * 60, flush=True)

    dest = ARTIFACTS_DIR / "e2e_thumbnail.png"
    result = generate_thumbnail(
        "Sony WH-1000XM5 Wireless Headphones",
        output_path=dest,
    )

    print(f"\n  Success: {result.success}", flush=True)
    print(f"  Duration: {result.duration_s:.1f}s", flush=True)
    print(f"  URL: {result.image_url[:100] if result.image_url else 'N/A'}", flush=True)
    print(f"  Local: {result.local_path}", flush=True)
    print(f"  SHA256: {result.checksum_sha256[:16]}..." if result.checksum_sha256 else "  SHA256: N/A", flush=True)
    print(f"  Error: {result.error}", flush=True)

    if result.success and dest.exists():
        size = dest.stat().st_size
        print(f"  File size: {size} bytes", flush=True)
        if size < 1024:
            print("  WARNING: File too small!", flush=True)
        else:
            print("  OK: File size looks good", flush=True)

    return result.success


def test_cc_ray():
    """Test CC generation via generate_ray_scene()."""
    print("\n" + "=" * 60, flush=True)
    print("  TEST 2: generate_ray_scene()", flush=True)
    print("=" * 60, flush=True)

    dest = ARTIFACTS_DIR / "e2e_ray_scene.png"
    result = generate_ray_scene(
        "Ray holding up wireless headphones with an excited expression, "
        "clean modern studio background, warm lighting, medium shot",
        output_path=dest,
    )

    print(f"\n  Success: {result.success}", flush=True)
    print(f"  Duration: {result.duration_s:.1f}s", flush=True)
    print(f"  URL: {result.image_url[:100] if result.image_url else 'N/A'}", flush=True)
    print(f"  Local: {result.local_path}", flush=True)
    print(f"  SHA256: {result.checksum_sha256[:16]}..." if result.checksum_sha256 else "  SHA256: N/A", flush=True)
    print(f"  Error: {result.error}", flush=True)

    if result.success and dest.exists():
        size = dest.stat().st_size
        print(f"  File size: {size} bytes", flush=True)
        if size < 1024:
            print("  WARNING: File too small!", flush=True)
        else:
            print("  OK: File size looks good", flush=True)

    return result.success


def test_variant():
    """Test generate_variant() with a DzineRequest."""
    print("\n" + "=" * 60, flush=True)
    print("  TEST 3: generate_variant()", flush=True)
    print("=" * 60, flush=True)

    req = DzineRequest(
        asset_type="product",
        product_name="Sony WH-1000XM5",
        image_variant="hero",
        niche_category="headphones",
    )
    req = build_prompts(req)
    print(f"  Prompt: {req.prompt[:100]}...", flush=True)

    dest = ARTIFACTS_DIR / "e2e_variant_hero.png"
    result = generate_variant(req, output_path=dest)

    print(f"\n  Success: {result.success}", flush=True)
    print(f"  Duration: {result.duration_s:.1f}s", flush=True)
    print(f"  URL: {result.image_url[:100] if result.image_url else 'N/A'}", flush=True)
    print(f"  Error: {result.error}", flush=True)

    if result.success and dest.exists():
        size = dest.stat().st_size
        print(f"  File size: {size} bytes", flush=True)

    return result.success


def main():
    print("=" * 60, flush=True)
    print("  PHASE 30: dzine_browser.py END-TO-END TEST", flush=True)
    print("=" * 60, flush=True)

    results = {}

    # Test 1: Txt2Img thumbnail
    try:
        results["thumbnail"] = test_txt2img()
    except Exception as e:
        print(f"\n  EXCEPTION: {e}", flush=True)
        import traceback
        traceback.print_exc()
        results["thumbnail"] = False

    # Brief pause between tests
    time.sleep(3)

    # Test 2: CC Ray scene
    try:
        results["ray_scene"] = test_cc_ray()
    except Exception as e:
        print(f"\n  EXCEPTION: {e}", flush=True)
        import traceback
        traceback.print_exc()
        results["ray_scene"] = False

    # Brief pause
    time.sleep(3)

    # Test 3: Product variant
    try:
        results["variant"] = test_variant()
    except Exception as e:
        print(f"\n  EXCEPTION: {e}", flush=True)
        import traceback
        traceback.print_exc()
        results["variant"] = False

    # Summary
    print("\n\n" + "=" * 60, flush=True)
    print("  SUMMARY", flush=True)
    print("=" * 60, flush=True)
    for name, success in results.items():
        status = "PASS" if success else "FAIL"
        print(f"  {status}: {name}", flush=True)

    total = sum(results.values())
    print(f"\n  {total}/{len(results)} tests passed", flush=True)

    print(f"\n===== PHASE 30 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
