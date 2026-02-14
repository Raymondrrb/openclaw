import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { parseYouTubeVideoId } from "./parse-url.js";
import { fetchYouTubeDoc } from "./transcript.js";
import { saveCompetitorVideo } from "./store.js";
import { youtubeToDoc } from "./service.js";

// --- Fixtures ---

const VIDEO_ID = "dQw4w9WgXcQ";

const PLAYER_RESPONSE = {
  videoDetails: {
    title: "Test Video Title",
    shortDescription: "A test description",
  },
  captions: {
    playerCaptionsTracklistRenderer: {
      captionTracks: [
        { baseUrl: "https://www.youtube.com/api/timedtext?v=test&lang=en", languageCode: "en" },
        { baseUrl: "https://www.youtube.com/api/timedtext?v=test&lang=es", languageCode: "es" },
      ],
    },
  },
};

function makeWatchPageHtml(playerResponse: unknown): string {
  return `<!DOCTYPE html><html><head></head><body>
<script>var ytInitialPlayerResponse = ${JSON.stringify(playerResponse)};</script>
</body></html>`;
}

const TIMED_TEXT_XML = `<?xml version="1.0" encoding="utf-8" ?>
<transcript>
  <text start="0.0" dur="2.5">Hello world</text>
  <text start="2.5" dur="3.0">This is a test &amp; demo</text>
  <text start="5.5" dur="1.5">It&#39;s working</text>
</transcript>`;

function createMockFetch(overrides?: {
  pageHtml?: string;
  pageStatus?: number;
  xmlBody?: string;
  xmlStatus?: number;
}) {
  const pageHtml = overrides?.pageHtml ?? makeWatchPageHtml(PLAYER_RESPONSE);
  const pageStatus = overrides?.pageStatus ?? 200;
  const xmlBody = overrides?.xmlBody ?? TIMED_TEXT_XML;
  const xmlStatus = overrides?.xmlStatus ?? 200;

  return vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;

    if (url.includes("youtube.com/watch")) {
      return new Response(pageHtml, { status: pageStatus });
    }
    if (url.includes("timedtext")) {
      return new Response(xmlBody, { status: xmlStatus });
    }
    return new Response("not found", { status: 404 });
  });
}

// --- parseYouTubeVideoId ---

describe("parseYouTubeVideoId", () => {
  it("extracts ID from standard watch URL", () => {
    expect(parseYouTubeVideoId("https://www.youtube.com/watch?v=dQw4w9WgXcQ")).toBe(VIDEO_ID);
  });

  it("extracts ID from short URL", () => {
    expect(parseYouTubeVideoId("https://youtu.be/dQw4w9WgXcQ")).toBe(VIDEO_ID);
  });

  it("extracts ID from embed URL", () => {
    expect(parseYouTubeVideoId("https://www.youtube.com/embed/dQw4w9WgXcQ")).toBe(VIDEO_ID);
  });

  it("extracts ID from shorts URL", () => {
    expect(parseYouTubeVideoId("https://www.youtube.com/shorts/dQw4w9WgXcQ")).toBe(VIDEO_ID);
  });

  it("extracts ID from mobile URL", () => {
    expect(parseYouTubeVideoId("https://m.youtube.com/watch?v=dQw4w9WgXcQ")).toBe(VIDEO_ID);
  });

  it("handles extra query params", () => {
    expect(
      parseYouTubeVideoId("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s&list=PLtest"),
    ).toBe(VIDEO_ID);
  });

  it("returns null for invalid URL", () => {
    expect(parseYouTubeVideoId("not-a-url")).toBeNull();
  });

  it("returns null for non-YouTube URL", () => {
    expect(parseYouTubeVideoId("https://vimeo.com/123456")).toBeNull();
  });

  it("returns null for YouTube URL without video ID", () => {
    expect(parseYouTubeVideoId("https://www.youtube.com/")).toBeNull();
  });
});

// --- fetchYouTubeDoc ---

describe("fetchYouTubeDoc", () => {
  it("extracts metadata and transcript from mocked page", async () => {
    const fetchFn = createMockFetch();
    const result = await fetchYouTubeDoc(VIDEO_ID, { fetchFn });

    expect(result.videoId).toBe(VIDEO_ID);
    expect(result.title).toBe("Test Video Title");
    expect(result.description).toBe("A test description");
    expect(result.timestamps).toHaveLength(3);
    expect(result.timestamps[0]).toEqual({ text: "Hello world", startMs: 0, durationMs: 2500 });
    expect(result.timestamps[1]).toEqual({
      text: "This is a test & demo",
      startMs: 2500,
      durationMs: 3000,
    });
    expect(result.timestamps[2]).toEqual({ text: "It's working", startMs: 5500, durationMs: 1500 });
    expect(result.transcript).toBe("Hello world This is a test & demo It's working");
    expect(result.extractedAt).toBeTruthy();
  });

  it("selects the requested language track", async () => {
    const fetchFn = createMockFetch();
    await fetchYouTubeDoc(VIDEO_ID, { fetchFn, language: "es" });

    // Second call should be the Spanish timedtext URL
    const calls = fetchFn.mock.calls;
    const timedtextCall = calls.find((c) => {
      const url = String(c[0]);
      return url.includes("timedtext");
    });
    expect(timedtextCall).toBeTruthy();
    expect(String(timedtextCall![0])).toContain("lang=es");
  });

  it("throws when page fetch fails", async () => {
    const fetchFn = createMockFetch({ pageStatus: 404 });
    await expect(fetchYouTubeDoc(VIDEO_ID, { fetchFn })).rejects.toThrow("page fetch failed: 404");
  });

  it("throws when player response is missing", async () => {
    const fetchFn = createMockFetch({ pageHtml: "<html>no player data</html>" });
    await expect(fetchYouTubeDoc(VIDEO_ID, { fetchFn })).rejects.toThrow(
      "Could not find ytInitialPlayerResponse",
    );
  });

  it("throws when no caption tracks exist", async () => {
    const noCaptions = { ...PLAYER_RESPONSE, captions: {} };
    const fetchFn = createMockFetch({ pageHtml: makeWatchPageHtml(noCaptions) });
    await expect(fetchYouTubeDoc(VIDEO_ID, { fetchFn })).rejects.toThrow("No caption tracks");
  });
});

