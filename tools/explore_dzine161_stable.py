#!/usr/bin/env python3
"""Phase 161 (STABLE): Character Tool exploration — refactored with OutputGuard.

This is the reference example of how to write explore scripts without blowing
up context. Original: explore_dzine161.py (1390 lines, 9 json.dumps calls,
2 dump_* functions, unbounded stdout).

Refactored patterns:
  BEFORE: print(f"[5] Prompt area: {json.dumps(prompt_details, indent=2)}")
  AFTER:  guard.write_artifact("prompt_details.json", prompt_details)
          guard.safe_print(f"[5] Prompt: textarea={prompt_details['textarea'] is not None}, presets={prompt_details.get('presetPrompts', [])}")

  BEFORE: dump_all_buttons(page, "build-buttons")  # prints every button
  AFTER:  guard.capture_elements(page, "build_buttons", selector="button", x_range=(60, 500))

  BEFORE: print(summary)  # 80-line summary string
  AFTER:  guard.write_artifact("summary.txt", summary)
          guard.safe_print("[DONE] Summary saved to summary.txt")

Run:
    python tools/stable_run.py --script explore_dzine161_stable.py --run-id dzine_161_stable
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))
_tools = Path(__file__).resolve().parent
if str(_tools) not in sys.path:
    sys.path.insert(0, str(_tools))

from lib.output_guard import OutputGuard


def close_quick_mode_popup(page, guard: OutputGuard):
    """Close the Quick Mode popup that overlays the CC panel."""
    closed = page.evaluate("""() => {
        var overlay = document.querySelector('button.opt');
        if (overlay) {
            var r = overlay.getBoundingClientRect();
            if (r.width > 200 && r.height > 200) {
                return {found: true, x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
            }
        }
        return {found: false};
    }""")
    if closed["found"]:
        guard.safe_print(f"  Quick Mode overlay at ({closed['x']},{closed['y']}) {closed['w']}x{closed['h']} — dismissing")
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
    return closed["found"]


def main():
    from playwright.sync_api import sync_playwright
    from lib.brave_profile import DEFAULT_CDP_PORT, is_browser_running
    from lib.dzine_browser import close_all_dialogs, VIEWPORT, SIDEBAR

    # ── Set up OutputGuard ───────────────────────────────────────────────
    run_id = os.environ.get("STABLE_RUN_ID", "dzine_161_stable")
    base_dir = os.environ.get("STABLE_RUN_BASE", str(_repo))
    guard = OutputGuard(run_id, base_dir=base_dir)

    guard.safe_print("=" * 60)
    guard.safe_print("PHASE 161 (STABLE): Character Tool Deep Exploration")
    guard.safe_print("=" * 60)

    if not is_browser_running():
        guard.safe_print("ERROR: Brave browser not running on CDP port 18800.")
        guard.finish(status="error", next_step="Start Brave with CDP on port 18800")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        # Find Dzine canvas page
        dzine_pages = [p for p in context.pages if "dzine.ai/canvas" in (p.url or "")]
        if dzine_pages:
            page = dzine_pages[0]
            guard.safe_print(f"Reusing canvas tab: {page.url[:80]}")
        else:
            guard.safe_print("No canvas tab found, opening new one...")
            page = context.new_page()
            page.goto("https://www.dzine.ai/canvas?id=19797967", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)

        page.set_viewport_size(VIEWPORT)
        page.bring_to_front()
        page.wait_for_timeout(2000)

        n_closed = close_all_dialogs(page)
        guard.safe_print(f"Closed {n_closed} dialogs")

        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        # ── 1. Open CC Panel ─────────────────────────────────────────────
        guard.safe_print("\n[1] Opening Character sidebar...")
        char_pos = SIDEBAR["character"]
        page.mouse.click(*char_pos)
        page.wait_for_timeout(2500)
        close_all_dialogs(page)
        close_quick_mode_popup(page, guard)

        guard.screenshot(page, "01_cc_panel")

        panel_header = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            var header = panel.querySelector('.gen-config-header h5, .gen-config-header .title');
            return {
                panelCls: (panel.className || '').substring(0, 80),
                headerText: header ? (header.innerText || '').trim() : 'N/A'
            };
        }""")
        # BEFORE: print(f"[1a] Panel header: {panel_header}")
        # AFTER: compact summary + artifact
        guard.write_artifact("panel_header.json", panel_header)
        guard.safe_print(f"[1] Panel: {panel_header.get('headerText', '?') if panel_header else 'NOT FOUND'}")

        # ── 2. Character Chooser ─────────────────────────────────────────
        guard.safe_print("\n[2] Listing characters...")

        page.evaluate("""() => {
            var el = document.querySelector('#consistent-character-choose');
            if (el) el.click();
        }""")
        page.wait_for_timeout(1500)

        characters = page.evaluate("""() => {
            var items = [];
            var advance = document.querySelector('.c-character .advance');
            if (!advance) return items;
            for (var el of advance.querySelectorAll('button.item, .item')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 0 && r.height > 0) {
                    items.push({
                        text: text.replace(/\\n/g, ' | '),
                        selected: el.className.includes('active') || el.className.includes('selected')
                    });
                }
            }
            return items;
        }""")
        # BEFORE: print each character with full coords
        # AFTER: write full data to artifact, print compact list
        guard.write_artifact("characters.json", characters)
        names = [c["text"][:20] for c in characters]
        guard.safe_print(f"[2] {len(characters)} characters: {', '.join(names)}")

        slots = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text.includes('Slots Used') && el.childElementCount === 0) return text;
            }
            return null;
        }""")
        guard.safe_print(f"[2] {slots or 'Slots info not found'}")

        guard.screenshot(page, "02_characters")

        # ── 3. Select Ray ────────────────────────────────────────────────
        guard.safe_print("\n[3] Selecting Ray...")

        ray_clicked = page.evaluate("""() => {
            var advance = document.querySelector('.c-character .advance');
            if (!advance) return null;
            for (var el of advance.querySelectorAll('button.item')) {
                var text = (el.innerText || '').trim();
                if (text === 'Ray' || text === 'Ray\\nRay') {
                    el.click();
                    return {text: text.replace(/\\n/g, ' | ')};
                }
            }
            for (var el of advance.querySelectorAll('button.item')) {
                var text = (el.innerText || '').trim();
                if (text.includes('Ray') && !text.includes('Quick')) {
                    el.click();
                    return {text: text.replace(/\\n/g, ' | '), fallback: true};
                }
            }
            return null;
        }""")
        guard.safe_print(f"[3] Ray: {'clicked' if ray_clicked else 'NOT FOUND'} — {ray_clicked}")
        page.wait_for_timeout(1500)
        guard.screenshot(page, "03_ray_selected")

        # ── 4. Full panel map ────────────────────────────────────────────
        guard.safe_print("\n[4] Mapping CC panel sections...")

        full_map = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            var form = panel.querySelector('.gen-config-form');
            if (!form) return null;
            var sections = [];
            for (var param of form.querySelectorAll('.config-param, .character-prompt-content, .c-character, .btn-generate')) {
                var r = param.getBoundingClientRect();
                if (r.width === 0) continue;
                var childTexts = [];
                for (var child of param.querySelectorAll('*')) {
                    var cr = child.getBoundingClientRect();
                    var text = '';
                    for (var node of child.childNodes) {
                        if (node.nodeType === 3) text += (node.textContent || '').trim() + ' ';
                    }
                    text = text.trim();
                    if (cr.width > 0 && text.length > 0 && text.length < 60) {
                        childTexts.push(text);
                    }
                }
                sections.push({
                    y: Math.round(r.y), h: Math.round(r.height),
                    cls: (param.className || '').substring(0, 40),
                    labels: childTexts.slice(0, 10)
                });
            }
            return sections;
        }""")
        # BEFORE: print every section with every child (50+ lines)
        # AFTER: artifact + compact summary
        guard.write_artifact("panel_sections.json", full_map)
        if full_map:
            guard.safe_print(f"[4] {len(full_map)} sections mapped (see panel_sections.json)")
        else:
            guard.safe_print("[4] Panel map: EMPTY")

        # ── 5. Prompt area ───────────────────────────────────────────────
        guard.safe_print("\n[5] Checking prompt area...")

        prompt_details = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            var prompt = panel.querySelector('.character-prompt');
            if (!prompt) return null;
            var textarea = prompt.querySelector('[contenteditable], textarea');
            var presetBtns = [];
            for (var btn of prompt.querySelectorAll('.preset-prompt-btn')) {
                presetBtns.push((btn.innerText || '').trim());
            }
            return {
                hasTextarea: !!textarea,
                maxLen: textarea ? (textarea.maxLength || parseInt((textarea.className || '').match(/len-(\\d+)/)?.[1]) || -1) : -1,
                placeholder: textarea ? (textarea.placeholder || textarea.getAttribute('data-placeholder') || '').substring(0, 60) : '',
                presetPrompts: presetBtns
            };
        }""")
        # BEFORE: print(f"[5] Prompt area: {json.dumps(prompt_details, indent=2)}")
        # AFTER:
        guard.write_artifact("prompt_details.json", prompt_details)
        if prompt_details:
            guard.safe_print(f"[5] Prompt: maxLen={prompt_details['maxLen']}, presets={prompt_details['presetPrompts']}")

        # ── 6. Control modes ─────────────────────────────────────────────
        guard.safe_print("\n[6] Checking control modes...")

        control_modes = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return [];
            var modes = [];
            for (var btn of panel.querySelectorAll('.options')) {
                var text = (btn.innerText || '').trim();
                if (['Camera', 'Pose', 'Reference'].includes(text)) {
                    modes.push({text: text, selected: btn.className.includes('selected')});
                }
            }
            return modes;
        }""")
        # BEFORE: print(f"[6a] Control modes: {json.dumps(control_modes, indent=2)}")
        # AFTER:
        active = [m["text"] for m in control_modes if m.get("selected")]
        guard.safe_print(f"[6] Modes: {[m['text'] for m in control_modes]}, active={active}")

        # ── 7-8. Camera/Pose/Reference details ──────────────────────────
        # Click camera button and capture its options
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            var btn = panel.querySelector('.camera-movement-btn');
            if (btn) btn.click();
        }""")
        page.wait_for_timeout(1500)

        # BEFORE: 40-line camera_panel evaluate + print
        # AFTER: capture the panel text to artifact
        guard.capture_dom_text(page, "camera_panel", ".c2i-camera-movement-panel")
        guard.screenshot(page, "06_camera_panel")
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # ── 9. Aspect ratios ─────────────────────────────────────────────
        ratios = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return [];
            var items = [];
            var seen = new Set();
            for (var el of panel.querySelectorAll('.c-aspect-ratio *')) {
                var text = (el.innerText || '').trim();
                if (el.childElementCount === 0 && text.length > 0 && text.length < 20 && !seen.has(text)) {
                    seen.add(text);
                    items.push({text: text, selected: el.className.includes('selected') || el.className.includes('canvas')});
                }
            }
            return items;
        }""")
        selected_ratio = [r["text"] for r in ratios if r.get("selected")]
        guard.safe_print(f"[9] Ratios: {[r['text'] for r in ratios]}, selected={selected_ratio}")

        # ── 10-11. Style, generation modes, generate button ──────────────
        gen_config = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            var modes = [];
            for (var btn of panel.querySelectorAll('.options')) {
                var text = (btn.innerText || '').trim();
                if (['Fast', 'Normal', 'HQ'].includes(text)) {
                    modes.push({text: text, selected: btn.className.includes('selected')});
                }
            }
            var genBtn = panel.querySelector('#character2img-generate-btn');
            return {
                modes: modes,
                generateText: genBtn ? (genBtn.innerText || '').trim().replace(/\\n/g, ' ') : null,
                generateDisabled: genBtn ? genBtn.disabled : true
            };
        }""")
        guard.write_artifact("gen_config.json", gen_config)
        if gen_config:
            active_mode = [m["text"] for m in gen_config["modes"] if m.get("selected")]
            guard.safe_print(f"[11] Gen modes: {[m['text'] for m in gen_config['modes']]}, active={active_mode}")
            guard.safe_print(f"[11] Generate: '{gen_config['generateText']}', disabled={gen_config['generateDisabled']}")

        # Test each mode's credit cost
        for mode in ["Fast", "Normal", "HQ"]:
            page.evaluate(f"""() => {{
                var panel = document.querySelector('.c-gen-config.show');
                for (var btn of panel.querySelectorAll('.options')) {{
                    if ((btn.innerText || '').trim() === '{mode}') {{ btn.click(); return; }}
                }}
            }}""")
            page.wait_for_timeout(500)
            credits = page.evaluate("""() => {
                var btn = document.querySelector('#character2img-generate-btn');
                return btn ? (btn.innerText || '').trim().replace(/\\n/g, ' ') : null;
            }""")
            guard.safe_print(f"  {mode}: '{credits}'")

        # ── 12-16. Hidden panels (DOM examination) ───────────────────────
        guard.safe_print("\n[12-16] Examining hidden sub-panels...")

        for panel_name in ["Character", "Insert Character", "Character Sheet"]:
            panel_data = page.evaluate(f"""() => {{
                for (var el of document.querySelectorAll('.c-gen-config')) {{
                    var header = el.querySelector('.gen-config-header');
                    var hText = header ? (header.innerText || '').trim() : '';
                    var text = (el.innerText || '').trim();
                    if (hText === '{panel_name}' || text.startsWith('{panel_name}')) {{
                        return {{
                            header: hText,
                            cls: (el.className || '').substring(0, 60),
                            textLen: text.length,
                            preview: text.substring(0, 200).replace(/\\n/g, ' | ')
                        }};
                    }}
                }}
                return null;
            }}""")
            if panel_data:
                # BEFORE: print full JSON + all children
                # AFTER: artifact + one-line summary
                safe_name = panel_name.lower().replace(" ", "_")
                guard.write_artifact(f"panel_{safe_name}.json", panel_data)
                guard.safe_print(f"  [{panel_name}] found, {panel_data['textLen']} chars (see panel_{safe_name}.json)")
            else:
                guard.safe_print(f"  [{panel_name}] NOT FOUND in DOM")

        # ── 17. Build/Manage via sidebar ─────────────────────────────────
        guard.safe_print("\n[17] Navigating to Character menu via back button...")

        # Close + reopen
        page.evaluate("""() => {
            var close = document.querySelector('.c-gen-config.show .ico-close');
            if (close) close.click();
        }""")
        page.wait_for_timeout(500)
        page.mouse.click(*char_pos)
        page.wait_for_timeout(2500)
        close_all_dialogs(page)

        has_back = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return false;
            var back = panel.querySelector('.back');
            return !!back;
        }""")
        guard.safe_print(f"[17] Back button: {'found' if has_back else 'NOT FOUND'}")

        if has_back:
            page.evaluate("""() => {
                document.querySelector('.c-gen-config.show .back').click();
            }""")
            page.wait_for_timeout(1500)

            # BEFORE: dump_all_buttons(page, "build-buttons") — prints every button
            # AFTER:
            guard.capture_elements(page, "character_menu", selector="button", x_range=(60, 350))
            guard.screenshot(page, "17_character_menu")

        # ── Finish ───────────────────────────────────────────────────────
        guard.finish(
            status="completed",
            next_step="Character tool fully mapped. No further exploration needed.",
            script_name="explore_dzine161_stable.py",
        )

    except Exception as e:
        guard.safe_print(f"ERROR: {e}")
        guard.finish(
            status="error",
            next_step=f"Fix error: {e}",
            script_name="explore_dzine161_stable.py",
        )
        raise
    finally:
        pw.stop()


if __name__ == "__main__":
    main()
