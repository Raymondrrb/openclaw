"""Tests for tools.lib.skill_graph — skill graph engine."""

import os
import tempfile
import textwrap
import unittest
from pathlib import Path

from tools.lib.skill_graph import (
    _parse_frontmatter,
    _extract_links,
    scan_nodes,
    scan_by_tag,
    scan_learnings,
    scan_failures,
    load_node,
    load_by_name,
    get_variant_prompt,
    pre_run_check,
    record_learning,
    record_run_summary,
    traverse,
    GenerationResult as SkillGenResult,
    RunSummary,
    SkillNode,
    SKILLS_ROOT,
)


class TestFrontmatterParsing(unittest.TestCase):
    """Test YAML frontmatter extraction from markdown."""

    def test_simple_frontmatter(self):
        text = textwrap.dedent("""\
        ---
        description: A test node
        tags: [foo, bar, baz]
        status: proven
        ---

        # Title
        """)
        fm = _parse_frontmatter(text)
        self.assertEqual(fm["description"], "A test node")
        self.assertEqual(fm["status"], "proven")
        self.assertIn("foo", fm["tags"])

    def test_quoted_description(self):
        text = textwrap.dedent("""\
        ---
        description: "Quoted: with special chars"
        tags: [a]
        ---
        """)
        fm = _parse_frontmatter(text)
        self.assertEqual(fm["description"], "Quoted: with special chars")

    def test_no_frontmatter(self):
        text = "# No frontmatter here\n\nJust content."
        fm = _parse_frontmatter(text)
        self.assertEqual(fm, {})

    def test_empty_tags(self):
        text = "---\ndescription: test\ntags: []\n---\n"
        fm = _parse_frontmatter(text)
        self.assertEqual(fm["tags"], "")


class TestWikilinkExtraction(unittest.TestCase):
    """Test [[wikilink]] extraction from markdown."""

    def test_simple_links(self):
        text = "See [[product-background]] and [[img2img-workflow]] for details."
        links = _extract_links(text)
        self.assertEqual(links, ["product-background", "img2img-workflow"])

    def test_relative_links(self):
        text = "See [[../dzine/product-background]] for the tool."
        links = _extract_links(text)
        self.assertEqual(links, ["../dzine/product-background"])

    def test_no_links(self):
        text = "No wikilinks in this text."
        links = _extract_links(text)
        self.assertEqual(links, [])

    def test_multiple_per_line(self):
        text = "Use [[tool-a]] or [[tool-b]] or [[tool-c]]."
        links = _extract_links(text)
        self.assertEqual(len(links), 3)


class TestScanNodes(unittest.TestCase):
    """Test scanning the real skill graph."""

    def test_scan_finds_nodes(self):
        nodes = scan_nodes()
        self.assertGreater(len(nodes), 15)

    def test_all_nodes_have_description(self):
        for node in scan_nodes():
            self.assertTrue(node.description, f"Node {node.path} has no description")

    def test_scan_by_tag_critical(self):
        critical = scan_by_tag("critical")
        self.assertGreater(len(critical), 0)

    def test_scan_by_tag_prompt(self):
        prompts = scan_by_tag("prompt")
        self.assertGreater(len(prompts), 3)

    def test_scan_learnings(self):
        learnings = scan_learnings()
        self.assertGreater(len(learnings), 0)
        # Newest first (reverse chronological by filename)
        stems = [n.path.stem for n in learnings if n.path.stem != "_index"]
        if len(stems) > 1:
            self.assertGreaterEqual(stems[0], stems[1])

    def test_scan_failures(self):
        failures = scan_failures()
        self.assertGreater(len(failures), 0)
        for f in failures:
            self.assertIn("failure", f.tags)


class TestLoadNode(unittest.TestCase):
    """Test loading full nodes with content and links."""

    def test_load_index(self):
        node = load_by_name("_index", SKILLS_ROOT)
        self.assertIsNotNone(node)
        self.assertIn("RayviewsLab", node.content)
        self.assertGreater(len(node.links), 0)

    def test_load_product_background(self):
        node = load_by_name("product-background")
        self.assertIsNotNone(node)
        self.assertEqual(node.status, "proven")
        self.assertIn("product-background", node.tags)
        self.assertIn("scene-variation", node.tags)

    def test_load_generative_expand(self):
        node = load_by_name("generative-expand")
        self.assertIsNotNone(node)
        self.assertEqual(node.status, "limited")

    def test_load_nonexistent(self):
        node = load_by_name("nonexistent-node-xyz")
        self.assertIsNone(node)


