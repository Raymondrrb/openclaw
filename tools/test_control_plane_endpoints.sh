#!/bin/zsh
set -euo pipefail

ENV_FILE="${1:-$HOME/.config/newproject/vercel_control_plane.env}"
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi

BASE_URL="${NEWPROJECT_VERCEL_BASE_URL:-https://new-project-control-plane.vercel.app}"
READ_TOKEN="${OPS_READ_SECRET:-}"
GATE_TOKEN="${OPS_GATE_SECRET:-}"
GO_TOKEN="${OPS_GO_SECRET:-}"
export BASE_URL READ_TOKEN GATE_TOKEN GO_TOKEN

python3 - <<'PY'
import json
import os
import urllib.error
import urllib.request

base = os.environ.get("BASE_URL", "").rstrip("/")
read = os.environ.get("READ_TOKEN", "")
gate = os.environ.get("GATE_TOKEN", "")
go = os.environ.get("GO_TOKEN", "")

missing = []
if not read:
    missing.append("OPS_READ_SECRET")
if not gate:
    missing.append("OPS_GATE_SECRET")
if missing:
    raise SystemExit(f"Missing required env vars in this shell: {', '.join(missing)}")

def req(method, path, token=None, body=None):
    url = f"{base}{path}"
    headers = {}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    r = urllib.request.Request(url, headers=headers, data=data, method=method)
    try:
        with urllib.request.urlopen(r, timeout=25) as resp:
            txt = resp.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(txt) if txt else None
            except Exception:
                payload = txt[:400]
            return {"ok": True, "status": int(resp.status), "payload": payload}
    except urllib.error.HTTPError as e:
        txt = e.read().decode("utf-8", errors="replace") if e.fp else ""
        try:
            payload = json.loads(txt) if txt else None
        except Exception:
            payload = txt[:400]
        return {"ok": False, "status": int(e.code), "payload": payload}
    except Exception as e:
        return {"ok": False, "status": 0, "error": str(e)}

results = {
    "base_url": base,
    "tokens": {
        "ops_read_secret_present": bool(read),
        "ops_gate_secret_present": bool(gate),
        "ops_go_secret_present": bool(go),
    },
    "health": req("GET", "/api/health"),
    "summary": req("GET", "/api/ops/summary", token=read if read else None),
    "runs": req("GET", "/api/ops/runs?limit=2", token=read if read else None),
    "gate_fake_run": req(
        "POST",
        "/api/ops/gate",
        token=gate if gate else None,
        body={
            "run_slug": "nonexistent_run_for_endpoint_test",
            "gate": "gate2",
            "decision": "approve",
            "reviewer": "endpoint-test",
            "notes": "safe test",
        },
    ),
    "go_fake_run": (
        req(
            "POST",
            "/api/ops/go",
            token=go if go else None,
            body={
                "run_slug": "nonexistent_run_for_endpoint_test",
                "action": "start_render",
                "requested_by": "endpoint-test",
                "notes": "safe test",
            },
        )
        if go
        else {"ok": False, "skipped": True, "reason": "OPS_GO_SECRET missing in shell"}
    ),
}

print(json.dumps(results, indent=2))
PY
