"""Phase 107: Complete Lip Sync — Apply audio + Generate lip sync video.
P106: TTS worked! Audio generated (3s), waveform visible, "Apply" button ready.
Flow: Apply audio → main Generate (36 credits) → lip sync video.
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


def generate_tts(page, text):
    """Open voice picker, type text, generate TTS, apply to timeline."""
    print(f"\n--- Generating TTS: '{text[:50]}...' ---", flush=True)

    # Open voice picker
    pv = page.evaluate("() => { var e=document.querySelector('.pick-voice'); if(e){var r=e.getBoundingClientRect(); return r.width>20?{x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)}:null;} return null; }")
    if not pv:
        print("  No pick voice button!", flush=True)
        return False
    page.mouse.click(pv['x'], pv['y'])
    page.wait_for_timeout(3000)

    # Ensure TTS tab
    page.evaluate("""() => {
        var w = document.querySelector('.voice-picker-wrapper');
        if (!w) return;
        for (var el of w.querySelectorAll('*')) {
            if ((el.innerText||'').trim() === 'Text to Speech' && el.getBoundingClientRect().width > 80) {
                el.click(); return;
            }
        }
    }""")
    page.wait_for_timeout(500)

    # Type text
    ta = page.locator('.voice-picker-wrapper .editable-textarea')
    if ta.count() > 0:
        ta.first.click()
        page.wait_for_timeout(300)
        page.keyboard.press("Meta+a")
        page.wait_for_timeout(200)
        page.keyboard.type(text, delay=20)
        page.wait_for_timeout(1000)
    else:
        print("  No textarea!", flush=True)
        return False

    # Click Generate Audio
    gen = page.evaluate("() => { var b = document.querySelector('.gen-audio-btn'); if(b&&!b.disabled){var r=b.getBoundingClientRect(); return {x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)};} return null; }")
    if not gen:
        print("  Generate Audio button disabled!", flush=True)
        return False

    page.mouse.click(gen['x'], gen['y'])
    print("  Generating TTS audio...", flush=True)

    # Wait for generation (check for Apply button)
    for i in range(30):
        has_apply = page.evaluate("""() => {
            for (var b of document.querySelectorAll('button')) {
                if ((b.innerText||'').trim() === 'Apply' && b.getBoundingClientRect().width > 50)
                    return true;
            }
            return false;
        }""")
        if has_apply:
            print(f"  TTS generated in ~{(i+1)*2}s", flush=True)
            return True
        page.wait_for_timeout(2000)

    print("  TTS generation timed out (60s)", flush=True)
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

    # STEP 1: Set face
    face_ok = set_face(page)
    if not face_ok:
        print("ABORT: face not set", flush=True)
        os._exit(1)

    # STEP 2: Generate TTS
    tts_ok = generate_tts(page, "Here are the top five wireless headphones you can buy right now. Each one offers incredible sound quality and comfort.")
    if not tts_ok:
        print("ABORT: TTS generation failed", flush=True)
        os._exit(1)

    ss(page, "P107_01_tts_done")

    # ============================================================
    #  STEP 3: Click "Apply" to add audio to timeline
    # ============================================================
    print("\n=== STEP 3: Click Apply ===", flush=True)

    apply_btn = page.evaluate("""() => {
        for (var b of document.querySelectorAll('button')) {
            var t = (b.innerText || '').trim();
            var r = b.getBoundingClientRect();
            if (t === 'Apply' && r.width > 50 && r.y > 600) {
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                        w: Math.round(r.width), class: (b.className||'').toString()};
            }
        }
        return null;
    }""")

    if apply_btn:
        print(f"  Apply btn: ({apply_btn['x']},{apply_btn['y']}) {apply_btn['w']}px .{apply_btn['class'][:40]}", flush=True)
        page.mouse.click(apply_btn['x'], apply_btn['y'])
        page.wait_for_timeout(5000)
        close_dialogs(page)
        ss(page, "P107_02_after_apply")
    else:
        print("  Apply button not found!", flush=True)
        os._exit(1)

    # ============================================================
    #  STEP 4: Check panel state — ready for generation?
    # ============================================================
    print("\n=== STEP 4: Check readiness ===", flush=True)

    readiness = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};

        var text = (panel.innerText || '').trim();
        var hasFaceWarning = text.includes('Please pick a face');
        var hasVoiceWarning = text.includes('Please create or upload a voice');

        var genBtn = panel.querySelector('.generative');
        var genDisabled = genBtn ? genBtn.disabled : true;
        var genText = genBtn ? (genBtn.innerText || '').trim() : '';
        var genReady = genBtn ? genBtn.classList.contains('ready') : false;

        return {
            hasFaceWarning: hasFaceWarning,
            hasVoiceWarning: hasVoiceWarning,
            genDisabled: genDisabled,
            genReady: genReady,
            genText: genText,
            panelText: text.substring(0, 300),
        };
    }""")
    print(f"  Face warning: {readiness.get('hasFaceWarning')}", flush=True)
    print(f"  Voice warning: {readiness.get('hasVoiceWarning')}", flush=True)
    print(f"  Generate disabled: {readiness.get('genDisabled')}", flush=True)
    print(f"  Generate ready: {readiness.get('genReady')}", flush=True)
    print(f"  Generate text: {readiness.get('genText')}", flush=True)

    # Check timeline for audio
    timeline = page.evaluate("""() => {
        var ta = document.querySelector('.timeline-audios');
        if (!ta) return {error: 'no .timeline-audios'};
        var text = (ta.innerText || '').trim();

        // Check for audio blocks/waveforms in timeline
        var audioBlocks = [];
        for (var el of ta.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var cls = (el.className || '').toString();
            if (r.width > 10 && r.height > 5 && cls.length > 0) {
                audioBlocks.push({
                    class: cls.substring(0, 40),
                    x: Math.round(r.x), w: Math.round(r.width),
                    text: (el.innerText || '').trim().substring(0, 30),
                });
            }
        }

        // Check play time
        var playTime = document.querySelector('.play-time');
        var timeText = playTime ? (playTime.innerText || '').trim() : '';

        return {text: text.substring(0, 100), audioBlocks: audioBlocks.slice(0, 10), playTime: timeText};
    }""")
    print(f"\n  Timeline audio:", flush=True)
    print(f"    Text: '{timeline.get('text', '')}'", flush=True)
    print(f"    Play time: {timeline.get('playTime')}", flush=True)
    print(f"    Audio blocks: {len(timeline.get('audioBlocks', []))}", flush=True)
    for ab in timeline.get('audioBlocks', [])[:5]:
        print(f"      .{ab['class'][:30]} x={ab['x']} w={ab['w']} '{ab['text']}'", flush=True)

    # ============================================================
    #  STEP 5: Generate Lip Sync Video (36 credits)
    # ============================================================
    if not readiness.get('hasFaceWarning') and not readiness.get('hasVoiceWarning'):
        print("\n=== STEP 5: Generate Lip Sync (36 credits) ===", flush=True)

        gen_btn = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            var btn = panel.querySelector('.generative');
            if (!btn) return null;
            var r = btn.getBoundingClientRect();
            return {
                x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                disabled: btn.disabled, text: (btn.innerText||'').trim(),
                ready: btn.classList.contains('ready'),
            };
        }""")
        print(f"  Main Generate: {json.dumps(gen_btn)}", flush=True)

        if gen_btn and not gen_btn.get('disabled'):
            print("  Clicking Generate (36 credits)...", flush=True)
            page.mouse.click(gen_btn['x'], gen_btn['y'])

            # Wait for generation — lip sync can take 1-3 minutes
            print("  Waiting for lip sync generation...", flush=True)
            for i in range(60):
                progress = page.evaluate("""() => {
                    // Check for progress indicator
                    var progress = document.querySelector('[class*="progress"], [class*="loading"]');
                    var pText = progress ? (progress.className || '').toString() : 'none';

                    // Check for result video
                    var videos = document.querySelectorAll('video');
                    var videoCount = 0;
                    for (var v of videos) {
                        if (v.getBoundingClientRect().width > 100) videoCount++;
                    }

                    // Check for completion
                    var resultPanel = document.querySelector('.result-panel');
                    var resultText = resultPanel ? (resultPanel.innerText || '').substring(0, 100) : '';

                    // Check for error
                    var error = null;
                    for (var el of document.querySelectorAll('[class*="error"], [class*="fail"]')) {
                        var t = (el.innerText || '').trim();
                        if (t.length > 5) error = t.substring(0, 100);
                    }

                    return {progress: pText.substring(0, 50), videoCount: videoCount,
                            resultText: resultText, error: error};
                }""")

                if progress.get('videoCount', 0) > 0:
                    print(f"  Video found after ~{(i+1)*3}s!", flush=True)
                    break
                if progress.get('error'):
                    print(f"  Error: {progress['error']}", flush=True)
                    break
                if i % 10 == 0:
                    print(f"  ...{(i+1)*3}s progress={progress.get('progress','?')}", flush=True)

                page.wait_for_timeout(3000)

            ss(page, "P107_03_after_lipsync_generate")

            # Final state check
            final = page.evaluate("""() => {
                var videos = [];
                for (var v of document.querySelectorAll('video')) {
                    var r = v.getBoundingClientRect();
                    if (r.width > 50) {
                        videos.push({
                            src: (v.src || v.currentSrc || '').substring(0, 150),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            duration: v.duration,
                        });
                    }
                }

                // Check results panel for lip sync result
                var results = [];
                for (var el of document.querySelectorAll('.result-item, [class*="lip-sync-result"]')) {
                    var text = (el.innerText || '').trim();
                    if (text.length > 0) results.push(text.substring(0, 80));
                }

                return {videos: videos, results: results.slice(0, 5)};
            }""")
            print(f"\n  Final state:", flush=True)
            print(f"    Videos: {json.dumps(final.get('videos', []), indent=2)}", flush=True)
            print(f"    Results: {final.get('results', [])}", flush=True)

        else:
            print("  Generate button is disabled/not found!", flush=True)
            print(f"  btn: {gen_btn}", flush=True)
    else:
        print("\n  NOT READY for generation:", flush=True)
        if readiness.get('hasFaceWarning'):
            print("    Missing: face image", flush=True)
        if readiness.get('hasVoiceWarning'):
            print("    Missing: voice/audio", flush=True)

    ss(page, "P107_04_final")
    print(f"\n\n===== PHASE 107 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
