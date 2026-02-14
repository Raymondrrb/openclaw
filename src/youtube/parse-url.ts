/**
 * Extract a YouTube video ID from common URL formats.
 *
 * Handles:
 *  - youtube.com/watch?v=ID
 *  - youtu.be/ID
 *  - youtube.com/embed/ID
 *  - youtube.com/shorts/ID
 *
 * Returns `null` when the URL isn't a recognised YouTube link.
 */
export function parseYouTubeVideoId(url: string): string | null {
  // 11-char base64-ish ID (letters, digits, hyphens, underscores)
  const ID = /[\w-]{11}/;

  try {
    const u = new URL(url);
    const host = u.hostname.replace(/^www\./, "");

    if (host === "youtu.be") {
      const id = u.pathname.slice(1).split("/")[0];
      return id && ID.test(id) ? id : null;
    }

    if (host === "youtube.com" || host === "m.youtube.com") {
      // /watch?v=ID
      const v = u.searchParams.get("v");
      if (v && ID.test(v)) return v;

      // /embed/ID or /shorts/ID
      const match = u.pathname.match(/^\/(embed|shorts)\/([\w-]{11})/);
      if (match) return match[2];
    }
  } catch {
    // not a valid URL
  }

  return null;
}
