from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict


@dataclass
class OpsTierDecision:
    tier: str
    reason: str
    directives: Dict[str, Any]
    signals: Dict[str, Any]


def decide_ops_tier(
    *,
    daily_budget_usd: float,
    spent_usd: float,
    failures: int,
    runs: int,
    critical_failures: int = 0,
) -> OpsTierDecision:
    remaining = max(0.0, daily_budget_usd - spent_usd)
    spend_ratio = (spent_usd / daily_budget_usd) if daily_budget_usd > 0 else 1.0
    failure_rate = (failures / runs) if runs > 0 else 0.0

    signals = {
        "daily_budget_usd": round(daily_budget_usd, 2),
        "spent_usd": round(spent_usd, 2),
        "remaining_budget_usd": round(remaining, 2),
        "spend_ratio": round(spend_ratio, 4),
        "failures": failures,
        "runs": runs,
        "failure_rate": round(failure_rate, 4),
        "critical_failures": critical_failures,
    }

    if critical_failures > 0 or spend_ratio >= 1.0:
        return OpsTierDecision(
            tier="paused",
            reason="Critical failure or budget exhausted",
            directives={
                "allow_expensive_steps": False,
                "retry_profile": "diagnostic_only",
                "model_profile": "none",
                "heartbeat_minutes": 30,
            },
            signals=signals,
        )

    if spend_ratio >= 0.8 or failure_rate >= 0.5:
        return OpsTierDecision(
            tier="critical",
            reason="High spend pressure or unstable run quality",
            directives={
                "allow_expensive_steps": False,
                "retry_profile": "minimal",
                "model_profile": "cheap_only",
                "heartbeat_minutes": 20,
            },
            signals=signals,
        )

    if spend_ratio >= 0.5 or failure_rate >= 0.25:
        return OpsTierDecision(
            tier="low_compute",
            reason="Moderate budget or reliability pressure",
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
        reason="Budget and reliability within healthy range",
        directives={
            "allow_expensive_steps": True,
            "limit_optional_variants": False,
            "retry_profile": "standard",
            "model_profile": "quality",
            "heartbeat_minutes": 10,
        },
        signals=signals,
    )


def decision_to_dict(decision: OpsTierDecision) -> Dict[str, Any]:
    return asdict(decision)
