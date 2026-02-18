#!/usr/bin/env python3
"""Final Top 5 selection from verified Amazon products.

Applies scoring rules: evidence strength, category diversity,
Amazon listing quality. Outputs the ranked products.json.

Usage:
    python3 tools/top5_ranker.py --verified verified.json --video-id xyz
    python3 tools/top5_ranker.py --verified verified.json --niche "wireless earbuds"

Stdlib only — no external deps.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.common import now_iso, project_root

VIDEOS_BASE = project_root() / "artifacts" / "videos"

# ---------------------------------------------------------------------------
# Scoring weights
# ---------------------------------------------------------------------------

WEIGHT_EVIDENCE = 3.0       # number + quality of review sources
WEIGHT_CONFIDENCE = 2.0     # Amazon ASIN match confidence
WEIGHT_PRICE = 1.0          # prefer mid-to-premium range
WEIGHT_REVIEWS = 0.5        # Amazon review count as tiebreaker
WEIGHT_REGRET = 2.5         # regret risk penalty (subtracted from score)

# Buyer-centric labels (Rayviews ranking framework)
CATEGORY_SLOTS = [
    "No-Regret Pick",
    "Best Value",
    "Best Upgrade",
    "Best for Specific Scenario",
    "Best Alternative",
]


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _evidence_score(product: dict) -> float:
    """Score based on number and quality of review sources."""
    evidence = product.get("evidence", [])
    # Base: number of sources
    score = len(evidence) * 2.0
    # Bonus for Wirecutter and RTINGS (highest quality)
    for e in evidence:
        source = e.get("source", "")
        if "Wirecutter" in source:
            score += 2.0
        elif "RTINGS" in source:
            score += 1.5
    return score


def _confidence_score(product: dict) -> float:
    """Score based on Amazon match confidence."""
    conf = product.get("match_confidence", "low")
    return {"high": 3.0, "medium": 1.5, "low": 0.5}.get(conf, 0.5)


def _price_score(product: dict) -> float:
    """Score favoring $50-$300 range products."""
    price_str = product.get("amazon_price", "")
    if not price_str:
        return 1.0
    try:
        # Extract numeric price
        import re
        m = re.search(r'[\d,]+\.?\d*', price_str.replace(",", ""))
        if not m:
            return 1.0
        price = float(m.group())
        if 50 <= price <= 300:
            return 2.0
        elif 30 <= price < 50 or 300 < price <= 500:
            return 1.5
        elif price < 30:
            return 0.5  # impulse junk territory
        else:
            return 1.0  # expensive but ok
    except Exception:
        return 1.0


def _reviews_score(product: dict) -> float:
    """Tiebreaker score based on Amazon review count."""
    reviews = product.get("amazon_reviews", "")
    if not reviews:
        return 0.0
    try:
        count = int(reviews.replace(",", ""))
        if count > 10000:
            return 2.0
        elif count > 1000:
            return 1.5
        elif count > 100:
            return 1.0
        return 0.5
    except Exception:
        return 0.0


def _category_label(product: dict, rank: int = 0) -> str:
    """Assign a buyer-centric label based on claims, price, and rank position.

    Labels follow the Rayviews ranking framework:
    #1 No-Regret Pick, #2 Best Value, #3 Best Upgrade,
    #4 Best for Specific Scenario, #5 Best Alternative.
    """
    claims = product.get("key_claims", [])
    claims_lower = " ".join(claims).lower()

    # Rank-based defaults (most reliable signal)
    if rank == 1:
        return "No-Regret Pick"

    # Claims-based assignment
    if "best value" in claims_lower or "best bang for the buck" in claims_lower:
        return "Best Value"
    if "upgrade pick" in claims_lower or "best premium" in claims_lower or "best splurge" in claims_lower:
        return "Best Upgrade"

    # Price-based fallback
    price_str = product.get("amazon_price", "")
    try:
        import re
        m = re.search(r'[\d,]+\.?\d*', price_str.replace(",", ""))
        if m:
            price = float(m.group())
            if price > 250:
                return "Best Upgrade"
    except Exception:
        pass

    # Specific use-case claims
    for keyword in ("travel", "calls", "gaming", "running", "working out",
                     "music", "small rooms", "large rooms", "commute", "office"):
        if keyword in claims_lower:
            return "Best for Specific Scenario"

    # Default based on rank position
    rank_defaults = {
        2: "Best Value",
        3: "Best Upgrade",
        4: "Best for Specific Scenario",
        5: "Best Alternative",
    }
    return rank_defaults.get(rank, "Best Alternative")


def score_product(product: dict) -> float:
    """Calculate total score for ranking.

    Includes regret penalty: products that are risky recommendations
    (single source, no downside, no warranty info, price extremes)
    get penalized — making the final Top 5 safer for the audience.
    """
    from tools.lib.buyer_trust import regret_score

    base = (
        _evidence_score(product) * WEIGHT_EVIDENCE
        + _confidence_score(product) * WEIGHT_CONFIDENCE
        + _price_score(product) * WEIGHT_PRICE
        + _reviews_score(product) * WEIGHT_REVIEWS
    )
    rs = regret_score(product)
    return base - (rs.total * WEIGHT_REGRET)


# ---------------------------------------------------------------------------
# Top 5 selection
# ---------------------------------------------------------------------------


def select_top5(
    verified: list[dict],
    *,
    contract_path: Path | None = None,
) -> list[dict]:
    """Select the final Top 5 with category diversity.

    Returns products ranked 1 (best) to 5 (entry-level), with
    diversity across categories (best overall, budget, premium, etc.).

    If contract_path is provided, every product must pass the
    subcategory gate. Any drift is a hard reject — the product
    is removed before scoring.
    """
    # --- Subcategory gate: HARD reject any drifted product ---
    if contract_path and contract_path.is_file():
        from tools.lib.subcategory_contract import load_contract, passes_gate
        contract = load_contract(contract_path)
        clean = []
        for p in verified:
            ok, reason = passes_gate(
                p.get("product_name", ""), p.get("brand", ""), contract,
            )
            if ok:
                clean.append(p)
            else:
                print(f"  DRIFT REJECT (top5): {p.get('product_name', '?')} — {reason}",
                      file=sys.stderr)
        verified = clean

    if len(verified) <= 5:
        # Not enough to be picky — rank by score
        scored = sorted(verified, key=lambda p: -score_product(p))
        for i, p in enumerate(scored):
            p["rank"] = i + 1
            p["category_label"] = _category_label(p, rank=i + 1)
            p["total_score"] = round(score_product(p), 1)
        return scored

    # Score all products
    for p in verified:
        p["total_score"] = round(score_product(p), 1)

    scored = sorted(verified, key=lambda p: -p["total_score"])

    # Select top 5 by score
    selected = scored[:5]

    # Rank: #1 = highest score, #5 = most accessible
    selected.sort(key=lambda p: -p["total_score"])

    # Assign ranks and buyer-centric labels
    for i, p in enumerate(selected):
        p["rank"] = i + 1
        p["category_label"] = _category_label(p, rank=i + 1)

    # Brand diversity warning (informational, not hard fail)
    warning = _check_brand_diversity(selected)
    if warning:
        print(f"  WARNING: {warning}", file=sys.stderr)

    return selected[:5]


# ---------------------------------------------------------------------------
# Evidence → benefits/downside extraction
# ---------------------------------------------------------------------------


_DOWNSIDE_KEYWORDS = (
    "downside", "drawback", "weakness", "complaint", "lacking", "missing",
    "disappointing", "worse", "cons", "con:", "not great", "mediocre",
    "struggles", "falls short", "only complaint", "but it", "however",
    "unfortunately", "trade-off", "tradeoff",
)


def _extract_benefits(product: dict) -> list[str]:
    """Extract 2-3 benefits from evidence reasons/key_claims."""
    seen = set()
    benefits = []

    # First: key_claims from review sources
    for claim in product.get("key_claims", []):
        claim = claim.strip()
        if not claim or len(claim) < 10:
            continue
        # Skip downside-sounding claims
        if any(kw in claim.lower() for kw in _DOWNSIDE_KEYWORDS):
            continue
        key = claim.lower()[:40]
        if key not in seen:
            seen.add(key)
            benefits.append(claim)
        if len(benefits) >= 3:
            break

    # Second: reasons from evidence sources (attributed)
    if len(benefits) < 2:
        for src in product.get("evidence", []):
            source_name = src.get("source", src.get("name", ""))
            for reason in src.get("reasons", []):
                reason = reason.strip()
                if not reason or len(reason) < 10:
                    continue
                if any(kw in reason.lower() for kw in _DOWNSIDE_KEYWORDS):
                    continue
                key = reason.lower()[:40]
                if key not in seen:
                    seen.add(key)
                    benefits.append(reason)
                if len(benefits) >= 3:
                    break
            if len(benefits) >= 3:
                break

    return benefits[:3]


def _extract_downside(product: dict) -> str:
    """Extract an honest downside from evidence, if reviewers mentioned one."""
    # Pre-extracted downside from research
    ds = product.get("downside", "").strip()
    if ds:
        return ds

    for claim in product.get("key_claims", []):
        if any(kw in claim.lower() for kw in _DOWNSIDE_KEYWORDS):
            return claim.strip()

    for src in product.get("evidence", []):
        for reason in src.get("reasons", []):
            if any(kw in reason.lower() for kw in _DOWNSIDE_KEYWORDS):
                return reason.strip()

    return ""


def _build_buy_avoid(product: dict, label: str) -> tuple[str, str]:
    """Generate 'buy_this_if' / 'avoid_this_if' from evidence and positioning."""
    benefits = _extract_benefits(product)
    downside = _extract_downside(product)
    claims_lower = " ".join(product.get("key_claims", [])).lower()

    # Build "buy this if" from top benefit + positioning
    buy_parts = []
    if label == "No-Regret Pick":
        buy_parts.append("you want the safest, most recommended option")
    elif label == "Best Value":
        buy_parts.append("you want the best performance per dollar")
    elif label == "Best Upgrade":
        buy_parts.append("you're willing to pay more for premium features")
    elif label == "Best for Specific Scenario":
        # Try to extract the specific scenario from claims
        for kw in ("travel", "gaming", "office", "commute", "small rooms",
                    "large rooms", "running", "calls"):
            if kw in claims_lower:
                buy_parts.append(f"your primary use is {kw}")
                break
        else:
            buy_parts.append("you have a specific use case in mind")
    else:
        buy_parts.append("the top picks don't fit your needs")

    if benefits:
        buy_parts.append(benefits[0].lower().rstrip("."))

    buy_this_if = " and ".join(buy_parts[:2])

    # Build "avoid this if" from downside
    if downside:
        avoid_this_if = downside.lower().rstrip(".")
    elif label == "Best Upgrade":
        avoid_this_if = "you're on a tight budget"
    elif label == "Best Value":
        avoid_this_if = "you need premium features"
    else:
        avoid_this_if = "check the downside section for trade-offs"

    return buy_this_if, avoid_this_if


def _check_brand_diversity(top5: list[dict]) -> str | None:
    """Warn if 3+ of 5 products share a brand. Not a hard fail."""
    from collections import Counter
    brands = [p.get("brand", "").lower().strip() for p in top5 if p.get("brand")]
    counts = Counter(brands)
    for brand, count in counts.most_common(1):
        if count >= 3:
            return f"Brand concentration warning: {brand} appears {count}/5 times"
    return None


# ---------------------------------------------------------------------------
# Output: products.json
# ---------------------------------------------------------------------------


def write_products_json(
    top5: list[dict],
    niche: str,
    output_path: Path,
    *,
    video_id: str = "",
    date: str = "",
) -> None:
    """Write the final ranked products.json for the pipeline."""
    from tools.lib.buyer_trust import (
        ScoreCard, regret_score, target_audience_text,
        confidence_tag,
    )

    products_out = []
    for p in sorted(top5, key=lambda x: -x.get("rank", 0)):  # 5 down to 1
        # Extract benefits from evidence reasons (real review data)
        benefits = _extract_benefits(p)
        # Extract downside from evidence (if reviewers mentioned one)
        downside = _extract_downside(p)
        # Build buy/avoid guidance
        label = p.get("category_label", "")
        buy_this_if, avoid_this_if = _build_buy_avoid(p, label)

        # Build scorecard with regret penalty for transparency
        rs = regret_score(p)
        card = ScoreCard(
            evidence_score=round(_evidence_score(p) * WEIGHT_EVIDENCE, 1),
            confidence_score=round(_confidence_score(p) * WEIGHT_CONFIDENCE, 1),
            price_score=round(_price_score(p) * WEIGHT_PRICE, 1),
            reviews_score=round(_reviews_score(p) * WEIGHT_REVIEWS, 1),
            regret_penalty=round(rs.total * WEIGHT_REGRET, 1),
            total=round(score_product(p), 1),
            regret_detail=rs,
        )

        # Tag evidence claims with confidence levels
        tagged_evidence = []
        for ev in p.get("evidence", []):
            tagged_reasons = []
            for reason in ev.get("reasons", []):
                tagged_reasons.append({
                    "text": reason,
                    "confidence": confidence_tag(reason),
                })
            tagged_ev = dict(ev)
            tagged_ev["tagged_reasons"] = tagged_reasons
            tagged_evidence.append(tagged_ev)

        products_out.append({
            "rank": p.get("rank", 0),
            "name": p.get("product_name", ""),
            "brand": p.get("brand", ""),
            "asin": p.get("asin", ""),
            "amazon_url": p.get("amazon_url", ""),
            "affiliate_url": p.get("affiliate_short_url") or p.get("affiliate_url", ""),
            "price": p.get("amazon_price", ""),
            "rating": p.get("amazon_rating", ""),
            "reviews_count": p.get("amazon_reviews", ""),
            "image_url": p.get("amazon_image_url", ""),
            "positioning": p.get("category_label", ""),
            "benefits": benefits,
            "target_audience": target_audience_text(p, label),
            "downside": downside,
            "buy_this_if": buy_this_if,
            "avoid_this_if": avoid_this_if,
            "evidence": tagged_evidence,
            "key_claims": p.get("key_claims", []),
            "scorecard": card.to_dict(),
        })

    wrapper = {
        "video_id": video_id,
        "date": date or now_iso()[:10],
        "niche": niche,
        "keyword": niche,
        "generated_at": now_iso(),
        "products": products_out,
        "sources_used": list({
            s.get("source", "")
            for p in top5
            for s in p.get("evidence", [])
        }),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(wrapper, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def load_verified(path: Path) -> list[dict]:
    """Load verified products JSON."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("products", data if isinstance(data, list) else [])


