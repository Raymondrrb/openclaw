"""Phase 110: Deep Img2Img panel mapping + proper prompt + generation.
P109 findings:
- Model selection worked (Nano Banana Pro → Realistic Product)
- Textarea selector `.custom-textarea, [contenteditable="true"]` returned null
- Panel has: Style Intensity, Structure Match, Color Match, Face Match, Gen Mode, Advanced
- "Describe Canvas" button auto-generates prompt from canvas
- Canvas image auto-used as input (no separate upload)
- 8 credits with Realistic Product
- Generation submitted at 0% — async processing

Goal: 1) Map ALL panel elements precisely (especially textarea)
      2) Check P109 generation result
      3) Type prompt properly using correct selector
      4) Test "Describe Canvas" auto-prompt
      5) Generate with prompt + check result
      6) Check completed Lip Sync video
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from playwright.sync_api import sync_playwright

CANVAS_URL = "https://www.dzine.ai/canvas?id=19797967"
SS_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dzine_explore"
SS_DIR.mkdir(parents=True, exist_ok=True)


def ss(page, name):
    page.screenshot(path=str(SS_DIR / f"{name}.png"))
    print(f"  SS: {name}", flush=True)


def close_dialogs(page):
    for _ in range(6):
        found = False
        for text in ["Not now", "Close", "Never show again", "Got it", "Skip", "Later"]:
            try:
                btn = page.locator(f'button:has-text("{text}")')
                if btn.count() > 0 and btn.first.is_visible(timeout=500):
                    btn.first.click()
                    page.wait_for_timeout(500)
                    found = True
            except Exception:
                pass
        if not found:
            break


def wait_for_canvas(page, max_wait=40):
    for i in range(max_wait):
        loaded = page.evaluate("() => document.querySelectorAll('.tool-group').length")
        if loaded >= 5:
            print(f"  Canvas loaded ({loaded} tool groups) after {i+1}s", flush=True)
            page.wait_for_timeout(2000)
            return True
        page.wait_for_timeout(1000)
    return False


def cleanup_tabs(ctx):
    pages = ctx.pages
    print(f"  Found {len(pages)} open tabs", flush=True)
    kept = False
    for p in pages:
        url = p.url or ""
        if "dzine.ai" in url:
            if kept:
                try:
                    p.close()
                except Exception:
                    pass
            else:
                kept = True
        elif url in ("", "about:blank", "chrome://newtab/"):
            try:
                p.close()
            except Exception:
                pass
    print(f"  Tabs after cleanup: {len(ctx.pages)}", flush=True)


def close_blocking_panels(page):
    """Close any panel that blocks the sidebar."""
    page.evaluate("""() => {
        // Close lip sync panel
        var lsp = document.querySelector('.lip-sync-config-panel.show');
        if (lsp) lsp.classList.remove('show');
        // Close any gen config panel
        var close = document.querySelector('.c-gen-config.show .ico-close');
        if (close) close.click();
    }""")
    page.wait_for_timeout(500)


def main():
    print("Connecting...", flush=True)
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:18800", timeout=15000)
    ctx = browser.contexts[0]
    cleanup_tabs(ctx)

    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
    print("  Waiting for canvas...", flush=True)
    wait_for_canvas(page)
    close_dialogs(page)

    # ============================================================
    #  STEP 1: Check previous results (P109 Img2Img + Lip Sync)
    # ============================================================
    print("\n=== STEP 1: Check previous results ===", flush=True)

    results = page.evaluate("""() => {
        var items = [];
        for (var el of document.querySelectorAll('.result-item')) {
            var r = el.getBoundingClientRect();
            if (r.width < 50 || r.height < 50) continue;
            var text = (el.innerText || '').trim().substring(0, 150);
            var cls = (el.className || '').toString();

            // Check for video
            var video = el.querySelector('video');
            var hasVideo = !!video;
            var videoSrc = video ? (video.src || video.currentSrc || '').substring(0, 100) : null;

            // Check for image
            var img = el.querySelector('img');
            var imgSrc = img ? (img.src || '').substring(0, 100) : null;

            // Check for download button
            var dl = el.querySelector('[class*="download"]');
            var hasDl = !!dl;

            // Status badges
            var badges = [];
            for (var badge of el.querySelectorAll('[class*="badge"], [class*="status"], [class*="tag"]')) {
                badges.push((badge.innerText || '').trim());
            }

            items.push({
                class: cls.substring(0, 80),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                text: text.substring(0, 80),
                hasVideo: hasVideo, videoSrc: videoSrc,
                imgSrc: imgSrc,
                hasDl: hasDl,
                badges: badges,
            });
        }
        return items;
    }""")

    print(f"  Result items: {len(results)}", flush=True)
    for i, r in enumerate(results[:6]):
        print(f"  [{i}] .{r['class'][:50]}", flush=True)
        print(f"      ({r['x']},{r['y']}) {r['w']}x{r['h']}", flush=True)
        print(f"      text: {r['text'][:60]}", flush=True)
        print(f"      video={r['hasVideo']} img={r['imgSrc'] is not None} dl={r['hasDl']}", flush=True)
        if r['videoSrc']:
            print(f"      video src: {r['videoSrc']}", flush=True)
        if r['badges']:
            print(f"      badges: {r['badges']}", flush=True)

    ss(page, "P110_01_results_check")

    # ============================================================
    #  STEP 2: Open Img2Img panel
    # ============================================================
    print("\n=== STEP 2: Open Img2Img panel ===", flush=True)

    close_blocking_panels(page)
    page.wait_for_timeout(1000)

    # Click Img2Img sidebar icon
    page.mouse.click(40, 252)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    # ============================================================
    #  STEP 3: Deep panel mapping — find ALL elements
    # ============================================================
    print("\n=== STEP 3: Deep panel mapping ===", flush=True)

    panel_map = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return {error: 'no panel'};

        // Find ALL textareas, inputs, contenteditable elements
        var inputs = [];
        for (var el of p.querySelectorAll('textarea, input, [contenteditable], [class*="textarea"], [class*="prompt"]')) {
            var r = el.getBoundingClientRect();
            if (r.width < 10) continue;
            inputs.push({
                tag: el.tagName,
                type: el.type || '',
                class: (el.className || '').toString().substring(0, 80),
                id: el.id || '',
                contentEditable: el.contentEditable,
                placeholder: el.getAttribute('placeholder') || '',
                text: (el.textContent || '').substring(0, 80),
                value: (el.value || '').substring(0, 80),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
            });
        }

        // Find ALL buttons
        var buttons = [];
        for (var btn of p.querySelectorAll('button, [class*="btn"], [class*="generate"]')) {
            var r = btn.getBoundingClientRect();
            if (r.width < 20 || r.height < 10) continue;
            var text = (btn.innerText || '').trim();
            if (text.length === 0 && !btn.className) continue;
            buttons.push({
                tag: btn.tagName,
                class: (btn.className || '').toString().substring(0, 80),
                text: text.substring(0, 40),
                disabled: btn.disabled,
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
            });
        }

        // Find ALL sliders
        var sliders = [];
        for (var sl of p.querySelectorAll('[class*="slider"], [class*="range"], input[type="range"]')) {
            var r = sl.getBoundingClientRect();
            sliders.push({
                class: (sl.className || '').toString().substring(0, 60),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width),
            });
        }

        // Find ALL toggles/switches
        var toggles = [];
        for (var t of p.querySelectorAll('[class*="toggle"], [class*="switch"]')) {
            var r = t.getBoundingClientRect();
            var text = '';
            var prev = t.previousElementSibling;
            if (prev) text = (prev.innerText || '').trim();
            var parent = t.parentElement;
            if (!text && parent) {
                for (var c of parent.childNodes) {
                    if (c.nodeType === 3) text += c.textContent.trim();
                }
            }
            toggles.push({
                class: (t.className || '').toString().substring(0, 60),
                label: text.substring(0, 30),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width),
            });
        }

        // Panel title and full text
        var title = p.querySelector('h5');
        var styleName = p.querySelector('.style-name');

        return {
            title: title ? (title.innerText || '').trim() : null,
            model: styleName ? (styleName.innerText || '').trim() : null,
            inputs: inputs,
            buttons: buttons.slice(0, 15),
            sliders: sliders,
            toggles: toggles,
            panelClass: (p.className || '').toString(),
            fullText: (p.innerText || '').substring(0, 600),
        };
    }""")

    print(f"  Title: {panel_map.get('title')}", flush=True)
    print(f"  Model: {panel_map.get('model')}", flush=True)
    print(f"  Panel class: {panel_map.get('panelClass', '')[:80]}", flush=True)

    print(f"\n  INPUTS ({len(panel_map.get('inputs', []))}):", flush=True)
    for inp in panel_map.get('inputs', []):
        print(f"    <{inp['tag']}> .{inp['class'][:50]}", flush=True)
        print(f"      ({inp['x']},{inp['y']}) {inp['w']}x{inp['h']} editable={inp['contentEditable']}", flush=True)
        print(f"      placeholder: '{inp['placeholder'][:50]}'", flush=True)
        print(f"      text: '{inp['text'][:50]}'", flush=True)

    print(f"\n  BUTTONS ({len(panel_map.get('buttons', []))}):", flush=True)
    for btn in panel_map.get('buttons', []):
        print(f"    <{btn['tag']}> .{btn['class'][:50]} '{btn['text'][:30]}' disabled={btn.get('disabled')}", flush=True)
        print(f"      ({btn['x']},{btn['y']}) {btn['w']}x{btn['h']}", flush=True)

    print(f"\n  SLIDERS ({len(panel_map.get('sliders', []))}):", flush=True)
    for sl in panel_map.get('sliders', []):
        print(f"    .{sl['class'][:50]} ({sl['x']},{sl['y']}) w={sl['w']}", flush=True)

    print(f"\n  TOGGLES ({len(panel_map.get('toggles', []))}):", flush=True)
    for t in panel_map.get('toggles', []):
        print(f"    .{t['class'][:50]} label='{t['label']}' ({t['x']},{t['y']})", flush=True)

    ss(page, "P110_02_panel_mapped")

    # ============================================================
    #  STEP 4: Find the prompt textarea specifically
    # ============================================================
    print("\n=== STEP 4: Find prompt textarea ===", flush=True)

    # Try broader search - any element that could be a text input
    textarea_search = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return {error: 'no panel'};

        var candidates = [];
        // Search for anything with "prompt" in class/id, or contenteditable, or textarea tag
        for (var el of p.querySelectorAll('*')) {
            var cls = (el.className || '').toString().toLowerCase();
            var id = (el.id || '').toLowerCase();
            var tag = el.tagName.toLowerCase();
            var r = el.getBoundingClientRect();

            if (r.width < 30 || r.height < 15 || r.x < 60 || r.x > 350) continue;

            var isCandidate = false;
            var reason = '';

            if (tag === 'textarea') { isCandidate = true; reason = 'textarea tag'; }
            else if (el.contentEditable === 'true') { isCandidate = true; reason = 'contentEditable'; }
            else if (cls.includes('prompt')) { isCandidate = true; reason = 'class has prompt'; }
            else if (cls.includes('textarea')) { isCandidate = true; reason = 'class has textarea'; }
            else if (cls.includes('input') && r.height > 20) { isCandidate = true; reason = 'class has input'; }
            else if (id.includes('prompt')) { isCandidate = true; reason = 'id has prompt'; }

            if (isCandidate) {
                candidates.push({
                    tag: tag,
                    class: cls.substring(0, 80),
                    id: id,
                    reason: reason,
                    contentEditable: el.contentEditable,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: (el.textContent || '').substring(0, 80),
                    placeholder: el.getAttribute('placeholder') || '',
                    children: el.children.length,
                });
            }
        }

        // Also check what's around the "0 / 1800" char counter
        var charCounter = null;
        for (var el of p.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text.match(/\\d+\\s*\\/\\s*1800/)) {
                var r = el.getBoundingClientRect();
                charCounter = {
                    text: text,
                    tag: el.tagName,
                    class: (el.className || '').toString().substring(0, 60),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                };
                // Check siblings/parent for textarea
                var parent = el.parentElement;
                if (parent) {
                    charCounter.parentTag = parent.tagName;
                    charCounter.parentClass = (parent.className || '').toString().substring(0, 60);
                    // Look for siblings that are textareas
                    var siblings = [];
                    for (var s of parent.children) {
                        siblings.push({
                            tag: s.tagName,
                            class: (s.className || '').toString().substring(0, 50),
                            contentEditable: s.contentEditable,
                            h: Math.round(s.getBoundingClientRect().height),
                        });
                    }
                    charCounter.siblings = siblings;
                }
                break;
            }
        }

        return {candidates: candidates, charCounter: charCounter};
    }""")

    print(f"  Textarea candidates ({len(textarea_search.get('candidates', []))}):", flush=True)
    for c in textarea_search.get('candidates', []):
        print(f"    <{c['tag']}> .{c['class'][:50]} reason={c['reason']}", flush=True)
        print(f"      ({c['x']},{c['y']}) {c['w']}x{c['h']} editable={c['contentEditable']} children={c['children']}", flush=True)
        print(f"      text: '{c['text'][:50]}' placeholder: '{c['placeholder'][:40]}'", flush=True)

    cc = textarea_search.get('charCounter')
    if cc:
        print(f"\n  Char counter: '{cc['text']}' <{cc['tag']}> .{cc.get('class', '')[:50]}", flush=True)
        print(f"    ({cc['x']},{cc['y']}) {cc['w']}x{cc['h']}", flush=True)
        print(f"    Parent: <{cc.get('parentTag')}> .{cc.get('parentClass', '')[:50]}", flush=True)
        if cc.get('siblings'):
            print(f"    Siblings:", flush=True)
            for s in cc['siblings']:
                print(f"      <{s['tag']}> .{s['class'][:40]} editable={s['contentEditable']} h={s['h']}", flush=True)

    # ============================================================
    #  STEP 5: Type prompt into the textarea
    # ============================================================
    print("\n=== STEP 5: Type prompt ===", flush=True)

    prompt_text = "Professional studio photo of premium wireless headphones, clean white background, commercial product photography, sharp details, high resolution"

    # Try to find and click the textarea area
    typed = page.evaluate("""(promptText) => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return {error: 'no panel'};

        // Strategy 1: Find contentEditable inside the panel that's near the char counter
        var ta = null;
        for (var el of p.querySelectorAll('[contenteditable="true"]')) {
            var r = el.getBoundingClientRect();
            if (r.width > 100 && r.height > 20 && r.x > 60 && r.x < 350) {
                ta = el;
                break;
            }
        }

        // Strategy 2: Find by class pattern
        if (!ta) {
            for (var el of p.querySelectorAll('.prompt-textarea, .custom-textarea, .textarea-extend, [class*="prompt"][class*="text"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 100 && r.height > 15) {
                    ta = el;
                    break;
                }
            }
        }

        // Strategy 3: Look for textarea tag
        if (!ta) {
            ta = p.querySelector('textarea');
        }

        if (ta) {
            var r = ta.getBoundingClientRect();
            return {
                found: true,
                tag: ta.tagName,
                class: (ta.className || '').toString().substring(0, 60),
                x: Math.round(r.x + r.width/2),
                y: Math.round(r.y + r.height/2),
                w: Math.round(r.width), h: Math.round(r.height),
                contentEditable: ta.contentEditable,
            };
        }

        return {found: false};
    }""", prompt_text)

    print(f"  Textarea search: {json.dumps(typed)}", flush=True)

    if typed.get('found'):
        # Click the textarea to focus
        page.mouse.click(typed['x'], typed['y'])
        page.wait_for_timeout(500)
        page.keyboard.press("Meta+a")
        page.wait_for_timeout(200)
        page.keyboard.type(prompt_text, delay=10)
        page.wait_for_timeout(1000)
        print(f"  Typed prompt ({len(prompt_text)} chars)", flush=True)
    else:
        # Fallback: try clicking the area where the placeholder text was visible
        # From P109 screenshot: textarea placeholder was at roughly (100, 110) area
        print("  No textarea found via JS. Trying click at prompt area (100, 110)...", flush=True)
        page.mouse.click(100, 110)
        page.wait_for_timeout(500)

        # Check what we clicked
        focused = page.evaluate("""() => {
            var el = document.activeElement;
            if (!el) return null;
            var r = el.getBoundingClientRect();
            return {
                tag: el.tagName,
                class: (el.className || '').toString().substring(0, 60),
                contentEditable: el.contentEditable,
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                text: (el.textContent || '').substring(0, 50),
            };
        }""")
        print(f"  Focused element: {json.dumps(focused)}", flush=True)

        if focused and (focused.get('contentEditable') == 'true' or focused.get('tag') == 'TEXTAREA'):
            page.keyboard.press("Meta+a")
            page.wait_for_timeout(200)
            page.keyboard.type(prompt_text, delay=10)
            page.wait_for_timeout(1000)
            print(f"  Typed into focused element ({len(prompt_text)} chars)", flush=True)
        else:
            # Try clicking higher in the panel where placeholder was visible
            print("  Trying other positions...", flush=True)
            for cy in [95, 105, 115, 125]:
                page.mouse.click(140, cy)
                page.wait_for_timeout(300)
                f2 = page.evaluate("() => { var e = document.activeElement; return e ? {tag: e.tagName, editable: e.contentEditable, class: (e.className||'').toString().substring(0,40)} : null; }")
                print(f"    y={cy}: {json.dumps(f2)}", flush=True)
                if f2 and (f2.get('editable') == 'true' or f2.get('tag') == 'TEXTAREA'):
                    page.keyboard.press("Meta+a")
                    page.wait_for_timeout(200)
                    page.keyboard.type(prompt_text, delay=10)
                    page.wait_for_timeout(1000)
                    print(f"    Typed prompt at y={cy}!", flush=True)
                    break

    # Check char count after typing
    char_count = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return null;
        for (var el of p.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            if (t.match(/\\d+\\s*\\/\\s*1800/)) return t;
        }
        return null;
    }""")
    print(f"  Char count: {char_count}", flush=True)

    ss(page, "P110_03_prompt_typed")

    # ============================================================
    #  STEP 6: Test "Describe Canvas" auto-prompt
    # ============================================================
    print("\n=== STEP 6: Map Describe Canvas button ===", flush=True)

    describe_btn = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return null;
        for (var el of p.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.includes('Describe Canvas') && r.width > 50 && r.height > 10 && r.height < 40) {
                return {
                    tag: el.tagName,
                    class: (el.className || '').toString().substring(0, 60),
                    text: text.substring(0, 40),
                    x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width), h: Math.round(r.height),
                };
            }
        }
        return null;
    }""")
    print(f"  Describe Canvas: {json.dumps(describe_btn)}", flush=True)

    # ============================================================
    #  STEP 7: Map ALL Img2Img controls (sliders, toggles, modes)
    # ============================================================
    print("\n=== STEP 7: Full controls map ===", flush=True)

    controls = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return {error: 'no panel'};

        // Organized sections
        var sections = [];
        for (var el of p.querySelectorAll('[class*="section"], [class*="group"], [class*="option"]')) {
            var r = el.getBoundingClientRect();
            if (r.width < 100 || r.height < 20 || r.x < 60 || r.x > 300) continue;
            var text = (el.innerText || '').trim();
            if (text.length > 3 && text.length < 100) {
                sections.push({
                    class: (el.className || '').toString().substring(0, 60),
                    text: text.substring(0, 60),
                    y: Math.round(r.y),
                    h: Math.round(r.height),
                });
            }
        }

        // Style Intensity
        var styleIntensity = null;
        for (var el of p.querySelectorAll('*')) {
            if ((el.innerText || '').trim().startsWith('Style Intensity')) {
                var parent = el.parentElement;
                if (parent) {
                    var slider = parent.querySelector('input[type="range"], [class*="slider"]');
                    var label = parent.querySelector('[class*="label"], [class*="value"]');
                    styleIntensity = {
                        y: Math.round(el.getBoundingClientRect().y),
                        slider: slider ? (slider.className || '').toString().substring(0, 40) : null,
                        sliderVal: slider ? slider.value : null,
                        label: label ? (label.innerText || '').trim() : null,
                    };
                }
                break;
            }
        }

        // Structure Match
        var structureMatch = null;
        for (var el of p.querySelectorAll('*')) {
            if ((el.innerText || '').trim().startsWith('Structure Match')) {
                var parent = el.parentElement;
                if (parent) {
                    var slider = parent.querySelector('input[type="range"], [class*="slider"]');
                    var label = parent.querySelector('[class*="label"], [class*="value"]');
                    structureMatch = {
                        y: Math.round(el.getBoundingClientRect().y),
                        slider: slider ? (slider.className || '').toString().substring(0, 40) : null,
                        sliderVal: slider ? slider.value : null,
                        label: label ? (label.innerText || '').trim() : null,
                    };
                }
                break;
            }
        }

        // Generation Mode
        var genMode = null;
        for (var el of p.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Generation Mode') {
                var parent = el.parentElement;
                if (parent) {
                    var opts = [];
                    for (var opt of parent.querySelectorAll('[class*="option"], button')) {
                        var text = (opt.innerText || '').trim();
                        var selected = (opt.className || '').includes('selected') || (opt.className || '').includes('active');
                        if (text && (text === 'Normal' || text === 'HQ')) {
                            opts.push({text: text, selected: selected});
                        }
                    }
                    genMode = {y: Math.round(el.getBoundingClientRect().y), options: opts};
                }
                break;
            }
        }

        // Image upload / canvas preview area
        var imgPreview = null;
        for (var el of p.querySelectorAll('img, [class*="preview"], [class*="upload"], [class*="pick-image"]')) {
            var r = el.getBoundingClientRect();
            if (r.width > 50 && r.height > 50 && r.x > 60 && r.x < 250 && r.y > 80 && r.y < 300) {
                imgPreview = {
                    tag: el.tagName,
                    class: (el.className || '').toString().substring(0, 60),
                    src: el.src ? el.src.substring(0, 100) : null,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                };
                break;
            }
        }

        // Generate button
        var genBtn = p.querySelector('.generative, [class*="generate"]');
        var genInfo = null;
        if (genBtn) {
            var r = genBtn.getBoundingClientRect();
            genInfo = {
                text: (genBtn.innerText || '').trim(),
                disabled: genBtn.disabled,
                class: (genBtn.className || '').toString().substring(0, 60),
                x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
            };
        }

        return {
            styleIntensity: styleIntensity,
            structureMatch: structureMatch,
            genMode: genMode,
            imgPreview: imgPreview,
            genBtn: genInfo,
        };
    }""")

    print(f"  Style Intensity: {json.dumps(controls.get('styleIntensity'))}", flush=True)
    print(f"  Structure Match: {json.dumps(controls.get('structureMatch'))}", flush=True)
    print(f"  Generation Mode: {json.dumps(controls.get('genMode'))}", flush=True)
    print(f"  Image Preview: {json.dumps(controls.get('imgPreview'))}", flush=True)
    print(f"  Generate Button: {json.dumps(controls.get('genBtn'))}", flush=True)

    # ============================================================
    #  STEP 8: Generate with prompt
    # ============================================================
    print("\n=== STEP 8: Generate ===", flush=True)

    gen_info = controls.get('genBtn')
    if gen_info and not gen_info.get('disabled'):
        # Count initial results
        initial_count = page.evaluate("""() => {
            return document.querySelectorAll('.result-item').length;
        }""")
        print(f"  Initial results: {initial_count}", flush=True)
        print(f"  Clicking Generate ({gen_info['text']})...", flush=True)

        page.mouse.click(gen_info['x'], gen_info['y'])
        page.wait_for_timeout(3000)

        # Check immediate state
        post_click = page.evaluate("""() => {
            var p = document.querySelector('.c-gen-config.show');
            var gen = p ? p.querySelector('.generative, [class*="generate"]') : null;
            var genText = gen ? (gen.innerText || '').trim() : '';
            var genDisabled = gen ? gen.disabled : true;
            var genClass = gen ? (gen.className || '').toString() : '';

            // Check for new result
            var results = document.querySelectorAll('.result-item');
            var lastResult = results.length > 0 ? results[results.length - 1] : null;
            var lastText = lastResult ? (lastResult.innerText || '').trim().substring(0, 80) : '';

            return {
                genText: genText,
                genDisabled: genDisabled,
                genClass: genClass.substring(0, 80),
                resultCount: results.length,
                lastResultText: lastText,
            };
        }""")
        print(f"  Post-click: gen='{post_click.get('genText', '')[:30]}' disabled={post_click.get('genDisabled')}", flush=True)
        print(f"  Results: {post_click.get('resultCount')} (was {initial_count})", flush=True)
        print(f"  Last result: {post_click.get('lastResultText', '')[:60]}", flush=True)

        ss(page, "P110_04_after_generate")

        # Wait for generation
        print("  Waiting for generation...", flush=True)
        for i in range(30):
            elapsed = (i + 1) * 3
            check = page.evaluate("""(initCount) => {
                var results = document.querySelectorAll('.result-item');
                var newCount = results.length;

                // Check newest result for completion
                var newest = null;
                if (results.length > 0) {
                    var last = results[results.length - 1];
                    var text = (last.innerText || '').trim();
                    var img = last.querySelector('img');
                    var imgLoaded = img ? (img.naturalWidth > 0) : false;
                    newest = {
                        text: text.substring(0, 60),
                        hasImg: !!img,
                        imgLoaded: imgLoaded,
                    };
                }

                // Check for percentage in results
                var pctMatch = null;
                for (var el of document.querySelectorAll('[class*="progress"], [class*="percent"]')) {
                    var t = (el.innerText || '').trim();
                    if (t.match(/\\d+%/)) pctMatch = t;
                }

                return {
                    resultCount: newCount, newResults: newCount - initCount,
                    newest: newest, progress: pctMatch,
                };
            }""", initial_count)

            if check.get('newResults', 0) > 0 and check.get('newest', {}).get('imgLoaded'):
                print(f"  New result with image at {elapsed}s!", flush=True)
                break

            if i % 5 == 0:
                print(f"  ...{elapsed}s results={check.get('resultCount')} new={check.get('newResults')} progress={check.get('progress')}", flush=True)

            page.wait_for_timeout(3000)

        ss(page, "P110_05_generation_result")
    else:
        print(f"  Generate button not ready: {gen_info}", flush=True)

    # ============================================================
    #  STEP 9: Check Lip Sync completed video
    # ============================================================
    print("\n=== STEP 9: Check Lip Sync video ===", flush=True)

    lip_sync_results = page.evaluate("""() => {
        var results = [];
        for (var el of document.querySelectorAll('.result-item')) {
            var text = (el.innerText || '').trim();
            if (!text.includes('Lip Sync')) continue;

            var r = el.getBoundingClientRect();
            var video = el.querySelector('video');
            var img = el.querySelector('img');
            var dl = el.querySelector('[class*="download"]');

            results.push({
                text: text.substring(0, 100),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                hasVideo: !!video,
                videoSrc: video ? (video.src || video.currentSrc || '').substring(0, 120) : null,
                videoDuration: video ? video.duration : null,
                hasImg: !!img,
                imgSrc: img ? (img.src || '').substring(0, 120) : null,
                hasDl: !!dl,
                waiting: text.includes('Waiting'),
            });
        }
        return results;
    }""")

    print(f"  Lip Sync results: {len(lip_sync_results)}", flush=True)
    for i, lr in enumerate(lip_sync_results):
        print(f"  [{i}] waiting={lr['waiting']} video={lr['hasVideo']} dl={lr['hasDl']}", flush=True)
        print(f"      text: {lr['text'][:70]}", flush=True)
        if lr['videoSrc']:
            print(f"      video: {lr['videoSrc'][:80]}", flush=True)
            print(f"      duration: {lr['videoDuration']}s", flush=True)
        if lr['imgSrc']:
            print(f"      img: {lr['imgSrc'][:80]}", flush=True)

    # ============================================================
    #  STEP 10: Credits check
    # ============================================================
    print("\n=== STEP 10: Credits ===", flush=True)

    credits = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text.match(/^[\\d,]+$/) && parseInt(text.replace(',', '')) > 1000) {
                var r = el.getBoundingClientRect();
                if (r.y < 30 && r.x > 400) {
                    return text;
                }
            }
        }
        return null;
    }""")
    print(f"  Credits remaining: {credits}", flush=True)

    ss(page, "P110_06_final")
    print(f"\n\n===== PHASE 110 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
