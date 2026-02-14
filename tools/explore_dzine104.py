"""Phase 104: Lip Sync voice — explore Upload Audio tab + test TTS generation.
Phase 103 found: "Speaking Voice" dialog at z=9998 with tabs:
  - Text to Speech (default): voices (James, Brittney...), text area, 4000 chars, "Generate Audio" FREE
  - Upload Audio: unexplored
Goal: A) Map Upload Audio tab  B) Scroll voice list  C) Generate test TTS audio
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
    """Proven flow: open Lip Sync → pick face → face detect → crop → done."""
    print("\n--- Setting face ---", flush=True)
    page.mouse.click(40, 425)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    is_open = page.evaluate("() => !!document.querySelector('.lip-sync-config-panel.show')")
    if not is_open:
        print("  Lip Sync didn't open!", flush=True)
        return False

    warning = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        return p ? (p.innerText || '').includes('Please pick a face') : true;
    }""")
    if not warning:
        print("  Face already set!", flush=True)
        return True

    coords = page.evaluate("""() => {
        for (var btn of document.querySelectorAll('button.pick-image')) {
            if (btn.classList.contains('pick-video')) continue;
            var r = btn.getBoundingClientRect();
            if ((btn.innerText||'').includes('Face Image') && r.width > 100) {
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
            }
        }
        return null;
    }""")
    if not coords:
        return False

    page.mouse.click(coords['x'], coords['y'])
    page.wait_for_timeout(3000)

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
        return False

    page.mouse.click(thumb['x'], thumb['y'])
    page.wait_for_timeout(4000)

    # Next 1: face detect
    page.evaluate("""() => {
        for (var btn of document.querySelectorAll('button'))
            if ((btn.innerText||'').trim() === 'Next') { btn.click(); return; }
    }""")
    page.wait_for_timeout(2000)

    # Next 2: crop
    page.evaluate("""() => {
        for (var btn of document.querySelectorAll('button'))
            if ((btn.innerText||'').trim() === 'Next') { btn.click(); return; }
    }""")
    page.wait_for_timeout(5000)
    close_dialogs(page)

    warning2 = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        return p ? (p.innerText || '').includes('Please pick a face') : true;
    }""")
    print(f"  Face set: {not warning2}", flush=True)
    return not warning2


def open_voice_picker(page):
    """Click 'Pick a voice' in the timeline."""
    pv = page.evaluate("""() => {
        var el = document.querySelector('.pick-voice');
        if (el) {
            var r = el.getBoundingClientRect();
            if (r.width > 20) return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
        }
        return null;
    }""")
    if pv:
        page.mouse.click(pv['x'], pv['y'])
        page.wait_for_timeout(3000)
        return True
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

    # STEP 1: Set face + open voice picker
    face_ok = set_face(page)
    if not face_ok:
        print("ABORT: face not set", flush=True)
        os._exit(1)

    voice_ok = open_voice_picker(page)
    if not voice_ok:
        print("ABORT: voice picker not opened", flush=True)
        os._exit(1)

    print("\n  Voice picker opened!", flush=True)

    # ============================================================
    #  PART A: Scroll voice list — catalog all voices
    # ============================================================
    print("\n=== PART A: Voice catalog ===", flush=True)

    all_voices = page.evaluate("""() => {
        var voices = [];
        // Find the voice list scrollable container
        var options = document.querySelectorAll('.c-option');
        for (var opt of options) {
            var r = opt.getBoundingClientRect();
            if (r.width < 100) continue;
            var name = opt.querySelector('.name');
            var gender = opt.querySelector('.gender');
            var useCase = opt.querySelector('.use_case');
            if (name) {
                voices.push({
                    name: (name.innerText || '').trim(),
                    gender: (gender?.innerText || '').trim(),
                    useCase: (useCase?.innerText || '').trim(),
                    y: Math.round(r.y),
                });
            }
        }
        return voices;
    }""")
    print(f"  Voices visible ({len(all_voices)}):", flush=True)
    for v in all_voices:
        print(f"    {v['name']} ({v['gender']}) — {v['useCase']}", flush=True)

    # Scroll voice list to see more
    more_voices = page.evaluate("""() => {
        // Find scrollable container for voice list
        var scrollable = null;
        for (var el of document.querySelectorAll('*')) {
            var cs = window.getComputedStyle(el);
            var r = el.getBoundingClientRect();
            if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll')
                && r.width > 300 && r.height > 100 && r.height < 400
                && r.y > 200 && r.y < 400) {
                scrollable = el;
                break;
            }
        }
        if (!scrollable) return {error: 'no scrollable'};

        var sh = scrollable.scrollHeight;
        var ch = scrollable.clientHeight;
        var maxScroll = sh - ch;

        // Scroll down and collect all voices
        var allVoices = new Set();
        var voiceList = [];
        var step = 200;
        for (var pos = 0; pos <= maxScroll; pos += step) {
            scrollable.scrollTop = pos;
            // Read voices at this position
            for (var opt of scrollable.querySelectorAll('.c-option')) {
                var name = opt.querySelector('.name');
                var gender = opt.querySelector('.gender');
                var useCase = opt.querySelector('.use_case');
                if (name) {
                    var n = (name.innerText || '').trim();
                    if (!allVoices.has(n)) {
                        allVoices.add(n);
                        voiceList.push({
                            name: n,
                            gender: (gender?.innerText || '').trim(),
                            useCase: (useCase?.innerText || '').trim(),
                        });
                    }
                }
            }
        }

        // Scroll back to top
        scrollable.scrollTop = 0;
        return {scrollHeight: sh, clientHeight: ch, voices: voiceList};
    }""")

    if more_voices.get('voices'):
        print(f"\n  Full voice catalog ({len(more_voices['voices'])} voices):", flush=True)
        print(f"  (scroll: {more_voices.get('scrollHeight')}px total, {more_voices.get('clientHeight')}px visible)", flush=True)
        for v in more_voices['voices']:
            print(f"    {v['name']} ({v['gender']}) — {v['useCase']}", flush=True)
    elif more_voices.get('error'):
        print(f"  {more_voices['error']}", flush=True)

    # ============================================================
    #  PART B: Click "Upload Audio" tab
    # ============================================================
    print("\n=== PART B: Upload Audio tab ===", flush=True)

    # Click the "Upload Audio" tab
    clicked = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (t === 'Upload Audio' && r.width > 80 && r.height > 20 && r.y > 150 && r.y < 250) {
                el.click();
                return true;
            }
        }
        return false;
    }""")
    print(f"  Clicked Upload Audio tab: {clicked}", flush=True)
    page.wait_for_timeout(2000)
    ss(page, "P104_01_upload_audio_tab")

    # Map the Upload Audio tab content
    upload_content = page.evaluate("""() => {
        // Find the voice picker dialog content
        var wrapper = document.querySelector('.voice-picker-wrapper');
        if (!wrapper) return {error: 'no wrapper'};

        var items = [];
        var seen = new Set();
        for (var child of wrapper.querySelectorAll('*')) {
            var r = child.getBoundingClientRect();
            if (r.width < 10 || r.height < 5) continue;
            var text = (child.innerText || '').trim();
            var cls = (child.className || '').toString();
            var tag = child.tagName;
            var key = tag + '|' + Math.round(r.y/3) + '|' + Math.round(r.x/5);
            if (seen.has(key)) continue;
            seen.add(key);
            if (text.length > 0 || tag === 'INPUT' || tag === 'BUTTON'
                || cls.includes('upload') || cls.includes('drop')
                || cls.includes('file') || cls.includes('audio')) {
                items.push({
                    tag: tag, class: cls.substring(0, 60),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: text.substring(0, 80),
                });
            }
        }
        items.sort(function(a,b){return a.y - b.y});

        // Check for file inputs
        var fileInputs = [];
        for (var inp of wrapper.querySelectorAll('input[type="file"]')) {
            fileInputs.push({
                accept: inp.accept || '',
                name: inp.name || '',
                id: inp.id || '',
                parentClass: (inp.parentElement?.className || '').toString().substring(0, 50),
            });
        }

        return {items: items.slice(0, 30), fileInputs: fileInputs};
    }""")

    if upload_content.get('items'):
        print(f"\n  Upload tab elements ({len(upload_content['items'])}):", flush=True)
        for item in upload_content['items']:
            print(f"    ({item['x']},{item['y']}) {item['w']}x{item['h']} <{item['tag']}> .{item['class'][:40]} '{item['text'][:50]}'", flush=True)

    if upload_content.get('fileInputs'):
        print(f"\n  File inputs ({len(upload_content['fileInputs'])}):", flush=True)
        for fi in upload_content['fileInputs']:
            print(f"    accept='{fi['accept']}' name='{fi['name']}' id='{fi['id']}' p=.{fi['parentClass']}", flush=True)

    # Check ALL file inputs on the page now
    all_file_inputs = page.evaluate("""() => {
        var inputs = [];
        for (var inp of document.querySelectorAll('input[type="file"]')) {
            var r = inp.getBoundingClientRect();
            inputs.push({
                accept: inp.accept || '',
                name: inp.name || '',
                id: inp.id || '',
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                parentClass: (inp.parentElement?.className || '').toString().substring(0, 80),
                display: window.getComputedStyle(inp).display,
            });
        }
        return inputs;
    }""")
    print(f"\n  All page file inputs ({len(all_file_inputs)}):", flush=True)
    for fi in all_file_inputs:
        print(f"    ({fi['x']},{fi['y']}) {fi['w']}x{fi['h']} accept='{fi['accept']}' disp={fi['display']} p=.{fi['parentClass'][:50]}", flush=True)

    # ============================================================
    #  PART C: Switch back to TTS tab + test generation
    # ============================================================
    print("\n=== PART C: TTS generation test ===", flush=True)

    # Click "Text to Speech" tab
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (t === 'Text to Speech' && r.width > 80 && r.height > 20 && r.y > 150 && r.y < 250) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    # Select "James" voice (first in list, narrative story)
    page.evaluate("""() => {
        var opts = document.querySelectorAll('.c-option');
        for (var opt of opts) {
            var name = opt.querySelector('.name');
            if (name && (name.innerText || '').trim() === 'James') {
                opt.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(500)

    # Type test text in the TTS textarea
    test_text = "Here are the top 5 wireless headphones you can buy right now."

    typed = page.evaluate("""(text) => {
        // Find the custom textarea
        var ta = document.querySelector('.custom-textarea');
        if (ta) {
            ta.focus();
            ta.textContent = text;
            // Dispatch input event
            ta.dispatchEvent(new Event('input', {bubbles: true}));
            ta.dispatchEvent(new Event('change', {bubbles: true}));
            return {found: 'custom-textarea', charCount: text.length};
        }
        // Fallback: find any textarea/editable in the voice dialog
        var wrapper = document.querySelector('.voice-picker-wrapper');
        if (wrapper) {
            var editable = wrapper.querySelector('[contenteditable="true"], textarea');
            if (editable) {
                editable.focus();
                editable.textContent = text;
                editable.dispatchEvent(new Event('input', {bubbles: true}));
                return {found: 'editable', charCount: text.length};
            }
        }
        return null;
    }""", test_text)
    print(f"  Text typed: {typed}", flush=True)
    page.wait_for_timeout(1000)
    ss(page, "P104_02_tts_text_typed")

    # Check character count
    char_count = page.evaluate("""() => {
        var stats = document.querySelector('.character-statistics');
        if (stats) return (stats.innerText || '').trim();
        return null;
    }""")
    print(f"  Character count: {char_count}", flush=True)

    # Find and click "Generate Audio" button
    gen_btn = page.evaluate("""() => {
        for (var btn of document.querySelectorAll('button')) {
            var t = (btn.innerText || '').trim();
            if (t.includes('Generate Audio') || t.includes('Generate')) {
                var r = btn.getBoundingClientRect();
                if (r.width > 100 && r.y > 600) {
                    return {
                        x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                        text: t, w: Math.round(r.width), h: Math.round(r.height),
                        disabled: btn.disabled,
                    };
                }
            }
        }
        return null;
    }""")
    print(f"  Generate button: {json.dumps(gen_btn)}", flush=True)

    if gen_btn and not gen_btn.get('disabled'):
        print("  Clicking Generate Audio...", flush=True)
        page.mouse.click(gen_btn['x'], gen_btn['y'])
        page.wait_for_timeout(15000)  # TTS generation may take time
        ss(page, "P104_03_after_generate")

        # Check what happened — audio generated?
        result_state = page.evaluate("""() => {
            // Check for audio in timeline
            var audios = document.querySelectorAll('.timeline-audio');
            var audioItems = [];
            for (var a of audios) {
                var r = a.getBoundingClientRect();
                var text = (a.innerText || '').trim();
                audioItems.push({
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: text.substring(0, 50),
                    class: (a.className || '').toString().substring(0, 50),
                });
            }

            // Check for "Pick a voice" still visible
            var pickVoice = document.querySelector('.pick-voice');
            var pvVisible = pickVoice ? pickVoice.getBoundingClientRect().width > 0 : false;

            // Check warning in panel
            var panel = document.querySelector('.c-gen-config.show');
            var panelWarning = panel ? (panel.innerText || '').trim() : '';

            // Check for audio waveform or progress
            var waveforms = [];
            for (var el of document.querySelectorAll('[class*="wave"], [class*="audio-block"], [class*="audio-item"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 10) {
                    waveforms.push({
                        class: (el.className || '').toString().substring(0, 50),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                    });
                }
            }

            return {
                audioItems: audioItems,
                pickVoiceStillVisible: pvVisible,
                panelWarning: panelWarning.substring(0, 300),
                waveforms: waveforms,
            };
        }""")

        print(f"\n  Result:", flush=True)
        print(f"    Audio items: {json.dumps(result_state.get('audioItems', []), indent=2)}", flush=True)
        print(f"    Pick voice still visible: {result_state.get('pickVoiceStillVisible')}", flush=True)
        print(f"    Panel text: {result_state.get('panelWarning', '')[:150]}", flush=True)
        print(f"    Waveforms: {json.dumps(result_state.get('waveforms', []), indent=2)}", flush=True)

        # Check if Generate button in the main panel is now ready
        main_gen = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            var btn = panel.querySelector('.generative');
            if (btn) {
                return {
                    text: (btn.innerText || '').trim(),
                    disabled: btn.disabled,
                    class: (btn.className || '').toString(),
                };
            }
            return null;
        }""")
        print(f"    Main Generate btn: {json.dumps(main_gen)}", flush=True)

    else:
        print("  Generate button not clickable or not found", flush=True)

    ss(page, "P104_04_final")
    print(f"\n\n===== PHASE 104 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
