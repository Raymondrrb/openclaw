#!/usr/bin/env python3
"""Phase 158: AI Video panel — Deep exploration, Part 2.

Now that we know the AI Video panel structure, this script:
1. Opens AI Video panel
2. Dismisses popups ("Skip", "Not now")
3. Scrolls model dropdown to capture ALL models with credits
4. Explores Reference mode
5. Scrolls the panel to find ALL settings (duration, quality, ratio, camera)
6. Documents all selectors for automation

Saves screenshots to /tmp/dzine_explore_158/
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

OUT_DIR = Path("/tmp/dzine_explore_158")


def shot(page, name: str) -> str:
    path = str(OUT_DIR / f"{name}.png")
    page.screenshot(path=path)
    print(f"  [screenshot] {path}")
    return path


def close_popups(page):
    """Close any popups (Not now, Skip, etc.)."""
    for text in ["Skip", "Not now", "Close", "Never show again", "Got it", "Later"]:
        try:
            btn = page.locator(f'button:has-text("{text}")')
            if btn.count() > 0 and btn.first.is_visible(timeout=500):
                btn.first.click()
                page.wait_for_timeout(500)
                print(f"  [popup] Closed: '{text}'")
        except Exception:
            pass


def main():
    from playwright.sync_api import sync_playwright
    from tools.lib.brave_profile import DEFAULT_CDP_PORT, is_browser_running
    from tools.lib.dzine_browser import close_all_dialogs, VIEWPORT

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("PHASE 158 Part 2: AI Video Panel — Deep Exploration")
    print("=" * 70)

    if not is_browser_running():
        print("[P158] ERROR: Brave not running.")
        return

    pw = sync_playwright().start()
    findings = {}

    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        dzine_pages = [p for p in context.pages if "dzine.ai/canvas" in (p.url or "")]
        if dzine_pages:
            page = dzine_pages[0]
        else:
            page = context.new_page()
            page.goto("https://www.dzine.ai/canvas?id=19797967", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)

        page.set_viewport_size(VIEWPORT)
        page.bring_to_front()
        page.wait_for_timeout(2000)

        close_all_dialogs(page)
        close_popups(page)
        page.wait_for_timeout(500)

        # Close any panel
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        page.evaluate("""() => {
            var closes = document.querySelectorAll('.c-gen-config.show .ico-close');
            for (var c of closes) c.click();
        }""")
        page.wait_for_timeout(1000)

        # Click canvas center to deselect
        page.mouse.click(700, 450)
        page.wait_for_timeout(500)

        # ===============================================================
        # 1. OPEN AI VIDEO PANEL
        # ===============================================================
        print(f"\n{'='*60}")
        print("1. OPEN AI VIDEO")
        print(f"{'='*60}")

        # Click AI Video sidebar via JS for reliability
        opened = page.evaluate("""() => {
            for (var el of document.querySelectorAll('.tool-group')) {
                var span = el.querySelector('.txt');
                if (span && span.innerText.trim() === 'AI Video') {
                    el.click();
                    return 'clicked via JS';
                }
            }
            // Fallback: click text directly
            for (var el of document.querySelectorAll('*')) {
                if (el.innerText && el.innerText.trim() === 'AI Video' && el.childElementCount === 0) {
                    var parent = el.closest('.tool-group') || el.parentElement;
                    if (parent) { parent.click(); return 'clicked parent'; }
                    el.click();
                    return 'clicked text';
                }
            }
            return null;
        }""")
        print(f"[1] Click result: {opened}")
        page.wait_for_timeout(3000)
        close_popups(page)
        page.wait_for_timeout(500)

        # If JS click didn't work, try coordinate click
        title = page.evaluate("""() => {
            var h = document.querySelector('.c-gen-config.show h5');
            return h ? h.innerText.trim() : 'unknown';
        }""")
        if title != 'AI Video':
            print(f"[1] Panel shows '{title}', trying coordinate click...")
            page.mouse.click(40, 361)
            page.wait_for_timeout(3000)
            close_popups(page)
            title = page.evaluate("""() => {
                var h = document.querySelector('.c-gen-config.show h5');
                return h ? h.innerText.trim() : 'unknown';
            }""")

        print(f"[1] Panel: '{title}'")
        if title != 'AI Video':
            # Last resort: click multiple times in sidebar area
            for y in range(340, 380, 5):
                page.mouse.click(40, y)
                page.wait_for_timeout(1500)
                title = page.evaluate("""() => {
                    var h = document.querySelector('.c-gen-config.show h5');
                    return h ? h.innerText.trim() : 'unknown';
                }""")
                if title == 'AI Video':
                    print(f"[1] Found AI Video at y={y}")
                    break
            close_popups(page)

        if title != 'AI Video':
            print("[1] ERROR: Could not open AI Video panel. Aborting.")
            shot(page, "ERROR_state")
            return

        shot(page, "20_ai_video_opened")

        # ===============================================================
        # 2. KEY FRAME MODE — Current state
        # ===============================================================
        print(f"\n{'='*60}")
        print("2. KEY FRAME MODE — Visible settings")
        print(f"{'='*60}")

        # The Key Frame mode is selected by default
        # Document all visible elements
        kf_state = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            return {
                mode: (() => {
                    var sel = panel.querySelector('.c-options .options.selected');
                    return sel ? sel.innerText.trim() : 'unknown';
                })(),
                frameMode: (() => {
                    var active = panel.querySelector('.frame-mode-tab.active .frame-mode-tab-btn');
                    return active ? active.innerText.trim() : 'unknown';
                })(),
                model: (() => {
                    var sel = panel.querySelector('.selected-name-text');
                    return sel ? sel.innerText.trim() : 'unknown';
                })(),
                metadata: (() => {
                    var m = panel.querySelector('#video-metadata');
                    return m ? m.innerText.trim() : '';
                })(),
                generateBtn: (() => {
                    var g = panel.querySelector('#keyframe-generate-btn-i2v');
                    return g ? {text: g.innerText.trim(), disabled: g.disabled} : null;
                })(),
                credits: (() => {
                    var c = panel.querySelector('.video-credits-remain');
                    return c ? c.innerText.trim() : '';
                })()
            };
        }""")
        print(f"[2] State: {json.dumps(kf_state, indent=2)}")
        findings['key_frame_state'] = kf_state

        # ===============================================================
        # 3. MODEL DROPDOWN — Full list with scrolling
        # ===============================================================
        print(f"\n{'='*60}")
        print("3. MODEL DROPDOWN — Complete list")
        print(f"{'='*60}")

        # Click the model selector
        page.mouse.click(212, 450)  # Center of model selector area
        page.wait_for_timeout(2500)
        close_popups(page)
        page.wait_for_timeout(500)

        shot(page, "21_model_dropdown_open")

        # Check if model panel opened
        panel_check = page.evaluate("""() => {
            var panel = document.querySelector('#i2v-custom-selector-panel');
            if (panel) {
                var r = panel.getBoundingClientRect();
                return {visible: r.width > 0, w: Math.round(r.width), h: Math.round(r.height),
                        cls: (panel.className || '').substring(0, 80)};
            }
            return null;
        }""")
        print(f"[3a] Model panel: {panel_check}")

        # Get filter checkboxes at top
        filters = page.evaluate("""() => {
            var panel = document.querySelector('#i2v-custom-selector-panel');
            if (!panel) return [];
            var items = [];
            for (var el of panel.querySelectorAll('.header-check, [class*="filter"], label, [class*="check"]')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 0 && text.length > 0 && text.length < 50 && r.y < 120) {
                    items.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        cls: (el.className || '').substring(0, 40),
                        checked: el.querySelector('input:checked') !== null ||
                                 el.className.includes('checked') || el.className.includes('active')
                    });
                }
            }
            return items;
        }""")
        print(f"[3b] Filters: {len(filters)}")
        for f in filters:
            chk = " [CHECKED]" if f['checked'] else ""
            print(f"  ({f['x']},{f['y']}) '{f['text']}' cls={f['cls'][:30]}{chk}")
        findings['filters'] = filters

        # Get ALL model items
        all_models = page.evaluate("""() => {
            var panel = document.querySelector('#i2v-custom-selector-panel');
            if (!panel) return [];
            var items = [];
            for (var el of panel.querySelectorAll('.option-item')) {
                var name = '';
                var nameEl = el.querySelector('.item-name');
                if (nameEl) name = nameEl.innerText.trim();

                var desc = '';
                var descEl = el.querySelector('.desc-text');
                if (descEl) desc = descEl.innerText.trim();

                var labels = [];
                for (var lab of el.querySelectorAll('.item-label')) {
                    labels.push(lab.innerText.trim());
                }

                var tips = '';
                var tipsEl = el.querySelector('.item-tips');
                if (tipsEl) tips = tipsEl.innerText.trim();

                var isHot = el.querySelector('.item-hot') !== null;
                var selected = el.className.includes('selected') || el.className.includes('active');

                var r = el.getBoundingClientRect();
                items.push({
                    name: name,
                    credits: desc,
                    labels: labels,
                    tips: tips,
                    isHot: isHot,
                    selected: selected,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height)
                });
            }
            return items;
        }""")
        print(f"\n[3c] Models found: {len(all_models)}")
        for i, m in enumerate(all_models):
            sel = " [SELECTED]" if m['selected'] else ""
            hot = " HOT" if m['isHot'] else ""
            labels = ", ".join(m['labels']) if m['labels'] else ""
            print(f"  {i+1:2d}. {m['name']:<25s} {m['credits']:<30s} [{labels}]{hot}{sel}")
            if m['tips']:
                print(f"      -> {m['tips']}")
        findings['models'] = all_models

        # Scroll the model panel to find more
        more_found = page.evaluate("""() => {
            var panel = document.querySelector('#i2v-custom-selector-panel');
            if (!panel) return {scrollable: false};
            var body = panel.querySelector('.selector-panel-body') || panel;
            // Find scrollable child
            for (var el of [body, ...panel.querySelectorAll('*')]) {
                if (el.scrollHeight > el.clientHeight + 30) {
                    return {
                        scrollable: true,
                        scrollHeight: el.scrollHeight,
                        clientHeight: el.clientHeight,
                        cls: (el.className || '').substring(0, 60)
                    };
                }
            }
            return {scrollable: false, panelScrollH: panel.scrollHeight, panelClientH: panel.clientHeight};
        }""")
        print(f"\n[3d] Scroll info: {more_found}")

        if more_found.get('scrollable'):
            # Scroll down to find more models
            for step in range(5):
                page.evaluate(f"""() => {{
                    var panel = document.querySelector('#i2v-custom-selector-panel');
                    if (!panel) return;
                    var body = panel.querySelector('.selector-panel-body') || panel;
                    for (var el of [body, ...panel.querySelectorAll('*')]) {{
                        if (el.scrollHeight > el.clientHeight + 30) {{
                            el.scrollTop += 300;
                            return;
                        }}
                    }}
                }}""")
                page.wait_for_timeout(800)

                more = page.evaluate("""() => {
                    var panel = document.querySelector('#i2v-custom-selector-panel');
                    if (!panel) return [];
                    var items = [];
                    for (var el of panel.querySelectorAll('.option-item')) {
                        var nameEl = el.querySelector('.item-name');
                        if (nameEl) {
                            var name = nameEl.innerText.trim();
                            var descEl = el.querySelector('.desc-text');
                            var desc = descEl ? descEl.innerText.trim() : '';
                            var labels = [];
                            for (var lab of el.querySelectorAll('.item-label')) labels.push(lab.innerText.trim());
                            var tips = '';
                            var tipsEl = el.querySelector('.item-tips');
                            if (tipsEl) tips = tipsEl.innerText.trim();
                            items.push({name: name, credits: desc, labels: labels, tips: tips});
                        }
                    }
                    return items;
                }""")
                new_names = [m['name'] for m in more if m['name'] not in [x['name'] for x in all_models]]
                if new_names:
                    print(f"[3d] Scroll {step}: {len(new_names)} new models: {new_names}")
                    for m in more:
                        if m['name'] in new_names:
                            all_models.append(m)

            shot(page, "22_model_dropdown_scrolled")
            findings['models'] = all_models
            print(f"\n[3e] TOTAL MODELS: {len(all_models)}")
            for i, m in enumerate(all_models):
                labels = ", ".join(m.get('labels', [])) if m.get('labels') else ""
                print(f"  {i+1:2d}. {m['name']:<25s} {m.get('credits',''):<30s} [{labels}]")
                if m.get('tips'):
                    print(f"      -> {m['tips']}")

        # Close model dropdown
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # ===============================================================
        # 4. SCROLL THE PANEL — Find ALL settings below the fold
        # ===============================================================
        print(f"\n{'='*60}")
        print("4. PANEL SCROLL — All settings")
        print(f"{'='*60}")

        # First, scroll to the very top
        page.evaluate("""() => {
            var body = document.querySelector('.c-gen-config.show .gen-config-body');
            if (body) body.scrollTop = 0;
        }""")
        page.wait_for_timeout(500)

        # Get full panel content by scrolling
        all_panel_elements = []
        for step in range(10):
            page.evaluate(f"""() => {{
                var body = document.querySelector('.c-gen-config.show .gen-config-body');
                if (body) body.scrollTop = {step * 150};
            }}""")
            page.wait_for_timeout(600)

            elements = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return [];
                var items = [];
                for (var el of panel.querySelectorAll('*')) {
                    if (el.childElementCount > 0) continue;
                    var r = el.getBoundingClientRect();
                    if (r.width <= 0 || r.y < 49 || r.y > 700 || r.x > 350) continue;
                    var text = (el.innerText || el.value || el.placeholder || el.getAttribute('data-placeholder') || '').trim();
                    if (text.length === 0 || text.length > 200) continue;
                    items.push({
                        text: text,
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 50),
                        id: el.id || '',
                        active: el.className.includes('active') || el.className.includes('selected')
                    });
                }
                return items.sort((a, b) => a.y - b.y);
            }""")

            new_count = 0
            for e in elements:
                key = e['text'] + '|' + e['cls']
                if key not in [x['text'] + '|' + x['cls'] for x in all_panel_elements]:
                    all_panel_elements.append(e)
                    new_count += 1

            if step % 3 == 0:
                shot(page, f"23_panel_scroll_{step}")

        print(f"[4] Total unique elements: {len(all_panel_elements)}")
        # Group by semantic sections
        current_section = "header"
        for e in sorted(all_panel_elements, key=lambda x: x['text']):
            active = " [ACTIVE]" if e['active'] else ""
            tag = e['tag'].lower()
            if tag in ('h5', 'span') and e['w'] > 40:
                section_marker = " --- SECTION ---"
            else:
                section_marker = ""
            print(f"  <{tag}> '{e['text'][:60]}' cls={e['cls'][:30]} id={e['id'][:20]}{active}{section_marker}")

        findings['all_panel_elements'] = all_panel_elements

        # ===============================================================
        # 5. SPECIFIC SETTINGS EXTRACTION
        # ===============================================================
        print(f"\n{'='*60}")
        print("5. SPECIFIC SETTINGS")
        print(f"{'='*60}")

        # Scroll to settings area
        page.evaluate("""() => {
            var body = document.querySelector('.c-gen-config.show .gen-config-body');
            if (body) body.scrollTop = body.scrollHeight;
        }""")
        page.wait_for_timeout(800)
        shot(page, "24_panel_bottom")

        # Extract settings from FULL panel (including hidden/scrolled areas)
        settings = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};

            var result = {};

            // Sound toggle
            var soundToggles = [];
            for (var el of panel.querySelectorAll('[class*="sound"], [class*="audio"]')) {
                soundToggles.push({
                    text: (el.innerText || '').trim().substring(0, 80),
                    cls: (el.className || '').substring(0, 60)
                });
            }
            result.sound = soundToggles;

            // Aspect ratios
            var ratios = [];
            for (var btn of panel.querySelectorAll('.size-btn')) {
                ratios.push({
                    text: btn.innerText.trim(),
                    selected: btn.className.includes('selected'),
                    disabled: btn.disabled || btn.className.includes('disabled')
                });
            }
            result.aspectRatios = ratios;

            // Quality buttons
            var quality = [];
            for (var btn of panel.querySelectorAll('.quality-btn')) {
                quality.push({
                    text: btn.innerText.trim(),
                    selected: btn.className.includes('selected')
                });
            }
            result.quality = quality;

            // Duration buttons
            var durations = [];
            for (var btn of panel.querySelectorAll('.duration-btn')) {
                durations.push({
                    text: btn.innerText.trim(),
                    selected: btn.className.includes('selected')
                });
            }
            result.duration = durations;

            // Camera section
            var cameraNames = [];
            for (var el of panel.querySelectorAll('.camera-name')) {
                cameraNames.push(el.innerText.trim());
            }
            result.cinematicShots = cameraNames;

            var optionNames = [];
            for (var el of panel.querySelectorAll('.option-name')) {
                optionNames.push(el.innerText.trim());
            }
            result.freeSelectionMoves = optionNames;

            // Camera tabs
            var cameraTabs = [];
            for (var el of panel.querySelectorAll('.camera-tabs .tab, [class*="camera"] .tab')) {
                cameraTabs.push({
                    text: el.innerText.trim(),
                    selected: el.className.includes('selected')
                });
            }
            result.cameraTabs = cameraTabs;

            // Creativity/Balance slider
            var sliders = [];
            for (var el of panel.querySelectorAll('input[type="range"], input.number, .slider')) {
                var r = el.getBoundingClientRect();
                sliders.push({
                    type: el.type || 'div',
                    value: el.value || '',
                    min: el.min || '',
                    max: el.max || '',
                    cls: (el.className || '').substring(0, 40),
                    x: Math.round(r.x), y: Math.round(r.y)
                });
            }
            result.sliders = sliders;

            // Prompt text areas
            var prompts = [];
            for (var el of panel.querySelectorAll('textarea')) {
                prompts.push({
                    placeholder: (el.placeholder || '').substring(0, 100),
                    cls: (el.className || '').substring(0, 40),
                    maxLength: el.maxLength || 0
                });
            }
            result.prompts = prompts;

            // Negative prompt
            var negPrompts = [];
            for (var el of panel.querySelectorAll('textarea')) {
                var ph = (el.placeholder || '').toLowerCase();
                if (ph.includes('negative')) {
                    negPrompts.push({
                        placeholder: el.placeholder.substring(0, 100),
                        cls: (el.className || '').substring(0, 40)
                    });
                }
            }
            result.negativePrompts = negPrompts;

            return result;
        }""")
        print(f"\n[5] Settings:")
        print(f"  Aspect Ratios: {settings.get('aspectRatios', [])}")
        print(f"  Quality: {settings.get('quality', [])}")
        print(f"  Duration: {settings.get('duration', [])}")
        print(f"  Cinematic Shots: {settings.get('cinematicShots', [])}")
        print(f"  Free Selection Moves: {settings.get('freeSelectionMoves', [])}")
        print(f"  Camera Tabs: {settings.get('cameraTabs', [])}")
        print(f"  Sliders: {settings.get('sliders', [])}")
        print(f"  Sound: {settings.get('sound', [])}")
        print(f"  Prompts: {settings.get('prompts', [])}")
        print(f"  Negative Prompts: {settings.get('negativePrompts', [])}")
        findings['settings'] = settings

        # ===============================================================
        # 6. REFERENCE MODE
        # ===============================================================
        print(f"\n{'='*60}")
        print("6. REFERENCE MODE")
        print(f"{'='*60}")

        # Click Reference tab
        page.evaluate("""() => {
            var body = document.querySelector('.c-gen-config.show .gen-config-body');
            if (body) body.scrollTop = 0;
        }""")
        page.wait_for_timeout(500)

        page.evaluate("""() => {
            var btns = document.querySelectorAll('.c-gen-config.show .c-options .options');
            for (var btn of btns) {
                if (btn.innerText.trim() === 'Reference') {
                    btn.click();
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(2000)
        close_popups(page)
        page.wait_for_timeout(500)

        shot(page, "25_reference_mode")

        # Get Reference mode panel state
        ref_state = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            return {
                mode: (() => {
                    var sel = panel.querySelector('.c-options .options.selected');
                    return sel ? sel.innerText.trim() : 'unknown';
                })(),
                text: (panel.innerText || '').substring(0, 3000)
            };
        }""")
        print(f"[6a] Mode: {ref_state.get('mode')}")
        print(f"[6a] Panel text:")
        for line in (ref_state.get('text') or '').split('\n'):
            line = line.strip()
            if line:
                print(f"  | {line[:120]}")
        findings['reference_mode'] = ref_state

        # Reference mode elements
        ref_elements = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return [];
            var items = [];
            for (var el of panel.querySelectorAll('button, textarea, [contenteditable], input, .pick-image, [class*="upload"], [class*="frame"]')) {
                var r = el.getBoundingClientRect();
                if (r.width <= 0 || r.y < 49 || r.y > 800) continue;
                items.push({
                    tag: el.tagName,
                    text: (el.innerText || el.placeholder || el.getAttribute('data-placeholder') || '').trim().substring(0, 100),
                    cls: (el.className || '').substring(0, 60),
                    id: el.id || '',
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height)
                });
            }
            return items.sort((a, b) => a.y - b.y);
        }""")
        print(f"\n[6b] Reference mode elements: {len(ref_elements)}")
        for e in ref_elements:
            print(f"  ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag'].lower()}> '{e['text'][:60]}' cls={e['cls'][:40]} id={e['id']}")
        findings['reference_elements'] = ref_elements

        # Scroll Reference mode panel
        page.evaluate("""() => {
            var body = document.querySelector('.c-gen-config.show .gen-config-body');
            if (body) body.scrollTop = body.scrollHeight;
        }""")
        page.wait_for_timeout(800)
        shot(page, "26_reference_mode_bottom")

        ref_bottom = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return [];
            var items = [];
            for (var el of panel.querySelectorAll('*')) {
                if (el.childElementCount > 0) continue;
                var r = el.getBoundingClientRect();
                if (r.width <= 0 || r.y < 49 || r.y > 800 || r.x > 350) continue;
                var text = (el.innerText || el.value || el.placeholder || '').trim();
                if (text.length > 0 && text.length < 200) {
                    items.push({
                        text: text,
                        tag: el.tagName,
                        cls: (el.className || '').substring(0, 40),
                        active: el.className.includes('active') || el.className.includes('selected')
                    });
                }
            }
            return items.sort((a, b) => a.y - b.y);
        }""")
        print(f"\n[6c] Reference bottom elements:")
        for e in ref_bottom:
            active = " [ACTIVE]" if e['active'] else ""
            print(f"  <{e['tag'].lower()}> '{e['text'][:80]}' cls={e['cls'][:30]}{active}")

        # Check Reference model selector
        ref_model = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            var sel = panel.querySelector('.selected-name-text');
            return sel ? sel.innerText.trim() : null;
        }""")
        print(f"\n[6d] Reference mode model: {ref_model}")

        # Click the Reference mode model selector to see if different models are available
        page.evaluate("""() => {
            var body = document.querySelector('.c-gen-config.show .gen-config-body');
            if (body) body.scrollTop = 0;
        }""")
        page.wait_for_timeout(400)

        page.evaluate("""() => {
            var wrapper = document.querySelector('.c-gen-config.show .custom-selector-wrapper');
            if (wrapper) wrapper.click();
        }""")
        page.wait_for_timeout(2000)

        ref_models = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show .selector-panel');
            if (!panel) return [];
            var items = [];
            for (var el of panel.querySelectorAll('.option-item')) {
                var nameEl = el.querySelector('.item-name');
                var descEl = el.querySelector('.desc-text');
                var labels = [];
                for (var lab of el.querySelectorAll('.item-label')) labels.push(lab.innerText.trim());
                items.push({
                    name: nameEl ? nameEl.innerText.trim() : '',
                    credits: descEl ? descEl.innerText.trim() : '',
                    labels: labels,
                    selected: el.className.includes('selected') || el.className.includes('active')
                });
            }
            return items;
        }""")
        print(f"\n[6e] Reference mode models: {len(ref_models)}")
        for i, m in enumerate(ref_models):
            sel = " [SELECTED]" if m['selected'] else ""
            labels = ", ".join(m['labels']) if m['labels'] else ""
            print(f"  {i+1:2d}. {m['name']:<25s} {m['credits']:<30s} [{labels}]{sel}")
        findings['reference_models'] = ref_models

        shot(page, "27_reference_model_dropdown")

        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # ===============================================================
        # 7. SWITCH BACK TO KEY FRAME — Explore AnyFrame sub-mode
        # ===============================================================
        print(f"\n{'='*60}")
        print("7. ANYFRAME SUB-MODE")
        print(f"{'='*60}")

        # Switch back to Key Frame
        page.evaluate("""() => {
            var body = document.querySelector('.c-gen-config.show .gen-config-body');
            if (body) body.scrollTop = 0;
        }""")
        page.wait_for_timeout(300)

        page.evaluate("""() => {
            var btns = document.querySelectorAll('.c-gen-config.show .c-options .options');
            for (var btn of btns) {
                if (btn.innerText.trim() === 'Key Frame') { btn.click(); return; }
            }
        }""")
        page.wait_for_timeout(1500)
        close_popups(page)

        # Click AnyFrame
        page.evaluate("""() => {
            var btn = document.querySelector('#ai-video-key-frame-any-frame .frame-mode-tab-btn');
            if (btn) btn.click();
        }""")
        page.wait_for_timeout(1500)
        close_popups(page)

        shot(page, "28_anyframe_mode")

        anyframe_state = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            return {
                text: (panel.innerText || '').substring(0, 3000),
                activeFrameMode: (() => {
                    var active = panel.querySelector('.frame-mode-tab.active .frame-mode-tab-btn');
                    return active ? active.innerText.trim() : 'unknown';
                })()
            };
        }""")
        print(f"[7a] Active frame mode: {anyframe_state.get('activeFrameMode')}")
        print(f"[7a] Panel text:")
        for line in (anyframe_state.get('text') or '').split('\n'):
            line = line.strip()
            if line:
                print(f"  | {line[:120]}")
        findings['anyframe_state'] = anyframe_state

        # ===============================================================
        # 8. SCROLL KEY FRAME MODE — Get camera presets in detail
        # ===============================================================
        print(f"\n{'='*60}")
        print("8. CAMERA PRESETS — Detailed")
        print(f"{'='*60}")

        # Switch back to Start and Last
        page.evaluate("""() => {
            var btn = document.querySelector('#ai-video-key-frame-start-and-last .frame-mode-tab-btn');
            if (btn) btn.click();
        }""")
        page.wait_for_timeout(1000)

        # Scroll down to find camera section
        for scroll_pos in [300, 500, 700, 900, 1100]:
            page.evaluate(f"""() => {{
                var body = document.querySelector('.c-gen-config.show .gen-config-body');
                if (body) body.scrollTop = {scroll_pos};
            }}""")
            page.wait_for_timeout(500)

            # Check if camera section is visible
            camera_visible = page.evaluate("""() => {
                for (var el of document.querySelectorAll('.c-gen-config.show *')) {
                    var text = (el.innerText || '').trim();
                    if (text === 'Camera' && el.childElementCount === 0) {
                        var r = el.getBoundingClientRect();
                        if (r.y > 49 && r.y < 700) return true;
                    }
                }
                return false;
            }""")
            if camera_visible:
                print(f"[8a] Camera section found at scrollTop={scroll_pos}")
                shot(page, "29_camera_section")
                break

        # Get all camera presets
        camera = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};

            var result = {};

            // Cinematic shots
            var shots = [];
            for (var el of panel.querySelectorAll('.camera-name')) {
                var r = el.getBoundingClientRect();
                var parent = el.closest('.camera-item') || el.parentElement;
                var active = parent ? (parent.className.includes('active') || parent.className.includes('selected')) : false;
                shots.push({
                    name: el.innerText.trim(),
                    active: active,
                    x: Math.round(r.x), y: Math.round(r.y)
                });
            }
            result.cinematicShots = shots;

            // Free selection options
            var options = [];
            for (var el of panel.querySelectorAll('.option-name')) {
                var r = el.getBoundingClientRect();
                var parent = el.closest('.option-item, .camera-option') || el.parentElement;
                var active = parent ? (parent.className.includes('active') || parent.className.includes('selected')) : false;
                options.push({
                    name: el.innerText.trim(),
                    active: active,
                    x: Math.round(r.x), y: Math.round(r.y)
                });
            }
            result.freeSelection = options;

            // Camera tabs
            var tabs = [];
            for (var el of panel.querySelectorAll('.tab')) {
                var r = el.getBoundingClientRect();
                if (r.x > 60 && r.x < 400 && r.width > 0) {
                    tabs.push({
                        name: el.innerText.trim(),
                        selected: el.className.includes('selected'),
                        x: Math.round(r.x), y: Math.round(r.y)
                    });
                }
            }
            result.cameraTabs = tabs;

            return result;
        }""")

        print(f"\n[8b] Camera Tabs: {camera.get('cameraTabs', [])}")
        print(f"\n[8c] Cinematic Shots ({len(camera.get('cinematicShots', []))}):")
        for s in camera.get('cinematicShots', []):
            active = " [ACTIVE]" if s['active'] else ""
            print(f"  ({s['x']},{s['y']}) '{s['name']}'{active}")

        print(f"\n[8d] Free Selection ({len(camera.get('freeSelection', []))}):")
        for s in camera.get('freeSelection', []):
            active = " [ACTIVE]" if s['active'] else ""
            print(f"  ({s['x']},{s['y']}) '{s['name']}'{active}")

        findings['camera'] = camera

        # Click "Free Selection" tab to see the moves
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('.c-gen-config.show .tab')) {
                if (el.innerText.trim() === 'Free Selection') {
                    el.click();
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(1000)
        shot(page, "30_free_selection_camera")

        # Get free selection options after clicking
        free_sel = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return [];
            var items = [];
            for (var el of panel.querySelectorAll('.option-name')) {
                var r = el.getBoundingClientRect();
                if (r.y > 49 && r.y < 800) {
                    var parent = el.closest('.camera-option, .option-item') || el.parentElement;
                    items.push({
                        name: el.innerText.trim(),
                        active: parent ? parent.className.includes('selected') || parent.className.includes('active') : false,
                        y: Math.round(r.y)
                    });
                }
            }
            return items;
        }""")
        print(f"\n[8e] Free Selection moves (visible):")
        for s in free_sel:
            active = " [ACTIVE]" if s['active'] else ""
            print(f"  y={s['y']} '{s['name']}'{active}")

        # ===============================================================
        # 9. EXTRACT ALL SELECTOR IDS FOR AUTOMATION
        # ===============================================================
        print(f"\n{'='*60}")
        print("9. AUTOMATION SELECTORS")
        print(f"{'='*60}")

        selectors = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};
            return {
                panelClass: 'c-gen-config.show.ai-video-panel',
                panelBodyId: 'keyframe-generate-btn-i2v-panel',
                formId: 'keyframe-generate-btn-i2v-form',
                keyFrameBtn: '.c-gen-config.show .c-options .options:first-child',
                referenceBtn: '.c-gen-config.show .c-options .options:last-child',
                startAndLastTab: '#ai-video-key-frame-start-and-last',
                anyFrameTab: '#ai-video-key-frame-any-frame',
                startFrameUpload: '.c-gen-config.show .pick-image:first-of-type',
                endFrameUpload: '.c-gen-config.show .pick-image:last-of-type',
                promptTextarea: '.c-gen-config.show textarea.len-1800',
                modelSelector: '#i2v-custom-selector-wrapper',
                modelSelectorBtn: '#i2v-custom-selector-btn',
                modelSelectorPanel: '#i2v-custom-selector-panel',
                videoMetadata: '#video-metadata',
                generateBtn: '#keyframe-generate-btn-i2v',
                closePanelBtn: '.c-gen-config.show .ico-close',
                sizeButtons: '.c-gen-config.show .size-btn',
                qualityButtons: '.c-gen-config.show .quality-btn',
                durationButtons: '.c-gen-config.show .duration-btn',
                cameraTabs: '.c-gen-config.show .tab',
                cinematicShots: '.c-gen-config.show .camera-name',
                freeSelectionOptions: '.c-gen-config.show .option-name'
            };
        }""")
        print(json.dumps(selectors, indent=2))
        findings['selectors'] = selectors

        # ===============================================================
        # SAVE FINDINGS
        # ===============================================================
        findings_path = OUT_DIR / "findings_v2.json"
        with open(findings_path, "w") as f:
            json.dump(findings, f, indent=2, default=str)
        print(f"\n[P158] Findings saved to: {findings_path}")

        # ===============================================================
        # COMPREHENSIVE SUMMARY
        # ===============================================================
        print("\n" + "=" * 70)
        print("PHASE 158 — COMPREHENSIVE SUMMARY")
        print("=" * 70)

        print("\n--- AI VIDEO PANEL ---")
        print(f"Panel CSS: .c-gen-config.show.ai-video-panel")
        print(f"Title: AI Video")

        print("\n--- MODES ---")
        print("1. Key Frame (default) — upload Start Frame and/or End Frame")
        print("   Sub-modes: 'Start and Last' | 'AnyFrame'")
        print("   AnyFrame: upload 1-6 images, AI animates between them")
        print("2. Reference — upload reference images for style/content guidance")

        print(f"\n--- MODELS ({len(all_models)} total) ---")
        for i, m in enumerate(all_models):
            labels = ", ".join(m.get('labels', []))
            print(f"  {i+1:2d}. {m['name']:<25s} {m.get('credits',''):<30s} [{labels}]")

        print(f"\n--- ASPECT RATIOS ---")
        for r in settings.get('aspectRatios', []):
            sel = " [SELECTED]" if r['selected'] else ""
            dis = " [DISABLED]" if r.get('disabled') else ""
            print(f"  {r['text']}{sel}{dis}")

        print(f"\n--- QUALITY ---")
        for q in settings.get('quality', []):
            sel = " [SELECTED]" if q['selected'] else ""
            print(f"  {q['text']}{sel}")

        print(f"\n--- DURATION ---")
        for d in settings.get('duration', []):
            sel = " [SELECTED]" if d['selected'] else ""
            print(f"  {d['text']}{sel}")

        print(f"\n--- CAMERA: Cinematic Shots ({len(camera.get('cinematicShots', []))}) ---")
        for s in camera.get('cinematicShots', []):
            print(f"  {s['name']}")

        print(f"\n--- CAMERA: Free Selection ({len(camera.get('freeSelection', []))}) ---")
        for s in camera.get('freeSelection', []):
            print(f"  {s['name']}")

        print(f"\n--- PROMPTS ---")
        for p in settings.get('prompts', []):
            print(f"  placeholder: '{p['placeholder']}'  cls={p['cls']}")

        print(f"\n--- NEGATIVE PROMPTS ---")
        for p in settings.get('negativePrompts', []):
            print(f"  placeholder: '{p['placeholder']}'  cls={p['cls']}")

        print(f"\n--- GENERATE BUTTON ---")
        print(f"  id: #keyframe-generate-btn-i2v")
        if kf_state and kf_state.get('generateBtn'):
            print(f"  text: {kf_state['generateBtn'].get('text')}")
            print(f"  disabled: {kf_state['generateBtn'].get('disabled')}")

        print(f"\n--- CREDITS ---")
        if kf_state:
            print(f"  {kf_state.get('credits', '')}")

        print(f"\n--- SCREENSHOTS ---")
        print(f"  {OUT_DIR}")

    except Exception as exc:
        import traceback
        print(f"\n[P158] ERROR: {exc}")
        traceback.print_exc()
    finally:
        try:
            pw.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
