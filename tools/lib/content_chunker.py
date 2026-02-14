"""Token-aware content chunker — splits long text for efficient LLM processing.

Implements the 3-pass strategy for long content:
1. INDEX: Split into sections, generate a table of contents
2. SELECT: Identify which sections contain relevant data
3. EXTRACT: Deep-process only selected sections

Uses x-markdown-tokens hint when available, otherwise estimates ~4 chars/token.

Stdlib only.

Usage:
    from lib.content_chunker import chunk_text, estimate_tokens, select_relevant_chunks

    tokens = estimate_tokens(text)   # quick estimate
    chunks = chunk_text(text, max_tokens=2000)
    relevant = select_relevant_chunks(chunks, keywords=["best overall", "top pick"])
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------

# Average chars per token for English text (conservative)
_CHARS_PER_TOKEN = 4.0


def estimate_tokens(text: str, *, hint: int | None = None) -> int:
    """Estimate token count. Uses server hint if available, else ~4 chars/token."""
    if hint is not None and hint > 0:
        return hint
    return max(1, int(len(text) / _CHARS_PER_TOKEN))


# ---------------------------------------------------------------------------
# Chunk data
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    """A section of text with metadata."""
    index: int
    text: str
    heading: str = ""
    token_estimate: int = 0
    start_line: int = 0
    end_line: int = 0
    relevance_score: float = 0.0

    @property
    def preview(self) -> str:
        """First 120 chars, single line."""
        return self.text[:120].replace("\n", " ").strip()


# ---------------------------------------------------------------------------
# Chunking strategies
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
_SECTION_BREAK_RE = re.compile(r"\n{3,}")


def chunk_by_headings(text: str, *, max_tokens: int = 2000) -> list[Chunk]:
    """Split text on markdown headings, merging small sections.

    Tries to keep each chunk under max_tokens while preserving heading boundaries.
    """
    lines = text.split("\n")
    sections: list[tuple[str, int, list[str]]] = []  # (heading, start_line, lines)
    current_heading = ""
    current_start = 0
    current_lines: list[str] = []

    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if m and current_lines:
            sections.append((current_heading, current_start, current_lines))
            current_heading = m.group(2).strip()
            current_start = i
            current_lines = [line]
        else:
            if m and not current_lines:
                current_heading = m.group(2).strip()
                current_start = i
            current_lines.append(line)

    if current_lines:
        sections.append((current_heading, current_start, current_lines))

    # Merge small sections to reach reasonable chunk sizes
    chunks: list[Chunk] = []
    buffer_heading = ""
    buffer_lines: list[str] = []
    buffer_start = 0

    for heading, start, sec_lines in sections:
        sec_text = "\n".join(sec_lines)
        sec_tokens = estimate_tokens(sec_text)

        if buffer_lines:
            buffer_text = "\n".join(buffer_lines)
            buffer_tokens = estimate_tokens(buffer_text)

            if buffer_tokens + sec_tokens > max_tokens and buffer_tokens > 0:
                # Flush buffer as chunk
                chunks.append(Chunk(
                    index=len(chunks),
                    text=buffer_text,
                    heading=buffer_heading,
                    token_estimate=buffer_tokens,
                    start_line=buffer_start,
                    end_line=buffer_start + len(buffer_lines) - 1,
                ))
                buffer_heading = heading
                buffer_lines = list(sec_lines)
                buffer_start = start
            else:
                # Merge into buffer
                buffer_lines.extend(sec_lines)
        else:
            buffer_heading = heading
            buffer_lines = list(sec_lines)
            buffer_start = start

    # Flush remaining buffer
    if buffer_lines:
        buffer_text = "\n".join(buffer_lines)
        chunks.append(Chunk(
            index=len(chunks),
            text=buffer_text,
            heading=buffer_heading,
            token_estimate=estimate_tokens(buffer_text),
            start_line=buffer_start,
            end_line=buffer_start + len(buffer_lines) - 1,
        ))

    # Split any oversized chunks
    final: list[Chunk] = []
    for chunk in chunks:
        if chunk.token_estimate > max_tokens * 1.5:
            sub_chunks = _split_oversized(chunk, max_tokens)
            for sc in sub_chunks:
                sc.index = len(final)
                final.append(sc)
        else:
            chunk.index = len(final)
            final.append(chunk)

    return final


def _split_oversized(chunk: Chunk, max_tokens: int) -> list[Chunk]:
    """Split a large chunk by paragraph breaks to stay under max_tokens."""
    paragraphs = re.split(r"\n\n+", chunk.text)
    result: list[Chunk] = []
    buf: list[str] = []
    buf_tokens = 0

    for para in paragraphs:
        para_tokens = estimate_tokens(para)
        if buf and buf_tokens + para_tokens > max_tokens:
            result.append(Chunk(
                index=0,
                text="\n\n".join(buf),
                heading=chunk.heading if not result else f"{chunk.heading} (cont.)",
                token_estimate=buf_tokens,
            ))
            buf = [para]
            buf_tokens = para_tokens
        else:
            buf.append(para)
            buf_tokens += para_tokens

    if buf:
        result.append(Chunk(
            index=0,
            text="\n\n".join(buf),
            heading=chunk.heading if not result else f"{chunk.heading} (cont.)",
            token_estimate=buf_tokens,
        ))

    return result


def chunk_by_size(text: str, *, max_tokens: int = 2000) -> list[Chunk]:
    """Simple size-based chunking by paragraph breaks."""
    paragraphs = re.split(r"\n\n+", text)
    chunks: list[Chunk] = []
    buf: list[str] = []
    buf_tokens = 0
    buf_start = 0
    current_line = 0

    for para in paragraphs:
        para_tokens = estimate_tokens(para)
        para_lines = para.count("\n") + 1

        if buf and buf_tokens + para_tokens > max_tokens:
            chunks.append(Chunk(
                index=len(chunks),
                text="\n\n".join(buf),
                token_estimate=buf_tokens,
                start_line=buf_start,
                end_line=current_line - 1,
            ))
            buf = [para]
            buf_tokens = para_tokens
            buf_start = current_line
        else:
            buf.append(para)
            buf_tokens += para_tokens

        current_line += para_lines + 1  # +1 for blank line between paras

    if buf:
        chunks.append(Chunk(
            index=len(chunks),
            text="\n\n".join(buf),
            token_estimate=buf_tokens,
            start_line=buf_start,
            end_line=current_line,
        ))

    return chunks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def chunk_text(
    text: str,
    *,
    max_tokens: int = 2000,
    token_hint: int | None = None,
    strategy: str = "auto",
) -> list[Chunk]:
    """Split text into chunks for efficient LLM processing.

    Args:
        text: The full text to chunk.
        max_tokens: Target max tokens per chunk.
        token_hint: Server-provided token estimate (from x-markdown-tokens).
        strategy: "headings" (split on ##), "size" (split on paragraphs), "auto".

    Returns:
        List of Chunk objects with text, metadata, and token estimates.
    """
    total_tokens = estimate_tokens(text, hint=token_hint)

    # Short text — no chunking needed
    if total_tokens <= max_tokens:
        return [Chunk(
            index=0,
            text=text,
            token_estimate=total_tokens,
            start_line=0,
            end_line=text.count("\n"),
        )]

    if strategy == "auto":
        # Use heading-based if text has markdown headings
        if _HEADING_RE.search(text):
            strategy = "headings"
        else:
            strategy = "size"

    if strategy == "headings":
        return chunk_by_headings(text, max_tokens=max_tokens)
    else:
        return chunk_by_size(text, max_tokens=max_tokens)


def select_relevant_chunks(
    chunks: list[Chunk],
    *,
    keywords: list[str] | None = None,
    max_chunks: int | None = None,
) -> list[Chunk]:
    """Score and filter chunks by relevance to keywords.

    Args:
        chunks: List of Chunk objects to score.
        keywords: Terms to match (case-insensitive). Higher match count = higher score.
        max_chunks: Maximum chunks to return (by score). None = all with score > 0.

    Returns:
        Filtered and sorted list of relevant chunks.
    """
    if not keywords:
        return chunks

    kw_lower = [k.lower() for k in keywords]

    for chunk in chunks:
        text_lower = chunk.text.lower()
        score = sum(1 for kw in kw_lower if kw in text_lower)
        # Bonus for heading matches
        if chunk.heading:
            heading_lower = chunk.heading.lower()
            score += sum(2 for kw in kw_lower if kw in heading_lower)
        chunk.relevance_score = score

    # Filter and sort
    scored = [c for c in chunks if c.relevance_score > 0]
    scored.sort(key=lambda c: (-c.relevance_score, c.index))

    if max_chunks is not None:
        scored = scored[:max_chunks]

    return scored


def chunk_summary(chunks: list[Chunk]) -> str:
    """One-line summary of chunks for stdout (never dumps full text)."""
    total_tokens = sum(c.token_estimate for c in chunks)
    return (
        f"{len(chunks)} chunks, ~{total_tokens} tokens total, "
        f"avg ~{total_tokens // max(len(chunks), 1)} tokens/chunk"
    )
