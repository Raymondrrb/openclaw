/**
 * Helper: Send a gate notification to Telegram with inline buttons.
 *
 * Called server-side when a run enters waiting_approval.
 * Not an API route — import and call from other server code.
 *
 * Usage:
 *   import { sendGateMessage } from "./send-gate";
 *   await sendGateMessage({ runId, reason, dashUrl });
 */

export interface GateMessageOptions {
  runId: string;
  reason: string;
  taskType?: string;
  videoId?: string;
  dashUrl?: string;
}

export async function sendGateMessage(opts: GateMessageOptions) {
  const botToken = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;

  if (!botToken || !chatId) {
    console.warn("[telegram] Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID — skipping gate message");
    return null;
  }

  const shortId = opts.runId.slice(0, 12);
  const dashLink = opts.dashUrl
    ? `${opts.dashUrl}/runs/${opts.runId}`
    : null;

  const lines = [
    `🚨 *Gate Active*`,
    `Run: \`${shortId}\``,
    opts.taskType ? `Task: ${opts.taskType}` : null,
    opts.videoId ? `Video: ${opts.videoId}` : null,
    `Reason: ${escapeMarkdown(opts.reason)}`,
  ].filter(Boolean);

  const text = lines.join("\n");

  // Build inline keyboard (callback_data max 64 bytes)
  const keyboard: { text: string; callback_data?: string; url?: string }[][] = [];

  // Row 1: Dashboard link (if available)
  if (dashLink) {
    keyboard.push([{ text: "🔎 View details", url: dashLink }]);
  }

  // Row 2: Approve / Refetch
  keyboard.push([
    { text: "✅ Approve", callback_data: `rv:a:${opts.runId}` },
    { text: "🔄 Refetch", callback_data: `rv:r:${opts.runId}` },
  ]);

  // Row 3: Unlock / Abort
  keyboard.push([
    { text: "🔓 Unlock", callback_data: `rv:u:${opts.runId}` },
    { text: "❌ Abort", callback_data: `rv:x:${opts.runId}` },
  ]);

  const res = await fetch(
    `https://api.telegram.org/bot${botToken}/sendMessage`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        chat_id: chatId,
        text,
        parse_mode: "MarkdownV2",
        reply_markup: { inline_keyboard: keyboard },
      }),
    },
  );

  const json = await res.json();
  if (!json.ok) {
    console.error("[telegram] sendGateMessage failed:", json);
  }
  return json;
}

/** Escape special chars for Telegram MarkdownV2. */
function escapeMarkdown(text: string): string {
  return text.replace(/([_*\[\]()~`>#+\-=|{}.!])/g, "\\$1");
}
