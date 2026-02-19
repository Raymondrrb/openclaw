from __future__ import annotations

"""Operational tier selection (cost/reliability guardrail).

Policy hierarchy (first match wins):
  1) paused:
     - manual flag (e.g., state/ops/PAUSED) OR env var OPS_PAUSED=1
  2) critical:
     - low credits
     - consecutive failures > N
     - disk insufficient
     - worker offline/unhealthy
  3) low_compute:
     - economy window (time-based)
     - daily budget near limit
  4) normal:
     - otherwise

All decisions include `reasons[]` (reason codes) and `reason` (human summary).
"""

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple


@dataclass
class OpsTierDecision:
    tier: str
    reason: str
    reasons: List[str] = field(default_factory=list)
    directives: Dict[str, Any] = field(default_factory=dict)
    signals: Dict[str, Any] = field(default_factory=dict)


def detect_ops_paused(*, project_root: Path, env: Optional[Mapping[str, str]] = None) -> Tuple[bool, List[str]]:
    """Detect manual pause state (objective signals only)."""
    e = env or os.environ
    reasons: List[str] = []
    if str(e.get("OPS_PAUSED", "") or "").strip().lower() in {"1", "true", "yes", "on"}:
        reasons.append("OPS_PAUSED_ENV")
    if (project_root / "state" / "ops" / "PAUSED").exists():
        reasons.append("OPS_PAUSED_FLAG")
    return bool(reasons), reasons


def decide_ops_tier(
    *,
    daily_budget_usd: float,
    spent_usd: float,
    failures: int,
    runs: int,
    critical_failures: int = 0,
    # Signals (optional; should be objective and derived outside this module)
    paused: bool = False,
    paused_reasons: Optional[List[str]] = None,
    worker_healthy: Optional[bool] = None,
    disk_free_gb: Optional[float] = None,
    consecutive_failures: int = 0,
    consecutive_failure_threshold: int = 3,
    low_credit_reasons: Optional[List[str]] = None,
    economy_window: bool = False,
    budget_near_limit_ratio: float = 0.85,
) -> OpsTierDecision:
    remaining = max(0.0, float(daily_budget_usd or 0) - float(spent_usd or 0))
    spend_ratio = (float(spent_usd or 0) / float(daily_budget_usd)) if float(daily_budget_usd or 0) > 0 else 1.0
    failure_rate = (float(failures or 0) / float(runs)) if int(runs or 0) > 0 else 0.0

    signals: Dict[str, Any] = {
        "daily_budget_usd": round(float(daily_budget_usd or 0), 2),
        "spent_usd": round(float(spent_usd or 0), 2),
        "remaining_budget_usd": round(float(remaining), 2),
        "spend_ratio": round(float(spend_ratio), 4),
        "failures": int(failures or 0),
        "runs": int(runs or 0),
        "failure_rate": round(float(failure_rate), 4),
        "critical_failures": int(critical_failures or 0),
        "consecutive_failures": int(consecutive_failures or 0),
        "consecutive_failure_threshold": int(consecutive_failure_threshold or 0),
        "disk_free_gb": None if disk_free_gb is None else round(float(disk_free_gb), 2),
        "worker_healthy": worker_healthy,
        "economy_window": bool(economy_window),
        "budget_near_limit_ratio": round(float(budget_near_limit_ratio), 4),
    }

    # Tier 0: PAUSED (manual)
    if paused:
        reasons = list(paused_reasons or []) or ["OPS_PAUSED"]
        return OpsTierDecision(
            tier="paused",
            reason="Paused by manual ops flag",
            reasons=reasons,
            directives={
                "allow_expensive_steps": False,
                "retry_profile": "diagnostic_only",
                "model_profile": "none",
                "heartbeat_minutes": 30,
            },
            signals=signals,
        )

    # Tier 1: CRITICAL (stop expensive steps)
    critical_reasons: List[str] = []

    low_credit = False
    if low_credit_reasons:
        low_credit = True
        critical_reasons += [str(x) for x in low_credit_reasons if str(x).strip()]
    # Budget exhaustion is treated as "lack of credit" in budget-based pipelines.
    if spend_ratio >= 1.0 or remaining <= 0:
        low_credit = True
        critical_reasons.append("BUDGET_EXHAUSTED")

    if int(critical_failures or 0) > 0:
        critical_reasons.append("CRITICAL_FAILURES_PRESENT")

    if int(consecutive_failure_threshold or 0) > 0 and int(consecutive_failures or 0) > int(consecutive_failure_threshold):
        critical_reasons.append("CONSECUTIVE_FAILURES_HIGH")

    if disk_free_gb is not None and float(disk_free_gb) < 5.0:
        critical_reasons.append("DISK_LOW")

    if worker_healthy is False:
        critical_reasons.append("WORKER_UNHEALTHY")

    if critical_reasons:
        critical_reasons = _dedupe_keep_order(critical_reasons)
        return OpsTierDecision(
            tier="critical",
            reason="; ".join(critical_reasons),
            reasons=critical_reasons,
            directives={
                "allow_expensive_steps": False,
                "retry_profile": "minimal",
                "model_profile": "cheap_only",
                "heartbeat_minutes": 20,
            },
            signals=signals,
        )

    # Tier 2: LOW_COMPUTE (save money; still allow expensive steps with limits)
    low_compute_reasons: List[str] = []
    if economy_window:
        low_compute_reasons.append("ECONOMY_WINDOW")
    if spend_ratio >= float(budget_near_limit_ratio):
        low_compute_reasons.append("BUDGET_NEAR_LIMIT")
    if low_compute_reasons:
        low_compute_reasons = _dedupe_keep_order(low_compute_reasons)
        return OpsTierDecision(
            tier="low_compute",
            reason="; ".join(low_compute_reasons),
            reasons=low_compute_reasons,
            directives={
                "allow_expensive_steps": True,
                "limit_optional_variants": True,
                "retry_profile": "reduced",
                "model_profile": "balanced",
                "heartbeat_minutes": 15,
            },
            signals=signals,
        )

    return OpsTierDecision(
        tier="normal",
        reason="Healthy",
        reasons=[],
        directives={
            "allow_expensive_steps": True,
            "limit_optional_variants": False,
            "retry_profile": "standard",
            "model_profile": "quality",
            "heartbeat_minutes": 10,
        },
        signals=signals,
    )


def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def decision_to_dict(decision: OpsTierDecision) -> Dict[str, Any]:
    return asdict(decision)
