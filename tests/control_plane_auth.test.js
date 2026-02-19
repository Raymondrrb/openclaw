const test = require("node:test");
const assert = require("node:assert/strict");

const summaryHandler = require("../api/ops/summary");
const runsHandler = require("../api/ops/runs");
const heartbeatHandler = require("../api/ops/heartbeat");
const gateHandler = require("../api/ops/gate");
const goHandler = require("../api/ops/go");

function mockReq({ method = "GET", headers = {}, query = {}, body } = {}) {
  return { method, headers, query, body };
}

function mockRes() {
  return {
    statusCode: 200,
    headers: {},
    payload: undefined,
    setHeader(name, value) {
      this.headers[String(name).toLowerCase()] = value;
    },
    status(code) {
      this.statusCode = code;
      return this;
    },
    json(obj) {
      this.payload = obj;
      return this;
    },
  };
}

function makeResp({ ok = true, status = 200, text = "", headers = {} } = {}) {
  const h = new Map(Object.entries(headers).map(([k, v]) => [k.toLowerCase(), v]));
  return {
    ok,
    status,
    headers: {
      get(name) {
        return h.get(String(name).toLowerCase()) ?? null;
      },
    },
    async text() {
      return text;
    },
  };
}

async function withEnv(vars, fn) {
  const prev = {};
  for (const [k, v] of Object.entries(vars)) {
    prev[k] = Object.prototype.hasOwnProperty.call(process.env, k) ? process.env[k] : undefined;
    if (v === null || v === undefined) {
      delete process.env[k];
    } else {
      process.env[k] = String(v);
    }
  }
  try {
    await fn();
  } finally {
    for (const [k, v] of Object.entries(prev)) {
      if (v === undefined) {
        delete process.env[k];
      } else {
        process.env[k] = v;
      }
    }
  }
}

async function withFetch(mock, fn) {
  const prev = global.fetch;
  global.fetch = mock;
  try {
    await fn();
  } finally {
    global.fetch = prev;
  }
}

test("control plane endpoints are fail-closed and do not widen privileges on missing secrets", async () => {
  await withEnv(
    {
      OPS_READ_SECRET: null,
      SUPABASE_URL: null,
      SUPABASE_SERVICE_ROLE_KEY: null,
    },
    async () => {
      const res = mockRes();
      await summaryHandler(mockReq({ method: "GET" }), res);
      assert.equal(res.statusCode, 500);
      assert.equal(res.payload.ok, false);
      assert.match(res.payload.error, /OPS_READ_SECRET/);
    },
  );

  await withEnv(
    {
      OPS_READ_SECRET: null,
      SUPABASE_URL: null,
      SUPABASE_SERVICE_ROLE_KEY: null,
    },
    async () => {
      const res = mockRes();
      await runsHandler(mockReq({ method: "GET" }), res);
      assert.equal(res.statusCode, 500);
      assert.equal(res.payload.ok, false);
      assert.match(res.payload.error, /OPS_READ_SECRET/);
    },
  );

  await withEnv(
    {
      OPS_GATE_SECRET: null,
      SUPABASE_URL: null,
      SUPABASE_SERVICE_ROLE_KEY: null,
    },
    async () => {
      const res = mockRes();
      await gateHandler(
        mockReq({
          method: "POST",
          headers: { authorization: "Bearer anything" },
          body: { run_slug: "x", gate: "gate1", decision: "approve" },
        }),
        res,
      );
      assert.equal(res.statusCode, 500);
      assert.equal(res.payload.ok, false);
      assert.match(res.payload.error, /OPS_GATE_SECRET/);
    },
  );

  await withEnv(
    {
      OPS_GO_SECRET: null,
      SUPABASE_URL: null,
      SUPABASE_SERVICE_ROLE_KEY: null,
    },
    async () => {
      const res = mockRes();
      await goHandler(
        mockReq({
          method: "POST",
          headers: { authorization: "Bearer anything" },
          body: { run_slug: "x", action: "start_render" },
        }),
        res,
      );
      assert.equal(res.statusCode, 500);
      assert.equal(res.payload.ok, false);
      assert.match(res.payload.error, /OPS_GO_SECRET/);
    },
  );

  await withEnv(
    {
      OPS_CRON_SECRET: null,
      CRON_SECRET: null,
      SUPABASE_URL: null,
      SUPABASE_SERVICE_ROLE_KEY: null,
    },
    async () => {
      const res = mockRes();
      await heartbeatHandler(mockReq({ method: "GET" }), res);
      assert.equal(res.statusCode, 500);
      assert.equal(res.payload.ok, false);
      assert.match(res.payload.error, /OPS_CRON_SECRET|CRON_SECRET/);
    },
  );

  await withEnv(
    {
      OPS_CRON_SECRET: null,
      CRON_SECRET: "cron-secret",
      SUPABASE_URL: "https://example.supabase.co",
      SUPABASE_SERVICE_ROLE_KEY: "service-role-key",
    },
    async () => {
      await withFetch(
        async () => makeResp({ ok: true, status: 201, text: "[]" }),
        async () => {
          const res = mockRes();
          await heartbeatHandler(
            mockReq({
              method: "GET",
              headers: { authorization: "Bearer cron-secret" },
            }),
            res,
          );
          assert.equal(res.statusCode, 200);
          assert.equal(res.payload.ok, true);
        },
      );
    },
  );

  await withEnv(
    {
      OPS_GATE_SECRET: "gate-secret",
      OPS_CRON_SECRET: "cron-secret",
      SUPABASE_URL: null,
      SUPABASE_SERVICE_ROLE_KEY: null,
    },
    async () => {
      const res = mockRes();
      await gateHandler(
        mockReq({
          method: "POST",
          headers: { authorization: "Bearer cron-secret" },
          body: {
            run_slug: "x",
            gate: "gate1",
            decision: "approve",
          },
        }),
        res,
      );
      assert.equal(res.statusCode, 401);
      assert.equal(res.payload.ok, false);
    },
  );

  await withEnv(
    {
      OPS_GO_SECRET: "go-secret",
      OPS_GATE_SECRET: "gate-secret",
      OPS_CRON_SECRET: "cron-secret",
      SUPABASE_URL: null,
      SUPABASE_SERVICE_ROLE_KEY: null,
    },
    async () => {
      const res = mockRes();
      await goHandler(
        mockReq({
          method: "POST",
          headers: { authorization: "Bearer gate-secret" },
          body: { run_slug: "x", action: "start_render" },
        }),
        res,
      );
      assert.equal(res.statusCode, 401);
      assert.equal(res.payload.ok, false);
    },
  );

  await withEnv(
    {
      OPS_READ_SECRET: "read-secret",
      SUPABASE_URL: "https://example.supabase.co",
      SUPABASE_SERVICE_ROLE_KEY: "service-role-key",
    },
    async () => {
      await withFetch(
        async () =>
          makeResp({
            ok: true,
            status: 200,
            text: "",
            headers: { "content-range": "0-0/123" },
          }),
        async () => {
          const res = mockRes();
          await summaryHandler(
            mockReq({
              method: "GET",
              headers: { authorization: "Bearer read-secret" },
            }),
            res,
          );
          assert.equal(res.statusCode, 200);
          assert.equal(res.payload.ok, true);
          assert.deepEqual(res.payload.counts, {
            policies: 123,
            proposals: 123,
            missions: 123,
            steps: 123,
            events: 123,
          });
        },
      );
    },
  );
});
