#!/usr/bin/env python3
"""RayVault Claims Guardrail — anti-lie firewall for script claims.

Checks if the script contains commercial claims not supported by Amazon
product text (title, bullets, description). Prevents brand-damaging
fabrications from reaching published videos.

Golden rule: if script says it, Amazon page must say it too.

Usage:
    python3 -m rayvault.claims_guardrail --run-dir state/runs/RUN_2026_02_14_A

Output:
    - claims_guardrail.json in run_dir
    - Updates 00_manifest.json with claims_validation block

Exit codes:
    0: PASS (no unsubstantiated claims)
    1: runtime error
    2: REVIEW_REQUIRED (violations found) or missing inputs
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rayvault.io import atomic_write_json, read_json, utc_now_iso

# ---------------------------------------------------------------------------
# Trigger patterns (high-risk commercial claims)
# ---------------------------------------------------------------------------

TRIGGER_PATTERNS = [
    r"\bwaterproof\b",
    r"\bwater[- ]?resistant\b",
    r"\blifetime warranty\b",
    r"\bgarantia vital[ií]cia\b",
    r"\b\d+\s*h(ours?)?\b",
    r"\bbatter(y|ia)\b",
    r"\bmedical\b",
    r"\bclinically\b",
    r"\bcertified\b",
    r"\bcertificado\b",
    r"\b100%\b",
    r"\brisk[- ]?free\b",
    r"\bsem risco\b",
    r"\bbest\b",
    r"\bmelhor\b",
    r"\bnumber one\b",
    r"\bfda\b",
    r"\bpatented\b",
    r"\bpatenteado\b",
]

# Claim category -> required evidence keywords in Amazon text
CLAIM_EVIDENCE_RULES: List[Tuple[str, List[str]]] = [
    ("waterproof", ["waterproof", "ipx", "water-resistant", "water resistant"]),
    ("battery_life", ["battery", "bateria", "hours", "horas", "mah"]),
    ("warranty", ["warranty", "garantia"]),
    ("certification", ["certified", "certificado", "fda", "ce", "ul"]),
    ("medical", ["medical", "clinical", "clinically"]),
    ("patented", ["patented", "patent", "patenteado"]),
]

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


# ---------------------------------------------------------------------------
# Product text extraction
# ---------------------------------------------------------------------------


def load_products(products_json: Path) -> List[Dict[str, Any]]:
    data = read_json(products_json)
    items = data.get("items", [])
    def _rank(x: Dict[str, Any]) -> int:
        try:
            return int(x.get("rank", 99))
        except (ValueError, TypeError):
            return 99
    return sorted(items, key=_rank)


def collect_allowed_text(product: Dict[str, Any]) -> str:
    """Build corpus of allowed text from Amazon product data."""
    parts = []
    for key in ("title", "description"):
        val = product.get(key)
        if val:
            parts.append(str(val))
    bullets = product.get("bullets") or product.get("bullet_points") or []
    parts.extend(str(b) for b in bullets if b)
    # Include claims_allowed if present
    allowed = product.get("claims_allowed") or []
    parts.extend(str(c) for c in allowed if c)
    return normalize_text(" ".join(parts))


# ---------------------------------------------------------------------------
# Claim detection
# ---------------------------------------------------------------------------


def find_trigger_sentences(script: str) -> List[str]:
    """Split script into sentences and return those matching trigger patterns."""
    raw = re.split(r"(?<=[\.\!\?])\s+", script.strip())
    hits = []
    for sent in raw:
        s = sent.lower()
        if any(re.search(pat, s, flags=re.IGNORECASE) for pat in TRIGGER_PATTERNS):
            hits.append(sent.strip())
    return hits


def check_evidence(
    sentence: str, allowed_text: str
) -> Tuple[bool, List[str]]:
    """Check if a trigger sentence has supporting evidence in allowed text.

    Returns (ok, missing_claims).
    """
    s = normalize_text(sentence)
    missing = []
    matched_any_rule = False

    for claim_name, evidence_keywords in CLAIM_EVIDENCE_RULES:
        # Check if this claim category is relevant to the sentence
        if not any(kw in s for kw in evidence_keywords):
            continue
        matched_any_rule = True
        # Check if evidence exists in allowed text
        if not any(kw in allowed_text for kw in evidence_keywords):
            missing.append(claim_name)

    # Fallback: if no specific rule matched, do generic token overlap check
    if not matched_any_rule:
        tokens = [t for t in re.findall(r"[a-zA-Z\u00C0-\u024F0-9]{4,}", s)][:12]
        if tokens and not any(t in allowed_text for t in tokens):
            missing.append("unsubstantiated_sentence")

    return (len(missing) == 0), missing


# ---------------------------------------------------------------------------
# Core guardrail
# ---------------------------------------------------------------------------


def _load_cached_products(run_dir: Path) -> Optional[List[Dict[str, Any]]]:
    """Try to load product metadata from per-product cached files.

    These are written by product_asset_fetch when cache is enabled,
    providing a single source of truth for claims validation.
    """
    products_dir = run_dir / "products"
    if not products_dir.is_dir():
        return None
    product_dirs = sorted(
        [d for d in products_dir.iterdir() if d.is_dir() and d.name.startswith("p")],
        key=lambda d: d.name,
    )
    if not product_dirs:
        return None
    products = []
    for pd in product_dirs:
        # Prefer product_metadata.json (from cache), then product.json
        for fname in ("product_metadata.json", "product.json"):
            fp = pd / fname
            if fp.exists():
                try:
                    products.append(read_json(fp))
                except Exception:
                    pass
                break
    return products if products else None


def guardrail(run_dir: Path, use_cached_products: bool = True) -> Dict[str, Any]:
    """Run claims guardrail on a run directory.

    Args:
        run_dir: Run directory path
        use_cached_products: If True, prefer cached product metadata
            (from TruthCache materialization) over raw products.json

    Returns result dict with status PASS or REVIEW_REQUIRED.
    """
    script_path = run_dir / "01_script.txt"
    products_path = run_dir / "products" / "products.json"

    if not script_path.exists():
        return {
            "status": "ERROR",
            "code": "MISSING_SCRIPT",
            "violations": [],
            "trigger_sentences_count": 0,
            "products_count": 0,
        }

    # Try cached products first (single source of truth from TruthCache)
    products = None
    products_source = "products_json"
    if use_cached_products:
        products = _load_cached_products(run_dir)
        if products:
            products_source = "cached_metadata"

    # Fallback to products.json
    if not products:
        if not products_path.exists():
            return {
                "status": "ERROR",
                "code": "MISSING_PRODUCTS_JSON",
                "violations": [],
                "trigger_sentences_count": 0,
                "products_count": 0,
            }
        products = load_products(products_path)

    script = script_path.read_text(encoding="utf-8")

    # Build union of all allowed text across products
    allowed_union = " ".join(
        collect_allowed_text(p) for p in products
    )

    trigger_sents = find_trigger_sentences(script)
    violations = []

    for sent in trigger_sents:
        ok, missing = check_evidence(sent, allowed_union)
        if not ok:
            violations.append({
                "sentence": sent[:200],
                "missing_evidence": missing,
            })

    status = "PASS" if not violations else "REVIEW_REQUIRED"

    return {
        "status": status,
        "violations": violations,
        "trigger_sentences_count": len(trigger_sents),
        "products_count": len(products),
        "products_source": products_source,
        "checked_at_utc": utc_now_iso(),
    }


def update_manifest(run_dir: Path, result: Dict[str, Any]) -> None:
    """Write claims_validation block to manifest."""
    mpath = run_dir / "00_manifest.json"
    if not mpath.exists():
        return
    m = read_json(mpath)
    m["claims_validation"] = {
        "status": result.get("status", "ERROR"),
        "violations_count": len(result.get("violations", [])),
        "violations": result.get("violations", []),
        "at_utc": result.get("checked_at_utc", utc_now_iso()),
    }
    atomic_write_json(mpath, m)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description="RayVault Claims Guardrail — anti-lie firewall",
    )
    ap.add_argument("--run-dir", required=True)
    args = ap.parse_args(argv)

    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.exists():
        print(f"Run dir not found: {run_dir}", file=sys.stderr)
        return 2

    result = guardrail(run_dir)
    # Write result file
    atomic_write_json(run_dir / "claims_guardrail.json", result)
    # Update manifest
    update_manifest(run_dir, result)

    status = result["status"]
    n_violations = len(result.get("violations", []))
    n_triggers = result.get("trigger_sentences_count", 0)
    print(
        f"claims_guardrail: {status} | triggers={n_triggers} "
        f"| violations={n_violations}"
    )
    if n_violations > 0:
        for v in result["violations"][:5]:
            print(f"  - {v['sentence'][:80]}... [{', '.join(v['missing_evidence'])}]")

    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
