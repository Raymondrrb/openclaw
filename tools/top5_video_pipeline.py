#!/usr/bin/env python3
"""
Top 5 YouTube video pipeline (theme -> deliverable package).

Stages:
1) Product discovery from Amazon by theme (scrape mode) or deterministic mock mode.
2) Script generation (8 min and 12 min variants).
3) Dzine + NanoBanana Pro prompt pack.
4) Voice generation instructions + character/credit estimate.
5) DaVinci automation manifest and execution checklist.
6) YouTube upload metadata package.

Outputs are written to:
  <PROJECT_ROOT>/content/pipeline_runs/<slug>_<YYYY-MM-DD>/
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.request import Request, urlopen


# ---------------------------------------------------------------------------
# Shared symbols live in video_pipeline_lib.py.  Re-exported here so that
# existing ``from top5_video_pipeline import X`` keeps working.
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))
from video_pipeline_lib import (  # noqa: F401
    BASE_DIR,
    DAILY_CATEGORIES_FILE,
    PRODUCT_SEGMENT_TYPES,
    Product,
    SEGMENT_TYPES,
    STOPWORDS,
    amazon_search_url_with_page,
    append_affiliate_tag,
    atomic_write_json,
    build_structured_script_prompt,
    canonical_amazon_url,
    collect_recent_asins,
    discover_products_scrape,
    download_amazon_reference_images,
    download_binary,
    ensure_placeholder_frame,
    extract_asin_from_url,
    extract_davinci_segments,
    extract_dzine_scenes,
    extract_image_candidates_from_product_html,
    extract_voice_segments,
    fetch_html,
    load_bs4,
    load_daily_categories,
    load_products_json,
    normalize_ws,
    now_date,
    now_iso,
    parse_feature_bullets,
    parse_float,
    parse_int,
    parse_price,
    parse_review_count,
    parse_run_date_from_dirname,
    parse_search_results,
    parse_structured_script,
    product_score,
    resolve_amazon_search_url_for_category,
    slugify,
    theme_match_score,
    theme_tokens,
    supabase_env,
    write_structured_script,
)

DEFAULT_OUTPUT_ROOT = BASE_DIR / "content" / "pipeline_runs"
# SUPABASE_ENV_FILE now lives in video_pipeline_lib.py
SCRIPTWRITER_SOUL_FILE = BASE_DIR / "agents" / "scriptwriter" / "SOUL.md"
TRAJECTORIES_DIR = BASE_DIR / "agents" / "trajectories"


STATUS_DRAFT_WAITING_GATE_1 = "draft_ready_waiting_gate_1"
STATUS_ASSETS_WAITING_GATE_2 = "assets_ready_waiting_gate_2"
STATUS_RENDERING = "rendering"
STATUS_UPLOADING = "uploading"
STATUS_PUBLISHED = "published"
STATUS_FAILED = "failed"

VALID_STATUSES = {
    STATUS_DRAFT_WAITING_GATE_1,
    STATUS_ASSETS_WAITING_GATE_2,
    STATUS_RENDERING,
    STATUS_UPLOADING,
    STATUS_PUBLISHED,
    STATUS_FAILED,
}

PHASE_GATE1 = "gate1"
PHASE_GATE2 = "gate2"
PHASE_APPROVE_GATE1 = "approve_gate1"
PHASE_REJECT_GATE1 = "reject_gate1"
PHASE_APPROVE_GATE2 = "approve_gate2"
PHASE_REJECT_GATE2 = "reject_gate2"
PHASE_FINALIZE = "finalize"

VALID_PHASES = {
    PHASE_GATE1,
    PHASE_GATE2,
    PHASE_APPROVE_GATE1,
    PHASE_REJECT_GATE1,
    PHASE_APPROVE_GATE2,
    PHASE_REJECT_GATE2,
    PHASE_FINALIZE,
}


def state_file_path(out_dir: Path) -> Path:
    return out_dir / "pipeline_state.json"


def load_state(out_dir: Path) -> Dict:
    path = state_file_path(out_dir)
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8")
    return json.loads(raw)


def save_state(out_dir: Path, state: Dict) -> Path:
    state["updated_at"] = now_iso()
    path = state_file_path(out_dir)
    tmp = path.with_suffix(".tmp")
    payload = json.dumps(state, indent=2).encode("utf-8")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(str(tmp), str(path))
    return path


def ensure_state_base(
    out_dir: Path,
    run_slug: str,
    theme: str,
    category: str,
    config: Dict,
) -> Dict:
    state = load_state(out_dir) if state_file_path(out_dir).exists() else {}
    if state:
        return state
    return {
        "run_slug": run_slug,
        "theme": theme,
        "category": category or theme,
        "status": STATUS_DRAFT_WAITING_GATE_1,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "gate1": {
            "approved": False,
            "rejected": False,
            "reviewer": "",
            "notes": "",
            "decision_at": "",
        },
        "gate2": {
            "approved": False,
            "rejected": False,
            "reviewer": "",
            "notes": "",
            "decision_at": "",
        },
        "config": config,
        "artifacts": {},
        "history": [],
    }


def set_status(state: Dict, status: str, reason: str = "") -> None:
    if status not in VALID_STATUSES:
        raise RuntimeError(f"Invalid status transition target: {status}")
    state["status"] = status
    state.setdefault("history", []).append(
        {"ts": now_iso(), "status": status, "reason": reason}
    )


def set_gate_decision(
    state: Dict,
    gate: str,
    approved: bool,
    reviewer: str,
    notes: str,
) -> None:
    if gate not in {"gate1", "gate2"}:
        raise RuntimeError(f"Unknown gate: {gate}")
    node = state.setdefault(gate, {})
    node["approved"] = bool(approved)
    node["rejected"] = not bool(approved)
    node["reviewer"] = reviewer
    node["notes"] = notes or ""
    node["decision_at"] = now_iso()


def require_gate_approved(state: Dict, gate: str) -> None:
    node = state.get(gate) or {}
    if not node.get("approved"):
        raise RuntimeError(
            f"Cannot proceed. {gate} is not approved. Run phase `approve_{gate}` first."
        )


def find_strong_claims(script_text: str) -> List[str]:
    risky_patterns = [
        r"\bguarantee(?:d|s)?\b",
        r"\bperfect\b",
        r"\bbest(?:\s+ever)?\b",
        r"\bno\.?\s*1\b",
        r"\balways\b",
        r"\bnever\b",
        r"\bultimate\b",
    ]
    lines = [normalize_ws(x) for x in script_text.splitlines() if normalize_ws(x)]
    flagged: List[str] = []
    for ln in lines:
        low = ln.lower()
        if any(re.search(p, low) for p in risky_patterns):
            flagged.append(ln[:240])
    # de-duplicate preserving order
    seen = set()
    uniq = []
    for item in flagged:
        if item not in seen:
            seen.add(item)
            uniq.append(item)
    return uniq[:20]


DEFAULT_ANTI_AI_PHRASES = [
    "without further ado",
    "let's dive in",
    "let's dive right in",
    "it's worth noting",
    "it's worth mentioning",
    "in today's video",
    "whether you're a",
    "at the end of the day",
    "takes it to the next level",
    "boasts",
    "features an impressive",
    "offers a seamless",
    "elevate your experience",
    "look no further",
    "game-changer",
    "game changer",
    "in the realm of",
    "when it comes to",
    "a testament to",
    "if you're in the market for",
    "packed with features",
    "sleek design",
    "bang for your buck",
]

ANTI_AI_STRUCTURAL_PATTERNS = [
    ("template_opening", re.compile(r"^\s*this\s+.{0,120}\b(boasts|features|offers|delivers)\b", re.IGNORECASE)),
    ("ranking_transition_cliche", re.compile(r"\bcoming in at number\s*#?\d+\b", re.IGNORECASE)),
    ("next_up_cliche", re.compile(r"\bnext up\b", re.IGNORECASE)),
]


def normalize_phrase_match(text: str) -> str:
    low = (text or "").lower().replace("’", "'")
    low = low.replace("'", "")
    low = low.replace("-", " ")
    low = re.sub(r"[^a-z0-9\s]", " ", low)
    return normalize_ws(low)


def load_anti_ai_phrases() -> List[str]:
    # Keep defaults deterministic even if SOUL.md changes format.
    phrases = list(DEFAULT_ANTI_AI_PHRASES)
    if not SCRIPTWRITER_SOUL_FILE.exists():
        return phrases
    try:
        lines = SCRIPTWRITER_SOUL_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return phrases

    in_block = False
    extracted: List[str] = []
    for raw in lines:
        line = raw.strip()
        if line.lower().startswith("### frases proibidas"):
            in_block = True
            continue
        if in_block and line.startswith("### "):
            break
        if not in_block or not line.startswith("- "):
            continue
        item = line[2:].strip()
        if not item:
            continue
        item = re.sub(r"\s*\(.*?\)\s*$", "", item).strip()
        variants = [item]
        if "/" in item and "http" not in item.lower():
            split_variants = [x.strip().strip("`\"' ") for x in item.split("/") if x.strip()]
            if len(split_variants) >= 2:
                variants = split_variants
        for phrase in variants:
            phrase = phrase.strip().strip("`\"' ")
            if phrase:
                extracted.append(phrase)

    if extracted:
        # Merge + deduplicate preserving order.
        merged = phrases + extracted
        seen = set()
        out = []
        for p in merged:
            key = normalize_phrase_match(p)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(p)
        return out
    return phrases


def find_anti_ai_violations(script_text: str, banned_phrases: List[str]) -> List[Dict[str, str]]:
    phrase_rules = []
    for p in banned_phrases:
        key = normalize_phrase_match(p)
        if key:
            phrase_rules.append((p, key))

    violations: List[Dict[str, str]] = []
    seen = set()
    for i, raw in enumerate(script_text.splitlines(), start=1):
        line = normalize_ws(raw)
        if not line:
            continue
        line_norm = normalize_phrase_match(line)
        line_low = line.lower()

        for phrase, key in phrase_rules:
            if key and key in line_norm:
                dedupe = (i, "phrase", key)
                if dedupe in seen:
                    continue
                seen.add(dedupe)
                violations.append(
                    {
                        "line": str(i),
                        "type": "phrase",
                        "rule": phrase,
                        "excerpt": line[:220],
                    }
                )

        for rule_name, pattern in ANTI_AI_STRUCTURAL_PATTERNS:
            if pattern.search(line_low):
                dedupe = (i, "pattern", rule_name)
                if dedupe in seen:
                    continue
                seen.add(dedupe)
                violations.append(
                    {
                        "line": str(i),
                        "type": "pattern",
                        "rule": rule_name,
                        "excerpt": line[:220],
                    }
                )
    return violations


def evaluate_anti_ai_quality(
    script_a_text: str,
    script_b_text: str,
    max_allowed: int,
) -> Dict:
    banned = load_anti_ai_phrases()
    a_violations = find_anti_ai_violations(script_a_text, banned)
    b_violations = find_anti_ai_violations(script_b_text, banned)
    total = len(a_violations) + len(b_violations)
    unique_rules = sorted(
        set([v["rule"] for v in a_violations + b_violations if v.get("rule")])
    )
    return {
        "pass": total <= max_allowed,
        "max_allowed": max_allowed,
        "banned_phrase_count": len(banned),
        "total_violations": total,
        "unique_rules": unique_rules,
        "script_a": a_violations,
        "script_b": b_violations,
    }


def write_gate1_anti_ai_report(
    out_dir: Path,
    anti_ai: Dict,
    script_a_path: Path,
    script_b_path: Path,
) -> Path:
    status = "PASS" if anti_ai.get("pass") else "FAIL"
    lines: List[str] = []
    lines.append("# Gate 1 Anti-AI Language Report")
    lines.append("")
    lines.append(f"- Status: `{status}`")
    lines.append(f"- Violations: `{anti_ai.get('total_violations', 0)}`")
    lines.append(f"- Max allowed: `{anti_ai.get('max_allowed', 0)}`")
    lines.append(f"- Banned phrase rules loaded: `{anti_ai.get('banned_phrase_count', 0)}`")
    lines.append(f"- Script A: `{script_a_path}`")
    lines.append(f"- Script B: `{script_b_path}`")
    lines.append("")
    if not anti_ai.get("pass"):
        lines.append("## Gate Recommendation")
        lines.append("- BLOCKER: rewrite script before approving Gate 1.")
        lines.append("")

    lines.append("## Script A Violations")
    a_violations = anti_ai.get("script_a") or []
    if not a_violations:
        lines.append("- None.")
    else:
        for item in a_violations[:80]:
            lines.append(
                f"- line {item.get('line')}: [{item.get('type')}] `{item.get('rule')}` -> {item.get('excerpt')}"
            )
    lines.append("")
    lines.append("## Script B Violations")
    b_violations = anti_ai.get("script_b") or []
    if not b_violations:
        lines.append("- None.")
    else:
        for item in b_violations[:120]:
            lines.append(
                f"- line {item.get('line')}: [{item.get('type')}] `{item.get('rule')}` -> {item.get('excerpt')}"
            )
    lines.append("")
    lines.append("## Unique Triggered Rules")
    for r in anti_ai.get("unique_rules") or []:
        lines.append(f"- {r}")
    if not anti_ai.get("unique_rules"):
        lines.append("- None.")

    path = out_dir / "gate1_anti_ai_report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path



# supabase_env() now lives in video_pipeline_lib.py (re-exported above)


def upsert_video_run_state_supabase(state: Dict) -> Dict:
    supabase_url, service_key = supabase_env()
    if not supabase_url or not service_key:
        return {"synced": False, "reason": "missing_supabase_env"}

    row = {
        "run_slug": state.get("run_slug", ""),
        "theme": state.get("theme", ""),
        "category": state.get("category", ""),
        "status": state.get("status", ""),
        "gate1_approved": bool((state.get("gate1") or {}).get("approved")),
        "gate2_approved": bool((state.get("gate2") or {}).get("approved")),
        "gate1_reviewer": (state.get("gate1") or {}).get("reviewer", ""),
        "gate2_reviewer": (state.get("gate2") or {}).get("reviewer", ""),
        "gate1_notes": (state.get("gate1") or {}).get("notes", ""),
        "gate2_notes": (state.get("gate2") or {}).get("notes", ""),
        "artifacts": state.get("artifacts") or {},
        "meta": {
            "config": state.get("config") or {},
            "history": state.get("history") or [],
            "updated_at": state.get("updated_at", now_iso()),
        },
        "updated_at": now_iso(),
    }

    base = supabase_url.rstrip("/")
    url = f"{base}/rest/v1/ops_video_runs?on_conflict=run_slug"
    req = Request(
        url,
        method="POST",
        data=json.dumps([row]).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
    )
    try:
        with urlopen(req, timeout=20) as resp:
            _ = resp.read()
        return {"synced": True}
    except Exception as exc:  # noqa: BLE001
        return {"synced": False, "reason": str(exc)}


def run_with_retries(
    cmd: List[str],
    *,
    attempts: int,
    backoff_sec: int,
    label: str,
    log_path: Path,
) -> subprocess.CompletedProcess:
    if attempts < 1:
        attempts = 1
    last: Optional[subprocess.CompletedProcess] = None
    events: List[Dict] = []
    for i in range(1, attempts + 1):
        start = time.time()
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        elapsed_ms = int((time.time() - start) * 1000)
        events.append(
            {
                "ts": now_iso(),
                "label": label,
                "attempt": i,
                "returncode": proc.returncode,
                "elapsed_ms": elapsed_ms,
                "stderr_preview": normalize_ws((proc.stderr or "")[:400]),
            }
        )
        if proc.returncode == 0:
            atomic_write_json(log_path, events)
            return proc
        last = proc
        if i < attempts:
            time.sleep(max(1, backoff_sec) * i)
    atomic_write_json(log_path, events)
    assert last is not None
    return last


def maybe_apply_threshold_profile(args: argparse.Namespace) -> Dict:
    info = {"applied": False, "source": "", "profile": ""}
    thresholds_file = (args.thresholds_file or "").strip()
    if not thresholds_file:
        return info
    path = Path(thresholds_file).expanduser()
    if not path.exists():
        raise RuntimeError(f"Thresholds file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("Thresholds file must be a JSON object.")
    key_candidates = []
    if args.category:
        key_candidates.append(args.category.lower().strip())
        key_candidates.append(slugify(args.category, 120))
    if args.theme:
        key_candidates.append(args.theme.lower().strip())
        key_candidates.append(slugify(args.theme, 120))
    key_candidates.append("default")

    profile = None
    selected = ""
    for k in key_candidates:
        if k in data and isinstance(data[k], dict):
            profile = data[k]
            selected = k
            break
    if not profile:
        return info
    if "min_rating" in profile:
        args.min_rating = float(profile["min_rating"])
    if "min_reviews" in profile:
        args.min_reviews = int(profile["min_reviews"])
    if "min_price" in profile:
        args.min_price = float(profile["min_price"])
    if "max_price" in profile:
        args.max_price = float(profile["max_price"])
    info.update({"applied": True, "source": str(path), "profile": selected})
    return info


def mock_products(theme: str, affiliate_tag: str, top_n: int, excluded_asins: set[str]) -> List[Product]:
    seed = [
        ("Smart LED Desk Lamp with Wireless Charger", "B0D8LAMP01", 49.99, 4.6, 12430),
        ("Programmable Mini Macro Keypad", "B0D8KEYP02", 39.99, 4.5, 6830),
        ("USB-C Docking Station Triple Display", "B0D8DOCK03", 129.99, 4.4, 2190),
        ("Ergonomic Vertical Mouse Pro", "B0D8MOUSE4", 59.99, 4.4, 9320),
        ("Noise-Cancelling Desktop Fan", "B0D8FAN005", 89.99, 4.3, 5010),
        ("AI Notebook Smart Pen Set", "B0D8PEN006", 79.99, 4.3, 2010),
        ("Magnetic Cable Organizer Kit", "B0D8CABLE7", 24.99, 4.4, 8842),
        ("Under-Desk Drawer Organizer", "B0D8DRAWR8", 32.99, 4.5, 3710),
        ("Portable 15.6-inch USB-C Monitor", "B0D8MONIT9", 169.99, 4.4, 1920),
        ("Smart Timer Cube for Focus Sessions", "B0D8TIMER0", 29.99, 4.6, 5422),
    ]
    products: List[Product] = []
    for title, asin, price, rating, reviews in seed:
        if asin in excluded_asins:
            continue
        url = f"https://www.amazon.com/dp/{asin}"
        products.append(
            Product(
                product_title=f"{title} ({theme.title()})",
                asin=asin,
                current_price_usd=price,
                rating=rating,
                review_count=reviews,
                feature_bullets=[
                    "Easy setup and stable daily use",
                    "Solid build quality for long-term value",
                    "Helps reduce desk clutter and improve workflow",
                    "Balanced performance for price",
                ],
                amazon_url=url,
                affiliate_url=append_affiliate_tag(url, affiliate_tag),
                available=True,
                ranking_score=product_score(rating, reviews, price),
            )
        )
        if len(products) >= top_n:
            break
    if len(products) < top_n:
        raise RuntimeError(
            f"Mock mode could only produce {len(products)} products after exclusion filter."
        )
    return products


def ensure_feature_benefits(product: Product) -> List[str]:
    title = product.product_title.lower()
    mapped: List[str] = []
    keyword_map = [
        (
            ["clock", "alarm"],
            [
                "Large readout improves glanceability, which is useful in both office and bedroom setups.",
                "Adjustable brightness helps at night so the display is visible but not distracting.",
                "Extra features like date, temperature, or USB charging add practical day-to-day utility.",
            ],
        ),
        (
            ["power strip", "usb c", "surge", "charging"],
            [
                "It centralizes charging so your desk cable flow becomes cleaner and easier to manage.",
                "Fast-charge USB-C support handles modern devices without extra adapters.",
                "Surge protection adds practical safety for daily connected gear.",
            ],
        ),
        (
            ["cable", "cord", "organizer", "tray", "holder"],
            [
                "It removes visual cable clutter quickly, which makes the whole setup look cleaner.",
                "Installation is usually fast and tool-light, so setup friction is low.",
                "The tray or holder capacity is enough for real desk use, not just one cable.",
            ],
        ),
        (
            ["headphone stand", "headset stand", "headphone", "headset"],
            [
                "It keeps your headset accessible and your desk surface less cluttered.",
                "A weighted base improves stability, especially during frequent grab-and-place use.",
                "Integrated hub or bungee features can reduce accessory sprawl around the main setup.",
            ],
        ),
        (
            ["foot rest", "footrest", "lumbar", "pillow", "back support"],
            [
                "It improves comfort during long seated sessions, which directly helps focus and consistency.",
                "Memory-foam style support adapts to body pressure better than rigid accessories.",
                "Washable covers and adjustable positioning make long-term maintenance easier.",
            ],
        ),
        (
            ["dock", "docking", "monitor", "hub"],
            [
                "It expands port options so you can run a cleaner single-cable workflow.",
                "Useful for multi-screen or multi-peripheral desks where switching devices is common.",
                "Helps standardize your workstation so setup is consistent each day.",
            ],
        ),
        (
            ["lamp", "light", "led"],
            [
                "Multiple brightness and color temperature levels make it easy to tune comfort for long work sessions.",
                "Eye-friendly diffusion helps reduce strain when you are switching between monitor and notes.",
                "The arm design saves desk space while still letting you aim light exactly where you need it.",
            ],
        ),
    ]
    for keys, benefits in keyword_map:
        if any(k in title for k in keys):
            mapped = benefits
            break
    if mapped:
        return mapped[:3]

    bullets = [normalize_ws(x) for x in product.feature_bullets if normalize_ws(x)]
    cleaned: List[str] = []
    for raw in bullets:
        t = raw.encode("ascii", "ignore").decode("ascii")
        t = re.sub(r"\[[^\]]+\]\s*-?\s*", "", t).strip()
        if "we used chatgpt" in t.lower():
            continue
        t = normalize_ws(t)
        if not t:
            continue
        sentences = [normalize_ws(x) for x in re.split(r"[.;]", t) if normalize_ws(x)]
        if not sentences:
            continue
        candidate = sentences[0]
        letters = [c for c in candidate if c.isalpha()]
        if letters:
            upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
            if upper_ratio > 0.33:
                continue
        words = candidate.split()
        if len(words) > 20:
            candidate = " ".join(words[:20]).rstrip(",.;:") + "."
        if candidate and candidate[-1] not in ".!?":
            candidate += "."
        cleaned.append(candidate[:1].upper() + candidate[1:])
        if len(cleaned) >= 3:
            break

    fallback = [
        "It delivers dependable day-to-day value instead of chasing flashy one-off features.",
        "Setup is straightforward enough for non-technical buyers.",
        "User sentiment indicates strong practical performance for the price.",
    ]
    return (cleaned + fallback)[:3]


def downside_for(product: Product, median_price: float) -> str:
    title = product.product_title.lower()
    if any(k in title for k in ["clock", "alarm"]):
        return "It is practical, but it does not add much if you already rely on a smartwatch or phone widgets."
    if any(k in title for k in ["cable", "tray", "organizer"]):
        return "Adhesive or fit can vary by desk surface, so check your material and edge clearance first."
    if any(k in title for k in ["headphone", "headset"]):
        return "Great for organization, but the value drops if you do not use the extra hub or bungee features."
    if any(k in title for k in ["lamp", "light"]):
        return "Build quality is good for the price, but premium all-metal models still feel sturdier."
    if any(k in title for k in ["power strip", "usb c", "surge"]):
        return "The clamp design is very useful, but desk thickness and wall clearance can limit placement."
    if product.current_price_usd > median_price * 1.35:
        return "It can feel expensive unless you use its premium features every day."
    if product.review_count < 1500:
        return "Review volume is lower than mainstream picks, so long-term confidence is slightly lower."
    if product.rating < 4.5:
        return "It is very good overall, but user satisfaction is slightly below the top-tier options."
    return "It does many things well, but it is not always the strongest choice for very niche power users."


def best_for(theme: str, product: Product) -> str:
    low = product.product_title.lower()
    if "power strip" in low or "usb c" in low or "surge" in low:
        return "multi-device users who want cleaner charging and safer desk power management"
    if "cable" in low or "organizer" in low or "tray" in low:
        return "people who want a cleaner desk quickly without a full setup rebuild"
    if "clock" in low or "alarm" in low:
        return "users who want fast glanceable info on desk without opening apps"
    if "dock" in low:
        return "remote workers who run multiple screens and want a cleaner desk setup"
    if "lamp" in low:
        return "people who work long hours and want eye-friendly lighting with utility"
    if "mouse" in low or "ergonomic" in low:
        return "users who prioritize comfort and reduced wrist strain over flashy specs"
    if "headphone" in low or "headset" in low:
        return "desk setups where accessories need dedicated organization and quick access"
    return f"buyers in the {theme} niche who want a practical, high-value option"


def short_title(product_title: str, max_words: int = 8) -> str:
    t = re.sub(r"\(.*?\)", "", product_title or "").strip()
    t = t.split(" - ")[0].split(" | ")[0]
    words = t.split()
    if len(words) <= max_words:
        return t
    return " ".join(words[:max_words]).rstrip(",.;:") + "..."


def product_section(rank_label: str, product: Product, theme: str, median_price: float, long: bool) -> str:
    benefits = ensure_feature_benefits(product)
    downside = downside_for(product, median_price)
    best = best_for(theme, product)
    price_bucket = "budget" if product.current_price_usd <= median_price else "mid-to-premium"
    competitor_hint = "review trend consistency and setup friction"

    base = []
    base.append(f"### {rank_label}: {short_title(product.product_title, max_words=10)}")
    base.append(
        f"At about ${product.current_price_usd:.2f}, this is a {price_bucket} pick with a {product.rating:.1f}-star average "
        f"across roughly {product.review_count:,} Amazon reviews."
    )
    base.append("What it does well in real use:")
    base.append(f"1. {benefits[0]}")
    base.append(f"2. {benefits[1]}")
    base.append(f"3. {benefits[2]}")
    base.append(f"One honest downside to keep in mind: {downside}")
    base.append(f"Best for: {best}.")
    base.append(
        f"If you are comparing this against other {theme} options, focus on {competitor_hint}, not just headline specs."
    )

    if long:
        base.append(
            "In practical terms, this is worth it when the workflow repeats daily. "
            "If the product solves a recurring annoyance, the value compounds fast."
        )
        base.append(
            "For long-term value, check how often you would actually use the core feature per week. "
            "That one metric usually predicts whether buyers keep or return this type of product."
        )

    return "\n".join(base)


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def pad_script(text: str, min_words: int, theme: str, ranked: List[Product]) -> str:
    if word_count(text) >= min_words:
        return text
    titles = [short_title(p.product_title, max_words=6) for p in ranked[:3]]
    extra_blocks = [
        (
            f"Real-world check: in the {theme} category, I care less about flashy specs and more about consistency after week three. "
            f"That is why picks like {titles[0]} and {titles[1]} score better for long-term use."
        ),
        (
            f"Another practical filter is maintenance friction. If a product saves time only on day one but adds friction later, "
            f"it should rank lower than options like {titles[2]} that stay predictable."
        ),
        (
            "Before buying, compare three things side by side: review trend quality, return convenience, and the cost per week of usage. "
            "That gives you a better buying decision than headline specs alone."
        ),
        (
            "Another overlooked factor is desk compatibility. A strong product can still be the wrong pick if your space, cable routing, "
            "or device mix does not match the intended setup."
        ),
        (
            "If two options are close, I usually favor the one with clearer warranty handling and cleaner user support feedback."
        ),
        (
            "For budget control, divide the product price by expected months of use. "
            "That simple math instantly filters out impulse buys."
        ),
        (
            f"In this list, {titles[0]} and {titles[2]} represent two different strategies: one prioritizes immediate utility, "
            "the other optimizes setup efficiency over time."
        ),
        (
            "The safest buying pattern is this: pick the feature you will use most often, then choose the model that performs that one thing reliably."
        ),
        (
            "Most buyer regret in this category comes from overbuying complexity. "
            "If you will not use advanced features weekly, skip them."
        ),
    ]
    idx = 0
    out = text
    while word_count(out) < min_words:
        block = extra_blocks[idx % len(extra_blocks)]
        out += "\n\n" + block
        idx += 1
    return out


def trim_script_to_max_words(text: str, max_words: int) -> str:
    if word_count(text) <= max_words:
        return text
    parts = re.findall(r"\b\w+\b|\W+", text)
    out_parts: List[str] = []
    seen_words = 0
    for token in parts:
        if re.fullmatch(r"\b\w+\b", token):
            if seen_words >= max_words:
                break
            seen_words += 1
        out_parts.append(token)
    return "".join(out_parts).strip()


def enforce_word_bounds(
    text: str,
    min_words: int,
    max_words: int,
    theme: str,
    ranked: List[Product],
) -> str:
    out = text
    wc = word_count(out)
    if wc < min_words:
        out = pad_script(out, min_words=min_words, theme=theme, ranked=ranked)
    out = trim_script_to_max_words(out, max_words=max_words)
    return out


def build_script(products: List[Product], theme: str, channel_name: str, long_version: bool) -> str:
    # Top 5 format: #5 to #1
    ranked = sorted(products, key=lambda p: p.ranking_score, reverse=True)
    show_order = list(reversed(ranked))
    median_price = sorted([p.current_price_usd for p in ranked])[len(ranked) // 2]

    top_1 = short_title(ranked[0].product_title)
    top_5 = short_title(show_order[0].product_title)
    target_label = "12-minute" if long_version else "8-minute"

    intro = (
        f"# {channel_name} - Top 5 {theme.title()} (Natural English Script, {target_label})\n\n"
        f"If you have ever bought a {theme} product that looked great on paper but disappointed in real life, this episode is for you. "
        f"I narrowed the market down to five options that hold up in real use, not just in ad copy. "
        f"Stay to the end, because the number one pick is the strongest balance of reliability, value, and user satisfaction. "
        f"And we start with an underrated entry at number five: {top_5}.\n\n"
        "Before we jump in, quick context: this list focuses on products currently sold on Amazon, with strong ratings, meaningful review volume, "
        f"and real-world usability. Let us start with number five and build up to number one: {top_1}."
    )

    sections = [intro]
    rank_num = 5
    for p in show_order:
        sections.append(product_section(f"#{rank_num}", p, theme, median_price, long=long_version))
        rank_num -= 1

    close = (
        "## Final recap and CTA\n"
        "So here is the recap: if you want balanced value, choose the pick that fits your daily routine, not the one with the loudest marketing. "
        "If you are price-sensitive, the middle ranks usually deliver the best cost-to-benefit ratio. "
        "If you want premium feel and long-term confidence, number one is still the safest buy in this list.\n\n"
        "If this saved you research time, subscribe to Rayviews for daily practical top lists. "
        "Affiliate links are in the description, and they help support the channel at no extra cost to you.\n\n"
        "Disclosure: prices and ratings can change over time. This ranking reflects the snapshot captured at time of recording."
    )
    sections.append(close)

    script = "\n\n".join(sections)
    if long_version:
        script = pad_script(script, min_words=1650, theme=theme, ranked=ranked)
        script = trim_script_to_max_words(script, max_words=1900)
    else:
        script = pad_script(script, min_words=1100, theme=theme, ranked=ranked)
        script = trim_script_to_max_words(script, max_words=1250)
    return script


def estimate_elevenlabs_chars(script_text: str) -> int:
    # ElevenLabs credit consumption is character-based for TTS.
    return len(script_text)


def generate_dzine_prompts(
    products: List[Product],
    theme: str,
    channel_name: str,
    reference_manifest: Dict[str, Dict],
) -> Dict:
    ranked = sorted(products, key=lambda p: p.ranking_score, reverse=True)
    prompts: List[Dict] = []
    for idx, p in enumerate(ranked, start=1):
        base_identity = (
            "Character: Ray, same face identity as channel avatar, confident reviewer style, "
            "outfit can change but visual identity must stay consistent. "
            "RayViews brand look: clean high-contrast lighting, soft neutral backgrounds, realistic skin tones, no cartoon style."
        )
        refs = reference_manifest.get(p.asin, {})
        hero_ref = refs.get("hero_ref_path", "")
        life_ref = refs.get("life_ref_path", "")
        prompts.append(
            {
                "rank": idx,
                "product_title": p.product_title,
                "asin": p.asin,
                "reference_anchor": {
                    "hero_ref_path": hero_ref,
                    "life_ref_path": life_ref,
                },
                "variant_1": (
                    f"Model: NanoBanana Pro. {base_identity} Use reference image {hero_ref} as product style anchor. "
                    f"Hero clean shot: Ray presenting {p.product_title} in a clean modern set, medium shot, realistic lighting, "
                    "no text in image, no price in image, leave simple negative space for later DaVinci overlays."
                ),
                "variant_2": (
                    f"Model: NanoBanana Pro. Use reference image {life_ref or hero_ref} as style anchor. "
                    f"In-use scene: Ray using {p.product_title} naturally in a lifestyle setup that matches {theme}, "
                    "high detail, coherent color palette, no text in image."
                ),
                "variant_3": (
                    f"Model: NanoBanana Pro. Benefit shot for {p.product_title}: emphasize one practical benefit visually, "
                    f"Ray in scene, consistent RayViews background style, product clearly visible, no embedded text or pricing."
                ),
                "variant_4_optional": (
                    f"Model: NanoBanana Pro. Optional creative comparison composition for {p.product_title} with Ray as presenter, "
                    "no logos, no text, no pricing in image."
                ),
            }
        )

    hero = ranked[0]
    thumbnail_prompt = (
        "Model: NanoBanana Pro. YouTube thumbnail, 16:9, Ray as primary presenter on left, "
        f"hero product '{hero.product_title}' on right, bold title area: 'TOP 5 {theme.upper()} {dt.date.today().year}', "
        "strong contrast, high clarity, emotional expression, "
        "leave safe margins for text readability."
    )

    guidance = {
        "recommended_images_per_product": 3,
        "why": (
            "For an 8-12 minute video with 5 products, three visuals per product gives enough shot variety "
            "to avoid repetition while keeping generation cost controlled. Typical pacing is 7-10 seconds per visual, "
            "so 15 images cover roughly 2.5-4 minutes; combined with Ray inserts, captions, and b-roll loops this fills the episode naturally."
        ),
    }

    return {"products": prompts, "thumbnail_prompt": thumbnail_prompt, "guidance": guidance}


def build_upload_package(
    theme: str,
    products: List[Product],
    affiliate_tag: str,
    channel_name: str,
) -> Dict:
    ranked = sorted(products, key=lambda p: p.ranking_score, reverse=True)
    title = f"Top 5 {theme.title()} on Amazon (Best Picks {dt.date.today().year})"
    lines = [
        f"Today on {channel_name}, we break down the Top 5 {theme} picks currently selling on Amazon.",
        "",
        "Affiliate links:",
    ]
    for idx, p in enumerate(ranked, start=1):
        lines.append(f"{idx}. {p.product_title} - {p.affiliate_url}")
    lines.extend(
        [
            "",
            "Disclosure: As an Amazon Associate, I may earn from qualifying purchases.",
            "Prices and ratings can change over time.",
        ]
    )
    description = "\n".join(lines)
    tags = [
        "top 5 products",
        "amazon finds",
        "product review",
        theme.lower(),
        "rayviews",
        f"best products {dt.date.today().year}",
        "buying guide",
    ]
    return {"title": title, "description": description, "tags": tags, "affiliate_tag": affiliate_tag}


def write_products_json_csv(products: List[Product], out_dir: Path) -> Tuple[Path, Path]:
    json_path = out_dir / "product_selection.json"
    csv_path = out_dir / "product_selection.csv"
    records = [asdict(p) for p in products]
    atomic_write_json(json_path, records)

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "product_title",
                "asin",
                "current_price_usd",
                "rating",
                "review_count",
                "feature_bullets",
                "amazon_url",
                "affiliate_url",
                "available",
                "ranking_score",
            ],
        )
        writer.writeheader()
        for p in products:
            row = asdict(p)
            row["feature_bullets"] = " | ".join(p.feature_bullets)
            writer.writerow(row)
    return json_path, csv_path


def write_scripts(script_a: str, script_b: str, out_dir: Path) -> Tuple[Path, Path]:
    a_path = out_dir / "script_A_8min.md"
    b_path = out_dir / "script_B_12min.md"
    a_path.write_text(script_a, encoding="utf-8")
    b_path.write_text(script_b, encoding="utf-8")
    return a_path, b_path


def extract_hook(script_text: str, max_chars: int = 420) -> str:
    lines = [normalize_ws(x) for x in script_text.splitlines() if normalize_ws(x)]
    for ln in lines:
        low = ln.lower()
        if low.startswith("#") or low.startswith("##"):
            continue
        if len(ln) >= 30:
            return ln[:max_chars]
    return (script_text or "")[:max_chars]


def write_gate1_review(
    out_dir: Path,
    category: str,
    products: List[Product],
    script_a_text: str,
    script_b_text: str,
    script_a_path: Path,
    script_b_path: Path,
    anti_ai: Dict,
    anti_ai_report_path: Path,
) -> Path:
    claims = find_strong_claims(script_a_text + "\n" + script_b_text)
    hook = extract_hook(script_a_text)
    missing_affiliate_tag = all(("tag=" not in (p.affiliate_url or "")) for p in products)
    anti_ai_status = "PASS" if anti_ai.get("pass") else "FAIL"
    lines: List[str] = []
    lines.append("# Gate 1 Review Package")
    lines.append("")
    lines.append(f"- Category: `{category}`")
    lines.append(f"- Script A (8 min target): `{script_a_path}` ({word_count(script_a_text)} words)")
    lines.append(f"- Script B (12 min target): `{script_b_path}` ({word_count(script_b_text)} words)")
    if missing_affiliate_tag:
        lines.append("- WARNING: Affiliate tag not configured; links below are non-affiliate Amazon URLs.")
    lines.append("")
    lines.append("## Top 5 Candidate Products")
    lines.append("| Rank | ASIN | Title | Price (USD) | Rating | Reviews | Affiliate Link |")
    lines.append("|---|---|---|---:|---:|---:|---|")
    ranked = sorted(products, key=lambda p: p.ranking_score, reverse=True)
    for idx, p in enumerate(ranked, start=1):
        lines.append(
            f"| {idx} | `{p.asin}` | {p.product_title[:86]} | {p.current_price_usd:.2f} | "
            f"{p.rating:.1f} | {p.review_count:,} | {p.affiliate_url} |"
        )
    lines.append("")
    lines.append("## Hook Preview")
    lines.append(hook)
    lines.append("")
    lines.append("## Strong Claims Flagged")
    if claims:
        for c in claims:
            lines.append(f"- {c}")
    else:
        lines.append("- None flagged.")
    lines.append("")
    lines.append("## Anti-AI Language Check")
    lines.append(f"- Status: `{anti_ai_status}`")
    lines.append(f"- Violations: `{anti_ai.get('total_violations', 0)}`")
    lines.append(f"- Max allowed: `{anti_ai.get('max_allowed', 0)}`")
    lines.append(f"- Report: `{anti_ai_report_path}`")
    if anti_ai_status == "FAIL":
        lines.append("- BLOCKER: rewrite script before Gate 1 approval.")
    lines.append("")
    lines.append("## Human Decision")
    lines.append("- Approve: run phase `approve_gate1`.")
    lines.append("- Reject: run phase `reject_gate1` and regenerate gate1.")
    path = out_dir / "gate1_review.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_voice_blocks_plan(
    script_a_text: str,
    voice_name: str,
    out_dir: Path,
) -> Path:
    block_specs = [
        ("intro", "Hook and context"),
        ("product_5", "Rank #5 section"),
        ("product_4", "Rank #4 section"),
        ("product_3", "Rank #3 section"),
        ("product_2", "Rank #2 section"),
        ("product_1", "Rank #1 section"),
        ("outro", "Recap + CTA + disclosures"),
    ]
    # Keep deterministic split for quality retakes: by approximate paragraph chunks.
    paragraphs = [x.strip() for x in script_a_text.split("\n\n") if x.strip()]
    chunks: List[str] = []
    if len(paragraphs) < 7:
        # fallback split by sentence windows
        sentences = re.split(r"(?<=[.!?])\s+", normalize_ws(script_a_text))
        step = max(1, len(sentences) // 7)
        for i in range(0, len(sentences), step):
            chunks.append(" ".join(sentences[i : i + step]).strip())
        chunks = chunks[:7]
    else:
        # skip heading block and map first 7 meaningful blocks
        body = [p for p in paragraphs if not p.lower().startswith("# ")]
        chunks = body[:7]
    while len(chunks) < 7:
        chunks.append("")

    out_dir_blocks = out_dir / "voice_blocks"
    out_dir_blocks.mkdir(parents=True, exist_ok=True)
    plan_lines = ["# Voice Blocks Plan (Quality Retakes)"]
    plan_lines.append("")
    plan_lines.append(f"- Voice: `{voice_name}`")
    plan_lines.append("- Blocks: intro + 5 products + outro")
    plan_lines.append("")
    for idx, (block_id, desc) in enumerate(block_specs, start=1):
        text = chunks[idx - 1].strip()
        txt_file = out_dir_blocks / f"{idx:02d}_{block_id}.txt"
        txt_file.write_text(text, encoding="utf-8")
        plan_lines.append(f"## {idx:02d}. {block_id}")
        plan_lines.append(f"- Description: {desc}")
        plan_lines.append(f"- File: `{txt_file}`")
        plan_lines.append(f"- Characters: `{len(text)}`")
        plan_lines.append("")
    plan_lines.append("Tip: regenerate only failed blocks to keep cost and quality under control.")
    path = out_dir / "voice_blocks_plan.md"
    path.write_text("\n".join(plan_lines), encoding="utf-8")
    return path


def build_gate2_assets(products: List[Product], category: str) -> Dict:
    ranked = sorted(products, key=lambda p: p.ranking_score, reverse=True)
    assets = []
    for idx, p in enumerate(ranked, start=1):
        assets.append(
            {
                "rank": idx,
                "asin": p.asin,
                "product_title": p.product_title,
                "hero_visual_1": {
                    "filename": f"p{idx}_hero_1.png",
                    "prompt": (
                        f"Model: NanoBanana Pro. Ray presenter with consistent face identity, wearing outfit matching {category} theme, "
                        f"holding/using {p.product_title}. Keep realistic scene with clean negative space for later text overlays in DaVinci. "
                        "Do not render price text inside image."
                    ),
                },
                "hero_visual_2": {
                    "filename": f"p{idx}_hero_2.png",
                    "prompt": (
                        f"Model: NanoBanana Pro. Ray in a relevant lifestyle scene with {p.product_title} in active use. "
                        "Show product clearly and leave clean area for later on-screen overlays. No price text in image."
                    ),
                },
                "spec_price_card": {
                    "filename": f"p{idx}_spec_card.png",
                    "prompt": (
                        f"Model: NanoBanana Pro. Clean product-focused composition for {p.product_title} with a clear specs/price card area, "
                        "minimal clutter, high readability for YouTube. Keep all overlay areas blank; no text inside image."
                    ),
                },
            }
        )
    thumbnails = [
        {
            "filename": "thumbnail_variant_a.png",
            "prompt": (
                f"Model: NanoBanana Pro. YouTube thumbnail 16:9, Ray on left, top ranked product on right, bold title area "
                f"'Top 5 {category.title()} {dt.date.today().year}', high contrast and clean readability."
            ),
        },
        {
            "filename": "thumbnail_variant_b.png",
            "prompt": (
                f"Model: NanoBanana Pro. YouTube thumbnail 16:9, energetic Ray expression, collage of 2 top products, "
                f"strong text zone for 'Best {category.title()} Picks', punchy but clean style."
            ),
        },
    ]
    return {"products": assets, "thumbnails": thumbnails}


def filter_gate2_assets_pack(pack: Dict, rejected_filenames: set[str]) -> Dict:
    if not rejected_filenames:
        return pack
    filtered_products = []
    for item in pack.get("products", []):
        sub = {
            "rank": item.get("rank"),
            "asin": item.get("asin"),
            "product_title": item.get("product_title"),
        }
        kept = 0
        for key in ("hero_visual_1", "hero_visual_2", "spec_price_card"):
            node = item.get(key) or {}
            fn = str(node.get("filename", ""))
            if fn and fn in rejected_filenames:
                sub[key] = node
                kept += 1
        if kept:
            filtered_products.append(sub)
    filtered_thumbs = []
    for t in pack.get("thumbnails", []):
        fn = str((t or {}).get("filename", ""))
        if fn and fn in rejected_filenames:
            filtered_thumbs.append(t)
    return {
        "products": filtered_products,
        "thumbnails": filtered_thumbs,
        "mode": "rejected_only",
        "rejected_filenames": sorted(rejected_filenames),
    }


def write_gate2_package(
    out_dir: Path,
    products: List[Product],
    category: str,
    rejected_filenames: set[str],
) -> Tuple[Path, Path, Path]:
    pack = build_gate2_assets(products, category)
    if rejected_filenames:
        pack = filter_gate2_assets_pack(pack, rejected_filenames)
        assets_json = out_dir / "gate2_assets_regen.json"
    else:
        assets_json = out_dir / "gate2_assets_pack.json"
    atomic_write_json(assets_json, pack)

    storyboard = []
    storyboard.append("# Gate 2 Compact Storyboard")
    storyboard.append("")
    if rejected_filenames:
        storyboard.append("- Mode: regenerate only rejected assets (by filename).")
        storyboard.append(f"- Requested filenames: {', '.join(sorted(rejected_filenames))}")
    else:
        storyboard.append("- Policy: 3 images per product (2 hero + 1 spec/price card) + 2 thumbnail variants.")
        storyboard.append("- This compact view shows 1 chosen image per product + 1 thumbnail choice.")
    storyboard.append("")
    for item in pack["products"]:
        hero = (item.get("hero_visual_1") or {}).get("filename") or (item.get("hero_visual_2") or {}).get("filename") or (item.get("spec_price_card") or {}).get("filename") or "n/a"
        storyboard.append(
            f"- Rank #{item['rank']} (`{item['asin']}`): primary frame `{hero}`."
        )
    storyboard.append("")
    if rejected_filenames:
        storyboard.append("- Thumbnail: only listed rejected variants are regenerated.")
    else:
        storyboard.append("- Thumbnail choice candidate: `thumbnail_variant_a.png`")
        storyboard.append("- If rejected, regenerate only rejected asset filenames.")
    gate2_storyboard = out_dir / "gate2_storyboard.md"
    gate2_storyboard.write_text("\n".join(storyboard), encoding="utf-8")

    gate2_review = []
    gate2_review.append("# Gate 2 Review Package")
    gate2_review.append("")
    gate2_review.append(f"- Asset pack JSON: `{assets_json}`")
    gate2_review.append(f"- Compact storyboard: `{gate2_storyboard}`")
    gate2_review.append("")
    gate2_review.append("## Human Decision")
    gate2_review.append("- Approve: run phase `approve_gate2`.")
    gate2_review.append("- Reject: run phase `reject_gate2` and regenerate only rejected assets.")
    gate2_review_path = out_dir / "gate2_review.md"
    gate2_review_path.write_text("\n".join(gate2_review), encoding="utf-8")
    return assets_json, gate2_storyboard, gate2_review_path


def write_price_overlay_plan(products: List[Product], out_dir: Path) -> Tuple[Path, Path]:
    ranked = sorted(products, key=lambda p: p.ranking_score, reverse=True)
    overlays = []
    for idx, p in enumerate(ranked, start=1):
        overlays.append(
            {
                "rank": idx,
                "asin": p.asin,
                "product_title": p.product_title,
                "price_text": f"${p.current_price_usd:.2f}",
                "overlay_text": f"${p.current_price_usd:.2f} · Amazon US · At time of recording",
            }
        )
    json_path = out_dir / "price_overlays.json"
    md_path = out_dir / "price_overlays.md"
    atomic_write_json(json_path, {"products": overlays})
    lines = ["# Price Overlay Plan", "", "Use these values as DaVinci text template inputs:"]
    for item in overlays:
        lines.append(
            f"- #{item['rank']} `{item['asin']}`: `{item['overlay_text']}`"
        )
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def build_dzine_expected_paths(products: List[Product], out_dir: Path, run_date: str) -> Dict:
    root = out_dir / "assets" / "dzine" / run_date
    items = []
    for p in products:
        asin = p.asin.upper().strip()
        pdir = root / asin
        items.append(
            {
                "asin": asin,
                "variants": [str(pdir / "v1.png"), str(pdir / "v2.png"), str(pdir / "v3.png")],
                "screenshots": [
                    str(pdir / "verify_v1.png"),
                    str(pdir / "verify_v2.png"),
                    str(pdir / "verify_v3.png"),
                ],
            }
        )
    return {
        "run_date": run_date,
        "root": str(root),
        "products": items,
        "thumbnails": [
            str(root / "thumbnails" / "thumb_a.png"),
            str(root / "thumbnails" / "thumb_b.png"),
        ],
        "lipsync": [
            str(root / "lipsync" / "hook.mp4"),
            str(root / "lipsync" / "transition.mp4"),
            str(root / "lipsync" / "outro.mp4"),
        ],
    }


def write_dzine_ui_automation_task(
    products: List[Product],
    out_dir: Path,
    run_date: str,
    reference_manifest: Dict[str, Dict],
    min_variants: int,
) -> Tuple[Path, Path]:
    expected = build_dzine_expected_paths(products, out_dir, run_date)
    expected_json = out_dir / "dzine_expected_outputs.json"
    atomic_write_json(expected_json, expected)

    lines: List[str] = []
    lines.append("# Dzine UI Automation Task (No API)")
    lines.append("")
    lines.append("Execution mode: OpenClaw browser automation with persistent profile + slow mode.")
    lines.append("Hard rules:")
    lines.append("- Do not use Dzine API.")
    lines.append("- Keep browser profile persistent (reuse logged session).")
    lines.append("- Use slow mode interaction (wait for UI transitions and generation completion).")
    lines.append("- For each generation, capture a verification screenshot before download.")
    lines.append("- Download outputs exactly to the paths below.")
    lines.append("- Do not render prices in Dzine images.")
    lines.append("")
    lines.append("Per product instructions:")
    ranked = sorted(products, key=lambda p: p.ranking_score, reverse=True)
    for idx, p in enumerate(ranked, start=1):
        refs = reference_manifest.get(p.asin, {})
        hero_ref = refs.get("hero_ref_path", "")
        life_ref = refs.get("life_ref_path", "")
        lines.append(f"## Product #{idx} - {p.product_title} ({p.asin})")
        lines.append(f"- Reference hero: `{hero_ref}`")
        lines.append(f"- Reference lifestyle: `{life_ref}`")
        lines.append("- Generate variants: Hero clean / In-use / Benefit shot.")
        lines.append(f"- Save: `{out_dir / 'assets' / 'dzine' / run_date / p.asin / 'v1.png'}`")
        lines.append(f"- Save: `{out_dir / 'assets' / 'dzine' / run_date / p.asin / 'v2.png'}`")
        lines.append(f"- Save: `{out_dir / 'assets' / 'dzine' / run_date / p.asin / 'v3.png'}`")
        lines.append(f"- Verify screenshot: `{out_dir / 'assets' / 'dzine' / run_date / p.asin / 'verify_v1.png'}`")
        lines.append(f"- Verify screenshot: `{out_dir / 'assets' / 'dzine' / run_date / p.asin / 'verify_v2.png'}`")
        lines.append(f"- Verify screenshot: `{out_dir / 'assets' / 'dzine' / run_date / p.asin / 'verify_v3.png'}`")
        lines.append("")
    lines.append("Thumbnail:")
    lines.append(f"- Save variant A: `{out_dir / 'assets' / 'dzine' / run_date / 'thumbnails' / 'thumb_a.png'}`")
    lines.append(f"- Save variant B: `{out_dir / 'assets' / 'dzine' / run_date / 'thumbnails' / 'thumb_b.png'}`")
    lines.append("")
    lines.append("Lip sync clips (short only):")
    lines.append(f"- Hook: `{out_dir / 'assets' / 'dzine' / run_date / 'lipsync' / 'hook.mp4'}`")
    lines.append(f"- Transition: `{out_dir / 'assets' / 'dzine' / run_date / 'lipsync' / 'transition.mp4'}`")
    lines.append(f"- Outro: `{out_dir / 'assets' / 'dzine' / run_date / 'lipsync' / 'outro.mp4'}`")
    lines.append("")
    lines.append(f"Minimum acceptance per product: {min_variants} variants.")
    lines.append("If any output fails, stop and document which files were not generated.")

    task_md = out_dir / "dzine_ui_automation_task.md"
    task_md.write_text("\n".join(lines), encoding="utf-8")
    return task_md, expected_json


def run_dzine_ui_automation(
    task_md: Path,
    agent_name: str,
    timeout_sec: int,
) -> Dict:
    msg = (
        f"Execute this Dzine UI automation task exactly from file `{task_md}`. "
        "Use OpenClaw managed browser with persistent profile and slow mode. "
        "After completion, reply with short status plus any blocking issues."
    )
    cmd = [
        "openclaw",
        "agent",
        "--agent",
        agent_name,
        "--thinking",
        "low",
        "--timeout",
        str(timeout_sec),
        "--json",
        "--message",
        msg,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except Exception as exc:  # noqa: BLE001
        return {"attempted": True, "ok": False, "error": str(exc)}
    return {
        "attempted": True,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout_preview": normalize_ws((proc.stdout or "")[:800]),
        "stderr_preview": normalize_ws((proc.stderr or "")[:800]),
    }


def scan_dzine_outputs(
    products: List[Product],
    out_dir: Path,
    run_date: str,
    min_variants: int,
) -> Dict:
    root = out_dir / "assets" / "dzine" / run_date
    per_product = []
    all_min_ok = True
    all_three_ok = True
    for p in sorted(products, key=lambda x: x.ranking_score, reverse=True):
        pdir = root / p.asin
        variants = [pdir / "v1.png", pdir / "v2.png", pdir / "v3.png"]
        shots = [pdir / "verify_v1.png", pdir / "verify_v2.png", pdir / "verify_v3.png"]
        existing = [str(x) for x in variants if x.exists()]
        existing_shots = [str(x) for x in shots if x.exists()]
        count = len(existing)
        if count < min_variants:
            all_min_ok = False
        if count < 3:
            all_three_ok = False
        per_product.append(
            {
                "asin": p.asin,
                "variant_count": count,
                "variants_existing": existing,
                "screenshots_existing": existing_shots,
                "min_ok": count >= min_variants,
            }
        )

    thumbs = [root / "thumbnails" / "thumb_a.png", root / "thumbnails" / "thumb_b.png"]
    thumbs_existing = [str(x) for x in thumbs if x.exists()]
    lips = [root / "lipsync" / "hook.mp4", root / "lipsync" / "transition.mp4", root / "lipsync" / "outro.mp4"]
    lips_existing = [str(x) for x in lips if x.exists()]

    result_status = "full_success" if all_three_ok else ("partial_success" if all_min_ok else "failed")
    return {
        "run_date": run_date,
        "root": str(root),
        "status": result_status,
        "min_variants_required": min_variants,
        "all_products_min_ok": all_min_ok,
        "all_products_three_ok": all_three_ok,
        "products": per_product,
        "thumbnail_variants_existing": thumbs_existing,
        "thumbnail_ok": len(thumbs_existing) >= 2,
        "lipsync_segments_existing": lips_existing,
        "lipsync_ok": len(lips_existing) >= 3,
    }


def write_dzine_automation_reports(
    out_dir: Path,
    scan: Dict,
    run_info: Dict,
    reference_manifest: Dict[str, Dict],
) -> Tuple[Path, Path]:
    fallback = {
        "use_amazon_ken_burns_for_day": scan.get("status") == "failed",
        "partial_fill_with_amazon_refs": scan.get("status") == "partial_success",
        "fallback_thumbnail_in_davinci": not scan.get("thumbnail_ok", False),
        "fallback_lipsync_static_avatar_with_captions": not scan.get("lipsync_ok", False),
    }
    report = {
        "generated_at": now_iso(),
        "automation_run": run_info,
        "scan": scan,
        "fallback": fallback,
        "reference_manifest_summary": {
            "count": len(reference_manifest),
            "hero_ok": sum(1 for v in reference_manifest.values() if v.get("hero_exists")),
            "life_ok": sum(1 for v in reference_manifest.values() if v.get("life_exists")),
        },
    }
    json_path = out_dir / "dzine_generation_report.json"
    md_path = out_dir / "dzine_generation_report.md"
    atomic_write_json(json_path, report)

    lines = ["# Dzine Generation Report", ""]
    lines.append(f"- Status: `{scan.get('status')}`")
    lines.append(f"- Attempted automation: `{run_info.get('attempted', False)}`")
    lines.append(f"- Automation command ok: `{run_info.get('ok', False)}`")
    lines.append(f"- Thumbnail variants found: `{len(scan.get('thumbnail_variants_existing', []))}/2`")
    lines.append(f"- Lip sync segments found: `{len(scan.get('lipsync_segments_existing', []))}/3`")
    lines.append("")
    lines.append("## Product Variant Coverage")
    for item in scan.get("products", []):
        lines.append(
            f"- `{item['asin']}`: {item['variant_count']} variants "
            f"(min ok: {item['min_ok']})"
        )
    lines.append("")
    lines.append("## Fallback Actions")
    if fallback["use_amazon_ken_burns_for_day"]:
        lines.append("- Full Dzine failure: use Amazon refs + DaVinci Ken Burns + price overlays.")
    if fallback["partial_fill_with_amazon_refs"]:
        lines.append("- Partial Dzine success: fill missing shots with Amazon refs + Ken Burns.")
    if fallback["fallback_lipsync_static_avatar_with_captions"]:
        lines.append("- Lip sync fallback: static avatar + captions for hook/transitions/outro.")
    if fallback["fallback_thumbnail_in_davinci"]:
        lines.append("- Thumbnail fallback: render template thumbnail in DaVinci.")
    if not any(fallback.values()):
        lines.append("- No fallback needed.")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path

def build_openclaw_script_prompt(
    products: List[Product],
    theme: str,
    channel_name: str,
    long_version: bool,
) -> str:
    ranked = sorted(products, key=lambda p: p.ranking_score, reverse=True)
    show_order = list(reversed(ranked))
    min_words, max_words = (1650, 1900) if long_version else (1100, 1250)
    duration_label = "12-minute" if long_version else "8-minute"
    lines: List[str] = []
    lines.append(
        f"Write a natural YouTube script in English for {channel_name}, Top 5 {theme}, {duration_label} version."
    )
    lines.append(
        f"Hard constraints: word count between {min_words} and {max_words}, no robotic phrasing, no emojis, no fake claims."
    )
    lines.append(
        "Voice constraint: write like a real human host who actually reviews products (confident, specific, a bit opinionated), not a generic narrator."
    )
    lines.append(
        "Avoid these cliches/AI tells: 'let's dive in', 'in this video', 'game changer', 'without further ado', 'as an AI', 'ultimate', 'best ever'."
    )
    lines.append("Structure:")
    lines.append("1) Hook (first 20 seconds): pain point + promise + tease #5 and #1.")
    lines.append("2) Countdown from #5 to #1.")
    lines.append("3) For each product include: summary, 3 practical benefits, 1 honest downside, current price, best user profile.")
    lines.append("4) Closing recap + CTA mentioning affiliate links in description.")
    lines.append("5) Add affiliate and AI disclosure naturally near the end.")
    lines.append("Style:")
    lines.append("- Conversational, confident, human, specific, no repetitive filler blocks.")
    lines.append("- Avoid generic repeated sentences and avoid listicle clichés.")
    lines.append("- Keep transitions between ranks smooth.")
    lines.append("- Add small real-world framing where helpful (e.g., who should skip it, what it feels like day-to-day, a quick 'if you're the kind of person who...' line).")
    lines.append("- Include a light 'prices change, check the link for current price' line once (not repeated every product).")
    lines.append("")
    lines.append("Products (same category only):")
    rank_num = 5
    median_price = sorted([p.current_price_usd for p in ranked])[len(ranked) // 2]
    for p in show_order:
        benefits = ensure_feature_benefits(p)
        downside = downside_for(p, median_price)
        best = best_for(theme, p)
        lines.append(
            f"#{rank_num} | {p.product_title} | price ${p.current_price_usd:.2f} | rating {p.rating:.1f} | reviews {p.review_count:,}"
        )
        lines.append(f"- Benefit 1 seed: {benefits[0]}")
        lines.append(f"- Benefit 2 seed: {benefits[1]}")
        lines.append(f"- Benefit 3 seed: {benefits[2]}")
        lines.append(f"- Honest downside seed: {downside}")
        lines.append(f"- Best for seed: {best}")
        rank_num -= 1
    lines.append("")
    lines.append("Output only markdown script. No meta commentary.")
    return "\n".join(lines)


def parse_openclaw_text(stdout_text: str) -> str:
    data = json.loads(stdout_text)
    payloads = (((data or {}).get("result") or {}).get("payloads") or [])
    if not payloads:
        raise RuntimeError("OpenClaw returned no payloads.")
    text = normalize_ws(payloads[0].get("text", "")).replace("\\n", "\n")
    if not text:
        raise RuntimeError("OpenClaw returned empty text payload.")
    return payloads[0].get("text", "")


def generate_script_with_openclaw(
    products: List[Product],
    theme: str,
    channel_name: str,
    long_version: bool,
    agent_id: str,
    timeout_sec: int,
) -> str:
    prompt = build_openclaw_script_prompt(products, theme, channel_name, long_version)
    suffix = "long" if long_version else "short"
    session_id = f"agent:{agent_id}:pipeline_{slugify(theme, 24)}_{suffix}_{int(time.time())}"
    cmd = [
        "openclaw",
        "agent",
        "--agent",
        agent_id,
        "--session-id",
        session_id,
        "--thinking",
        "low",
        "--timeout",
        str(timeout_sec),
        "--json",
        "--message",
        prompt,
    ]
    p = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if p.returncode != 0:
        raise RuntimeError(
            f"OpenClaw script generation failed ({suffix}). stderr: {normalize_ws(p.stderr)[:280]}"
        )
    return parse_openclaw_text(p.stdout)


def write_dzine_prompts(prompt_pack: Dict, out_dir: Path) -> Tuple[Path, Path]:
    json_path = out_dir / "dzine_prompts.json"
    md_path = out_dir / "dzine_prompts.md"
    atomic_write_json(json_path, prompt_pack)

    lines: List[str] = []
    lines.append("# Dzine Prompt Pack (NanoBanana Pro)")
    lines.append("")
    lines.append("All prompts below explicitly target `NanoBanana Pro`.")
    lines.append("")
    for p in prompt_pack["products"]:
        lines.append(f"## Rank #{p['rank']} - {p['product_title']}")
        lines.append(f"- ASIN: `{p['asin']}`")
        ref = p.get("reference_anchor") or {}
        lines.append(f"- Reference hero: `{ref.get('hero_ref_path', '')}`")
        lines.append(f"- Reference lifestyle: `{ref.get('life_ref_path', '')}`")
        lines.append(f"- Variant 1: {p['variant_1']}")
        lines.append(f"- Variant 2: {p['variant_2']}")
        lines.append(f"- Variant 3: {p['variant_3']}")
        lines.append(f"- Variant 4 (optional): {p['variant_4_optional']}")
        lines.append("")
    lines.append("## Thumbnail Prompt")
    lines.append(prompt_pack["thumbnail_prompt"])
    lines.append("")
    lines.append("## Guidance")
    lines.append(
        f"- Recommended images/product: `{prompt_pack['guidance']['recommended_images_per_product']}`"
    )
    lines.append(f"- Why: {prompt_pack['guidance']['why']}")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def write_voice_plan(
    script_a: str,
    script_b: str,
    voice_name: str,
    out_dir: Path,
) -> Path:
    chars_a = estimate_elevenlabs_chars(script_a)
    chars_b = estimate_elevenlabs_chars(script_b)
    lines = [
        "# Voice Generation Plan (ElevenLabs)",
        "",
        f"- Voice: `{voice_name}`",
        "- Credit model: approx 1 character = 1 TTS credit.",
        "",
        "## Character / Credit Estimate",
        f"- Script A (~8 min): `{chars_a}` characters (estimated credits: `{chars_a}`)",
        f"- Script B (~12 min): `{chars_b}` characters (estimated credits: `{chars_b}`)",
        "",
        "## Generation Command Examples",
        "```bash",
        "ELEVENLABS_API_KEY=YOUR_KEY \\",
        f"python3 \"{BASE_DIR / 'tools' / 'elevenlabs_voiceover_api.py'}\" \\",
        f"  --script \"{(out_dir / 'script_A_8min.md')}\" \\",
        f"  --voice-name \"{voice_name}\" \\",
        f"  --output-dir \"{(out_dir / 'voiceover_A')}\" \\",
        f"  --report \"{(out_dir / 'voiceover_A_report.md')}\"",
        "```",
        "",
        "```bash",
        "ELEVENLABS_API_KEY=YOUR_KEY \\",
        f"python3 \"{BASE_DIR / 'tools' / 'elevenlabs_voiceover_api.py'}\" \\",
        f"  --script \"{(out_dir / 'script_B_12min.md')}\" \\",
        f"  --voice-name \"{voice_name}\" \\",
        f"  --output-dir \"{(out_dir / 'voiceover_B')}\" \\",
        f"  --report \"{(out_dir / 'voiceover_B_report.md')}\"",
        "```",
        "",
        "Tip: generate in chunks (existing script already chunks by headings) to reduce regeneration cost.",
    ]
    path = out_dir / "voice_generation_plan.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_davinci_manifest(
    products: List[Product],
    theme: str,
    out_dir: Path,
    run_date: str,
    reference_manifest: Dict[str, Dict],
    dzine_scan: Dict,
) -> Path:
    image_assets = []
    placeholder = ensure_placeholder_frame(out_dir)
    ranked = sorted(products, key=lambda p: p.ranking_score, reverse=True)
    dz_root = out_dir / "assets" / "dzine" / run_date
    for i, p in enumerate(ranked, start=1):
        asin = p.asin
        pdir = dz_root / asin
        dz_variants = [pdir / "v1.png", pdir / "v2.png", pdir / "v3.png"]
        existing_variants = [x for x in dz_variants if x.exists()]
        refs = reference_manifest.get(asin, {})
        hero_ref = Path(refs.get("hero_ref_path", ""))
        life_ref = Path(refs.get("life_ref_path", ""))
        fallback_cycle = [hero_ref, life_ref, hero_ref]

        chosen: List[Path] = []
        if len(existing_variants) >= 3:
            chosen = existing_variants[:3]
        elif len(existing_variants) >= 2:
            chosen = existing_variants[:2]
            for f in fallback_cycle:
                if f.exists():
                    chosen.append(f)
                    break
        else:
            for f in fallback_cycle:
                if f.exists():
                    chosen.append(f)
        while len(chosen) < 3 and hero_ref.exists():
            chosen.append(hero_ref)
        if not chosen:
            chosen = [placeholder, placeholder, placeholder]

        for v_idx, path_obj in enumerate(chosen[:3], start=1):
            image_assets.append(
                {
                    "id": f"p{i}_v{v_idx}",
                    "product": p.product_title,
                    "asin": asin,
                    "path": str(path_obj),
                    "source": "dzine" if str(path_obj).startswith(str(dz_root)) else "amazon_ref",
                    "motion": "ken_burns" if not str(path_obj).startswith(str(dz_root)) else "none",
                }
            )

    overlay_items = []
    for i, p in enumerate(ranked, start=1):
        overlay_items.append(
            {
                "rank": i,
                "asin": p.asin,
                "product_title": p.product_title,
                "price_text": f"${p.current_price_usd:.2f}",
                "overlay_text": f"${p.current_price_usd:.2f} · Amazon US · At time of recording",
                "template": "price_card_default",
            }
        )

    thumbs = [
        dz_root / "thumbnails" / "thumb_a.png",
        dz_root / "thumbnails" / "thumb_b.png",
    ]
    thumb_existing = [str(x) for x in thumbs if x.exists()]

    manifest = {
        "project_name": f"Rayviews_Top5_{slugify(theme, 24)}_{now_date()}",
        "timeline_name": "Top5_Main_16x9",
        "resolution": {"width": 1920, "height": 1080},
        "fps": 30,
        "voiceover_path": str(out_dir / "voiceover_A" / "vo_01_hook.mp3"),
        "music_path": str(out_dir / "assets" / "bgm.mp3"),
        "caption_srt_path": str(out_dir / "captions.srt"),
        "image_assets": image_assets,
        "price_overlays": overlay_items,
        "lipsync_segments": {
            "hook": str(dz_root / "lipsync" / "hook.mp4"),
            "transition": str(dz_root / "lipsync" / "transition.mp4"),
            "outro": str(dz_root / "lipsync" / "outro.mp4"),
            "fallback_mode": "static_avatar_with_captions" if not dzine_scan.get("lipsync_ok", False) else "normal",
        },
        "thumbnail": {
            "variants": thumb_existing,
            "fallback_template": str(out_dir / "assets" / "thumbnail_fallback_template.png"),
            "use_fallback": len(thumb_existing) < 2,
        },
        "render": {
            "target_dir": str(out_dir / "render"),
            "custom_name": f"rayviews_top5_{slugify(theme, 24)}",
            "preset_candidates": ["YouTube 1080p", "H.264 Master", "YouTube"],
        },
        "fallback_policy": {
            "dzine_status": dzine_scan.get("status"),
            "min_variants_required": dzine_scan.get("min_variants_required", 2),
            "full_failure_use_amazon_refs_ken_burns": dzine_scan.get("status") == "failed",
            "partial_failure_fill_missing_with_refs": dzine_scan.get("status") == "partial_success",
        },
    }
    path = out_dir / "davinci_manifest.json"
    atomic_write_json(path, manifest)
    return path


def write_upload_files(upload_pack: Dict, out_dir: Path) -> Tuple[Path, Path]:
    metadata_json = out_dir / "youtube_upload_metadata.json"
    description_txt = out_dir / "youtube_description.txt"
    atomic_write_json(metadata_json, upload_pack)
    description_txt.write_text(upload_pack["description"], encoding="utf-8")
    return metadata_json, description_txt


def write_final_checklist(
    out_dir: Path,
    json_products: Path,
    csv_products: Path,
    script_a: Path,
    script_b: Path,
    gate1_anti_ai_report: Path,
    dzine_md: Path,
    refs_manifest: Path,
    dzine_task: Path,
    dzine_report: Path,
    price_overlay_plan: Path,
    voice_plan: Path,
    davinci_manifest: Path,
    upload_json: Path,
) -> Path:
    lines = [
        "# End-to-End Run Checklist",
        "",
        "## Stage 1 - Product Discovery",
        f"- Confirm product JSON: `{json_products}`",
        f"- Confirm product CSV: `{csv_products}`",
        "- Validate all products are in same category and sold on Amazon.",
        "- Confirm no ASIN repeats from the recent exclusion window.",
        "",
        "Debug tips:",
        "- If fewer than 5 results, lower filters (`--min-reviews`, `--min-rating`) or choose a broader theme.",
        "- If Amazon blocks requests, wait, reduce page count, or run with `--discovery-mode mock`.",
        "",
        "## Stage 2 - Script",
        f"- Script A path: `{script_a}`",
        f"- Script B path: `{script_b}`",
        f"- Anti-AI report: `{gate1_anti_ai_report}`",
        "- Confirm each product has 3 benefits + 1 downside + best-for line.",
        "",
        "Debug tips:",
        "- If script sounds repetitive, re-run with a more specific theme phrase.",
        "- Keep claims tied to discovered bullets and review metrics.",
        "",
        "## Stage 3 - Dzine Prompts",
        f"- Prompt pack: `{dzine_md}`",
        f"- Amazon references manifest: `{refs_manifest}`",
        f"- Dzine UI task: `{dzine_task}`",
        f"- Dzine generation report: `{dzine_report}`",
        f"- Price overlays for DaVinci: `{price_overlay_plan}`",
        "- Generate at least 3 images/product plus 1 thumbnail.",
        "",
        "Debug tips:",
        "- If character consistency drifts, repeat identity anchor text at start of each prompt.",
        "- Do not render price text inside Dzine images; overlay it in DaVinci templates.",
        "- If Dzine fails, fall back to Amazon references + Ken Burns motion for that day.",
        "",
        "## Stage 4 - Voice (ElevenLabs)",
        f"- Voice plan: `{voice_plan}`",
        "- Generate Script A or Script B audio chunks using your chosen voice clone.",
        "",
        "Debug tips:",
        "- If pacing is flat, reduce stability and increase style slightly in ElevenLabs settings.",
        "- Regenerate only failed chunks to save credits.",
        "",
        "## Stage 5 - Edit Automation (DaVinci Resolve)",
        f"- Manifest: `{davinci_manifest}`",
        f"- Run: `python3 {BASE_DIR / 'tools' / 'davinci_top5_autocut.py'} --manifest <manifest>`",
        "",
        "Debug tips:",
        "- Ensure Resolve is open and an active local library is selected.",
        "- If transition API method is missing, script still builds timeline and logs manual fallback step.",
        "",
        "## Stage 6 - Upload Automation (YouTube API)",
        f"- Upload metadata: `{upload_json}`",
        f"- Run: `python3 {BASE_DIR / 'tools' / 'youtube_upload_api.py'} ...`",
        "",
        "Debug tips:",
        "- First OAuth run must be interactive in browser.",
        "- If upload fails, check quota and category/privacy values.",
    ]
    path = out_dir / "FINAL_CHECKLIST.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_success_trajectory(run_slug: str, state: Dict, out_dir: Path) -> Path:
    TRAJECTORIES_DIR.mkdir(parents=True, exist_ok=True)
    artifacts = state.get("artifacts") or {}
    products_path = Path(artifacts.get("products_json", out_dir / "product_selection.json"))

    decisions: List[Dict] = []
    if products_path.exists():
        try:
            products = load_products_json(products_path)
            ranked = sorted(products, key=lambda p: p.ranking_score, reverse=True)
            for idx, p in enumerate(ranked, start=1):
                decisions.append(
                    {
                        "rank": idx,
                        "asin": p.asin,
                        "title": p.product_title,
                        "price_usd": p.current_price_usd,
                        "rating": p.rating,
                        "review_count": p.review_count,
                        "score": p.ranking_score,
                    }
                )
        except Exception:
            decisions = []

    sources = []
    for key in [
        "products_json",
        "products_csv",
        "script_a",
        "script_b",
        "gate1_review",
        "gate2_review",
        "davinci_manifest",
        "youtube_upload_metadata",
        "youtube_upload_metadata_json",
    ]:
        v = artifacts.get(key)
        if v:
            sources.append(str(v))

    payload = {
        "id": f"traj_{run_slug}",
        "run_slug": run_slug,
        "created_at": now_iso(),
        "category": state.get("category", ""),
        "ranking_rule": "Composite score over rating, reviews, theme match, and availability constraints.",
        "sources": sources,
        "decisions": decisions,
        "notes": {
            "gate1_reviewer": (state.get("gate1") or {}).get("reviewer", ""),
            "gate1_notes": (state.get("gate1") or {}).get("notes", ""),
            "gate2_reviewer": (state.get("gate2") or {}).get("reviewer", ""),
            "gate2_notes": (state.get("gate2") or {}).get("notes", ""),
            "status": state.get("status", ""),
        },
    }
    out = TRAJECTORIES_DIR / f"{now_date()}_{run_slug}.json"
    atomic_write_json(out, payload)
    return out


def infer_latest_run_slug(output_root: Path, theme: str) -> str:
    prefix = slugify(theme)
    candidates = []
    for d in output_root.iterdir():
        if d.is_dir() and d.name.startswith(prefix + "_"):
            candidates.append(d.name)
    if not candidates:
        raise RuntimeError(
            "No existing run found for this theme. Pass --run-slug or run phase gate1 first."
        )
    return sorted(candidates)[-1]


def ensure_disclaimer_line(script_text: str) -> str:
    line = "Prices may change—check the link for current price."
    if line.lower() in script_text.lower():
        return script_text
    return script_text.rstrip() + "\n\n" + line + "\n"


def resolve_run_context(args: argparse.Namespace) -> Tuple[str, Path]:
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    run_slug = (args.run_slug or "").strip()
    if not run_slug:
        if args.phase == PHASE_GATE1:
            if not args.theme:
                raise RuntimeError("Phase gate1 requires --theme when --run-slug is not provided.")
            run_slug = f"{slugify(args.theme)}_{now_date()}"
        else:
            if not args.theme:
                raise RuntimeError("For this phase, pass --run-slug or --theme.")
            run_slug = infer_latest_run_slug(output_root, args.theme)
    out_dir = output_root / run_slug
    return run_slug, out_dir


def sync_state(state: Dict, out_dir: Path) -> Dict:
    state_path = save_state(out_dir, state)
    sync_info = upsert_video_run_state_supabase(state)
    return {"state_file": str(state_path), "supabase_sync": sync_info}


def phase_gate1(args: argparse.Namespace, run_slug: str, out_dir: Path) -> Dict:
    # Allow early pipeline runs without an affiliate tag; we'll surface this as a Gate-1 warning.
    # The links will be plain Amazon URLs until a tag is configured.
    if args.affiliate_tag is None:
        args.affiliate_tag = ""
    out_dir.mkdir(parents=True, exist_ok=True)
    output_root = Path(args.output_root)
    config = {
        "min_rating": args.min_rating,
        "min_reviews": args.min_reviews,
        "min_price": args.min_price,
        "max_price": args.max_price,
        "exclude_last_days": args.exclude_last_days,
        "script_source": args.script_source,
    }
    state = ensure_state_base(
        out_dir=out_dir,
        run_slug=run_slug,
        theme=args.theme,
        category=args.category or args.theme,
        config=config,
    )
    state["theme"] = args.theme
    state["category"] = args.category or args.theme

    excluded_asins = collect_recent_asins(output_root, args.exclude_last_days)
    products_json_path = out_dir / "product_selection.json"
    products_csv_path = out_dir / "product_selection.csv"

    if args.regenerate == "script" and products_json_path.exists():
        products = load_products_json(products_json_path)
    else:
        if args.discovery_mode == "mock":
            products = mock_products(args.theme, args.affiliate_tag, args.top_n, excluded_asins)
        else:
            # Prefer a category-specific Amazon starting point when available so discovery stays
            # inside the chosen category-of-day instead of drifting into whatever is trending.
            category_key = (args.category or args.theme or "").strip()
            category_search_url = resolve_amazon_search_url_for_category(category_key)
            products = discover_products_scrape(
                theme=args.theme,
                affiliate_tag=args.affiliate_tag,
                top_n=args.top_n,
                min_rating=args.min_rating,
                min_reviews=args.min_reviews,
                min_price=args.min_price,
                max_price=args.max_price,
                max_pages=args.max_pages,
                excluded_asins=excluded_asins,
                min_theme_match=args.min_theme_match,
                search_url=category_search_url,
            )
        products_json_path, products_csv_path = write_products_json_csv(products, out_dir)

    if args.script_source == "openclaw":
        script_a_text = generate_script_with_openclaw(
            products=products,
            theme=args.theme,
            channel_name=args.channel_name,
            long_version=False,
            agent_id=args.openclaw_agent,
            timeout_sec=args.openclaw_timeout,
        )
        script_b_text = generate_script_with_openclaw(
            products=products,
            theme=args.theme,
            channel_name=args.channel_name,
            long_version=True,
            agent_id=args.openclaw_agent,
            timeout_sec=args.openclaw_timeout,
        )
    else:
        script_a_text = build_script(products, args.theme, args.channel_name, long_version=False)
        script_b_text = build_script(products, args.theme, args.channel_name, long_version=True)

    ranked = sorted(products, key=lambda p: p.ranking_score, reverse=True)
    script_a_text = enforce_word_bounds(
        ensure_disclaimer_line(script_a_text), 1100, 1250, args.theme, ranked
    )
    script_b_text = enforce_word_bounds(
        ensure_disclaimer_line(script_b_text), 1650, 1900, args.theme, ranked
    )
    script_a_path, script_b_path = write_scripts(script_a_text, script_b_text, out_dir)
    anti_ai = evaluate_anti_ai_quality(
        script_a_text=script_a_text,
        script_b_text=script_b_text,
        max_allowed=max(0, int(args.anti_ai_max_violations)),
    )
    anti_ai_report = write_gate1_anti_ai_report(
        out_dir=out_dir,
        anti_ai=anti_ai,
        script_a_path=script_a_path,
        script_b_path=script_b_path,
    )
    gate1_review = write_gate1_review(
        out_dir=out_dir,
        category=state["category"],
        products=products,
        script_a_text=script_a_text,
        script_b_text=script_b_text,
        script_a_path=script_a_path,
        script_b_path=script_b_path,
        anti_ai=anti_ai,
        anti_ai_report_path=anti_ai_report,
    )
    upload_pack = build_upload_package(args.theme, products, args.affiliate_tag, args.channel_name)
    upload_json, upload_desc = write_upload_files(upload_pack, out_dir)

    gate1_reason = "gate1 package generated; awaiting human approval"
    if not anti_ai.get("pass"):
        gate1_reason = "gate1 package generated with anti-AI violations; rewrite recommended before approval"
    set_status(state, STATUS_DRAFT_WAITING_GATE_1, gate1_reason)
    state["gate1"].update({"approved": False, "rejected": False, "reviewer": "", "notes": "", "decision_at": ""})
    state["artifacts"].update(
        {
            "products_json": str(products_json_path),
            "products_csv": str(products_csv_path),
            "script_a": str(script_a_path),
            "script_b": str(script_b_path),
            "gate1_anti_ai_report": str(anti_ai_report),
            "gate1_review": str(gate1_review),
            "upload_metadata_json": str(upload_json),
            "upload_description_txt": str(upload_desc),
        }
    )
    state.setdefault("quality_checks", {})["anti_ai"] = {
        "pass": bool(anti_ai.get("pass")),
        "total_violations": int(anti_ai.get("total_violations", 0)),
        "max_allowed": int(anti_ai.get("max_allowed", 0)),
        "updated_at": now_iso(),
    }
    sync_meta = sync_state(state, out_dir)
    return {
        "phase": PHASE_GATE1,
        "run_slug": run_slug,
        "output_dir": str(out_dir),
        "status": state["status"],
        "excluded_asins_count": len(excluded_asins),
        "products_json": str(products_json_path),
        "products_csv": str(products_csv_path),
        "script_a": str(script_a_path),
        "script_b": str(script_b_path),
        "gate1_anti_ai_report": str(anti_ai_report),
        "anti_ai_status": "PASS" if anti_ai.get("pass") else "FAIL",
        "anti_ai_total_violations": anti_ai.get("total_violations", 0),
        "anti_ai_needs_rewrite": not anti_ai.get("pass"),
        "gate1_review": str(gate1_review),
        "script_a_word_count": word_count(script_a_text),
        "script_b_word_count": word_count(script_b_text),
        **sync_meta,
    }


def phase_gate2(args: argparse.Namespace, run_slug: str, out_dir: Path) -> Dict:
    state = load_state(out_dir)
    if not state:
        raise RuntimeError("Run state not found. Execute gate1 first.")
    require_gate_approved(state, "gate1")

    products_json = Path((state.get("artifacts") or {}).get("products_json", out_dir / "product_selection.json"))
    if not products_json.exists():
        raise RuntimeError("products_json not found in run artifacts.")
    products = load_products_json(products_json)

    script_a_path = Path((state.get("artifacts") or {}).get("script_a", out_dir / "script_A_8min.md"))
    script_b_path = Path((state.get("artifacts") or {}).get("script_b", out_dir / "script_B_12min.md"))
    if not script_a_path.exists() or not script_b_path.exists():
        raise RuntimeError("Script files are missing; rerun gate1.")
    script_a_text = script_a_path.read_text(encoding="utf-8")
    script_b_text = script_b_path.read_text(encoding="utf-8")

    category = state.get("category") or state.get("theme") or args.theme
    run_date = (parse_run_date_from_dirname(run_slug) or dt.date.today()).isoformat()

    refs_manifest_path, refs_manifest = download_amazon_reference_images(products, out_dir)
    price_overlays_json, price_overlays_md = write_price_overlay_plan(products, out_dir)

    rejected_filenames = set()
    if args.rejected_assets:
        rejected_filenames = {
            x.strip()
            for x in str(args.rejected_assets).split(",")
            if x.strip()
        }
    dzine_pack = generate_dzine_prompts(products, category, args.channel_name, refs_manifest)
    dzine_json, dzine_md = write_dzine_prompts(dzine_pack, out_dir)
    dzine_task, dzine_expected = write_dzine_ui_automation_task(
        products=products,
        out_dir=out_dir,
        run_date=run_date,
        reference_manifest=refs_manifest,
        min_variants=args.min_dzine_variants,
    )
    dzine_run_info = {"attempted": False, "ok": False, "reason": "automation_not_requested"}
    if args.run_dzine_ui_automation:
        dzine_run_info = run_dzine_ui_automation(
            task_md=dzine_task,
            agent_name=args.dzine_agent,
            timeout_sec=args.dzine_timeout,
        )
    dzine_scan = scan_dzine_outputs(
        products=products,
        out_dir=out_dir,
        run_date=run_date,
        min_variants=args.min_dzine_variants,
    )
    dzine_report_json, dzine_report_md = write_dzine_automation_reports(
        out_dir=out_dir,
        scan=dzine_scan,
        run_info=dzine_run_info,
        reference_manifest=refs_manifest,
    )
    voice_plan = write_voice_plan(script_a_text, script_b_text, args.voice_name, out_dir)
    voice_blocks = write_voice_blocks_plan(script_a_text, args.voice_name, out_dir)
    gate2_assets_json, gate2_storyboard, gate2_review = write_gate2_package(
        out_dir=out_dir,
        products=products,
        category=category,
        rejected_filenames=rejected_filenames,
    )
    davinci_manifest = write_davinci_manifest(
        products=products,
        theme=category,
        out_dir=out_dir,
        run_date=run_date,
        reference_manifest=refs_manifest,
        dzine_scan=dzine_scan,
    )
    checklist = write_final_checklist(
        out_dir=out_dir,
        json_products=products_json,
        csv_products=Path((state.get("artifacts") or {}).get("products_csv", out_dir / "product_selection.csv")),
        script_a=script_a_path,
        script_b=script_b_path,
        gate1_anti_ai_report=Path((state.get("artifacts") or {}).get("gate1_anti_ai_report", out_dir / "gate1_anti_ai_report.md")),
        dzine_md=dzine_md,
        refs_manifest=refs_manifest_path,
        dzine_task=dzine_task,
        dzine_report=dzine_report_md,
        price_overlay_plan=price_overlays_md,
        voice_plan=voice_plan,
        davinci_manifest=davinci_manifest,
        upload_json=Path((state.get("artifacts") or {}).get("upload_metadata_json", out_dir / "youtube_upload_metadata.json")),
    )

    set_status(state, STATUS_ASSETS_WAITING_GATE_2, "gate2 package generated; awaiting human approval")
    state["gate2"].update({"approved": False, "rejected": False, "reviewer": "", "notes": "", "decision_at": ""})
    state["artifacts"].update(
        {
            "dzine_prompts_json": str(dzine_json),
            "dzine_prompts_md": str(dzine_md),
            "amazon_reference_manifest": str(refs_manifest_path),
            "dzine_ui_task": str(dzine_task),
            "dzine_expected_outputs": str(dzine_expected),
            "dzine_generation_report_json": str(dzine_report_json),
            "dzine_generation_report_md": str(dzine_report_md),
            "price_overlays_json": str(price_overlays_json),
            "price_overlays_md": str(price_overlays_md),
            "voice_plan": str(voice_plan),
            "voice_blocks_plan": str(voice_blocks),
            "gate2_assets_pack_json": str(gate2_assets_json),
            "gate2_storyboard": str(gate2_storyboard),
            "gate2_review": str(gate2_review),
            "davinci_manifest": str(davinci_manifest),
            "final_checklist": str(checklist),
        }
    )
    sync_meta = sync_state(state, out_dir)
    return {
        "phase": PHASE_GATE2,
        "run_slug": run_slug,
        "output_dir": str(out_dir),
        "status": state["status"],
        "gate2_review": str(gate2_review),
        "gate2_storyboard": str(gate2_storyboard),
        "dzine_generation_report": str(dzine_report_md),
        "dzine_status": dzine_scan.get("status"),
        "voice_blocks_plan": str(voice_blocks),
        "davinci_manifest": str(davinci_manifest),
        **sync_meta,
    }


def phase_gate_decision(
    phase: str,
    args: argparse.Namespace,
    run_slug: str,
    out_dir: Path,
) -> Dict:
    state = load_state(out_dir)
    if not state:
        raise RuntimeError("Run state not found.")
    reviewer = (args.reviewer or "").strip()
    if not reviewer:
        raise RuntimeError("Reviewer is required. Pass --reviewer '<name>'.")
    notes = args.notes or ""

    if phase == PHASE_APPROVE_GATE1:
        set_gate_decision(state, "gate1", approved=True, reviewer=reviewer, notes=notes)
    elif phase == PHASE_REJECT_GATE1:
        set_gate_decision(state, "gate1", approved=False, reviewer=reviewer, notes=notes)
        set_status(state, STATUS_DRAFT_WAITING_GATE_1, "gate1 rejected; waiting regeneration")
    elif phase == PHASE_APPROVE_GATE2:
        require_gate_approved(state, "gate1")
        set_gate_decision(state, "gate2", approved=True, reviewer=reviewer, notes=notes)
    elif phase == PHASE_REJECT_GATE2:
        set_gate_decision(state, "gate2", approved=False, reviewer=reviewer, notes=notes)
        set_status(state, STATUS_ASSETS_WAITING_GATE_2, "gate2 rejected; waiting asset regeneration")
    else:
        raise RuntimeError(f"Unsupported decision phase: {phase}")

    sync_meta = sync_state(state, out_dir)
    return {
        "phase": phase,
        "run_slug": run_slug,
        "status": state["status"],
        "gate1": state.get("gate1"),
        "gate2": state.get("gate2"),
        **sync_meta,
    }


def phase_finalize(args: argparse.Namespace, run_slug: str, out_dir: Path) -> Dict:
    state = load_state(out_dir)
    if not state:
        raise RuntimeError("Run state not found.")
    require_gate_approved(state, "gate2")

    manifest = Path((state.get("artifacts") or {}).get("davinci_manifest", out_dir / "davinci_manifest.json"))
    metadata_json = Path((state.get("artifacts") or {}).get("upload_metadata_json", out_dir / "youtube_upload_metadata.json"))
    if not manifest.exists():
        raise RuntimeError("DaVinci manifest not found. Run gate2 first.")
    if not metadata_json.exists():
        raise RuntimeError("YouTube metadata file missing. Run gate1 first.")

    set_status(state, STATUS_RENDERING, "finalize started: rendering stage")
    sync_meta_render = sync_state(state, out_dir)

    render_report = out_dir / "davinci_run_report.json"
    upload_report = out_dir / "youtube_upload_report.json"
    render_attempts_log = out_dir / "render_attempts.json"
    upload_attempts_log = out_dir / "upload_attempts.json"
    render_cmd = [
        "python3",
        str(BASE_DIR / "tools" / "davinci_top5_autocut.py"),
        "--manifest",
        str(manifest),
        "--report",
        str(render_report),
    ]

    upload_cmd = [
        "python3",
        str(BASE_DIR / "tools" / "youtube_upload_api.py"),
        "--client-secrets",
        args.youtube_client_secrets,
        "--video-file",
        args.youtube_video_file,
        "--metadata-json",
        str(metadata_json),
        "--privacy-status",
        args.youtube_privacy,
    ]

    if args.finalize_dry_run:
        set_status(state, STATUS_UPLOADING, "dry-run: upload stage simulated")
        set_status(state, STATUS_PUBLISHED, "dry-run: finalize completed")
        sync_meta_final = sync_state(state, out_dir)
        return {
            "phase": PHASE_FINALIZE,
            "run_slug": run_slug,
            "status": state["status"],
            "dry_run": True,
            "render_cmd": " ".join(render_cmd),
            "upload_cmd": " ".join(upload_cmd),
            **sync_meta_render,
            **sync_meta_final,
        }

    r = run_with_retries(
        render_cmd,
        attempts=args.step_retries,
        backoff_sec=args.step_backoff_sec,
        label="davinci_render",
        log_path=render_attempts_log,
    )
    if r.returncode != 0:
        set_status(state, STATUS_FAILED, f"render_failed: {normalize_ws(r.stderr)[:220]}")
        sync_meta = sync_state(state, out_dir)
        raise RuntimeError(f"Render failed. See {render_report} and {render_attempts_log}. {sync_meta}")

    set_status(state, STATUS_UPLOADING, "render completed; uploading stage")
    sync_meta_upload = sync_state(state, out_dir)

    if not args.youtube_client_secrets or not args.youtube_video_file:
        set_status(state, STATUS_FAILED, "upload_blocked: provide --youtube-client-secrets and --youtube-video-file")
        sync_meta = sync_state(state, out_dir)
        raise RuntimeError("Upload inputs missing for finalize.")

    u = run_with_retries(
        upload_cmd,
        attempts=args.step_retries,
        backoff_sec=args.step_backoff_sec,
        label="youtube_upload",
        log_path=upload_attempts_log,
    )
    if u.returncode != 0:
        set_status(state, STATUS_FAILED, f"upload_failed: {normalize_ws(u.stderr)[:220]}")
        sync_meta = sync_state(state, out_dir)
        raise RuntimeError(f"Upload failed. See {upload_report} and {upload_attempts_log}. {sync_meta}")

    set_status(state, STATUS_PUBLISHED, "render + upload completed")
    trajectory_path = ""
    trajectory_error = ""
    try:
        trajectory = write_success_trajectory(run_slug, state, out_dir)
        trajectory_path = str(trajectory)
        state.setdefault("artifacts", {})["trajectory_json"] = trajectory_path
    except Exception as exc:  # noqa: BLE001
        trajectory_error = normalize_ws(str(exc))[:220]
    sync_meta_done = sync_state(state, out_dir)
    return {
        "phase": PHASE_FINALIZE,
        "run_slug": run_slug,
        "status": state["status"],
        "render_report": str(render_report),
        "upload_report": str(upload_report),
        "render_attempts_log": str(render_attempts_log),
        "upload_attempts_log": str(upload_attempts_log),
        "trajectory_json": trajectory_path,
        "trajectory_error": trajectory_error,
        **sync_meta_render,
        **sync_meta_upload,
        **sync_meta_done,
    }


def run_pipeline(args: argparse.Namespace) -> Dict:
    if args.phase not in VALID_PHASES:
        raise RuntimeError(f"Unknown phase: {args.phase}")
    threshold_info = maybe_apply_threshold_profile(args)
    run_slug, out_dir = resolve_run_context(args)

    if args.phase == PHASE_GATE1:
        out = phase_gate1(args, run_slug, out_dir)
        out["threshold_profile"] = threshold_info
        return out
    if args.phase == PHASE_GATE2:
        out = phase_gate2(args, run_slug, out_dir)
        out["threshold_profile"] = threshold_info
        return out
    if args.phase in {
        PHASE_APPROVE_GATE1,
        PHASE_REJECT_GATE1,
        PHASE_APPROVE_GATE2,
        PHASE_REJECT_GATE2,
    }:
        out = phase_gate_decision(args.phase, args, run_slug, out_dir)
        out["threshold_profile"] = threshold_info
        return out
    if args.phase == PHASE_FINALIZE:
        out = phase_finalize(args, run_slug, out_dir)
        out["threshold_profile"] = threshold_info
        return out
    raise RuntimeError(f"Unhandled phase: {args.phase}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build a full Top 5 YouTube pipeline package.")
    p.add_argument(
        "--phase",
        choices=sorted(VALID_PHASES),
        default=PHASE_GATE1,
        help="Pipeline phase: gate1 -> approve_gate1/reject_gate1 -> gate2 -> approve_gate2/reject_gate2 -> finalize",
    )
    p.add_argument("--theme", default="", help='Theme, e.g. "desk gadgets" or "travel accessories"')
    p.add_argument("--category", default="", help="Category label shown in Gate 1 review package")
    p.add_argument("--run-slug", default="", help="Existing run slug for non-gate1 phases")
    p.add_argument("--affiliate-tag", default="", help="Amazon affiliate tag, e.g. rayviews-20")
    p.add_argument("--channel-name", default="Rayviews", help="Channel name used in scripts")
    p.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="Output root folder")
    p.add_argument("--top-n", type=int, default=5, help="Number of products to select")
    p.add_argument("--min-rating", type=float, default=4.3, help="Minimum product rating")
    p.add_argument("--min-reviews", type=int, default=500, help="Minimum review count")
    p.add_argument("--min-price", type=float, default=20.0, help="Minimum product price")
    p.add_argument("--max-price", type=float, default=200.0, help="Maximum product price")
    p.add_argument("--max-pages", type=int, default=8, help="Max Amazon search pages in scrape mode")
    p.add_argument(
        "--exclude-last-days",
        type=int,
        default=15,
        help="Avoid ASINs used in recent runs for this many days",
    )
    p.add_argument(
        "--min-theme-match",
        type=float,
        default=0.2,
        help="Title-theme token overlap threshold (0-1) for category coherence",
    )
    p.add_argument(
        "--discovery-mode",
        choices=["scrape", "mock"],
        default="scrape",
        help="Use live Amazon scraping or deterministic mock data",
    )
    p.add_argument(
        "--script-source",
        choices=["local", "openclaw"],
        default="local",
        help="Generate scripts via local composer or OpenClaw agent (uses your logged account)",
    )
    p.add_argument(
        "--openclaw-agent",
        default="scriptwriter",
        help="OpenClaw agent id used when --script-source openclaw",
    )
    p.add_argument(
        "--openclaw-timeout",
        type=int,
        default=480,
        help="Timeout seconds for each OpenClaw script generation turn",
    )
    p.add_argument(
        "--regenerate",
        choices=["all", "products", "script"],
        default="all",
        help="In gate1, choose what to regenerate (used after rejection)",
    )
    p.add_argument(
        "--anti-ai-max-violations",
        type=int,
        default=0,
        help="Gate1 anti-AI language tolerance. 0 = fail on any banned phrase/pattern.",
    )
    p.add_argument(
        "--rejected-assets",
        default="",
        help="Gate2 selective regeneration: comma-separated filenames to regenerate only rejected assets",
    )
    p.add_argument(
        "--run-dzine-ui-automation",
        action="store_true",
        help="In gate2, ask OpenClaw browser automation agent to execute Dzine UI generation and downloads.",
    )
    p.add_argument(
        "--dzine-agent",
        default="dzine_producer",
        help="OpenClaw agent id for Dzine UI automation.",
    )
    p.add_argument(
        "--dzine-timeout",
        type=int,
        default=1800,
        help="Timeout seconds for Dzine UI automation request.",
    )
    p.add_argument(
        "--min-dzine-variants",
        type=int,
        default=2,
        help="Minimum required Dzine image variants per product for partial success.",
    )
    p.add_argument("--reviewer", default="", help="Human reviewer name for approve/reject phases")
    p.add_argument("--notes", default="", help="Reviewer notes for approve/reject phases")
    p.add_argument("--finalize-dry-run", action="store_true", help="Simulate render+upload transitions")
    p.add_argument("--step-retries", type=int, default=3, help="Retries per finalize step (render/upload)")
    p.add_argument("--step-backoff-sec", type=int, default=8, help="Base backoff seconds between retries")
    p.add_argument(
        "--thresholds-file",
        default="",
        help="Optional JSON file with per-category thresholds (min_rating/min_reviews/min_price/max_price)",
    )
    p.add_argument("--youtube-client-secrets", default="", help="Path to YouTube OAuth client secrets json")
    p.add_argument("--youtube-video-file", default="", help="Rendered video file for upload phase")
    p.add_argument("--youtube-privacy", default="private", choices=["private", "public", "unlisted"])
    p.add_argument("--voice-name", default="Thomas Louis", help="ElevenLabs voice name")
    return p


def main() -> int:
    args = build_parser().parse_args()
    try:
        summary = run_pipeline(args)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps({"ok": True, **summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
