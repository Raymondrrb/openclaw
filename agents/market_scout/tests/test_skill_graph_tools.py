#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN = ROOT / "scripts" / "skill_graph_scan.py"
LINT = ROOT / "scripts" / "graph_lint.py"
GRAPH = ROOT / "skill_graph"


class SkillGraphToolsTests(unittest.TestCase):
    def run_json(self, cmd: list[str]) -> dict:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        self.assertEqual(
            proc.returncode,
            0,
            msg=f"Command failed: {' '.join(cmd)}\nstdout={proc.stdout}\nstderr={proc.stderr}",
        )
        return json.loads(proc.stdout)

    def test_scan_finds_safety_nodes_for_compliance_task(self) -> None:
        out = self.run_json(
            [
                "python3",
                str(SCAN),
                "--graph-root",
                str(GRAPH),
                "--task",
                "gate1 compliance affiliate disclosure and injection",
                "--json",
            ]
        )
        ids = [n["id"] for n in out["nodes"]]
        self.assertIn("safety-compliance", ids)
        self.assertTrue(out["traversal"][0] == "index")

    def test_scan_fallback_when_task_has_no_matches(self) -> None:
        out = self.run_json(
            [
                "python3",
                str(SCAN),
                "--graph-root",
                str(GRAPH),
                "--task",
                "zxqv unrelated term",
                "--json",
            ]
        )
        ids = [n["id"] for n in out["nodes"]]
        self.assertIn("index", ids)

    def test_lint_detects_broken_link(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "index.md").write_text(
                textwrap.dedent(
                    """\
                    ---
                    id: index
                    title: Index
                    description: entry
                    tags: [index]
                    links: ["[[missing-node]]"]
                    ---

                    # Index
                    """
                ),
                encoding="utf-8",
            )
            proc = subprocess.run(
                ["python3", str(LINT), "--graph-root", str(root), "--json"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 1)
            payload = json.loads(proc.stdout)
            codes = [e["code"] for e in payload["errors"]]
            self.assertIn("broken_link", codes)


if __name__ == "__main__":
    unittest.main()
