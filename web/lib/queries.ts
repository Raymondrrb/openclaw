import { createServerClient } from "@/lib/supabase/server";
import type {
  PipelineRun,
  Niche,
  Top5Product,
  AmazonProduct,
  ShortlistItem,
  ResearchSource,
  Script,
  Asset,
  TTSChunk,
  AgentEvent,
} from "@/lib/types";

function db() {
  return createServerClient();
}

export async function getLatestRun(): Promise<PipelineRun | null> {
  const { data } = await db()
    .from("pipeline_runs")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(1)
    .single();
  return data;
}

export async function getRecentRuns(days = 14): Promise<PipelineRun[]> {
  const since = new Date();
  since.setDate(since.getDate() - days);
  const { data } = await db()
    .from("pipeline_runs")
    .select("*")
    .gte("created_at", since.toISOString())
    .order("created_at", { ascending: false });
  return data ?? [];
}

export async function getRunByVideoId(videoId: string): Promise<PipelineRun | null> {
  const { data } = await db()
    .from("pipeline_runs")
    .select("*")
    .eq("video_id", videoId)
    .single();
  return data;
}

export async function getNiche(runId: string): Promise<Niche | null> {
  const { data } = await db()
    .from("niches")
    .select("*")
    .eq("run_id", runId)
    .limit(1)
    .single();
  return data;
}

export async function getTop5Products(runId: string): Promise<Top5Product[]> {
  const { data } = await db()
    .from("top5")
    .select("*")
    .eq("run_id", runId)
    .order("rank", { ascending: true });
  return data ?? [];
}

export async function getAmazonProducts(runId: string): Promise<AmazonProduct[]> {
  const { data } = await db()
    .from("amazon_products")
    .select("*")
    .eq("run_id", runId)
    .order("created_at", { ascending: true });
  return data ?? [];
}

export async function getShortlistItems(runId: string): Promise<ShortlistItem[]> {
  const { data } = await db()
    .from("shortlist_items")
    .select("*")
    .eq("run_id", runId)
    .order("candidate_rank", { ascending: true });
  return data ?? [];
}

export async function getResearchSources(runId: string): Promise<ResearchSource[]> {
  const { data } = await db()
    .from("research_sources")
    .select("*")
    .eq("run_id", runId)
    .order("created_at", { ascending: true });
  return data ?? [];
}

export async function getScript(runId: string): Promise<Script | null> {
  const { data } = await db()
    .from("scripts")
    .select("*")
    .eq("run_id", runId)
    .limit(1)
    .single();
  return data;
}

export async function getAssets(runId: string): Promise<Asset[]> {
  const { data } = await db()
    .from("assets")
    .select("*")
    .eq("run_id", runId)
    .order("created_at", { ascending: true });
  return data ?? [];
}

export async function getTTSChunks(runId: string): Promise<TTSChunk[]> {
  const { data } = await db()
    .from("tts_audio")
    .select("*")
    .eq("run_id", runId)
    .order("chunk_index", { ascending: true });
  return data ?? [];
}

export async function getGateEvents(runId: string): Promise<AgentEvent[]> {
  const { data } = await db()
    .from("agent_events")
    .select("*")
    .eq("run_id", runId)
    .order("created_at", { ascending: true });
  return data ?? [];
}
