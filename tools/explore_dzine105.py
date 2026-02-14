"""Phase 105: Complete Lip Sync — fix TTS generation + test audio upload.
Issues from P104:
- TTS "Generate Audio" button was inside voice picker (z=9998) but code found main panel's disabled "Generate"
- Upload Audio has no <input type="file"> — uses JS file chooser (page.expect_file_chooser)
- Text was typed into wrong textarea (main panel's, not voice picker's)
Goal: A) TTS: type text → Generate Audio → audio appears in timeline
      B) Upload: use file_chooser event to upload ElevenLabs audio
      C) Full Lip Sync generate (face + audio → 36 credits)
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
    """Proven flow from Phase 102."""
    print("\n--- Setting face ---", flush=True)
    page.mouse.click(40, 425)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    is_open = page.evaluate("() => !!document.querySelector('.lip-sync-config-panel.show')")
    if not is_open:
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
            if ((btn.innerText||'').includes('Face Image') && r.width > 100)
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
        }
        return null;
    }""")
    if not coords:
        return False

    page.mouse.click(coords['x'], coords['y'])
    page.wait_for_timeout(3000)

    thumb = page.evaluate("""() => {
        var d = document.querySelector('.pick-image-dialog');
        if (!d) return null;
        for (var el of d.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var bg = window.getComputedStyle(el).backgroundImage || '';
            if (r.width > 50 && r.height > 50 && bg !== 'none' && r.x > 400 && r.x < 800 && r.y > 350 && r.y < 500)
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
        }
        return null;
    }""")
    if not thumb:
        return False

    page.mouse.click(thumb['x'], thumb['y'])
    page.wait_for_timeout(4000)

    for _ in range(2):
        page.evaluate("() => { for (var b of document.querySelectorAll('button')) if ((b.innerText||'').trim()==='Next') { b.click(); return; } }")
        page.wait_for_timeout(2000)

    close_dialogs(page)
    w2 = page.evaluate("() => { var p = document.querySelector('.c-gen-config.show'); return p ? (p.innerText||'').includes('Please pick a face') : true; }")
    print(f"  Face set: {not w2}", flush=True)
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

    # ============================================================
    #  PART A: TTS GENERATION (inside voice picker dialog)
    # ============================================================
    print("\n=== PART A: TTS Generation ===", flush=True)

    # Open voice picker
    pv = page.evaluate("() => { var e = document.querySelector('.pick-voice'); if (e) { var r = e.getBoundingClientRect(); return r.width > 20 ? {x: Math.round(r.x+r.width/2), y: Math.round(r.y+r.height/2)} : null; } return null; }")
    if pv:
        page.mouse.click(pv['x'], pv['y'])
        page.wait_for_timeout(3000)
        print("  Voice picker opened", flush=True)
    else:
        print("  Pick a voice not found!", flush=True)
        os._exit(1)

    # Ensure we're on "Text to Speech" tab
    page.evaluate("""() => {
        var wrapper = document.querySelector('.voice-picker-wrapper');
        if (!wrapper) return false;
        for (var el of wrapper.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (t === 'Text to Speech' && r.width > 80 && r.y > 150 && r.y < 400) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    # Select James voice
    page.evaluate("""() => {
        for (var opt of document.querySelectorAll('.c-option')) {
            var name = opt.querySelector('.name');
            if (name && (name.innerText||'').trim() === 'James') {
                opt.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(500)

    # Map the voice picker's text area SPECIFICALLY
    textarea_info = page.evaluate("""() => {
        var wrapper = document.querySelector('.voice-picker-wrapper');
        if (!wrapper) return {error: 'no wrapper'};

        // Find text area inside the voice picker
        var textareas = [];
        for (var el of wrapper.querySelectorAll('textarea, [contenteditable="true"], .custom-textarea, [class*="textarea"]')) {
            var r = el.getBoundingClientRect();
            textareas.push({
                tag: el.tagName,
                class: (el.className || '').toString().substring(0, 60),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                editable: el.contentEditable,
                placeholder: el.getAttribute('placeholder') || '',
                textContent: (el.textContent || '').substring(0, 50),
            });
        }

        // Find "Generate Audio" button inside voice picker
        var genBtns = [];
        for (var btn of wrapper.querySelectorAll('button, [class*="generate"]')) {
            var t = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (t.includes('Generate') && r.width > 80) {
                genBtns.push({
                    tag: btn.tagName,
                    class: (btn.className || '').toString().substring(0, 60),
                    x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: t, disabled: btn.disabled,
                });
            }
        }

        return {textareas: textareas, genBtns: genBtns};
    }""")
    print(f"  Textareas in voice picker: {json.dumps(textarea_info.get('textareas', []), indent=2)}", flush=True)
    print(f"  Generate buttons in voice picker: {json.dumps(textarea_info.get('genBtns', []), indent=2)}", flush=True)

    # Type text into the voice picker's textarea
    test_text = "Here are the top five wireless headphones you can buy right now."

    # Click on the textarea first to focus it
    ta = textarea_info.get('textareas', [])
    if ta:
        first_ta = ta[0]
        print(f"  Clicking textarea at ({first_ta['x']},{first_ta['y']})", flush=True)
        page.mouse.click(first_ta['x'] + first_ta['w'] // 2, first_ta['y'] + first_ta['h'] // 2)
        page.wait_for_timeout(500)

        # Clear and type
        page.keyboard.press("Meta+a")
        page.wait_for_timeout(200)
        page.keyboard.type(test_text, delay=20)
        page.wait_for_timeout(1000)

    ss(page, "P105_01_tts_text_typed")

    # Check character count in voice picker
    char_info = page.evaluate("""() => {
        var wrapper = document.querySelector('.voice-picker-wrapper');
        if (!wrapper) return null;
        for (var el of wrapper.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            if (t.match(/\\d+\\/\\d+/)) return t;
        }
        return null;
    }""")
    print(f"  Voice picker char count: {char_info}", flush=True)

    # Find and click "Generate Audio" button INSIDE voice picker
    gen_btns = textarea_info.get('genBtns', [])
    gen_audio_btn = None
    for gb in gen_btns:
        if 'Audio' in gb.get('text', '') or 'Free' in gb.get('text', ''):
            gen_audio_btn = gb
            break
    if not gen_audio_btn and gen_btns:
        gen_audio_btn = gen_btns[0]

    if gen_audio_btn:
        print(f"  Generate Audio btn: ({gen_audio_btn['x']},{gen_audio_btn['y']}) '{gen_audio_btn['text']}' disabled={gen_audio_btn.get('disabled')}", flush=True)

        if not gen_audio_btn.get('disabled'):
            print("  Clicking Generate Audio...", flush=True)
            page.mouse.click(gen_audio_btn['x'], gen_audio_btn['y'])

            # Wait for generation (FREE TTS, should be quick)
            print("  Waiting for audio generation...", flush=True)
            page.wait_for_timeout(20000)
            ss(page, "P105_02_after_tts_generate")

            # Check result — has audio appeared in timeline?
            tts_result = page.evaluate("""() => {
                // Check if voice picker closed
                var picker = document.querySelector('.voice-picker-wrapper');
                var pickerVisible = picker ? picker.getBoundingClientRect().width > 0 : false;

                // Check timeline for audio
                var timelineAudio = document.querySelector('.timeline-audios');
                var audioText = timelineAudio ? (timelineAudio.innerText || '').trim() : '';

                // Check "Pick a voice" still visible
                var pv = document.querySelector('.pick-voice');
                var pvVisible = pv ? pv.getBoundingClientRect().width > 0 : false;

                // Check for waveform/audio-block elements
                var audioBlocks = [];
                for (var el of document.querySelectorAll('[class*="audio-block"], [class*="waveform"], [class*="audio-item"], .audio-bar')) {
                    var r = el.getBoundingClientRect();
                    audioBlocks.push({
                        class: (el.className || '').toString().substring(0, 50),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                    });
                }

                // Check panel warning
                var panel = document.querySelector('.c-gen-config.show');
                var panelText = panel ? (panel.innerText || '').trim().substring(0, 300) : '';

                // Check play button time
                var playTime = document.querySelector('.play-time');
                var timeText = playTime ? (playTime.innerText || '').trim() : '';

                return {
                    pickerVisible: pickerVisible,
                    pvVisible: pvVisible,
                    audioText: audioText,
                    audioBlocks: audioBlocks,
                    panelText: panelText.substring(0, 200),
                    playTime: timeText,
                };
            }""")

            print(f"\n  TTS Result:", flush=True)
            print(f"    Picker still visible: {tts_result.get('pickerVisible')}", flush=True)
            print(f"    Pick voice visible: {tts_result.get('pvVisible')}", flush=True)
            print(f"    Timeline audio text: '{tts_result.get('audioText')}'", flush=True)
            print(f"    Audio blocks: {json.dumps(tts_result.get('audioBlocks', []))}", flush=True)
            print(f"    Panel text: {tts_result.get('panelText', '')[:150]}", flush=True)
            print(f"    Play time: {tts_result.get('playTime')}", flush=True)

            # If audio was generated, check if main Generate button is now enabled
            main_gen = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return null;
                var btn = panel.querySelector('.generative');
                if (btn) return {text: (btn.innerText||'').trim(), disabled: btn.disabled, class: (btn.className||'').toString()};
                return null;
            }""")
            print(f"    Main Generate: {json.dumps(main_gen)}", flush=True)

        else:
            print("  Generate Audio button is DISABLED", flush=True)
            # Check why — need text in the textarea?
            ta_content = page.evaluate("""() => {
                var wrapper = document.querySelector('.voice-picker-wrapper');
                if (!wrapper) return null;
                var ta = wrapper.querySelector('.custom-textarea, textarea, [contenteditable]');
                if (ta) return {text: (ta.textContent||'').substring(0, 100), tag: ta.tagName};
                return null;
            }""")
            print(f"  Textarea content: {ta_content}", flush=True)
    else:
        print("  No Generate Audio button found in voice picker!", flush=True)

    # ============================================================
    #  PART B: Check if we can now run full Lip Sync generation
    # ============================================================
    print("\n=== PART B: Full Lip Sync generation readiness ===", flush=True)

    readiness = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};

        var text = (panel.innerText || '').trim();
        var hasVoiceWarning = text.includes('Please create or upload a voice');
        var hasFaceWarning = text.includes('Please pick a face');

        var genBtn = panel.querySelector('.generative');
        var genDisabled = genBtn ? genBtn.disabled : true;
        var genText = genBtn ? (genBtn.innerText || '').trim() : '';

        return {
            hasVoiceWarning: hasVoiceWarning,
            hasFaceWarning: hasFaceWarning,
            genDisabled: genDisabled,
            genText: genText,
            fullText: text.substring(0, 400),
        };
    }""")
    print(f"  Readiness:", flush=True)
    print(f"    Face warning: {readiness.get('hasFaceWarning')}", flush=True)
    print(f"    Voice warning: {readiness.get('hasVoiceWarning')}", flush=True)
    print(f"    Generate disabled: {readiness.get('genDisabled')}", flush=True)
    print(f"    Generate text: {readiness.get('genText')}", flush=True)

    ss(page, "P105_03_final")
    print(f"\n\n===== PHASE 105 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
