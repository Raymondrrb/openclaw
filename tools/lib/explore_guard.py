#!/usr/bin/env python3
"""Exploration guard — prevents context explosions in Dzine exploration scripts.

Import this at the top of any explore_dzine*.py script and use its helpers
instead of raw print/screenshot/DOM-dump calls.

Usage:
    from lib.explore_guard import ExploreGuard
    guard = ExploreGuard("explore_dzine_162", max_screenshots=10, max_observations=50)
    guard.screenshot(page, "panel_open")
    guard.observe("button_found", {"text": "Generate", "x": 92, "y": 710})
    guard.dump_buttons(page, "left_panel", x_min=60, x_max=350)
    guard.finish()  # writes summary to disk
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


class ExploreGuard:
    """Caps screenshots, DOM dumps, and observations to prevent context overflow."""

    def __init__(
        self,
        run_name: str,
        *,
        max_screenshots: int = 10,
        max_observations: int = 50,
        max_dom_elements: int = 40,
        output_dir: str | None = None,
    ):
        self.run_name = run_name
        self.max_screenshots = max_screenshots
        self.max_observations = max_observations
        self.max_dom_elements = max_dom_elements

        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = Path(f"/tmp/dzine_{run_name}")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._screenshot_count = 0
        self._observation_count = 0
        self._observations: list[dict] = []
        self._start_time = time.time()

        # Write observations incrementally to this file
        self._obs_file = self.output_dir / "observations.jsonl"
        self._summary_file = self.output_dir / "summary.json"

    def screenshot(self, page, name: str) -> str | None:
        """Take a screenshot if under the cap. Returns path or None."""
        if self._screenshot_count >= self.max_screenshots:
            print(f"  [GUARD] Screenshot cap reached ({self.max_screenshots}), skipping: {name}")
            return None
        path = str(self.output_dir / f"{name}.png")
        page.screenshot(path=path)
        self._screenshot_count += 1
        remaining = self.max_screenshots - self._screenshot_count
        print(f"  Screenshot: {name} ({remaining} remaining)")
        return path

    def observe(self, key: str, data: dict | str | list) -> None:
        """Record an observation. Written to disk immediately, printed as compact summary."""
        if self._observation_count >= self.max_observations:
            print(f"  [GUARD] Observation cap reached ({self.max_observations}), skipping: {key}")
            return

        entry = {
            "key": key,
            "data": data,
            "t": round(time.time() - self._start_time, 1),
        }
        self._observations.append(entry)
        self._observation_count += 1

        # Write incrementally to disk (append)
        with open(self._obs_file, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # Print compact version (max 120 chars)
        compact = json.dumps(data, ensure_ascii=False)
        if len(compact) > 120:
            compact = compact[:117] + "..."
        print(f"  [{key}] {compact}")

    def dump_buttons(
        self,
        page,
        label: str,
        *,
        x_min: int = 60,
        x_max: int = 500,
        y_min: int = 50,
        y_max: int = 900,
    ) -> list[dict]:
        """Extract buttons in a region. Caps at max_dom_elements. Writes to file, prints summary only."""
        buttons = page.evaluate(f"""() => {{
            var items = [];
            for (var el of document.querySelectorAll('button, [role="button"]')) {{
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 0 && r.height > 0 && r.x >= {x_min} && r.x < {x_max} &&
                    r.y >= {y_min} && r.y < {y_max} && text.length > 0) {{
                    items.push({{
                        text: text.substring(0, 60).replace(/\\n/g, ' '),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').toString().substring(0, 80),
                        id: el.id || ''
                    }});
                    if (items.length >= {self.max_dom_elements}) break;
                }}
            }}
            return items;
        }}""")

        # Write full data to file
        dump_file = self.output_dir / f"buttons_{label}.json"
        with open(dump_file, "w") as f:
            json.dump(buttons, f, indent=2, ensure_ascii=False)

        # Print ONLY summary to stdout
        print(f"  [{label}] {len(buttons)} buttons found (saved to {dump_file.name})")
        for b in buttons[:5]:
            print(f"    - \"{b['text'][:40]}\" at ({b['x']},{b['y']}) {b['w']}x{b['h']}")
        if len(buttons) > 5:
            print(f"    ... and {len(buttons) - 5} more (see file)")

        self.observe(f"buttons_{label}", {"count": len(buttons), "file": str(dump_file.name)})
        return buttons

    def dump_dom_region(
        self,
        page,
        label: str,
        selector: str,
        *,
        max_chars: int = 2000,
    ) -> str | None:
        """Extract inner text of a DOM region. Caps output, writes full to file."""
        text = page.evaluate(f"""() => {{
            var el = document.querySelector('{selector}');
            if (!el) return null;
            return (el.innerText || '').substring(0, 5000);
        }}""")
        if text is None:
            print(f"  [{label}] selector '{selector}' not found")
            return None

        # Write full text to file
        text_file = self.output_dir / f"dom_{label}.txt"
        with open(text_file, "w") as f:
            f.write(text)

        # Print only truncated version
        short = text[:max_chars].replace("\n", " | ")
        if len(text) > max_chars:
            short += f"... ({len(text)} chars total, see {text_file.name})"
        print(f"  [{label}] {short}")

        self.observe(f"dom_{label}", {"chars": len(text), "file": str(text_file.name)})
        return text

    def finish(self) -> dict:
        """Write final summary to disk. Call at end of script."""
        elapsed = round(time.time() - self._start_time, 1)
        summary = {
            "run_name": self.run_name,
            "screenshots_taken": self._screenshot_count,
            "observations_recorded": self._observation_count,
            "elapsed_seconds": elapsed,
            "output_dir": str(self.output_dir),
            "files": [str(f.name) for f in sorted(self.output_dir.iterdir())],
        }
        with open(self._summary_file, "w") as f:
            json.dump(summary, f, indent=2)

        print(f"\n{'='*60}")
        print(f"  Run complete: {self.run_name}")
        print(f"  Screenshots: {self._screenshot_count}/{self.max_screenshots}")
        print(f"  Observations: {self._observation_count}/{self.max_observations}")
        print(f"  Time: {elapsed}s")
        print(f"  Output: {self.output_dir}")
        print(f"{'='*60}")
        return summary

    @property
    def can_screenshot(self) -> bool:
        return self._screenshot_count < self.max_screenshots

    @property
    def can_observe(self) -> bool:
        return self._observation_count < self.max_observations
