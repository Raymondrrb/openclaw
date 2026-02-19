"""Learning Gate — blocks pipeline advance when unresolved learnings exist.

A composite gate that runs 4 checks before allowing a pipeline stage
to proceed. Works alongside preflight_gate and circuit_breaker.

Checks:
  1. check_diff_policies  — policies.py SHA changed since last run?
  2. check_diff_soul      — SOUL file for stage's agent changed?
  3. check_regressions    — unresolved FAIL/BLOCKER events for video+stage?
  4. check_known_failures — recurring error patterns (count >= 3, no resolution)?

Stdlib only.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from tools.lib.common import project_root


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

@dataclass
class GateCheck:
    """Result of a single gate check."""
    name: str
    passed: bool
    reason: str = ""


@dataclass
class LearningGateResult:
    """Result of the full learning gate evaluation."""
    blocked: bool
    reason: str
    checks: list[GateCheck] = field(default_factory=list)


# Stage → primary agent mapping
STAGE_AGENT_MAP = {
    "research": "researcher",
    "script": "scriptwriter",
    "script-brief": "scriptwriter",
    "script-review": "reviewer",
    "assets": "dzine_producer",
    "tts": "publisher",
    "manifest": "davinci_editor",
    "day": "market_scout",
}


# ---------------------------------------------------------------------------
# State tracking
# ---------------------------------------------------------------------------

_STATE_DIR = project_root() / "state" / "learning_gate"


def _state_path(video_id: str) -> Path:
    d = _STATE_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{video_id}.json"


def _read_state(video_id: str) -> dict:
    import json
    path = _state_path(video_id)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_state(video_id: str, data: dict) -> None:
    from rayvault.io import atomic_write_json
    atomic_write_json(_state_path(video_id), data)


def _sha1_of_file(path: Path) -> str:
    if not path.is_file():
        return ""
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_diff_policies(video_id: str) -> GateCheck:
    """Check if policies.py changed since last gate pass for this video."""
    policies_path = project_root() / "rayvault" / "policies.py"
    current_sha = _sha1_of_file(policies_path)

    state = _read_state(video_id)
    last_sha = state.get("policies_sha", "")

    if not last_sha:
        # First run — record and pass
        state["policies_sha"] = current_sha
        _write_state(video_id, state)
        return GateCheck(name="diff_policies", passed=True, reason="First run, recorded baseline")

    if current_sha != last_sha:
        return GateCheck(
            name="diff_policies",
            passed=False,
            reason=f"policies.py changed (was {last_sha[:8]}, now {current_sha[:8]}). Review thresholds before proceeding.",
        )

    return GateCheck(name="diff_policies", passed=True)


def check_diff_soul(video_id: str, stage: str) -> GateCheck:
    """Check if the SOUL file for this stage's agent changed since last pass."""
    agent = STAGE_AGENT_MAP.get(stage, "")
    if not agent:
        return GateCheck(name="diff_soul", passed=True, reason=f"No agent mapped for stage '{stage}'")

    soul_path = project_root() / "agents" / "team" / f"SOUL_{agent}.md"
    current_sha = _sha1_of_file(soul_path)

    state = _read_state(video_id)
    soul_shas = state.get("soul_shas", {})
    last_sha = soul_shas.get(agent, "")

    if not last_sha:
        soul_shas[agent] = current_sha
        state["soul_shas"] = soul_shas
        _write_state(video_id, state)
        return GateCheck(name="diff_soul", passed=True, reason=f"First run for {agent}, recorded baseline")

    if current_sha != last_sha:
        return GateCheck(
            name="diff_soul",
            passed=False,
            reason=f"SOUL_{agent}.md changed. Review agent governance before proceeding.",
        )

    return GateCheck(name="diff_soul", passed=True)


