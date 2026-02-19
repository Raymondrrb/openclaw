#!/usr/bin/env python3
import argparse
import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Dict, List, Optional, Tuple

from lib.common import load_env_file, now_iso


BASE_DIR = os.environ.get("PROJECT_ROOT", os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
REPORTS_MARKET_DIR = os.path.join(BASE_DIR, "reports", "market")
CONTENT_DIR = os.path.join(BASE_DIR, "content")
TASKS_MD = os.path.join(BASE_DIR, "agents", "tasks", "tasks.md")
OPS_EVENTS = os.path.join(BASE_DIR, "ops", "events.jsonl")
OPS_EVENTS_BG = os.path.expanduser("~/.config/newproject/ops/events.jsonl")
VERCEL_CONTROL_ENV = os.path.expanduser("~/.config/newproject/vercel_control_plane.env")
DEFAULT_VERCEL_BASE = os.getenv("NEWPROJECT_VERCEL_BASE_URL", "https://new-project-control-plane.vercel.app")

# Lean profile: fewer agents with broader responsibilities.
# Logical role -> OpenClaw agent
ROLE_AGENT_MAP: Dict[str, str] = {
    "researcher": "researcher",
    "affiliate_linker": "researcher",
    "scriptwriter": "scriptwriter",
    "seo": "scriptwriter",
    "reviewer": "reviewer",
    "edit_strategist": "reviewer",
    "quality_gate": "reviewer",
    "asset_hunter": "dzine_producer",
    "dzine_producer": "dzine_producer",
    "davinci_editor": "davinci_editor",
    "publisher": "publisher",
    "youtube_uploader": "publisher",
}


def parse_args():
    p = argparse.ArgumentParser(
        description="Auto-dispatch opportunities from daily market pulse into agent tasks."
    )
    p.add_argument("--date", default=dt.date.today().isoformat(), help="Date in YYYY-MM-DD")
    p.add_argument("--report", default="", help="Explicit market pulse JSON path")
    p.add_argument(
        "--threshold",
        type=float,
        default=4.10,
        help="Minimum top opportunity score to trigger dispatch",
    )
    p.add_argument(
        "--notify-agents",
        action="store_true",
        help="Trigger full execution chain using lean role mapping (research + affiliate -> script + seo -> review + quality -> assets/dzine -> davinci -> publish/upload payload)",
    )
    p.add_argument(
        "--allow-elevenlabs",
        action="store_true",
        help="Allow ElevenLabs API calls (paid). Default is OFF to enforce human approval gates.",
    )
    p.add_argument(
        "--allow-dzine",
        action="store_true",
        help="Allow Dzine UI automation steps. Default is OFF to enforce human approval gates.",
    )
    p.add_argument(
        "--allow-upload",
        action="store_true",
        help="Allow external upload/pre-publish actions. Default is OFF to enforce human approval gates.",
    )
    p.add_argument(
        "--wait-seconds",
        type=int,
        default=420,
        help="Max wait per dependency file in the execution chain",
    )
    p.add_argument(
        "--max-long-videos-per-day",
        type=int,
        default=1,
        help="Maximum number of long-video episodes to start per day (default: 1)",
    )
    p.add_argument(
        "--force-dispatch",
        action="store_true",
        help="Bypass daily long-video limit check",
    )
    p.add_argument(
        "--no-repeat-days",
        type=int,
        default=15,
        help="Avoid repeating products that appeared in dispatched episodes during this lookback window",
    )
    p.add_argument(
        "--min-unique-products",
        type=int,
        default=5,
        help="Minimum number of unique (non-repeated) products required for a strict Top 5",
    )
    p.add_argument(
        "--voice-name",
        default="Thomas Louis",
        help="ElevenLabs voice name for daily narration generation",
    )
    p.add_argument(
        "--vercel-base-url",
        default=DEFAULT_VERCEL_BASE,
        help="Vercel control plane base URL",
    )
    p.add_argument(
        "--vercel-timeout-seconds",
        type=int,
        default=20,
        help="Timeout for Vercel endpoint checks",
    )
    p.add_argument(
        "--skip-vercel-control-plane",
        action="store_true",
        help="Skip Vercel control plane checks (health/heartbeat/summary)",
    )
    return p.parse_args()


def append_ops_event(event_type: str, message: str, data: Optional[Dict] = None):
    payload = {"ts": now_iso(), "type": event_type, "message": message}
    if data:
        payload["data"] = data
    raw = json.dumps(payload, ensure_ascii=False) + "\n"
    targets = [OPS_EVENTS, OPS_EVENTS_BG]
    for target in targets:
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "a", encoding="utf-8") as f:
                f.write(raw)
        except OSError:
            # Keep pipeline running even if one event sink is unavailable.
            continue



def http_json_get(url: str, bearer_token: str = "", timeout_seconds: int = 20) -> Dict:
    req = urllib.request.Request(url, method="GET")
    if bearer_token:
        req.add_header("Authorization", f"Bearer {bearer_token}")

    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            data = None
            try:
                data = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                data = {"raw": raw[:500]}
            return {
                "ok": 200 <= int(resp.status) < 300,
                "status": int(resp.status),
                "url": url,
                "data": data,
            }
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            body = str(e)
        return {
            "ok": False,
            "status": int(getattr(e, "code", 0) or 0),
            "url": url,
            "error": body[:500],
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "status": 0, "url": url, "error": str(e)}


def run_vercel_control_plane_start(base_url: str, timeout_seconds: int) -> Dict:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return {"ok": False, "skipped": True, "reason": "empty base URL"}

    health = http_json_get(f"{base}/api/health", timeout_seconds=timeout_seconds)

    # Prefer Vercel's conventional CRON_SECRET (used by Vercel Cron header auth),
    # but allow legacy/local tooling to keep using OPS_CRON_SECRET.
    cron_secret = (os.getenv("CRON_SECRET") or os.getenv("OPS_CRON_SECRET") or "").strip()
    if cron_secret:
        heartbeat = http_json_get(
            f"{base}/api/ops/heartbeat",
            bearer_token=cron_secret,
            timeout_seconds=timeout_seconds,
        )
    else:
        heartbeat = {"ok": False, "skipped": True, "reason": "CRON_SECRET/OPS_CRON_SECRET missing"}

    overall_ok = bool(health.get("ok")) and bool(heartbeat.get("ok") or heartbeat.get("skipped"))
    return {"ok": overall_ok, "baseUrl": base, "health": health, "heartbeat": heartbeat}


def run_vercel_control_plane_end(base_url: str, timeout_seconds: int) -> Dict:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return {"ok": False, "skipped": True, "reason": "empty base URL"}

    read_secret = os.getenv("OPS_READ_SECRET", "").strip()
    if read_secret:
        summary = http_json_get(
            f"{base}/api/ops/summary",
            bearer_token=read_secret,
            timeout_seconds=timeout_seconds,
        )
    else:
        summary = {"ok": False, "skipped": True, "reason": "OPS_READ_SECRET missing"}

    return {"ok": bool(summary.get("ok") or summary.get("skipped")), "baseUrl": base, "summary": summary}


def slugify(value: str, max_len: int = 48) -> str:
    if not value:
        return "opportunity"
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    if not value:
        value = "opportunity"
    return value[:max_len].rstrip("_")


def resolve_report_path(date_str: str, explicit_path: str) -> str:
    if explicit_path:
        return explicit_path
    candidate = os.path.join(REPORTS_MARKET_DIR, f"{date_str}_market_pulse.json")
    if os.path.exists(candidate):
        return candidate

    # Fallback: latest market pulse JSON available
    all_candidates = sorted(glob.glob(os.path.join(REPORTS_MARKET_DIR, "*_market_pulse.json")))
    if all_candidates:
        return all_candidates[-1]
    return candidate