// --- saveCompetitorVideo ---

describe("saveCompetitorVideo", () => {
  let savedUrl: string | undefined;
  let savedKey: string | undefined;

  beforeEach(() => {
    savedUrl = process.env.SUPABASE_URL;
    savedKey = process.env.SUPABASE_SERVICE_KEY;
    delete process.env.SUPABASE_URL;
    delete process.env.SUPABASE_SERVICE_KEY;
  });

  afterEach(() => {
    if (savedUrl !== undefined) process.env.SUPABASE_URL = savedUrl;
    else delete process.env.SUPABASE_URL;
    if (savedKey !== undefined) process.env.SUPABASE_SERVICE_KEY = savedKey;
    else delete process.env.SUPABASE_SERVICE_KEY;
  });

  const DOC = {
    videoId: VIDEO_ID,
    title: "Test",
    description: "Desc",
    transcript: "Hello world",
    timestamps: [{ text: "Hello world", startMs: 0, durationMs: 2500 }],
    extractedAt: "2026-01-01T00:00:00.000Z",
  };

  it("sends correct PostgREST request and returns id", async () => {
    const fetchFn = vi.fn(async () =>
      new Response(JSON.stringify([{ id: "uuid-123" }]), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await saveCompetitorVideo(DOC, {
      supabaseUrl: "https://test.supabase.co",
      supabaseKey: "test-key",
      fetchFn,
    });

    expect(result).toEqual({ id: "uuid-123" });

    // Verify request shape
    const [url, init] = fetchFn.mock.calls[0];
    expect(url).toBe("https://test.supabase.co/rest/v1/competitor_videos");
    expect(init.method).toBe("POST");
    expect(init.headers).toMatchObject({
      apikey: "test-key",
      Authorization: "Bearer test-key",
      Prefer: "return=representation,resolution=merge-duplicates",
    });

    const body = JSON.parse(init.body as string);
    expect(body.video_id).toBe(VIDEO_ID);
    expect(body.title).toBe("Test");
  });

  it("throws when SUPABASE_URL is missing", async () => {
    await expect(saveCompetitorVideo(DOC, { supabaseKey: "k" })).rejects.toThrow(
      "SUPABASE_URL is not set",
    );
  });

  it("throws when SUPABASE_SERVICE_KEY is missing", async () => {
    await expect(
      saveCompetitorVideo(DOC, { supabaseUrl: "https://x.supabase.co" }),
    ).rejects.toThrow("SUPABASE_SERVICE_KEY is not set");
  });

  it("throws on non-OK response", async () => {
    const fetchFn = vi.fn(async () => new Response("conflict", { status: 409 }));
    await expect(
      saveCompetitorVideo(DOC, {
        supabaseUrl: "https://test.supabase.co",
        supabaseKey: "k",
        fetchFn,
      }),
    ).rejects.toThrow("Supabase insert failed (409)");
  });
});

// --- youtubeToDoc (integration) ---

describe("youtubeToDoc", () => {
  it("full flow: parse → fetch → return", async () => {
    const fetchFn = createMockFetch();
    const result = await youtubeToDoc("https://www.youtube.com/watch?v=dQw4w9WgXcQ", { fetchFn });

    expect(result.videoId).toBe(VIDEO_ID);
    expect(result.title).toBe("Test Video Title");
    expect(result.transcript).toContain("Hello world");
  });

  it("full flow with store=true", async () => {
    const supabaseResponse = JSON.stringify([{ id: "uuid-456" }]);

    const fetchFn = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;

      if (url.includes("youtube.com/watch")) {
        return new Response(makeWatchPageHtml(PLAYER_RESPONSE), { status: 200 });
      }
      if (url.includes("timedtext")) {
        return new Response(TIMED_TEXT_XML, { status: 200 });
      }
      if (url.includes("supabase")) {
        return new Response(supabaseResponse, {
          status: 201,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response("not found", { status: 404 });
    });

    const result = await youtubeToDoc("https://youtu.be/dQw4w9WgXcQ", {
      fetchFn,
      store: true,
      supabaseUrl: "https://test.supabase.co",
      supabaseKey: "test-key",
    });

    expect(result.videoId).toBe(VIDEO_ID);
    // Verify Supabase was called
    const supabaseCall = fetchFn.mock.calls.find((c) => String(c[0]).includes("supabase"));
    expect(supabaseCall).toBeTruthy();
  });

  it("rejects invalid YouTube URL", async () => {
    await expect(youtubeToDoc("https://vimeo.com/123")).rejects.toThrow("Invalid YouTube URL");
  });
});
