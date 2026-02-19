#!/usr/bin/env python3
"""RayVault Compliance Contract (Amazon Associates + FTC disclosures).

Writes/updates deterministic compliance artifacts before Gate 2:
  - compliance_report.json
  - upload/disclosure_snippets.json
  - upload/pinned_comment.txt

Also patches manifest (00_manifest.json) when present.

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
from typing import Any, Dict, List
from urllib.parse import urlparse

from rayvault.io import atomic_write_json, read_json, utc_now_iso

DISCLOSURE_INTRO = (
    "As an Amazon Associate I earn from qualifying purchases. "
    "Quick disclosure: some links in this video are affiliate links, so I may earn a commission "
    "if you buy through them, at no extra cost to you."
)
DISCLOSURE_DESCRIPTION = (
    "As an Amazon Associate I earn from qualifying purchases. "
    "Disclosure: This description contains affiliate links. If you purchase through them, "
    "I may earn a commission at no extra cost to you. Prices may change over time."
)
DISCLOSURE_PINNED = (
    "As an Amazon Associate I earn from qualifying purchases. "
    "Affiliate disclosure: links in this post are affiliate links. "
    "I may earn a commission if you buy through them (no extra cost to you). "
    "Prices can change, so always check the current listing."
)

SHORTENER_DOMAINS = {
    "bit.ly",
    "tinyurl.com",
    "t.co",
    "goo.gl",
    "ow.ly",
    "buff.ly",
    "rb.gy",
    "is.gd",
    "cutt.ly",
    "shorturl.at",
}

ALLOWED_AMAZON_SUFFIXES = {
    "amazon.com",
    "amazon.co.uk",
    "amazon.ca",
    "amazon.de",
    "amazon.fr",
    "amazon.es",
    "amazon.it",
    "amazon.com.br",
    "amazon.com.mx",
}
ALLOWED_AMAZON_SHORT_DOMAINS = {"amzn.to"}


def _normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _find_manifest(run_dir: Path) -> Path | None:
    for p in (run_dir / "00_manifest.json", run_dir / "rayvault" / "00_manifest.json"):
        if p.exists():
            return p
    return None


def _contains_disclosure_intro(script_data: Dict[str, Any]) -> bool:
    structure = script_data.get("structure", []) if isinstance(script_data, dict) else []
    intro_lines = []
    for seg in structure[:2]:
        voice = str(seg.get("voice_text", "")).strip()
        if voice:
            intro_lines.append(voice)
    intro_text = _normalize_text(" ".join(intro_lines))
    if "as an amazon associate i earn from qualifying purchases" in intro_text:
        return True
    return ("affiliate" in intro_text) and ("commission" in intro_text)


def _extract_affiliate_links(products_data: Dict[str, Any]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    products = products_data.get("products", []) if isinstance(products_data, dict) else []
    for p in products:
        rows.append(
            {
                "asin": str(p.get("asin", "")),
                "affiliate_url": str(p.get("affiliate_url", "")),
                "product_url": str(p.get("product_url", "")),
            }
        )
    return rows


def _is_amazon_domain(netloc: str) -> bool:
    host = (netloc or "").strip().lower()
    if host.startswith("www."):
        host = host[4:]
    if host in ALLOWED_AMAZON_SHORT_DOMAINS:
        return True
    if host in ALLOWED_AMAZON_SUFFIXES:
        return True
    return any(host.endswith("." + suffix) for suffix in ALLOWED_AMAZON_SUFFIXES)


def _validate_link_clarity(links: List[Dict[str, str]]) -> Dict[str, Any]:
    violations: List[Dict[str, str]] = []
    checked = 0
    for row in links:
        aff = str(row.get("affiliate_url", "")).strip()
        if not aff:
            violations.append({"asin": row.get("asin", ""), "error": "missing_affiliate_url"})
            continue
        checked += 1
        parsed = urlparse(aff)
        host = parsed.netloc.strip().lower()
        host_no_www = host[4:] if host.startswith("www.") else host
        if host_no_www in SHORTENER_DOMAINS and host_no_www not in ALLOWED_AMAZON_SHORT_DOMAINS:
            violations.append({"asin": row.get("asin", ""), "url": aff, "error": "shortener_domain_blocked"})
            continue
        if not _is_amazon_domain(host):
            violations.append({"asin": row.get("asin", ""), "url": aff, "error": "destination_not_amazon"})
            continue
    return {"checked": checked, "violations": violations}


def _validate_amazon_marks_naming(run_dir: Path, assets_manifest: Dict[str, Any]) -> Dict[str, Any]:
    violations: List[str] = []
    assets = assets_manifest.get("assets", []) if isinstance(assets_manifest, dict) else []
    for asset in assets:
        files = asset.get("files", {}) if isinstance(asset, dict) else {}
        for key, value in files.items():
            paths: List[str] = []
            if isinstance(value, str):
                paths = [value]
            elif isinstance(value, list):
                paths = [str(x) for x in value]
            for rel in paths:
                rel_norm = rel.replace("\\", "/").lower()
                # Allow reference source naming only.
                if rel_norm.endswith("/ref_amazon.jpg"):
                    continue
                if "amazon" in Path(rel_norm).name:
                    violations.append(rel)

    overlays = run_dir / "rayvault" / "overlays_index.json"
    if overlays.exists():
        data = read_json(overlays)
        for item in data.get("overlays", []) if isinstance(data, dict) else []:
            path = str(item.get("path", ""))
            name = Path(path).name.lower()
            if "amazon" in name:
                violations.append(path)
    return {"violations": sorted(set(violations))}


def _write_disclosure_artifacts(run_dir: Path) -> Dict[str, str]:
    upload_dir = run_dir / "upload"
    upload_dir.mkdir(parents=True, exist_ok=True)
    snippets = {
        "intro_disclosure": DISCLOSURE_INTRO,
        "description_disclosure": DISCLOSURE_DESCRIPTION,
        "pinned_comment_disclosure": DISCLOSURE_PINNED,
    }
    snippets_path = upload_dir / "disclosure_snippets.json"
    atomic_write_json(snippets_path, snippets)
    pinned_path = upload_dir / "pinned_comment.txt"
    pinned_path.write_text(DISCLOSURE_PINNED + "\n", encoding="utf-8")
    return {
        "snippets_json": str(snippets_path),
        "pinned_comment_txt": str(pinned_path),
    }


def run_contract(run_dir: Path) -> Dict[str, Any]:
    script_path = run_dir / "script.json"
    products_path = run_dir / "products.json"
    assets_manifest_path = run_dir / "assets_manifest.json"
    manifest_path = _find_manifest(run_dir)

    missing = []
    for p in (script_path, products_path, assets_manifest_path):
        if not p.exists():
            missing.append(str(p.relative_to(run_dir)))
    if missing:
        return {
            "ok": False,
            "status": "FAIL",
            "exit_code": 2,
            "error": f"missing required files: {', '.join(missing)}",
            "checked_at_utc": utc_now_iso(),
        }

    script_data = read_json(script_path)
    products_data = read_json(products_path)
    assets_manifest = read_json(assets_manifest_path)

    intro_ok = _contains_disclosure_intro(script_data)
    link_check = _validate_link_clarity(_extract_affiliate_links(products_data))
    marks_check = _validate_amazon_marks_naming(run_dir, assets_manifest)
    files = _write_disclosure_artifacts(run_dir)

    reasons_fail: List[str] = []
    reasons_warn: List[str] = []

    if not intro_ok:
        reasons_fail.append("missing affiliate disclosure in intro segments")
    if link_check["violations"]:
        reasons_fail.append(f"link_clarity violations: {len(link_check['violations'])}")
    if marks_check["violations"]:
        reasons_warn.append(
            f"asset/overlay naming contains 'amazon' in {len(marks_check['violations'])} files"
        )

    status = "OK"
    exit_code = 0
    if reasons_fail:
        status = "FAIL"
        exit_code = 2
    elif reasons_warn:
        status = "WARN"
        exit_code = 1

    contract_block = {
        "required": {
            "intro_disclosure": True,
            "description_disclosure": True,
            "pinned_comment_disclosure": True,
            "link_clarity_no_shorteners": True,
        },
        "snippets": {
            "intro_disclosure": DISCLOSURE_INTRO,
            "description_disclosure": DISCLOSURE_DESCRIPTION,
            "pinned_comment_disclosure": DISCLOSURE_PINNED,
        },
        "artifacts": files,
    }

    report = {
        "ok": status == "OK",
        "status": status,
        "exit_code": exit_code,
        "checked_at_utc": utc_now_iso(),
        "intro_disclosure_present": intro_ok,
        "link_clarity": link_check,
        "amazon_marks_naming": marks_check,
        "contract": contract_block,
        "reasons": reasons_fail + reasons_warn,
    }

    report_path = run_dir / "compliance_report.json"
    atomic_write_json(report_path, report)

    if manifest_path:
        manifest = read_json(manifest_path)
        manifest["compliance_contract"] = {
            "status": status,
            "ok": report["ok"],
            "exit_code": exit_code,
            "checked_at_utc": report["checked_at_utc"],
            "report_path": str(report_path),
            "required_placements": contract_block["required"],
            "snippets": contract_block["snippets"],
            "reasons": report["reasons"],
        }
        atomic_write_json(manifest_path, manifest)

    return report


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RayVault Compliance Contract")
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.exists():
        print(f"Run dir not found: {run_dir}", file=sys.stderr)
        return 2

    report = run_contract(run_dir)
    print(
        f"compliance_contract: {report.get('status')} "
        f"(exit_code={report.get('exit_code')}) -> {run_dir / 'compliance_report.json'}"
    )
    return int(report.get("exit_code", 2))


if __name__ == "__main__":
    raise SystemExit(main())