def load_json(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_category_of_day(date_str: str) -> Dict:
    """
    Deterministic daily category override (rotation) to prevent drift.
    This is the authoritative source when market pulse JSON lacks categoryOfTheDay.
    """
    path = os.path.join(REPORTS_MARKET_DIR, f"{date_str}_category_of_day.json")
    if not os.path.exists(path):
        return {}
    try:
        payload = load_json(path)
    except Exception:  # noqa: BLE001
        return {}
    cat = payload.get("category") or {}
    if not isinstance(cat, dict):
        return {}
    label = str(cat.get("label", "")).strip()
    slug = str(cat.get("slug", "")).strip()
    amazon = cat.get("amazon") or {}
    starting = ""
    if isinstance(amazon, dict):
        starting = str(amazon.get("searchUrl") or amazon.get("bestSellersUrl") or "").strip()
    if not label:
        return {}
    return {"slug": slug, "label": label, "amazonStartingPoint": starting}


def confidence_to_score(value: str) -> float:
    m = {
        "high": 4.6,
        "medium": 3.9,
        "low": 3.2,
    }
    return m.get((value or "").strip().lower(), 0.0)


PRODUCT_KEY_STOPWORDS = {
    "amazon",
    "new",
    "latest",
    "model",
    "version",
}

IDEA_MATCH_STOPWORDS = {
    "best",
    "buy",
    "to",
    "in",
    "on",
    "for",
    "the",
    "and",
    "vs",
    "top",
    "review",
    "reviews",
    "guide",
    "comparison",
    "2025",
    "2026",
    "2027",
    "home",
    "your",
    "which",
    "one",
    "more",
    "upgrades",
}


def product_key(name: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", (name or "").lower())
    if not tokens:
        return ""
    filtered = [t for t in tokens if t not in PRODUCT_KEY_STOPWORDS]
    normalized = " ".join(filtered).strip()
    if normalized:
        return normalized
    return " ".join(tokens).strip()


def extract_asin_from_url(url: str) -> str:
    """
    Best-effort ASIN extractor for Amazon URLs.
    Returns uppercase ASIN (10 chars) or empty string.
    """
    if not url:
        return ""
    m = re.search(r"/(?:dp|gp/product)/([A-Za-z0-9]{10})(?:[/?]|$)", url)
    if not m:
        return ""
    return m.group(1).upper()


def product_key_for_item(item: Dict) -> str:
    """
    Prefer ASIN-based keys when a product has Amazon URLs available.
    Falls back to name-based key.
    """
    try:
        sources = item.get("sources") or []
        if isinstance(sources, list):
            for s in sources:
                asin = extract_asin_from_url(str(s))
                if asin:
                    return f"asin:{asin}"
    except Exception:
        pass
    return product_key(str(item.get("name", "")).strip())


def match_tokens(text: str) -> List[str]:
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [t for t in tokens if t not in IDEA_MATCH_STOPWORDS]


def parse_date_or_today(date_str: str) -> dt.date:
    try:
        return dt.date.fromisoformat(str(date_str))
    except ValueError:
        return dt.date.today()


def parse_ranked_products_from_research_text(text: str, limit: int = 12) -> List[str]:
    products: List[str] = []
    seen = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        candidate = ""
        # Preferred explicit product marker.
        m = re.match(r"^-+\s+\*\*Product:\*\*\s+(.+)$", line, flags=re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()

        # Numbered heading style: "## 1) Product name"
        if not candidate:
            m = re.match(r"^##\s*\d+\)\s+(.+)$", line)
            if m:
                candidate = m.group(1).strip()

        m = re.match(r"^\d+\.\s+\*\*(.+?)\*\*", line)
        if m and not candidate:
            candidate = m.group(1).strip()
        if not candidate:
            m = re.match(r"^\d+\.\s+(.+?)(?:\s+\||\s+[-–—]|$)", line)
            if m:
                candidate = m.group(1).strip()
        if not candidate and line.startswith("|") and line.count("|") >= 4:
            # Table format: | product | listing_url | ...
            cols = [c.strip() for c in line.strip("|").split("|")]
            if cols:
                candidate = cols[0]

        if not candidate:
            continue
        low = candidate.lower()
        if low in {"product", "products", "n/a"}:
            continue
        # Ignore lines that are clearly pros/cons bullets or other prose.
        if re.match(r"^(pros?|cons?|why|note|source|rating|price|confidence)\b", low):
            continue
        if len(low.split()) < 2:
            continue
        key = product_key(candidate)
        if not key or key in seen:
            continue
        seen.add(key)
        products.append(candidate)
        if len(products) >= limit:
            break
    return products


def collect_recent_product_history(report_date: str, lookback_days: int) -> Dict[str, List[str]]:
    if lookback_days <= 0:
        return {"keys": [], "names": []}

    current_day = parse_date_or_today(report_date)
    start_day = current_day - dt.timedelta(days=lookback_days)
    key_to_name: Dict[str, str] = {}

    # 1) Recent dispatched episode research outputs.
    for episode_dir in sorted(glob.glob(os.path.join(CONTENT_DIR, "auto_*_20??-??-??"))):
        if not os.path.isdir(episode_dir):
            continue
        base = os.path.basename(episode_dir)
        m = re.search(r"_(\d{4}-\d{2}-\d{2})$", base)
        if not m:
            continue
        day = parse_date_or_today(m.group(1))
        if day < start_day or day >= current_day:
            continue
        research_path = os.path.join(episode_dir, "research.md")
        if not os.path.exists(research_path):
            continue
        try:
            with open(research_path, "r", encoding="utf-8") as f:
                names = parse_ranked_products_from_research_text(f.read())
        except OSError:
            continue
        for name in names:
            key = product_key(name)
            if key and key not in key_to_name:
                key_to_name[key] = name

    # 2) Recent market pulse snapshots (fallback when episode file is missing).
    for json_path in sorted(glob.glob(os.path.join(REPORTS_MARKET_DIR, "*_market_pulse.json"))):
        m = re.search(r"(\d{4}-\d{2}-\d{2})_market_pulse\.json$", os.path.basename(json_path))
        if not m:
            continue
        day = parse_date_or_today(m.group(1))
        if day < start_day or day >= current_day:
            continue
        try:
            payload = load_json(json_path)
        except (OSError, json.JSONDecodeError):
            continue
        for item in payload.get("topProductsOver100", []) or []:
            name = str(item.get("name", "")).strip()
            key = product_key_for_item(item) or product_key(name)
            if key and key not in key_to_name:
                key_to_name[key] = name

    names = sorted(key_to_name.values())
    keys = sorted(key_to_name.keys())
    return {"keys": keys, "names": names}


def split_products_by_novelty(top_products: List[Dict], blocked_keys: set) -> Tuple[List[Dict], List[Dict]]:
    fresh: List[Dict] = []
    repeated: List[Dict] = []
    for item in top_products:
        key = product_key_for_item(item)
        if key and key in blocked_keys:
            repeated.append(item)
        else:
            fresh.append(item)
    return fresh, repeated


def assess_research_novelty(
    research_path: str, blocked_keys: set, min_unique_products: int
) -> Tuple[bool, List[str], List[str]]:
    if not os.path.exists(research_path) or os.path.getsize(research_path) == 0:
        return False, [], []
    try:
        with open(research_path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return False, [], []

    found_names = parse_ranked_products_from_research_text(text)
    found_keys = [product_key(name) for name in found_names]
    repeated_names = [name for name, key in zip(found_names, found_keys) if key and key in blocked_keys]
    unique_count = len([key for key in found_keys if key and key not in blocked_keys])

    # Must have enough unique products and zero repeated products in ranked list.
    ok = unique_count >= min_unique_products and len(repeated_names) == 0
    return ok, repeated_names, found_names


def pick_best_opportunity(report: Dict) -> Tuple[float, str, str]:
    top_products = report.get("topProductsOver100", [])
    best_score = 0.0
    best_product = ""
    for item in top_products:
        try:
            score = float(item.get("opportunityScore", 0.0) or 0.0)
        except (ValueError, TypeError):
            score = 0.0
        if score <= 0:
            score = confidence_to_score(str(item.get("confidence", "")))
        if score <= 0:
            # Last fallback when only signal count exists.
            signals = item.get("signals", []) or []
            score = min(4.8, 3.5 + (0.25 * len(signals)))
        if score > best_score:
            best_score = score
            best_product = item.get("name", "")

    idea_title = ""
    long_ideas = report.get("videoIdeas", {}).get("long", []) or report.get("opportunities", {}).get(
        "longVideos", []
    )
    if long_ideas:
        product_tokens = set(match_tokens(best_product))
        chosen_idx = 0
        chosen_title = ""
        chosen_conf_score = 0.0
        chosen_match_score = -1.0
        for idx, item in enumerate(long_ideas):
            title = item.get("title", "") or item.get("idea", "")
            if not title:
                continue
            title_tokens = set(match_tokens(title))
            overlap = len(product_tokens.intersection(title_tokens)) if product_tokens else 0
            conf_score = confidence_to_score(str(item.get("confidence", "")))
            # Strongly prefer title/product alignment. Small index bias keeps deterministic tie-break.
            match_score = (overlap * 10.0) + conf_score - (idx * 0.01)
            if match_score > chosen_match_score:
                chosen_match_score = match_score
                chosen_idx = idx
                chosen_title = title
                chosen_conf_score = conf_score
        if not chosen_title:
            first = long_ideas[0]
            chosen_title = first.get("title", "") or first.get("idea", "")
            chosen_conf_score = confidence_to_score(str(first.get("confidence", "")))
            chosen_idx = 0

        idea_title = chosen_title
        if best_score <= 0:
            best_score = chosen_conf_score
        if chosen_idx > 0:
            append_ops_event(
                "market_dispatch_alignment",
                "selected long-idea aligned with trigger product",
                {
                    "triggerProduct": best_product,
                    "selectedIdea": idea_title,
                    "selectedIndex": chosen_idx,
                },
            )

    if not idea_title and best_product:
        idea_title = f"Top 5 alternatives to {best_product} on Amazon US"

    return best_score, best_product, idea_title


def infer_category_of_day(report: Dict, best_product: str, idea_title: str) -> Tuple[str, str]:
    rising = report.get("risingCategories", []) or []
    context_tokens = set(match_tokens(f"{best_product} {idea_title}"))

    # Product-first heuristics: lock a single subcategory (never mixed).
    product_low = (best_product or "").lower()
    product_heuristics = [
        ("Smart displays", ["echo show", "smart display"]),
        ("Smart speakers", ["echo studio", "homepod", "smart speaker"]),
        ("Home security doorbells", ["doorbell", "ring wired", "ring doorbell"]),
        ("Open-ear / premium earbuds and headphones", ["airpods", "earbud", "headphone", "beats"]),
        ("Tablets", ["ipad", "tablet"]),
        ("Budget-to-mid premium TVs", ["tv", "fire tv", "roku"]),
    ]
    for label, keys in product_heuristics:
        if any(k in product_low for k in keys):
            return label, "product-first heuristic from trigger product"

    best_cat = ""
    best_reason = ""
    best_match = -1.0
    for idx, cat in enumerate(rising):
        name = str(cat.get("category", "")).strip()
        if not name:
            continue
        name_low = name.lower()
        # Convert blended labels from source into one strict subcategory.
        if "smart displays / smart speakers" in name_low:
            name = "Smart displays"
        cat_tokens = set(match_tokens(name))
        overlap = len(cat_tokens.intersection(context_tokens))
        conf = confidence_to_score(str(cat.get("confidence", "")))
        score = (overlap * 10.0) + conf - (idx * 0.01)
        if score > best_match:
            best_match = score
            best_cat = name
            evidence = (
                cat.get("observedFact")
                or cat.get("evidence")
                or cat.get("note")
                or "category selected from rising signals"
            )
            best_reason = str(evidence)

    if best_cat:
        return best_cat, best_reason

    idea_low = (idea_title or "").lower()
    heuristics = [
        ("Open-ear / premium earbuds and headphones", ["earbud", "headphone", "airpods", "beats", "open-ear"]),
        ("Smart displays", ["echo show", "smart display"]),
        ("Smart speakers", ["echo studio", "homepod", "smart speaker"]),
        ("Home security doorbells", ["doorbell", "ring"]),
        ("Budget-to-mid premium TVs", ["tv", "roku", "fire tv"]),
        ("Tablets", ["ipad", "tablet"]),
    ]
    for label, keys in heuristics:
        if any(k in idea_low for k in keys):
            return label, "fallback heuristic from selected idea title"

    return "Consumer Electronics (Amazon US)", "fallback default category"


def sanitize_idea_for_category(category_of_day: str, idea_title: str, report_date: str) -> str:
    title = (idea_title or "").strip()
    if not title:
        return title

    low = title.lower()
    if category_of_day == "Smart displays":
        banned = ["echo studio", "homepod", "smart speaker", "speaker"]
        if any(token in low for token in banned):
            return f"Top 5 Smart Displays Over $100 on Amazon US ({report_date})"
    if category_of_day == "Smart speakers":
        banned = ["echo show", "smart display", "display"]
        if any(token in low for token in banned):
            return f"Top 5 Smart Speakers Over $100 on Amazon US ({report_date})"
    return title


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def build_episode_dir(report_date: str, idea_title: str) -> str:
    slug = slugify(idea_title)
    return os.path.join(CONTENT_DIR, f"auto_{slug}_{report_date}")


def episode_has_long_pipeline_started(episode_dir: str) -> bool:
    markers = [
        "dispatch_brief.md",
        "research.md",
        "script_long.md",
        "publish_package.md",
        "youtube_upload_payload.md",
    ]
    for marker in markers:
        marker_path = os.path.join(episode_dir, marker)
        if os.path.exists(marker_path) and os.path.getsize(marker_path) > 0:
            return True
    return False


def list_started_long_episodes_for_date(report_date: str) -> List[str]:
    pattern = os.path.join(CONTENT_DIR, f"auto_*_{report_date}")
    dirs = [p for p in glob.glob(pattern) if os.path.isdir(p)]
    started = [d for d in dirs if episode_has_long_pipeline_started(d)]
    return sorted(started)


def write_dispatch_files(
    report: Dict,
    report_path: str,
    report_date: str,
    episode_dir: str,
    best_score: float,
    best_product: str,
    idea_title: str,
    category_of_day: str,
    category_reason: str,
    no_repeat_days: int,
    min_unique_products: int,
    lookback_products: List[str],
    repeated_market_candidates: List[str],
    fresh_market_count: int,
) -> Dict[str, str]:
    ensure_dir(episode_dir)

    brief_path = os.path.join(episode_dir, "dispatch_brief.md")
    researcher_prompt_path = os.path.join(episode_dir, "researcher_task.md")
    affiliate_prompt_path = os.path.join(episode_dir, "affiliate_linker_task.md")
    scriptwriter_prompt_path = os.path.join(episode_dir, "scriptwriter_task.md")
    seo_prompt_path = os.path.join(episode_dir, "seo_task.md")
    reviewer_prompt_path = os.path.join(episode_dir, "reviewer_task.md")
    edit_strategist_prompt_path = os.path.join(episode_dir, "edit_strategist_task.md")
    quality_gate_prompt_path = os.path.join(episode_dir, "quality_gate_task.md")
    asset_hunter_prompt_path = os.path.join(episode_dir, "asset_hunter_task.md")
    dzine_producer_prompt_path = os.path.join(episode_dir, "dzine_producer_task.md")
    davinci_editor_prompt_path = os.path.join(episode_dir, "davinci_editor_task.md")
    publisher_prompt_path = os.path.join(episode_dir, "publisher_task.md")
    youtube_uploader_prompt_path = os.path.join(episode_dir, "youtube_uploader_task.md")
    lookback_path = os.path.join(episode_dir, "no_repeat_lookback_15d.md")
    directive_path = os.path.join(BASE_DIR, "agents", "workflows", "daily_video_directive.md")

    top_products = report.get("topProductsOver100", [])
    sources = report.get("sources", [])
    rising = report.get("risingCategories", [])

    with open(brief_path, "w", encoding="utf-8") as f:
        f.write(f"# Auto Dispatch Brief — {report_date}\n\n")
        f.write(f"- Trigger score: **{best_score:.2f}**\n")
        f.write(f"- Trigger product: **{best_product or 'N/A'}**\n")
        f.write(f"- Category of the day: **{category_of_day}**\n")
        f.write(f"- Priority video idea: **{idea_title}**\n")
        f.write(f"- Source report: `{report_path}`\n\n")
        f.write("## Category Decision\n")
        f.write(f"- Selected category: **{category_of_day}**\n")
        f.write(f"- Selection reason: {category_reason}\n\n")
        f.write("## No-Repeat Policy\n")
        f.write(
            f"- Lookback window: **{no_repeat_days} days** (minimum **{min_unique_products}** unique products required).\n"
        )
        f.write(f"- Fresh candidates available today: **{fresh_market_count}**.\n")
        if repeated_market_candidates:
            f.write("- Repeated market candidates filtered out at dispatch stage:\n")
            for name in repeated_market_candidates[:15]:
                f.write(f"  - {name}\n")
        else:
            f.write("- No repeated market candidates were detected in today's shortlist.\n")
        f.write(
            f"- Lookback file for researcher and reviewer: `{lookback_path}`\n\n"
        )
        f.write("## Rising Categories\n")
        for idx, cat in enumerate(rising[:5], start=1):
            evidence = (
                cat.get("evidence")
                or cat.get("observedFact")
                or cat.get("note")
                or "N/A"
            )
            f.write(
                f"{idx}. {cat.get('category', 'N/A')} | Confidence: {cat.get('confidence', 'N/A')} | "
                f"Evidence: {evidence}\n"
            )
        if not rising:
            f.write("- No category signal available.\n")

        f.write("\n## Top Products Over $100\n")
        for idx, p in enumerate(top_products[:8], start=1):
            price = p.get("priceUsd", p.get("price", "N/A"))
            rating = p.get("rating", "N/A")
            rating_count = p.get("ratingCount", p.get("rating_count", "N/A"))
            score = p.get("opportunityScore", confidence_to_score(str(p.get("confidence", ""))))
            source = p.get("source", "")
            if not source:
                src_list = p.get("sources", [])
                if isinstance(src_list, list) and src_list:
                    source = src_list[0]
                else:
                    source = "N/A"
            f.write(
                f"{idx}. {p.get('name', 'N/A')} | ${price} | "
                f"Rating {rating} ({rating_count}) | "
                f"Score {score} | {source}\n"
            )
        if not top_products:
            f.write("- No product data available.\n")

        f.write("\n## Rules\n")
        f.write("- Deliverables in English.\n")
        f.write("- Amazon US focus.\n")
        f.write("- Include affiliate + AI disclosure sections in final script package.\n")
        f.write("- Generate one valid Amazon affiliate link per ranked product before publish steps.\n")
        f.write("- Treat prices/ratings as time-sensitive and add at-time-of-recording language.\n")
        f.write(
            f"- Do not repeat products listed in `{lookback_path}` unless Ray explicitly overrides.\n"
        )

        f.write("\n## Sources\n")
        for s in sources:
            f.write(f"- {s}\n")
        if not sources:
            f.write("- No sources listed in report.\n")

    with open(lookback_path, "w", encoding="utf-8") as f:
        f.write(f"# No-Repeat Product Lookback — {report_date}\n\n")
        f.write(
            f"- Rule: avoid repeating products from the last {no_repeat_days} days.\n"
        )
        f.write(f"- Minimum unique products required: {min_unique_products}\n")
        f.write(f"- Total blocked products in lookback: {len(lookback_products)}\n\n")
        if lookback_products:
            for idx, name in enumerate(lookback_products[:300], start=1):
                f.write(f"{idx}. {name}\n")
        else:
            f.write("- No blocked products found in lookback window.\n")

    with open(researcher_prompt_path, "w", encoding="utf-8") as f:
        f.write("# Researcher Task\n\n")
        f.write(f"Read: `{brief_path}`, `{lookback_path}`, `{directive_path}`\n\n")
        f.write("Task:\n")
        f.write("- You are the Product Research Specialist for this episode.\n")
        f.write("- Produce an Amazon US research pack for the priority idea in the brief.\n")
        f.write(f"- Use ONE category only: `{category_of_day}`.\n")
        f.write("- Build one strict Top 5 list in this category.\n")
        f.write("- All 5 ranked products must be in the SAME category.\n")
        f.write("- Never mix sibling subcategories in same ranking list.\n")
        f.write("  - If category is `Smart displays`: include only display-led devices (exclude smart speakers).\n")
        f.write("  - If category is `Smart speakers`: include only speaker-led devices (exclude smart displays).\n")
        f.write("- Include per product: product, price, rating, rating_count, 3 pros, 3 cons, source links.\n")
        f.write("- Every product must be currently available for sale on Amazon US (include listing URL and availability status).\n")
        f.write("- Include Amazon review metrics plus at least 2 trusted external review sources per product.\n")
        f.write("- Trusted external sources examples: RTINGS, Tom's Guide, TechRadar, PCMag, The Verge, CNET, Wirecutter.\n")
        f.write("- Pros/cons must be grounded in user/reviewer evidence. Do not invent claims.\n")
        f.write("- Add `Source Quality Matrix` with source freshness date and confidence.\n")
        f.write("- Add `Scoring Method` section (weighted) and explain why #1 beats #2.\n")
        f.write("- Add `User Consensus` section summarizing recurring praise/complaints from user reviews.\n")
        f.write("- Keep only products over $100 unless the brief explicitly says otherwise.\n")
        f.write("- If using Amazon pages: open product in a new tab, capture data, then close that product tab.\n")
        f.write("- Keep browser clean: no stale extra tabs after each product capture.\n")
        f.write("- Add one section: `What changed vs previous cycle` if data exists.\n")
        f.write(
            f"- Enforce no-repeat policy: no product from the last {no_repeat_days} days can appear in the final Top list.\n"
        )
        f.write(f"- Ensure at least {min_unique_products} unique products not present in lookback.\n")
        f.write("- Add section `Uniqueness Check` with:\n")
        f.write("  - selected products and lookback-hit status,\n")
        f.write("  - rejected repeated products,\n")
        f.write("  - final statement `No repeats in final ranked list: YES/NO`.\n")
        f.write("- If uniqueness cannot be satisfied, write `BLOCKER` and explain why.\n\n")
        f.write(f"Output path: `{os.path.join(episode_dir, 'research.md')}`\n")

    with open(affiliate_prompt_path, "w", encoding="utf-8") as f:
        f.write("# Affiliate Linker Task\n\n")
        f.write(
            f"Read: `{brief_path}`, `{os.path.join(episode_dir, 'research.md')}`, "
            f"`{BASE_DIR}/agents/workflows/affiliate_linker_playbook.md`, "
            f"`{directive_path}`\n\n"
        )
        f.write("Task:\n")
        f.write("- Build one affiliate link pack in English.\n")
        f.write("- Use one Amazon affiliate link per ranked product from research.md.\n")
        f.write("- Use OpenClaw managed browser session (no relay dependency).\n")
        f.write("- Preflight first: confirm Amazon Associates session is logged in inside managed browser.\n")
        f.write("- If not logged in, stop and write blocker `LOGIN_REQUIRED` with exact next action.\n")
        f.write("- For EACH product do this exact flow:\n")
        f.write("  1) Open listing URL in a new tab.\n")
        f.write("  2) Click the yellow SiteStripe button `Get link` at the top.\n")
        f.write("  3) In popup, copy final URL and validate it contains `tag=`.\n")
        f.write("  4) Save URL to the table row.\n")
        f.write("  5) Close the product tab immediately before moving to next product.\n")
        f.write("- Capture links from Amazon Associates/SiteStripe inside this managed session.\n")
        f.write("- Use browser actions with timeoutMs=60000 for slow product pages/popups.\n")
        f.write("- If any link cannot be generated, mark BLOCKER and stop downstream publish.\n\n")
        f.write(f"Output path: `{os.path.join(episode_dir, 'affiliate_links.md')}`\n")

    with open(scriptwriter_prompt_path, "w", encoding="utf-8") as f:
        f.write("# Scriptwriter Task\n\n")
        f.write(
            f"Read: `{brief_path}`, `{os.path.join(episode_dir, 'research.md')}`, "
            f"`{os.path.join(episode_dir, 'affiliate_links.md')}`, `{lookback_path}`, `{directive_path}`\n\n"
        )
        f.write("Task:\n")
        f.write("- You are the Narrative Conversion Specialist for this episode.\n")
        f.write("- Write one 8-12 minute YouTube script in English.\n")
        f.write("- Target ~1,300 to 1,750 words (natural speech pace for 8-12 min).\n")
        f.write(f"- Keep all ranked products inside category `{category_of_day}`.\n")
        f.write("- Structure: hook, criteria, ranked sections (#5 to #1), recap, CTA.\n")
        f.write("- Human-authentic style is mandatory: natural rhythm, opinionated phrasing, and concrete examples.\n")
        f.write("- Do NOT sound generic/AI. Avoid boilerplate transitions and robotic phrasing.\n")
        f.write("- Use varied sentence lengths and occasional conversational contractions.\n")
        f.write("- Add one contrarian insight and one real buyer scenario per ranked product.\n")
        f.write("- Use concrete evidence from research (do not invent numbers or claims).\n")
        f.write("- Keep claims grounded in research sources only.\n")
        f.write("- Include affiliate disclosure and AI disclosure block.\n")
        f.write("- Include 'at time of recording' caveat for dynamic metrics.\n\n")
        f.write("- Do not introduce products outside the Top 5 defined in `research.md`.\n\n")
        f.write(f"Output path: `{os.path.join(episode_dir, 'script_long.md')}`\n")

    with open(seo_prompt_path, "w", encoding="utf-8") as f:
        f.write("# SEO Task\n\n")
        f.write(
            f"Read: `{brief_path}`, `{os.path.join(episode_dir, 'research.md')}`, "
            f"`{os.path.join(episode_dir, 'script_long.md')}`, "
            f"`{os.path.join(episode_dir, 'affiliate_links.md')}`, `{lookback_path}`\n\n"
        )
        f.write("Task:\n")
        f.write("- You are the Search + CTR Specialist for this episode.\n")
        f.write("- Produce YouTube SEO package in English.\n")
        f.write("- Include: 3 titles, final title, description, chapters, 15 tags, 10 hashtags, pinned comment.\n")
        f.write("- Keep affiliate + AI disclosure in description text.\n\n")
        f.write(f"Output path: `{os.path.join(episode_dir, 'seo_package.md')}`\n")

    with open(reviewer_prompt_path, "w", encoding="utf-8") as f:
        f.write("# Reviewer Task\n\n")
        f.write(
            f"Read and review: `{os.path.join(episode_dir, 'research.md')}`, "
            f"`{os.path.join(episode_dir, 'script_long.md')}`, "
            f"`{os.path.join(episode_dir, 'seo_package.md')}`, `{lookback_path}`, `{directive_path}`\n\n"
        )
        f.write("Task:\n")
        f.write("- You are the Quality + Integrity Specialist for this episode.\n")
        f.write("- Validate factual consistency, risk points, and compliance requirements.\n")
        f.write("- Validate structure: strict Top 5 in same category.\n")
        f.write("- Validate all 5 products are sold on Amazon US and have listing links.\n")
        f.write("- Validate each product has pros/cons supported by trusted review sources.\n")
        f.write("- Validate writing authenticity: conversational, specific, and non-generic.\n")
        f.write("- Flag AI-sounding phrasing and provide concrete rewrites.\n")
        f.write(
            f"- Return NO-GO if any ranked product repeats from lookback window ({no_repeat_days} days).\n"
        )
        f.write("- Output GO/NO-GO with concise fixes if needed.\n\n")
        f.write(f"Output path: `{os.path.join(episode_dir, 'review_final.md')}`\n")

    with open(edit_strategist_prompt_path, "w", encoding="utf-8") as f:
        f.write("# Edit Strategist Task\n\n")
        f.write(
            f"Read: `{brief_path}`, `{os.path.join(episode_dir, 'script_long.md')}`, "
            f"`{os.path.join(episode_dir, 'seo_package.md')}`, "
            f"`{os.path.join(episode_dir, 'review_final.md')}`\n\n"
        )
        f.write("Task:\n")
        f.write("- Build one monetization-focused editing plan for this exact episode.\n")
        f.write("- Keep recommendations practical for Fliki/InVideo/CapCut workflows.\n")
        f.write("- Include: retention hooks, pacing map, B-roll rhythm, CTA timing, compliance placement.\n")
        f.write("- Add 10-item pre-publish quality checklist.\n\n")
        f.write(f"Output path: `{os.path.join(episode_dir, 'edit_strategy.md')}`\n")

    with open(quality_gate_prompt_path, "w", encoding="utf-8") as f:
        f.write("# Quality Gate Task\n\n")
        f.write(
            f"Read: `{brief_path}`, `{os.path.join(episode_dir, 'script_long.md')}`, "
            f"`{os.path.join(episode_dir, 'seo_package.md')}`, "
            f"`{os.path.join(episode_dir, 'review_final.md')}`, "
            f"`{os.path.join(episode_dir, 'edit_strategy.md')}`, "
            f"`{BASE_DIR}/reports/benchmarks/video_NwEexVMPH3I_analysis.md`\n\n"
        )
        f.write("Task:\n")
        f.write("- Score this episode against benchmark standard (0-100).\n")
        f.write("- Return PASS if score >= 85; otherwise FAIL with top fixes.\n")
        f.write("- Evaluate: hook, pacing, trust depth, CTA quality, compliance, and visual readiness.\n")
        f.write("- Fail if strict Top 5 same-category structure is missing.\n")
        f.write("- Fail if any product is outside category or not listed as available on Amazon US.\n")
        f.write("- Fail if pros/cons are not backed by trusted review sources.\n")
        f.write("- Fail if script sounds AI-generic or lacks authentic human voice.\n")
        f.write("- Include a short `Humanity Check` section with examples from script text.\n")
        f.write("- Keep output concise and actionable.\n\n")
        f.write(f"Output path: `{os.path.join(episode_dir, 'quality_gate.md')}`\n")

    with open(asset_hunter_prompt_path, "w", encoding="utf-8") as f:
        f.write("# Asset Hunter Task\n\n")
        f.write(
            f"Read: `{brief_path}`, `{os.path.join(episode_dir, 'script_long.md')}`, "
            f"`{os.path.join(episode_dir, 'review_final.md')}`, "
            f"`{os.path.join(episode_dir, 'edit_strategy.md')}`\n\n"
        )
        f.write("Task:\n")
        f.write("- Build visual package for this episode.\n")
        f.write("- Create `shot_list.md` with scene timing and visual intent.\n")
        f.write("- Create `asset_manifest.md` with source_url, license_or_usage_note, local_path, status.\n")
        f.write("- Prefer official brand media and Amazon listing references for review context.\n\n")
        f.write(f"Output paths: `{os.path.join(episode_dir, 'shot_list.md')}` and `{os.path.join(episode_dir, 'asset_manifest.md')}`\n")

    with open(dzine_producer_prompt_path, "w", encoding="utf-8") as f:
        f.write("# Dzine Producer Task\n\n")
        f.write(
            f"Read: `{brief_path}`, `{os.path.join(episode_dir, 'script_long.md')}`, "
            f"`{os.path.join(episode_dir, 'shot_list.md')}`, "
            f"`{os.path.join(episode_dir, 'asset_manifest.md')}`, "
            f"`{os.path.join(episode_dir, 'video_safe_manifest.md')}`, "
            f"`{os.path.join(episode_dir, 'elevenlabs_voiceover_report.md')}`, "
            f"`{os.path.join(episode_dir, 'quality_gate.md')}`, "
            f"`{BASE_DIR}/agents/workflows/dzine_producer_playbook.md`, "
            f"`{directive_path}`\n\n"
        )
        f.write("Task:\n")
        f.write("- Use Dzine workflow for today's episode visuals.\n")
        f.write("- In Dzine Character tab, always use Character `Ray`.\n")
        f.write("- Use New Project + Lip Sync workflow.\n")
        f.write("- In Insert Character, always fill both fields:\n")
        f.write("  - Top field: stable Ray identity anchor + outfit adapted to today's products.\n")
        f.write("  - Bottom field: product-relevant action & scene with natural product placement.\n")
        f.write("- Prefer highest quality model and 1080p output when available.\n")
        f.write("- Use ElevenLabs final voice chunks for scene sync.\n")
        f.write("- For product visuals, use Amazon references only as input and generate original variants via Dzine img2img + NanoBanana Pro.\n")
        f.write("- Generate at least 3 distinct product images per ranked product for timeline coverage.\n")
        f.write("- Each product image must show visible price text overlay from research (at time of recording).\n")
        f.write("- After capturing reference from Amazon for each product, close that product tab.\n")
        f.write("- Keep same avatar face identity; outfit can vary.\n")
        f.write("- Use OpenClaw managed browser session for Dzine (no relay dependency).\n")
        f.write("- Keep composition mix near 80-90% visuals and 10-20% lip-sync inserts.\n")
        f.write("- Create: dzine_prompt_pack.md, dzine_asset_manifest.md, dzine_generation_report.md, dzine_thumbnail_candidates.md, dzine_lipsync_map.md, dzine_img2img_plan.md.\n")
        f.write("- If blocked by auth/captcha/MFA, write blockers with exact next actions and stop.\n\n")
        f.write(
            f"Output paths: `{os.path.join(episode_dir, 'dzine_prompt_pack.md')}`, "
            f"`{os.path.join(episode_dir, 'dzine_asset_manifest.md')}`, "
            f"`{os.path.join(episode_dir, 'dzine_generation_report.md')}`, "
            f"`{os.path.join(episode_dir, 'dzine_thumbnail_candidates.md')}`, "
            f"`{os.path.join(episode_dir, 'dzine_lipsync_map.md')}`, "
            f"`{os.path.join(episode_dir, 'dzine_img2img_plan.md')}`\n"
        )

    with open(davinci_editor_prompt_path, "w", encoding="utf-8") as f:
        f.write("# DaVinci Editor Task\n\n")
        f.write(
            f"Read: `{brief_path}`, `{os.path.join(episode_dir, 'script_long.md')}`, "
            f"`{os.path.join(episode_dir, 'seo_package.md')}`, "
            f"`{os.path.join(episode_dir, 'edit_strategy.md')}`, "
            f"`{os.path.join(episode_dir, 'quality_gate.md')}`, "
            f"`{os.path.join(episode_dir, 'elevenlabs_voiceover_report.md')}`, "
            f"`{os.path.join(episode_dir, 'video_safe_manifest.md')}`, "
            f"`{BASE_DIR}/agents/workflows/davinci_editor_playbook.md`, "
            f"`{BASE_DIR}/agents/workflows/davinci_mcp_safe_profile.md`, "
            f"`{BASE_DIR}/agents/knowledge/davinci_operator_manual.md`\n\n"
        )
        f.write("Task:\n")
        f.write("- Generate DaVinci production pack for this episode.\n")
        f.write("- Create: davinci_edit_plan.md, davinci_timeline_map.md, davinci_export_preset.md, davinci_qc_checklist.md.\n")
        f.write("- If using MCP automation, stay within allowlist from davinci_mcp_safe_profile.md.\n")
        f.write("- If any required step is outside allowlist, mark REVIEW_REQUIRED and stop.\n")
        f.write("- Enforce audio intelligibility and loudness checks in QC.\n")
        f.write("- Keep it concise and production-ready for DaVinci Resolve.\n\n")
        f.write(
            f"Output paths: `{os.path.join(episode_dir, 'davinci_edit_plan.md')}`, "
            f"`{os.path.join(episode_dir, 'davinci_timeline_map.md')}`, "
            f"`{os.path.join(episode_dir, 'davinci_export_preset.md')}`, "
            f"`{os.path.join(episode_dir, 'davinci_qc_checklist.md')}`\n"
        )

    with open(publisher_prompt_path, "w", encoding="utf-8") as f:
        f.write("# Publisher Task\n\n")
        f.write(
            f"Read: `{brief_path}`, `{os.path.join(episode_dir, 'affiliate_links.md')}`, "
            f"`{os.path.join(episode_dir, 'seo_package.md')}`, "
            f"`{os.path.join(episode_dir, 'review_final.md')}`, "
            f"`{os.path.join(episode_dir, 'quality_gate.md')}`, "
            f"`{os.path.join(episode_dir, 'davinci_qc_checklist.md')}`, "
            f"`{BASE_DIR}/agents/workflows/publisher_playbook.md`\n\n"
        )
        f.write("Task:\n")
        f.write("- Generate final YouTube upload package for this episode.\n")
        f.write("- Create: publish_package.md, upload_checklist.md, youtube_studio_steps.md.\n")
        f.write("- Block and report if review is NO-GO, quality gate is FAIL, or affiliate links are missing/placeholder.\n")
        f.write("- Keep it concise and ready for manual upload with final human approval.\n\n")
        f.write(
            f"Output paths: `{os.path.join(episode_dir, 'publish_package.md')}`, "
            f"`{os.path.join(episode_dir, 'upload_checklist.md')}`, "
            f"`{os.path.join(episode_dir, 'youtube_studio_steps.md')}`\n"
        )

    with open(youtube_uploader_prompt_path, "w", encoding="utf-8") as f:
        f.write("# YouTube Uploader Task\n\n")
        f.write(
            f"Read: `{brief_path}`, `{os.path.join(episode_dir, 'affiliate_links.md')}`, "
            f"`{os.path.join(episode_dir, 'publish_package.md')}`, "
            f"`{os.path.join(episode_dir, 'seo_package.md')}`, "
            f"`{os.path.join(episode_dir, 'review_final.md')}`, "
            f"`{os.path.join(episode_dir, 'quality_gate.md')}`, "
            f"`{BASE_DIR}/agents/workflows/youtube_uploader_playbook.md`\n\n"
        )
        f.write("Task:\n")
        f.write("- Generate manual-assisted YouTube upload package.\n")
        f.write("- Create: youtube_upload_payload.md, youtube_upload_checklist.md, youtube_publish_hold.md.\n")
        f.write("- Stop before publish and require Ray approval.\n")
        f.write("- Block and report if review is NO-GO, quality gate is FAIL, or affiliate links are missing/placeholder.\n\n")
        f.write(
            f"Output paths: `{os.path.join(episode_dir, 'youtube_upload_payload.md')}`, "
            f"`{os.path.join(episode_dir, 'youtube_upload_checklist.md')}`, "
            f"`{os.path.join(episode_dir, 'youtube_publish_hold.md')}`\n"
        )

    return {
        "brief": brief_path,
        "lookback": lookback_path,
        "researcher_prompt": researcher_prompt_path,
        "affiliate_prompt": affiliate_prompt_path,
        "scriptwriter_prompt": scriptwriter_prompt_path,
        "seo_prompt": seo_prompt_path,
        "reviewer_prompt": reviewer_prompt_path,
        "edit_strategist_prompt": edit_strategist_prompt_path,
        "quality_gate_prompt": quality_gate_prompt_path,
        "asset_hunter_prompt": asset_hunter_prompt_path,
        "dzine_producer_prompt": dzine_producer_prompt_path,
        "davinci_editor_prompt": davinci_editor_prompt_path,
        "publisher_prompt": publisher_prompt_path,
        "youtube_uploader_prompt": youtube_uploader_prompt_path,
    }


def update_tasks(tasks_md_path: str, dispatch_token: str, idea_title: str, episode_dir: str) -> bool:
    if not os.path.exists(tasks_md_path):
        return False

    with open(tasks_md_path, "r", encoding="utf-8") as f:
        text = f.read()

    if dispatch_token in text:
        return False

    lines = text.splitlines()
    insert_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "## Assigned":
            insert_idx = i + 1
            break

    if insert_idx is None:
        lines.append("")
        lines.append("## Assigned")
        insert_idx = len(lines)

    new_lines = [
        f"- [ ] {dispatch_token} Researcher (research + affiliate links) kickoff -> {idea_title}",
        f"- [ ] {dispatch_token} Scriptwriter (script + SEO package) after affiliate_links.md",
        f"- [ ] {dispatch_token} Reviewer (review + edit strategy + quality gate) after seo_package.md",
        f"- [ ] {dispatch_token} Dzine Producer (assets + Dzine package) after quality_gate.md PASS",
        f"- [ ] {dispatch_token} DaVinci Editor after Dzine package + voiceover",
        f"- [ ] {dispatch_token} Publisher (publish package + upload payload draft) after DaVinci plan",
        f"  Path: {episode_dir}",
    ]

    lines[insert_idx:insert_idx] = new_lines + [""]
    with open(tasks_md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return True


def resolve_agent_for_role(role: str) -> str:
    return ROLE_AGENT_MAP.get(role, role)


def notify_agent(agent: str, message: str, *, session_id: str = "") -> Tuple[bool, str]:
    # Keep a generous agent timeout so long browser-assisted tasks can finish.
    cmd = ["openclaw", "agent", "--agent", agent, "--timeout", "900"]
    if session_id:
        cmd += ["--session-id", session_id]
    cmd += ["--message", message]
    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except Exception as e:  # noqa: BLE001
        return False, str(e)

    ok = res.returncode == 0
    out = (res.stdout or res.stderr or "").strip()
    return ok, out


def wait_for_file(path: str, max_seconds: int, step_seconds: int = 6, min_mtime: float = 0.0) -> bool:
    waited = 0
    while waited < max_seconds:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            if min_mtime <= 0.0 or os.path.getmtime(path) >= min_mtime:
                return True
        time.sleep(step_seconds)
        waited += step_seconds
    if os.path.exists(path) and os.path.getsize(path) > 0:
        if min_mtime <= 0.0 or os.path.getmtime(path) >= min_mtime:
            return True
    return False


def wait_for_files(
    paths: List[str], max_seconds: int, step_seconds: int = 6, min_mtime: float = 0.0
) -> Tuple[bool, List[str]]:
    waited = 0
    missing: List[str] = []
    while waited < max_seconds:
        missing = []
        for p in paths:
            if not os.path.exists(p) or os.path.getsize(p) == 0:
                missing.append(p)
                continue
            if min_mtime > 0.0 and os.path.getmtime(p) < min_mtime:
                missing.append(p)
        if not missing:
            return True, []
        time.sleep(step_seconds)
        waited += step_seconds
    return False, missing


def ready_after_step(path: str, ok: bool, output: str, wait_seconds: int, min_mtime: float) -> bool:
    if not ok:
        return False
    low_out = (output or "").lower()
    # Fallback: if agent explicitly referenced path and file exists, accept to avoid needless blocking.
    if path in (output or "") and os.path.exists(path) and os.path.getsize(path) > 0:
        return True
    if os.path.exists(path) and os.path.getsize(path) > 0:
        success_hints = ["done", "completed", "conclu", "feito", "saved", "salvo", "updated", "overwrote"]
        if any(h in low_out for h in success_hints):
            return True
    if wait_for_file(path, wait_seconds, min_mtime=min_mtime):
        return True
    return False


def reviewer_is_go(review_path: str) -> bool:
    if not os.path.exists(review_path):
        return False
    try:
        with open(review_path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return False
    if re.search(r"\bdecision\b\s*:\s*\**\s*go\b", text, flags=re.IGNORECASE):
        return True
    return False


def quality_gate_is_pass(quality_gate_path: str) -> bool:
    if not os.path.exists(quality_gate_path):
        return False
    try:
        with open(quality_gate_path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return False

    if re.search(r"\b(pass|approved)\b", text, flags=re.IGNORECASE):
        return True
    if re.search(r"\bscore\b[^0-9]{0,8}([8-9][5-9]|100)\b", text, flags=re.IGNORECASE):
        return True
    return False


def affiliate_links_ready(affiliate_links_path: str, min_links: int = 3) -> bool:
    if not os.path.exists(affiliate_links_path) or os.path.getsize(affiliate_links_path) == 0:
        return False
    try:
        with open(affiliate_links_path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return False

    if re.search(r"\[(ADD_LINK|TODO|TBD)\]", text, flags=re.IGNORECASE):
        return False
    if re.search(r"\b(ADD_LINK|TODO|TBD|PLACEHOLDER)\b", text, flags=re.IGNORECASE):
        return False
    if re.search(r"\b(BLOCKER|BLOCKED)\b", text, flags=re.IGNORECASE):
        return False

    # Expected row format:
    # | product | listing_url | affiliate_url | source_method | OK |
    row_pattern = re.compile(
        r"^\|\s*[^|]+\|\s*https?://[^|]+\|\s*https?://[^|]+\|\s*[^|]+\|\s*OK\s*\|$",
        flags=re.IGNORECASE | re.MULTILINE,
    )
    ok_rows = row_pattern.findall(text)
    return len(ok_rows) >= min_links


def file_contains(path: str, pattern: str, flags: int = re.IGNORECASE) -> bool:
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return False
    return re.search(pattern, text, flags=flags) is not None


def restart_openclaw_browser() -> Tuple[bool, str]:
    cmds = [
        ["openclaw", "browser", "stop", "--json"],
        ["openclaw", "browser", "start", "--json"],
        ["openclaw", "browser", "status", "--json"],
    ]
    outputs: List[str] = []
    for cmd in cmds:
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
        except Exception as e:  # noqa: BLE001
            return False, str(e)
        out = (res.stdout or res.stderr or "").strip()
        outputs.append(out)
        if res.returncode != 0:
            return False, out
    return True, "\n".join(outputs[-2:])


def run_video_safe_transform(episode_dir: str) -> Tuple[bool, str]:
    cmd = [
        "/usr/bin/python3",
        os.path.join(BASE_DIR, "tools", "build_video_safe_assets.py"),
        "--content-dir",
        episode_dir,
        "--overwrite",
    ]
    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
    except Exception as e:  # noqa: BLE001
        return False, str(e)

    ok = res.returncode == 0
    out = (res.stdout or res.stderr or "").strip()
    return ok, out


def run_elevenlabs_voiceover(script_path: str, episode_dir: str, voice_name: str) -> Tuple[bool, str, str]:
    voice_slug = slugify(voice_name, 24)
    output_dir = os.path.join(episode_dir, f"voiceover_{voice_slug}")
    report_path = os.path.join(episode_dir, "elevenlabs_voiceover_report.md")

    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        return False, "Missing ELEVENLABS_API_KEY in environment.", report_path

    cmd = [
        "/usr/bin/python3",
        os.path.join(BASE_DIR, "tools", "elevenlabs_voiceover_api.py"),
        "--script",
        script_path,
        "--voice-name",
        voice_name,
        "--output-dir",
        output_dir,
        "--report",
        report_path,
        "--overwrite",
    ]
    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
    except Exception as e:  # noqa: BLE001
        return False, str(e), report_path

    ok = res.returncode == 0 and os.path.exists(report_path) and os.path.getsize(report_path) > 0
    out = (res.stdout or res.stderr or "").strip()
    return ok, out, report_path


def voiceover_report_ready(report_path: str) -> bool:
    if not os.path.exists(report_path) or os.path.getsize(report_path) == 0:
        return False
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return False
    if re.search(r"\|\s*`[^`]+`\s*\|\s*`[^`]+`\s*\|\s*FAIL\b", text, flags=re.IGNORECASE):
        return False
    if re.search(r"possible clipping", text, flags=re.IGNORECASE):
        return False
    return True


def run_davinci_preflight() -> Tuple[bool, str]:
    cmd = ["/usr/bin/python3", os.path.join(BASE_DIR, "tools", "davinci_smoke_test.py")]
    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
    except Exception as e:  # noqa: BLE001
        return False, str(e)

    report_json = os.path.join(BASE_DIR, "tmp", "davinci_smoke", "smoke_report.json")
    if not (res.returncode == 0 and os.path.exists(report_json)):
        out = (res.stdout or res.stderr or "").strip()
        return False, out[:500]

    try:
        with open(report_json, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:  # noqa: BLE001
        return False, f"Failed reading smoke_report.json: {e}"

    ok = bool(payload.get("ok"))
    return ok, json.dumps(payload, ensure_ascii=False)[:500]


def main():
    args = parse_args()
    load_env_file(VERCEL_CONTROL_ENV)

    if str(args.date).strip().upper() == "TODAY":
        args.date = dt.date.today().isoformat()

    vercel_start = {}
    if args.skip_vercel_control_plane:
        vercel_start = {"ok": True, "skipped": True, "reason": "flag --skip-vercel-control-plane"}
    else:
        vercel_start = run_vercel_control_plane_start(args.vercel_base_url, args.vercel_timeout_seconds)
        append_ops_event(
            "vercel_control_plane_start",
            "vercel control plane start checks",
            {
                "baseUrl": vercel_start.get("baseUrl", ""),
                "healthOk": bool(vercel_start.get("health", {}).get("ok")),
                "heartbeatOk": bool(vercel_start.get("heartbeat", {}).get("ok")),
                "heartbeatSkipped": bool(vercel_start.get("heartbeat", {}).get("skipped")),
            },
        )

    def finish_with_result(payload: Dict, exit_code: int = 0):
        payload.setdefault("vercelControlPlaneStart", vercel_start)
        if "vercelControlPlaneEnd" not in payload:
            if args.skip_vercel_control_plane:
                vercel_end_local = {
                    "ok": True,
                    "skipped": True,
                    "reason": "flag --skip-vercel-control-plane",
                }
            else:
                vercel_end_local = run_vercel_control_plane_end(
                    args.vercel_base_url, args.vercel_timeout_seconds
                )
                append_ops_event(
                    "vercel_control_plane_end",
                    "vercel control plane end checks",
                    {
                        "baseUrl": vercel_end_local.get("baseUrl", ""),
                        "summaryOk": bool(vercel_end_local.get("summary", {}).get("ok")),
                        "summarySkipped": bool(
                            vercel_end_local.get("summary", {}).get("skipped")
                        ),
                    },
                )
            payload["vercelControlPlaneEnd"] = vercel_end_local
        print(json.dumps(payload, indent=2))
        if exit_code:
            sys.exit(exit_code)

    report_path = resolve_report_path(args.date, args.report)
    if not os.path.exists(report_path):
        result = {
            "dispatched": False,
            "reason": "market_pulse_report_missing",
            "reportPath": report_path,
            "date": args.date,
        }
        append_ops_event(
            "market_dispatch_error",
            "market pulse report missing",
            {"report_path": report_path, "date": args.date},
        )
        finish_with_result(result, exit_code=2)
        return

    report = load_json(report_path)
    report_date = report.get("date", args.date)

    lookback_history = collect_recent_product_history(report_date, args.no_repeat_days)
    blocked_keys = set(lookback_history.get("keys", []))
    blocked_names = lookback_history.get("names", [])
    original_top_products = list(report.get("topProductsOver100", []) or [])
    fresh_top_products, repeated_top_products = split_products_by_novelty(
        original_top_products, blocked_keys
    )
    repeated_top_names = [
        str(item.get("name", "")).strip()
        for item in repeated_top_products
        if str(item.get("name", "")).strip()
    ]
    fresh_top_count = len(fresh_top_products)

    if args.no_repeat_days > 0 and original_top_products:
        report = dict(report)
        # Preserve ranked order with novelty-first preference.
        report["topProductsOver100"] = (fresh_top_products + repeated_top_products)[:12]

    novelty_precheck: Optional[Dict] = None
    if args.no_repeat_days > 0 and original_top_products and fresh_top_count < args.min_unique_products:
        novelty_precheck = {
            "warning": "insufficient_unique_candidates_in_market_snapshot",
            "date": report_date,
            "lookbackDays": args.no_repeat_days,
            "minUniqueProducts": args.min_unique_products,
            "freshCandidates": fresh_top_count,
            "repeatedCandidates": len(repeated_top_products),
            "repeatedProductNames": repeated_top_names[:15],
            "action": "continue_dispatch_and_enforce_uniqueness_in_research_step",
        }
        append_ops_event("market_dispatch_warning", "low unique candidate count in precheck", novelty_precheck)

    best_score, best_product, idea_title = pick_best_opportunity(report)
    # Prefer the explicit category-of-the-day selected upstream (rotation),
    # so we don't drift back into "default" categories like headphones based on stale trend seeds.
    category_override = report.get("categoryOfTheDay") or {}
    if isinstance(category_override, dict) and str(category_override.get("label", "")).strip():
        category_of_day = str(category_override["label"]).strip()
        category_reason = "categoryOfTheDay from market pulse report"
    else:
        # If the report lacks categoryOfTheDay, fall back to the deterministic rotation file.
        # This keeps the system predictable and prevents heuristic drift into headphones.
        rot = load_category_of_day(report_date)
        if rot.get("label"):
            category_of_day = str(rot["label"]).strip()
            category_reason = "categoryOfTheDay from rotation file"
            # Ensure the report still carries the override for downstream consumers.
            report = dict(report)
            report["categoryOfTheDay"] = rot
        else:
            category_of_day, category_reason = infer_category_of_day(report, best_product, idea_title)
    original_idea_title = idea_title
    idea_title = sanitize_idea_for_category(category_of_day, idea_title, report_date)
    if idea_title != original_idea_title:
        append_ops_event(
            "market_dispatch_alignment",
            "rewrote idea title to preserve strict single-subcategory episode",
            {
                "categoryOfDay": category_of_day,
                "originalIdeaTitle": original_idea_title,
                "rewrittenIdeaTitle": idea_title,
            },
        )
    if best_score < args.threshold:
        result = {
            "dispatched": False,
            "reason": "score_below_threshold",
            "bestScore": round(best_score, 2),
            "threshold": args.threshold,
        }
        append_ops_event("market_dispatch_skipped", "score below threshold", result)
        finish_with_result(result)
        return

    episode_dir = build_episode_dir(report_date, idea_title)
    planned_episode_dir = episode_dir
    started_today = list_started_long_episodes_for_date(report_date)
    started_other = [d for d in started_today if os.path.abspath(d) != os.path.abspath(episode_dir)]
    resumed_existing = False
    if (
        not args.force_dispatch
        and args.max_long_videos_per_day >= 0
        and len(started_other) >= args.max_long_videos_per_day
    ):
        if started_today:
            episode_dir = started_today[-1]
            resumed_existing = True
            append_ops_event(
                "market_dispatch_resumed",
                "daily limit reached, resuming existing episode",
                {
                    "date": report_date,
                    "episodeDir": episode_dir,
                    "plannedEpisodeDir": planned_episode_dir,
                    "maxLongVideosPerDay": args.max_long_videos_per_day,
                },
            )
        else:
            result = {
                "dispatched": False,
                "reason": "daily_long_video_limit_reached",
                "date": report_date,
                "maxLongVideosPerDay": args.max_long_videos_per_day,
                "existingEpisodeDirs": started_today,
                "plannedEpisodeDir": episode_dir,
                "hint": "Use --force-dispatch only if you intentionally want more than the daily cap.",
            }
            append_ops_event("market_dispatch_skipped", "daily long video limit reached", result)
            finish_with_result(result)
            return

    paths = write_dispatch_files(
        report=report,
        report_path=report_path,
        report_date=report_date,
        episode_dir=episode_dir,
        best_score=best_score,
        best_product=best_product,
        idea_title=idea_title,
        category_of_day=category_of_day,
        category_reason=category_reason,
        no_repeat_days=args.no_repeat_days,
        min_unique_products=args.min_unique_products,
        lookback_products=blocked_names,
        repeated_market_candidates=repeated_top_names,
        fresh_market_count=fresh_top_count,
    )

    dispatch_token = f"[AUTO_DISPATCH::{report_date}::{slugify(idea_title, 24)}]"
    tasks_updated = update_tasks(
        tasks_md_path=TASKS_MD,
        dispatch_token=dispatch_token,
        idea_title=idea_title,
        episode_dir=episode_dir,
    )

    notify_results: List[Dict] = []
    if args.notify_agents:
        research_output = os.path.join(episode_dir, "research.md")
        affiliate_output = os.path.join(episode_dir, "affiliate_links.md")
        script_output = os.path.join(episode_dir, "script_long.md")
        seo_output = os.path.join(episode_dir, "seo_package.md")
        review_output = os.path.join(episode_dir, "review_final.md")
        edit_strategy_output = os.path.join(episode_dir, "edit_strategy.md")
        quality_gate_output = os.path.join(episode_dir, "quality_gate.md")
        shot_output = os.path.join(episode_dir, "shot_list.md")
        asset_manifest_output = os.path.join(episode_dir, "asset_manifest.md")
        video_safe_manifest_output = os.path.join(episode_dir, "video_safe_manifest.md")
        dzine_generation_report_output = os.path.join(episode_dir, "dzine_generation_report.md")
        dzine_prompt_pack_output = os.path.join(episode_dir, "dzine_prompt_pack.md")
        dzine_asset_manifest_output = os.path.join(episode_dir, "dzine_asset_manifest.md")
        dzine_thumbnail_output = os.path.join(episode_dir, "dzine_thumbnail_candidates.md")
        dzine_lipsync_map_output = os.path.join(episode_dir, "dzine_lipsync_map.md")
        dzine_img2img_plan_output = os.path.join(episode_dir, "dzine_img2img_plan.md")
        davinci_edit_plan_output = os.path.join(episode_dir, "davinci_edit_plan.md")
        publish_package_output = os.path.join(episode_dir, "publish_package.md")
        youtube_upload_payload_output = os.path.join(episode_dir, "youtube_upload_payload.md")
        run_start = time.time()
        session_suffix = slugify(os.path.basename(episode_dir), 48)

        def mark_skipped(agents: List[str], reason: str):
            for a in agents:
                notify_results.append({"agent": a, "ok": False, "output": f"Skipped: {reason}"})

        def run_and_wait(agent: str, message: str, output_path: str = "") -> bool:
            resolved_agent = resolve_agent_for_role(agent)
            # Use an explicit per-episode session id to prevent cross-day context drift.
            # This avoids the "why did it pick headphones again?" issue caused by long-lived chat memory.
            session_id = f"agent:{resolved_agent}:{session_suffix}"
            ok, out = notify_agent(resolved_agent, message, session_id=session_id)
            ready = ok
            if output_path:
                ready = ready_after_step(output_path, ok, out, args.wait_seconds, run_start)
            notify_results.append(
                {
                    "agent": agent,
                    "resolvedAgent": resolved_agent,
                    "ok": ready,
                    "output": (out or "")[:500],
                }
            )
            return ready

        researcher_msg = (
            "New auto-dispatch task opened. "
            f"Read {paths['researcher_prompt']} and execute full research now. "
            f"Overwrite and save result to {research_output}. "
            "Include product, price, rating, rating_count, pros, cons, and source links."
        )
        if not run_and_wait("researcher", researcher_msg, research_output):
            mark_skipped(
                [
                    "affiliate_linker",
                    "scriptwriter",
                    "seo",
                    "reviewer",
                    "edit_strategist",
                    "quality_gate",
                    "asset_hunter",
                    "video_safe_builder",
                    "dzine_producer",
                    "davinci_editor",
                    "publisher",
                    "youtube_uploader",
                ],
                f"research.md not ready after {args.wait_seconds}s",
            )
        else:
            research_novelty_ok = True
            if args.no_repeat_days > 0 and blocked_keys:
                novelty_ok, repeated_found, parsed_names = assess_research_novelty(
                    research_output,
                    blocked_keys,
                    args.min_unique_products,
                )
                if not novelty_ok:
                    repeated_text = ", ".join(repeated_found[:8]) if repeated_found else "unknown"
                    retry_msg = (
                        "Your last research output violated no-repeat policy. "
                        f"Read {paths['lookback']} and rewrite {research_output} now. "
                        f"Remove repeated products from last {args.no_repeat_days} days. "
                        f"Need at least {args.min_unique_products} unique products. "
                        f"Repeated detected: {repeated_text}. "
                        "Keep the same output format and include the Uniqueness Check section."
                    )
                    retry_ready = run_and_wait("researcher", retry_msg, research_output)
                    if retry_ready:
                        novelty_ok, repeated_found, parsed_names = assess_research_novelty(
                            research_output,
                            blocked_keys,
                            args.min_unique_products,
                        )
                    if not novelty_ok:
                        research_novelty_ok = False
                        notify_results.append(
                            {
                                "agent": "researcher",
                                "ok": False,
                                "output": (
                                    "research.md failed no-repeat validation after retry. "
                                    f"repeated={', '.join(repeated_found[:8]) or 'unknown'} "
                                    f"| parsed_count={len(parsed_names)}"
                                )[:500],
                            }
                        )

            if not research_novelty_ok:
                mark_skipped(
                    [
                        "affiliate_linker",
                        "scriptwriter",
                        "seo",
                        "reviewer",
                        "edit_strategist",
                        "quality_gate",
                        "asset_hunter",
                        "video_safe_builder",
                        "dzine_producer",
                        "davinci_editor",
                        "publisher",
                        "youtube_uploader",
                    ],
                    "research.md violates no-repeat policy",
                )
            else:
                affiliate_msg = (
                    "Research is ready for this auto-dispatch task. "
                    f"Read {paths['affiliate_prompt']} and execute affiliate link collection now. "
                    f"Overwrite output at {affiliate_output}. "
                    "Use one valid Amazon affiliate link per ranked product and avoid placeholders."
                )
                affiliate_ready = run_and_wait("affiliate_linker", affiliate_msg, affiliate_output)
                if affiliate_ready and not affiliate_links_ready(affiliate_output, min_links=3):
                    affiliate_ready = False
                    notify_results.append(
                        {
                            "agent": "affiliate_linker",
                            "ok": False,
                            "output": "affiliate_links.md exists but failed validation (missing/placeholder/non-Amazon links).",
                        }
                    )

                # Auto-heal path: browser-control timeout can happen when the managed profile
                # stalls. Restart OpenClaw browser once and retry affiliate collection.
                affiliate_timed_out = file_contains(
                    affiliate_output,
                    r"Can't reach the OpenClaw browser control service|timed out after 20000ms",
                )
                if not affiliate_ready and affiliate_timed_out:
                    restart_ok, restart_out = restart_openclaw_browser()
                    notify_results.append(
                        {
                            "agent": "affiliate_linker",
                            "ok": restart_ok,
                            "output": (
                                "Auto-restart OpenClaw browser before retry. "
                                + (restart_out or "")
                            )[:500],
                        }
                    )
                    if restart_ok:
                        retry_msg = (
                            "Retry affiliate collection after managed-browser restart. "
                            f"Read {paths['affiliate_prompt']} again and overwrite {affiliate_output}. "
                            "If not logged into Associates, write LOGIN_REQUIRED blocker."
                        )
                        affiliate_ready = run_and_wait("affiliate_linker", retry_msg, affiliate_output)
                        if affiliate_ready and not affiliate_links_ready(affiliate_output, min_links=3):
                            affiliate_ready = False
                            notify_results.append(
                                {
                                    "agent": "affiliate_linker",
                                    "ok": False,
                                    "output": "affiliate_links.md still invalid after browser restart retry.",
                                }
                            )

                affiliate_login_required = file_contains(affiliate_output, r"\bLOGIN_REQUIRED\b")
                if affiliate_login_required:
                    notify_results.append(
                        {
                            "agent": "affiliate_linker",
                            "ok": False,
                            "output": "Amazon Associates login required in OpenClaw managed browser profile.",
                        }
                    )

                if not affiliate_ready:
                    mark_skipped(
                        [
                            "scriptwriter",
                            "seo",
                            "reviewer",
                            "edit_strategist",
                            "quality_gate",
                            "asset_hunter",
                            "video_safe_builder",
                            "dzine_producer",
                            "davinci_editor",
                            "publisher",
                            "youtube_uploader",
                        ],
                        "affiliate_links.md not ready/valid",
                    )
                else:
                    script_msg = (
                        "Research and affiliate links are ready for this auto-dispatch task. "
                        f"Read {paths['scriptwriter_prompt']} and execute now. "
                        f"Overwrite {script_output}."
                    )
                    if not run_and_wait("scriptwriter", script_msg, script_output):
                        mark_skipped(
                            [
                                "seo",
                                "reviewer",
                                "edit_strategist",
                                "quality_gate",
                                "asset_hunter",
                                "video_safe_builder",
                                "dzine_producer",
                                "davinci_editor",
                                "publisher",
                                "youtube_uploader",
                            ],
                            "script_long.md not ready",
                        )
                    else:
                        seo_msg = (
                            "Script is ready for this auto-dispatch task. "
                            f"Read {paths['seo_prompt']} and execute now. "
                            f"Overwrite {seo_output}."
                        )
                    if not run_and_wait("seo", seo_msg, seo_output):
                        mark_skipped(
                            [
                                "reviewer",
                                "edit_strategist",
                                "quality_gate",
                                "asset_hunter",
                                "video_safe_builder",
                                "dzine_producer",
                                "davinci_editor",
                                "publisher",
                                "youtube_uploader",
                            ],
                            "seo_package.md not ready",
                        )
                    else:
                        reviewer_msg = (
                            "SEO package is ready for this auto-dispatch task. "
                            f"Read {paths['reviewer_prompt']} and execute now. "
                            f"Overwrite {review_output} with GO/NO-GO."
                        )
                        review_ready = run_and_wait("reviewer", reviewer_msg, review_output)
                        if not review_ready:
                            mark_skipped(
                                [
                                    "edit_strategist",
                                    "quality_gate",
                                    "asset_hunter",
                                    "video_safe_builder",
                                    "dzine_producer",
                                    "davinci_editor",
                                    "publisher",
                                    "youtube_uploader",
                                ],
                                "review_final.md not ready",
                            )
                        elif not reviewer_is_go(review_output):
                            mark_skipped(
                                [
                                    "edit_strategist",
                                    "quality_gate",
                                    "asset_hunter",
                                    "video_safe_builder",
                                    "dzine_producer",
                                    "davinci_editor",
                                    "publisher",
                                    "youtube_uploader",
                                ],
                                "reviewer decision is not GO",
                            )
                        else:
                            edit_msg = (
                                "Review decision is GO for this auto-dispatch task. "
                                f"Read {paths['edit_strategist_prompt']} and execute now. "
                                f"Overwrite {edit_strategy_output}."
                            )
                            if not run_and_wait("edit_strategist", edit_msg, edit_strategy_output):
                                mark_skipped(
                                    [
                                        "quality_gate",
                                        "asset_hunter",
                                        "video_safe_builder",
                                        "dzine_producer",
                                        "davinci_editor",
                                        "publisher",
                                        "youtube_uploader",
                                    ],
                                    "edit_strategy.md not ready",
                                )
                            else:
                                quality_msg = (
                                    "Edit strategy is ready. "
                                    f"Read {paths['quality_gate_prompt']} and execute now. "
                                    f"Overwrite {quality_gate_output} and return PASS/FAIL with score."
                                )
                                quality_ready = run_and_wait("quality_gate", quality_msg, quality_gate_output)
                                if not quality_ready:
                                    mark_skipped(
                                        [
                                            "asset_hunter",
                                            "video_safe_builder",
                                            "dzine_producer",
                                            "davinci_editor",
                                            "publisher",
                                            "youtube_uploader",
                                        ],
                                        "quality_gate.md not ready",
                                    )
                                elif not quality_gate_is_pass(quality_gate_output):
                                    mark_skipped(
                                        [
                                            "asset_hunter",
                                            "video_safe_builder",
                                            "dzine_producer",
                                            "davinci_editor",
                                            "publisher",
                                            "youtube_uploader",
                                        ],
                                        "quality gate is not PASS",
                                    )
                                else:
                                    voice_ready = False
                                    if not args.allow_elevenlabs:
                                        notify_results.append(
                                            {
                                                "agent": "elevenlabs_voiceover",
                                                "ok": False,
                                                "output": "Skipped: allow-elevenlabs=false (waiting Gate approvals).",
                                            }
                                        )
                                    else:
                                        voice_ok, voice_out, voice_report_output = run_elevenlabs_voiceover(
                                            script_path=script_output,
                                            episode_dir=episode_dir,
                                            voice_name=args.voice_name,
                                        )
                                        voice_ready = voice_ok and voiceover_report_ready(voice_report_output)
                                        notify_results.append(
                                            {
                                                "agent": "elevenlabs_voiceover",
                                                "ok": voice_ready,
                                                "output": (voice_out or "")[:500],
                                            }
                                        )
                                    asset_msg = (
                                        "Quality gate is PASS for this auto-dispatch task. "
                                        f"Read {paths['asset_hunter_prompt']} and execute now. "
                                        f"Overwrite {shot_output} and {asset_manifest_output}."
                                    )
                                    if not run_and_wait("asset_hunter", asset_msg, asset_manifest_output):
                                        mark_skipped(
                                            [
                                                "video_safe_builder",
                                                "dzine_producer",
                                                "davinci_editor",
                                                "publisher",
                                                "youtube_uploader",
                                            ],
                                            "asset_manifest.md not ready",
                                        )
                                    else:
                                        ok_vs, out_vs = run_video_safe_transform(episode_dir)
                                        notify_results.append(
                                            {
                                                "agent": "video_safe_builder",
                                                "ok": ok_vs and os.path.exists(video_safe_manifest_output),
                                                "output": (out_vs or "")[:500],
                                            }
                                        )
                                        if not (ok_vs and os.path.exists(video_safe_manifest_output)):
                                            mark_skipped(
                                                ["dzine_producer", "davinci_editor", "publisher", "youtube_uploader"],
                                                "video-safe builder failed",
                                            )
                                        else:
                                            if not voice_ready:
                                                mark_skipped(
                                                    ["dzine_producer", "davinci_editor", "publisher", "youtube_uploader"],
                                                    "elevenlabs voiceover not ready",
                                                )
                                            else:
                                                if not args.allow_dzine:
                                                    notify_results.append(
                                                        {
                                                            "agent": "dzine_producer",
                                                            "ok": False,
                                                            "output": "Skipped: allow-dzine=false (waiting Gate approvals).",
                                                        }
                                                    )
                                                    mark_skipped(
                                                        ["davinci_editor", "publisher", "youtube_uploader"],
                                                        "dzine disabled by policy",
                                                    )
                                                else:
                                                    dz_msg = (
                                                        "Video-safe assets and voiceover are ready. "
                                                        f"Read {paths['dzine_producer_prompt']} and execute now. "
                                                        f"Write outputs and ensure {dzine_generation_report_output} exists."
                                                    )
                                                    dz_ready = run_and_wait("dzine_producer", dz_msg, dzine_generation_report_output)
                                                    dz_required_outputs = [
                                                        dzine_prompt_pack_output,
                                                        dzine_asset_manifest_output,
                                                        dzine_generation_report_output,
                                                        dzine_thumbnail_output,
                                                        dzine_lipsync_map_output,
                                                        dzine_img2img_plan_output,
                                                    ]
                                                    dz_files_ready, dz_missing = wait_for_files(
                                                        dz_required_outputs,
                                                        args.wait_seconds,
                                                        min_mtime=run_start,
                                                    )
                                                    if dz_ready and not dz_files_ready:
                                                        notify_results.append(
                                                            {
                                                                "agent": "dzine_producer",
                                                                "ok": False,
                                                                "output": "Missing required Dzine outputs: "
                                                                + ", ".join([os.path.basename(p) for p in dz_missing]),
                                                            }
                                                        )
                                                    if not dz_ready or not dz_files_ready:
                                                        notify_results.append(
                                                            {
                                                                "agent": "dzine_producer",
                                                                "ok": False,
                                                                "output": (
                                                                    f"Warning: Dzine package not complete after {args.wait_seconds}s; "
                                                                    "skipping DaVinci/publish chain."
                                                                ),
                                                            }
                                                        )
                                                        mark_skipped(
                                                            ["davinci_editor", "publisher", "youtube_uploader"],
                                                            "dzine package incomplete",
                                                        )
                                                    else:
                                                        dv_pf_ok, dv_pf_out = run_davinci_preflight()
                                                        notify_results.append(
                                                            {
                                                                "agent": "davinci_preflight",
                                                                "ok": dv_pf_ok,
                                                                "output": (dv_pf_out or "")[:500],
                                                            }
                                                        )
                                                        if not dv_pf_ok:
                                                            mark_skipped(
                                                                ["publisher", "youtube_uploader"],
                                                                "davinci preflight failed",
                                                            )
                                                        else:
                                                            if not args.allow_upload:
                                                                notify_results.append(
                                                                    {
                                                                        "agent": "publisher",
                                                                        "ok": False,
                                                                        "output": "Skipped: allow-upload=false (waiting Gate approvals).",
                                                                    }
                                                                )
                                                                mark_skipped(
                                                                    ["youtube_uploader"],
                                                                    "upload disabled by policy",
                                                                )
                                                            else:
                                                                dv_msg = (
                                                                    "Video-safe assets and voiceover are ready. "
                                                                    "Use Dzine outputs when available. "
                                                                    f"Read {paths['davinci_editor_prompt']} and execute now. "
                                                                    f"Write outputs and ensure {davinci_edit_plan_output} exists."
                                                                )
                                                                if not run_and_wait("davinci_editor", dv_msg, davinci_edit_plan_output):
                                                                    mark_skipped(
                                                                        ["publisher", "youtube_uploader"],
                                                                        "davinci_edit_plan.md not ready",
                                                                    )
                                                                else:
                                                                    pub_msg = (
                                                                        "DaVinci outputs and affiliate links are ready. "
                                                                        f"Read {paths['publisher_prompt']} and execute now. "
                                                                        f"Write outputs and ensure {publish_package_output} exists."
                                                                    )
                                                                    if not run_and_wait("publisher", pub_msg, publish_package_output):
                                                                        mark_skipped(
                                                                            ["youtube_uploader"],
                                                                            "publish_package.md not ready",
                                                                        )
                                                                    else:
                                                                        up_msg = (
                                                                            "Publish package and affiliate links are ready. "
                                                                            f"Read {paths['youtube_uploader_prompt']} and execute now. "
                                                                            f"Write outputs and ensure {youtube_upload_payload_output} exists. "
                                                                            "Stop before final publish click and require Ray approval."
                                                                        )
                                                                        run_and_wait("youtube_uploader", up_msg, youtube_upload_payload_output)

        if not any(r.get("agent") == "youtube_uploader" for r in notify_results):
            notify_results.append(
                {
                    "agent": "youtube_uploader",
                    "ok": False,
                    "output": "Skipped: upstream step did not complete",
                }
            )
        if not any(r.get("agent") == "dzine_producer" for r in notify_results):
            notify_results.append(
                {
                    "agent": "dzine_producer",
                    "ok": False,
                    "output": "Skipped: upstream step did not complete",
                }
            )
        if not any(r.get("agent") == "elevenlabs_voiceover" for r in notify_results):
            notify_results.append(
                {
                    "agent": "elevenlabs_voiceover",
                    "ok": False,
                    "output": "Skipped: upstream step did not complete",
                }
            )

    result = {
        "dispatched": True,
        "reportPath": report_path,
        "episodeDir": episode_dir,
        "plannedEpisodeDir": planned_episode_dir,
        "resumedExistingEpisode": resumed_existing,
        "maxLongVideosPerDay": args.max_long_videos_per_day,
        "voiceName": args.voice_name,
        "bestScore": round(best_score, 2),
        "threshold": args.threshold,
        "categoryOfDay": category_of_day,
        "categoryReason": category_reason,
        "ideaTitle": idea_title,
        "dispatchToken": dispatch_token,
        "tasksUpdated": tasks_updated,
        "noveltyPrecheck": novelty_precheck,
        "files": paths,
        "notifiedAgents": notify_results,
    }
    append_ops_event(
        "market_dispatch_opened",
        "auto dispatch opened",
        {
            "reportPath": report_path,
            "episodeDir": episode_dir,
            "categoryOfDay": category_of_day,
            "ideaTitle": idea_title,
            "bestScore": round(best_score, 2),
            "notifyAgents": bool(args.notify_agents),
        },
    )
    finish_with_result(result)


if __name__ == "__main__":
    main()