def check_regressions(video_id: str, stage: str) -> GateCheck:
    """Check for unresolved FAIL/BLOCKER learning events for this video+stage."""
    from tools.learning_event import list_events

    events = list_events(video_id=video_id, component=stage)
    unresolved = [
        e for e in events
        if e.severity in ("FAIL", "BLOCKER")
        and e.status in ("open",)
    ]

    if unresolved:
        ids = ", ".join(e.event_id for e in unresolved[:3])
        return GateCheck(
            name="regressions",
            passed=False,
            reason=f"{len(unresolved)} unresolved {'/'.join(e.severity for e in unresolved[:3])} event(s) for {video_id}/{stage}: {ids}",
        )

    return GateCheck(name="regressions", passed=True)


def check_known_failures(stage: str) -> GateCheck:
    """Check for recurring error patterns (3+ occurrences, no resolution)."""
    from tools.lib.error_log import get_patterns

    patterns = get_patterns(min_count=3)
    blocking = [p for p in patterns if p.get("stage") == stage and p.get("unresolved", 0) > 0]

    if blocking:
        top = blocking[0]
        return GateCheck(
            name="known_failures",
            passed=False,
            reason=f"Recurring pattern in {stage}: \"{top['pattern']}\" ({top['count']}x, {top['unresolved']} unresolved)",
        )

    return GateCheck(name="known_failures", passed=True)


# ---------------------------------------------------------------------------
# Main gate
# ---------------------------------------------------------------------------

def learning_gate(video_id: str, stage: str) -> LearningGateResult:
    """Run all 4 learning gate checks.

    Returns LearningGateResult with blocked=True if any check fails.
    """
    from rayvault.policies import LEARNING_GATE_ENABLED

    if not LEARNING_GATE_ENABLED:
        return LearningGateResult(
            blocked=False,
            reason="Learning gate disabled via LEARNING_GATE_ENABLED=False",
            checks=[],
        )

    checks = [
        check_diff_policies(video_id),
        check_diff_soul(video_id, stage),
        check_regressions(video_id, stage),
        check_known_failures(stage),
    ]

    failed = [c for c in checks if not c.passed]

    if failed:
        reasons = "; ".join(c.reason for c in failed)
        # Record state update for passed checks
        state = _read_state(video_id)
        policies_path = project_root() / "rayvault" / "policies.py"
        state["policies_sha"] = _sha1_of_file(policies_path)
        agent = STAGE_AGENT_MAP.get(stage, "")
        if agent:
            soul_path = project_root() / "agents" / "team" / f"SOUL_{agent}.md"
            soul_shas = state.get("soul_shas", {})
            soul_shas[agent] = _sha1_of_file(soul_path)
            state["soul_shas"] = soul_shas
        _write_state(video_id, state)

        return LearningGateResult(
            blocked=True,
            reason=f"BLOCKED_FOR_LEARNING: {reasons}",
            checks=checks,
        )

    # All passed — update state
    state = _read_state(video_id)
    policies_path = project_root() / "rayvault" / "policies.py"
    state["policies_sha"] = _sha1_of_file(policies_path)
    agent = STAGE_AGENT_MAP.get(stage, "")
    if agent:
        soul_path = project_root() / "agents" / "team" / f"SOUL_{agent}.md"
        soul_shas = state.get("soul_shas", {})
        soul_shas[agent] = _sha1_of_file(soul_path)
        state["soul_shas"] = soul_shas
    state["last_passed"] = {
        "stage": stage,
        "timestamp": __import__("tools.lib.common", fromlist=["now_iso"]).now_iso(),
    }
    _write_state(video_id, state)

    return LearningGateResult(blocked=False, reason="All checks passed", checks=checks)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli() -> None:
    import sys

    args = sys.argv[1:]
    if len(args) < 2:
        print("Usage: python3 tools/learning_gate.py <video_id> <stage>")
        print("Stages: research, script, assets, tts, manifest, day")
        return

    video_id, stage = args[0], args[1]
    result = learning_gate(video_id, stage)

    if result.blocked:
        print(f"BLOCKED: {result.reason}")
        for c in result.checks:
            status = "PASS" if c.passed else "FAIL"
            print(f"  [{status}] {c.name}: {c.reason}")
        sys.exit(2)
    else:
        print(f"PASSED: {result.reason}")
        for c in result.checks:
            print(f"  [PASS] {c.name}: {c.reason}")


if __name__ == "__main__":
    _cli()
