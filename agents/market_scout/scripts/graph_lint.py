#!/usr/bin/env python3
"""Lint the local skill graph structure for deterministic traversal."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set

WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


@dataclass
class LintError:
    code: str
    message: str
    path: str | None = None


def normalize_id(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("[[") and raw.endswith("]]"):
        raw = raw[2:-2]
    return raw.strip().lower().replace(" ", "-")


def parse_list(raw: str) -> List[str]:
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [x.strip().strip('"').strip("'") for x in inner.split(",") if x.strip()]
    if not raw:
        return []
    return [raw.strip('"').strip("'")]


def parse_frontmatter(content: str) -> Dict[str, str] | None:
    lines = content.splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        return None
    data: Dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return data
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return None


def collect_nodes(graph_root: Path) -> tuple[Dict[str, Path], Dict[str, Dict[str, str]], List[LintError]]:
    errors: List[LintError] = []
    node_paths: Dict[str, Path] = {}
    metadata: Dict[str, Dict[str, str]] = {}

    for path in sorted(graph_root.rglob("*.md")):
        content = path.read_text(encoding="utf-8")
        fm = parse_frontmatter(content)
        if fm is None:
            errors.append(LintError("missing_frontmatter", "Missing or malformed YAML frontmatter", str(path)))
            continue

        missing = [k for k in ["id", "title", "description", "tags", "links"] if k not in fm]
        if missing:
            errors.append(LintError("missing_fields", f"Missing required frontmatter fields: {', '.join(missing)}", str(path)))
            continue

        node_id = normalize_id(fm["id"])
        if node_id in node_paths:
            errors.append(
                LintError(
                    "duplicate_id",
                    f"Duplicate node id '{node_id}' already declared at {node_paths[node_id]}",
                    str(path),
                )
            )
            continue

        node_paths[node_id] = path
        metadata[node_id] = {
            "content": content,
            "links": fm["links"],
        }

    return node_paths, metadata, errors


def lint_graph(graph_root: Path, allow_orphans: Set[str]) -> List[LintError]:
    node_paths, metadata, errors = collect_nodes(graph_root)

    outbound: Dict[str, Set[str]] = {}
    inbound: Dict[str, int] = {node_id: 0 for node_id in node_paths}

    for node_id, meta in metadata.items():
        content = meta["content"]
        fm_links = {normalize_id(x) for x in parse_list(meta["links"]) if normalize_id(x)}
        prose_links = {normalize_id(m.group(1)) for m in WIKILINK_RE.finditer(content)}
        links = fm_links | prose_links
        outbound[node_id] = links

        for link in links:
            if link not in node_paths:
                errors.append(
                    LintError(
                        "broken_link",
                        f"Node '{node_id}' references missing node '{link}'",
                        str(node_paths[node_id]),
                    )
                )
                continue
            inbound[link] = inbound.get(link, 0) + 1

    for node_id, count in inbound.items():
        if count == 0 and node_id not in allow_orphans:
            errors.append(
                LintError(
                    "orphan_node",
                    f"Node '{node_id}' has no inbound links (add from a MOC or index)",
                    str(node_paths[node_id]),
                )
            )

    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lint skill graph for broken links, orphan nodes, and frontmatter issues")
    parser.add_argument(
        "--graph-root",
        default=str(Path(__file__).resolve().parent.parent / "skill_graph"),
        help="Path to skill graph root",
    )
    parser.add_argument(
        "--allow-orphan",
        action="append",
        default=["index"],
        help="Node id allowed to be orphan (can be passed multiple times)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = Path(args.graph_root).resolve()
    allow_orphans = {normalize_id(x) for x in args.allow_orphan}

    errors = lint_graph(root, allow_orphans)
    payload = {
        "graph_root": str(root),
        "ok": len(errors) == 0,
        "error_count": len(errors),
        "errors": [e.__dict__ for e in errors],
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=True, indent=2))
    else:
        if not errors:
            print(f"OK: skill graph lint passed ({root})")
        else:
            print(f"FAIL: skill graph lint found {len(errors)} issue(s)")
            for err in errors:
                loc = f" [{err.path}]" if err.path else ""
                print(f"- {err.code}: {err.message}{loc}")

    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
