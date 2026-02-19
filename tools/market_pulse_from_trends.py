#!/usr/bin/env python3
"""Build a daily market pulse seed from YouTube trend + Brave Search JSON files."""
import argparse
import datetime as dt
import glob
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
from lib.common import save_json

_BASE_DIR = os.path.abspath(os.environ.get("PROJECT_ROOT", os.path.join(os.path.dirname(__file__), "..")))
DEFAULT_TRENDS_DIR = os.path.join(_BASE_DIR, "reports", "trends")
DEFAULT_OUT_DIR = os.path.join(_BASE_DIR, "reports", "market")


STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "best",
    "top",
    "review",
    "reviews",
    "amazon",
    "open",
    "ear",
    "earbuds",
    "vs",
    "2026",
    "new",
    "you",
    "your",
    "are",
    "how",
    "what",
    "why",
    "when",
    "guide",
    "these",
    "stop",
    "wearing",
    "hurt",
    "try",
    "instead",
    "finally",
    "fixes",
    "biggest",
    "problem",
    "built",
    "compromises",
    "reviewing",
    "unboxing",
    "translation",
    "case",
    "charging",
    "earphone",
    "earphones",
    "products",
}


def parse_args():
    p = argparse.ArgumentParser(description="Build a daily market pulse seed from trend JSON files.")
    p.add_argument("--date", default=dt.date.today().isoformat(), help="Report date in YYYY-MM-DD")
    p.add_argument("--trends-dir", default=DEFAULT_TRENDS_DIR)
    p.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    p.add_argument("--top-items", type=int, default=5)
    p.add_argument(
        "--fallback-latest",
        action="store_true",
        help="If no trend file exists for --date, fall back to the latest available snapshot.",
    )
    return p.parse_args()


def extract_date_from_path(path):
    """Extract YYYY-MM-DD from filenames like slug_DATE.json or slug_DATE_brave_web.json."""
    m = re.search(r"_(\d{4}-\d{2}-\d{2})(?:_brave_(?:web|news))?\.json$", os.path.basename(path))
    return m.group(1) if m else None


def detect_source(path, data):
    """Detect whether a trend file is from YouTube or Brave (web/news)."""
    basename = os.path.basename(path)
    if "_brave_web.json" in basename or data.get("source") == "brave" and data.get("searchType") == "web":
        return "brave_web"
    if "_brave_news.json" in basename or data.get("source") == "brave" and data.get("searchType") == "news":
        return "brave_news"
    return "youtube"


def load_trend_files(trends_dir, date_str, *, fallback_latest: bool):
    """Load YouTube trend files and Brave search files for the given date."""
    # Glob YouTube files (slug_DATE.json) and Brave files (slug_DATE_brave_web/news.json)
    patterns = [
        os.path.join(trends_dir, f"*_{date_str}.json"),
        os.path.join(trends_dir, f"*_{date_str}_brave_web.json"),
        os.path.join(trends_dir, f"*_{date_str}_brave_news.json"),
    ]
    files = sorted(set(f for pat in patterns for f in glob.glob(pat)))
    used_date = date_str

    if not files and fallback_latest:
        all_files = sorted(glob.glob(os.path.join(trends_dir, "*.json")))
        dated = []
        for path in all_files:
            d = extract_date_from_path(path)
            if d:
                dated.append((d, path))
        if dated:
            latest_date = max(d for d, _ in dated)
            files = [p for d, p in dated if d == latest_date]
            used_date = latest_date

    datasets = []
    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        data["_path"] = path
        data["_source"] = detect_source(path, data)
        datasets.append(data)
    return datasets, used_date


def extract_keywords(datasets, top_items):
    words = Counter()
    for ds in datasets:
        items = ds.get("items", [])[:top_items]
        for item in items:
            title = item.get("title", "")
            for token in re.findall(r"[A-Za-z0-9\+\-]{3,}", title.lower()):
                if token in STOPWORDS:
                    continue
                if token.isdigit():
                    continue
                words[token] += 1
    return words


def _safe_float(v, d=0.0):
    try:
        return float(v)
    except (ValueError, TypeError):
        return d


def rank_queries(datasets):
    """Rank datasets: YouTube by viewsPerHour, Brave by mention volume. Normalize to 0-100."""
    yt_ranked = []
    brave_ranked = []

    for ds in datasets:
        query = ds.get("query", "")
        items = ds.get("items", [])
        source = ds.get("_source", "youtube")

        if source == "youtube":
            best_vph = 0.0
            if items:
                best_vph = max(_safe_float(it.get("viewsPerHour", 0.0)) for it in items)
            yt_ranked.append({
                "query": query,
                "count": len(items),
                "bestViewsPerHour": round(best_vph, 2),
                "source": source,
                "sourceFile": ds.get("_path"),
            })
        else:
            # Brave: rank by total mentionScore sum as signal strength
            total_score = sum(_safe_float(it.get("mentionScore", 0)) for it in items)
            brave_ranked.append({
                "query": query,
                "count": len(items),
                "totalMentionScore": round(total_score, 2),
                "source": source,
                "sourceFile": ds.get("_path"),
            })

    yt_ranked.sort(key=lambda x: x["bestViewsPerHour"], reverse=True)
    brave_ranked.sort(key=lambda x: x["totalMentionScore"], reverse=True)

    # Normalize both to 0-100 scale for combined ranking
    if yt_ranked:
        max_vph = yt_ranked[0]["bestViewsPerHour"] or 1.0
        for r in yt_ranked:
            r["normalizedScore"] = round(r["bestViewsPerHour"] / max_vph * 100, 1)
    if brave_ranked:
        max_ms = brave_ranked[0]["totalMentionScore"] or 1.0
        for r in brave_ranked:
            r["normalizedScore"] = round(r["totalMentionScore"] / max_ms * 100, 1)

    return yt_ranked, brave_ranked


