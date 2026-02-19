"""Skill Graph — auto-improvement engine for RayviewsLab agents.

Reads, scans, and updates the interconnected skill graph at agents/skills/.
Provides functions for:
- Scanning node descriptions (YAML frontmatter) without reading full files
- Loading specific nodes by path or tag
- Recording learnings after pipeline runs
- Querying relevant learnings before a run
- Updating prompt nodes based on generation results

The skill graph follows the arscontexta pattern:
- Each node = one complete thought (markdown + YAML frontmatter)
- Wikilinks [[target]] create traversable connections
- Progressive disclosure: index → descriptions → links → full content
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SKILLS_ROOT = Path(__file__).resolve().parent.parent.parent / "agents" / "skills"
LEARNINGS_DIR = SKILLS_ROOT / "learnings"
PROMPTS_DIR = SKILLS_ROOT / "prompts"

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_YAML_KV_RE = re.compile(r"^(\w[\w-]*):\s*(.+)$", re.MULTILINE)
_YAML_LIST_RE = re.compile(r"^(\w[\w-]*):\s*\[([^\]]*)\]$", re.MULTILINE)
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SkillNode:
    """A single node in the skill graph."""
    path: Path
    description: str = ""
    tags: list[str] = field(default_factory=list)
    status: str = ""
    created: str = ""
    updated: str = ""
    frontmatter: dict[str, str] = field(default_factory=dict)
    links: list[str] = field(default_factory=list)
    content: str = ""


@dataclass
class GenerationResult:
    """Outcome of a single image generation for learning recording."""
    variant: str  # hero, usage1, detail, mood, usage2
    product_rank: int
    prompt_used: str
    tool_used: str  # product-background, generative-expand, img2img
    success: bool
    fidelity_score: float = 0.0  # 0-10
    variety_score: float = 0.0   # 0-10, how different from other variants
    duration_s: float = 0.0
    file_size_kb: int = 0
    notes: str = ""


@dataclass
class RunSummary:
    """Summary of a complete pipeline asset generation run."""
    video_id: str
    timestamp: str = ""
    total_generated: int = 0
    total_failed: int = 0
    avg_fidelity: float = 0.0
    avg_variety: float = 0.0
    results: list[GenerationResult] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# YAML frontmatter parsing (stdlib-only, no PyYAML)
# ---------------------------------------------------------------------------

def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extract YAML frontmatter key-value pairs from markdown text."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    block = m.group(1)
    result: dict[str, str] = {}
    for km in _YAML_KV_RE.finditer(block):
        key, val = km.group(1), km.group(2).strip().strip('"').strip("'")
        result[key] = val
    # Parse list values like tags: [tag1, tag2]
    for lm in _YAML_LIST_RE.finditer(block):
        key = lm.group(1)
        items = [x.strip().strip('"').strip("'") for x in lm.group(2).split(",")]
        result[key] = ",".join(items)
    return result


def _extract_links(text: str) -> list[str]:
    """Extract all [[wikilinks]] from markdown text."""
    return _WIKILINK_RE.findall(text)


# ---------------------------------------------------------------------------
# Scanning — read descriptions without loading full files
# ---------------------------------------------------------------------------

def scan_nodes(root: Path | None = None) -> list[SkillNode]:
    """Scan all skill nodes, reading only YAML frontmatter.

    Returns list of SkillNode with description, tags, status populated.
    Content is NOT loaded (empty string) — use load_node() for full content.
    """
    root = root or SKILLS_ROOT
    nodes = []
    for md_path in sorted(root.rglob("*.md")):
        try:
            # Read only first 1KB for frontmatter
            with open(md_path, "r", encoding="utf-8") as f:
                head = f.read(1024)
        except OSError:
            continue

        fm = _parse_frontmatter(head)
        if not fm:
            continue

        tags_str = fm.get("tags", "")
        tags = [t.strip() for t in tags_str.split(",") if t.strip()]

        node = SkillNode(
            path=md_path,
            description=fm.get("description", ""),
            tags=tags,
            status=fm.get("status", ""),
            created=fm.get("created", ""),
            updated=fm.get("updated", ""),
            frontmatter=fm,
        )
        nodes.append(node)
    return nodes


def scan_by_tag(tag: str, root: Path | None = None) -> list[SkillNode]:
    """Scan nodes and filter by tag."""
    return [n for n in scan_nodes(root) if tag in n.tags]


def scan_learnings() -> list[SkillNode]:
    """Scan all learning nodes, newest first (by filename date prefix)."""
    nodes = scan_nodes(LEARNINGS_DIR)
    return sorted(nodes, key=lambda n: n.path.stem, reverse=True)


def scan_failures() -> list[SkillNode]:
    """Scan learnings tagged as failures."""
    return [n for n in scan_learnings() if "failure" in n.tags]


# ---------------------------------------------------------------------------
# Loading — read full node content
# ---------------------------------------------------------------------------

def load_node(path: Path) -> SkillNode:
    """Load a skill node with full content and wikilinks."""
    text = path.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    tags_str = fm.get("tags", "")
    tags = [t.strip() for t in tags_str.split(",") if t.strip()]

    return SkillNode(
        path=path,
        description=fm.get("description", ""),
        tags=tags,
        status=fm.get("status", ""),
        created=fm.get("created", ""),
        updated=fm.get("updated", ""),
        frontmatter=fm,
        links=_extract_links(text),
        content=text,
    )


def load_by_name(name: str, root: Path | None = None) -> SkillNode | None:
    """Find and load a node by filename (without extension)."""
    root = root or SKILLS_ROOT
    for md_path in root.rglob("*.md"):
        if md_path.stem == name:
            return load_node(md_path)
    return None


# ---------------------------------------------------------------------------
# Prompt loading — get variant-specific prompts from skill graph
# ---------------------------------------------------------------------------

def get_variant_prompt(variant: str, tool: str = "product-background") -> str:
    """Load the prompt template for a specific variant and tool.

    Args:
        variant: hero, usage1, usage2, detail, mood
        tool: product-background or img2img

    Returns prompt text, or empty string if not found.
    """
    variant_to_file = {
        "hero": "hero-shot",
        "usage1": "lifestyle-shot",
        "usage2": "usage-variation",
        "detail": "detail-shot",
        "mood": "mood-shot",
    }

    filename = variant_to_file.get(variant)
    if not filename:
        return ""

    node_path = PROMPTS_DIR / f"{filename}.md"
    if not node_path.exists():
        return ""

    node = load_node(node_path)
    content = node.content

    # Extract the template for the specified tool
    tool_header = {
        "product-background": "## Template (Product Background)",
        "img2img": "## Template (Img2Img)",
    }.get(tool, "## Template (Product Background)")

    # Find the template section and extract the code block
    idx = content.find(tool_header)
    if idx == -1:
        return ""

    # Find the next code block after the header
    code_start = content.find("```\n", idx)
    if code_start == -1:
        return ""
    code_start += 4  # skip ```\n

    code_end = content.find("\n```", code_start)
    if code_end == -1:
        return ""

    return content[code_start:code_end].strip()


# ---------------------------------------------------------------------------
# Recording learnings — auto-improvement after pipeline runs
# ---------------------------------------------------------------------------

def record_learning(
    title: str,
    description: str,
    *,
    severity: str = "medium",
    tags: list[str] | None = None,
    video_id: str = "",
    affected_tools: list[str] | None = None,
    fix: str = "",
    body: str = "",
) -> Path:
    """Record a new learning node in the learnings directory.

    Returns the path to the created node.
    """
    LEARNINGS_DIR.mkdir(parents=True, exist_ok=True)

    date_prefix = time.strftime("%Y-%m-%d")
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    filename = f"{date_prefix}-{slug}.md"
    path = LEARNINGS_DIR / filename

    # Avoid overwriting — add counter suffix if exists
    counter = 2
    while path.exists():
        filename = f"{date_prefix}-{slug}-{counter}.md"
        path = LEARNINGS_DIR / filename
        counter += 1

    all_tags = ["learning"] + (tags or [])
    tags_str = ", ".join(all_tags)
    tools_str = ", ".join(affected_tools or [])

    content = f"""---
