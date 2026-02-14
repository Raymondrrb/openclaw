"""Phase 106: Debug Generate Audio disabled + try voice re-select.
P105: text typed ok (64/4000), James selected, but gen-audio-btn stays disabled=true.
Hypothesis: voice selection needs to happen AFTER text is typed, or voice isn't truly selected.
Try: 1) Check button state deeply  2) Click James voice AFTER typing text  3) Check again
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


def set_face(page):
    page.mouse.click(40, 425)
    page.wait_for_timeout(3000)
    close_dialogs(page)
    w = page.evaluate("() => { var p = document.querySelector('.c-gen-config.show'); return p ? (p.innerText||'').includes('Please pick a face') : true; }")
    if not w:
        print("  Face already set!", flush=True)
        return True
    # Full face selection flow
    coords = page.evaluate("() => { for (var b of document.querySelectorAll('button.pick-image')) { if (b.classList.contains('pick-video')) continue; var r=b.getBoundingClientRect(); if ((b.innerText||'').includes('Face Image')&&r.width>100) return {x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)}; } return null; }")
    if not coords: return False
    page.mouse.click(coords['x'], coords['y'])
    page.wait_for_timeout(3000)
    thumb = page.evaluate("() => { var d=document.querySelector('.pick-image-dialog'); if(!d) return null; for(var e of d.querySelectorAll('*')){var r=e.getBoundingClientRect();var bg=window.getComputedStyle(e).backgroundImage||''; if(r.width>50&&r.height>50&&bg!=='none'&&r.x>400&&r.x<800&&r.y>350&&r.y<500) return {x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)};} return null; }")
    if not thumb: return False
    page.mouse.click(thumb['x'], thumb['y'])
    page.wait_for_timeout(4000)
    for _ in range(2):
        page.evaluate("() => { for(var b of document.querySelectorAll('button')) if((b.innerText||'').trim()==='Next'){b.click();return;} }")
        page.wait_for_timeout(2000)
    close_dialogs(page)
    w2 = page.evaluate("() => { var p=document.querySelector('.c-gen-config.show'); return p?(p.innerText||'').includes('Please pick a face'):true; }")
    return not w2


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

    face_ok = set_face(page)
    if not face_ok:
        print("ABORT: face not set", flush=True)
        os._exit(1)

    # Open voice picker
    pv = page.evaluate("() => { var e=document.querySelector('.pick-voice'); if(e){var r=e.getBoundingClientRect(); return r.width>20?{x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)}:null;} return null; }")
    if pv:
        page.mouse.click(pv['x'], pv['y'])
        page.wait_for_timeout(3000)
        print("  Voice picker opened", flush=True)
    else:
        print("ABORT: no voice picker", flush=True)
        os._exit(1)

    # ============================================================
    #  STEP 1: Check initial Generate Audio button state
    # ============================================================
    print("\n=== STEP 1: Initial button state ===", flush=True)

    btn_state = page.evaluate("""() => {
        var btn = document.querySelector('.gen-audio-btn');
        if (!btn) return {error: 'no .gen-audio-btn'};
        var r = btn.getBoundingClientRect();
        return {
            disabled: btn.disabled,
            class: btn.className,
            text: (btn.innerText || '').trim(),
            ariaDisabled: btn.getAttribute('aria-disabled'),
            x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
            style: btn.getAttribute('style') || '',
            opacity: window.getComputedStyle(btn).opacity,
            pointerEvents: window.getComputedStyle(btn).pointerEvents,
        };
    }""")
    print(f"  Gen Audio btn: {json.dumps(btn_state, indent=2)}", flush=True)

    # ============================================================
    #  STEP 2: Check voice selection state
    # ============================================================
    print("\n=== STEP 2: Voice selection state ===", flush=True)

    voice_state = page.evaluate("""() => {
        var selected = [];
        var opts = document.querySelectorAll('.c-option');
        for (var opt of opts) {
            var r = opt.getBoundingClientRect();
            if (r.width < 100) continue;
            var name = opt.querySelector('.name');
            if (!name) continue;
            var n = (name.innerText || '').trim();
            // Check for selected state
            var radio = opt.querySelector('input[type="radio"]');
            var isSelected = false;
            if (radio) isSelected = radio.checked;
            // Also check for "selected" class or aria-checked
            var cls = (opt.className || '').toString();
            if (cls.includes('selected') || cls.includes('active') || cls.includes('checked')) isSelected = true;

            selected.push({
                name: n,
                radioChecked: radio ? radio.checked : null,
                hasRadio: !!radio,
                className: cls.substring(0, 50),
                selected: isSelected,
            });
        }
        // Only return first 10 and any selected
        var results = [];
        for (var s of selected) {
            if (s.selected || results.length < 6) results.push(s);
        }
        return results;
    }""")
    print(f"  Voice states:", flush=True)
    for v in voice_state:
        sel = " <-- SELECTED" if v['selected'] else ""
        print(f"    {v['name']}: radio={v.get('radioChecked')} hasRadio={v['hasRadio']} cls='{v['className'][:30]}'{sel}", flush=True)

    # ============================================================
    #  STEP 3: Type text into textarea
    # ============================================================
    print("\n=== STEP 3: Type text ===", flush=True)

    # Click the editable textarea
    ta = page.locator('.voice-picker-wrapper .editable-textarea')
    if ta.count() > 0:
        ta.first.click()
        page.wait_for_timeout(300)
        page.keyboard.press("Meta+a")
        page.wait_for_timeout(200)
        test_text = "Here are the top five wireless headphones for 2025."
        page.keyboard.type(test_text, delay=30)
        page.wait_for_timeout(1000)
        print(f"  Typed: '{test_text}'", flush=True)
    else:
        print("  Editable textarea not found!", flush=True)

    # Check button state again
    btn2 = page.evaluate("() => { var b = document.querySelector('.gen-audio-btn'); return b ? {disabled: b.disabled, class: b.className} : null; }")
    print(f"  Button after typing: disabled={btn2.get('disabled')}, class={btn2.get('class', '')[:60]}", flush=True)

    # ============================================================
    #  STEP 4: Click James voice explicitly
    # ============================================================
    print("\n=== STEP 4: Click James voice ===", flush=True)

    # Use mouse click on the James radio/option
    james_click = page.evaluate("""() => {
        for (var opt of document.querySelectorAll('.c-option')) {
            var name = opt.querySelector('.name');
            if (name && (name.innerText || '').trim() === 'James') {
                var r = opt.getBoundingClientRect();
                if (r.width > 100) {
                    // Click the radio button or the option itself
                    var radio = opt.querySelector('input[type="radio"]');
                    if (radio) {
                        radio.click();
                        return {method: 'radio-click', x: Math.round(r.x), y: Math.round(r.y)};
                    }
                    return {method: 'option', x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                }
            }
        }
        return null;
    }""")
    print(f"  James click: {james_click}", flush=True)

    if james_click and james_click.get('method') == 'option':
        page.mouse.click(james_click['x'], james_click['y'])
    page.wait_for_timeout(1500)

    # Check button state
    btn3 = page.evaluate("() => { var b = document.querySelector('.gen-audio-btn'); return b ? {disabled: b.disabled, class: b.className} : null; }")
    print(f"  Button after voice click: disabled={btn3.get('disabled')}, class={btn3.get('class', '')[:60]}", flush=True)

    # ============================================================
    #  STEP 5: Try mouse click on James option area directly
    # ============================================================
    print("\n=== STEP 5: Mouse click on James area ===", flush=True)

    james_coords = page.evaluate("""() => {
        for (var opt of document.querySelectorAll('.c-option')) {
            var name = opt.querySelector('.name');
            if (name && (name.innerText || '').trim() === 'James') {
                var r = opt.getBoundingClientRect();
                return {x: Math.round(r.x + 20), y: Math.round(r.y + r.height/2),
                        w: Math.round(r.width), h: Math.round(r.height)};
            }
        }
        return null;
    }""")
    if james_coords:
        print(f"  James at ({james_coords['x']},{james_coords['y']}) {james_coords['w']}x{james_coords['h']}", flush=True)
        page.mouse.click(james_coords['x'], james_coords['y'])
        page.wait_for_timeout(1500)

    # Check again
    btn4 = page.evaluate("() => { var b = document.querySelector('.gen-audio-btn'); return b ? {disabled: b.disabled} : null; }")
    print(f"  Button after mouse click: disabled={btn4.get('disabled')}", flush=True)

    ss(page, "P106_01_after_voice_select")

    # ============================================================
    #  STEP 6: Check if textarea is INSIDE the voice picker correctly
    # ============================================================
    print("\n=== STEP 6: Deep textarea check ===", flush=True)

    deep = page.evaluate("""() => {
        var picker = document.querySelector('.voice-picker');
        if (!picker) return {error: 'no .voice-picker'};

        // Get the textarea's actual value from the app's perspective
        var ta = picker.querySelector('.editable-textarea');
        var text = ta ? ta.textContent : 'NO TEXTAREA';

        // Check all children that might hold state
        var stateInfo = {};
        for (var el of picker.querySelectorAll('*')) {
            var cls = (el.className || '').toString();
            // Look for mode/model indicators
            if (cls.includes('model') || cls.includes('mode') || cls.includes('trigger')) {
                var r = el.getBoundingClientRect();
                if (r.width > 10) {
                    stateInfo[cls.substring(0,30)] = (el.innerText || '').trim().substring(0, 50);
                }
            }
        }

        // Check the mode selector
        var modeTrigger = picker.querySelector('.model-trigger');
        var modeText = modeTrigger ? (modeTrigger.innerText || '').trim() : null;

        // Look for any error/warning messages
        var warnings = [];
        for (var el of picker.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            var cls = (el.className || '').toString();
            if ((cls.includes('error') || cls.includes('warning') || cls.includes('alert'))
                && t.length > 0) {
                warnings.push(t.substring(0, 80));
            }
        }

        return {
            textareaContent: text.substring(0, 100),
            mode: modeText,
            stateInfo: stateInfo,
            warnings: warnings,
        };
    }""")
    print(f"  Deep check: {json.dumps(deep, indent=2)}", flush=True)

    # ============================================================
    #  STEP 7: Try clicking Generate Audio with mouse anyway
    # ============================================================
    print("\n=== STEP 7: Force click Generate Audio ===", flush=True)

    gen_coords = page.evaluate("""() => {
        var btn = document.querySelector('.gen-audio-btn');
        if (!btn) return null;
        var r = btn.getBoundingClientRect();
        return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                disabled: btn.disabled};
    }""")
    if gen_coords:
        print(f"  Clicking Generate Audio at ({gen_coords['x']},{gen_coords['y']}) disabled={gen_coords['disabled']}", flush=True)
        # Try removing disabled and clicking
        page.evaluate("() => { var b = document.querySelector('.gen-audio-btn'); if(b) b.disabled = false; }")
        page.wait_for_timeout(300)
        page.mouse.click(gen_coords['x'], gen_coords['y'])
        page.wait_for_timeout(15000)  # Wait for potential generation
        ss(page, "P106_02_after_force_generate")

        # Check what happened
        result = page.evaluate("""() => {
            // Check if audio appeared in timeline
            var pv = document.querySelector('.pick-voice');
            var pvVisible = pv ? pv.getBoundingClientRect().width > 0 : false;

            // Check for loading/progress indicators
            var loading = [];
            for (var el of document.querySelectorAll('[class*="loading"], [class*="progress"], [class*="spinning"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 0) loading.push((el.className||'').toString().substring(0,50));
            }

            // Check panel warning
            var panel = document.querySelector('.c-gen-config.show');
            var voiceWarning = panel ? (panel.innerText||'').includes('Please create or upload a voice') : true;

            // Check timeline audio content
            var ta = document.querySelector('.timeline-audio');
            var taText = ta ? (ta.innerText||'').trim() : '';
            var taWidth = ta ? ta.getBoundingClientRect().width : 0;

            return {pvVisible, loading, voiceWarning, taText: taText.substring(0,50), taWidth};
        }""")
        print(f"  Result: {json.dumps(result, indent=2)}", flush=True)

    # ============================================================
    #  STEP 8: Check if Standard Mode selector is the issue
    # ============================================================
    print("\n=== STEP 8: Mode selector ===", flush=True)

    mode_info = page.evaluate("""() => {
        var trigger = document.querySelector('.model-trigger');
        if (!trigger) return null;
        var r = trigger.getBoundingClientRect();
        return {
            text: (trigger.innerText || '').trim(),
            x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
            w: Math.round(r.width), h: Math.round(r.height),
        };
    }""")
    print(f"  Mode trigger: {json.dumps(mode_info)}", flush=True)

    if mode_info:
        # Click the mode trigger to see options
        page.mouse.click(mode_info['x'], mode_info['y'])
        page.wait_for_timeout(2000)
        ss(page, "P106_03_mode_options")

        # Check for mode dropdown
        mode_options = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('*')) {
                var t = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                var cs = window.getComputedStyle(el);
                var z = parseInt(cs.zIndex) || 0;
                // Look for dropdown items near the mode trigger
                if (r.y > 600 && r.y < 750 && r.width > 50 && r.height > 20
                    && r.height < 50 && t.length > 3 && t.length < 50
                    && !t.includes('\\n') && z > 50) {
                    items.push({text: t, x: Math.round(r.x), y: Math.round(r.y),
                                w: Math.round(r.width), z: z});
                }
            }
            return items;
        }""")
        print(f"  Mode options: {json.dumps(mode_options, indent=2)}", flush=True)

    ss(page, "P106_04_final")
    print(f"\n\n===== PHASE 106 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
