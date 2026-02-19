#!/usr/bin/env python3
"""Progressive-disclosure selector for the local skill graph."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List


TOKEN_RE = re.compile(r"[a-z0-9_\-]+")
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


@dataclass
class Node:
    node_id: str
    title: str
    description: str
    tags: List[str]
    links: List[str]
    path: Path


def tokenize(text: str) -> List[str]:
    return [t for t in TOKEN_RE.findall((text or "").lower()) if len(t) > 1]


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
        parts = [p.strip().strip('"').strip("'") for p in inner.split(",")]
        return [p for p in parts if p]
    if not raw:
        return []
    return [raw.strip('"').strip("'")]


def parse_frontmatter(text: str) -> Dict[str, str]:
    lines = text.splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        return {}
    front = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        front[key.strip()] = value.strip()
    return front


def parse_node(path: Path) -> Node:
    raw = path.read_text(encoding="utf-8")
    front = parse_frontmatter(raw)
    node_id = normalize_id(front.get("id") or path.stem)
    title = front.get("title", path.stem)
    description = front.get("description", "")
    tags = [normalize_id(x) for x in parse_list(front.get("tags", ""))]

    links = [normalize_id(x) for x in parse_list(front.get("links", ""))]
    if not links:
        links = [normalize_id(m.group(1)) for m in WIKILINK_RE.finditer(raw)]

    links = [l for l in links if l]
    return Node(node_id=node_id, title=title, description=description, tags=tags, links=links, path=path)


def load_nodes(graph_root: Path) -> Dict[str, Node]:
    nodes: Dict[str, Node] = {}
    for path in sorted(graph_root.rglob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        node = parse_node(path)
        nodes[node.node_id] = node
    return nodes


def score_node(node: Node, task_tokens: Iterable[str]) -> float:
    task = set(task_tokens)
    if not task:
        return 0.0

    hay_title = set(tokenize(node.title))
    hay_desc = set(tokenize(node.description))
    hay_tags = set(tokenize(" ".join(node.tags)))
    hay_id = set(tokenize(node.node_id))

    score = 0.0
    score += len(task & hay_title) * 2.0
    score += len(task & hay_desc) * 1.5
    score += len(task & hay_tags) * 1.2
    score += len(task & hay_id) * 1.0
    return score


def pick_nodes(
    nodes: Dict[str, Node],
    task: str,
    start: str,
    top: int,
    min_score: float,
    include_start: bool,
) -> List[Dict[str, object]]:
    task_tokens = tokenize(task)
    start_id = normalize_id(start)
    results: Dict[str, Dict[str, object]] = {}

    if start_id in nodes:
        frontier = [start_id] + nodes[start_id].links
    else:
        frontier = list(nodes.keys())

    for node_id in frontier:
        node = nodes.get(node_id)
        if not node:
            continue
        base = score_node(node, task_tokens)
        if node_id == start_id and not include_start and base < min_score:
            continue
        if node_id != start_id and base < min_score:
            continue
        results[node_id] = {
            "id": node.node_id,
            "title": node.title,
            "description": node.description,
            "score": base,
            "reason": "direct_match" if base >= min_score else "start_node",
            "path": str(node.path),
            "links": node.links,
        }

    # One-hop expansion from direct matches for progressive disclosure.
    seed_nodes = sorted(results.values(), key=lambda x: x["score"], reverse=True)[: max(top, 3)]
    for seed in seed_nodes:
        seed_node = nodes.get(seed["id"])
        if not seed_node:
            continue
        for linked in seed_node.links:
            linked_node = nodes.get(linked)
            if not linked_node:
                continue
            bonus = max(float(seed["score"]) * 0.35, 0.4)
            if linked in results:
                results[linked]["score"] = max(float(results[linked]["score"]), bonus)
                continue
            results[linked] = {
                "id": linked_node.node_id,
                "title": linked_node.title,
                "description": linked_node.description,
                "score": bonus,
                "reason": f"linked_from:{seed_node.node_id}",
                "path": str(linked_node.path),
                "links": linked_node.links,
            }

    # If nothing matched, include start node + one hop so the caller can still navigate.
    if not results and start_id in nodes:
        start_node = nodes[start_id]
        results[start_id] = {
            "id": start_node.node_id,
            "title": start_node.title,
            "description": start_node.description,
            "score": 0.0,
            "reason": "fallback_start",
            "path": str(start_node.path),
            "links": start_node.links,
        }
        for linked in start_node.links[: max(2, min(4, top))]:
            linked_node = nodes.get(linked)
            if not linked_node:
                continue
            results[linked] = {
                "id": linked_node.node_id,
                "title": linked_node.title,
                "description": linked_node.description,
                "score": 0.3,
                "reason": f"fallback_linked_from:{start_node.node_id}",
                "path": str(linked_node.path),
                "links": linked_node.links,
            }

    ordered = sorted(results.values(), key=lambda x: (float(x["score"]), x["id"]), reverse=True)
    return ordered[:top]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Find relevant skill-graph nodes for a task")
    p.add_argument("--task", required=True, help="Task description")
    p.add_argument("--graph-root", default=str(Path(__file__).resolve().parent.parent / "skill_graph"))
    p.add_argument("--start", default="index", help="Start node id")
    p.add_argument("--top", type=int, default=6)
    p.add_argument("--min-score", type=float, default=0.6, help="Minimum direct relevance score")
    p.add_argument("--include-start", action="store_true", help="Always include the start node")
    p.add_argument("--json", action="store_true")
    return p


def main() -> int:
    args = build_parser().parse_args()
    root = Path(args.graph_root).resolve()
    nodes = load_nodes(root)
    selected = pick_nodes(
        nodes,
        args.task,
        args.start,
        args.top,
        min_score=max(0.0, float(args.min_score)),
        include_start=bool(args.include_start),
    )
    traversal = [normalize_id(args.start)] + [str(n.get("id", "")) for n in selected if str(n.get("id", ""))]
    dedup_traversal = []
    seen = set()
    for node_id in traversal:
        if node_id and node_id not in seen:
            dedup_traversal.append(node_id)
            seen.add(node_id)
    payload = {
        "task": args.task,
        "graph_root": str(root),
        "start": normalize_id(args.start),
        "count": len(selected),
        "traversal": dedup_traversal,
        "nodes": selected,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=True, indent=2))
    else:
        print(f"Task: {args.task}")
        print(f"Start: {payload['start']}")
        print(f"Traversal: {' -> '.join(payload['traversal'])}")
        for idx, n in enumerate(selected, start=1):
            print(f"{idx}. {n['id']} ({n['score']:.2f}) - {n['reason']}")
            print(f"   {n['path']}")
            if n["description"]:
                print(f"   {n['description']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
