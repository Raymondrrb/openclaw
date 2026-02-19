#!/usr/bin/env python3
"""
Pipeline Step 1: Generate structured script JSON.

Reads product_selection.json from a pipeline run directory and generates
a structured script.json that downstream workers consume.

Usage:
    python3 tools/pipeline_step_1_generate_script.py --run-dir content/pipeline_runs/RUN_ID/
    python3 tools/pipeline_step_1_generate_script.py --run-dir content/pipeline_runs/RUN_ID/ --script-source openclaw

Input:  {run_dir}/product_selection.json
Output: {run_dir}/script.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from video_pipeline_lib import (
    Product,
    build_structured_script_prompt,
    load_products_json,
    normalize_ws,
    parse_structured_script,
    write_structured_script,
)


def generate_with_openclaw(
    products: list[Product],
    theme: str,
    channel_name: str,
    agent_id: str = "scriptwriter",
    timeout_sec: int = 300,
    variation_plan: dict | None = None,
) -> dict:
    prompt = build_structured_script_prompt(products, theme, channel_name, variation_plan)
    session_id = f"agent:{agent_id}:structured_{int(time.time())}"
    cmd = [
        "openclaw", "agent",
        "--agent", agent_id,
        "--session-id", session_id,
        "--thinking", "low",
        "--timeout", str(timeout_sec),
        "--json",
        "--message", prompt,
    ]
    p = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if p.returncode != 0:
        raise RuntimeError(f"OpenClaw failed. stderr: {normalize_ws(p.stderr)[:300]}")

    data = json.loads(p.stdout)
    payloads = (((data or {}).get("result") or {}).get("payloads") or [])
    if not payloads:
        raise RuntimeError("OpenClaw returned no payloads.")
    raw_text = payloads[0].get("text", "")
    if not raw_text:
        raise RuntimeError("OpenClaw returned empty text.")

    return parse_structured_script(raw_text)


def generate_mock(products: list[Product], theme: str, channel_name: str,
                  variation_plan: dict | None = None) -> dict:
    """Generate a deterministic mock structured script for testing."""
    ranked = sorted(products, key=lambda p: p.ranking_score, reverse=True)
    segments = []

    segments.append({
        "type": "HOOK",
        "narration": f"{theme} in 2026 is more confusing than ever. So which one is actually worth your money?",
        "visual_hint": f"Quick montage of five {theme} products flashing on screen with price tags",
    })
    segments.append({
        "type": "CREDIBILITY",
        "narration": f"I tested these for two weeks. Real usage, real numbers.",
        "visual_hint": f"Desk setup with multiple {theme} products being used side by side",
    })
    segments.append({
        "type": "CRITERIA",
        "narration": "I ranked these based on three things: performance, build quality, and value for money.",
        "visual_hint": "Clean infographic showing three ranking criteria with icons",
    })

    for i, p in enumerate(reversed(ranked), start=1):
        rank = 6 - i
        segments.append({
            "type": "PRODUCT_INTRO",
            "product_name": p.product_title,
            "narration": f"Number {rank}. The {p.product_title}.",
            "visual_hint": f"Clean shot of {p.product_title} on a neutral background",
        })
        segments.append({
            "type": "PRODUCT_DEMO",
            "product_name": p.product_title,
            "narration": f"At ${p.current_price_usd:.2f} with a {p.rating} star rating from {p.review_count:,} reviews, this one delivers.",
            "visual_hint": f"User actively using {p.product_title} in a realistic daily scenario",
        })
        segments.append({
            "type": "PRODUCT_REVIEW",
            "product_name": p.product_title,
            "narration": f"The build quality impressed me. But it's not perfect.",
            "visual_hint": f"Close-up detail shot of {p.product_title} showing build quality",
        })
        segments.append({
            "type": "PRODUCT_RANK",
            "product_name": p.product_title,
            "narration": f"If you need solid performance on a budget, this is your pick. If you want premium everything, skip this one.",
        })
        if rank > 1:
            segments.append({
                "type": "FORWARD_HOOK",
                "narration": "But the next one might change your mind.",
            })

    segments.append({
        "type": "WINNER_REINFORCEMENT",
        "narration": f"If you only buy one thing from this list, get the {ranked[0].product_title}.",
        "visual_hint": f"Side-by-side comparison of top 3 products with winner highlighted",
    })
    segments.append({
        "type": "ENDING_DECISION",
        "narration": f"That's the top 5 {theme} for 2026. Check the links for current pricing. "
                     "If this helped, subscribe for more. "
                     "Disclosure: this video contains affiliate links and was produced with AI assistance.",
    })

    total_words = sum(len(s.get("narration", "").split()) for s in segments)

    return {
        "video_title": f"Top 5 Best {theme} in 2026",
        "estimated_duration_minutes": round(total_words / 150, 1),
        "total_word_count": total_words,
        "segments": segments,
        "youtube": {
            "description": f"Top 5 {theme} for 2026. Tested and ranked.\n\nAffiliate disclosure: links below may earn a commission.\nAI disclosure: script produced with AI assistance.",
            "tags": [theme, f"best {theme} 2026", f"top 5 {theme}", "review"],
            "chapters": [
                {"time": "0:00", "label": "Intro"},
                {"time": "0:25", "label": "How I Tested"},
            ],
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Step 1: Generate structured script")
    parser.add_argument("--run-dir", required=True, help="Pipeline run directory")
    parser.add_argument("--script-source", choices=["openclaw", "mock"], default="mock")
    parser.add_argument("--theme", default="", help="Category/theme (read from state if empty)")
    parser.add_argument("--channel-name", default="Rayviews")
    parser.add_argument("--openclaw-agent", default="scriptwriter")
    parser.add_argument("--openclaw-timeout", type=int, default=300)
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    products_path = run_dir / "product_selection.json"
    output_path = run_dir / "script.json"

    if output_path.exists():
        print(f"[SKIP] script.json already exists at {output_path}")
        sys.exit(0)

    if not products_path.exists():
        print(f"[ERROR] product_selection.json not found at {products_path}")
        sys.exit(1)

    products = load_products_json(products_path)
    if not products:
        print("[ERROR] No products found in product_selection.json")
        sys.exit(1)

    theme = args.theme
    if not theme:
        state_path = run_dir / "state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            theme = state.get("theme", state.get("category", "products"))
        else:
            theme = "products"

    # Load variation_plan.json if it exists
    variation_plan = None
    vp_path = run_dir / "variation_plan.json"
    if vp_path.exists():
        variation_plan = json.loads(vp_path.read_text(encoding="utf-8"))
        print(f"[INFO] Loaded variation_plan: {variation_plan.get('selections', {}).get('structure_template', '?')}")

    print(f"[STEP 1] Generating structured script for '{theme}' ({len(products)} products)")

    if args.script_source == "openclaw":
        structured = generate_with_openclaw(
            products, theme, args.channel_name,
            args.openclaw_agent, args.openclaw_timeout,
            variation_plan,
        )
    else:
        structured = generate_mock(products, theme, args.channel_name, variation_plan)

    path = write_structured_script(structured, run_dir)
    wc = structured.get("total_word_count", 0)
    segs = len(structured.get("segments", []))
    print(f"[DONE] script.json written: {wc} words, {segs} segments → {path}")


if __name__ == "__main__":
    main()
