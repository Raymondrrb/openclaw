"""Phase 108: Wait for Lip Sync generation to complete.
P107: Generation started (green progress bar visible), but stopped too early.
Goal: 1) Check if P107's generation completed  2) If not, repeat and wait up to 3min
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


def generate_tts_and_apply(page, text):
    """Full flow: open voice picker → type text → generate → apply."""
    pv = page.evaluate("() => { var e=document.querySelector('.pick-voice'); if(e){var r=e.getBoundingClientRect(); return r.width>20?{x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)}:null;} return null; }")
    if not pv:
        print("  No pick voice button!", flush=True)
        return False
    page.mouse.click(pv['x'], pv['y'])
    page.wait_for_timeout(3000)

    # TTS tab
    page.evaluate("() => { var w=document.querySelector('.voice-picker-wrapper'); if(!w) return; for(var e of w.querySelectorAll('*')) if((e.innerText||'').trim()==='Text to Speech'&&e.getBoundingClientRect().width>80){e.click();return;} }")
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
        return False

    # Generate Audio
    gen = page.evaluate("() => { var b=document.querySelector('.gen-audio-btn'); if(b&&!b.disabled){var r=b.getBoundingClientRect(); return {x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)};} return null; }")
    if not gen:
        return False
    page.mouse.click(gen['x'], gen['y'])
    print("  TTS generating...", flush=True)

    # Wait for Apply button
    for i in range(30):
        has_apply = page.evaluate("() => { for(var b of document.querySelectorAll('button')) if((b.innerText||'').trim()==='Apply'&&b.getBoundingClientRect().width>50) return true; return false; }")
        if has_apply:
            print(f"  TTS done in ~{(i+1)*2}s", flush=True)
            break
        page.wait_for_timeout(2000)
    else:
        return False

    # Click Apply
    page.evaluate("() => { for(var b of document.querySelectorAll('button')) if((b.innerText||'').trim()==='Apply'&&b.getBoundingClientRect().width>50){b.click();return;} }")
    page.wait_for_timeout(5000)
    close_dialogs(page)
    return True


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
    #  STEP 1: Check if P107's generation already completed
    # ============================================================
    print("\n=== STEP 1: Check for existing results ===", flush=True)

    # Open Lip Sync panel
    page.mouse.click(40, 425)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    existing = page.evaluate("""() => {
        // Check results panel for lip sync videos
        var results = document.querySelector('.result-panel');
        if (!results) return {hasResults: false};

        var videos = results.querySelectorAll('video');
        var videoInfos = [];
        for (var v of videos) {
            var r = v.getBoundingClientRect();
            if (r.width > 50) {
                videoInfos.push({
                    src: (v.src || v.currentSrc || '').substring(0, 150),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }
        }

        // Check for lip sync result items
        var lsResults = [];
        for (var el of results.querySelectorAll('.result-item')) {
            var text = (el.innerText || '').trim();
            if (text.includes('Lip Sync')) {
                var r = el.getBoundingClientRect();
                lsResults.push({
                    text: text.substring(0, 80),
                    y: Math.round(r.y),
                });
            }
        }

        // Check if Generate button is in progress
        var panel = document.querySelector('.c-gen-config.show');
        var genBtn = panel ? panel.querySelector('.generative') : null;
        var genState = 'unknown';
        if (genBtn) {
            var cls = (genBtn.className || '').toString();
            if (cls.includes('loading') || cls.includes('progress')) genState = 'loading';
            else if (genBtn.disabled) genState = 'disabled';
            else genState = 'ready';
        }

        return {
            hasResults: videoInfos.length > 0 || lsResults.length > 0,
            videos: videoInfos,
            lsResults: lsResults,
            genState: genState,
        };
    }""")
    print(f"  Existing results: {json.dumps(existing, indent=2)}", flush=True)

    # Check panel state
    panel_state = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};
        var text = (panel.innerText || '').trim();
        return {
            hasFaceWarning: text.includes('Please pick a face'),
            hasVoiceWarning: text.includes('Please create or upload a voice'),
            text: text.substring(0, 300),
        };
    }""")
    print(f"  Panel: face={panel_state.get('hasFaceWarning')}, voice={panel_state.get('hasVoiceWarning')}", flush=True)

    # ============================================================
    #  STEP 2: Set up if needed (face + audio)
    # ============================================================
    needs_setup = panel_state.get('hasFaceWarning') or panel_state.get('hasVoiceWarning')

    if needs_setup:
        print("\n=== STEP 2: Setting up face + audio ===", flush=True)

        if panel_state.get('hasFaceWarning'):
            face_ok = set_face(page)
            if not face_ok:
                print("ABORT: face not set", flush=True)
                os._exit(1)

        if panel_state.get('hasVoiceWarning'):
            audio_ok = generate_tts_and_apply(page, "Here are the top five wireless headphones you can buy right now. Each one offers great sound quality.")
            if not audio_ok:
                print("ABORT: TTS failed", flush=True)
                os._exit(1)

    ss(page, "P108_01_ready")

    # ============================================================
    #  STEP 3: Generate Lip Sync video
    # ============================================================
    print("\n=== STEP 3: Generate Lip Sync ===", flush=True)

    gen_btn = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return null;
        var btn = panel.querySelector('.generative');
        if (!btn) return null;
        var r = btn.getBoundingClientRect();
        return {
            x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
            disabled: btn.disabled, text: (btn.innerText||'').trim(),
            class: (btn.className||'').toString().substring(0, 60),
        };
    }""")
    print(f"  Generate btn: {json.dumps(gen_btn)}", flush=True)

    if not gen_btn or gen_btn.get('disabled'):
        print("  Generate button not ready!", flush=True)
        ss(page, "P108_02_not_ready")
        os._exit(1)

    print(f"  Clicking Generate ({gen_btn['text']})...", flush=True)
    page.mouse.click(gen_btn['x'], gen_btn['y'])
    page.wait_for_timeout(3000)
    ss(page, "P108_02_generating")

    # Wait for generation to complete (up to 3 minutes)
    print("  Waiting for lip sync generation (up to 3min)...", flush=True)
    start = time.time()
    completed = False

    for i in range(60):
        elapsed = int(time.time() - start)

        status = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            var btn = panel ? panel.querySelector('.generative') : null;
            var btnText = btn ? (btn.innerText||'').trim() : '';
            var btnClass = btn ? (btn.className||'').toString() : '';
            var btnDisabled = btn ? btn.disabled : true;

            // Check for video elements in results
            var videos = [];
            for (var v of document.querySelectorAll('video')) {
                var r = v.getBoundingClientRect();
                if (r.width > 50) {
                    videos.push({
                        src: (v.src || v.currentSrc || '').substring(0, 150),
                        w: Math.round(r.width), h: Math.round(r.height),
                    });
                }
            }

            // Check for lip sync result in results panel
            var resultPanel = document.querySelector('.c-material-library-v2');
            var rpText = resultPanel ? (resultPanel.innerText||'').substring(0, 200) : '';

            // Check for toast/notification
            var toast = document.querySelector('.show-message');
            var toastText = toast ? (toast.innerText||'').trim() : '';

            // Check generate button state more deeply
            var isLoading = btnClass.includes('loading') || btnClass.includes('progress');
            var hasSpinner = btn ? btn.querySelector('[class*="spin"], [class*="loading"], .ico-loading') !== null : false;

            return {
                btnText: btnText, btnDisabled: btnDisabled, btnClass: btnClass.substring(0, 60),
                isLoading: isLoading, hasSpinner: hasSpinner,
                videoCount: videos.length, videos: videos,
                rpText: rpText.substring(0, 100),
                toastText: toastText.substring(0, 100),
            };
        }""")

        if status.get('videoCount', 0) > 0:
            print(f"  VIDEO FOUND at {elapsed}s!", flush=True)
            completed = True
            break

        # Check if button returned to ready state (generation done)
        if not status.get('isLoading') and not status.get('hasSpinner') and 'Generate' in status.get('btnText', '') and not status.get('btnDisabled'):
            # Button is back to Generate state — check if it completed or failed
            if i > 5:  # Only after at least 15s
                print(f"  Button returned to ready at {elapsed}s (may have completed or failed)", flush=True)
                break

        if i % 5 == 0:
            print(f"  ...{elapsed}s btn='{status.get('btnText','?')[:20]}' loading={status.get('isLoading')} videos={status.get('videoCount')} toast='{status.get('toastText','')[:40]}'", flush=True)

        if i % 10 == 0 and i > 0:
            ss(page, f"P108_progress_{elapsed}s")

        page.wait_for_timeout(3000)

    ss(page, "P108_03_after_generate")

    # ============================================================
    #  STEP 4: Check final state
    # ============================================================
    print("\n=== STEP 4: Final state ===", flush=True)

    final = page.evaluate("""() => {
        // All video elements
        var videos = [];
        for (var v of document.querySelectorAll('video')) {
            var r = v.getBoundingClientRect();
            videos.push({
                src: (v.src || v.currentSrc || '').substring(0, 200),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                duration: v.duration || 0,
                visible: r.width > 0,
            });
        }

        // Results panel items
        var resultItems = [];
        for (var el of document.querySelectorAll('.result-item')) {
            var text = (el.innerText || '').trim();
            resultItems.push(text.substring(0, 80));
        }

        // Check for any Lip Sync specific results
        var lsResults = [];
        for (var el of document.querySelectorAll('[class*="lip-sync"], [class*="lipsync"]')) {
            var r = el.getBoundingClientRect();
            if (r.width > 10) {
                lsResults.push({
                    class: (el.className||'').toString().substring(0, 50),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }
        }

        // Panel state
        var panel = document.querySelector('.c-gen-config.show');
        var panelText = panel ? (panel.innerText||'').trim().substring(0, 200) : '';

        return {
            videos: videos,
            resultItems: resultItems.slice(0, 5),
            lsResults: lsResults.slice(0, 5),
            panelText: panelText,
        };
    }""")

    print(f"  Videos ({len(final.get('videos', []))}):", flush=True)
    for v in final.get('videos', []):
        print(f"    ({v['x']},{v['y']}) {v['w']}x{v['h']} dur={v['duration']}s vis={v['visible']}", flush=True)
        print(f"      src={v['src'][:100]}", flush=True)
    print(f"  Result items: {final.get('resultItems', [])[:3]}", flush=True)
    print(f"  LS results: {final.get('lsResults', [])}", flush=True)
    print(f"  Panel: {final.get('panelText', '')[:150]}", flush=True)

    # Check results panel scroll position for lip sync results
    scroll_results = page.evaluate("""() => {
        var rp = document.querySelector('.material-v2-result-content');
        if (!rp) return null;
        // Scroll to top to see latest result
        rp.scrollTop = 0;
        var firstItem = rp.querySelector('.result-item');
        if (firstItem) {
            var text = (firstItem.innerText || '').trim();
            return {
                scrollHeight: rp.scrollHeight,
                firstResultText: text.substring(0, 100),
            };
        }
        return {scrollHeight: rp.scrollHeight};
    }""")
    print(f"  Results scroll: {json.dumps(scroll_results)}", flush=True)

    ss(page, "P108_04_final")
    print(f"\n\n===== PHASE 108 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
