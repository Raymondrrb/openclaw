#!/usr/bin/env python3
"""Phase 161: Deep exploration of the Character tool in Dzine canvas.

Second pass — now that we know the DOM structure from the first run:
- The Character sidebar click opens "Consistent Character" (CC) panel directly
- "Build Your Character" and "Manage Your Characters" are in a hidden collapse-panel
- "Insert Character" is a separate c-gen-config panel
- "Character Sheet" is a separate c-gen-config panel
- "Generate 360 Video" is a separate c-gen-config panel
- A "Quick Mode" overlay appears on first open

Key findings from first run:
- Ray character EXISTS (2 slots used out of 60)
- Characters listed: Lip Boy, Cat Girl, Cow Cat, Richy, Anna (presets) + "Quick Ray" + "Ray"
- Generate button ID: character2img-generate-btn
- Prompt placeholder: 'Descreva o que voce quer criar com o personagem' (1800 char limit)
- Preset prompts: Walk, Read, Wave
- Control modes: Camera, Pose, Reference
- Aspect ratios: 3:4, 1:1, 4:3, canvas (1536x864)
- Generation modes: Fast, Normal, HQ (4 credits normal)
- Camera settings: Auto/Auto (Character Direction + Camera Shot)
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

SHOT_DIR = "/tmp/dzine_explore_161"


def ss(page, name):
    path = f"{SHOT_DIR}/{name}.png"
    page.screenshot(path=path)
    print(f"  Screenshot: {name}", flush=True)


def close_quick_mode_popup(page):
    """Close the Quick Mode popup that overlays the CC panel."""
    closed = page.evaluate("""() => {
        // The Quick Mode overlay is a button.opt at ~(416,245) 296x400
        // Try to close it or click away
        var overlay = document.querySelector('button.opt');
        if (overlay) {
            var r = overlay.getBoundingClientRect();
            if (r.width > 200 && r.height > 200) {
                // Click outside it or press escape
                return {found: true, x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
            }
        }
        return {found: false};
    }""")
    if closed['found']:
        print(f"  Quick Mode overlay at ({closed['x']},{closed['y']}) {closed['w']}x{closed['h']}")
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
    return closed['found']


def dump_all_buttons(page, label, *, x_min=60, x_max=500, y_min=50, y_max=900):
    """Extract all buttons/clickable elements in a region."""
    buttons = page.evaluate(f"""() => {{
        var items = [];
        for (var el of document.querySelectorAll('button, [role="button"], a, [class*="btn"]')) {{
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (r.width > 0 && r.height > 0 && r.x >= {x_min} && r.x < {x_max} &&
                r.y >= {y_min} && r.y < {y_max}) {{
                items.push({{
                    text: text.substring(0, 100).replace(/\\n/g, ' | '),
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cls: (el.className || '').substring(0, 80),
                    id: el.id || '',
                    disabled: el.disabled || false
                }});
            }}
        }}
        var unique = [], seen = new Set();
        for (var item of items) {{
            var key = item.text.substring(0, 30) + '|' + item.y;
            if (!seen.has(key)) {{ seen.add(key); unique.push(item); }}
        }}
        return unique.sort((a, b) => a.y - b.y);
    }}""")
    print(f"\n[{label}] Found {len(buttons)} buttons/clickable:")
    for b in buttons:
        dis = " [DISABLED]" if b['disabled'] else ""
        id_str = f" id={b['id']}" if b['id'] else ""
        print(f"  ({b['x']},{b['y']}) {b['w']}x{b['h']} <{b['tag']}> '{b['text'][:70]}' cls={b['cls'][:50]}{id_str}{dis}")
    return buttons


def dump_inputs(page, label, *, x_min=60, x_max=500, y_min=50, y_max=900):
    """Extract all input/textarea/contenteditable elements."""
    inputs = page.evaluate(f"""() => {{
        var items = [];
        for (var el of document.querySelectorAll('input, textarea, [contenteditable="true"]')) {{
            var r = el.getBoundingClientRect();
            if (r.width > 0 && r.height > 0 && r.x >= {x_min} && r.x < {x_max} &&
                r.y >= {y_min} && r.y < {y_max}) {{
                items.push({{
                    tag: el.tagName,
                    type: el.type || '',
                    placeholder: (el.placeholder || el.getAttribute('data-placeholder') || '').substring(0, 80),
                    value: (el.value || el.innerText || '').substring(0, 100),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cls: (el.className || '').substring(0, 60),
                    id: el.id || '',
                    maxLength: el.maxLength || -1
                }});
            }}
        }}
        return items.sort((a, b) => a.y - b.y);
    }}""")
    print(f"\n[{label}] Found {len(inputs)} inputs:")
    for inp in inputs:
        id_str = f" id={inp['id']}" if inp['id'] else ""
        print(f"  ({inp['x']},{inp['y']}) {inp['w']}x{inp['h']} <{inp['tag']}> type={inp['type']} ph='{inp['placeholder'][:50]}' val='{inp['value'][:40]}' cls={inp['cls'][:40]}{id_str}")
    return inputs


def show_hidden_panel(page, panel_class_fragment, label):
    """Force-show a hidden c-gen-config panel by toggling display."""
    result = page.evaluate(f"""() => {{
        // Find the panel
        for (var el of document.querySelectorAll('.c-gen-config')) {{
            var text = el.innerText || '';
            if (text.includes('{panel_class_fragment}')) {{
                // Temporarily show it
                var oldDisplay = el.style.display;
                el.style.display = 'block';
                el.classList.add('show');
                return {{
                    text: text.substring(0, 500).replace(/\\n/g, ' | '),
                    cls: (el.className || '').substring(0, 80),
                    oldDisplay: oldDisplay
                }};
            }}
        }}
        return null;
    }}""")
    if result:
        print(f"\n[{label}] Panel found: cls={result['cls'][:60]}")
        print(f"  Content: {result['text'][:300]}")
    else:
        print(f"\n[{label}] Panel NOT found")
    return result


def main():
    from playwright.sync_api import sync_playwright
    from tools.lib.brave_profile import DEFAULT_CDP_PORT, is_browser_running
    from tools.lib.dzine_browser import close_all_dialogs, VIEWPORT, SIDEBAR

    os.makedirs(SHOT_DIR, exist_ok=True)

    print("=" * 70)
    print("PHASE 161 (Pass 2): Character Tool Deep Exploration")
    print("=" * 70)

    if not is_browser_running():
        print("[P161] ERROR: Brave browser not running on CDP port 18800.")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        # Find Dzine canvas page
        dzine_pages = [p for p in context.pages if "dzine.ai/canvas" in (p.url or "")]
        if dzine_pages:
            page = dzine_pages[0]
            print(f"[P161] Reusing canvas tab: {page.url}")
        else:
            print("[P161] No canvas tab found, opening new one...")
            page = context.new_page()
            page.goto("https://www.dzine.ai/canvas?id=19797967", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)

        page.set_viewport_size(VIEWPORT)
        page.bring_to_front()
        page.wait_for_timeout(2000)

        n_closed = close_all_dialogs(page)
        print(f"[P161] Closed {n_closed} dialogs")

        # Close any open panels
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('.c-gen-config.show .ico-close')) el.click();
        }""")
        page.wait_for_timeout(500)

        # ============================================================
        # 1. OPEN CC PANEL (Character sidebar)
        # ============================================================
        print(f"\n{'='*70}")
        print("1. OPEN CONSISTENT CHARACTER PANEL")
        print(f"{'='*70}")

        char_pos = SIDEBAR["character"]
        print(f"[1] Clicking Character sidebar at {char_pos}")
        page.mouse.click(*char_pos)
        page.wait_for_timeout(2500)
        close_all_dialogs(page)

        # Close Quick Mode popup if it appeared
        close_quick_mode_popup(page)
        page.wait_for_timeout(500)

        ss(page, "01_cc_panel")

        # Check if we see the CC panel or "Please select a layer"
        panel_header = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            var header = panel.querySelector('.gen-config-header h5, .gen-config-header .title');
            return {
                panelCls: (panel.className || '').substring(0, 80),
                headerText: header ? (header.innerText || '').trim() : 'N/A',
                fullText: (panel.innerText || '').substring(0, 200).replace(/\\n/g, ' | ')
            };
        }""")
        print(f"[1a] Panel header: {panel_header}")

        # ============================================================
        # 2. CHARACTER CHOOSER — List all characters
        # ============================================================
        print(f"\n{'='*70}")
        print("2. CHARACTER CHOOSER — ALL CHARACTERS")
        print(f"{'='*70}")

        # The character chooser is the popup that appears at x=360+ (right side of CC panel)
        # It's activated by clicking "Choose a Character" button
        chooser = page.evaluate("""() => {
            var el = document.querySelector('#consistent-character-choose');
            if (el) {
                var r = el.getBoundingClientRect();
                el.click();
                return {text: (el.innerText || '').trim(), x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width)};
            }
            return null;
        }""")
        print(f"[2a] Chooser button: {chooser}")
        page.wait_for_timeout(1500)

        ss(page, "02_character_chooser")

        # Extract all characters from the chooser popup
        characters = page.evaluate("""() => {
            var items = [];
            // The advance panel contains character items
            var advance = document.querySelector('.c-character .advance');
            if (!advance) return items;

            for (var el of advance.querySelectorAll('button.item, .item')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 0 && r.height > 0) {
                    // Check for images
                    var img = el.querySelector('img');
                    var imgSrc = img ? (img.src || '').substring(0, 120) : '';
                    // Check if selected
                    var selected = el.className.includes('active') || el.className.includes('selected');
                    items.push({
                        text: text.replace(/\\n/g, ' | '),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 60),
                        imgSrc: imgSrc,
                        selected: selected
                    });
                }
            }
            return items;
        }""")
        print(f"\n[2b] Characters in chooser: {len(characters)}")
        for c in characters:
            sel = " [SELECTED]" if c['selected'] else ""
            img = f" img=...{c['imgSrc'][-40:]}" if c['imgSrc'] else ""
            print(f"  ({c['x']},{c['y']}) {c['w']}x{c['h']} '{c['text'][:50]}' cls={c['cls'][:40]}{sel}{img}")

        # Get the full chooser popup details
        chooser_popup = page.evaluate("""() => {
            var advance = document.querySelector('.c-character .advance');
            if (!advance) return null;
            var r = advance.getBoundingClientRect();
            return {
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                text: (advance.innerText || '').substring(0, 500).replace(/\\n/g, ' | '),
                cls: (advance.className || '').substring(0, 60)
            };
        }""")
        print(f"\n[2c] Chooser popup: {chooser_popup}")

        # Specifically check "Build your character" button within the chooser
        build_btn = page.evaluate("""() => {
            var btn = document.querySelector('.btn-add');
            if (btn) {
                var r = btn.getBoundingClientRect();
                return {text: (btn.innerText || '').trim(), x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), cls: (btn.className || '').substring(0, 60)};
            }
            return null;
        }""")
        print(f"\n[2d] Build character button: {build_btn}")

        # Check slots info
        slots = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text.includes('Slots Used') && el.childElementCount === 0) {
                    return text;
                }
            }
            return null;
        }""")
        print(f"[2e] Slots: {slots}")

        # ============================================================
        # 3. SELECT RAY CHARACTER — Examine its details
        # ============================================================
        print(f"\n{'='*70}")
        print("3. SELECT RAY CHARACTER")
        print(f"{'='*70}")

        # Click on the Ray character button (the one that says just "Ray", not "Quick | Ray")
        ray_clicked = page.evaluate("""() => {
            var advance = document.querySelector('.c-character .advance');
            if (!advance) return null;
            for (var el of advance.querySelectorAll('button.item')) {
                var text = (el.innerText || '').trim();
                // Look for "Ray" but not "Quick | Ray"
                if (text === 'Ray' || text === 'Ray\\nRay') {
                    var r = el.getBoundingClientRect();
                    el.click();
                    return {text: text.replace(/\\n/g, ' | '), x: Math.round(r.x), y: Math.round(r.y), cls: (el.className || '').substring(0, 60)};
                }
            }
            // Fallback: click any Ray
            for (var el of advance.querySelectorAll('button.item')) {
                var text = (el.innerText || '').trim();
                if (text.includes('Ray') && !text.includes('Quick')) {
                    var r = el.getBoundingClientRect();
                    el.click();
                    return {text: text.replace(/\\n/g, ' | '), x: Math.round(r.x), y: Math.round(r.y), cls: (el.className || '').substring(0, 60), fallback: true};
                }
            }
            return null;
        }""")
        print(f"[3a] Clicked Ray: {ray_clicked}")
        page.wait_for_timeout(1500)

        ss(page, "03_ray_selected")

        # Check what the panel shows now after selecting Ray
        after_select = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            var charEl = panel.querySelector('#consistent-character-choose');
            var charText = charEl ? (charEl.innerText || '').trim() : '';
            var warning = panel.querySelector('.warning-text');
            var warnText = warning ? (warning.innerText || '').trim() : '';
            var genBtn = panel.querySelector('#character2img-generate-btn');
            var genText = genBtn ? (genBtn.innerText || '').trim() : '';
            var genDisabled = genBtn ? genBtn.disabled : true;
            return {
                charSelected: charText,
                warning: warnText,
                generateBtn: genText,
                generateDisabled: genDisabled
            };
        }""")
        print(f"[3b] After selecting Ray: {after_select}")

        # ============================================================
        # 4. CC PANEL — FULL GENERATION OPTIONS MAP
        # ============================================================
        print(f"\n{'='*70}")
        print("4. CC PANEL — FULL GENERATION OPTIONS")
        print(f"{'='*70}")

        # Map every section of the CC panel
        full_map = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            var form = panel.querySelector('.gen-config-form');
            if (!form) return null;

            var sections = [];
            for (var param of form.querySelectorAll('.config-param, .character-prompt-content, .c-character, .btn-generate')) {
                var r = param.getBoundingClientRect();
                if (r.width === 0) continue;

                var section = {
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cls: (param.className || '').substring(0, 60),
                    children: []
                };

                // Get direct text content
                for (var child of param.querySelectorAll('*')) {
                    var cr = child.getBoundingClientRect();
                    var text = '';
                    for (var node of child.childNodes) {
                        if (node.nodeType === 3) text += (node.textContent || '').trim() + ' ';
                    }
                    text = text.trim();
                    if (cr.width > 0 && text.length > 0 && text.length < 60) {
                        section.children.push({
                            text: text,
                            tag: child.tagName,
                            x: Math.round(cr.x), y: Math.round(cr.y),
                            w: Math.round(cr.width), h: Math.round(cr.height),
                            cls: (child.className || '').substring(0, 50),
                            id: child.id || ''
                        });
                    }
                }
                sections.push(section);
            }
            return sections;
        }""")
        if full_map:
            print(f"[4] Sections: {len(full_map)}")
            for i, section in enumerate(full_map):
                print(f"\n  Section {i}: ({section['x']},{section['y']}) {section['w']}x{section['h']} cls={section['cls'][:40]}")
                for child in section['children']:
                    id_str = f" id={child['id']}" if child['id'] else ""
                    print(f"    ({child['x']},{child['y']}) {child['w']}x{child['h']} <{child['tag']}> '{child['text']}' cls={child['cls'][:30]}{id_str}")

        # ============================================================
        # 5. PROMPT AREA DETAILS
        # ============================================================
        print(f"\n{'='*70}")
        print("5. PROMPT AREA DETAILS")
        print(f"{'='*70}")

        prompt_details = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;

            var prompt = panel.querySelector('.character-prompt');
            if (!prompt) return null;
            var r = prompt.getBoundingClientRect();

            var textarea = prompt.querySelector('[contenteditable], textarea');
            var ta = textarea ? {
                tag: textarea.tagName,
                x: Math.round(textarea.getBoundingClientRect().x),
                y: Math.round(textarea.getBoundingClientRect().y),
                w: Math.round(textarea.getBoundingClientRect().width),
                h: Math.round(textarea.getBoundingClientRect().height),
                cls: (textarea.className || '').substring(0, 60),
                placeholder: (textarea.placeholder || textarea.getAttribute('data-placeholder') || '').substring(0, 80),
                maxLen: textarea.maxLength || parseInt(textarea.className.match(/len-(\\d+)/)?.[1]) || -1
            } : null;

            var presetBtns = [];
            for (var btn of prompt.querySelectorAll('.preset-prompt-btn')) {
                presetBtns.push((btn.innerText || '').trim());
            }

            var tipsLink = prompt.querySelector('[class*="tips"], [class*="hint"]');
            var tips = tipsLink ? (tipsLink.innerText || '').trim() : null;

            return {
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                textarea: ta,
                presetPrompts: presetBtns,
                tips: tips,
                charCount: prompt.querySelector('[class*="count"]') ?
                    (prompt.querySelector('[class*="count"]').innerText || '').trim() : null
            };
        }""")
        print(f"[5] Prompt area: {json.dumps(prompt_details, indent=2)}")

        # ============================================================
        # 6. CONTROL MODE (Camera/Pose/Reference)
        # ============================================================
        print(f"\n{'='*70}")
        print("6. CONTROL MODE — Camera, Pose, Reference")
        print(f"{'='*70}")

        control_modes = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;

            var modes = [];
            for (var btn of panel.querySelectorAll('.options')) {
                var r = btn.getBoundingClientRect();
                var text = (btn.innerText || '').trim();
                if (r.y > 350 && r.y < 420 && r.width > 0) {
                    modes.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        selected: btn.className.includes('selected'),
                        cls: (btn.className || '').substring(0, 40)
                    });
                }
            }
            return modes;
        }""")
        print(f"[6a] Control modes: {json.dumps(control_modes, indent=2)}")

        # Click Camera and get its options
        print("\n[6b] Camera panel details:")
        cam_btn = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            var btn = panel.querySelector('.camera-movement-btn');
            if (btn) { btn.click(); return true; }
            return false;
        }""")
        page.wait_for_timeout(1500)

        camera_panel = page.evaluate("""() => {
            var panel = document.querySelector('.c2i-camera-movement-panel');
            if (!panel) return null;
            var r = panel.getBoundingClientRect();
            if (r.width === 0) return null;

            var sections = {};
            var currentSection = '';
            for (var el of panel.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var cr = el.getBoundingClientRect();
                if (cr.width === 0) continue;

                if (el.className.includes('panel-title') || el.className.includes('section-title')) {
                    currentSection = text;
                    if (!sections[currentSection]) sections[currentSection] = [];
                }
                else if (el.childElementCount === 0 && text.length > 0 && text.length < 30 && cr.x > 360) {
                    if (!currentSection) currentSection = 'Other';
                    if (!sections[currentSection]) sections[currentSection] = [];
                    var isActive = el.className.includes('active') || el.className.includes('selected');
                    sections[currentSection].push({text: text, active: isActive});
                }
            }
            return {
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                text: (panel.innerText || '').substring(0, 500).replace(/\\n/g, ' | '),
                sections: sections
            };
        }""")
        if camera_panel:
            print(f"  Position: ({camera_panel['x']},{camera_panel['y']}) {camera_panel['w']}x{camera_panel['h']}")
            print(f"  Full text: {camera_panel['text'][:300]}")
            for section, items in camera_panel.get('sections', {}).items():
                print(f"  Section '{section}':")
                for item in items:
                    act = " [ACTIVE]" if item['active'] else ""
                    print(f"    - {item['text']}{act}")
        else:
            # Maybe the panel uses different class
            alt_panel = page.evaluate("""() => {
                for (var el of document.querySelectorAll('[class*="camera-movement"]')) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 100) {
                        return {text: (el.innerText || '').substring(0, 500).replace(/\\n/g, ' | '), cls: (el.className || '').substring(0, 60)};
                    }
                }
                return null;
            }""")
            print(f"  Alt camera panel: {alt_panel}")

        ss(page, "06_camera_panel")

        # Close camera panel
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # ============================================================
        # 7. CLICK POSE TAB
        # ============================================================
        print(f"\n{'='*70}")
        print("7. POSE CONTROL MODE")
        print(f"{'='*70}")

        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            for (var btn of panel.querySelectorAll('.options')) {
                if ((btn.innerText || '').trim() === 'Pose') { btn.click(); return true; }
            }
            return false;
        }""")
        page.wait_for_timeout(1000)

        pose_details = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            // Check what changed in the control area
            var controlArea = panel.querySelector('.camera-movement-wrapper');
            if (!controlArea) return null;
            var r = controlArea.getBoundingClientRect();
            return {
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                text: (controlArea.innerText || '').trim().replace(/\\n/g, ' | ')
            };
        }""")
        print(f"[7] Pose details: {pose_details}")

        ss(page, "07_pose_mode")

        # ============================================================
        # 8. CLICK REFERENCE TAB
        # ============================================================
        print(f"\n{'='*70}")
        print("8. REFERENCE CONTROL MODE")
        print(f"{'='*70}")

        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            for (var btn of panel.querySelectorAll('.options')) {
                if ((btn.innerText || '').trim() === 'Reference') { btn.click(); return true; }
            }
            return false;
        }""")
        page.wait_for_timeout(1000)

        ref_details = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            var controlArea = panel.querySelector('.camera-movement-wrapper');
            if (controlArea) {
                var r = controlArea.getBoundingClientRect();
                return {
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: (controlArea.innerText || '').trim().replace(/\\n/g, ' | ')
                };
            }
            // Broader search
            var params = panel.querySelectorAll('.config-param');
            for (var p of params) {
                var text = (p.innerText || '').trim();
                if (text.includes('Reference') || text.includes('Upload') || text.includes('Pick')) {
                    var r = p.getBoundingClientRect();
                    return {text: text.replace(/\\n/g, ' | '), x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
                }
            }
            return null;
        }""")
        print(f"[8] Reference details: {ref_details}")

        ss(page, "08_reference_mode")

        # Switch back to Camera
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            for (var btn of panel.querySelectorAll('.options')) {
                if ((btn.innerText || '').trim() === 'Camera') { btn.click(); return true; }
            }
            return false;
        }""")
        page.wait_for_timeout(500)

        # ============================================================
        # 9. ASPECT RATIO OPTIONS
        # ============================================================
        print(f"\n{'='*70}")
        print("9. ASPECT RATIO OPTIONS")
        print(f"{'='*70}")

        ratios = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return [];
            var ratioArea = panel.querySelector('.c-aspect-ratio');
            if (!ratioArea) return [];

            var items = [];
            for (var el of ratioArea.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 0 && text.length > 0 && text.length < 20 && el.childElementCount === 0) {
                    items.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        selected: el.className.includes('selected') || el.className.includes('active') || el.className.includes('canvas'),
                        cls: (el.className || '').substring(0, 40)
                    });
                }
            }
            // Deduplicate
            var unique = [], seen = new Set();
            for (var item of items) {
                if (!seen.has(item.text)) { seen.add(item.text); unique.push(item); }
            }
            return unique;
        }""")
        print(f"[9] Aspect ratios: {len(ratios)}")
        for r in ratios:
            sel = " [SELECTED]" if r['selected'] else ""
            print(f"  ({r['x']},{r['y']}) {r['w']}x{r['h']} '{r['text']}' cls={r['cls'][:30]}{sel}")

        # ============================================================
        # 10. STYLE OPTION
        # ============================================================
        print(f"\n{'='*70}")
        print("10. STYLE & OTHER OPTIONS")
        print(f"{'='*70}")

        style_and_options = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;

            var result = {style: null, nonExplicit: null, switches: []};

            // Find Style section
            for (var param of panel.querySelectorAll('.config-param')) {
                var text = (param.innerText || '').trim();
                if (text.includes('Style')) {
                    var r = param.getBoundingClientRect();
                    // Get the style icon/button
                    var styleIcon = param.querySelector('.ico-style');
                    var styleBtn = param.querySelector('button, [class*="style"]');
                    result.style = {
                        text: text.replace(/\\n/g, ' | '),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        hasNew: text.includes('NEW')
                    };
                }
                if (text.includes('Non-Explicit')) {
                    result.nonExplicit = text;
                }
            }

            // Find switches
            for (var sw of panel.querySelectorAll('.switch, [class*="switch"]')) {
                var r = sw.getBoundingClientRect();
                if (r.width > 0 && r.x > 200) {
                    var isOn = sw.className.includes('isChecked') || sw.className.includes('on') || sw.className.includes('active');
                    // Find label for this switch
                    var parent = sw.closest('.config-param') || sw.closest('.group');
                    var label = parent ? (parent.querySelector('.group span, .group div')?.innerText || '').trim() : '';
                    result.switches.push({
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        isOn: isOn,
                        label: label.substring(0, 40),
                        cls: (sw.className || '').substring(0, 40)
                    });
                }
            }

            return result;
        }""")
        print(f"[10] Style & options: {json.dumps(style_and_options, indent=2)}")

        # ============================================================
        # 11. GENERATION MODE OPTIONS (Fast/Normal/HQ)
        # ============================================================
        print(f"\n{'='*70}")
        print("11. GENERATION MODE & GENERATE BUTTON")
        print(f"{'='*70}")

        gen_modes = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;

            var modeArea = panel.querySelector('#cc-config-param-fast-mode');
            if (!modeArea) {
                // Fallback: look for Fast/Normal/HQ buttons
                var modes = [];
                for (var btn of panel.querySelectorAll('.options')) {
                    var text = (btn.innerText || '').trim();
                    if (['Fast', 'Normal', 'HQ'].includes(text)) {
                        var r = btn.getBoundingClientRect();
                        modes.push({
                            text: text,
                            x: Math.round(r.x), y: Math.round(r.y),
                            selected: btn.className.includes('selected'),
                            cls: (btn.className || '').substring(0, 40)
                        });
                    }
                }
                return {modes: modes};
            }

            var r = modeArea.getBoundingClientRect();
            var modes = [];
            for (var btn of modeArea.querySelectorAll('.options, button')) {
                var text = (btn.innerText || '').trim();
                if (text.length > 0 && text.length < 10) {
                    modes.push({
                        text: text,
                        selected: btn.className.includes('selected'),
                        cls: (btn.className || '').substring(0, 40)
                    });
                }
            }

            // Generate button
            var genBtn = panel.querySelector('#character2img-generate-btn');
            var gen = genBtn ? {
                text: (genBtn.innerText || '').trim().replace(/\\n/g, ' '),
                disabled: genBtn.disabled,
                x: Math.round(genBtn.getBoundingClientRect().x),
                y: Math.round(genBtn.getBoundingClientRect().y),
                w: Math.round(genBtn.getBoundingClientRect().width),
                h: Math.round(genBtn.getBoundingClientRect().height),
                id: genBtn.id,
                cls: (genBtn.className || '').substring(0, 60)
            } : null;

            // Warning text
            var warn = panel.querySelector('.warning-text');
            var warnText = warn ? (warn.innerText || '').trim() : null;

            return {
                x: Math.round(r.x), y: Math.round(r.y),
                modes: modes,
                generateBtn: gen,
                warning: warnText
            };
        }""")
        print(f"[11] Generation config: {json.dumps(gen_modes, indent=2)}")

        # Test each mode to check credits
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
            print(f"  {mode}: Generate button = '{credits}'")

        # ============================================================
        # 12. HIDDEN PANELS — BUILD YOUR CHARACTER
        # ============================================================
        print(f"\n{'='*70}")
        print("12. BUILD YOUR CHARACTER (hidden collapse-panel)")
        print(f"{'='*70}")

        # The "Build Your Character" / "Manage Your Characters" are in a collapse-panel
        # that contains "Character" header. Let's examine its content from the DOM.
        build_panel = page.evaluate("""() => {
            for (var el of document.querySelectorAll('.c-gen-config.collapse-panel')) {
                var headerText = '';
                var header = el.querySelector('.gen-config-header');
                if (header) headerText = (header.innerText || '').trim();
                if (headerText === 'Character') {
                    return {
                        header: headerText,
                        fullText: (el.innerText || '').substring(0, 1000).replace(/\\n/g, ' | '),
                        cls: (el.className || '').substring(0, 80)
                    };
                }
            }
            return null;
        }""")
        print(f"[12a] Character collapse-panel: {json.dumps(build_panel, indent=2) if build_panel else 'NOT FOUND'}")

        # Extract the collapse panel items
        collapse_items = page.evaluate("""() => {
            for (var el of document.querySelectorAll('.c-gen-config.collapse-panel')) {
                var header = el.querySelector('.gen-config-header');
                if (header && (header.innerText || '').trim() === 'Character') {
                    var items = [];
                    var content = el.querySelector('.collapse-config-panel');
                    if (content) {
                        for (var child of content.querySelectorAll('*')) {
                            var text = (child.innerText || '').trim();
                            if (child.childElementCount === 0 && text.length > 0 && text.length < 60) {
                                items.push({
                                    text: text,
                                    tag: child.tagName,
                                    cls: (child.className || '').substring(0, 60),
                                    clickable: child.tagName === 'BUTTON' || child.tagName === 'A' ||
                                        window.getComputedStyle(child).cursor === 'pointer'
                                });
                            }
                        }
                    }
                    return items;
                }
            }
            return [];
        }""")
        print(f"\n[12b] Character menu items: {len(collapse_items)}")
        for item in collapse_items:
            click = " [CLICKABLE]" if item['clickable'] else ""
            print(f"  <{item['tag']}> '{item['text']}' cls={item['cls'][:40]}{click}")

        # Try to open "Build Your Character" via the collapse panel
        print("\n[12c] Opening Build Your Character...")
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('.collapse-config-panel *')) {
                var text = (el.innerText || '').trim();
                if (text === 'Build Your Character' && el.childElementCount <= 1) {
                    el.click();
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(2000)
        close_all_dialogs(page)

        # Check what opened
        build_view = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            var header = panel.querySelector('.gen-config-header h5, .gen-config-header .title');
            return {
                header: header ? (header.innerText || '').trim() : 'N/A',
                fullText: (panel.innerText || '').substring(0, 500).replace(/\\n/g, ' | '),
                cls: (panel.className || '').substring(0, 80)
            };
        }""")
        print(f"[12d] After clicking Build: {json.dumps(build_view, indent=2) if build_view else 'NOTHING'}")

        ss(page, "12_build_character")

        # ============================================================
        # 13. HIDDEN PANELS — MANAGE YOUR CHARACTERS
        # ============================================================
        print(f"\n{'='*70}")
        print("13. MANAGE YOUR CHARACTERS")
        print(f"{'='*70}")

        # Go back to CC panel
        page.evaluate("""() => {
            // Click back button if visible
            var back = document.querySelector('.c-gen-config.show .back');
            if (back) { back.click(); return true; }
            return false;
        }""")
        page.wait_for_timeout(1000)

        # Try clicking Manage Your Characters
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('.collapse-config-panel *, .c-gen-config *')) {
                var text = (el.innerText || '').trim();
                if (text === 'Manage Your Characters' && el.childElementCount <= 1) {
                    el.click();
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(2000)
        close_all_dialogs(page)

        manage_view = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            var header = panel.querySelector('.gen-config-header h5, .gen-config-header .title');
            return {
                header: header ? (header.innerText || '').trim() : 'N/A',
                fullText: (panel.innerText || '').substring(0, 800).replace(/\\n/g, ' | '),
                cls: (panel.className || '').substring(0, 80)
            };
        }""")
        print(f"[13a] Manage panel: {json.dumps(manage_view, indent=2) if manage_view else 'NOTHING'}")

        ss(page, "13_manage_characters")

        # ============================================================
        # 14. HIDDEN PANELS — INSERT CHARACTER (from DOM)
        # ============================================================
        print(f"\n{'='*70}")
        print("14. INSERT CHARACTER PANEL (DOM examination)")
        print(f"{'='*70}")

        insert_panel = page.evaluate("""() => {
            for (var el of document.querySelectorAll('.c-gen-config')) {
                var text = (el.innerText || '').trim();
                if (text.startsWith('Insert Character')) {
                    // Parse structure
                    var children = [];
                    for (var child of el.querySelectorAll('*')) {
                        var t = (child.innerText || '').trim();
                        if (child.childElementCount === 0 && t.length > 0 && t.length < 50) {
                            children.push({
                                text: t, tag: child.tagName,
                                cls: (child.className || '').substring(0, 40),
                                id: child.id || ''
                            });
                        }
                    }
                    return {
                        cls: (el.className || '').substring(0, 80),
                        text: text.substring(0, 500).replace(/\\n/g, ' | '),
                        children: children
                    };
                }
            }
            return null;
        }""")
        print(f"[14] Insert Character panel:")
        if insert_panel:
            print(f"  cls: {insert_panel['cls']}")
            print(f"  text: {insert_panel['text'][:300]}")
            print(f"  Children ({len(insert_panel['children'])}):")
            for c in insert_panel['children'][:30]:
                id_str = f" id={c['id']}" if c['id'] else ""
                print(f"    <{c['tag']}> '{c['text']}' cls={c['cls'][:30]}{id_str}")

        # ============================================================
        # 15. HIDDEN PANELS — CHARACTER SHEET (from DOM)
        # ============================================================
        print(f"\n{'='*70}")
        print("15. CHARACTER SHEET PANEL (DOM examination)")
        print(f"{'='*70}")

        sheet_panel = page.evaluate("""() => {
            for (var el of document.querySelectorAll('.c-gen-config')) {
                var header = el.querySelector('.gen-config-header');
                var hText = header ? (header.innerText || '').trim() : '';
                if (hText === 'Character Sheet') {
                    var children = [];
                    for (var child of el.querySelectorAll('*')) {
                        var t = (child.innerText || '').trim();
                        if (child.childElementCount === 0 && t.length > 0 && t.length < 50) {
                            children.push({
                                text: t, tag: child.tagName,
                                cls: (child.className || '').substring(0, 40),
                                id: child.id || ''
                            });
                        }
                    }
                    return {
                        cls: (el.className || '').substring(0, 80),
                        text: (el.innerText || '').substring(0, 500).replace(/\\n/g, ' | '),
                        children: children
                    };
                }
            }
            return null;
        }""")
        print(f"[15] Character Sheet panel:")
        if sheet_panel:
            print(f"  cls: {sheet_panel['cls']}")
            print(f"  text: {sheet_panel['text'][:300]}")
            print(f"  Children ({len(sheet_panel['children'])}):")
            for c in sheet_panel['children'][:30]:
                id_str = f" id={c['id']}" if c['id'] else ""
                print(f"    <{c['tag']}> '{c['text']}' cls={c['cls'][:30]}{id_str}")

        # ============================================================
        # 16. HIDDEN PANELS — GENERATE 360 VIDEO (from DOM)
        # ============================================================
        print(f"\n{'='*70}")
        print("16. GENERATE 360 VIDEO PANEL (DOM examination)")
        print(f"{'='*70}")

        video360_panel = page.evaluate("""() => {
            for (var el of document.querySelectorAll('.c-gen-config')) {
                var header = el.querySelector('.gen-config-header');
                var hText = header ? (header.innerText || '').trim() : '';
                if (hText.includes('360')) {
                    var children = [];
                    for (var child of el.querySelectorAll('*')) {
                        var t = (child.innerText || '').trim();
                        if (child.childElementCount === 0 && t.length > 0 && t.length < 50) {
                            children.push({
                                text: t, tag: child.tagName,
                                cls: (child.className || '').substring(0, 40),
                                id: child.id || ''
                            });
                        }
                    }
                    return {
                        cls: (el.className || '').substring(0, 80),
                        text: (el.innerText || '').substring(0, 500).replace(/\\n/g, ' | '),
                        children: children
                    };
                }
            }
            return null;
        }""")
        print(f"[16] Generate 360 Video panel:")
        if video360_panel:
            print(f"  cls: {video360_panel['cls']}")
            print(f"  text: {video360_panel['text'][:300]}")
            print(f"  Children ({len(video360_panel['children'])}):")
            for c in video360_panel['children'][:30]:
                id_str = f" id={c['id']}" if c['id'] else ""
                print(f"    <{c['tag']}> '{c['text']}' cls={c['cls'][:30]}{id_str}")

        # ============================================================
        # 17. NAVIGATE TO BUILD/MANAGE via sidebar menu
        # ============================================================
        print(f"\n{'='*70}")
        print("17. ACCESS BUILD/MANAGE VIA CHARACTER SIDEBAR CLICK")
        print(f"{'='*70}")

        # First close current panel
        page.evaluate("""() => {
            var close = document.querySelector('.c-gen-config.show .ico-close');
            if (close) close.click();
        }""")
        page.wait_for_timeout(500)

        # Click Character sidebar icon
        page.mouse.click(*char_pos)
        page.wait_for_timeout(2500)
        close_all_dialogs(page)

        # Now check what panel opened
        opened = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show, .panels.show');
            if (!panel) return null;
            var header = panel.querySelector('.gen-config-header h5, .gen-config-header .title, h5');
            return {
                header: header ? (header.innerText || '').trim() : 'N/A',
                cls: (panel.className || '').substring(0, 80),
                preview: (panel.innerText || '').substring(0, 200).replace(/\\n/g, ' | ')
            };
        }""")
        print(f"[17a] Opened panel: {opened}")

        # Check if the "Character" collapse panel is accessible from the CC panel
        # It might be a "back" navigation
        has_back = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return false;
            var back = panel.querySelector('.back');
            if (back) {
                var r = back.getBoundingClientRect();
                return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width)};
            }
            return false;
        }""")
        print(f"[17b] Back button: {has_back}")

        if has_back:
            print("[17c] Clicking back button...")
            page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                var back = panel.querySelector('.back');
                if (back) back.click();
            }""")
            page.wait_for_timeout(1500)

            after_back = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show, .panels.show');
                if (!panel) return null;
                var header = panel.querySelector('.gen-config-header h5, .gen-config-header .title, h5');
                return {
                    header: header ? (header.innerText || '').trim() : 'N/A',
                    cls: (panel.className || '').substring(0, 80),
                    preview: (panel.innerText || '').substring(0, 400).replace(/\\n/g, ' | ')
                };
            }""")
            print(f"[17d] After back: {after_back}")
            ss(page, "17_after_back")

            # Look for Build/Manage buttons in this view
            build_manage = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show, .panels.show');
                if (!panel) return [];
                var items = [];
                for (var el of panel.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if ((text === 'Build Your Character' || text === 'Manage Your Characters' ||
                         text.includes('Generate Images') || text.includes('Insert Character') ||
                         text.includes('Character Sheet') || text.includes('360')) &&
                        el.childElementCount <= 2) {
                        var r = el.getBoundingClientRect();
                        if (r.width > 0) {
                            items.push({
                                text: text.substring(0, 60),
                                tag: el.tagName,
                                x: Math.round(r.x), y: Math.round(r.y),
                                w: Math.round(r.width), h: Math.round(r.height),
                                cls: (el.className || '').substring(0, 60),
                                clickable: el.tagName === 'BUTTON' || window.getComputedStyle(el).cursor === 'pointer'
                            });
                        }
                    }
                }
                return items;
            }""")
            print(f"\n[17e] Build/Manage buttons in view: {len(build_manage)}")
            for bm in build_manage:
                click = " [CLICKABLE]" if bm['clickable'] else ""
                print(f"  ({bm['x']},{bm['y']}) {bm['w']}x{bm['h']} <{bm['tag']}> '{bm['text']}' cls={bm['cls'][:40]}{click}")

            # Click "Build Your Character" if found
            if build_manage:
                for bm in build_manage:
                    if 'Build' in bm['text']:
                        print(f"\n[17f] Clicking 'Build Your Character'...")
                        page.mouse.click(bm['x'] + bm['w'] // 2, bm['y'] + bm['h'] // 2)
                        page.wait_for_timeout(2000)
                        close_all_dialogs(page)

                        build_opened = page.evaluate("""() => {
                            var panel = document.querySelector('.c-gen-config.show, .panels.show');
                            if (!panel) return null;
                            var header = panel.querySelector('.gen-config-header h5, .gen-config-header .title, h5');
                            return {
                                header: header ? (header.innerText || '').trim() : 'N/A',
                                cls: (panel.className || '').substring(0, 80),
                                preview: (panel.innerText || '').substring(0, 500).replace(/\\n/g, ' | ')
                            };
                        }""")
                        print(f"[17g] Build panel opened: {json.dumps(build_opened, indent=2) if build_opened else 'NOTHING'}")
                        ss(page, "17_build_opened")

                        dump_all_buttons(page, "17h-build-buttons")
                        dump_inputs(page, "17i-build-inputs")

                        # Look for upload/file input in build panel
                        build_uploads = page.evaluate("""() => {
                            var panel = document.querySelector('.c-gen-config.show');
                            if (!panel) return null;
                            var items = [];
                            for (var el of panel.querySelectorAll('[class*="upload"], [class*="drop"], input[type="file"]')) {
                                var r = el.getBoundingClientRect();
                                items.push({
                                    tag: el.tagName,
                                    cls: (el.className || '').substring(0, 60),
                                    text: (el.innerText || '').trim().substring(0, 80),
                                    x: Math.round(r.x), y: Math.round(r.y),
                                    w: Math.round(r.width), h: Math.round(r.height)
                                });
                            }
                            return items;
                        }""")
                        print(f"\n[17j] Upload elements in Build: {build_uploads}")
                        break

            # Go back and try "Manage Your Characters"
            page.evaluate("""() => {
                var back = document.querySelector('.c-gen-config.show .back');
                if (back) back.click();
            }""")
            page.wait_for_timeout(1000)

            for bm in build_manage:
                if 'Manage' in bm['text']:
                    print(f"\n[17k] Clicking 'Manage Your Characters'...")
                    page.mouse.click(bm['x'] + bm['w'] // 2, bm['y'] + bm['h'] // 2)
                    page.wait_for_timeout(2000)
                    close_all_dialogs(page)

                    manage_opened = page.evaluate("""() => {
                        var panel = document.querySelector('.c-gen-config.show, .panels.show');
                        if (!panel) return null;
                        var header = panel.querySelector('.gen-config-header h5, .gen-config-header .title, h5');

                        // Look for character list
                        var chars = [];
                        for (var el of panel.querySelectorAll('[class*="item"], [class*="card"], [class*="character"]')) {
                            var r = el.getBoundingClientRect();
                            var text = (el.innerText || '').trim();
                            if (r.width > 40 && r.height > 40 && text.length > 0 && text.length < 60 && r.x > 60 && r.x < 400) {
                                var img = el.querySelector('img');
                                chars.push({
                                    text: text.replace(/\\n/g, ' | '),
                                    x: Math.round(r.x), y: Math.round(r.y),
                                    w: Math.round(r.width), h: Math.round(r.height),
                                    hasImg: !!img,
                                    imgSrc: img ? (img.src || '').substring(0, 100) : ''
                                });
                            }
                        }

                        return {
                            header: header ? (header.innerText || '').trim() : 'N/A',
                            cls: (panel.className || '').substring(0, 80),
                            preview: (panel.innerText || '').substring(0, 500).replace(/\\n/g, ' | '),
                            characters: chars
                        };
                    }""")
                    print(f"[17l] Manage panel: {json.dumps(manage_opened, indent=2) if manage_opened else 'NOTHING'}")
                    ss(page, "17_manage_opened")
                    break

        # ============================================================
        # SUMMARY
        # ============================================================
        print(f"\n{'='*70}")
        print("PHASE 161 — COMPLETE CHARACTER TOOL MAP")
        print(f"{'='*70}")

        summary = """
CHARACTER TOOL ARCHITECTURE
============================

Sidebar Icon: (40, 306) — opens "Consistent Character" (CC) panel
Panel class: .c-gen-config.show.float-c2i-gen-btn

NAVIGATION:
  - Character sidebar click → CC generation panel (main view)
  - Back button (top-left) → Character menu (collapse-panel)
  - Character menu has: Build Your Character, Manage Your Characters
  - Sub-tools: Insert Character, Character Sheet, Generate 360 Video (separate panels)

CC GENERATION PANEL (main view):
  Header: "Consistent Character"
  Panel ID: character2img-generate-btn-panel
  Form ID: character2img-generate-btn-form

  1. CHARACTER CHOOSER (top)
     - Button: #consistent-character-choose (.character-choose.active)
     - Opens: .c-character .advance (dropdown at x=360+)
     - Content: Character list + "Slots Used: 2 / 60"
     - "Build your character" button (.btn-add) at top of list
     - Presets: Lip Boy, Cat Girl, Cow Cat, Richy, Anna
     - Custom: "Quick | Ray" (Quick mode), "Ray" (full character)
     - Expand popup: .switch-popup.ico-maximize button

  2. PROMPT AREA
     - Container: .character-prompt-content
     - Title: "Character Action & Scene"
     - Textarea: div[contenteditable].custom-textarea.len-1800
     - Placeholder: 'Descreva o que voce quer criar com o personagem'
     - Char limit: 1800
     - Preset prompts: Walk, Read, Wave (.preset-prompt-btn)
     - "Tips for writing better prompts" link

  3. CONTROL MODE (.config-param at y~350)
     - Three tabs: Camera | Pose | Reference (.options buttons)
     - Default: Camera (selected)
     - Camera: .camera-movement-btn → opens .c2i-camera-movement-panel
       - Character Direction: Auto, Front View, Back View, Left View, Right View
       - Camera Shot: Auto, Closeup, Half Body, Full Body
     - Pose: Upload a pose reference image
     - Reference: Upload a reference image

  4. ASPECT RATIO (.c-aspect-ratio at y~498)
     - Default size: 1536x864
     - Options: 3:4 | 1:1 | 4:3 | canvas [selected]

  5. STYLE (y~586)
     - Style icon (.ico-style) — opens style picker (same as Txt2Img)
     - "NEW" badge
     - Has its own style-list-panel with consistent-character category

  6. NON-EXPLICIT (y~634)
     - Toggle switch (content safety filter)

  7. GENERATION MODE (#cc-config-param-fast-mode at y~682)
     - Fast | Normal [default] | HQ
     - Credits: 4 (all modes)

  8. GENERATE BUTTON
     - Button: #character2img-generate-btn (.generative.ready)
     - Position: (92, 771) 240x48
     - Text: "Generate 4" (4 credits)
     - Disabled when no character selected
     - Warning: "Please choose a character." when none selected

SUB-PANELS:
  - Build Your Character: Accessed via back → Character menu
  - Manage Your Characters: Accessed via back → Character menu
  - Insert Character: .float-insert-character-gen-btn (has Lasso/Brush/Auto selection + character chooser)
  - Character Sheet: .float-cs-gen-btn (style: Dzine 3D Render v2, ratios: 16:9/2:1/4:3, Face Match NEW)
  - Generate 360 Video: Pick image + Duration 5s/10s, 6 credits

Screenshots: /tmp/dzine_explore_161/
"""
        print(summary)

    finally:
        pw.stop()


if __name__ == "__main__":
    main()
