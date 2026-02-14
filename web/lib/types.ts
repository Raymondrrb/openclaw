/** TypeScript types matching all 13 Supabase tables. */

export type RunStatus = "running" | "complete" | "failed" | "aborted";
export type ScriptStatus = "draft" | "brief" | "raw" | "reviewed" | "final" | "approved";
export type Severity = "low" | "med" | "high";

export interface PipelineRun {
  id: string;
  video_id: string;
  status: RunStatus;
  cluster: string;
  micro_niche: Record<string, unknown>;
  config_snapshot: Record<string, unknown>;
  stages_completed: string[];
  error_code: string;
  error_message: string;
  elapsed_ms: number;
  created_at: string;
  updated_at: string;
}

export interface Niche {
  id: number;
  run_id: string;
  video_id: string;
  cluster: string;
  subcategory: string;
  buyer_pain: string;
  intent_phrase: string;
  price_min: number;
  price_max: number;
  must_have_features: string[];
  forbidden_variants: string[];
  gap_score: number;
  total_score: number;
  candidate_set: unknown[];
  chosen_reason: string;
  created_at: string;
}

export interface ResearchSource {
  id: number;
  run_id: string;
  source_domain: string;
  source_url: string;
  extraction: Record<string, unknown>;
  checksum: string;
  ok: boolean;
  error: string;
  created_at: string;
}

export interface ShortlistItem {
  id: number;
  run_id: string;
  product_name_clean: string;
  candidate_rank: number;
  buyer_pain_fit: string;
  claims: unknown[];
  downsides: unknown[];
  evidence_by_source: Record<string, unknown>;
  passed_domain_policy: boolean;
  notes: string;
  created_at: string;
}

export interface AmazonProduct {
  id: number;
  run_id: string;
  asin: string;
  amazon_title: string;
  price: number | null;
  rating: number | null;
  review_count: number;
  in_stock: boolean;
  pdp_url: string;
  affiliate_short_url: string;
  verified_at: string;
  rejected: boolean;
  reject_reason: string;
  created_at: string;
}

export interface Top5Product {
  id: number;
  run_id: string;
  rank: number;
  asin: string;
  role_label: string;
  benefits: string[];
  downside: string;
  source_evidence: Record<string, unknown>[];
  affiliate_short_url: string;
  price: number | null;
  created_at: string;
}

export interface Script {
  id: number;
  run_id: string;
  brief_text: string;
  script_raw: string;
  review_notes: string;
  script_final: string;
  word_count: number;
  has_disclosure: boolean;
  status: ScriptStatus;
  created_at: string;
}

export interface Asset {
  id: number;
  run_id: string;
  asset_type: string;
  product_asin: string;
  prompt: string;
  style_rules_version: string;
  storage_path: string;
  width: number;
  height: number;
  ok: boolean;
  error: string;
  created_at: string;
}

export interface TTSChunk {
  id: number;
  run_id: string;
  chunk_index: number;
  text: string;
  voice_id: string;
  model: string;
  storage_path: string;
  duration_seconds: number;
  ok: boolean;
  error: string;
  created_at: string;
}

export interface AgentEvent {
  id: number;
  run_id: string;
  stage: string;
  agent_name: string;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface Lesson {
  id: number;
  scope: string;
  trigger: string;
  rule: string;
  example: Record<string, unknown>;
  severity: Severity;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ChannelMemory {
  key: string;
  value: Record<string, unknown>;
  updated_at: string;
}

export interface VideoMetric {
  id: number;
  video_id: string;
  youtube_id: string;
  niche: string;
  views_24h: number | null;
  views_48h: number | null;
  views_7d: number | null;
  views_30d: number | null;
  ctr: number | null;
  avd_seconds: number | null;
  avg_view_percent: number | null;
  affiliate_clicks: number | null;
  conversions: number | null;
  rpm_estimate: number | null;
  recorded_at: string;
}
