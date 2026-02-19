#!/usr/bin/env python3
"""CLI wrapper around tools.lib.ops_tier for market_scout local workflows."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.lib.ops_tier import decide_ops_tier, detect_ops_paused, decision_to_dict  # noqa: E402


def _truthy(v: str | None) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--daily-budget-usd", type=float, default=30.0)
    p.add_argument("--spent-usd", type=float, default=0.0)
    p.add_argument("--consecutive-failures", type=int, default=0)
    p.add_argument("--worker-healthy", default="1")
    p.add_argument("--credits-remaining", type=float, default=999999.0)
    p.add_argument("--min-credits-required", type=float, default=1000.0)
    p.add_argument("--disk-free-gb", type=float, default=999.0)
    p.add_argument("--min-disk-gb", type=float, default=5.0)
    p.add_argument("--economy-window", action="store_true")
    p.add_argument("--pause-file", default="state/ops/PAUSED")
    p.add_argument("--ops-paused", default="0")
    p.add_argument("--json", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    paused, paused_reasons = detect_ops_paused(project_root=PROJECT_ROOT)
    if Path(args.pause_file).exists() and "OPS_PAUSED_FLAG" not in paused_reasons:
        paused = True
        paused_reasons.append("OPS_PAUSED_FLAG")
    if _truthy(args.ops_paused):
        paused = True
        paused_reasons.append("OPS_PAUSED_ENV")

    low_credit_reasons = []
    if args.credits_remaining < args.min_credits_required:
        low_credit_reasons.append("ELEVENLABS_LOW_CREDIT")

    decision = decide_ops_tier(
        daily_budget_usd=args.daily_budget_usd,
        spent_usd=args.spent_usd,
        failures=max(args.consecutive_failures, 0),
        runs=1,
        critical_failures=0,
        paused=paused,
        paused_reasons=paused_reasons,
        worker_healthy=_truthy(args.worker_healthy),
        disk_free_gb=args.disk_free_gb,
        consecutive_failures=args.consecutive_failures,
        consecutive_failure_threshold=2,
        low_credit_reasons=low_credit_reasons,
        economy_window=args.economy_window,
        budget_near_limit_ratio=0.85,
    )

    payload = decision_to_dict(decision)
    payload["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    if args.json:
        print(json.dumps(payload, ensure_ascii=True, indent=2))
    else:
        print(f"{payload['tier']}: {payload.get('reason','')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
