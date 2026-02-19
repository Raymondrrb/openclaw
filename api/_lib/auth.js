const crypto = require("crypto");

function bearerToken(req) {
  const auth = (req && req.headers && req.headers.authorization) || "";
  if (!auth.startsWith("Bearer ")) {
    return "";
  }
  return auth.slice("Bearer ".length).trim();
}

function safeEqual(a, b) {
  // timingSafeEqual requires same-length buffers; length mismatch returns false.
  const ba = Buffer.from(String(a || ""), "utf8");
  const bb = Buffer.from(String(b || ""), "utf8");
  if (ba.length !== bb.length) {
    return false;
  }
  return crypto.timingSafeEqual(ba, bb);
}

function pickEnvSecret(names) {
  for (const name of names) {
    const raw = process.env[name];
    const v = typeof raw === "string" ? raw.trim() : "";
    if (v) {
      return v;
    }
  }
  return "";
}

function requireBearerAuth(req, res, { envNames }) {
  const expected = pickEnvSecret(envNames);
  if (!expected) {
    return res.status(500).json({
      ok: false,
      error: `Server misconfigured: missing ${envNames.join(" or ")}`,
    });
  }

  const got = bearerToken(req);
  if (!got || !safeEqual(got, expected)) {
    return res.status(401).json({ ok: false, error: "Unauthorized" });
  }

  return null;
}

module.exports = {
  bearerToken,
  safeEqual,
  pickEnvSecret,
  requireBearerAuth,
};
