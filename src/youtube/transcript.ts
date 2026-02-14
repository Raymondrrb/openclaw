import { execFile } from "node:child_process";
import { readFile, unlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import type { YouTubeDocResult, YouTubeTranscriptSegment } from "./types.js";

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export type FetchYouTubeDocOptions = {
  fetchFn?: FetchFn;
  /** BCP-47 language code preference (e.g. "en"). Falls back to first available track. */
  language?: string;
};

const BROWSER_UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36";

/**
 * Fetch a YouTube video's metadata and transcript.
 *
 * Uses two strategies:
 *  1. Scrape the watch page for title/description from `ytInitialPlayerResponse`
 *  2. Extract subtitles via `yt-dlp` (handles YouTube's anti-bot measures)
 *
 * When `fetchFn` is provided (tests), falls back to the legacy timedtext XML
 * scraping path so tests can run without yt-dlp installed.
 */
export async function fetchYouTubeDoc(
  videoId: string,
  opts?: FetchYouTubeDocOptions,
): Promise<YouTubeDocResult> {
  // When a custom fetchFn is injected (tests), use the legacy scraping path
  if (opts?.fetchFn) {
    return fetchYouTubeDocLegacy(videoId, opts);
  }

  const lang = opts?.language ?? "en";

  // 1. Fetch metadata from the watch page
  const { title, description } = await fetchMetadata(videoId);

  // 2. Extract subtitles via yt-dlp
  const timestamps = await extractSubsWithYtDlp(videoId, lang);
  const transcript = timestamps.map((s) => s.text).join(" ");

  return {
    videoId,
    title,
    description,
    transcript,
    timestamps,
    extractedAt: new Date().toISOString(),
  };
}

// --- yt-dlp extraction ---

/** Shell out to yt-dlp to download auto/manual subs as json3 and parse them. */
async function extractSubsWithYtDlp(
  videoId: string,
  lang: string,
): Promise<YouTubeTranscriptSegment[]> {
  const outTemplate = join(tmpdir(), `yt-${randomUUID()}`);
  const url = `https://www.youtube.com/watch?v=${videoId}`;

  await new Promise<void>((resolve, reject) => {
    execFile(
      "yt-dlp",
      [
        "--write-auto-sub",
        "--write-sub",
        "--sub-lang",
        lang,
        "--sub-format",
        "json3",
        "--skip-download",
        "-o",
        outTemplate,
        url,
      ],
      { timeout: 30_000 },
      (err) => {
        if (err) reject(new Error(`yt-dlp failed: ${err.message}`));
        else resolve();
      },
    );
  });

  // yt-dlp writes to <template>.<lang>.json3
  const subPath = `${outTemplate}.${lang}.json3`;
  let raw: string;
  try {
    raw = await readFile(subPath, "utf8");
  } catch {
    throw new Error(`No subtitles found for language "${lang}"`);
  } finally {
    // Clean up temp file
    await unlink(subPath).catch(() => {});
  }

  return parseJson3Subs(raw);
}

/** Parse yt-dlp's json3 subtitle format into transcript segments. */
function parseJson3Subs(raw: string): YouTubeTranscriptSegment[] {
  const data = JSON.parse(raw) as {
    events?: { tStartMs?: number; dDurationMs?: number; segs?: { utf8?: string }[] }[];
  };

  const segments: YouTubeTranscriptSegment[] = [];
  for (const event of data.events ?? []) {
    if (!event.segs) continue;
    const text = event.segs
      .map((s) => s.utf8 ?? "")
      .join("")
      .trim();
    if (!text || text === "\n") continue;
    segments.push({
      text,
      startMs: event.tStartMs ?? 0,
      durationMs: event.dDurationMs ?? 0,
    });
  }
  return segments;
}

// --- metadata from watch page ---

async function fetchMetadata(videoId: string): Promise<{ title: string; description: string }> {
  const pageUrl = `https://www.youtube.com/watch?v=${encodeURIComponent(videoId)}`;
  const res = await globalThis.fetch(pageUrl, {
    headers: { "User-Agent": BROWSER_UA },
  });
  if (!res.ok) {
    throw new Error(`YouTube page fetch failed: ${res.status}`);
  }
  const html = await res.text();
  const player = extractPlayerResponse(html);
  return {
    title: player?.videoDetails?.title ?? "",
    description: player?.videoDetails?.shortDescription ?? "",
  };
}

// --- legacy path (used when fetchFn is injected, e.g. tests) ---

async function fetchYouTubeDocLegacy(
  videoId: string,
  opts: FetchYouTubeDocOptions,
): Promise<YouTubeDocResult> {
  const fetcher = opts.fetchFn!;

  const pageUrl = `https://www.youtube.com/watch?v=${encodeURIComponent(videoId)}`;
  const pageRes = await fetcher(pageUrl, {
    headers: { "User-Agent": BROWSER_UA },
  });
  if (!pageRes.ok) {
    throw new Error(`YouTube page fetch failed: ${pageRes.status}`);
  }
  const html = await pageRes.text();

  const playerJson = extractPlayerResponse(html);
  if (!playerJson) {
    throw new Error("Could not find ytInitialPlayerResponse in page");
  }

  const title: string = playerJson.videoDetails?.title ?? "";
  const description: string = playerJson.videoDetails?.shortDescription ?? "";

  const tracks: CaptionTrack[] =
    playerJson.captions?.playerCaptionsTracklistRenderer?.captionTracks ?? [];

  if (tracks.length === 0) {
    throw new Error("No caption tracks available for this video");
  }

  const track = pickTrack(tracks, opts.language) ?? tracks[0];
  const xmlRes = await fetcher(track.baseUrl, {
    headers: { "User-Agent": BROWSER_UA },
  });
  if (!xmlRes.ok) {
    throw new Error(`Timedtext fetch failed: ${xmlRes.status}`);
  }
  const xml = await xmlRes.text();

  const timestamps = parseTimedText(xml);
  const transcript = timestamps.map((s) => s.text).join(" ");

  return {
    videoId,
    title,
    description,
    transcript,
    timestamps,
    extractedAt: new Date().toISOString(),
  };
}

// --- shared helpers ---

type CaptionTrack = {
  baseUrl: string;
  languageCode?: string;
};

type PlayerResponse = {
  videoDetails?: { title?: string; shortDescription?: string };
  captions?: {
    playerCaptionsTracklistRenderer?: { captionTracks?: CaptionTrack[] };
  };
};

function extractPlayerResponse(html: string): PlayerResponse | null {
  const marker = "var ytInitialPlayerResponse = ";
  const start = html.indexOf(marker);
  if (start === -1) return null;

  const jsonStart = start + marker.length;
  let depth = 0;
  let end = -1;
  for (let i = jsonStart; i < html.length; i++) {
    if (html[i] === "{") depth++;
    else if (html[i] === "}") {
      depth--;
      if (depth === 0) {
        end = i + 1;
        break;
      }
    }
  }

  if (end === -1) return null;
  try {
    return JSON.parse(html.slice(jsonStart, end)) as PlayerResponse;
  } catch {
    return null;
  }
}

function pickTrack(tracks: CaptionTrack[], lang?: string): CaptionTrack | undefined {
  if (!lang) return undefined;
  return tracks.find((t) => t.languageCode === lang);
}

function htmlDecode(s: string): string {
  return s
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'")
    .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(Number(n)))
    .replace(/\n/g, " ");
}

function parseTimedText(xml: string): YouTubeTranscriptSegment[] {
  const segments: YouTubeTranscriptSegment[] = [];
  const re = /<text\s+start="([\d.]+)"\s+dur="([\d.]+)"[^>]*>([\s\S]*?)<\/text>/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(xml)) !== null) {
    segments.push({
      text: htmlDecode(m[3]).trim(),
      startMs: Math.round(Number(m[1]) * 1000),
      durationMs: Math.round(Number(m[2]) * 1000),
    });
  }
  return segments;
}