def find_combined_keywords(datasets, top_items):
    """Find keywords that appear in both YouTube and Brave results."""
    yt_words = Counter()
    brave_words = Counter()
    for ds in datasets:
        source = ds.get("_source", "youtube")
        items = ds.get("items", [])[:top_items]
        target = yt_words if source == "youtube" else brave_words
        for item in items:
            title = item.get("title", "")
            desc = item.get("description", "")
            text = f"{title} {desc}"
            for token in re.findall(r"[A-Za-z0-9\+\-]{3,}", text.lower()):
                if token in STOPWORDS or token.isdigit():
                    continue
                target[token] += 1

    # Keywords present in both sources, ranked by combined count
    overlap = set(yt_words.keys()) & set(brave_words.keys())
    combined = [(w, yt_words[w] + brave_words[w]) for w in overlap]
    combined.sort(key=lambda x: x[1], reverse=True)
    return combined


def build_markdown(date_str, source_date, datasets, yt_rank, brave_rank, keywords, combined_kw, top_items):
    ts = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat() + "Z"
    top_kw = [w for w, _ in keywords.most_common(12)]

    yt_datasets = [ds for ds in datasets if ds.get("_source") == "youtube"]
    brave_datasets = [ds for ds in datasets if ds.get("_source", "").startswith("brave")]

    lines = []
    lines.append(f"# Daily Market Pulse Seed — {date_str}")
    lines.append("")
    lines.append(f"- Generated at: {ts}")
    lines.append("- Region target: US")
    if source_date != date_str:
        lines.append(f"- Trend source date fallback: {source_date}")
    lines.append(f"- Sources: YouTube ({len(yt_datasets)} files), Brave ({len(brave_datasets)} files)")
    lines.append("- Note: This is a trend-seed report. Validate Amazon pricing/rating data before publish.")
    lines.append("")

    # Executive Summary
    lines.append("## Executive Summary")
    if not yt_rank and not brave_rank:
        lines.append("- No trend JSON files found for this date.")
    else:
        lines.append(f"- Processed {len(yt_rank)} YouTube + {len(brave_rank)} Brave query sets.")
        if yt_rank:
            lines.append(f"- Highest YouTube velocity: `{yt_rank[0]['query']}` ({yt_rank[0]['bestViewsPerHour']} views/hour peak).")
        if brave_rank:
            lines.append(f"- Highest Brave mention volume: `{brave_rank[0]['query']}` ({brave_rank[0]['totalMentionScore']} mention score).")
        if top_kw:
            lines.append(f"- Repeated topic tokens: {', '.join(top_kw[:8])}.")
        if combined_kw:
            top_combined = [w for w, _ in combined_kw[:6]]
            lines.append(f"- Cross-source keywords (YouTube + Brave): {', '.join(top_combined)}.")
    lines.append("")

    # YouTube Query Velocity Ranking
    lines.append("## YouTube Query Velocity Ranking")
    for idx, row in enumerate(yt_rank[:10], start=1):
        lines.append(
            f"{idx}. `{row['query']}` — peak {row['bestViewsPerHour']} views/hour — items: {row['count']}"
        )
    if not yt_rank:
        lines.append("- No YouTube data.")
    lines.append("")

    # Brave Web Signals
    lines.append("## Brave Web Signals")
    brave_web = [r for r in brave_rank if r["source"] == "brave_web"]
    brave_news = [r for r in brave_rank if r["source"] == "brave_news"]
    if brave_web:
        lines.append("### Web Results")
        for idx, row in enumerate(brave_web[:10], start=1):
            lines.append(
                f"{idx}. `{row['query']}` — mention score: {row['totalMentionScore']} — results: {row['count']}"
            )
    if brave_news:
        lines.append("### News Results")
        for idx, row in enumerate(brave_news[:10], start=1):
            lines.append(
                f"{idx}. `{row['query']}` — mention score: {row['totalMentionScore']} — results: {row['count']}"
            )
    if not brave_web and not brave_news:
        lines.append("- No Brave data. Run `brave_trends_batch.py` to collect web+news signals.")
    lines.append("")

    # Combined Signals
    lines.append("## Combined Signals")
    if combined_kw:
        lines.append("Keywords appearing in both YouTube and Brave results (strongest cross-source signals):")
        lines.append("")
        for idx, (word, count) in enumerate(combined_kw[:15], start=1):
            lines.append(f"{idx}. **{word}** (mentions: {count})")
    else:
        lines.append("- No overlapping keywords found between sources.")
    lines.append("")

    # Top Videos by Query (YouTube only)
    lines.append("## Top Videos by Query")
    for ds in yt_datasets:
        query = ds.get("query", "unknown query")
        lines.append(f"### {query}")
        items = ds.get("items", [])[:top_items]
        if not items:
            lines.append("- No items.")
            continue
        for i, item in enumerate(items, start=1):
            lines.append(
                f"{i}) {item.get('title', 'Untitled')} | {item.get('channelTitle', 'Unknown')} | "
                f"VPH: {item.get('viewsPerHour', 0)} | {item.get('url', '')}"
            )
    lines.append("")

    # Top Brave Results (web + news)
    if brave_datasets:
        lines.append("## Top Brave Results")
        for ds in brave_datasets:
            source_label = "Web" if ds.get("_source") == "brave_web" else "News"
            query = ds.get("query", "unknown query")
            lines.append(f"### [{source_label}] {query}")
            items = ds.get("items", [])[:top_items]
            if not items:
                lines.append("- No items.")
                continue
            for i, item in enumerate(items, start=1):
                lines.append(
                    f"{i}) {item.get('title', 'Untitled')} | {item.get('domain', '')} | "
                    f"Score: {item.get('mentionScore', 0)} | {item.get('url', '')}"
                )
        lines.append("")

    lines.append("## Suggested Market Watch (Amazon US)")
    lines.append("- Best Sellers (Electronics): https://www.amazon.com/Best-Sellers-Electronics/zgbs/electronics")
    lines.append("- Movers & Shakers (Electronics): https://www.amazon.com/gp/movers-and-shakers/electronics")
    lines.append("- New Releases (Electronics): https://www.amazon.com/gp/new-releases/electronics")
    lines.append("")
    lines.append("## Candidate Ideas For Today")
    ideas = []
    for row in yt_rank[:3]:
        q = row.get("query", "").lower()
        q = re.sub(r"\b(review|reviews|best|top|2026|amazon|us)\b", "", q)
        q = re.sub(r"\s+", " ", q).strip()
        if q:
            ideas.append(f"Top 5 {q} products over $100 (Amazon US)")
    # Add ideas from combined keywords
    for kw, _ in combined_kw:
        if len(ideas) >= 5:
            break
        if kw in STOPWORDS:
            continue
        ideas.append(f"Top 5 {kw} products over $100 (Amazon US)")
    # Fill remaining from general keywords
    for kw in top_kw:
        if len(ideas) >= 5:
            break
        if kw in STOPWORDS:
            continue
        ideas.append(f"Top 5 {kw} products over $100 (Amazon US)")

    if ideas:
        for idx, idea in enumerate(ideas[:5], start=1):
            lines.append(f"{idx}. {idea}")
    else:
        lines.append("- No keyword signals extracted.")
    lines.append("")
    lines.append("## Next Action")
    lines.append("- Run market_scout with browser checks to convert this seed into a final daily market report.")
    lines.append("")
    return "\n".join(lines)


