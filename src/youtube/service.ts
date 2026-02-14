import type { YouTubeDocResult } from "./types.js";
import { parseYouTubeVideoId } from "./parse-url.js";
import { fetchYouTubeDoc } from "./transcript.js";
import { saveCompetitorVideo } from "./store.js";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export type YouTubeToDocOptions = {
  /** When true, persist the result to Supabase. Default: false. */
  store?: boolean;
  fetchFn?: FetchFn;
  /** BCP-47 language code preference for captions. */
  language?: string;
  /** Override Supabase URL (otherwise reads SUPABASE_URL env). */
  supabaseUrl?: string;
  /** Override Supabase service key (otherwise reads SUPABASE_SERVICE_KEY env). */
  supabaseKey?: string;
};

/**
 * Main entry point: extract structured doc + transcript from a YouTube video.
 *
 * Parses the URL, fetches metadata + captions, and optionally stores
 * the result in Supabase.
 */
export async function youtubeToDoc(
  videoUrl: string,
  opts?: YouTubeToDocOptions,
): Promise<YouTubeDocResult> {
  const videoId = parseYouTubeVideoId(videoUrl);
  if (!videoId) {
    throw new Error(`Invalid YouTube URL: ${videoUrl}`);
  }

  const doc = await fetchYouTubeDoc(videoId, {
    fetchFn: opts?.fetchFn,
    language: opts?.language,
  });

  if (opts?.store) {
    await saveCompetitorVideo(doc, {
      supabaseUrl: opts.supabaseUrl,
      supabaseKey: opts.supabaseKey,
      fetchFn: opts.fetchFn,
    });
  }

  return doc;
}
