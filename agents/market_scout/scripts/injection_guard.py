#!/usr/bin/env python3
"""CLI wrapper around tools.lib.injection_guard for market_scout local workflows."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.lib.injection_guard import sanitize_external_text  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="external")
    parser.add_argument("--input-file", default=None)
    parser.add_argument("--max-chars", type=int, default=12000)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.input_file:
        raw = Path(args.input_file).read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()
    raw = raw[: args.max_chars]

    result = sanitize_external_text(raw, source=args.source, mode="generic")
    status = str(result.get("status", "OK")).upper()

    payload = {
        "source": args.source,
        "status": status,
        "blocked": status == "FAIL",
        "reason_codes": sorted(
            set(list(result.get("fail_reason_codes", []) or []) + list(result.get("warn_reason_codes", []) or []))
        ),
        "sanitized": result.get("sanitized", ""),
        "findings": [],
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=True, indent=2))
    else:
        print(payload["sanitized"])

    if status == "FAIL":
        return 2
    if status == "WARN":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
