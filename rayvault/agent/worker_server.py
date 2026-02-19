"""RayVault distributed worker server.

FastAPI service intended to run on Windows node over Tailscale.

Endpoints:
- GET  /health
- POST /caps
- POST /job
- GET  /job/{job_id}
- GET  /job/{job_id}/logs
- GET  /job/{job_id}/artifacts
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from rayvault.agent.jobs import JobExecutionError, detect_capabilities, execute_job
from rayvault.agent.protocol import (
    JOB_STEPS,
    Envelope,
    ProtocolError,
    require_valid_auth,
    utc_now_iso,
)


@dataclass
class JobRecord:
    envelope: Envelope
    payload: Dict[str, Any]
    status: str = "queued"
    progress: float = 0.0
    message: str = "queued"
    created_at: str = field(default_factory=utc_now_iso)
    started_at: str = ""
    finished_at: str = ""
    exit_code: int = 0
    metrics: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    error_code: str = ""
    error_message: str = ""
    idempotent: bool = False
    cached_job_id: str = ""
    worker_id: str = ""
    log_path: str = ""
    receipt_path: str = ""


class WorkerState:
    def __init__(self, *, workspace_root: Path, worker_id: str, secret: str):
        self.workspace_root = workspace_root.resolve()
        self.worker_id = worker_id
        self.secret = secret

        self.jobs_dir = self.workspace_root / "jobs"
        self.logs_dir = self.workspace_root / "logs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        self.jobs: Dict[str, JobRecord] = {}
        self.jobs_by_hash: Dict[str, str] = {}
        self.lock = threading.Lock()
        self.q: queue.Queue[str] = queue.Queue()
        self.stop_event = threading.Event()

    def _job_key(self, env: Envelope) -> str:
        return f"{env.step_name}:{env.inputs_hash}"

    def enqueue(self, env: Envelope, payload: Dict[str, Any]) -> Dict[str, Any]:
        key = self._job_key(env)
        with self.lock:
            existing_id = self.jobs_by_hash.get(key)
            if existing_id:
                existing = self.jobs.get(existing_id)
                if existing:
                    existing.idempotent = True
                    return {
                        "ok": True,
                        "idempotent": True,
                        "cached_job_id": existing_id,
                        "job": serialize_record(existing),
                    }

            if env.job_id in self.jobs:
                existing = self.jobs[env.job_id]
                return {
                    "ok": True,
                    "idempotent": True,
                    "cached_job_id": env.job_id,
                    "job": serialize_record(existing),
                }

            rec = JobRecord(
                envelope=env,
                payload=payload or {},
                worker_id=self.worker_id,
            )
            rec.log_path = str((self.logs_dir / f"{env.job_id}.log").resolve())
            rec.receipt_path = str((self.jobs_dir / env.job_id / "job_receipt.json").resolve())
            self.jobs[env.job_id] = rec
            self.jobs_by_hash[key] = env.job_id
            self.q.put(env.job_id)

        self.append_log(env.job_id, f"[{utc_now_iso()}] queued step={env.step_name}")
        return {
            "ok": True,
            "idempotent": False,
            "job": serialize_record(rec),
        }

    def append_log(self, job_id: str, line: str, *, level: str = "info", event: str = "worker_log") -> None:
        rec = self.jobs.get(job_id)
        if not rec or not rec.log_path:
            return
        p = Path(rec.log_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": utc_now_iso(),
            "job_id": job_id,
            "event": event,
            "level": level.lower(),
            "message": line.rstrip(),
        }
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    def _write_receipt(self, rec: JobRecord) -> None:
        p = Path(rec.receipt_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": rec.envelope.run_id,
            "job_id": rec.envelope.job_id,
            "step_name": rec.envelope.step_name,
            "inputs_hash": rec.envelope.inputs_hash,
            "status": rec.status,
            "exit_code": rec.exit_code,
            "worker_id": rec.worker_id,
            "created_at": rec.created_at,
            "started_at": rec.started_at,
            "finished_at": rec.finished_at,
            "metrics": rec.metrics,
            "artifacts": rec.artifacts,
            "error_code": rec.error_code,
            "error_message": rec.error_message,
            "log_path": rec.log_path,
        }
        from rayvault.io import atomic_write_json
        atomic_write_json(p, payload)

    def worker_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                job_id = self.q.get(timeout=0.5)
            except queue.Empty:
                continue

            with self.lock:
                rec = self.jobs.get(job_id)
                if not rec:
                    continue
                rec.status = "running"
                rec.progress = 0.1
                rec.message = "running"
                rec.started_at = utc_now_iso()
            self.append_log(job_id, f"[{utc_now_iso()}] started")

            try:
                out = execute_job(rec.envelope, rec.payload, workspace_root=self.workspace_root)
                with self.lock:
                    rec.status = str(out.get("status", "succeeded"))
                    rec.progress = 1.0
                    rec.message = rec.status
                    rec.exit_code = int(out.get("exit_code", 0))
                    rec.metrics = out.get("metrics", {}) if isinstance(out.get("metrics"), dict) else {}
                    rec.artifacts = out.get("artifacts", []) if isinstance(out.get("artifacts"), list) else []
                    rec.finished_at = utc_now_iso()
                self.append_log(job_id, f"[{utc_now_iso()}] finished status={rec.status} exit={rec.exit_code}")
            except JobExecutionError as exc:
                with self.lock:
                    rec.status = "failed"
                    rec.progress = 1.0
                    rec.message = exc.message
                    rec.exit_code = 2
                    rec.error_code = exc.code
                    rec.error_message = exc.message
                    rec.finished_at = utc_now_iso()
                self.append_log(job_id, f"[{utc_now_iso()}] failed code={exc.code} msg={exc.message}")
            except Exception as exc:  # noqa: BLE001
                with self.lock:
                    rec.status = "failed"
                    rec.progress = 1.0
                    rec.message = str(exc)
                    rec.exit_code = 1
                    rec.error_code = "UNHANDLED_EXCEPTION"
                    rec.error_message = str(exc)
                    rec.finished_at = utc_now_iso()
                self.append_log(job_id, f"[{utc_now_iso()}] failed code=UNHANDLED_EXCEPTION msg={exc}")
            finally:
                with self.lock:
                    rec = self.jobs.get(job_id)
                    if rec:
                        self._write_receipt(rec)
                self.q.task_done()


def serialize_record(rec: JobRecord) -> Dict[str, Any]:
    return {
        "run_id": rec.envelope.run_id,
        "job_id": rec.envelope.job_id,
        "step_name": rec.envelope.step_name,
        "inputs_hash": rec.envelope.inputs_hash,
        "status": rec.status,
        "progress": rec.progress,
        "message": rec.message,
        "created_at": rec.created_at,
        "started_at": rec.started_at,
        "finished_at": rec.finished_at,
        "exit_code": rec.exit_code,
        "metrics": rec.metrics,
        "artifacts": rec.artifacts,
        "error_code": rec.error_code,
        "error_message": rec.error_message,
        "idempotent": rec.idempotent,
        "cached_job_id": rec.cached_job_id,
        "worker_id": rec.worker_id,
        "log_path": rec.log_path,
        "receipt_path": rec.receipt_path,
    }


def _query_envelope(
    *,
    run_id: str,
    job_id: str,
    step_name: str,
    inputs_hash: str,
    timestamp: str,
    auth_token: str,
) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "job_id": job_id,
        "step_name": step_name,
        "inputs_hash": inputs_hash,
        "timestamp": timestamp,
        "auth_token": auth_token,
    }


def _require_message_type(body: Dict[str, Any], expected: str) -> None:
    got = str(body.get("message_type", "")).strip()
    if got != expected:
        raise HTTPException(status_code=400, detail=f"message_type must be {expected!r}")


def create_app(*, workspace_root: Path, worker_id: str, secret: str) -> FastAPI:
    state = WorkerState(workspace_root=workspace_root, worker_id=worker_id, secret=secret)
    app = FastAPI(title="RayVault Worker", version="1.1.0")

    worker_thread = threading.Thread(target=state.worker_loop, daemon=True)
    worker_thread.start()

    @app.get("/health")
    def health() -> Dict[str, Any]:
        caps = detect_capabilities()
        return {
            "ok": True,
            "version": app.version,
            "worker_id": worker_id,
            "time": utc_now_iso(),
            "queue_depth": state.q.qsize(),
            "caps": caps,
        }

    @app.post("/caps")
    async def caps(req: Request) -> Dict[str, Any]:
        body = await req.json()
        _require_message_type(body, "register_caps")
        try:
            _ = require_valid_auth(secret, body, allowed_steps={"REGISTER_CAPS"})
        except ProtocolError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

        caps = detect_capabilities()
        return {
            "ok": True,
            "version": app.version,
            "worker_id": worker_id,
            "capabilities": caps,
            "os": caps.get("os"),
            "cpu": caps.get("cpu"),
            "ram_gb": caps.get("ram_gb"),
            "gpu_model": caps.get("gpu_model"),
            "vram_gb": caps.get("vram_gb"),
            "python_version": caps.get("python_version"),
            "ffmpeg_version": caps.get("ffmpeg_version"),
            "davinci_available": bool(caps.get("davinci_available", False)),
        }

    @app.post("/job")
    async def submit_job(req: Request) -> Dict[str, Any]:
        body = await req.json()
        _require_message_type(body, "submit_job")
        payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
        try:
            env = require_valid_auth(secret, body, allowed_steps=JOB_STEPS)
        except ProtocolError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

        out = state.enqueue(env, payload)
        return out

    @app.get("/job/{job_id}")
    def job_status(
        job_id: str,
        run_id: str = Query(...),
        step_name: str = Query(...),
        inputs_hash: str = Query(...),
        timestamp: str = Query(...),
        auth_token: str = Query(...),
    ) -> Dict[str, Any]:
        try:
            env = require_valid_auth(
                secret,
                _query_envelope(
                    run_id=run_id,
                    job_id=job_id,
                    step_name=step_name,
                    inputs_hash=inputs_hash,
                    timestamp=timestamp,
                    auth_token=auth_token,
                ),
                allowed_steps={"JOB_STATUS"},
            )
        except ProtocolError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

        with state.lock:
            rec = state.jobs.get(job_id)
            if not rec:
                raise HTTPException(status_code=404, detail=f"job_id not found: {job_id}")
            if rec.envelope.run_id != env.run_id or rec.envelope.inputs_hash != env.inputs_hash:
                raise HTTPException(status_code=403, detail="job envelope mismatch")
            return {"ok": True, "job": serialize_record(rec)}

    @app.get("/job/{job_id}/logs")
    def job_logs(
        job_id: str,
        run_id: str = Query(...),
        step_name: str = Query(...),
        inputs_hash: str = Query(...),
        timestamp: str = Query(...),
        auth_token: str = Query(...),
    ) -> PlainTextResponse:
        try:
            env = require_valid_auth(
                secret,
                _query_envelope(
                    run_id=run_id,
                    job_id=job_id,
                    step_name=step_name,
                    inputs_hash=inputs_hash,
                    timestamp=timestamp,
                    auth_token=auth_token,
                ),
                allowed_steps={"JOB_LOGS"},
            )
        except ProtocolError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

        with state.lock:
            rec = state.jobs.get(job_id)
            if not rec:
                raise HTTPException(status_code=404, detail=f"job_id not found: {job_id}")
            if rec.envelope.run_id != env.run_id or rec.envelope.inputs_hash != env.inputs_hash:
                raise HTTPException(status_code=403, detail="job envelope mismatch")
            log_path = Path(rec.log_path)
        if not log_path.exists():
            return PlainTextResponse("", status_code=200)
        return PlainTextResponse(log_path.read_text(encoding="utf-8"), status_code=200)

    @app.get("/job/{job_id}/artifacts")
    def job_artifacts(
        job_id: str,
        run_id: str = Query(...),
        step_name: str = Query(...),
        inputs_hash: str = Query(...),
        timestamp: str = Query(...),
        auth_token: str = Query(...),
    ) -> JSONResponse:
        try:
            env = require_valid_auth(
                secret,
                _query_envelope(
                    run_id=run_id,
                    job_id=job_id,
                    step_name=step_name,
                    inputs_hash=inputs_hash,
                    timestamp=timestamp,
                    auth_token=auth_token,
                ),
                allowed_steps={"JOB_ARTIFACTS"},
            )
        except ProtocolError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

        with state.lock:
            rec = state.jobs.get(job_id)
            if not rec:
                raise HTTPException(status_code=404, detail=f"job_id not found: {job_id}")
            if rec.envelope.run_id != env.run_id or rec.envelope.inputs_hash != env.inputs_hash:
                raise HTTPException(status_code=403, detail="job envelope mismatch")
            payload = {
                "ok": True,
                "job_id": job_id,
                "status": rec.status,
                "artifacts": rec.artifacts,
                "receipt_path": rec.receipt_path,
            }
        return JSONResponse(payload, status_code=200)

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description="Run RayVault worker server")
    parser.add_argument("--host", default=os.environ.get("RAYVAULT_WORKER_HOST", "127.0.0.1"))
    try:
        _default_port = int(os.environ.get("RAYVAULT_WORKER_PORT", "8787"))
    except (ValueError, TypeError):
        _default_port = 8787
    parser.add_argument("--port", type=int, default=_default_port)
    parser.add_argument(
        "--workspace-root",
        default=os.environ.get("RAYVAULT_WORKER_ROOT", "state/cluster/worker_data"),
        help="Local worker data root",
    )
    parser.add_argument("--worker-id", default=os.environ.get("RAYVAULT_WORKER_ID", "worker-default"))
    parser.add_argument(
        "--cluster-secret",
        default=os.environ.get("RAYVAULT_CLUSTER_SECRET", ""),
        help="Shared HMAC secret",
    )
    args = parser.parse_args()

    secret = str(args.cluster_secret or "").strip()
    if not secret:
        raise SystemExit("RAYVAULT_CLUSTER_SECRET is required")

    app = create_app(
        workspace_root=Path(args.workspace_root).expanduser(),
        worker_id=args.worker_id,
        secret=secret,
    )

    try:
        import uvicorn
    except Exception as exc:  # noqa: BLE001
        raise SystemExit("uvicorn is required. Install: pip install uvicorn fastapi") from exc

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
