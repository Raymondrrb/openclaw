#!/usr/bin/env python3
"""
Variation Planner — Generates a variation_plan.json for each pipeline run.

Selects opener style, structure template, product block pattern, visual style,
voice pacing, CTA variant, and disclosure template. Maximizes variation across
recent runs using a weighted diversity score.

Usage (library):
    from variation_planner import plan_variations
    plan = plan_variations(run_id, category, products)

Usage (standalone):
    python3 tools/variation_planner.py --run-id RUN_ID --category monitors --products products.json
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parent.parent))
POLICY_PATH = BASE_DIR / "policies" / "format_variation_policy.json"
RUNS_DIR = BASE_DIR / "pipeline_runs"
CONFIG_DIR = Path(os.path.expanduser("~/.config/newproject"))
SUPABASE_ENV = CONFIG_DIR / "supabase.env"

SCHEMA_VERSION = "1.0.0"

DEFAULT_EDITORIAL_FORMATS = {
    "classic_top5": {
        "label": "Classic Top 5",
        "description": "Traditional ranked countdown with balanced coverage.",
        "chapter_pattern": "intro + #5..#1 + final verdict",
        "script_rules": [
            "Maintain five ranked products (#5 to #1).",
            "Include one concise verdict per product.",
        ],
    },
    "buy_skip_upgrade": {
        "label": "Buy / Skip / Upgrade",
        "description": "Each product receives an explicit buy/skip/upgrade verdict.",
        "chapter_pattern": "intro + 5 product verdict chapters + decision recap",
        "script_rules": [
            "For each product, include one explicit verdict: BUY, SKIP, or UPGRADE.",
            "Justify verdict with one trade-off sentence.",
        ],
    },
    "persona_top3": {
        "label": "Top Picks by Persona",
        "description": "Frame recommendations around user personas.",
        "chapter_pattern": "intro + 5 products + persona mapping recap",
        "script_rules": [
            "For each product, identify the best-fit persona.",
            "At recap, map top picks to at least three personas.",
        ],
    },
    "one_winner_two_alts": {
        "label": "One Winner + 2 Alternatives",
        "description": "Declare a clear winner and two meaningful alternatives.",
        "chapter_pattern": "intro + 5 products + winner/alternatives recap",
        "script_rules": [
            "Declare one winner, two alternatives, and explain non-winner trade-offs.",
            "State why remaining products were not selected as alternatives.",
        ],
    },
    "budget_vs_premium": {
        "label": "Budget vs Premium",
        "description": "Force comparison by value tier and usage fit.",
        "chapter_pattern": "intro + budget lane + premium lane + final recommendation",
        "script_rules": [
            "Mark each product as budget/mid/premium lane.",
            "Recommend one budget-safe pick and one premium pick.",
        ],
    },
}


# ---------------------------------------------------------------------------
# Policy loading
# ---------------------------------------------------------------------------

def load_policy() -> Dict:
    """Load the format variation policy JSON."""
    if not POLICY_PATH.exists():
        raise FileNotFoundError(f"Policy not found: {POLICY_PATH}")
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# History retrieval
# ---------------------------------------------------------------------------

def _load_supabase_config() -> Optional[Dict[str, str]]:
    """Load Supabase URL and key from env file."""
    if not SUPABASE_ENV.exists():
        return None
    config = {}
    for line in SUPABASE_ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            key, _, val = line.partition("=")
            config[key.strip()] = val.strip().strip('"').strip("'")
    url = config.get("SUPABASE_URL", "")
    key = config.get("SUPABASE_SERVICE_ROLE_KEY", "") or config.get("SUPABASE_KEY", "")
    if url and key:
        return {"url": url, "key": key}
    return None


def fetch_recent_variation_events(lookback_runs: int = 10) -> List[Dict]:
    """Fetch recent variation plans from Supabase ops_events table."""
    sb = _load_supabase_config()
    if not sb:
        return []
    try:
        from urllib.request import Request, urlopen
        url = (
            f"{sb['url']}/rest/v1/ops_events"
            f"?event_type=eq.variation_planned"
            f"&order=created_at.desc"
            f"&limit={lookback_runs}"
        )
        req = Request(url, headers={
            "apikey": sb["key"],
            "Authorization": f"Bearer {sb['key']}",
            "Content-Type": "application/json",
        })
        with urlopen(req, timeout=10) as resp:
            rows = json.loads(resp.read().decode())
        plans = []
        for row in rows:
            payload = row.get("payload") or row.get("data") or {}
            if isinstance(payload, str):
                payload = json.loads(payload)
            selections = payload.get("selections")
            if selections:
                plans.append({
                    "run_id": row.get("run_id", ""),
                    "created_at": row.get("created_at", ""),
                    "selections": selections,
                })
        return plans
    except Exception:
        return []


def fetch_local_variation_history(lookback_runs: int = 10) -> List[Dict]:
    """Scan local pipeline_runs for variation_plan.json files as fallback."""
    if not RUNS_DIR.exists():
        return []
    plans = []
    run_dirs = sorted(RUNS_DIR.iterdir(), key=lambda d: d.stat().st_mtime, reverse=True)
    for run_dir in run_dirs:
        if not run_dir.is_dir():
            continue
        vp = run_dir / "variation_plan.json"
        if vp.exists():
            try:
                data = json.loads(vp.read_text(encoding="utf-8"))
                plans.append({
                    "run_id": data.get("run_id", run_dir.name),
                    "created_at": data.get("created_at", ""),
                    "selections": data.get("selections", {}),
                })
            except (json.JSONDecodeError, OSError):
                continue
        if len(plans) >= lookback_runs:
            break
    return plans


def _get_history(lookback_runs: int = 10) -> List[Dict]:
    """Get variation history from Supabase first, local fallback."""
    history = fetch_recent_variation_events(lookback_runs)
    if not history:
        history = fetch_local_variation_history(lookback_runs)
    return history


# ---------------------------------------------------------------------------
# Variation scoring
# ---------------------------------------------------------------------------

def compute_variation_score(candidate: Dict[str, str], history: List[Dict],
                            weights: Dict[str, float]) -> float:
    """Compute diversity score (0.0 = identical to recent, 1.0 = fully unique).

    For each dimension, score is 1.0 if the candidate value was never used
    in history, decaying by recency if it was used.
    """
    if not history:
        return 1.0

    total_weight = sum(weights.values())
    if total_weight == 0:
        return 1.0

    score = 0.0
    for dim, weight in weights.items():
        candidate_val = candidate.get(dim, "")
        # Find most recent use of this value
        dim_score = 1.0
        for i, past in enumerate(history):
            past_selections = past.get("selections", {})
            if past_selections.get(dim) == candidate_val:
                # Decay: more recent = lower score. i=0 is most recent.
                # i/len gives 0.0 for most recent → dim_score near 0.
                # i/len gives ~1.0 for oldest → dim_score near 0.5.
                recency_decay = i / max(len(history), 1)
                dim_score = min(dim_score, recency_decay * 0.5)
                break
        score += dim_score * (weight / total_weight)

    return round(score, 4)


# ---------------------------------------------------------------------------
# Selection logic
# ---------------------------------------------------------------------------

def _deterministic_seed(run_id: str, category: str) -> int:
    """Derive a seed from run_id + category for reproducible randomness."""
    h = hashlib.sha256(f"{run_id}:{category}".encode()).hexdigest()
    return int(h[:8], 16)


def select_variation(policy: Dict, history: List[Dict], category: str,
                     force_overrides: Optional[Dict[str, str]] = None,
                     perf_history: Optional[List[Dict]] = None) -> Tuple[Dict[str, str], float]:
    """Select variation dimensions that maximize diversity.

    Tries random candidates and picks the one with the highest combined score
    (variation diversity + performance bonus from past metrics).
    """
    weights = dict(policy.get("constraints", {}).get("dimension_weights", {}))
    weights.setdefault("editorial_format", 0.12)
    # Filter out underscore-prefixed keys (metadata like _description)
    angle_keys = [k for k in policy.get("marketing_angles", {}).keys() if not k.startswith("_")]
    editorial_formats = policy.get("editorial_formats", {})
    if not isinstance(editorial_formats, dict) or not editorial_formats:
        editorial_formats = DEFAULT_EDITORIAL_FORMATS

    dimensions = {
        "opener_style": list(policy.get("opener_styles", {}).keys()),
        "structure_template": list(policy.get("structure_templates", {}).keys()),
        "marketing_angle": angle_keys,
        "product_block_pattern": list(policy.get("product_block_patterns", {}).keys()),
        "editorial_format": list(editorial_formats.keys()),
        "visual_style": list(policy.get("visual_styles", {}).keys()),
        "voice_pacing": list(policy.get("voice_pacing_profiles", {}).keys()),
        "cta_variant": list(policy.get("cta_variants", {}).keys()),
        "disclosure_template": list(policy.get("disclosure_templates", {}).keys()),
    }

    overrides = force_overrides or {}

    best_candidate = None
    best_score = -1.0
    attempts = 50  # try enough combinations to find a good one

    for _ in range(attempts):
        candidate = {}
        for dim, options in dimensions.items():
            if dim in overrides:
                candidate[dim] = overrides[dim]
            elif options:
                candidate[dim] = random.choice(options)
            else:
                candidate[dim] = ""
        diversity = compute_variation_score(candidate, history, weights)
        perf_bonus = compute_performance_bonus(candidate, perf_history or [])
        score = diversity + perf_bonus
        if score > best_score:
            best_score = score
            best_candidate = candidate

    return best_candidate or {}, best_score


# ---------------------------------------------------------------------------
# Prompt instruction builder
# ---------------------------------------------------------------------------

def _load_category_context(category: str, policy: Dict) -> Dict[str, str]:
    """Load per-category context docs (offer characteristics + customer avatar).

    Looks in config/category_context/{category_slug}/ for .md files.
    Returns dict with keys 'offer_characteristics' and 'customer_avatar'.
    """
    ctx_config = policy.get("category_context", {})
    ctx_dir_name = ctx_config.get("context_dir", "config/category_context")
    ctx_dir = BASE_DIR / ctx_dir_name / category.lower().replace(" ", "_")

    result = {
        "offer_characteristics": "",
        "customer_avatar": "",
        "fallback_prompt": ctx_config.get("fallback_prompt", ""),
    }

    if not ctx_dir.exists():
        return result

    for filename in ["offer_characteristics.md", "offer_characteristics.txt"]:
        f = ctx_dir / filename
        if f.exists():
            try:
                result["offer_characteristics"] = f.read_text(encoding="utf-8").strip()
            except OSError:
                pass
            break

    for filename in ["customer_avatar.md", "customer_avatar.txt"]:
        f = ctx_dir / filename
        if f.exists():
            try:
                result["customer_avatar"] = f.read_text(encoding="utf-8").strip()
            except OSError:
                pass
            break

    return result


def _build_prompt_instructions(selections: Dict[str, str], policy: Dict,
                               products: List[Dict], category: str = "") -> Dict[str, Any]:
    """Translate selections into concrete prompt instructions for the LLM."""
    opener_key = selections.get("opener_style", "overwhelm")
    opener_data = policy.get("opener_styles", {}).get(opener_key, {})
    opener_template = opener_data.get("template", "")

    structure_key = selections.get("structure_template", "classic_countdown")
    structure_data = policy.get("structure_templates", {}).get(structure_key, {})

    block_key = selections.get("product_block_pattern", "classic_4seg")
    block_data = policy.get("product_block_patterns", {}).get(block_key, {})

    visual_key = selections.get("visual_style", "clean_studio")
    visual_data = policy.get("visual_styles", {}).get(visual_key, {})

    pacing_key = selections.get("voice_pacing", "standard")
    pacing_data = policy.get("voice_pacing_profiles", {}).get(pacing_key, {})

    cta_key = selections.get("cta_variant", "soft_subscribe")
    cta_data = policy.get("cta_variants", {}).get(cta_key, {})

    disclosure_key = selections.get("disclosure_template", "standard")
    disclosure_data = policy.get("disclosure_templates", {}).get(disclosure_key, {})

    # Marketing angle (Fogarty two-shot method)
    angle_key = selections.get("marketing_angle", "")
    angle_data = policy.get("marketing_angles", {}).get(angle_key, {})

    # Determine product order based on structure
    product_order = structure_data.get("product_order", "ascending_rank")

    # Load per-category context docs if available
    cat_slug = category
    if not cat_slug and products:
        cat_slug = products[0].get("category", products[0].get("title", "products"))
    category_context = _load_category_context(cat_slug, policy)

    editorial_formats = policy.get("editorial_formats", {})
    if not isinstance(editorial_formats, dict) or not editorial_formats:
        editorial_formats = DEFAULT_EDITORIAL_FORMATS
    format_key = selections.get("editorial_format", "classic_top5")
    format_data = editorial_formats.get(format_key, DEFAULT_EDITORIAL_FORMATS["classic_top5"])

    result = {
        "opener_template": opener_template,
        "opener_description": opener_data.get("description", ""),
        "structure_description": structure_data.get("description", ""),
        "structure_flow": structure_data.get("segment_flow", ""),
        "editorial_format": format_key,
        "editorial_format_label": format_data.get("label", format_key),
        "editorial_format_description": format_data.get("description", ""),
        "editorial_format_rules": format_data.get("script_rules", []),
        "editorial_chapter_pattern": format_data.get("chapter_pattern", ""),
        "product_order": product_order,
        "segments_per_product": block_data.get("segments_per_product", []),
        "block_description": block_data.get("description", ""),
        "visual_direction": visual_data.get("dzine_direction", ""),
        "visual_description": visual_data.get("description", ""),
        "voice_wpm_target": pacing_data.get("wpm_target", 150),
        "voice_description": pacing_data.get("description", ""),
        "cta_line": cta_data.get("line", ""),
        "disclosure_text": disclosure_data.get("text", ""),
        "marketing_angle": angle_data.get("description", ""),
        "marketing_angle_prompt": angle_data.get("prompt_injection", ""),
    }

    # Inject category context if available
    if category_context["offer_characteristics"]:
        result["offer_context"] = category_context["offer_characteristics"]
    if category_context["customer_avatar"]:
        result["customer_avatar"] = category_context["customer_avatar"]
    if not category_context["offer_characteristics"] and not category_context["customer_avatar"]:
        result["category_context_fallback"] = category_context["fallback_prompt"]

    return result


def _build_youtube_ab_variants(selections: Dict[str, str], policy: Dict,
                               category: str, products: List[Dict]) -> Dict[str, Any]:
    """Generate A/B test variants for YouTube metadata.

    Inspired by Anthropic Growth Marketing's Google Ads creative generation:
    use the selected marketing angle + structure to produce multiple
    title/description variants for testing.
    """
    cat_display = category.replace("_", " ").title()
    year = dt.datetime.now().year

    angle_key = selections.get("marketing_angle", "value_hunter")
    angle_data = policy.get("marketing_angles", {}).get(angle_key, {})
    angle_label = angle_data.get("label", angle_key)

    opener_key = selections.get("opener_style", "overwhelm")
    structure_key = selections.get("structure_template", "classic_countdown")

    # Title variants — each under 70 chars for YouTube SEO
    title_templates = {
        "classic": f"Top 5 Best {cat_display} in {year}",
        "question": f"Which {cat_display.rstrip('s')} Should You Buy in {year}?",
        "number": f"5 {cat_display} Tested — Only 1 Worth Buying",
        "negative": f"Stop Buying Bad {cat_display} — Watch This First",
        "specific": f"I Tested 5 {cat_display} — Here's the Winner",
    }

    # Select 3 variants based on angle + opener
    variant_keys = list(title_templates.keys())
    # Bias toward variants that match the angle
    angle_title_affinities = {
        "value_hunter": ["classic", "number", "question"],
        "problem_solver": ["question", "negative", "specific"],
        "honest_disappointment": ["negative", "specific", "number"],
        "first_timer": ["question", "classic", "specific"],
        "spec_myth_buster": ["negative", "number", "specific"],
        "upgrade_path": ["question", "specific", "classic"],
        "gift_guide": ["classic", "question", "number"],
    }
    selected_keys = angle_title_affinities.get(angle_key, variant_keys[:3])

    title_variants = []
    for k in selected_keys:
        title = title_templates.get(k, title_templates["classic"])
        if len(title) <= 70:
            title_variants.append({"variant_id": k, "title": title})

    # Description intro variants
    desc_intros = {
        "direct": f"After testing 5 {cat_display.lower()} side by side, here are my honest rankings.",
        "problem": f"Choosing the right {cat_display.lower().rstrip('s')} shouldn't be this hard. I tested 5 so you don't have to.",
        "authority": f"Two weeks of real-world testing. 5 {cat_display.lower()}. One clear winner.",
    }

    return {
        "title_variants": title_variants,
        "description_intros": [
            {"variant_id": k, "text": v} for k, v in desc_intros.items()
        ],
        "angle_used": angle_key,
        "angle_label": angle_label,
        "note": "Use title_variants[0] as primary. Test others via YouTube A/B testing or community posts.",
    }


# ---------------------------------------------------------------------------
# Performance feedback (learning from past metrics)
# ---------------------------------------------------------------------------

def _fetch_local_run_metrics(lookback: int = 10) -> List[Dict]:
    """Scan past runs for metrics.json + variation_plan.json pairs.

    Returns list of {selections, metrics} dicts for runs that have both.
    """
    if not RUNS_DIR.exists():
        return []
    results = []
    run_dirs = sorted(RUNS_DIR.iterdir(), key=lambda d: d.stat().st_mtime, reverse=True)
    for run_dir in run_dirs:
        if not run_dir.is_dir():
            continue
        vp = run_dir / "variation_plan.json"
        mp = run_dir / "metrics" / "metrics.json"
        if vp.exists() and mp.exists():
            try:
                vp_data = json.loads(vp.read_text(encoding="utf-8"))
                mp_data = json.loads(mp.read_text(encoding="utf-8"))
                view_count = mp_data.get("view_count", 0)
                like_count = mp_data.get("like_count", 0)
                if view_count > 0:
                    results.append({
                        "selections": vp_data.get("selections", {}),
                        "views": view_count,
                        "likes": like_count,
                        "engagement": like_count / max(view_count, 1),
                    })
            except (json.JSONDecodeError, OSError):
                continue
        if len(results) >= lookback:
            break
    return results


def compute_performance_bonus(candidate: Dict[str, str],
                              perf_history: List[Dict]) -> float:
    """Compute a bonus score (0.0-0.2) based on past performance.

    If a dimension value was used in a high-performing run,
    give it a small bonus. This creates a gentle bias toward
    what worked without killing diversity.
    """
    if not perf_history:
        return 0.0

    # Rank past runs by engagement rate
    sorted_runs = sorted(perf_history, key=lambda r: r.get("engagement", 0), reverse=True)
    top_quartile = sorted_runs[:max(1, len(sorted_runs) // 4)]

    bonus = 0.0
    matches = 0
    for dim, val in candidate.items():
        for run in top_quartile:
            if run.get("selections", {}).get(dim) == val:
                matches += 1
                break

    if candidate:
        # Scale: if all dims match top performers, bonus = 0.15
        bonus = (matches / len(candidate)) * 0.15

    return round(bonus, 4)


def _build_dzine_instructions(selections: Dict[str, str], policy: Dict) -> Dict[str, str]:
    """Build Dzine-specific instructions from selections."""
    dzine_prefs = policy.get("dzine_model_preferences", {})
    visual_key = selections.get("visual_style", "clean_studio")

    return {
        "primary_model": dzine_prefs.get("product_photography", {}).get("model", "Seedream 5.0"),
        "avatar_model": dzine_prefs.get("avatar_creative", {}).get("model", "NanoBanana Pro"),
        "style_direction": visual_key,
    }


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_variation_plan(run_id: str, category: str, products: List[Dict],
                         force_overrides: Optional[Dict[str, str]] = None) -> Dict:
    """Build a complete variation plan for a pipeline run.

    Returns a dict suitable for writing to variation_plan.json.
    """
    policy = load_policy()
    constraints = policy.get("constraints", {})
    lookback = constraints.get("lookback_runs", 10)

    history = _get_history(lookback)
    perf_history = _fetch_local_run_metrics(lookback)

    # Seed RNG for reproducibility within a run
    seed = _deterministic_seed(run_id, category)
    random.seed(seed)

    selections, score = select_variation(
        policy, history, category, force_overrides, perf_history=perf_history,
    )

    # If score is below minimum, try harder with more attempts
    min_score = constraints.get("min_variation_score", 0.6)
    if score < min_score and not force_overrides:
        random.seed(seed + 1)
        for extra_attempt in range(100):
            selections2, score2 = select_variation(
                policy, history, category, perf_history=perf_history,
            )
            if score2 > score:
                selections = selections2
                score = score2
            if score >= min_score:
                break

    prompt_instructions = _build_prompt_instructions(selections, policy, products, category)
    dzine_instructions = _build_dzine_instructions(selections, policy)
    youtube_ab = _build_youtube_ab_variants(selections, policy, category, products)

    plan = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "category": category,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "variation_score": score,
        "selections": selections,
        "prompt_instructions": prompt_instructions,
        "dzine_instructions": dzine_instructions,
        "youtube_ab_variants": youtube_ab,
    }

    if perf_history:
        plan["performance_feedback"] = {
            "runs_with_metrics": len(perf_history),
            "note": "variation_score includes performance bonus from past metrics",
        }

    return plan


def plan_variations(run_id: str, category: str, products: List[Dict],
                    force_overrides: Optional[Dict[str, str]] = None) -> Dict:
    """Public alias for build_variation_plan."""
    return build_variation_plan(run_id, category, products, force_overrides)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Variation Planner — generate variation_plan.json")
    parser.add_argument("--run-id", required=True, help="Pipeline run ID")
    parser.add_argument("--category", required=True, help="Product category")
    parser.add_argument("--products", default="", help="Path to products.json (optional)")
    parser.add_argument("--output", default="", help="Output path (default: stdout)")
    args = parser.parse_args()

    products = []
    if args.products:
        p = Path(args.products)
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            products = data.get("products", data if isinstance(data, list) else [])

    plan = plan_variations(args.run_id, args.category, products)

    output = json.dumps(plan, indent=2, ensure_ascii=False)
    if args.output:
        out_path = Path(args.output)
        tmp = out_path.with_suffix(".tmp")
        payload = (output + "\n").encode("utf-8")
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        try:
            os.write(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(str(tmp), str(out_path))
        print(f"[OK] variation_plan.json written to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
