import { createClient } from "@supabase/supabase-js";
import { getPublicEnv } from "@/lib/env";

/** Browser-side Supabase client using anon key. For future real-time use. */
export function createBrowserClient() {
  const env = getPublicEnv();
  return createClient(env.supabaseUrl, env.supabaseAnonKey);
}
