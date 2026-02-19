const crypto = require("crypto");

const { requireBearerAuth } = require("../_lib/auth");

function parseBody(req) {
  if (!req.body) {
    return {};
  }
  if (typeof req.body === "object") {
    return req.body;
  }
  try {
    return JSON.parse(req.body);
  } catch (e) {
    return {};
  }
}

function validAction(value) {
  return (
    value === "start_render" ||
    value === "start_upload" ||
    value === "mark_published" ||
    value === "mark_failed" ||
    value === "reset_to_gate2"
  );
}

async function fetchRun({ supabaseUrl, serviceKey, runSlug }) {
  const base = supabaseUrl.replace(/\/$/, "");
  const url =
    `${base}/rest/v1/ops_video_runs` +
    `?select=run_slug,status,gate1_approved,gate2_approved,updated_at` +
    `&run_slug=eq.${encodeURIComponent(runSlug)}&limit=1`;
  const resp = await fetch(url, {
    method: "GET",
    headers: {
      apikey: serviceKey,
      Authorization: `Bearer ${serviceKey}`,
    },
  });
  const txt = await resp.text();
  if (!resp.ok) {
    throw new Error(`ops_video_runs read failed: ${resp.status} ${txt || resp.statusText}`);
  }
  const rows = txt ? JSON.parse(txt) : [];
  return Array.isArray(rows) && rows.length ? rows[0] : null;
}

async function patchRun({ supabaseUrl, serviceKey, runSlug, body }) {
  const base = supabaseUrl.replace(/\/$/, "");
  const url = `${base}/rest/v1/ops_video_runs?run_slug=eq.${encodeURIComponent(runSlug)}`;
  const resp = await fetch(url, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      apikey: serviceKey,
      Authorization: `Bearer ${serviceKey}`,
      Prefer: "return=representation",
    },
    body: JSON.stringify(body),
  });
  const txt = await resp.text();
  if (!resp.ok) {
    throw new Error(`ops_video_runs update failed: ${resp.status} ${txt || resp.statusText}`);
  }
  const data = txt ? JSON.parse(txt) : [];
  return Array.isArray(data) && data.length ? data[0] : null;
}

async function insertEvent({
  supabaseUrl,
  serviceKey,
  runSlug,
  action,
  previousStatus,
  nextStatus,
  requestedBy,
  notes,
}) {
  const base = supabaseUrl.replace(/\/$/, "");
  const url = `${base}/rest/v1/ops_agent_events`;
  const now = new Date().toISOString();
  const eventRow = {
    event_hash: crypto
      .createHash("sha256")
      .update(`go:${runSlug}:${action}:${now}:${crypto.randomUUID()}`)
      .digest("hex")
      .slice(0, 48),
    ts: now,
    type: "go_action",
    message: `GO action ${action} for ${runSlug}: ${previousStatus} -> ${nextStatus}`,
    data: {
      run_slug: runSlug,
      action,
      previous_status: previousStatus,
      next_status: nextStatus,
      requested_by: requestedBy,
      notes,
      source: "vercel-api",
    },
  };
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      apikey: serviceKey,
      Authorization: `Bearer ${serviceKey}`,
      Prefer: "return=minimal",
    },
    body: JSON.stringify(eventRow),
  });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(`ops_agent_events insert failed: ${resp.status} ${txt || resp.statusText}`);
  }
}

function resolveNextStatus(action) {
  if (action === "start_render") {
    return "rendering";
  }
  if (action === "start_upload") {
    return "uploading";
  }
  if (action === "mark_published") {
    return "published";
  }
  if (action === "mark_failed") {
    return "failed";
  }
  if (action === "reset_to_gate2") {
    return "assets_ready_waiting_gate_2";
  }
  return "";
}

function actionPreconditionError(run, action) {
  const status = run.status;
  if (action === "start_render" && !run.gate1_approved) {
    return "gate1_approved is required before start_render";
  }
  if (!run.gate2_approved && action !== "reset_to_gate2") {
    return "gate2_approved is required before GO actions";
  }
  if (action === "start_render") {
    const allowed = new Set([
      "assets_ready_waiting_gate_2",
      "draft_ready_waiting_gate_1",
      "failed",
    ]);
    if (!allowed.has(status)) {
      return `start_render not allowed from status=${status}`;
    }
  } else if (action === "start_upload") {
    if (status !== "rendering") {
      return `start_upload requires status=rendering (got ${status})`;
    }
  } else if (action === "mark_published") {
    if (status !== "uploading") {
      return `mark_published requires status=uploading (got ${status})`;
    }
  } else if (action === "mark_failed") {
    // allowed from anywhere
    return "";
  } else if (action === "reset_to_gate2") {
    // allowed from anywhere
    return "";
  }
  return "";
}

module.exports = async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");

  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return res.status(405).json({ ok: false, error: "Method not allowed" });
  }

  const authErr = requireBearerAuth(req, res, { envNames: ["OPS_GO_SECRET"] });
  if (authErr) {
    return authErr;
  }

  const supabaseUrl = process.env.SUPABASE_URL;
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!supabaseUrl || !serviceKey) {
    return res.status(500).json({
      ok: false,
      error: "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY",
    });
  }

  const body = parseBody(req);
  const runSlug = String(body.run_slug || body.runSlug || "").trim();
  const action = String(body.action || "start_render").trim();
  const requestedBy = String(body.requested_by || body.requestedBy || "n8n").trim();
  const notes = String(body.notes || "").trim();

  if (!runSlug) {
    return res.status(400).json({ ok: false, error: "run_slug is required" });
  }
  if (!validAction(action)) {
    return res.status(400).json({
      ok: false,
      error:
        "action must be one of: start_render, start_upload, mark_published, mark_failed, reset_to_gate2",
    });
  }

  try {
    const current = await fetchRun({ supabaseUrl, serviceKey, runSlug });
    if (!current) {
      return res.status(404).json({ ok: false, error: `run_slug not found: ${runSlug}` });
    }

    const preErr = actionPreconditionError(current, action);
    if (preErr) {
      return res.status(409).json({
        ok: false,
        error: preErr,
        run: current,
      });
    }

    const nextStatus = resolveNextStatus(action);
    const updateBody = {
      status: nextStatus,
      updated_at: new Date().toISOString(),
    };
    const updated = await patchRun({
      supabaseUrl,
      serviceKey,
      runSlug,
      body: updateBody,
    });
    await insertEvent({
      supabaseUrl,
      serviceKey,
      runSlug,
      action,
      previousStatus: current.status,
      nextStatus,
      requestedBy,
      notes,
    });
    return res.status(200).json({
      ok: true,
      ts: new Date().toISOString(),
      run_slug: runSlug,
      action,
      previous_status: current.status,
      next_status: nextStatus,
      requested_by: requestedBy,
      notes,
      row: updated,
    });
  } catch (err) {
    return res.status(500).json({
      ok: false,
      error: err && err.message ? err.message : String(err),
    });
  }
};
