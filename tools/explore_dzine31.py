"""Phase 31: Clean E2E test with shared session.

Tests the refactored dzine_browser.py with shared session management.
Sequential calls should all use the same Playwright connection.
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.lib.dzine_browser import (
    GenerationResult,
    close_session,
    generate_ray_scene,
    generate_thumbnail,
    generate_variant,
)
from tools.lib.dzine_schema import DzineRequest, build_prompts

ARTIFACTS = Path(__file__).resolve().parent.parent / "artifacts" / "dzine_explore"
ARTIFACTS.mkdir(parents=True, exist_ok=True)


def main():
    print("=" * 60, flush=True)
    print("  PHASE 31: SHARED SESSION E2E TEST", flush=True)
    print("=" * 60, flush=True)

    results = {}

    # TEST 1: Txt2Img thumbnail
    print("\n--- TEST 1: generate_thumbnail() ---", flush=True)
    try:
        dest = ARTIFACTS / "e2e31_thumbnail.png"
        r = generate_thumbnail(
            "Bose QuietComfort Ultra Headphones",
            output_path=dest,
        )
        print(f"  Success={r.success}  Duration={r.duration_s:.1f}s", flush=True)
        print(f"  URL={r.image_url[:80] if r.image_url else 'N/A'}", flush=True)
        print(f"  Error={r.error}", flush=True)
        if r.success and dest.exists():
            print(f"  File: {dest.stat().st_size} bytes", flush=True)
        results["thumbnail"] = r.success
    except Exception as e:
        print(f"  EXCEPTION: {e}", flush=True)
        import traceback; traceback.print_exc()
        results["thumbnail"] = False

    time.sleep(2)

    # TEST 2: CC Ray scene (reuses same session)
    print("\n--- TEST 2: generate_ray_scene() ---", flush=True)
    try:
        dest = ARTIFACTS / "e2e31_ray.png"
        r = generate_ray_scene(
            "Ray examining a pair of premium headphones with an approving expression, "
            "modern studio background, warm lighting, medium shot",
            output_path=dest,
        )
        print(f"  Success={r.success}  Duration={r.duration_s:.1f}s", flush=True)
        print(f"  URL={r.image_url[:80] if r.image_url else 'N/A'}", flush=True)
        print(f"  Error={r.error}", flush=True)
        if r.success and dest.exists():
            print(f"  File: {dest.stat().st_size} bytes", flush=True)
        results["ray_scene"] = r.success
    except Exception as e:
        print(f"  EXCEPTION: {e}", flush=True)
        import traceback; traceback.print_exc()
        results["ray_scene"] = False

    time.sleep(2)

    # TEST 3: Product variant (reuses same session)
    print("\n--- TEST 3: generate_variant() ---", flush=True)
    try:
        req = DzineRequest(
            asset_type="product",
            product_name="Bose QuietComfort Ultra",
            image_variant="hero",
            niche_category="audio",
        )
        req = build_prompts(req)
        print(f"  Prompt: {req.prompt[:80]}...", flush=True)

        dest = ARTIFACTS / "e2e31_hero.png"
        r = generate_variant(req, output_path=dest)
        print(f"  Success={r.success}  Duration={r.duration_s:.1f}s", flush=True)
        print(f"  URL={r.image_url[:80] if r.image_url else 'N/A'}", flush=True)
        print(f"  Error={r.error}", flush=True)
        if r.success and dest.exists():
            print(f"  File: {dest.stat().st_size} bytes", flush=True)
        results["variant"] = r.success
    except Exception as e:
        print(f"  EXCEPTION: {e}", flush=True)
        import traceback; traceback.print_exc()
        results["variant"] = False

    # Close the shared session
    close_session()

    # Summary
    print("\n" + "=" * 60, flush=True)
    print("  RESULTS", flush=True)
    print("=" * 60, flush=True)
    for name, ok in results.items():
        print(f"  {'PASS' if ok else 'FAIL'}: {name}", flush=True)
    print(f"\n  {sum(results.values())}/{len(results)} passed", flush=True)

    print(f"\n===== PHASE 31 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
