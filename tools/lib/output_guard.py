#!/usr/bin/env python3
"""Output guard — prevents context explosions in Dzine exploration scripts.

Replaces raw print(json.dumps(…)) / print(dom) patterns with disk-backed
artifacts and compact stdout summaries.

Usage:
    from lib.output_guard import OutputGuard

    guard = OutputGuard("explore_dzine_162")
    guard.safe_print("Panel opened successfully")
    guard.write_artifact("buttons.json", buttons_data)
    guard.summarize_dom(dom_stats)
    guard.screenshot(page, "step_1")
    guard.capture_elements(page, "left_panel", selector="button", x_range=(60, 350))
    report = guard.finish()

Environment:
    RAY_TOKEN_MODE=1  — stricter caps (half limits), shorter summaries
"""

from __future__ import annotations

import gzip
import io
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _token_mode() -> bool:
    return os.environ.get("RAY_TOKEN_MODE", "") == "1"


class OutputGuard:
    """Disk-backed output guard with hard caps on stdout, artifacts, and DOM."""

    # ── Defaults (halved when RAY_TOKEN_MODE=1) ──────────────────────────
    _BASE_LIMITS = {
        "max_print_chars": 2000,
        "max_stdout_lines": 30,
        "max_screenshots": 10,
        "max_nodes": 5000,
        "max_selectors": 200,
        "max_artifact_bytes": 5 * 1024 * 1024,  # 5 MB
        "max_artifacts": 50,
    }

    def __init__(
        self,
        run_id: str,
        *,
        base_dir: str | Path | None = None,
    ):
        self.run_id = run_id
        self.started_at = datetime.now(timezone.utc).isoformat()
        self._start_ts = time.monotonic()

        # Resolve base directory
        if base_dir:
            self._base = Path(base_dir)
        else:
            self._base = Path(__file__).resolve().parent.parent.parent  # repo root

        # Output dirs
        self.artifacts_dir = self._base / "artifacts" / run_id
        self.logs_dir = self._base / "logs"
        self.runs_dir = self._base / "runs" / run_id

        for d in (self.artifacts_dir, self.logs_dir, self.runs_dir):
            d.mkdir(parents=True, exist_ok=True)

        # Limits
        strict = _token_mode()
        div = 2 if strict else 1
        self.limits = {k: v // div for k, v in self._BASE_LIMITS.items()}

        # Counters
        self._stdout_lines = 0
        self._screenshot_count = 0
        self._artifact_count = 0
        self._total_artifact_bytes = 0
        self._warnings: list[str] = []
        self._artifacts_manifest: list[dict] = []

        # Full log (always written to disk)
        self._log_path = self.logs_dir / f"{run_id}.log"
        self._log_file = open(self._log_path, "w", encoding="utf-8")
        self._log(f"=== OutputGuard run_id={run_id} started_at={self.started_at} ===")
        self._log(f"    token_mode={'STRICT' if strict else 'normal'}  limits={json.dumps(self.limits)}")

    # ── Core: safe_print ─────────────────────────────────────────────────

    def safe_print(self, text: str, *, max_chars: int | None = None) -> None:
        """Print to stdout with truncation. Always writes full text to log."""
        cap = max_chars or self.limits["max_print_chars"]

        # Always log full text to disk
        self._log(text)

        # Truncate for stdout
        if self._stdout_lines >= self.limits["max_stdout_lines"]:
            return  # silent — stdout cap reached

        lines = text.split("\n")
        for line in lines:
            if self._stdout_lines >= self.limits["max_stdout_lines"]:
                print(f"  [GUARD] stdout cap ({self.limits['max_stdout_lines']} lines) reached — rest in {self._log_path.name}")
                self._stdout_lines += 1
                return
            if len(line) > cap:
                line = line[:cap - 20] + f"… ({len(line)} chars, see log)"
            print(line, flush=True)
            self._stdout_lines += 1

    # ── Artifacts ────────────────────────────────────────────────────────

    def write_artifact(
        self,
        name: str,
        data: Any,
        *,
        compress: bool = False,
    ) -> Path | None:
        """Write artifact to disk. Returns path or None if cap exceeded."""
        if self._artifact_count >= self.limits["max_artifacts"]:
            w = f"Artifact cap ({self.limits['max_artifacts']}) reached, skipping: {name}"
            self._warn(w)
            return None

        # Serialize
        if isinstance(data, (dict, list)):
            raw = json.dumps(data, indent=2, ensure_ascii=False, default=str).encode("utf-8")
        elif isinstance(data, str):
            raw = data.encode("utf-8")
        elif isinstance(data, bytes):
            raw = data
        else:
            raw = str(data).encode("utf-8")

        # Size check
        if len(raw) > self.limits["max_artifact_bytes"]:
            compress = True  # force compression for oversized artifacts
            self._warn(f"Artifact '{name}' is {len(raw)} bytes — compressing")

        # Compress if needed or requested
        if compress or len(raw) > self.limits["max_artifact_bytes"]:
            compressed = gzip.compress(raw)
            if len(compressed) > self.limits["max_artifact_bytes"]:
                # Even compressed it's too big — truncate and mark partial
                compressed = gzip.compress(raw[: self.limits["max_artifact_bytes"]])
                name = f"PARTIAL_{name}"
                self._warn(f"Artifact '{name}' truncated to {self.limits['max_artifact_bytes']} bytes (pre-compress)")
            out_path = self.artifacts_dir / f"{name}.gz"
            out_path.write_bytes(compressed)
            size = len(compressed)
        else:
            out_path = self.artifacts_dir / name
            out_path.write_bytes(raw)
            size = len(raw)

        self._artifact_count += 1
        self._total_artifact_bytes += size
        self._artifacts_manifest.append({
            "name": out_path.name,
            "original_bytes": len(raw),
            "disk_bytes": size,
            "compressed": compress or out_path.suffix == ".gz",
        })

        self._log(f"Artifact: {out_path.name} ({size:,} bytes)")
        self.safe_print(f"  [artifact] {out_path.name} ({size:,} bytes)")
        return out_path

    # ── DOM helpers ──────────────────────────────────────────────────────

    def summarize_dom(self, dom_stats: dict) -> str:
        """Convert raw DOM stats dict into a compact one-line summary for stdout."""
        node_count = dom_stats.get("nodes", dom_stats.get("count", "?"))
        byte_count = dom_stats.get("bytes", dom_stats.get("size", "?"))
        tag = dom_stats.get("tag", dom_stats.get("selector", ""))
        summary = f"DOM: {node_count} nodes, {byte_count} bytes"
        if tag:
            summary += f" [{tag}]"

        # Write full stats to artifact
        self.write_artifact("dom_stats.json", dom_stats)
        self.safe_print(f"  {summary}")
        return summary

    def capture_elements(
        self,
        page,
        label: str,
        *,
        selector: str = "button, [role='button']",
        x_range: tuple[int, int] = (0, 1440),
        y_range: tuple[int, int] = (0, 900),
    ) -> list[dict]:
        """Extract elements from page, write full data to artifact, print compact summary."""
        max_nodes = self.limits["max_selectors"]
        x_min, x_max = x_range
        y_min, y_max = y_range

        elements = page.evaluate(f"""() => {{
            var items = [];
            for (var el of document.querySelectorAll('{selector}')) {{
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 0 && r.height > 0 &&
                    r.x >= {x_min} && r.x < {x_max} &&
                    r.y >= {y_min} && r.y < {y_max}) {{
                    items.push({{
                        text: text.substring(0, 80),
                        tag: el.tagName,
                        id: el.id || '',
                        cls: (typeof el.className === 'string' ? el.className : '').substring(0, 100),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height)
                    }});
                    if (items.length >= {max_nodes}) break;
                }}
            }}
            return items;
        }}""")

        # Write full data to artifact (never stdout)
        self.write_artifact(f"elements_{label}.json", elements)

        # Print compact summary only
        count = len(elements)
        capped = " (CAPPED)" if count >= max_nodes else ""
        self.safe_print(f"  [{label}] {count} elements{capped}")
        for el in elements[:5]:
            self.safe_print(f"    {el['tag']} \"{el['text'][:40]}\" ({el['x']},{el['y']}) {el['w']}x{el['h']}")
        if count > 5:
            self.safe_print(f"    … +{count - 5} more (see elements_{label}.json)")

        return elements

    def capture_dom_text(
        self,
        page,
        label: str,
        selector: str,
    ) -> str | None:
        """Extract innerText of a DOM node. Full text to artifact, truncated to stdout."""
        max_chars = self.limits["max_nodes"] * 10  # rough cap
        text = page.evaluate(f"""() => {{
            var el = document.querySelector('{selector}');
            if (!el) return null;
            return (el.innerText || '').substring(0, {max_chars});
        }}""")
        if text is None:
            self.safe_print(f"  [{label}] selector '{selector}' — NOT FOUND")
            return None

        self.write_artifact(f"dom_{label}.txt", text)
        preview = text[:200].replace("\n", " | ")
        self.safe_print(f"  [{label}] {len(text)} chars: {preview}…")
        return text

    # ── Screenshots ──────────────────────────────────────────────────────

    def screenshot(self, page, name: str) -> Path | None:
        """Take screenshot if under cap. Returns path or None."""
        if self._screenshot_count >= self.limits["max_screenshots"]:
            self._warn(f"Screenshot cap ({self.limits['max_screenshots']}) reached, skipping: {name}")
            return None

        path = self.artifacts_dir / f"{name}.png"
        page.screenshot(path=str(path))
        self._screenshot_count += 1
        remaining = self.limits["max_screenshots"] - self._screenshot_count
        self.safe_print(f"  [screenshot] {name}.png ({remaining} remaining)")
        self._artifacts_manifest.append({
            "name": f"{name}.png",
            "type": "screenshot",
        })
        return path

    # ── Checkpoint & Report ──────────────────────────────────────────────

    def finish(
        self,
        *,
        status: str = "completed",
        next_step: str = "",
        script_name: str = "",
        extra: dict | None = None,
    ) -> dict:
        """Write checkpoint.json + run_report.md. Call at end of script."""
        elapsed = round(time.monotonic() - self._start_ts, 1)
        finished_at = datetime.now(timezone.utc).isoformat()

        checkpoint = {
            "run_id": self.run_id,
            "script_name": script_name or self.run_id,
            "started_at": self.started_at,
            "finished_at": finished_at,
            "elapsed_seconds": elapsed,
            "status": status,
            "artifacts": self._artifacts_manifest,
            "warnings": self._warnings,
            "counters": {
                "stdout_lines": self._stdout_lines,
                "screenshots": self._screenshot_count,
                "artifacts": self._artifact_count,
                "total_artifact_bytes": self._total_artifact_bytes,
            },
            "next_step": next_step,
        }
        if extra:
            checkpoint["extra"] = extra

        # Write checkpoint
        cp_path = self.runs_dir / "checkpoint.json"
        cp_path.write_text(json.dumps(checkpoint, indent=2, ensure_ascii=False))

        # Write run report
        report_lines = [
            f"# Run Report: {self.run_id}",
            "",
            f"- **Status:** {status}",
            f"- **Duration:** {elapsed}s",
            f"- **Script:** {script_name or self.run_id}",
            f"- **Started:** {self.started_at}",
            f"- **Finished:** {finished_at}",
            "",
            "## Counters",
            f"- stdout lines: {self._stdout_lines}/{self.limits['max_stdout_lines']}",
            f"- screenshots: {self._screenshot_count}/{self.limits['max_screenshots']}",
            f"- artifacts: {self._artifact_count}/{self.limits['max_artifacts']}",
            f"- total artifact bytes: {self._total_artifact_bytes:,}",
            "",
        ]

        if self._warnings:
            report_lines.append("## Warnings")
            for w in self._warnings:
                report_lines.append(f"- {w}")
            report_lines.append("")

        if self._artifacts_manifest:
            report_lines.append("## Artifacts")
            for a in self._artifacts_manifest:
                if "disk_bytes" in a:
                    report_lines.append(f"- `{a['name']}` ({a['disk_bytes']:,} bytes)")
                else:
                    report_lines.append(f"- `{a['name']}`")
            report_lines.append("")

        if next_step:
            report_lines.append("## Next Step")
            report_lines.append(next_step)
            report_lines.append("")

        report_path = self.runs_dir / "run_report.md"
        report_path.write_text("\n".join(report_lines))

        # Close log
        self._log(f"=== Finished: status={status} elapsed={elapsed}s ===")
        self._log_file.close()

        # Final stdout summary
        print(f"\n{'=' * 60}", flush=True)
        print(f"  Run: {self.run_id}  status={status}  {elapsed}s", flush=True)
        print(f"  Screenshots: {self._screenshot_count}/{self.limits['max_screenshots']}", flush=True)
        print(f"  Artifacts: {self._artifact_count} ({self._total_artifact_bytes:,} bytes)", flush=True)
        if self._warnings:
            print(f"  Warnings: {len(self._warnings)}", flush=True)
        print(f"  Log: {self._log_path}", flush=True)
        print(f"  Report: {report_path}", flush=True)
        print(f"  Checkpoint: {cp_path}", flush=True)
        print(f"{'=' * 60}", flush=True)

        return checkpoint

    # ── Internal ─────────────────────────────────────────────────────────

    def _log(self, text: str) -> None:
        """Write to log file (always full, no truncation)."""
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self._log_file.write(f"[{ts}] {text}\n")
        self._log_file.flush()

    def _warn(self, msg: str) -> None:
        """Record warning, log it, print to stdout."""
        self._warnings.append(msg)
        self._log(f"WARNING: {msg}")
        self.safe_print(f"  [WARN] {msg}")