def main() -> int:
    parser = argparse.ArgumentParser(description="Top 5 product ranker")
    parser.add_argument("--verified", required=True, help="Path to verified.json")
    parser.add_argument("--niche", default="", help="Product niche")
    parser.add_argument("--video-id", default="", help="Video ID")
    parser.add_argument("--output", default="", help="Output path for products.json")
    args = parser.parse_args()

    verified = load_verified(Path(args.verified))
    if not verified:
        print("No verified products", file=sys.stderr)
        return 1

    print(f"Verified products: {len(verified)}")

    # Load subcategory contract if available
    contract_path = None
    if args.video_id:
        cp = VIDEOS_BASE / args.video_id / "inputs" / "subcategory_contract.json"
        if cp.is_file():
            contract_path = cp

    top5 = select_top5(verified, contract_path=contract_path)

    print(f"\nTop 5 ({args.niche or 'unknown niche'}):\n")
    for p in top5:
        print(f"  #{p['rank']} {p.get('product_name', '?'):<45s} "
              f"[{p.get('category_label', '?')}] "
              f"score={p.get('total_score', 0):.1f} "
              f"conf={p.get('match_confidence', '?')}")

    # Write output
    if args.video_id:
        output_path = VIDEOS_BASE / args.video_id / "inputs" / "products.json"
    elif args.output:
        output_path = Path(args.output)
    else:
        output_path = project_root() / "data" / "products.json"

    niche = args.niche
    if not niche and args.video_id:
        niche_path = VIDEOS_BASE / args.video_id / "inputs" / "niche.txt"
        if niche_path.is_file():
            niche = niche_path.read_text(encoding="utf-8").strip()

    write_products_json(top5, niche, output_path, video_id=args.video_id)
    print(f"\nWrote {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
