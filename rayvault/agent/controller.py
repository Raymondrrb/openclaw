"""RayVault cluster controller (Mac side).

Responsibilities:
- Read cluster node config from state/cluster/nodes.json
- Health-check Tailscale workers
- Submit jobs with signed envelopes (HMAC)
- Retry remote submit once; fallback to local execution when workers are unavailable
- Persist receipts/log snapshots for observability
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from rayvault.agent.jobs import JobExecutionError, execute_job
from rayvault.agent.protocol import Envelope, JOB_STEPS, build_envelope, compute_inputs_hash, normalize_step_name, utc_now_iso


MAC_ONLY_STEPS = {
    "DAVINCI_RENDER_FINAL",
    "DAVINCI_RENDER",
}

# Legacy Windows worker step naming differs from controller step names.
LEGACY_JOB_TYPE_MAP = {
    "TTS_RENDER_CHUNKS": "tts_render_chunks",
    "AUDIO_POSTCHECK": "audio_postcheck",
    "FFMPEG_PROBE": "ffprobe_analyze",
    "FRAME_SAMPLING": "frame_sampling",
    "OPENCLAW_TASK": "openclaw_task",
}

DEFAULT_STATE_DIR = Path("state/cluster")
DEFAULT_NODES_FILE = DEFAULT_STATE_DIR / "nodes.json"


class ControllerError(RuntimeError):
    """Raised for cluster controller failures."""


@dataclass
class ClusterNode:
    node_id: str
    host: str
    port: int
    role: str = "worker"
    enabled: bool = True
    timeout_sec: int = 15
    tags: List[str] = field(default_factory=list)

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


@dataclass
class SubmitResult:
    ok: bool
    mode: str
    run_id: str
    job_id: str
    step_name: str
    status: str
    node_id: str = ""
    idempotent: bool = False
    exit_code: int = 0
    message: str = ""
    receipt_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "mode": self.mode,
            "run_id": self.run_id,
            "job_id": self.job_id,
            "step_name": self.step_name,
            "status": self.status,
            "node_id": self.node_id,
            "idempotent": self.idempotent,
            "exit_code": self.exit_code,
            "message": self.message,
            "receipt_path": self.receipt_path,
        }


from rayvault.io import atomic_write_json as _atomic_write_json


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _http_json(
    method: str,
    url: str,
    *,
    body: Optional[Dict[str, Any]] = None,
    timeout: int = 15,
) -> Dict[str, Any]:
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = Request(url, data=data, method=method.upper(), headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            if not raw.strip():
                return {}
            return json.loads(raw)
    except HTTPError as exc:
        msg = exc.read().decode("utf-8", errors="replace")
        raise ControllerError(f"HTTP {exc.code} {url}: {msg[:500]}") from exc
    except URLError as exc:
        raise ControllerError(f"URL error {url}: {exc}") from exc


def _http_text(url: str, *, timeout: int = 15) -> str:
    req = Request(url, method="GET", headers={"Accept": "text/plain"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        msg = exc.read().decode("utf-8", errors="replace")
        raise ControllerError(f"HTTP {exc.code} {url}: {msg[:500]}") from exc
    except URLError as exc:
        raise ControllerError(f"URL error {url}: {exc}") from exc


def _extract_job_record(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Support both modern ({job:{...}}) and legacy (flat {...}) job payloads."""
    if isinstance(payload.get("job"), dict):
        return payload["job"]
    return payload


def _legacy_job_type(step_name: str) -> str:
    if not step_name:
        return "unknown"
    return LEGACY_JOB_TYPE_MAP.get(step_name, step_name.lower())


def _job_is_success(job_obj: Dict[str, Any]) -> bool:
    status = str(job_obj.get("status", "")).strip().lower()
    if status in {"succeeded"}:
        return True
    if status in {"failed", "error", "cancelled"}:
        return False
    if status == "completed":
        if job_obj.get("error") not in (None, "", {}):
            return False
        result = job_obj.get("result")
        if isinstance(result, dict):
            rs = str(result.get("status", "")).strip().lower()
            if rs in {"error", "failed", "failure"}:
                return False
        return True
    return False


def _build_hmac_candidates(body: Dict[str, Any]) -> List[str]:
    stripped = {k: v for k, v in body.items() if k != "auth_token"}
    candidates: List[str] = []

    job_type = str(stripped.get("job_type", "")).strip()
    job_id = str(stripped.get("job_id", "")).strip()
    run_id = str(stripped.get("run_id", "")).strip()
    step_name = str(stripped.get("step_name", "")).strip()

    if job_type:
        candidates.append(job_type)
    if job_id and job_type:
        candidates.append(f"{job_id}|{job_type}")
    if run_id and job_id and step_name:
        candidates.append(f"{run_id}|{job_id}|{step_name}")

    # Strongest option in worker v0.5.0: sorted body fields (excluding auth_token)
    all_fields = "|".join(str(v) for k, v in sorted(stripped.items()))
    if all_fields:
        candidates.append(all_fields)

    return candidates


def _hmac_token(secret: str, message: str) -> str:
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


