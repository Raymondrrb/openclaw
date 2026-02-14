/** Env var validation with fail-fast. Never logs actual values. */

function require(name: string): string {
  const val = process.env[name];
  if (!val) {
    throw new Error(`Missing required env var: ${name}`);
  }
  return val;
}

function optional(name: string): string | undefined {
  return process.env[name] || undefined;
}

/** Client-side env vars (NEXT_PUBLIC_*). Safe to call anywhere. */
export function getPublicEnv() {
  return {
    supabaseUrl: require("NEXT_PUBLIC_SUPABASE_URL"),
    supabaseAnonKey: require("NEXT_PUBLIC_SUPABASE_ANON_KEY"),
  };
}

/** Server-side env vars. Throws if required vars are missing. */
export function getServerEnv() {
  return {
    ...getPublicEnv(),
    supabaseServiceRoleKey: require("SUPABASE_SERVICE_ROLE_KEY"),
    telegramBotToken: optional("TELEGRAM_BOT_TOKEN"),
    telegramChatId: optional("TELEGRAM_CHAT_ID"),
    cronSecret: optional("CRON_SECRET"),
  };
}

/** Presence check for health endpoint — never leaks values. */
export function envPresenceCheck() {
  return {
    supabase_url: !!process.env.NEXT_PUBLIC_SUPABASE_URL,
    supabase_anon_key: !!process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
    supabase_service_role: !!process.env.SUPABASE_SERVICE_ROLE_KEY,
    telegram: !!process.env.TELEGRAM_BOT_TOKEN && !!process.env.TELEGRAM_CHAT_ID,
  };
}
