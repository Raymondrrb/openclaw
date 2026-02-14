"""Buyer-trust scoring and verification for the Rayviews pipeline.

Optimized for an older (30-65+), conversion-driven audience that values
trust, reliability, and low-regret decisions over novelty or hype.

Provides:
    - EvidenceRow: structured claim with source attribution + confidence
    - RegretScore: multi-factor regret risk assessment
    - ScoreCard: full product scoring card for transparency
    - PublishReadiness: pre-publish QA gate checklist
    - confidence_tag(): classify claim confidence level
    - regret_score(): calculate regret risk from product evidence
    - publish_readiness_check(): validate video is ready to publish
    - target_audience_text(): generate "who this is for" from evidence

Stdlib only — no external deps.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Evidence confidence levels
# ---------------------------------------------------------------------------

CONFIDENCE_MEASURED = "measured"      # lab test, benchmark, specific number
CONFIDENCE_EDITORIAL = "editorial"    # expert opinion, subjective assessment
CONFIDENCE_USER = "user_reported"     # Amazon reviews, user feedback

_MEASURED_SIGNALS = re.compile(
    r"\b(\d+\.?\d*)\s*(dB|hours?|mAh|mm|Hz|ms|watts?|W|grams?|g|percent|%|minutes?|seconds?|feet|ft|inches?|in)\b"
    r"|\b(measured|tested|scored|rated\s+\d|benchmark|lab\s+test)\b",
    re.IGNORECASE,
)

_USER_SIGNALS = re.compile(
    r"\b(users?\s+report|owners?\s+say|customers?\s+complain|amazon\s+reviews?"
    r"|user\s+feedback|complaints?\s+about|many\s+buyers|some\s+users|most\s+owners)\b",
    re.IGNORECASE,
)


def confidence_tag(claim: str) -> str:
    """Classify a claim's confidence level based on its language.

    Returns one of: "measured", "editorial", "user_reported".
    """
    if _MEASURED_SIGNALS.search(claim):
        return CONFIDENCE_MEASURED
    if _USER_SIGNALS.search(claim):
        return CONFIDENCE_USER
    return CONFIDENCE_EDITORIAL


# ---------------------------------------------------------------------------
# Structured evidence
# ---------------------------------------------------------------------------


@dataclass
class EvidenceRow:
    """One piece of evidence for a product, with source attribution."""
    claim: str
    source: str                    # "Wirecutter", "RTINGS", "PCMag"
    source_url: str = ""
    confidence: str = ""           # measured / editorial / user_reported
    category_label: str = ""       # "best overall", "best budget", etc.

    def __post_init__(self):
        if not self.confidence:
            self.confidence = confidence_tag(self.claim)


# ---------------------------------------------------------------------------
# Regret scoring
# ---------------------------------------------------------------------------


@dataclass
class RegretScore:
    """Multi-factor regret risk assessment for a product.

    Lower score = lower regret risk = safer recommendation.
    Factors that INCREASE regret risk (bad):
        - Few sources recommending it
        - No downside disclosed (hides risk)
        - No warranty/return signal
        - Extreme price (too cheap = disposable, too expensive = buyer's remorse)
        - Low evidence confidence (all editorial, no measured claims)
    """
    source_count_penalty: float = 0.0    # 0=2+ sources, 2=single source
    downside_penalty: float = 0.0         # 0=has downside, 3=none disclosed
    warranty_penalty: float = 0.0         # 0=warranty mentioned, 1=unknown
    price_extreme_penalty: float = 0.0    # 0=mid-range, 2=extreme
    evidence_quality_penalty: float = 0.0  # 0=has measured, 1=all editorial
    total: float = 0.0

    def __post_init__(self):
        self.total = (
            self.source_count_penalty
            + self.downside_penalty
            + self.warranty_penalty
            + self.price_extreme_penalty
            + self.evidence_quality_penalty
        )


_WARRANTY_SIGNALS = re.compile(
    r"\b(warranty|year\s+guarantee|return\s+polic|money.?back|refund|replacement"
    r"|\d+.?year|limited\s+warranty|manufacturer\s+warranty|coverage)\b",
    re.IGNORECASE,
)


def _has_warranty_signal(product: dict) -> bool:
    """Check if any evidence mentions warranty or return policy."""
    for ev in product.get("evidence", []):
        for reason in ev.get("reasons", []):
            if _WARRANTY_SIGNALS.search(reason):
                return True
    for claim in product.get("key_claims", []):
        if _WARRANTY_SIGNALS.search(claim):
            return True
    return False


def _extract_price_float(price_str: str) -> float | None:
    """Extract numeric price from a string like '$149.99'."""
    if not price_str:
        return None
    m = re.search(r'[\d,]+\.?\d*', price_str.replace(",", ""))
    if m:
        try:
            return float(m.group())
        except ValueError:
            return None
    return None


def _evidence_has_measured(product: dict) -> bool:
    """Check if any evidence claim has measured/tested data."""
    for ev in product.get("evidence", []):
        for reason in ev.get("reasons", []):
            if confidence_tag(reason) == CONFIDENCE_MEASURED:
                return True
    for claim in product.get("key_claims", []):
        if confidence_tag(claim) == CONFIDENCE_MEASURED:
            return True
    return False


def regret_score(product: dict) -> RegretScore:
    """Calculate regret risk for a product.

    Used as a penalty in ranking — products with higher regret risk
    get scored down, making the final Top 5 safer recommendations.
    """
    rs = RegretScore()

    # Source count: 2+ sources = 0 penalty, 1 source = 2.0 penalty
    source_count = len(product.get("evidence", []))
    if source_count < 2:
        rs.source_count_penalty = 2.0

    # Downside: no disclosed downside = 3.0 penalty (trust killer)
    downside = product.get("downside", "")
    _downside_kws = (
        "downside", "drawback", "however", "unfortunately",
        "complaint", "but", "con:", "weakness",
    )
    if not downside:
        # Check key_claims first
        for claim in product.get("key_claims", []):
            if any(kw in claim.lower() for kw in _downside_kws):
                downside = claim
                break
    if not downside:
        # Check evidence reasons
        for ev in product.get("evidence", []):
            for reason in ev.get("reasons", []):
                if any(kw in reason.lower() for kw in _downside_kws):
                    downside = reason
                    break
            if downside:
                break
    if not downside:
        rs.downside_penalty = 3.0

    # Warranty: no warranty signal = 1.0 penalty
    if not _has_warranty_signal(product):
        rs.warranty_penalty = 1.0

    # Price extremes: <$30 or >$500 = 2.0 penalty, $30-50 or $300-500 = 1.0
    price = _extract_price_float(product.get("amazon_price", "") or product.get("price", ""))
    if price is not None:
        if price < 30 or price > 500:
            rs.price_extreme_penalty = 2.0
        elif price < 50 or price > 300:
            rs.price_extreme_penalty = 1.0

    # Evidence quality: all editorial (no measured) = 1.0 penalty
    if not _evidence_has_measured(product):
        rs.evidence_quality_penalty = 1.0

    # Recalculate total
    rs.total = (
        rs.source_count_penalty
        + rs.downside_penalty
        + rs.warranty_penalty
        + rs.price_extreme_penalty
        + rs.evidence_quality_penalty
    )
    return rs


# ---------------------------------------------------------------------------
# ScoreCard (transparency output)
# ---------------------------------------------------------------------------


@dataclass
class ScoreCard:
    """Full scoring card for a product — written to products.json for transparency."""
    evidence_score: float = 0.0
    confidence_score: float = 0.0
    price_score: float = 0.0
    reviews_score: float = 0.0
    regret_penalty: float = 0.0
    total: float = 0.0
    regret_detail: RegretScore | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "evidence": round(self.evidence_score, 1),
            "confidence": round(self.confidence_score, 1),
            "price": round(self.price_score, 1),
            "reviews": round(self.reviews_score, 1),
            "regret_penalty": round(self.regret_penalty, 1),
            "total": round(self.total, 1),
        }
        if self.regret_detail:
            d["regret_breakdown"] = {
                "source_count": round(self.regret_detail.source_count_penalty, 1),
                "no_downside": round(self.regret_detail.downside_penalty, 1),
                "no_warranty": round(self.regret_detail.warranty_penalty, 1),
                "price_extreme": round(self.regret_detail.price_extreme_penalty, 1),
                "evidence_quality": round(self.regret_detail.evidence_quality_penalty, 1),
            }
        return d


# ---------------------------------------------------------------------------
# Target audience generation
# ---------------------------------------------------------------------------


def target_audience_text(product: dict, label: str) -> str:
    """Generate a 'who this is for' sentence from evidence + positioning.

    Speaks to the older (30-65+) audience: practical, specific, no jargon.
    """
    claims_lower = " ".join(product.get("key_claims", [])).lower()
    price = _extract_price_float(
        product.get("amazon_price", "") or product.get("price", "")
    )

    if label == "No-Regret Pick":
        return "For anyone who wants a reliable, well-reviewed option without overthinking it."

    if label == "Best Value":
        if price and price < 80:
            return "For budget-conscious buyers who want solid performance without paying premium prices."
        return "For buyers who want the best balance of quality and price."

    if label == "Best Upgrade":
        return "For buyers who are ready to invest more for noticeably better quality and durability."

    if label == "Best for Specific Scenario":
        # Extract the scenario from claims
        for kw, desc in [
            ("travel", "frequent travelers who need something portable and durable"),
            ("gaming", "gamers who need low latency and immersive sound"),
            ("calls", "remote workers who spend hours on video calls"),
            ("office", "professionals who need focus and comfort for long work sessions"),
            ("running", "active users who need a secure, sweat-resistant fit"),
            ("commute", "commuters who need solid noise isolation on the go"),
            ("small rooms", "buyers with smaller spaces who want room-filling sound"),
            ("large rooms", "buyers with larger spaces who need powerful coverage"),
        ]:
            if kw in claims_lower:
                return f"For {desc}."

        return "For buyers with a specific use case who need the right tool for the job."

    return "For buyers who want a solid alternative if the top picks don't match their needs."


# ---------------------------------------------------------------------------
# Publish readiness checklist
# ---------------------------------------------------------------------------


@dataclass
class CheckItem:
    """One item in the publish readiness checklist."""
    name: str
    passed: bool
    detail: str = ""


@dataclass
class PublishReadiness:
    """Pre-publish QA gate result."""
    checks: list[CheckItem] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> list[CheckItem]:
        return [c for c in self.checks if not c.passed]

    def summary(self) -> str:
        total = len(self.checks)
        passed = sum(1 for c in self.checks if c.passed)
        verdict = "READY" if self.passed else "NOT READY"
        lines = [f"Publish Readiness: {verdict} ({passed}/{total} checks passed)"]
        for c in self.checks:
            status = "PASS" if c.passed else "FAIL"
            detail = f" — {c.detail}" if c.detail else ""
            lines.append(f"  [{status}] {c.name}{detail}")
        return "\n".join(lines)


def publish_readiness_check(
    video_dir: Path,
    *,
    products_data: dict | None = None,
    script_text: str = "",
) -> PublishReadiness:
    """Run the pre-publish QA gate.

    Checks all artifacts exist and meet quality standards.
    """
    result = PublishReadiness()

    # 1. products.json exists and has 4-5 products
    products_path = video_dir / "inputs" / "products.json"
    if products_data is None and products_path.is_file():
        products_data = json.loads(products_path.read_text(encoding="utf-8"))

    if products_data:
        products = products_data.get("products", [])
        count = len(products)
        result.checks.append(CheckItem(
            "Products (4-5)",
            4 <= count <= 5,
            f"{count} products",
        ))

        # 2. Every product has an affiliate link
        missing_links = [p["name"] for p in products if not p.get("affiliate_url")]
        result.checks.append(CheckItem(
            "Affiliate links",
            len(missing_links) == 0,
            f"Missing: {', '.join(missing_links[:3])}" if missing_links else "All present",
        ))

        # 3. Every product has an honest downside
        missing_downside = [p["name"] for p in products if not p.get("downside")]
        result.checks.append(CheckItem(
            "Honest downsides",
            len(missing_downside) == 0,
            f"Missing: {', '.join(missing_downside[:3])}" if missing_downside else "All present",
        ))

        # 4. Every product has buy_this_if / avoid_this_if
        missing_buy = [p["name"] for p in products if not p.get("buy_this_if")]
        result.checks.append(CheckItem(
            "Buy/avoid guidance",
            len(missing_buy) == 0,
            f"Missing: {', '.join(missing_buy[:3])}" if missing_buy else "All present",
        ))

        # 5. Evidence from 2+ sources overall
        all_sources = set()
        for p in products:
            for ev in p.get("evidence", []):
                all_sources.add(ev.get("source", ""))
        result.checks.append(CheckItem(
            "Multi-source evidence",
            len(all_sources) >= 2,
            f"{len(all_sources)} sources: {', '.join(sorted(all_sources))}",
        ))
    else:
        result.checks.append(CheckItem("Products file", False, "products.json missing"))

    # 6. Script exists and has correct word count
    script_path = video_dir / "script" / "script.txt"
    if not script_text and script_path.is_file():
        script_text = script_path.read_text(encoding="utf-8")

    if script_text:
        word_count = len(script_text.split())
        result.checks.append(CheckItem(
            "Script word count",
            1150 <= word_count <= 1800,
            f"{word_count} words",
        ))

        # 7. FTC disclosure present
        lower = script_text.lower()
        has_disclosure = "affiliate" in lower and "commission" in lower
        result.checks.append(CheckItem(
            "FTC disclosure",
            has_disclosure,
            "Present" if has_disclosure else "Missing affiliate/commission keywords",
        ))

        # 8. No hype words
        hype_words = {
            "insane", "crazy", "unbelievable", "mind-blowing", "game-changer",
            "jaw-dropping", "revolutionary", "groundbreaking",
        }
        found_hype = [w for w in hype_words if w in lower]
        result.checks.append(CheckItem(
            "No hype words",
            len(found_hype) == 0,
            f"Found: {', '.join(found_hype)}" if found_hype else "Clean",
        ))
    else:
        result.checks.append(CheckItem("Script", False, "script.txt missing"))

    # 9. Audio chunks exist
    chunks_dir = video_dir / "audio" / "chunks"
    if chunks_dir.is_dir():
        chunks = list(chunks_dir.glob("*.mp3"))
        result.checks.append(CheckItem(
            "Audio chunks",
            len(chunks) >= 3,
            f"{len(chunks)} chunks",
        ))
    else:
        result.checks.append(CheckItem("Audio chunks", False, "chunks directory missing"))

    # 10. Thumbnail exists
    thumb = video_dir / "assets" / "thumbnail.png"
    if not thumb.is_file():
        thumb = video_dir / "assets" / "thumbnail.jpg"
    result.checks.append(CheckItem(
        "Thumbnail",
        thumb.is_file() and thumb.stat().st_size > 50 * 1024,
        "Present" if thumb.is_file() else "Missing",
    ))

    return result