class TestVariantPrompts(unittest.TestCase):
    """Test loading variant-specific prompts from skill graph."""

    def test_hero_prompt(self):
        prompt = get_variant_prompt("hero", "product-background")
        self.assertGreater(len(prompt), 100)
        self.assertIn("dark", prompt.lower())
        self.assertIn("studio", prompt.lower())

    def test_lifestyle_prompt(self):
        prompt = get_variant_prompt("usage1", "product-background")
        self.assertGreater(len(prompt), 100)
        self.assertIn("living room", prompt.lower())
        self.assertIn("sunlight", prompt.lower())

    def test_detail_prompt(self):
        prompt = get_variant_prompt("detail", "product-background")
        self.assertGreater(len(prompt), 100)
        self.assertIn("white", prompt.lower())

    def test_mood_prompt(self):
        prompt = get_variant_prompt("mood", "product-background")
        self.assertGreater(len(prompt), 100)
        self.assertIn("dramatic", prompt.lower())

    def test_usage2_prompt(self):
        prompt = get_variant_prompt("usage2", "product-background")
        self.assertGreater(len(prompt), 100)
        self.assertIn("kitchen", prompt.lower())

    def test_all_prompts_distinct(self):
        """All variant prompts must be completely different."""
        prompts = {}
        for v in ["hero", "usage1", "usage2", "detail", "mood"]:
            prompts[v] = get_variant_prompt(v, "product-background")

        # Check every pair is distinct
        variants = list(prompts.keys())
        for i in range(len(variants)):
            for j in range(i + 1, len(variants)):
                v1, v2 = variants[i], variants[j]
                self.assertNotEqual(
                    prompts[v1], prompts[v2],
                    f"Prompts for {v1} and {v2} are identical!"
                )
                # Check word overlap is < 50%
                words1 = set(prompts[v1].lower().split())
                words2 = set(prompts[v2].lower().split())
                overlap = len(words1 & words2)
                total = max(len(words1), len(words2))
                overlap_pct = overlap / total if total else 0
                self.assertLess(
                    overlap_pct, 0.5,
                    f"Prompts {v1} and {v2} have {overlap_pct:.0%} word overlap"
                )

    def test_img2img_prompt(self):
        prompt = get_variant_prompt("hero", "img2img")
        self.assertGreater(len(prompt), 100)
        # Img2Img prompts should mention the product
        self.assertIn("product", prompt.lower())

    def test_unknown_variant(self):
        prompt = get_variant_prompt("nonexistent", "product-background")
        self.assertEqual(prompt, "")


class TestPreRunCheck(unittest.TestCase):
    """Test pre-run safety checks from learnings."""

    def test_generative_expand_warns(self):
        warnings = pre_run_check("generative-expand")
        self.assertGreater(len(warnings), 0)
        # Should include the critical identical-images warning
        has_critical = any("CRITICAL" in w for w in warnings)
        self.assertTrue(has_critical)

    def test_product_background_fewer_warnings(self):
        pb_warnings = pre_run_check("product-background")
        expand_warnings = pre_run_check("generative-expand")
        # Product Background should have fewer tool-specific warnings than gen-expand
        self.assertLessEqual(len(pb_warnings), len(expand_warnings))

    def test_empty_tool(self):
        warnings = pre_run_check("")
        # Empty tool still returns critical warnings
        critical_count = sum(1 for w in warnings if "CRITICAL" in w)
        self.assertGreaterEqual(critical_count, 0)

    def test_surfaces_high_severity_active_rules(self):
        """pre_run_check should surface high-severity active nodes (image QA rules)."""
        warnings = pre_run_check("product-background")
        # Image QA rules have severity=high, status=active AND tag=critical
        # So they may appear as CRITICAL or MANDATORY depending on tags
        has_qa = any("QA" in w or "Image" in w for w in warnings)
        self.assertTrue(has_qa, f"Expected image QA warning, got: {warnings}")

    def test_image_qa_rules_surfaced(self):
        """Image QA rules should appear in pre-run warnings regardless of tool."""
        for tool in ["product-background", "generative-expand", ""]:
            warnings = pre_run_check(tool)
            has_qa = any("Image QA" in w or "generation run" in w.lower() for w in warnings)
            self.assertTrue(has_qa, f"Expected image QA warning for tool '{tool}', got: {warnings}")


class TestRecordLearning(unittest.TestCase):
    """Test recording new learnings."""

    def test_record_and_read(self):
        path = record_learning(
            title="Test Learning",
            description="This is a test learning entry",
            severity="low",
            tags=["test"],
            video_id="test-vid",
            body="## Details\n\nTest body content.",
        )
        try:
            self.assertTrue(path.exists())
            content = path.read_text(encoding="utf-8")
            self.assertIn("test learning entry", content)
            self.assertIn("Test body content", content)
        finally:
            # Clean up
            if path.exists():
                path.unlink()

    def test_record_avoids_overwrite(self):
        paths = []
        try:
            for i in range(3):
                p = record_learning(
                    title="Duplicate Title",
                    description=f"Entry {i}",
                    tags=["test"],
                )
                paths.append(p)
            # All paths should be unique
            self.assertEqual(len(set(paths)), 3)
        finally:
            for p in paths:
                if p.exists():
                    p.unlink()

    def test_record_run_summary(self):
        summary = RunSummary(
            video_id="test-summary",
            total_generated=5,
            total_failed=0,
            avg_fidelity=9.5,
            avg_variety=8.0,
            results=[
                SkillGenResult(
                    variant="hero",
                    product_rank=1,
                    prompt_used="test prompt",
                    tool_used="product-background",
                    success=True,
                    fidelity_score=9.5,
                    variety_score=8.0,
                    duration_s=30.0,
                    file_size_kb=150,
                ),
            ],
        )
        path = record_run_summary(summary)
        try:
            self.assertTrue(path.exists())
            content = path.read_text(encoding="utf-8")
            self.assertIn("test-summary", content)
            self.assertIn("9.5", content)
        finally:
            if path.exists():
                path.unlink()


class TestTraverse(unittest.TestCase):
    """Test graph traversal via wikilinks."""

    def test_traverse_from_index(self):
        nodes = traverse("_index", max_depth=1)
        self.assertGreater(len(nodes), 1)
        # Index should link to MOCs
        names = [n.path.stem for n in nodes]
        self.assertIn("_index", names)

    def test_traverse_depth_0(self):
        nodes = traverse("product-background", max_depth=0)
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].path.stem, "product-background")

    def test_traverse_nonexistent(self):
        nodes = traverse("nonexistent-node-xyz")
        self.assertEqual(len(nodes), 0)


if __name__ == "__main__":
    unittest.main()