class RayVaultController:
    def __init__(
        self,
        *,
        nodes_file: Path = DEFAULT_NODES_FILE,
        cluster_secret: str = "",
    ):
        self.nodes_file = nodes_file.expanduser().resolve()
        if not self.nodes_file.exists():
            raise ControllerError(f"nodes config not found: {self.nodes_file}")

        cfg = _read_json(self.nodes_file)
        self.config = cfg
        secret_env = str((cfg.get("auth") or {}).get("secret_env") or "RAYVAULT_CLUSTER_SECRET")
        if cluster_secret:
            secret_value = str(cluster_secret).strip()
            secret_source = "cli"
        else:
            candidates = [
                (secret_env, os.environ.get(secret_env, "")),
                ("RAYVAULT_CLUSTER_SECRET_CURRENT", os.environ.get("RAYVAULT_CLUSTER_SECRET_CURRENT", "")),
                ("RAYVAULT_CLUSTER_SECRET", os.environ.get("RAYVAULT_CLUSTER_SECRET", "")),
            ]
            secret_value = ""
            secret_source = ""
            for name, value in candidates:
                v = str(value or "").strip()
                if v:
                    secret_value = v
                    secret_source = name
                    break
        self.cluster_secret = secret_value
        self.cluster_secret_source = secret_source
        if not self.cluster_secret:
            raise ControllerError(
                f"missing cluster secret. Set env {secret_env} (or RAYVAULT_CLUSTER_SECRET_CURRENT / RAYVAULT_CLUSTER_SECRET) "
                "or pass --cluster-secret"
            )

        self.cluster_secret_previous = str(os.environ.get("RAYVAULT_CLUSTER_SECRET_PREVIOUS", "")).strip()
        self.auth_mode = str(os.environ.get("RAYVAULT_CONTROLLER_AUTH_MODE", "hmac_strict")).strip().lower()
        self.allow_plain_fallback = str(os.environ.get("RAYVAULT_ALLOW_PLAIN_FALLBACK", "0")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.secret_candidates: List[str] = [self.cluster_secret]
        if self.cluster_secret_previous and self.cluster_secret_previous != self.cluster_secret:
            self.secret_candidates.append(self.cluster_secret_previous)

        state_root = Path(str(cfg.get("state_dir") or DEFAULT_STATE_DIR)).expanduser().resolve()
        self.state_dir = state_root
        self.receipts_root = self.state_dir / "receipts"
        self.receipts_root.mkdir(parents=True, exist_ok=True)

        controller_cfg = cfg.get("controller") if isinstance(cfg.get("controller"), dict) else {}
        self.local_workspace_root = Path(
            str(controller_cfg.get("local_workspace_root") or self.state_dir / "local_worker_data")
        ).expanduser().resolve()
        self.local_workspace_root.mkdir(parents=True, exist_ok=True)

        try:
            self.request_timeout_sec = int(controller_cfg.get("request_timeout_sec", 15) or 15)
        except (ValueError, TypeError):
            self.request_timeout_sec = 15
        try:
            self.remote_poll_interval_sec = float(controller_cfg.get("poll_interval_sec", 2.0) or 2.0)
        except (ValueError, TypeError):
            self.remote_poll_interval_sec = 2.0
        try:
            self.remote_poll_timeout_sec = int(controller_cfg.get("poll_timeout_sec", 900) or 900)
        except (ValueError, TypeError):
            self.remote_poll_timeout_sec = 900

        self.nodes = self._load_nodes(cfg)
        self._caps_cache: Dict[str, Dict[str, Any]] = {}

    def _load_nodes(self, cfg: Dict[str, Any]) -> List[ClusterNode]:
        raw_nodes = cfg.get("nodes") if isinstance(cfg.get("nodes"), list) else []
        out: List[ClusterNode] = []
        for item in raw_nodes:
            if not isinstance(item, dict):
                continue
            node_id = str(item.get("node_id", "")).strip()
            host = str(item.get("host", "")).strip()
            try:
                port = int(item.get("port", 0) or 0)
            except (ValueError, TypeError):
                port = 0
            if not node_id or not host or port <= 0:
                continue
            try:
                _timeout = int(item.get("timeout_sec", self.request_timeout_sec) or self.request_timeout_sec)
            except (ValueError, TypeError):
                _timeout = self.request_timeout_sec
            out.append(
                ClusterNode(
                    node_id=node_id,
                    host=host,
                    port=port,
                    role=str(item.get("role", "worker") or "worker").strip().lower(),
                    enabled=bool(item.get("enabled", True)),
                    timeout_sec=_timeout,
                    tags=[str(x) for x in item.get("tags", []) if str(x).strip()],
                )
            )
        return out

    def enabled_workers(self) -> List[ClusterNode]:
        return [n for n in self.nodes if n.enabled and n.role == "worker"]

    def healthcheck(self) -> Dict[str, Any]:
        rows: List[Dict[str, Any]] = []
        for node in self.enabled_workers():
            started = time.time()
            ok = False
            error = ""
            payload: Dict[str, Any] = {}
            try:
                payload = _http_json("GET", f"{node.base_url}/health", timeout=node.timeout_sec)
                ok = bool(payload.get("ok", False))
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
            rows.append(
                {
                    "node_id": node.node_id,
                    "host": node.host,
                    "port": node.port,
                    "ok": ok,
                    "elapsed_ms": int((time.time() - started) * 1000),
                    "worker_id": payload.get("worker_id") if isinstance(payload, dict) else None,
                    "worker_version": payload.get("version") if isinstance(payload, dict) else None,
                    "queue_depth": payload.get("queue_depth") if isinstance(payload, dict) else None,
                    "caps": payload.get("caps") if isinstance(payload, dict) else None,
                    "error": error,
                }
            )

        return {
            "ok": any(r["ok"] for r in rows),
            "ts": utc_now_iso(),
            "controller_auth_source": self.cluster_secret_source,
            "controller_auth_mode": self.auth_mode,
            "workers": rows,
        }

    def _signed_query(self, *, run_id: str, job_id: str, step_name: str, inputs_hash: str) -> str:
        env = build_envelope(
            run_id=run_id,
            job_id=job_id,
            step_name=step_name,
            inputs_hash=inputs_hash,
            secret=self.cluster_secret,
            timestamp=utc_now_iso(),
        )
        return urlencode(env)

    def _secret_query(self, secret: str = "") -> str:
        return urlencode({"auth_token": secret or self.cluster_secret})

    def _sign_legacy_body(self, body: Dict[str, Any], *, secret: str = "", candidate: int = -1) -> Dict[str, Any]:
        sec = secret or self.cluster_secret
        candidates = _build_hmac_candidates(body)
        if not candidates:
            raise ControllerError("Cannot build HMAC candidates from empty body")
        idx = candidate if -len(candidates) <= candidate < len(candidates) else -1
        token = _hmac_token(sec, candidates[idx])
        out = dict(body)
        out["auth_token"] = token
        return out

    def _http_json_with_auth_fallback(
        self,
        method: str,
        *,
        signed_url: str,
        secret_urls: List[str],
        body: Optional[Dict[str, Any]] = None,
        timeout: int,
    ) -> Dict[str, Any]:
        try:
            return _http_json(method, signed_url, body=body, timeout=timeout)
        except Exception as first_exc:
            for secret_url in secret_urls:
                try:
                    return _http_json(method, secret_url, body=body, timeout=timeout)
                except Exception:
                    continue
            raise first_exc

    def _download_remote_file(
        self,
        *,
        node: ClusterNode,
        url_signed: str,
        url_secrets: List[str],
        out_path: Path,
    ) -> None:
        req = Request(url_signed, method="GET")
        try:
            with urlopen(req, timeout=node.timeout_sec) as resp:
                data = resp.read()
        except Exception as first_exc:
            data = b""
            ok = False
            for url_secret in url_secrets:
                try:
                    req = Request(url_secret, method="GET")
                    with urlopen(req, timeout=node.timeout_sec) as resp:
                        data = resp.read()
                    ok = True
                    break
                except Exception:
                    continue
            if not ok:
                raise first_exc
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(out_path.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, out_path)

    def _receipt_dir(self, run_id: str, job_id: str) -> Path:
        out = self.receipts_root / run_id / job_id
        out.mkdir(parents=True, exist_ok=True)
        return out

    def _write_remote_artifacts_snapshot(
        self,
        *,
        node: ClusterNode,
        run_id: str,
        job_id: str,
        inputs_hash: str,
        status_payload: Dict[str, Any],
    ) -> Tuple[Path, Dict[str, Any]]:
        receipt_dir = self._receipt_dir(run_id, job_id)

        logs_query = self._signed_query(
            run_id=run_id,
            job_id=job_id,
            step_name="JOB_LOGS",
            inputs_hash=inputs_hash,
        )
        logs_url_signed = f"{node.base_url}/job/{job_id}/logs?{logs_query}"
        logs_url_secrets = [
            f"{node.base_url}/job/{job_id}/logs?{self._secret_query(sec)}" for sec in self.secret_candidates
        ]
        logs_txt = ""
        try:
            logs_payload = self._http_json_with_auth_fallback(
                "GET",
                signed_url=logs_url_signed,
                secret_urls=logs_url_secrets,
                timeout=node.timeout_sec,
            )
            if isinstance(logs_payload, dict) and isinstance(logs_payload.get("logs"), list):
                lines: List[str] = []
                for item in logs_payload["logs"]:
                    if isinstance(item, dict):
                        lines.append(f"{item.get('ts', '')} {item.get('msg', '')}".strip())
                    else:
                        lines.append(str(item))
                logs_txt = "\n".join(lines)
            else:
                logs_txt = json.dumps(logs_payload, ensure_ascii=False, indent=2)
        except Exception:
            try:
                logs_txt = _http_text(logs_url_signed, timeout=node.timeout_sec)
            except Exception:
                logs_txt = ""
                for logs_url_secret in logs_url_secrets:
                    try:
                        logs_txt = _http_text(logs_url_secret, timeout=node.timeout_sec)
                        break
                    except Exception:
                        continue
        logs_path = receipt_dir / "worker.log"
        logs_path.write_text(logs_txt, encoding="utf-8")

        artifacts_query = self._signed_query(
            run_id=run_id,
            job_id=job_id,
            step_name="JOB_ARTIFACTS",
            inputs_hash=inputs_hash,
        )
        artifacts_payload = self._http_json_with_auth_fallback(
            "GET",
            signed_url=f"{node.base_url}/job/{job_id}/artifacts?{artifacts_query}",
            secret_urls=[
                f"{node.base_url}/job/{job_id}/artifacts?{self._secret_query(sec)}" for sec in self.secret_candidates
            ],
            timeout=node.timeout_sec,
        )

        artifact_rows = artifacts_payload.get("artifacts") if isinstance(artifacts_payload, dict) else []
        artifact_rows = artifact_rows if isinstance(artifact_rows, list) else []
        artifact_dir = receipt_dir / "artifacts"
        downloaded_files: List[Dict[str, Any]] = []

        for row in artifact_rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name", "")).strip()
            if not name:
                continue
            safe_name = name.replace("\\", "_").replace("/", "_")
            out_path = artifact_dir / safe_name
            artifact_name_q = quote(name, safe="")
            signed_u = f"{node.base_url}/job/{job_id}/artifacts/{artifact_name_q}?{artifacts_query}"
            secret_urls = [
                f"{node.base_url}/job/{job_id}/artifacts/{artifact_name_q}?{self._secret_query(sec)}"
                for sec in self.secret_candidates
            ]
            try:
                self._download_remote_file(
                    node=node,
                    url_signed=signed_u,
                    url_secrets=secret_urls,
                    out_path=out_path,
                )
                downloaded_files.append(
                    {
                        "name": name,
                        "local_path": str(out_path),
                        "size": out_path.stat().st_size if out_path.exists() else None,
                        "sha256": row.get("sha256"),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                downloaded_files.append(
                    {
                        "name": name,
                        "local_path": "",
                        "error": str(exc),
                        "sha256": row.get("sha256"),
                    }
                )

        # Optional bulk zip download (best-effort)
        zip_path = receipt_dir / "artifacts.zip"
        try:
            self._download_remote_file(
                node=node,
                url_signed=f"{node.base_url}/job/{job_id}/artifacts.zip?{artifacts_query}",
                url_secrets=[
                    f"{node.base_url}/job/{job_id}/artifacts.zip?{self._secret_query(sec)}"
                    for sec in self.secret_candidates
                ],
                out_path=zip_path,
            )
        except Exception:
            pass

        job_obj = _extract_job_record(status_payload)
        status_text = str(job_obj.get("status", "unknown")).strip().lower()
        success = _job_is_success(job_obj)
        exit_code = job_obj.get("exit_code")
        if exit_code is None:
            if status_text in {"succeeded", "completed", "failed", "error", "cancelled"}:
                exit_code = 0 if success else 1
            else:
                exit_code = 1

        receipt = {
            "mode": "remote",
            "node_id": node.node_id,
            "run_id": run_id,
            "job_id": job_id,
            "inputs_hash": inputs_hash,
            "status": job_obj.get("status", "unknown"),
            "exit_code": int(exit_code or 0),
            "finished_at": utc_now_iso(),
            "job_status": job_obj,
            "artifacts": artifact_rows,
            "downloaded_artifacts": downloaded_files,
            "artifacts_dir": str(artifact_dir),
            "artifacts_zip": str(zip_path) if zip_path.exists() else "",
            "remote_receipt_path": artifacts_payload.get("receipt_path") if isinstance(artifacts_payload, dict) else "",
            "log_path": str(logs_path),
        }
        receipt_path = receipt_dir / "job_receipt.json"
        _atomic_write_json(receipt_path, receipt)
        return receipt_path, receipt

    def _poll_remote_status(
        self,
        *,
        node: ClusterNode,
        run_id: str,
        job_id: str,
        inputs_hash: str,
        timeout_sec: int,
    ) -> Tuple[Path, Dict[str, Any]]:
        deadline = time.time() + max(5, timeout_sec)
        while time.time() < deadline:
            query = self._signed_query(
                run_id=run_id,
                job_id=job_id,
                step_name="JOB_STATUS",
                inputs_hash=inputs_hash,
            )
            payload = self._http_json_with_auth_fallback(
                "GET",
                signed_url=f"{node.base_url}/job/{job_id}?{query}",
                secret_urls=[f"{node.base_url}/job/{job_id}?{self._secret_query(sec)}" for sec in self.secret_candidates],
                timeout=node.timeout_sec,
            )
            status = str(_extract_job_record(payload).get("status", "")).strip().lower()
            if status in {"succeeded", "failed", "cancelled", "completed", "error"}:
                return self._write_remote_artifacts_snapshot(
                    node=node,
                    run_id=run_id,
                    job_id=job_id,
                    inputs_hash=inputs_hash,
                    status_payload=payload,
                )
            time.sleep(self.remote_poll_interval_sec)

        raise ControllerError(
            f"remote job polling timed out after {timeout_sec}s: node={node.node_id} job_id={job_id}"
        )

    def _local_cache_path(self, *, step_name: str, inputs_hash: str) -> Path:
        safe = f"{step_name.lower()}_{inputs_hash}.json"
        return self.state_dir / "local_cache" / safe

    def _run_local(
        self,
        *,
        run_id: str,
        job_id: str,
        step_name: str,
        inputs_hash: str,
        payload: Dict[str, Any],
        force: bool,
    ) -> SubmitResult:
        cache_path = self._local_cache_path(step_name=step_name, inputs_hash=inputs_hash)
        if cache_path.exists() and not force:
            cached = _read_json(cache_path)
            return SubmitResult(
                ok=bool(cached.get("ok", True)),
                mode="local_cached",
                run_id=run_id,
                job_id=job_id,
                step_name=step_name,
                status=str(cached.get("status", "succeeded")),
                node_id="local",
                idempotent=True,
                exit_code=int(cached.get("exit_code", 0) or 0),
                message="cached local receipt",
                receipt_path=str(cached.get("receipt_path", "")),
            )

        started = time.time()
        receipt_dir = self._receipt_dir(run_id, job_id)
        logs_path = receipt_dir / "worker.log"
        env = Envelope(
            run_id=run_id,
            job_id=job_id,
            step_name=step_name,
            inputs_hash=inputs_hash,
            timestamp=utc_now_iso(),
            auth_token="local",
        )

        try:
            out = execute_job(env, payload, workspace_root=self.local_workspace_root)
            status = str(out.get("status", "succeeded"))
            exit_code = int(out.get("exit_code", 0) or 0)
            logs_path.write_text(
                f"[{utc_now_iso()}] local fallback executed step={step_name} status={status} exit={exit_code}\n",
                encoding="utf-8",
            )
            receipt = {
                "mode": "local",
                "run_id": run_id,
                "job_id": job_id,
                "step_name": step_name,
                "inputs_hash": inputs_hash,
                "status": status,
                "exit_code": exit_code,
                "started_at": dt.datetime.fromtimestamp(started, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "finished_at": utc_now_iso(),
                "duration_ms": int((time.time() - started) * 1000),
                "metrics": out.get("metrics") if isinstance(out.get("metrics"), dict) else {},
                "artifacts": out.get("artifacts") if isinstance(out.get("artifacts"), list) else [],
                "log_path": str(logs_path),
            }
            receipt_path = receipt_dir / "job_receipt.json"
            _atomic_write_json(receipt_path, receipt)
            _atomic_write_json(
                cache_path,
                {
                    "ok": status == "succeeded",
                    "status": status,
                    "exit_code": exit_code,
                    "receipt_path": str(receipt_path),
                },
            )
            return SubmitResult(
                ok=status == "succeeded",
                mode="local",
                run_id=run_id,
                job_id=job_id,
                step_name=step_name,
                status=status,
                node_id="local",
                exit_code=exit_code,
                receipt_path=str(receipt_path),
            )
        except JobExecutionError as exc:
            logs_path.write_text(
                f"[{utc_now_iso()}] local fallback failed code={exc.code} message={exc.message}\n",
                encoding="utf-8",
            )
            receipt = {
                "mode": "local",
                "run_id": run_id,
                "job_id": job_id,
                "step_name": step_name,
                "inputs_hash": inputs_hash,
                "status": "failed",
                "exit_code": 2,
                "error_code": exc.code,
                "error_message": exc.message,
                "finished_at": utc_now_iso(),
                "log_path": str(logs_path),
            }
            receipt_path = receipt_dir / "job_receipt.json"
            _atomic_write_json(receipt_path, receipt)
            return SubmitResult(
                ok=False,
                mode="local",
                run_id=run_id,
                job_id=job_id,
                step_name=step_name,
                status="failed",
                node_id="local",
                exit_code=2,
                message=f"{exc.code}: {exc.message}",
                receipt_path=str(receipt_path),
            )

    def register_caps(self, node: ClusterNode, *, run_id: str = "cluster_probe") -> Dict[str, Any]:
        inputs_hash = compute_inputs_hash({"node_id": node.node_id, "action": "register_caps"})
        env = build_envelope(
            run_id=run_id,
            job_id=f"caps-{node.node_id}",
            step_name="REGISTER_CAPS",
            inputs_hash=inputs_hash,
            secret=self.cluster_secret,
            timestamp=utc_now_iso(),
        )
        body = dict(env)
        body["message_type"] = "register_caps"
        body["payload"] = {"controller": "rayvault"}
        modern_error = None
        try:
            return _http_json("POST", f"{node.base_url}/caps", body=body, timeout=node.timeout_sec)
        except ControllerError as exc:
            modern_error = exc

        # Legacy v0.5 path: HMAC token in body
        legacy_base = {
            "run_id": run_id,
            "job_id": f"caps-{node.node_id}",
            "step_name": "register_caps",
            "job_type": "caps",
            "controller": "rayvault",
        }
        for idx, secret in enumerate(self.secret_candidates):
            try:
                signed = self._sign_legacy_body(legacy_base, secret=secret, candidate=-1)
                out = _http_json("POST", f"{node.base_url}/caps", body=signed, timeout=node.timeout_sec)
                if isinstance(out, dict):
                    out["_compat_mode"] = "legacy_hmac_v05"
                    out["_auth_secret_index"] = idx
                return out
            except ControllerError:
                continue

        # Optional plain fallback (disabled by default in strict mode)
        if self.allow_plain_fallback:
            for idx, secret in enumerate(self.secret_candidates):
                try:
                    plain = {"auth_token": secret}
                    out = _http_json("POST", f"{node.base_url}/caps", body=plain, timeout=node.timeout_sec)
                    if isinstance(out, dict):
                        out["_compat_mode"] = "legacy_plain_token"
                        out["_auth_secret_index"] = idx
                    return out
                except ControllerError:
                    continue

        raise ControllerError(
            f"{modern_error}; legacy /caps HMAC auth failed and plain fallback={'enabled' if self.allow_plain_fallback else 'disabled'}"
        )

    def _cached_caps(self, node: ClusterNode) -> Dict[str, Any]:
        if node.node_id in self._caps_cache:
            return self._caps_cache[node.node_id]
        caps = self.register_caps(node, run_id="cluster_caps_cache")
        self._caps_cache[node.node_id] = caps if isinstance(caps, dict) else {}
        return self._caps_cache[node.node_id]

    @staticmethod
    def _caps_payload(caps_response: Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(caps_response.get("capabilities"), dict):
            return caps_response["capabilities"]
        return caps_response if isinstance(caps_response, dict) else {}

    def _worker_meets_requirements(self, node: ClusterNode, requirements: Dict[str, Any]) -> Tuple[bool, str]:
        if not requirements:
            return True, ""
        caps_resp = self._cached_caps(node)
        caps = self._caps_payload(caps_resp)

        os_in = requirements.get("os_in")
        if isinstance(os_in, list) and os_in:
            wanted = {str(x).strip().lower() for x in os_in if str(x).strip()}
            got_os = str(caps.get("os") or caps.get("platform") or "").strip().lower()
            if got_os and got_os not in wanted:
                return False, f"os={got_os} not in {sorted(wanted)}"

        if bool(requirements.get("davinci_available", False)) and not bool(caps.get("davinci_available", False)):
            return False, "davinci_available=false"
        if bool(requirements.get("gpu_required", False)) and not bool(caps.get("gpu", False)):
            return False, "gpu_required=true but gpu=false"

        try:
            min_ram = float(requirements.get("min_ram_gb", 0) or 0)
        except (ValueError, TypeError):
            min_ram = 0.0
        try:
            min_vram = float(requirements.get("min_vram_gb", 0) or 0)
        except (ValueError, TypeError):
            min_vram = 0.0
        try:
            ram_gb = float(caps.get("ram_gb", 0) or 0)
        except (ValueError, TypeError):
            ram_gb = 0.0
        try:
            vram_gb = float(caps.get("vram_gb", 0) or 0)
        except (ValueError, TypeError):
            vram_gb = 0.0

        if min_ram > 0 and ram_gb < min_ram:
            return False, f"ram_gb={ram_gb} < min_ram_gb={min_ram}"
        if min_vram > 0 and vram_gb < min_vram:
            return False, f"vram_gb={vram_gb} < min_vram_gb={min_vram}"

        return True, ""

    def _remote_step_supported(self, node: ClusterNode, step_name: str) -> Tuple[bool, str]:
        """Return (is_supported, reason)."""
        caps = self._cached_caps(node)
        compat = str(caps.get("_compat_mode", "")).strip()
        if not compat.startswith("legacy_"):
            # Modern worker contract handled by protocol envelopes.
            return True, ""

        supported: List[str] = []
        if isinstance(caps.get("supported_steps"), list):
            supported.extend(str(x).strip().lower() for x in caps["supported_steps"])
        if isinstance(caps.get("capabilities"), list):
            supported.extend(str(x).strip().lower() for x in caps["capabilities"])
        legacy_step = _legacy_job_type(step_name)
        if legacy_step in set(supported):
            return True, ""

        return False, f"remote worker missing capability '{legacy_step}'"

    def sync_remote_artifacts(
        self,
        *,
        node: ClusterNode,
        run_id: str,
        job_id: str,
        inputs_hash: str = "",
    ) -> Tuple[Path, Dict[str, Any]]:
        job_query = self._signed_query(
            run_id=run_id,
            job_id=job_id,
            step_name="JOB_STATUS",
            inputs_hash=inputs_hash or compute_inputs_hash({"job_id": job_id}),
        )
        status_payload = self._http_json_with_auth_fallback(
            "GET",
            signed_url=f"{node.base_url}/job/{job_id}?{job_query}",
            secret_urls=[f"{node.base_url}/job/{job_id}?{self._secret_query(sec)}" for sec in self.secret_candidates],
            timeout=node.timeout_sec,
        )
        job_obj = _extract_job_record(status_payload)
        guessed_hash = inputs_hash or str(job_obj.get("inputs_hash") or compute_inputs_hash({"job_id": job_id}))
        return self._write_remote_artifacts_snapshot(
            node=node,
            run_id=run_id,
            job_id=job_id,
            inputs_hash=guessed_hash,
            status_payload=status_payload,
        )

    def submit_job(
        self,
        *,
        run_id: str,
        job_id: str,
        step_name: str,
        payload: Dict[str, Any],
        requirements: Optional[Dict[str, Any]] = None,
        inputs_hash: str = "",
        force: bool = False,
        allow_local_fallback: bool = True,
    ) -> SubmitResult:
        step = normalize_step_name(step_name)
        hash_value = (inputs_hash or compute_inputs_hash(payload or {})).strip().lower()
        reqs = requirements if isinstance(requirements, dict) else {}
        if not reqs and isinstance(payload.get("requirements"), dict):
            reqs = payload["requirements"]

        if step in MAC_ONLY_STEPS or step not in JOB_STEPS:
            return self._run_local(
                run_id=run_id,
                job_id=job_id,
                step_name=step,
                inputs_hash=hash_value,
                payload=payload,
                force=force,
            )

        workers = self.enabled_workers()
        if not workers:
            if allow_local_fallback:
                return self._run_local(
                    run_id=run_id,
                    job_id=job_id,
                    step_name=step,
                    inputs_hash=hash_value,
                    payload=payload,
                    force=force,
                )
            raise ControllerError("No enabled worker nodes")

        candidate_workers: List[ClusterNode] = []
        req_rejections: List[str] = []
        for node in workers:
            ok, reason = self._worker_meets_requirements(node, reqs)
            if ok:
                candidate_workers.append(node)
            else:
                req_rejections.append(f"{node.node_id}: {reason}")

        if not candidate_workers:
            msg = "No worker satisfies requirements"
            if req_rejections:
                msg += f" ({'; '.join(req_rejections)})"
            if allow_local_fallback:
                fallback = self._run_local(
                    run_id=run_id,
                    job_id=job_id,
                    step_name=step,
                    inputs_hash=hash_value,
                    payload=payload,
                    force=force,
                )
                if fallback.message:
                    fallback.message = f"{msg}; {fallback.message}"
                else:
                    fallback.message = f"{msg}; used local fallback"
                return fallback
            raise ControllerError(msg)

        attempts = 2  # initial + one retry
        last_error = ""
        fatal_remote_error = False
        for attempt in range(1, attempts + 1):
            unsupported_count = 0
            for node in candidate_workers:
                try:
                    supported, reason = self._remote_step_supported(node, step)
                    if not supported:
                        last_error = f"{node.node_id}: {reason}"
                        unsupported_count += 1
                        continue

                    caps = self._caps_cache.get(node.node_id, {})
                    compat_mode = str((caps or {}).get("_compat_mode", "")).strip()

                    if compat_mode.startswith("legacy_"):
                        submitted = {}
                        legacy_base = {
                            "run_id": run_id,
                            "job_id": job_id,
                            "step_name": step.lower(),
                            "job_type": _legacy_job_type(step),
                            "params": payload or {},
                        }
                        submitted_ok = False
                        for idx, sec in enumerate(self.secret_candidates):
                            try:
                                signed_body = self._sign_legacy_body(legacy_base, secret=sec, candidate=-1)
                                submitted = _http_json(
                                    "POST",
                                    f"{node.base_url}/job",
                                    body=signed_body,
                                    timeout=node.timeout_sec,
                                )
                                if isinstance(submitted, dict):
                                    submitted["_auth_mode"] = "hmac_strong"
                                    submitted["_auth_secret_index"] = idx
                                submitted_ok = True
                                break
                            except ControllerError:
                                continue

                        if not submitted_ok and self.allow_plain_fallback:
                            for idx, sec in enumerate(self.secret_candidates):
                                try:
                                    plain_body = dict(legacy_base)
                                    plain_body["auth_token"] = sec
                                    submitted = _http_json(
                                        "POST",
                                        f"{node.base_url}/job",
                                        body=plain_body,
                                        timeout=node.timeout_sec,
                                    )
                                    if isinstance(submitted, dict):
                                        submitted["_auth_mode"] = "plain_fallback"
                                        submitted["_auth_secret_index"] = idx
                                    submitted_ok = True
                                    break
                                except ControllerError:
                                    continue

                        if not submitted_ok:
                            raise ControllerError(
                                f"{node.node_id}: legacy job submit auth failed (hmac and plain={self.allow_plain_fallback})"
                            )
                    else:
                        env = build_envelope(
                            run_id=run_id,
                            job_id=job_id,
                            step_name=step,
                            inputs_hash=hash_value,
                            secret=self.cluster_secret,
                            timestamp=utc_now_iso(),
                        )
                        body = dict(env)
                        body["message_type"] = "submit_job"
                        body["payload"] = payload or {}
                        submitted = _http_json("POST", f"{node.base_url}/job", body=body, timeout=node.timeout_sec)
                    submitted_job_id = (
                        str((_extract_job_record(submitted).get("job_id") or job_id)).strip() or job_id
                    )

                    receipt_path, receipt = self._poll_remote_status(
                        node=node,
                        run_id=run_id,
                        job_id=submitted_job_id,
                        inputs_hash=hash_value,
                        timeout_sec=self.remote_poll_timeout_sec,
                    )
                    job_status = str(receipt.get("status", "unknown"))
                    ok_status = _job_is_success(
                        receipt.get("job_status")
                        if isinstance(receipt.get("job_status"), dict)
                        else {"status": job_status}
                    )
                    if not ok_status:
                        last_error = (
                            f"{node.node_id}: remote job failed status={job_status} "
                            f"receipt={receipt_path}"
                        )
                        continue
                    return SubmitResult(
                        ok=ok_status,
                        mode="remote",
                        run_id=run_id,
                        job_id=submitted_job_id,
                        step_name=step,
                        status=job_status,
                        node_id=node.node_id,
                        idempotent=bool(submitted.get("idempotent", False)),
                        exit_code=int(receipt.get("exit_code", 0) or 0),
                        message="",
                        receipt_path=str(receipt_path),
                    )
                except Exception as exc:  # noqa: BLE001
                    last_error = str(exc)
                    low = last_error.lower()
                    if "does not support" in low or "missing job_type" in low:
                        fatal_remote_error = True
                    continue
            if unsupported_count == len(candidate_workers):
                fatal_remote_error = True
            if fatal_remote_error:
                break
            if attempt < attempts:
                time.sleep(2.0)

        if allow_local_fallback:
            fallback = self._run_local(
                run_id=run_id,
                job_id=job_id,
                step_name=step,
                inputs_hash=hash_value,
                payload=payload,
                force=force,
            )
            if fallback.message:
                fallback.message = f"remote failed ({last_error}); {fallback.message}"
            else:
                fallback.message = f"remote failed ({last_error}); used local fallback"
            return fallback

        raise ControllerError(f"Remote submit failed after retries: {last_error}")


def _load_payload_arg(payload_json: str, payload_file: str) -> Dict[str, Any]:
    if payload_file:
        p = Path(payload_file).expanduser()
        if not p.exists():
            raise ControllerError(f"payload file not found: {p}")
        data = _read_json(p)
        if not isinstance(data, dict):
            raise ControllerError("payload file must contain a JSON object")
        return data

    if payload_json:
        data = json.loads(payload_json)
        if not isinstance(data, dict):
            raise ControllerError("--payload-json must decode to a JSON object")
        return data

    return {}


def _load_object_arg(value_json: str, value_file: str) -> Dict[str, Any]:
    if value_file:
        p = Path(value_file).expanduser()
        if not p.exists():
            raise ControllerError(f"JSON file not found: {p}")
        data = _read_json(p)
        if not isinstance(data, dict):
            raise ControllerError(f"JSON file must contain an object: {p}")
        return data
    if value_json:
        data = json.loads(value_json)
        if not isinstance(data, dict):
            raise ControllerError("JSON argument must decode to a JSON object")
        return data
    return {}


def _cmd_health(ctrl: RayVaultController, args: argparse.Namespace) -> int:
    out = ctrl.healthcheck()
    print(json.dumps(out, indent=2))
    return 0


def _cmd_caps(ctrl: RayVaultController, args: argparse.Namespace) -> int:
    node_id = str(args.node_id or "").strip()
    nodes = [n for n in ctrl.enabled_workers() if not node_id or n.node_id == node_id]
    if not nodes:
        raise ControllerError(f"no matching enabled worker for node_id={node_id!r}")

    rows: List[Dict[str, Any]] = []
    ok_all = True
    for node in nodes:
        try:
            rows.append(
                {
                    "node_id": node.node_id,
                    "ok": True,
                    "caps": ctrl.register_caps(node, run_id=args.run_id),
                }
            )
        except Exception as exc:  # noqa: BLE001
            ok_all = False
            rows.append(
                {
                    "node_id": node.node_id,
                    "ok": False,
                    "error": str(exc),
                }
            )
    print(json.dumps({"ok": ok_all, "rows": rows}, indent=2))
    return 0 if ok_all else 1


def _cmd_submit(ctrl: RayVaultController, args: argparse.Namespace) -> int:
    payload = _load_payload_arg(args.payload_json, args.payload_file)
    requirements = _load_object_arg(args.requirements_json, args.requirements_file)

    out = ctrl.submit_job(
        run_id=args.run_id,
        job_id=args.job_id,
        step_name=args.step_name,
        payload=payload,
        requirements=requirements,
        inputs_hash=args.inputs_hash,
        force=bool(args.force),
        allow_local_fallback=not bool(args.no_local_fallback),
    )
    print(json.dumps(out.to_dict(), indent=2))
    return 0 if out.ok else 2


def _cmd_sync_artifacts(ctrl: RayVaultController, args: argparse.Namespace) -> int:
    workers = ctrl.enabled_workers()
    if not workers:
        raise ControllerError("No enabled worker nodes")

    node_id = str(args.node_id or "").strip()
    node = workers[0]
    if node_id:
        matches = [w for w in workers if w.node_id == node_id]
        if not matches:
            raise ControllerError(f"worker not found: {node_id}")
        node = matches[0]

    receipt_path, receipt = ctrl.sync_remote_artifacts(
        node=node,
        run_id=args.run_id,
        job_id=args.job_id,
        inputs_hash=args.inputs_hash,
    )
    print(json.dumps({"ok": True, "receipt_path": str(receipt_path), "receipt": receipt}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="RayVault cluster controller")
    p.add_argument("--nodes-file", default=str(DEFAULT_NODES_FILE))
    p.add_argument("--cluster-secret", default="")

    sub = p.add_subparsers(dest="cmd", required=True)

    p_health = sub.add_parser("health", help="Probe /health on enabled workers")
    p_health.set_defaults(func=_cmd_health)

    p_caps = sub.add_parser("caps", help="Register/probe worker capabilities")
    p_caps.add_argument("--node-id", default="")
    p_caps.add_argument("--run-id", default="cluster_caps_probe")
    p_caps.set_defaults(func=_cmd_caps)

    p_submit = sub.add_parser("submit", help="Submit a job to worker (with local fallback)")
    p_submit.add_argument("--run-id", required=True)
    p_submit.add_argument("--job-id", required=True)
    p_submit.add_argument("--step-name", required=True)
    p_submit.add_argument("--payload-json", default="")
    p_submit.add_argument("--payload-file", default="")
    p_submit.add_argument("--requirements-json", default="")
    p_submit.add_argument("--requirements-file", default="")
    p_submit.add_argument("--inputs-hash", default="")
    p_submit.add_argument("--force", action="store_true")
    p_submit.add_argument("--no-local-fallback", action="store_true")
    p_submit.set_defaults(func=_cmd_submit)

    p_sync = sub.add_parser("sync-artifacts", help="Download remote artifacts/logs for an existing job_id")
    p_sync.add_argument("--run-id", required=True)
    p_sync.add_argument("--job-id", required=True)
    p_sync.add_argument("--node-id", default="")
    p_sync.add_argument("--inputs-hash", default="")
    p_sync.set_defaults(func=_cmd_sync_artifacts)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    ctrl = RayVaultController(
        nodes_file=Path(args.nodes_file),
        cluster_secret=args.cluster_secret,
    )
    return int(args.func(ctrl, args))


if __name__ == "__main__":
    raise SystemExit(main())
