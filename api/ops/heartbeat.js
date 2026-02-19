const crypto = require("crypto");

const { requireBearerAuth } = require("../_lib/auth");

async function insertEvent(eventRow) {
  const supabaseUrl = process.env.SUPABASE_URL;
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;

  if (!supabaseUrl || !serviceKey) {
    return {
      ok: false,
      status: 500,
      error: "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY",
    };
  }

  const url = `${supabaseUrl.replace(/\/$/, "")}/rest/v1/ops_agent_events`;
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      apikey: serviceKey,
      Authorization: `Bearer ${serviceKey}`,
      Prefer: "return=representation",
    },
    body: JSON.stringify(eventRow),
  });

  const txt = await resp.text();
  if (!resp.ok) {
    return {
      ok: false,
      status: resp.status,
      error: `Supabase insert failed: ${txt || resp.statusText}`,
    };
  }

  let data = null;
  try {
    data = txt ? JSON.parse(txt) : null;
  } catch (e) {
    data = txt;
  }
  return { ok: true, status: 200, data };
}

module.exports = async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");

  if (req.method !== "GET" && req.method !== "POST") {
    res.setHeader("Allow", "GET, POST");
    return res.status(405).json({ ok: false, error: "Method not allowed" });
  }

  const authErr = requireBearerAuth(req, res, {
    // Prefer Vercel's conventional CRON_SECRET, but allow OPS_CRON_SECRET for local tooling.
    envNames: ["CRON_SECRET", "OPS_CRON_SECRET"],
  });
  if (authErr) {
    return authErr;
  }

  const now = new Date().toISOString();
  const eventHash = crypto
    .createHash("sha256")
    .update(`vercel-heartbeat:${now}:${crypto.randomUUID()}`)
    .digest("hex")
    .slice(0, 48);

  const eventRow = {
    event_hash: eventHash,
    ts: now,
    type: "vercel_heartbeat",
    message: "Vercel heartbeat executed",
    data: {
      source: "vercel-cron",
      vercel_env: process.env.VERCEL_ENV || "unknown",
      region: process.env.VERCEL_REGION || "unknown",
      method: req.method,
      ua: req.headers["user-agent"] || "",
    },
  };

  try {
    const result = await insertEvent(eventRow);
    if (!result.ok) {
      return res.status(result.status).json({
        ok: false,
        error: result.error,
        ts: now,
      });
    }
    return res.status(200).json({
      ok: true,
      ts: now,
      inserted: Array.isArray(result.data) ? result.data.length : 1,
    });
  } catch (err) {
    return res.status(500).json({
      ok: false,
      error: err && err.message ? err.message : String(err),
      ts: now,
    });
  }
};
