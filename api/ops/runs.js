const { requireBearerAuth } = require("../_lib/auth");

function toInt(value, fallback) {
  const n = Number(value);
  if (!Number.isFinite(n)) {
    return fallback;
  }
  return Math.max(1, Math.min(100, Math.trunc(n)));
}

module.exports = async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");

  if (req.method !== "GET") {
    res.setHeader("Allow", "GET");
    return res.status(405).json({ ok: false, error: "Method not allowed" });
  }

  const authErr = requireBearerAuth(req, res, { envNames: ["OPS_READ_SECRET"] });
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

  const q = req.query || {};
  const limit = toInt(q.limit || 10, 10);
  const status = (q.status || "").trim();
  const base = supabaseUrl.replace(/\/$/, "");

  let url =
    `${base}/rest/v1/ops_video_runs` +
    `?select=run_slug,theme,category,status,gate1_approved,gate2_approved,gate1_reviewer,gate2_reviewer,gate1_notes,gate2_notes,created_at,updated_at` +
    `&order=updated_at.desc&limit=${limit}`;
  if (status) {
    url += `&status=eq.${encodeURIComponent(status)}`;
  }

  try {
    const resp = await fetch(url, {
      method: "GET",
      headers: {
        apikey: serviceKey,
        Authorization: `Bearer ${serviceKey}`,
      },
    });
    const txt = await resp.text();
    if (!resp.ok) {
      return res.status(resp.status).json({
        ok: false,
        error: txt || resp.statusText,
      });
    }
    const rows = txt ? JSON.parse(txt) : [];
    return res.status(200).json({
      ok: true,
      ts: new Date().toISOString(),
      limit,
      count: Array.isArray(rows) ? rows.length : 0,
      rows,
    });
  } catch (err) {
    return res.status(500).json({
      ok: false,
      error: err && err.message ? err.message : String(err),
    });
  }
};
