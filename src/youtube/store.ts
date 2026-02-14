import type { YouTubeDocResult } from "./types.js";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export type SaveCompetitorVideoOptions = {
  supabaseUrl?: string;
  supabaseKey?: string;
  fetchFn?: FetchFn;
};

/**
 * Persist a competitor video document to Supabase via raw PostgREST.
 *
 * Upserts on `video_url` (relies on the unique constraint in the
 * `competitor_videos` table). Returns the row id.
 */
export async function saveCompetitorVideo(
  doc: YouTubeDocResult,
  opts?: SaveCompetitorVideoOptions,
): Promise<{ id: string }> {
  const supabaseUrl = opts?.supabaseUrl ?? process.env.SUPABASE_URL;
  const supabaseKey = opts?.supabaseKey ?? process.env.SUPABASE_SERVICE_KEY;

  if (!supabaseUrl) throw new Error("SUPABASE_URL is not set");
  if (!supabaseKey) throw new Error("SUPABASE_SERVICE_KEY is not set");

  const fetcher = opts?.fetchFn ?? globalThis.fetch;

  const body = {
    video_url: `https://www.youtube.com/watch?v=${doc.videoId}`,
    video_id: doc.videoId,
    title: doc.title,
    description: doc.description,
    transcript: doc.transcript,
    timestamps: doc.timestamps,
    extracted_at: doc.extractedAt,
  };

  const res = await fetcher(`${supabaseUrl}/rest/v1/competitor_videos`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      apikey: supabaseKey,
      Authorization: `Bearer ${supabaseKey}`,
      Prefer: "return=representation,resolution=merge-duplicates",
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Supabase insert failed (${res.status}): ${text}`);
  }

  const rows = (await res.json()) as { id: string }[];
  if (!rows[0]) {
    throw new Error("Supabase returned empty response");
  }

  return { id: rows[0].id };
}
