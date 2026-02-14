"""Panic manager — Local First -> DB Second -> Telegram Third.

Guarantees:
1. Spool write is atomic (tempfile + fsync + os.replace) — never corrupts.
2. Filenames use ms + uuid — no collision even in bursts.
3. DB update checks response status and logs failure.
4. Event payload includes event_id (uuid) for idempotent replay.
5. Telegram uses plain text (no parse_mode) — no escaping issues.
6. report_panic() always returns fast — DB/Telegram are best-effort.

Stdlib + urllib only (no requests dependency).

Usage:
    from tools.lib.config import load_worker_config
    from tools.lib.panic import PanicManager

    cfg, secrets = load_worker_config()
    pm = PanicManager(cfg, secrets)
    pm.report_panic("panic_lost_lock", run_id, "heartbeat returned false")
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from tools.lib.config import WorkerConfig, SecretsConfig, panic_template


# ---------------------------------------------------------------------------
# Atomic write helper
# ---------------------------------------------------------------------------

def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    """Write JSON atomically: tempfile + fsync + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)  # atomic on same filesystem
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# PanicManager
# ---------------------------------------------------------------------------

class PanicManager:
    """Three-phase panic reporter: Spool -> DB -> Telegram.

    All three phases are independent — if DB or Telegram fail, the spool
    file persists for later replay via doctor.py.
    """

    def __init__(self, cfg: WorkerConfig, secrets: SecretsConfig):
        self.cfg = cfg
        self.secrets = secrets
        Path(self.cfg.spool_dir).mkdir(parents=True, exist_ok=True)

    def report_panic(
        self,
        reason_key: str,
        run_id: str,
        error_msg: str,
        *,
        latency_ms: int | None = None,
        retry_count: int = 0,
    ) -> str:
        """Report panic: spool locally, then best-effort DB + Telegram.

        Returns the spool filename (useful for logging / tests).
        """
        now = datetime.now(timezone.utc)
        event_id = str(uuid.uuid4())

        payload: Dict[str, Any] = {
            "event_id": event_id,
            "worker_id": self.cfg.worker_id,
            "run_id": run_id,
            "reason_key": reason_key,
            "error_msg": (error_msg or "")[:self.cfg.max_worker_error_len],
            "latency_ms": latency_ms,
            "retry_count": retry_count,
            "timestamp": now.isoformat(),
        }

        # 1) SPOOL LOCAL (atomic, never loses data)
        ts_ms = int(time.time() * 1000)
        spool_name = f"panic_{ts_ms}_{reason_key}_{event_id}.json"
        spool_path = Path(self.cfg.spool_dir) / spool_name
        _atomic_write_json(spool_path, payload)

        # 2) DB (best effort)
        self._try_update_db(payload)

        # 3) Telegram (best effort)
        self._try_send_telegram(reason_key, run_id, now,
                                latency_ms=latency_ms,
                                retry_count=retry_count)

        print(
            f"[panic] REPORTED: {reason_key} | run=...{run_id[-8:]} | spool={spool_name}",
            file=sys.stderr,
        )
        return spool_name

    # ----- internal: HTTP helpers -----

    def _headers(self) -> Dict[str, str]:
        key = self.secrets.supabase_service_key
        return {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    def _http_post(self, url: str, data: dict, *, timeout: int = 0) -> tuple[int, str]:
        """POST via urllib. Returns (status_code, body). Never raises."""
        import urllib.request
        import urllib.error

        if timeout <= 0:
            timeout = self.cfg.rpc_timeout_sec

        body_bytes = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body_bytes,
                                     headers=self._headers(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", errors="replace")
        except Exception as e:
            return 0, str(e)

    def _http_patch(self, url: str, data: dict, *, timeout: int = 0) -> tuple[int, str]:
        """PATCH via urllib. Returns (status_code, body). Never raises."""
        import urllib.request
        import urllib.error

        if timeout <= 0:
            timeout = self.cfg.rpc_timeout_sec

        body_bytes = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body_bytes,
                                     headers=self._headers(), method="PATCH")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", errors="replace")
        except Exception as e:
            return 0, str(e)

    # ----- internal: DB update -----

    def _try_update_db(self, payload: Dict[str, Any]) -> None:
        """Update pipeline_runs (worker_state=panic) + insert run_events."""
        if not self.secrets.supabase_url:
            return

        run_id = payload["run_id"]
        reason_key = payload["reason_key"]
        err = payload["error_msg"]

        # 1. PATCH pipeline_runs: worker_state=panic
        runs_url = (
            f"{self.secrets.supabase_url}/rest/v1/pipeline_runs"
            f"?id=eq.{run_id}"
        )
        patch_data = {
            "worker_state": "panic",
            "worker_last_error": f"{reason_key}: {err}"[:self.cfg.max_worker_error_len],
            "last_heartbeat_at": payload["timestamp"],
        }
        if payload.get("latency_ms") is not None:
            patch_data["last_heartbeat_latency_ms"] = payload["latency_ms"]

        status, body = self._http_patch(runs_url, patch_data)
        if status >= 300:
            print(
                f"[panic] DB runs PATCH failed: {status} {body[:200]}",
                file=sys.stderr,
            )

        # 2. POST run_events: forensic record with SRE columns
        from tools.lib.config import PANIC_REASONS
        severity = PANIC_REASONS.get(reason_key, {}).get("severity", "WARN")

        ev_url = f"{self.secrets.supabase_url}/rest/v1/run_events"
        event_data = {
            "run_id": run_id,
            "action_id": payload["event_id"],
            "event_id": payload["event_id"],
            "event_type": "worker_panic",
            "severity": severity,
            "reason_key": reason_key,
            "source": f"worker:{payload['worker_id']}",
            "occurred_at": payload["timestamp"],
            "payload": payload,
        }
        status2, body2 = self._http_post(ev_url, event_data)
        # 409 = unique violation → event already exists (idempotent, treat as ok)
        if status2 == 409:
            pass  # duplicate event_id — already recorded
        elif status2 >= 300:
            print(
                f"[panic] DB run_events POST failed: {status2} {body2[:200]}",
                file=sys.stderr,
            )

    # ----- internal: Telegram -----

    def _try_send_telegram(
        self,
        reason_key: str,
        run_id: str,
        now: datetime,
        *,
        latency_ms: int | None = None,
        retry_count: int = 0,
    ) -> None:
        """Send Telegram alert (plain text, no parse_mode)."""
        token = self.secrets.telegram_bot_token
        chat_id = self.secrets.telegram_admin_chat_id
        if not token or not chat_id:
            return

        details_url = None
        if self.secrets.vercel_base_url:
            details_url = f"{self.secrets.vercel_base_url}/runs/{run_id}"

        text = panic_template(
            reason_key=reason_key,
            run_id=run_id,
            utc_ts=now,
            latency_ms=latency_ms,
            retry_count=retry_count,
            details_url=details_url,
        )
        text = text[:self.cfg.telegram_max_len]

        tg_url = f"https://api.telegram.org/bot{token}/sendMessage"
        tg_payload = {
            "chat_id": chat_id,
            "text": text,
            # Plain text — no parse_mode to avoid escaping issues
        }

        import urllib.request
        import urllib.error

        body_bytes = json.dumps(tg_payload).encode("utf-8")
        req = urllib.request.Request(
            tg_url, data=body_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.rpc_timeout_sec) as resp:
                if resp.status >= 300:
                    print(
                        f"[panic] Telegram send failed: {resp.status}",
                        file=sys.stderr,
                    )
        except Exception as e:
            print(f"[panic] Telegram send error: {e}", file=sys.stderr)
