"""Phase 103: Lip Sync voice/audio — click "Pick a voice" + explore audio upload.
Phase 102 completed face selection: face set, timeline visible, "Pick a voice" button at (200,811).
Now: discover voice creation/upload mechanism and complete the Lip Sync workflow.
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
    """Reusable: open Lip Sync, pick face from canvas, face detect, crop, done."""
    print("\n--- Setting face ---", flush=True)
    # Open Lip Sync
    page.mouse.click(40, 425)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    is_open = page.evaluate("() => !!document.querySelector('.lip-sync-config-panel.show')")
    if not is_open:
        print("  Lip Sync didn't open!", flush=True)
        return False

    # Check if face is already set (no "Please pick a face" warning)
    warning = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        return p ? (p.innerText || '').includes('Please pick a face') : true;
    }""")
    if not warning:
        print("  Face already set!", flush=True)
        return True

    # Click "Pick a Face Image"
    coords = page.evaluate("""() => {
        for (var btn of document.querySelectorAll('button.pick-image')) {
            if (btn.classList.contains('pick-video')) continue;
            var r = btn.getBoundingClientRect();
            var text = (btn.innerText || '').trim();
            if (text.includes('Face Image') && r.width > 100) {
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
            }
        }
        return null;
    }""")
    if not coords:
        print("  No face image button!", flush=True)
        return False

    page.mouse.click(coords['x'], coords['y'])
    page.wait_for_timeout(3000)

    # Click first canvas thumbnail (BUTTON.image-item with bg-image in dialog)
    thumb = page.evaluate("""() => {
        var dialog = document.querySelector('.pick-image-dialog');
        if (!dialog) return null;
        for (var el of dialog.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var cs = window.getComputedStyle(el);
            var bg = cs.backgroundImage || '';
            if (r.width > 50 && r.height > 50 && bg !== 'none' && bg !== ''
                && r.x > 400 && r.x < 800 && r.y > 350 && r.y < 500) {
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
            }
        }
        return null;
    }""")
    if not thumb:
        print("  No thumbnail in dialog!", flush=True)
        return False

    page.mouse.click(thumb['x'], thumb['y'])
    page.wait_for_timeout(4000)

    # Face detect → Next
    page.evaluate("""() => {
        for (var btn of document.querySelectorAll('button')) {
            if ((btn.innerText || '').trim() === 'Next') { btn.click(); return; }
        }
    }""")
    page.wait_for_timeout(2000)

    # Crop → Next
    page.evaluate("""() => {
        for (var btn of document.querySelectorAll('button')) {
            if ((btn.innerText || '').trim() === 'Next') { btn.click(); return; }
        }
    }""")
    page.wait_for_timeout(5000)
    close_dialogs(page)

    # Verify
    warning2 = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        return p ? (p.innerText || '').includes('Please pick a face') : true;
    }""")
    if not warning2:
        print("  Face set successfully!", flush=True)
        return True
    else:
        print("  Face NOT set (warning still showing)", flush=True)
        return False


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
    #  STEP 1: Set face (reuse proven flow from Phase 102)
    # ============================================================
    face_ok = set_face(page)
    if not face_ok:
        print("ABORT: face not set", flush=True)
        os._exit(1)

    ss(page, "P103_01_face_set")

    # ============================================================
    #  STEP 2: Click "Pick a voice" button
    # ============================================================
    print("\n=== STEP 2: Click 'Pick a voice' ===", flush=True)

    pick_voice = page.evaluate("""() => {
        // Find "Pick a voice" element
        var pv = document.querySelector('.pick-voice');
        if (pv) {
            var r = pv.getBoundingClientRect();
            return {
                x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                w: Math.round(r.width), h: Math.round(r.height),
                class: (pv.className || '').toString(),
                text: (pv.innerText || '').trim(),
            };
        }
        // Fallback: find by text
        for (var el of document.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (t === 'Pick a voice' && r.width > 50 && r.height > 20) {
                return {
                    x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width), h: Math.round(r.height),
                    class: (el.className || '').toString(),
                    text: t,
                };
            }
        }
        return null;
    }""")

    if pick_voice:
        print(f"  Found: ({pick_voice['x']},{pick_voice['y']}) {pick_voice['w']}x{pick_voice['h']}", flush=True)
        print(f"  Class: {pick_voice['class']}", flush=True)
        page.mouse.click(pick_voice['x'], pick_voice['y'])
        page.wait_for_timeout(3000)
        ss(page, "P103_02_after_pick_voice")
    else:
        print("  'Pick a voice' NOT found!", flush=True)
        # Try direct click at the known position from Phase 102
        print("  Trying direct click at (275, 805)...", flush=True)
        page.mouse.click(275, 805)
        page.wait_for_timeout(3000)
        ss(page, "P103_02_direct_click")

    # ============================================================
    #  STEP 3: Map whatever dialog/panel appeared
    # ============================================================
    print("\n=== STEP 3: Map voice dialog/panel ===", flush=True)

    # Check for any new overlay/dialog
    overlays = page.evaluate("""() => {
        var overlays = [];
        for (var el of document.querySelectorAll('*')) {
            var cs = window.getComputedStyle(el);
            var z = parseInt(cs.zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > 300 && r.width > 200 && r.height > 100) {
                overlays.push({
                    tag: el.tagName,
                    class: (el.className || '').toString().substring(0, 80),
                    z: z, x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: (el.innerText || '').substring(0, 200),
                });
            }
        }
        overlays.sort(function(a,b){return b.z - a.z});
        return overlays.slice(0, 8);
    }""")
    print(f"  High-z overlays ({len(overlays)}):", flush=True)
    for o in overlays:
        print(f"    z={o['z']} <{o['tag']}> .{o['class'][:50]}", flush=True)
        print(f"      ({o['x']},{o['y']}) {o['w']}x{o['h']}", flush=True)
        print(f"      text: {o['text'][:100]}", flush=True)

    # Look for voice/audio related panels
    voice_panel = page.evaluate("""() => {
        // Search for voice-related panel/dialog
        var selectors = [
            '.voice-panel', '.voice-dialog', '.audio-panel', '.audio-dialog',
            '.pick-voice-panel', '.voice-selector', '.tts-panel',
            '.add-pick-voice', '.sound-effects-container',
            '[class*="voice"]', '[class*="audio-panel"]',
        ];
        for (var sel of selectors) {
            var els = document.querySelectorAll(sel);
            for (var el of els) {
                var r = el.getBoundingClientRect();
                if (r.width > 50 && r.height > 50) {
                    return {
                        selector: sel,
                        class: (el.className || '').toString().substring(0, 100),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: (el.innerText || '').substring(0, 300),
                        childCount: el.children.length,
                    };
                }
            }
        }
        return null;
    }""")

    if voice_panel:
        print(f"\n  Voice panel found:", flush=True)
        print(f"    Selector: {voice_panel['selector']}", flush=True)
        print(f"    Class: {voice_panel['class']}", flush=True)
        print(f"    Rect: ({voice_panel['x']},{voice_panel['y']}) {voice_panel['w']}x{voice_panel['h']}", flush=True)
        print(f"    Children: {voice_panel['childCount']}", flush=True)
        print(f"    Text: {voice_panel['text'][:200]}", flush=True)

    # Map ALL elements in the bottom area (timeline + any new panels)
    bottom_area = page.evaluate("""() => {
        var items = [];
        var seen = new Set();
        for (var el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            // Bottom area: y > 600
            if (r.y > 600 && r.width > 20 && r.height > 10 && r.width < 600) {
                var text = (el.innerText || '').trim();
                var cls = (el.className || '').toString();
                var tag = el.tagName;
                var key = tag + '|' + Math.round(r.y/5) + '|' + Math.round(r.x/10);
                if (seen.has(key)) continue;
                seen.add(key);
                if (text.length > 0 || tag === 'BUTTON' || tag === 'INPUT'
                    || tag === 'SELECT' || cls.includes('voice') || cls.includes('audio')
                    || cls.includes('upload') || cls.includes('speaker')) {
                    items.push({
                        tag: tag, class: cls.substring(0, 50),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 60),
                        cursor: window.getComputedStyle(el).cursor,
                    });
                }
            }
        }
        items.sort(function(a,b){return a.y === b.y ? a.x - b.x : a.y - b.y});
        return items.slice(0, 40);
    }""")
    print(f"\n  Bottom area elements ({len(bottom_area)}):", flush=True)
    for b in bottom_area:
        cur = f" [{b['cursor']}]" if b['cursor'] == 'pointer' else ""
        print(f"    ({b['x']},{b['y']}) {b['w']}x{b['h']} <{b['tag']}> .{b['class'][:35]} '{b['text'][:40]}'{cur}", flush=True)

    # Check for any new popover/dropdown near the "Pick a voice" area
    popover_area = page.evaluate("""() => {
        var items = [];
        for (var el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var cs = window.getComputedStyle(el);
            // Check area around where voice picker should appear
            // It might pop up ABOVE the timeline
            if (r.x > 100 && r.x < 600 && r.y > 500 && r.y < 850
                && r.width > 150 && r.height > 80) {
                var z = parseInt(cs.zIndex) || 0;
                if (z > 50 || cs.position === 'fixed' || cs.position === 'absolute') {
                    items.push({
                        tag: el.tagName,
                        class: (el.className || '').toString().substring(0, 80),
                        z: z, pos: cs.position,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: (el.innerText || '').substring(0, 200),
                    });
                }
            }
        }
        items.sort(function(a,b){return b.z - a.z});
        return items.slice(0, 10);
    }""")
    print(f"\n  Popover area elements ({len(popover_area)}):", flush=True)
    for p in popover_area:
        print(f"    z={p['z']} pos={p['pos']} ({p['x']},{p['y']}) {p['w']}x{p['h']}", flush=True)
        print(f"      <{p['tag']}> .{p['class'][:50]}", flush=True)
        print(f"      text: {p['text'][:100]}", flush=True)

    # ============================================================
    #  STEP 4: Look for voice options (TTS, upload, record, etc.)
    # ============================================================
    print("\n=== STEP 4: Voice option elements ===", flush=True)

    # Check for file input elements (for audio upload)
    file_inputs = page.evaluate("""() => {
        var inputs = [];
        for (var inp of document.querySelectorAll('input[type="file"]')) {
            var r = inp.getBoundingClientRect();
            inputs.push({
                accept: inp.accept || '',
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                name: inp.name || '',
                id: inp.id || '',
                parentClass: (inp.parentElement?.className || '').toString().substring(0, 50),
            });
        }
        return inputs;
    }""")
    print(f"  File inputs ({len(file_inputs)}):", flush=True)
    for fi in file_inputs:
        print(f"    ({fi['x']},{fi['y']}) {fi['w']}x{fi['h']} accept='{fi['accept']}' id='{fi['id']}' p=.{fi['parentClass']}", flush=True)

    # Check for text areas / text input (for TTS)
    tts_inputs = page.evaluate("""() => {
        var inputs = [];
        for (var el of document.querySelectorAll('textarea, input[type="text"], [contenteditable="true"]')) {
            var r = el.getBoundingClientRect();
            if (r.width > 30 && r.height > 10 && r.y > 600) {
                inputs.push({
                    tag: el.tagName, class: (el.className || '').toString().substring(0, 50),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    placeholder: el.placeholder || '',
                    value: (el.value || el.textContent || '').substring(0, 50),
                });
            }
        }
        return inputs;
    }""")
    print(f"  TTS-like inputs ({len(tts_inputs)}):", flush=True)
    for ti in tts_inputs:
        print(f"    ({ti['x']},{ti['y']}) {ti['w']}x{ti['h']} <{ti['tag']}> .{ti['class'][:30]} ph='{ti['placeholder'][:30]}' val='{ti['value'][:30]}'", flush=True)

    ss(page, "P103_03_voice_state")

    # ============================================================
    #  STEP 5: Try clicking "Speaker A" label to see options
    # ============================================================
    print("\n=== STEP 5: Click Speaker A ===", flush=True)

    speaker = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (t === 'Speaker A' && r.width > 30 && r.height > 10 && r.y > 700) {
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                        w: Math.round(r.width), h: Math.round(r.height)};
            }
        }
        return null;
    }""")
    if speaker:
        print(f"  Clicking Speaker A at ({speaker['x']},{speaker['y']})", flush=True)
        page.mouse.click(speaker['x'], speaker['y'])
        page.wait_for_timeout(2000)
        ss(page, "P103_04_after_speaker_click")

        # Check what changed
        new_items = page.evaluate("""() => {
            var items = [];
            var seen = new Set();
            for (var el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var cs = window.getComputedStyle(el);
                var z = parseInt(cs.zIndex) || 0;
                // Look for new popover/dropdown
                if ((z > 100 || cs.position === 'absolute' || cs.position === 'fixed')
                    && r.width > 50 && r.height > 30 && r.y > 500 && r.y < 850) {
                    var text = (el.innerText || '').trim();
                    var cls = (el.className || '').toString();
                    var key = cls.substring(0,20) + '|' + Math.round(r.y/5);
                    if (seen.has(key)) continue;
                    seen.add(key);
                    items.push({
                        tag: el.tagName, class: cls.substring(0, 60),
                        z: z, x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 100),
                    });
                }
            }
            items.sort(function(a,b){return b.z - a.z});
            return items.slice(0, 15);
        }""")
        print(f"  New overlays ({len(new_items)}):", flush=True)
        for n in new_items:
            print(f"    z={n['z']} ({n['x']},{n['y']}) {n['w']}x{n['h']} <{n['tag']}> .{n['class'][:40]} '{n['text'][:50]}'", flush=True)

    # ============================================================
    #  STEP 6: Click the + button near audio timeline if visible
    # ============================================================
    print("\n=== STEP 6: Audio add buttons ===", flush=True)

    add_btns = page.evaluate("""() => {
        var btns = [];
        for (var el of document.querySelectorAll('button, [class*="add"], [class*="plus"]')) {
            var r = el.getBoundingClientRect();
            if (r.y > 700 && r.width > 10 && r.height > 10 && r.width < 200) {
                var text = (el.innerText || '').trim();
                var cls = (el.className || '').toString();
                btns.push({
                    tag: el.tagName, class: cls.substring(0, 50),
                    x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: text.substring(0, 40),
                });
            }
        }
        return btns;
    }""")
    print(f"  Buttons in timeline ({len(add_btns)}):", flush=True)
    for b in add_btns:
        print(f"    ({b['x']},{b['y']}) {b['w']}x{b['h']} <{b['tag']}> .{b['class'][:35]} '{b['text'][:30]}'", flush=True)

    # Look for the upload icon / add audio button
    upload_btn = page.evaluate("""() => {
        // Check near (404, 888) - upload-image-btn from phase 102
        var ubtn = document.querySelector('.upload-image-btn');
        if (ubtn) {
            var r = ubtn.getBoundingClientRect();
            return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width), h: Math.round(r.height),
                    class: (ubtn.className || '').toString()};
        }
        return null;
    }""")
    if upload_btn:
        print(f"\n  Upload btn: ({upload_btn['x']},{upload_btn['y']}) {upload_btn['w']}x{upload_btn['h']} .{upload_btn['class']}", flush=True)

    ss(page, "P103_05_final")
    print(f"\n\n===== PHASE 103 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
