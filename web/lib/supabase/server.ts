import { createClient } from "@supabase/supabase-js";
import { getServerEnv } from "@/lib/env";

/** Server-side Supabase client using service role key. */
export function createServerClient() {
  const env = getServerEnv();
  return createClient(env.supabaseUrl, env.supabaseServiceRoleKey);
}
