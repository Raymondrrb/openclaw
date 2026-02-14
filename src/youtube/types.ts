/** A single timed caption segment from a YouTube video. */
export type YouTubeTranscriptSegment = {
  text: string;
  startMs: number;
  durationMs: number;
};

/** Normalized result of extracting a YouTube video's metadata + transcript. */
export type YouTubeDocResult = {
  videoId: string;
  title: string;
  description: string;
  /** Full transcript as plain text (segments joined with spaces). */
  transcript: string;
  /** Individual timed segments for downstream use. */
  timestamps: YouTubeTranscriptSegment[];
  extractedAt: string; // ISO-8601
};
