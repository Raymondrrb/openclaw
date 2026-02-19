#!/usr/bin/env python3
"""Search historical trend and market report data via SQLite FTS5.

Inspired by tobi/qmd's approach — BM25 full-text search over local docs.
This is a lightweight Python implementation for the Rayviews pipeline,
indexing JSON trend files and markdown market reports.

Usage:
    # Index all reports (run daily or before searching)
    python3 tools/trend_history_search.py index

    # Search across all history
    python3 tools/trend_history_search.py search "portable monitor"

    # Search with filters
    python3 tools/trend_history_search.py search "robot vacuum" --source youtube --top 10
    python3 tools/trend_history_search.py search "trending earbuds" --source brave_web --days 7

    # Show what product/keyword appeared across dates
    python3 tools/trend_history_search.py timeline "portable monitor"

    # JSON output for agent consumption
    python3 tools/trend_history_search.py search "smart ring" --json
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(__file__))
from lib.common import project_root

_BASE = str(project_root())
DB_PATH = os.path.join(_BASE, "reports", ".trend_search.db")
TRENDS_DIR = os.path.join(_BASE, "reports", "trends")
MARKET_DIR = os.path.join(_BASE, "reports", "market")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS docs (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE,
            source TEXT,
            date TEXT,
            slug TEXT,
            doc_type TEXT,
            modified REAL
        )
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(
            path, source, date, slug, doc_type, title, content,
            tokenize='porter unicode61'
        )
    """)
    conn.commit()
    return conn


def extract_date(path):
    m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(path))
    return m.group(1) if m else ""


def detect_source(path):
    basename = os.path.basename(path)
    if "_brave_web" in basename:
        return "brave_web"
    if "_brave_news" in basename:
        return "brave_news"
    if "market_pulse" in basename or "market_delta" in basename or "category_of_day" in basename:
        return "market"
    return "youtube"


def extract_slug(path):
    basename = os.path.basename(path)
    # Remove date and suffixes to get the slug
    slug = re.sub(r"_\d{4}-\d{2}-\d{2}.*$", "", basename)
    return slug


def extract_content_from_json(path):
    """Extract searchable text from a trend/market JSON file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return "", ""

    parts = []
    title = data.get("query", "") or data.get("date", "") or os.path.basename(path)

    # Extract from items (trend data)
    for item in data.get("items", []):
        t = item.get("title", "")
        d = item.get("description", "")
        ch = item.get("channelTitle", "")
        if t:
            parts.append(t)
        if d:
            parts.append(d)
        if ch:
            parts.append(ch)

    # Extract from queryVelocity (market pulse JSON)
    for qv in data.get("queryVelocity", []):
        q = qv.get("query", "")
        if q:
            parts.append(q)

    # Extract top keywords
    for kw_pair in data.get("topKeywords", []):
        if isinstance(kw_pair, (list, tuple)) and kw_pair:
            parts.append(str(kw_pair[0]))

    return title, " ".join(parts)


def extract_content_from_md(path):
    """Extract searchable text from a markdown report."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return "", ""

    # First line as title
    lines = text.strip().split("\n")
    title = lines[0].lstrip("# ").strip() if lines else os.path.basename(path)
    return title, text


