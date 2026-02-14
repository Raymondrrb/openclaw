"""Central configuration contract for RayviewsLab worker infrastructure.

Single source of truth for:
- Lease, heartbeat, and polling parameters
- Panic taxonomy (reason keys + human labels + recommended actions)
- Health thresholds (latency, stale gate)
- Spool / checkpoint / state paths
- Environment variable loading
- Dual timezone helpers (UTC + America/Sao_Paulo)

Stdlib only — no external deps.

Usage:
    from tools.lib.config import load_worker_config, PANIC_REASONS, format_dual_time

    cfg, secrets = load_worker_config()
    print(cfg.heartbeat_interval_sec)
    print(PANIC_REASONS["panic_lost_lock"]["label"])
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from tools.lib.common import project_root, load_env_file


# ---------------------------------------------------------------------------
# Timezone helpers
# ---------------------------------------------------------------------------

TZ_UTC = timezone.utc
TZ_BRT = timezone(timedelta(hours=-3))  # America/Sao_Paulo standard


def format_dual_time(dt: datetime) -> str:
    """Format datetime as 'HH:MM UTC / HH:MM BRT (YYYY-MM-DD)'."""
    utc = dt.astimezone(TZ_UTC)
    brt = dt.astimezone(TZ_BRT)
    return f"{utc:%H:%M} UTC / {brt:%H:%M} BRT ({utc:%Y-%m-%d})"


# ---------------------------------------------------------------------------
# Panic taxonomy — controlled reason keys
# ---------------------------------------------------------------------------

PANIC_REASONS: Dict[str, Dict[str, str]] = {
    "panic_lost_lock": {
        "label": "Lock Lost",
        "emoji": "\U0001f6a8",  # rotating light
        "severity": "CRITICAL",
        "action": "Check for duplicate workers / short lease. Do NOT retry.",
    },
    "panic_heartbeat_uncertain": {
        "label": "Heartbeat Uncertain",
        "emoji": "\u26a0\ufe0f",  # warning
        "severity": "WARN",
        "action": "Check Wi-Fi/router; wait 2-5 min; run doctor --health.",
    },
    "panic_browser_frozen": {
        "label": "Browser Frozen",
        "emoji": "\u2744\ufe0f",  # snowflake
        "severity": "CRITICAL",
        "action": "Restart browser; check RAM/GPU; worker auto-resumes via claim_next.",
    },
    "panic_integrity_failure": {
        "label": "Integrity Failure",
        "emoji": "\u274c",  # cross mark
        "severity": "CRITICAL",
        "action": "Open dashboard — review evidence diff before proceeding.",
    },
}


def panic_template(
    reason_key: str,
    run_id: str,
    utc_ts: datetime,
    *,
    latency_ms: int | None = None,
    retry_count: int = 0,
    details_url: str | None = None,
) -> str:
    """Build a human-readable panic alert (plain text, Telegram-safe).

    Uses no special parse_mode characters that need escaping.
    """
    info = PANIC_REASONS.get(reason_key, {
        "label": reason_key, "emoji": "\u2753", "severity": "UNKNOWN",
        "action": "Investigate.",
    })

    severity = info.get("severity", "UNKNOWN")
    lines = [
        f"{info['emoji']} PANIC [{severity}]: {info['label']}",
        f"Run: ...{run_id[-8:]}",
        f"Time: {format_dual_time(utc_ts)}",
    ]
    if latency_ms is not None:
        lines.append(f"Latency: {latency_ms}ms")
    if retry_count:
        lines.append(f"Retries: {retry_count}")
    lines.append("")
    lines.append(f"Action: {info['action']}")
    if details_url:
        lines.append(f"Dashboard: {details_url}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Health thresholds
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HealthThresholds:
    """Thresholds for doctor health checks."""
    heartbeat_latency_warn_ms: int = 3000
    heartbeat_latency_crit_ms: int = 8000
    stale_gate_hours: int = 72
    ghost_run_hours: int = 48
    stale_worker_minutes: int = 30       # active worker with no heartbeat
    spool_max_retries: int = 3           # quarantine after N replay failures


# ---------------------------------------------------------------------------
# Worker configuration
# ---------------------------------------------------------------------------

@dataclass
class WorkerConfig:
    """All tunables for a worker instance."""
    worker_id: str = ""

    # Lease & heartbeat
    lease_minutes: int = 15
    heartbeat_interval_sec: int = 120
    heartbeat_jitter_sec: int = 15
    heartbeat_max_retries: int = 3

    # Polling
    poll_interval_sec: int = 30
    poll_jitter_sec: int = 15
    quarantine_sec: int = 45

    # Paths (relative to repo root)
    spool_dir: str = ""
    checkpoint_dir: str = ""
    state_dir: str = ""

    # Network
    rpc_timeout_sec: int = 10

    # Truncation limits
    max_worker_error_len: int = 500
    telegram_max_len: int = 4000

    # Health thresholds
    thresholds: HealthThresholds = field(default_factory=HealthThresholds)

    def __post_init__(self):
        root = str(project_root())
        if not self.spool_dir:
            self.spool_dir = os.path.join(root, "spool")
        if not self.checkpoint_dir:
            self.checkpoint_dir = os.path.join(root, "checkpoints")
        if not self.state_dir:
            self.state_dir = os.path.join(root, "state")


# ---------------------------------------------------------------------------
# Secrets (never serialized, never logged)
# ---------------------------------------------------------------------------

@dataclass
class SecretsConfig:
    """Environment secrets — loaded once, never written to disk."""
    supabase_url: str = ""
    supabase_service_key: str = ""
    telegram_bot_token: str = ""
    telegram_admin_chat_id: str = ""
    vercel_base_url: str = ""


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def load_worker_config(
    *,
    env_file: str | Path | None = None,
    worker_id: str = "",
) -> tuple[WorkerConfig, SecretsConfig]:
    """Load config from environment variables.

    Reads .env file if present (does not override existing env vars).
    Returns (WorkerConfig, SecretsConfig).
    """
    load_env_file(env_file)

    cfg = WorkerConfig(
        worker_id=worker_id or os.environ.get("WORKER_ID", ""),
        lease_minutes=int(os.environ.get("LEASE_MINUTES", "15")),
        heartbeat_interval_sec=int(os.environ.get("HEARTBEAT_INTERVAL_SEC", "120")),
        heartbeat_jitter_sec=int(os.environ.get("HEARTBEAT_JITTER_SEC", "15")),
        heartbeat_max_retries=int(os.environ.get("HEARTBEAT_MAX_RETRIES", "3")),
        poll_interval_sec=int(os.environ.get("POLL_INTERVAL_SEC", "30")),
        poll_jitter_sec=int(os.environ.get("POLL_JITTER_SEC", "15")),
        quarantine_sec=int(os.environ.get("QUARANTINE_SEC", "45")),
        rpc_timeout_sec=int(os.environ.get("RPC_TIMEOUT_SEC", "10")),
        max_worker_error_len=int(os.environ.get("MAX_WORKER_ERROR_LEN", "500")),
        telegram_max_len=int(os.environ.get("TELEGRAM_MAX_LEN", "4000")),
    )

    # Populate worker_id from hostname if still empty
    if not cfg.worker_id:
        import socket
        cfg.worker_id = socket.gethostname()

    secrets = SecretsConfig(
        supabase_url=os.environ.get("SUPABASE_URL", "").rstrip("/"),
        supabase_service_key=os.environ.get("SUPABASE_SERVICE_KEY", ""),
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        telegram_admin_chat_id=os.environ.get("TELEGRAM_ADMIN_CHAT_ID", ""),
        vercel_base_url=os.environ.get("VERCEL_BASE_URL", "").rstrip("/"),
    )

    return cfg, secrets