def main():
    args = parse_args()
    if str(args.date).strip().upper() == "TODAY":
        args.date = dt.date.today().isoformat()
    os.makedirs(args.out_dir, exist_ok=True)

    datasets, source_date = load_trend_files(args.trends_dir, args.date, fallback_latest=args.fallback_latest)
    yt_rank, brave_rank = rank_queries(datasets)
    keywords = extract_keywords(datasets, args.top_items)
    combined_kw = find_combined_keywords(datasets, args.top_items)

    md = build_markdown(args.date, source_date, datasets, yt_rank, brave_rank, keywords, combined_kw, args.top_items)
    out_md = os.path.join(args.out_dir, f"{args.date}_market_pulse_seed.md")
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(md)

    yt_count = sum(1 for ds in datasets if ds.get("_source") == "youtube")
    brave_count = sum(1 for ds in datasets if ds.get("_source", "").startswith("brave"))

    out_json = os.path.join(args.out_dir, f"{args.date}_market_pulse_seed.json")
    payload = {
        "date": args.date,
        "trendSourceDate": source_date,
        "generatedAt": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat() + "Z",
        "trendFilesProcessed": yt_count,
        "braveFilesProcessed": brave_count,
        "queryVelocity": yt_rank,
        "braveSignals": brave_rank,
        "topKeywords": keywords.most_common(20),
        "combinedKeywords": combined_kw[:20],
        "sourceDir": args.trends_dir,
    }
    save_json(out_json, payload)

    print(f"Wrote seed report: {out_md}")
    print(f"Wrote seed json: {out_json}")
    print(f"  YouTube files: {yt_count}, Brave files: {brave_count}")


if __name__ == "__main__":
    main()
