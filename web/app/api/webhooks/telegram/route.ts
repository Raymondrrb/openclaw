/**
 * Telegram Webhook Handler — Inline button decisions for RayVault gates.
 *
 * Handles callback_query from inline buttons:
 *   rv:a:<uuid> → Approve (status → approved, worker resumes)
 *   rv:r:<uuid> → Refetch (status → running, re-triggers research)
 *   rv:x:<uuid> → Abort (status → aborted)
 *   rv:u:<uuid> → Force Unlock (clears lock via rpc_force_unlock_run)
 *
 * Security:
 *   - Validates X-Telegram-Bot-Api-Secret-Token header
 *   - Only TELEGRAM_ADMIN_USER_IDS can press buttons
 *   - Uses service_role key for Supabase (never exposed to client)
 *
 * Setup:
 *   1. Set webhook: POST https://api.telegram.org/bot<TOKEN>/setWebhook
 *      { "url": "https://your.vercel.app/api/webhooks/telegram",
 *        "secret_token": "<TELEGRAM_WEBHOOK_SECRET>" }
 *   2. Env vars: TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET,
 *      TELEGRAM_ADMIN_USER_IDS (comma-separated), SUPABASE_* vars
 */

import { NextResponse } from "next/server";
import { createServerClient } from "@/lib/supabase/server";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

function getWebhookConfig() {
  const botToken = process.env.TELEGRAM_BOT_TOKEN;
  const webhookSecret = process.env.TELEGRAM_WEBHOOK_SECRET;
  const adminIds = (process.env.TELEGRAM_ADMIN_USER_IDS || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  if (!botToken || !webhookSecret) {
    throw new Error("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_WEBHOOK_SECRET");
  }

  return { botToken, webhookSecret, adminIds };
}

// ---------------------------------------------------------------------------
// Telegram API helper
// ---------------------------------------------------------------------------

async function tg(
  botToken: string,
  method: string,
  payload: Record<string, unknown>,
) {
  const res = await fetch(
    `https://api.telegram.org/bot${botToken}/${method}`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  const json = await res.json();
  if (!json.ok) {
    console.error(`[telegram] ${method} failed:`, json);
  }
  return json;
}

// ---------------------------------------------------------------------------
// Callback data parser
// ---------------------------------------------------------------------------

type Action = "approve" | "refetch" | "abort" | "unlock";

function parseCallbackData(
  data: string,
): { action: Action; runId: string } | null {
  const parts = data.split(":");
  if (parts.length !== 3 || parts[0] !== "rv") return null;

  const codeMap: Record<string, Action> = {
    a: "approve",
    r: "refetch",
    x: "abort",
    u: "unlock",
  };
  const action = codeMap[parts[1]];
  if (!action) return null;

  const runId = parts[2];
  // Basic UUID validation (36 chars with hyphens)
  if (!/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(runId)) {
    return null;
  }

  return { action, runId };
}

// ---------------------------------------------------------------------------
// Decision executor
// ---------------------------------------------------------------------------

async function decideRun(
  action: Action,
  runId: string,
  operatorName: string,
): Promise<{ ok: boolean; statusText: string }> {
  const sb = createServerClient();

  if (action === "unlock") {
    const { data, error } = await sb.rpc("rpc_force_unlock_run", {
      p_run_id: runId,
      p_operator_id: operatorName,
      p_reason: "unlock via telegram button",
      p_force: true,
    });
    if (error) throw error;
    return { ok: !!data, statusText: "Unlocked" };
  }

  // Map action → new status
  const statusMap: Record<string, string> = {
    approve: "approved",
    refetch: "running",
    abort: "aborted",
  };
  const newStatus = statusMap[action];

  // Update run status
  const { error: updErr } = await sb
    .from("pipeline_runs")
    .update({
      status: newStatus,
      updated_at: new Date().toISOString(),
    })
    .eq("id", runId);

  if (updErr) throw updErr;

  // Log event for forensics
  const { error: evErr } = await sb.from("run_events").insert({
    run_id: runId,
    event_type: `user_${action}`,
    payload: {
      source: "telegram",
      action,
      operator: operatorName,
      ts: new Date().toISOString(),
    },
  });
  if (evErr) {
    console.error("[telegram] Event insert failed:", evErr);
    // Non-fatal: decision was already applied
  }

  const labels: Record<string, string> = {
    approve: "Approved",
    refetch: "Refetch requested",
    abort: "Aborted",
  };
  return { ok: true, statusText: labels[action] || action };
}

// ---------------------------------------------------------------------------
// POST handler
// ---------------------------------------------------------------------------

export async function POST(req: Request) {
  // 1. Validate webhook secret
  let config;
  try {
    config = getWebhookConfig();
  } catch {
    return NextResponse.json({ error: "misconfigured" }, { status: 500 });
  }

  const secret = req.headers.get("x-telegram-bot-api-secret-token");
  if (!secret || secret !== config.webhookSecret) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let update: any;
  try {
    update = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }

  // 2. Handle callback_query (inline button press)
  if (update.callback_query) {
    const cq = update.callback_query;
    const fromId = cq.from?.id;
    const cbId = cq.id;
    const msg = cq.message;
    const data = cq.data as string;
    const operatorName = cq.from?.username || `tg:${fromId}`;

    // Auth: only admin users can press buttons
    if (!fromId || !config.adminIds.includes(String(fromId))) {
      await tg(config.botToken, "answerCallbackQuery", {
        callback_query_id: cbId,
        text: "Not authorized.",
        show_alert: true,
      });
      return NextResponse.json({ ok: true });
    }

    // Parse callback data
    const parsed = parseCallbackData(data);
    if (!parsed) {
      await tg(config.botToken, "answerCallbackQuery", {
        callback_query_id: cbId,
        text: "Invalid action.",
        show_alert: true,
      });
      return NextResponse.json({ ok: true });
    }

    try {
      const result = await decideRun(parsed.action, parsed.runId, operatorName);

      // Instant feedback
      await tg(config.botToken, "answerCallbackQuery", {
        callback_query_id: cbId,
        text: result.statusText,
        show_alert: false,
      });

      // Edit original message to reflect decision (remove buttons)
      if (msg?.chat?.id && msg?.message_id) {
        const newText = `${msg.text || "Gate"}\n\n→ Decision: ${result.statusText} (by @${operatorName})`;
        await tg(config.botToken, "editMessageText", {
          chat_id: msg.chat.id,
          message_id: msg.message_id,
          text: newText,
          reply_markup: { inline_keyboard: [] },
        });
      }
    } catch (e) {
      console.error("[telegram] Decision error:", e);
      await tg(config.botToken, "answerCallbackQuery", {
        callback_query_id: cbId,
        text: "Error applying action.",
        show_alert: true,
      });
    }

    return NextResponse.json({ ok: true });
  }

  // 3. Other updates (text commands, etc.) — ignore gracefully
  return NextResponse.json({ ok: true });
}