description: "{description}"
tags: [{tags_str}]
created: {date_prefix}
severity: {severity}
video_id: {video_id}
affected_tools: [{tools_str}]
fix: {fix}
---

# {title}

{body}
"""

    # Atomic write
    tmp = path.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp), str(path))
    except OSError:
        if tmp.exists():
            tmp.unlink()
        raise

    # Update learnings index
    _update_learnings_index(path, description)

    return path


def _update_learnings_index(new_node: Path, description: str) -> None:
    """Add new learning to the learnings/_index.md Recent Learnings section."""
    index_path = LEARNINGS_DIR / "_index.md"
    if not index_path.exists():
        return

    try:
        text = index_path.read_text(encoding="utf-8")
    except OSError:
        return

    # Find "## Recent Learnings" section and insert after it
    marker = "## Recent Learnings (newest first)\n"
    idx = text.find(marker)
    if idx == -1:
        return

    insert_pos = idx + len(marker)
    stem = new_node.stem
    new_line = f"\n- [[{stem}]] — {description}"
    text = text[:insert_pos] + new_line + text[insert_pos:]

    # Atomic write
    tmp = index_path.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp), str(index_path))
    except OSError:
        if tmp.exists():
            tmp.unlink()


def record_run_summary(summary: RunSummary) -> Path:
    """Record a complete pipeline run as a learning node."""
    issues_text = ""
    if summary.issues:
        issues_text = "\n## Issues Found\n\n"
        for issue in summary.issues:
            issues_text += f"- {issue}\n"

    results_text = "\n## Per-Variant Results\n\n"
    results_text += "| Variant | Tool | Fidelity | Variety | Duration | Size | Notes |\n"
    results_text += "|---------|------|----------|---------|----------|------|-------|\n"
    for r in summary.results:
        results_text += (
            f"| {r.product_rank:02d}_{r.variant} | {r.tool_used} | "
            f"{r.fidelity_score:.1f} | {r.variety_score:.1f} | "
            f"{r.duration_s:.0f}s | {r.file_size_kb}KB | {r.notes} |\n"
        )

    body = f"""## Summary

