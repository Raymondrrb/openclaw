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

function validGate(value) {
  return value === "gate1" || value === "gate2";
}

function validDecision(value) {
  return value === "approve" || value === "reject";
}

async function fetchRun({ supabaseUrl, serviceKey, runSlug }) {
  const base = supabaseUrl.replace(/\/$/, "");
  const url =
    `${base}/rest/v1/ops_video_runs` +
    `?select=run_slug,status,gate1_approved,gate2_approved,gate1_reviewer,gate2_reviewer,updated_at` +
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
  return Array.isArray(data) ? data : [];
}

async function insertEvent({ supabaseUrl, serviceKey, gate, decision, runSlug, reviewer, notes }) {
  const base = supabaseUrl.replace(/\/$/, "");
  const url = `${base}/rest/v1/ops_agent_events`;
  const now = new Date().toISOString();
  const eventRow = {
    event_hash: crypto
      .createHash("sha256")
      .update(`gate:${runSlug}:${gate}:${decision}:${now}:${crypto.randomUUID()}`)
      .digest("hex")
      .slice(0, 48),
    ts: now,
    type: "quality_gate_decision",
    message: `Gate decision ${gate}=${decision} for ${runSlug}`,
    data: {
      run_slug: runSlug,
      gate,
      decision,
      reviewer,
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

module.exports = async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");

  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return res.status(405).json({ ok: false, error: "Method not allowed" });
  }

  const authErr = requireBearerAuth(req, res, { envNames: ["OPS_GATE_SECRET"] });
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
  const gate = String(body.gate || "").trim();
  const decision = String(body.decision || "").trim();
  const reviewer = String(body.reviewer || "n8n").trim();
  const notes = String(body.notes || "").trim();

  if (!runSlug) {
    return res.status(400).json({ ok: false, error: "run_slug is required" });
  }
  if (!validGate(gate)) {
    return res.status(400).json({ ok: false, error: "gate must be gate1 or gate2" });
  }
  if (!validDecision(decision)) {
    return res.status(400).json({ ok: false, error: "decision must be approve or reject" });
  }

  const approved = decision === "approve";

  try {
    const current = await fetchRun({ supabaseUrl, serviceKey, runSlug });
    if (!current) {
      return res.status(404).json({ ok: false, error: `run_slug not found: ${runSlug}` });
    }

    const field = gate === "gate1" ? "gate1_approved" : "gate2_approved";
    if (current[field] === approved) {
      return res.status(200).json({
        ok: true,
        idempotent: true,
        ts: new Date().toISOString(),
        run_slug: runSlug,
        gate,
        decision,
        reviewer,
        row: current,
      });
    }
  } catch (err) {
    return res.status(500).json({
      ok: false,
      error: err && err.message ? err.message : String(err),
    });
  }

  const patchBody = {
    updated_at: new Date().toISOString(),
  };
  if (gate === "gate1") {
    patchBody.gate1_approved = approved;
    patchBody.gate1_reviewer = reviewer;
    patchBody.gate1_notes = notes;
    if (!approved) {
      patchBody.status = "draft_ready_waiting_gate_1";
    }
  } else {
    patchBody.gate2_approved = approved;
    patchBody.gate2_reviewer = reviewer;
    patchBody.gate2_notes = notes;
    if (!approved) {
      patchBody.status = "assets_ready_waiting_gate_2";
    }
  }

  try {
    const rows = await patchRun({
      supabaseUrl,
      serviceKey,
      runSlug,
      body: patchBody,
    });
    if (!rows.length) {
      return res.status(404).json({ ok: false, error: `run_slug not found: ${runSlug}` });
    }
    await insertEvent({
      supabaseUrl,
      serviceKey,
      gate,
      decision,
      runSlug,
      reviewer,
      notes,
    });
    return res.status(200).json({
      ok: true,
      ts: new Date().toISOString(),
      run_slug: runSlug,
      gate,
      decision,
      reviewer,
      row: rows[0],
    });
  } catch (err) {
    return res.status(500).json({
      ok: false,
      error: err && err.message ? err.message : String(err),
    });
  }
};
