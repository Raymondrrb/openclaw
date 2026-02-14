import { NextResponse } from "next/server";
import { envPresenceCheck } from "@/lib/env";
import { createServerClient } from "@/lib/supabase/server";

export async function GET() {
  const presence = envPresenceCheck();

  let supabaseConnection = false;
  try {
    const supabase = createServerClient();
    const { error } = await supabase
      .from("pipeline_runs")
      .select("id")
      .limit(1);
    supabaseConnection = !error;
  } catch {
    supabaseConnection = false;
  }

  const checks = {
    ...presence,
    supabase_connection: supabaseConnection,
  };

  const coreOk =
    checks.supabase_url &&
    checks.supabase_anon_key &&
    checks.supabase_service_role &&
    checks.supabase_connection;

  return NextResponse.json(
    {
      status: coreOk ? "ok" : "degraded",
      checks,
      timestamp: new Date().toISOString(),
    },
    { status: coreOk ? 200 : 503 }
  );
}
