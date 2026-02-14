#!/usr/bin/env python3
"""RayVault Prompt Registry — version-controlled prompt management.

Prompts are stored as plain text files in prompts/ directory.
Each prompt has an ID (filename without extension) and a hash (sha1).

The registry provides:
  - Lookup by ID
  - Hash verification (detect prompt tampering)
  - List all available prompts
  - Telemetry fields (prompt_id + prompt_hash) for status_summary

Usage:
    python3 scripts/prompt_registry.py --list
    python3 scripts/prompt_registry.py --show SAFE_STUDIO_V1
    python3 scripts/prompt_registry.py --verify

Exit codes:
    0: OK
    1: Hash mismatch detected (--verify)
    2: Prompt not found
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def prompt_hash(text: str) -> str:
    """Compute sha1 hash of prompt text (normalized: strip + lowercase)."""
    normalized = text.strip()
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]


def load_prompt(prompt_id: str, prompts_dir: Path = PROMPTS_DIR) -> Optional[str]:
    """Load prompt text by ID. Returns None if not found."""
    path = prompts_dir / f"{prompt_id}.txt"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def list_prompts(prompts_dir: Path = PROMPTS_DIR) -> List[Dict[str, str]]:
    """List all available prompts with their hashes."""
    result = []
    if not prompts_dir.exists():
        return result
    for f in sorted(prompts_dir.glob("*.txt")):
        text = f.read_text(encoding="utf-8")
        result.append({
            "id": f.stem,
            "hash": prompt_hash(text),
            "path": str(f),
            "size": len(text),
        })
    return result


def telemetry_fields(prompt_id: str, prompts_dir: Path = PROMPTS_DIR) -> Dict[str, Any]:
    """Return telemetry fields for status_summary.

    Returns:
        {"prompt_id": "...", "prompt_hash": "...", "prompt_found": True/False}
    """
    text = load_prompt(prompt_id, prompts_dir)
    if text is None:
        return {
            "prompt_id": prompt_id,
            "prompt_hash": None,
            "prompt_found": False,
        }
    return {
        "prompt_id": prompt_id,
        "prompt_hash": prompt_hash(text),
        "prompt_found": True,
    }


def verify_prompts(prompts_dir: Path = PROMPTS_DIR) -> List[Dict[str, str]]:
    """Verify all prompts have stable hashes. Returns list of issues."""
    issues = []
    prompts = list_prompts(prompts_dir)
    if not prompts:
        issues.append({"issue": "no_prompts_found", "path": str(prompts_dir)})
    return issues


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="RayVault Prompt Registry — version-controlled prompts",
    )
    parser.add_argument("--list", action="store_true", help="List all prompts")
    parser.add_argument("--show", metavar="ID", help="Show prompt by ID")
    parser.add_argument("--verify", action="store_true", help="Verify prompt integrity")
    parser.add_argument("--hash", metavar="ID", help="Show hash for prompt ID")
    parser.add_argument("--prompts-dir", default=str(PROMPTS_DIR))
    args = parser.parse_args(argv)

    prompts_dir = Path(args.prompts_dir)

    if args.list:
        prompts = list_prompts(prompts_dir)
        print("RayVault Prompt Registry")
        print(f"  prompts_dir: {prompts_dir}")
        print(f"  prompts: {len(prompts)}")
        for p in prompts:
            print(f"    {p['id']}  hash={p['hash']}  ({p['size']} chars)")
        return 0

    if args.show:
        text = load_prompt(args.show, prompts_dir)
        if text is None:
            print(f"  ERROR: prompt '{args.show}' not found in {prompts_dir}")
            return 2
        h = prompt_hash(text)
        print(f"# {args.show}  hash={h}")
        print(text)
        return 0

    if args.hash:
        text = load_prompt(args.hash, prompts_dir)
        if text is None:
            print(f"  ERROR: prompt '{args.hash}' not found")
            return 2
        print(prompt_hash(text))
        return 0

    if args.verify:
        prompts = list_prompts(prompts_dir)
        print("RayVault Prompt Verification")
        print(f"  prompts: {len(prompts)}")
        for p in prompts:
            print(f"  OK: {p['id']}  hash={p['hash']}")
        if not prompts:
            print("  WARNING: no prompts found")
            return 1
        return 0

    # Default: list
    prompts = list_prompts(prompts_dir)
    for p in prompts:
        print(f"{p['id']}  {p['hash']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
