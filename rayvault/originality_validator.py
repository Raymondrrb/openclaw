#!/usr/bin/env python3
"""RayVault Originality Validator.

Quality-first anti-inauthentic checks for scripts before Gate 2.

Outputs:
  - originality_report.json
  - optional manifest patch with originality block

Exit codes:
  0 OK
  1 WARN
  2 FAIL
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from rayvault.io import atomic_write_json, read_json, utc_now_iso

DEFAULT_POLICY: Dict[str, Any] = {
    "min_script_uniqueness_score_ok": 0.72,
    "min_script_uniqueness_score_fail": 0.58,
    "max_template_phrase_hits_ok": 6,
    "max_template_phrase_hits_fail": 12,
    "min_products_with_evidence_ok": 5,
    "min_products_with_evidence_fail": 4,
    "min_evidence_segments_per_product": 1,
    "min_opinion_density_ok": 0.12,
    "min_opinion_density_fail": 0.08,
    "min_contraindication_sentences_ok": 5,
    "min_contraindication_sentences_fail": 3,
    "ngram_size": 3,
}

TEMPLATE_PHRASE_BLACKLIST = [
    "this one is great for",
    "if you are looking for",
    "at the end of the day",
    "without further ado",
    "let's dive in",
    "game changer",
    "packed with features",
    "sleek design",
    "best bang for your buck",
    "takes it to the next level",
]

EVIDENCE_KEYWORDS = {
    "because",
    "compared",
    "versus",
    "vs",
    "test",
    "tested",
    "measurement",
    "rating",
    "review",
    "trade-off",
    "tradeoff",
    "however",
    "but",
    "warranty",
    "latency",
    "battery",
}

OPINION_MARKERS = {
    "i think",
    "i found",
    "i noticed",
    "in my test",
    "in my usage",
    "my take",
    "in my opinion",
}

CONTRA_MARKERS = {
    "not for",
    "skip if",
    "if you don't",
    "if you do not",
    "who should not buy",
    "avoid this if",
}


def _normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", (s or "").lower())).strip()


def _split_sentences(text: str) -> List[str]:
    raw = re.split(r"(?<=[\.\!\?])\s+", text.strip())
    return [s.strip() for s in raw if s.strip()]


def _extract_script_rows(script: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for seg in script.get("structure", []):
        seg_id = str(seg.get("id", ""))
        seg_type = str(seg.get("type", ""))
        rank = seg.get("product_rank")
        role = str(seg.get("role", "")).strip().lower()
        voice = str(seg.get("voice_text", "")).strip()
        if voice:
            rows.append(
                {
                    "segment_id": seg_id,
                    "segment_type": seg_type,
                    "product_rank": rank,
                    "role": role,
                    "voice_text": voice,
                }
            )
        for i, sub in enumerate(seg.get("segments", []), start=1):
            sub_voice = str(sub.get("voice_text", "")).strip()
            if not sub_voice:
                continue
            rows.append(
                {
                    "segment_id": f"{seg_id}::{i}",
                    "segment_type": str(sub.get("kind", "")),
                    "product_rank": rank,
                    "role": str(sub.get("role", role)).strip().lower(),
                    "voice_text": sub_voice,
                }
            )
    return rows


def _compute_uniqueness(rows: List[Dict[str, Any]], ngram_size: int) -> Dict[str, Any]:
    texts = [_normalize_text(r.get("voice_text", "")) for r in rows if r.get("voice_text")]
    tokens: List[str] = []
    for t in texts:
        tokens.extend([w for w in t.split() if w])
    n = max(2, int(ngram_size or 3))
    ngrams: List[str] = []
    for i in range(0, max(0, len(tokens) - n + 1)):
        ngrams.append(" ".join(tokens[i : i + n]))
    if not ngrams:
        return {"score": 0.0, "total_ngrams": 0, "repeated_ngrams": 0}
    counts: Dict[str, int] = {}
    for ng in ngrams:
        counts[ng] = counts.get(ng, 0) + 1
    repeated = sum(v - 1 for v in counts.values() if v > 1)
    ratio = repeated / max(len(ngrams), 1)
    score = max(0.0, min(1.0, 1.0 - ratio * 1.8))
    return {
        "score": round(score, 4),
        "total_ngrams": len(ngrams),
        "repeated_ngrams": int(repeated),
        "repeated_ratio": round(ratio, 4),
    }


def _compute_template_hits(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    hits: List[Dict[str, Any]] = []
    for r in rows:
        t = _normalize_text(r.get("voice_text", ""))
        for phrase in TEMPLATE_PHRASE_BLACKLIST:
            if phrase in t:
                hits.append({"segment_id": r.get("segment_id", ""), "phrase": phrase})
    return {"count": len(hits), "hits": hits[:50]}


def _is_evidence_row(row: Dict[str, Any]) -> bool:
    role = str(row.get("role", "")).lower()
    if role == "evidence":
        return True
    t = _normalize_text(str(row.get("voice_text", "")))
    if any(k in t for k in EVIDENCE_KEYWORDS):
        return True
    if re.search(r"\b\d+(\.\d+)?(%|ms|hz|mah|hours?|h)\b", t):
        return True
    return False


def _compute_evidence(rows: List[Dict[str, Any]], products: List[Dict[str, Any]]) -> Dict[str, Any]:
    expected_ranks = []
    for p in products:
        try:
            expected_ranks.append(int(p.get("rank")))
        except Exception:
            continue
    if not expected_ranks:
        expected_ranks = [1, 2, 3, 4, 5]

    per_product: Dict[int, int] = {r: 0 for r in expected_ranks}
    for r in rows:
        rank = r.get("product_rank")
        if rank is None:
            continue
        try:
            rank_i = int(rank)
        except Exception:
            continue
        if rank_i not in per_product:
            continue
        if _is_evidence_row(r):
            per_product[rank_i] += 1

    with_evidence = sum(1 for _, c in per_product.items() if c > 0)
    return {
        "per_product": {str(k): int(v) for k, v in sorted(per_product.items())},
        "products_with_evidence": with_evidence,
        "products_total": len(per_product),
    }


def _compute_opinion_density(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    all_text = "\n".join(str(r.get("voice_text", "")) for r in rows)
    sents = _split_sentences(all_text)
    if not sents:
        return {
            "total_sentences": 0,
            "opinion_sentences": 0,
            "contraindication_sentences": 0,
            "opinion_density": 0.0,
        }
    opinion = 0
    contra = 0
    for s in sents:
        n = _normalize_text(s)
        if any(m in n for m in OPINION_MARKERS) or (
            (" i " in f" {n} " or n.startswith("i ")) and ("because" in n or "but" in n)
        ):
            opinion += 1
        if any(m in n for m in CONTRA_MARKERS):
            contra += 1
    density = opinion / max(len(sents), 1)
    return {
        "total_sentences": len(sents),
        "opinion_sentences": opinion,
        "contraindication_sentences": contra,
        "opinion_density": round(density, 4),
    }


def _status_from_metrics(metrics: Dict[str, Any], policy: Dict[str, Any]) -> Tuple[str, int, List[str]]:
    reasons_fail: List[str] = []
    reasons_warn: List[str] = []

    uniq = float(metrics["script_uniqueness"]["score"])
    tpl_hits = int(metrics["template_phrases"]["count"])
    ev_with = int(metrics["evidence"]["products_with_evidence"])
    ev_total = int(metrics["evidence"]["products_total"])
    ev_min_per = int(policy["min_evidence_segments_per_product"])
    contra = int(metrics["opinion"]["contraindication_sentences"])
    opinion_density = float(metrics["opinion"]["opinion_density"])

    # Uniqueness can be structurally lower in "Top N" formats even when evidence/opinion quality is high.
    # Fail hard only when low uniqueness is accompanied by other weak quality signals.
    if uniq < float(policy["min_script_uniqueness_score_fail"]):
        low_quality_context = (
            tpl_hits > int(policy["max_template_phrase_hits_ok"])
            or ev_with < int(policy["min_products_with_evidence_ok"])
            or opinion_density < float(policy["min_opinion_density_ok"])
            or contra < int(policy["min_contraindication_sentences_ok"])
        )
        if low_quality_context:
            reasons_fail.append(f"script_uniqueness_score too low ({uniq})")
        else:
            reasons_warn.append(
                f"script_uniqueness_score low but tolerated due strong evidence/opinion signals ({uniq})"
            )
    elif uniq < float(policy["min_script_uniqueness_score_ok"]):
        reasons_warn.append(f"script_uniqueness_score below target ({uniq})")

    if tpl_hits > int(policy["max_template_phrase_hits_fail"]):
        reasons_fail.append(f"template phrase hits too high ({tpl_hits})")
    elif tpl_hits > int(policy["max_template_phrase_hits_ok"]):
        reasons_warn.append(f"template phrase hits above target ({tpl_hits})")

    # Evidence density by product
    per_product = metrics["evidence"]["per_product"]
    below_min = [k for k, v in per_product.items() if int(v) < ev_min_per]
    if ev_with < int(policy["min_products_with_evidence_fail"]):
        reasons_fail.append(f"only {ev_with}/{ev_total} products have evidence segments")
    elif ev_with < int(policy["min_products_with_evidence_ok"]):
        reasons_warn.append(f"only {ev_with}/{ev_total} products have evidence segments")
    if below_min:
        reasons_warn.append(
            f"products below min evidence segments ({ev_min_per}): {', '.join(below_min)}"
        )

    if opinion_density < float(policy["min_opinion_density_fail"]):
        reasons_fail.append(f"opinion_density too low ({opinion_density})")
    elif opinion_density < float(policy["min_opinion_density_ok"]):
        reasons_warn.append(f"opinion_density below target ({opinion_density})")

    if contra < int(policy["min_contraindication_sentences_fail"]):
        reasons_fail.append(f"contraindication sentences too low ({contra})")
    elif contra < int(policy["min_contraindication_sentences_ok"]):
        reasons_warn.append(f"contraindication sentences below target ({contra})")

    if reasons_fail:
        return ("FAIL", 2, reasons_fail + reasons_warn)
    if reasons_warn:
        return ("WARN", 1, reasons_warn)
    return ("OK", 0, [])


def _find_manifest(run_dir: Path) -> Path | None:
    candidates = [
        run_dir / "00_manifest.json",
        run_dir / "rayvault" / "00_manifest.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def run_validation(run_dir: Path, policy: Dict[str, Any] | None = None) -> Dict[str, Any]:
    policy_data = dict(DEFAULT_POLICY)
    if policy:
        policy_data.update(policy)

    script_path = run_dir / "script.json"
    products_path = run_dir / "products.json"
    if not script_path.exists():
        return {
            "ok": False,
            "status": "FAIL",
            "exit_code": 2,
            "error": "script.json missing",
            "checked_at_utc": utc_now_iso(),
        }
    if not products_path.exists():
        return {
            "ok": False,
            "status": "FAIL",
            "exit_code": 2,
            "error": "products.json missing",
            "checked_at_utc": utc_now_iso(),
        }

    script = read_json(script_path)
    products_data = read_json(products_path)
    products = products_data.get("products", []) if isinstance(products_data, dict) else []
    rows = _extract_script_rows(script)

    metrics = {
        "script_uniqueness": _compute_uniqueness(rows, int(policy_data["ngram_size"])),
        "template_phrases": _compute_template_hits(rows),
        "evidence": _compute_evidence(rows, products if isinstance(products, list) else []),
        "opinion": _compute_opinion_density(rows),
    }
    status, exit_code, reasons = _status_from_metrics(metrics, policy_data)
    suggestions = []
    if status != "OK":
        suggestions.extend(
            [
                "Add one concrete evidence segment per product (comparison, measurement, or explicit trade-off).",
                "Increase 'who should NOT buy' lines to at least one per product block.",
                "Rewrite repeated phrasing with concrete personal observations from testing.",
            ]
        )

    report = {
        "ok": status == "OK",
        "status": status,
        "exit_code": exit_code,
        "policy": policy_data,
        "metrics": metrics,
        "reasons": reasons,
        "suggestions": suggestions,
        "checked_at_utc": utc_now_iso(),
    }
    return report


def write_report(run_dir: Path, report: Dict[str, Any]) -> Path:
    out = run_dir / "originality_report.json"
    atomic_write_json(out, report)
    manifest_path = _find_manifest(run_dir)
    if manifest_path:
        manifest = read_json(manifest_path)
        manifest["originality_validation"] = {
            "status": report.get("status"),
            "ok": bool(report.get("ok", False)),
            "exit_code": int(report.get("exit_code", 2)),
            "checked_at_utc": report.get("checked_at_utc", utc_now_iso()),
            "report_path": str(out),
            "reasons": report.get("reasons", []),
        }
        atomic_write_json(manifest_path, manifest)
    return out


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RayVault Originality Validator")
    parser.add_argument("--run-dir", required=True, help="Path to pipeline run dir")
    parser.add_argument("--policy-json", default="", help="Optional JSON string with threshold overrides")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.exists():
        print(f"Run dir not found: {run_dir}", file=sys.stderr)
        return 2
    policy_override = {}
    if args.policy_json.strip():
        try:
            parsed = json.loads(args.policy_json)
            if isinstance(parsed, dict):
                policy_override = parsed
        except Exception as exc:
            print(f"Invalid --policy-json: {exc}", file=sys.stderr)
            return 2

    report = run_validation(run_dir, policy_override)
    path = write_report(run_dir, report)
    print(
        f"originality_validator: {report.get('status')} "
        f"(exit_code={report.get('exit_code')}) -> {path}"
    )
    return int(report.get("exit_code", 2))


if __name__ == "__main__":
    raise SystemExit(main())
