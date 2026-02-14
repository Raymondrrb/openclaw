"""Phase 109: Img2Img generation test — select model + prompt + generate.
Phase 100 mapped 218 models across 13 categories. Panel structure mapped in Phase 94/99.
Goal: 1) Open Img2Img  2) Select "Realistic Product" model  3) Type prompt  4) Generate
      5) Check result in Results panel
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


def close_lip_sync_panel(page):
    """Close the lip-sync-config-panel if it's blocking."""
    page.evaluate("""() => {
        var lsp = document.querySelector('.lip-sync-config-panel.show');
        if (lsp) {
            lsp.classList.remove('show');
            return true;
        }
        // Also close any open gen config panel
        var close = document.querySelector('.c-gen-config.show .ico-close');
        if (close) close.click();
        return false;
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
    #  STEP 1: Close any blocking panels + open Img2Img
    # ============================================================
    print("\n=== STEP 1: Open Img2Img ===", flush=True)

    close_lip_sync_panel(page)
    page.wait_for_timeout(1000)

    # Click Img2Img at (40, 252)
    page.mouse.click(40, 252)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    # Verify Img2Img panel
    panel = page.evaluate("""() => {
        var p = document.querySelector('.img2img-config-panel');
        if (!p) return null;
        var r = p.getBoundingClientRect();
        var show = p.classList.contains('show');
        return {
            show: show,
            x: Math.round(r.x), y: Math.round(r.y),
            w: Math.round(r.width), h: Math.round(r.height),
            text: (p.innerText || '').substring(0, 200),
        };
    }""")
    print(f"  Panel: {json.dumps(panel)}", flush=True)

    if not panel or not panel.get('show'):
        # Try clicking again after ensuring no blocking panel
        print("  Img2Img not open, retrying...", flush=True)
        close_lip_sync_panel(page)
        page.wait_for_timeout(500)
        page.mouse.click(40, 252)
        page.wait_for_timeout(3000)
        close_dialogs(page)

    ss(page, "P109_01_img2img_panel")

    # ============================================================
    #  STEP 2: Map current panel state
    # ============================================================
    print("\n=== STEP 2: Panel state ===", flush=True)

    state = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return {error: 'no panel'};

        var styleName = p.querySelector('.style-name');
        var prompt = p.querySelector('.custom-textarea, .textarea-extend, [contenteditable]');
        var genBtn = p.querySelector('.generative');

        return {
            title: (p.querySelector('h5')?.innerText || '').trim(),
            model: styleName ? (styleName.innerText || '').trim() : null,
            promptText: prompt ? (prompt.textContent || '').substring(0, 100) : null,
            genText: genBtn ? (genBtn.innerText || '').trim() : null,
            genDisabled: genBtn ? genBtn.disabled : true,
            fullText: (p.innerText || '').substring(0, 400),
        };
    }""")
    print(f"  Title: {state.get('title')}", flush=True)
    print(f"  Current model: {state.get('model')}", flush=True)
    print(f"  Prompt: {state.get('promptText')}", flush=True)
    print(f"  Generate: {state.get('genText')} disabled={state.get('genDisabled')}", flush=True)

    # ============================================================
    #  STEP 3: Select "Realistic Product" model
    # ============================================================
    print("\n=== STEP 3: Select Realistic Product model ===", flush=True)

    # Click style-name to open selector
    page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return;
        var sn = p.querySelector('.style-name');
        if (sn) sn.click();
    }""")
    page.wait_for_timeout(3000)

    # Find and click "Realistic" category
    page.evaluate("""(catName) => {
        for (var el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.width > 600 && r.height > 400 && r.x > 100) {
                for (var item of el.querySelectorAll('*')) {
                    var text = (item.innerText || '').trim();
                    var ir = item.getBoundingClientRect();
                    if (text === catName && ir.x < 400 && ir.width > 30 && ir.height > 10 && ir.height < 40) {
                        item.click(); return true;
                    }
                }
            }
        }
        return false;
    }""", "Realistic")
    page.wait_for_timeout(1500)

    # Find and click "Realistic Product" model
    clicked_model = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.width > 500 && r.height > 300 && r.x > 350) {
                for (var child of el.querySelectorAll('*')) {
                    var text = (child.innerText || '').trim();
                    var cr = child.getBoundingClientRect();
                    if (text === 'Realistic Product' && cr.height < 25 && cr.height > 8) {
                        // Click the parent card/thumbnail, not just the text
                        var parent = child.parentElement;
                        while (parent && parent.getBoundingClientRect().height < 50) {
                            parent = parent.parentElement;
                        }
                        if (parent) {
                            parent.click();
                            return {clicked: 'parent', text: text};
                        }
                        child.click();
                        return {clicked: 'text', text: text};
                    }
                }
            }
        }
        return null;
    }""")
    print(f"  Clicked model: {clicked_model}", flush=True)
    page.wait_for_timeout(2000)
    ss(page, "P109_02_model_selected")

    # Verify model changed
    new_model = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return null;
        var sn = p.querySelector('.style-name');
        return sn ? (sn.innerText || '').trim() : null;
    }""")
    print(f"  Model now: {new_model}", flush=True)

    # ============================================================
    #  STEP 4: Type prompt
    # ============================================================
    print("\n=== STEP 4: Type prompt ===", flush=True)

    prompt_text = "Professional product photo of premium wireless headphones on a clean white background, studio lighting, high resolution, commercial photography"

    # Find the prompt textarea in the Img2Img panel
    ta_info = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return null;
        var ta = p.querySelector('.custom-textarea, [contenteditable="true"]');
        if (ta) {
            var r = ta.getBoundingClientRect();
            return {
                tag: ta.tagName, class: (ta.className||'').toString().substring(0, 50),
                x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                w: Math.round(r.width), h: Math.round(r.height),
                editable: ta.contentEditable,
            };
        }
        return null;
    }""")
    print(f"  Textarea: {json.dumps(ta_info)}", flush=True)

    if ta_info:
        page.mouse.click(ta_info['x'], ta_info['y'])
        page.wait_for_timeout(300)
        page.keyboard.press("Meta+a")
        page.wait_for_timeout(200)
        page.keyboard.type(prompt_text, delay=10)
        page.wait_for_timeout(1000)
        print(f"  Typed prompt ({len(prompt_text)} chars)", flush=True)

    ss(page, "P109_03_prompt_typed")

    # ============================================================
    #  STEP 5: Check quality/aspect settings + generate
    # ============================================================
    print("\n=== STEP 5: Settings + Generate ===", flush=True)

    settings = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return null;

        // Quality
        var quality = null;
        for (var el of p.querySelectorAll('.quality-options .options, [class*="quality"] .selected')) {
            if ((el.className||'').includes('selected') || (el.className||'').includes('active')) {
                quality = (el.innerText || '').trim();
            }
        }

        // Aspect ratio
        var aspect = null;
        for (var el of p.querySelectorAll('[class*="ratio"] .selected, [class*="aspect"] .selected')) {
            aspect = (el.innerText || '').trim();
        }

        // Generate button
        var gen = p.querySelector('.generative');
        var genInfo = gen ? {
            text: (gen.innerText || '').trim(),
            disabled: gen.disabled,
            x: Math.round(gen.getBoundingClientRect().x + gen.getBoundingClientRect().width/2),
            y: Math.round(gen.getBoundingClientRect().y + gen.getBoundingClientRect().height/2),
        } : null;

        // Number of images
        var numImages = null;
        for (var el of p.querySelectorAll('[class*="num"], [class*="count"]')) {
            var t = (el.innerText || '').trim();
            if (t.match(/^\d+$/)) numImages = t;
        }

        return {quality, aspect, gen: genInfo, numImages};
    }""")
    print(f"  Settings: {json.dumps(settings, indent=2)}", flush=True)

    # Count initial results
    initial_results = page.evaluate("""() => {
        var imgs = document.querySelectorAll('.result-panel img[src*="stylar_product"]');
        return imgs.length;
    }""")
    print(f"  Initial result images: {initial_results}", flush=True)

    # Click Generate
    if settings and settings.get('gen') and not settings['gen'].get('disabled'):
        gen = settings['gen']
        print(f"  Clicking Generate ({gen['text']})...", flush=True)
        page.mouse.click(gen['x'], gen['y'])

        # Wait for generation
        print("  Waiting for Img2Img generation...", flush=True)
        for i in range(40):
            elapsed = (i + 1) * 3

            check = page.evaluate("""(initCount) => {
                // Check for new result images
                var imgs = document.querySelectorAll('.result-panel img[src*="stylar_product"]');
                var newCount = imgs.length;

                // Check button state
                var p = document.querySelector('.c-gen-config.show');
                var gen = p ? p.querySelector('.generative') : null;
                var btnText = gen ? (gen.innerText || '').trim() : '';
                var btnClass = gen ? (gen.className || '').toString() : '';

                // Check for loading/progress
                var isGenerating = btnClass.includes('loading') || btnClass.includes('progress')
                    || !gen || gen.disabled;

                // Check for toast
                var toast = document.querySelector('.show-message');
                var toastText = toast ? (toast.innerText || '').trim() : '';

                return {
                    resultCount: newCount,
                    newImages: newCount - initCount,
                    isGenerating: isGenerating,
                    btnText: btnText.substring(0, 30),
                    toastText: toastText.substring(0, 50),
                };
            }""", initial_results)

            if check.get('newImages', 0) > 0:
                print(f"  {check['newImages']} new images at {elapsed}s!", flush=True)
                break

            if not check.get('isGenerating') and elapsed > 15:
                print(f"  Generation seems done at {elapsed}s (btn ready)", flush=True)
                break

            if i % 5 == 0:
                print(f"  ...{elapsed}s results={check.get('resultCount')} gen={check.get('isGenerating')} toast='{check.get('toastText','')}'", flush=True)

            page.wait_for_timeout(3000)

        ss(page, "P109_04_after_generate")

        # ============================================================
        #  STEP 6: Check results
        # ============================================================
        print("\n=== STEP 6: Check results ===", flush=True)

        results = page.evaluate("""() => {
            // Get all result images
            var imgs = [];
            for (var img of document.querySelectorAll('.result-panel img')) {
                var r = img.getBoundingClientRect();
                var src = img.src || '';
                if (r.width > 50 && r.height > 50 && src.includes('stylar_product')) {
                    imgs.push({
                        src: src.substring(0, 150),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                    });
                }
            }

            // Get first result item info
            var firstResult = document.querySelector('.result-panel .result-item');
            var firstText = firstResult ? (firstResult.innerText || '').substring(0, 100) : '';

            return {images: imgs.slice(0, 5), firstResultText: firstText};
        }""")

        print(f"  Result images ({len(results.get('images', []))}):", flush=True)
        for img in results.get('images', [])[:3]:
            print(f"    ({img['x']},{img['y']}) {img['w']}x{img['h']}", flush=True)
            print(f"      src={img['src'][:80]}", flush=True)
        print(f"  First result: {results.get('firstResultText', '')[:80]}", flush=True)

    else:
        print("  Generate button not ready!", flush=True)

    ss(page, "P109_05_final")
    print(f"\n\n===== PHASE 109 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