def index_files(conn):
    """Index all trend JSONs and market report MDs."""
    patterns = [
        (os.path.join(TRENDS_DIR, "*.json"), "json"),
        (os.path.join(MARKET_DIR, "*.json"), "json"),
        (os.path.join(MARKET_DIR, "*.md"), "md"),
    ]

    indexed = 0
    skipped = 0

    for pattern, fmt in patterns:
        for path in sorted(glob.glob(pattern)):
            mtime = os.path.getmtime(path)
            # Skip if already indexed and not modified
            row = conn.execute("SELECT modified FROM docs WHERE path = ?", (path,)).fetchone()
            if row and row[0] >= mtime:
                skipped += 1
                continue

            date = extract_date(path)
            source = detect_source(path)
            slug = extract_slug(path)
            doc_type = "trend" if "trends" in path else "market"

            if fmt == "json":
                title, content = extract_content_from_json(path)
            else:
                title, content = extract_content_from_md(path)

            if not content.strip():
                continue

            # Upsert into docs
            conn.execute("""
                INSERT INTO docs (path, source, date, slug, doc_type, modified)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    source=excluded.source, date=excluded.date,
                    slug=excluded.slug, doc_type=excluded.doc_type,
                    modified=excluded.modified
            """, (path, source, date, slug, doc_type, mtime))

            doc_id = conn.execute("SELECT id FROM docs WHERE path = ?", (path,)).fetchone()[0]

            # Delete old FTS entry if exists, then insert new
            conn.execute("DELETE FROM docs_fts WHERE rowid = ?", (doc_id,))
            conn.execute("""
                INSERT INTO docs_fts (rowid, path, source, date, slug, doc_type, title, content)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (doc_id, path, source, date, slug, doc_type, title, content))

            indexed += 1

    conn.commit()
    return indexed, skipped


def search(conn, query, source=None, days=None, top=5, as_json=False):
    """BM25 full-text search across indexed reports."""
    where_clauses = []
    params = []

    if source:
        where_clauses.append("d.source = ?")
        params.append(source)
    if days:
        cutoff = (dt.date.today() - dt.timedelta(days=days)).isoformat()
        where_clauses.append("d.date >= ?")
        params.append(cutoff)

    where_sql = ""
    if where_clauses:
        where_sql = "AND " + " AND ".join(where_clauses)

    sql = f"""
        SELECT
            d.path, d.source, d.date, d.slug, d.doc_type,
            f.title,
            snippet(docs_fts, 6, '>>>', '<<<', '...', 40) AS snippet,
            bm25(docs_fts) AS score
        FROM docs_fts f
        JOIN docs d ON d.id = f.rowid
        WHERE docs_fts MATCH ?
        {where_sql}
        ORDER BY bm25(docs_fts)
        LIMIT ?
    """
    params = [query] + params + [top]
    rows = conn.execute(sql, params).fetchall()

    results = []
    for path, source, date, slug, doc_type, title, snippet, score in rows:
        results.append({
            "path": path,
            "source": source,
            "date": date,
            "slug": slug,
            "docType": doc_type,
            "title": title,
            "snippet": snippet,
            "score": round(abs(score), 4),
        })

    if as_json:
        return json.dumps(results, indent=2)

    lines = []
    for i, r in enumerate(results, 1):
        rel_path = os.path.relpath(r["path"], _BASE)
        lines.append(f"{i}. [{r['source']}] {r['date']} — {r['title']}")
        lines.append(f"   {rel_path}  (score: {r['score']})")
        lines.append(f"   {r['snippet']}")
        lines.append("")
    return "\n".join(lines) if lines else "No results found."


def timeline(conn, query, top=20):
    """Show when a keyword/product appeared across dates."""
    sql = """
        SELECT d.date, d.source, d.slug, f.title,
               bm25(docs_fts) AS score
        FROM docs_fts f
        JOIN docs d ON d.id = f.rowid
        WHERE docs_fts MATCH ?
        ORDER BY d.date DESC, bm25(docs_fts)
        LIMIT ?
    """
    rows = conn.execute(sql, (query, top)).fetchall()

    if not rows:
        return "No results found."

    lines = [f"Timeline for '{query}':", ""]
    current_date = None
    for date, source, slug, title, score in rows:
        if date != current_date:
            current_date = date
            lines.append(f"  {date}:")
        lines.append(f"    [{source}] {slug} — {title} (score: {round(abs(score), 4)})")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description="Search historical trend and market report data.")
    sub = p.add_subparsers(dest="command")

    # index
    sub.add_parser("index", help="Index all trend and market report files")

    # search
    sp = sub.add_parser("search", help="Search indexed reports")
    sp.add_argument("query", help="Search query")
    sp.add_argument("--source", choices=["youtube", "brave_web", "brave_news", "market"])
    sp.add_argument("--days", type=int, help="Limit to last N days")
    sp.add_argument("--top", type=int, default=5, help="Number of results")
    sp.add_argument("--json", action="store_true", help="Output as JSON")

    # timeline
    tp = sub.add_parser("timeline", help="Show when a keyword appeared across dates")
    tp.add_argument("query", help="Search query")
    tp.add_argument("--top", type=int, default=20)

    args = p.parse_args()
    conn = get_db()

    if args.command == "index":
        indexed, skipped = index_files(conn)
        total = indexed + skipped
        print(f"Indexed {indexed} new/updated files ({skipped} unchanged, {total} total)")

    elif args.command == "search":
        # Auto-index before searching
        index_files(conn)
        output = search(conn, args.query, source=args.source, days=args.days,
                        top=args.top, as_json=args.json)
        print(output)

    elif args.command == "timeline":
        index_files(conn)
        print(timeline(conn, args.query, top=args.top))

    else:
        p.print_help()

    conn.close()


if __name__ == "__main__":
    main()