- Video: {summary.video_id}
- Generated: {summary.total_generated}, Failed: {summary.total_failed}
- Average fidelity: {summary.avg_fidelity:.1f}/10
- Average variety: {summary.avg_variety:.1f}/10
{issues_text}{results_text}"""

    severity = "low" if not summary.issues else "medium"
    tags = ["run-summary"]
    if summary.total_failed > 0:
        tags.append("failure")
    if summary.avg_variety < 3.0:
        tags.append("low-variety")

    return record_learning(
        title=f"Pipeline run {summary.video_id}",
        description=f"Run {summary.video_id}: {summary.total_generated} generated, avg fidelity {summary.avg_fidelity:.1f}, avg variety {summary.avg_variety:.1f}",
        severity=severity,
        tags=tags,
        video_id=summary.video_id,
        body=body,
    )


# ---------------------------------------------------------------------------
# Pre-run checks — query relevant learnings before generation
# ---------------------------------------------------------------------------

def get_relevant_learnings(tool: str = "", variant: str = "") -> list[SkillNode]:
    """Get learnings relevant to the planned generation.

    Filters by tool and variant tags. Returns nodes with severity: critical first.
    """
    learnings = scan_learnings()
    relevant = []
    for node in learnings:
        if tool and tool in node.tags:
            relevant.append(node)
        elif variant and variant in node.tags:
            relevant.append(node)
        elif "critical" in node.tags:
            relevant.append(node)

    # Sort: critical first
    relevant.sort(key=lambda n: (0 if "critical" in n.tags else 1, n.path.stem), reverse=False)
    return relevant


def pre_run_check(tool: str, video_id: str = "") -> list[str]:
    """Check learnings for known issues with the planned tool.

    Returns list of warning messages. Empty list = no known issues.
    """
    warnings = []
    learnings = get_relevant_learnings(tool=tool)

    for node in learnings:
        if node.status == "critical" or "critical" in node.tags:
            warnings.append(f"CRITICAL: {node.description}")
        elif "failure" in node.tags:
            fix = node.frontmatter.get("fix", "")
            warnings.append(f"Known issue: {node.description} (fix: {fix})")

    return warnings


# ---------------------------------------------------------------------------
# Graph traversal — follow wikilinks
# ---------------------------------------------------------------------------

def traverse(start_name: str, max_depth: int = 2) -> list[SkillNode]:
    """Traverse the skill graph from a starting node, following wikilinks.

    Returns all reachable nodes up to max_depth levels deep.
    """
    visited: set[str] = set()
    result: list[SkillNode] = []

    def _visit(name: str, depth: int) -> None:
        if depth > max_depth or name in visited:
            return
        visited.add(name)
        node = load_by_name(name)
        if not node:
            return
        result.append(node)
        for link in node.links:
            # Resolve relative links like ../dzine/product-background
            link_name = link.split("/")[-1]
            _visit(link_name, depth + 1)

    _visit(start_name, 0)
    return result


# ---------------------------------------------------------------------------
# CLI interface
# ---------------------------------------------------------------------------

def _cli() -> None:
    """Simple CLI for inspecting the skill graph."""
    import sys

    args = sys.argv[1:]
    if not args or args[0] == "scan":
        nodes = scan_nodes()
        print(f"Skill graph: {len(nodes)} nodes\n")
        for node in nodes:
            rel = node.path.relative_to(SKILLS_ROOT)
            status = f" [{node.status}]" if node.status else ""
            print(f"  {rel}{status}")
            print(f"    {node.description}")
            if node.tags:
                print(f"    tags: {', '.join(node.tags)}")
            print()

    elif args[0] == "learnings":
        learnings = scan_learnings()
        print(f"Learnings: {len(learnings)} entries\n")
        for node in learnings:
            sev = node.frontmatter.get("severity", "")
            sev_str = f" ({sev})" if sev else ""
            print(f"  {node.path.stem}{sev_str}")
            print(f"    {node.description}")
            print()

    elif args[0] == "check":
        tool = args[1] if len(args) > 1 else ""
        warnings = pre_run_check(tool)
        if warnings:
            print(f"Pre-run warnings for tool '{tool}':")
            for w in warnings:
                print(f"  ! {w}")
        else:
            print(f"No known issues for tool '{tool}'")

    elif args[0] == "prompt":
        variant = args[1] if len(args) > 1 else "hero"
        tool = args[2] if len(args) > 2 else "product-background"
        prompt = get_variant_prompt(variant, tool)
        if prompt:
            print(f"Prompt for {variant} ({tool}):\n")
            print(prompt)
        else:
            print(f"No prompt found for {variant} ({tool})")

    elif args[0] == "traverse":
        start = args[1] if len(args) > 1 else "_index"
        nodes = traverse(start)
        print(f"Traversal from '{start}': {len(nodes)} nodes reached\n")
        for node in nodes:
            rel = node.path.relative_to(SKILLS_ROOT)
            links = len(node.links)
            print(f"  {rel} ({links} links)")

    else:
        print("Usage: python -m tools.lib.skill_graph [scan|learnings|check TOOL|prompt VARIANT [TOOL]|traverse START]")


if __name__ == "__main__":
    _cli()
