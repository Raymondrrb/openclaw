const { requireBearerAuth } = require("../_lib/auth");

function parseCountFromRange(contentRange) {
  if (!contentRange) {
    return null;
  }
  const idx = contentRange.lastIndexOf("/");
  if (idx < 0) {
    return null;
  }
  const raw = contentRange.slice(idx + 1).trim();
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

async function tableCount({ table, selectCol, supabaseUrl, serviceKey }) {
  const base = supabaseUrl.replace(/\/$/, "");
  const url = `${base}/rest/v1/${table}?select=${encodeURIComponent(selectCol)}`;
  const resp = await fetch(url, {
    method: "GET",
    headers: {
      apikey: serviceKey,
      Authorization: `Bearer ${serviceKey}`,
      Prefer: "count=exact",
      Range: "0-0",
    },
  });

  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(`${table}: ${resp.status} ${txt || resp.statusText}`);
  }

  return parseCountFromRange(resp.headers.get("content-range"));
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

  try {
    const [policies, proposals, missions, steps, events] = await Promise.all([
      tableCount({
        table: "ops_policy",
        selectCol: "key",
        supabaseUrl,
        serviceKey,
      }),
      tableCount({
        table: "ops_mission_proposals",
        selectCol: "id",
        supabaseUrl,
        serviceKey,
      }),
      tableCount({
        table: "ops_missions",
        selectCol: "id",
        supabaseUrl,
        serviceKey,
      }),
      tableCount({
        table: "ops_mission_steps",
        selectCol: "id",
        supabaseUrl,
        serviceKey,
      }),
      tableCount({
        table: "ops_agent_events",
        selectCol: "id",
        supabaseUrl,
        serviceKey,
      }),
    ]);

    return res.status(200).json({
      ok: true,
      ts: new Date().toISOString(),
      counts: { policies, proposals, missions, steps, events },
    });
  } catch (err) {
    return res.status(500).json({
      ok: false,
      error: err && err.message ? err.message : String(err),
    });
  }
};
