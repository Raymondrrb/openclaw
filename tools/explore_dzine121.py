"""Phase 121: Consistent Character (Ray) generation + Img2Img pipeline test.
P120 SUCCESS: Txt2Img generated, downloaded (150KB WebP), placed on canvas.

Goal: 1) Generate a CC Ray image in a product review scene
      2) Download the Ray image
      3) Open Img2Img with the placed canvas image
      4) Run Img2Img with a style modification prompt
      5) Download and compare both images
      6) Test the Style Picker in Txt2Img
"""

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from playwright.sync_api import sync_playwright

CANVAS_URL = "https://www.dzine.ai/canvas?id=19797967"
SS_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dzine_explore"
SS_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR = Path.home() / "Downloads"


def ss(page, name):
    page.screenshot(path=str(SS_DIR / f"{name}.png"))
    print(f"  SS: {name}", flush=True)


def close_dialogs(page):
    for _ in range(8):
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


def close_all_panels(page):
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('.c-gen-config.show .ico-close')) el.click();
        for (var el of document.querySelectorAll('.panels.show .ico-close')) el.click();
        var lsp = document.querySelector('.lip-sync-config-panel.show');
        if (lsp) lsp.classList.remove('show');
    }""")
    page.wait_for_timeout(1000)


def open_sidebar_tool(page, target_y):
    close_all_panels(page)
    page.wait_for_timeout(500)
    page.mouse.click(40, 766)
    page.wait_for_timeout(1500)
    close_all_panels(page)
    page.wait_for_timeout(500)
    page.mouse.click(40, target_y)
    page.wait_for_timeout(2500)
    close_dialogs(page)


def wait_for_new_images(page, before_count, max_wait=120, label=""):
    """Wait for new images to appear in results panel."""
    start = time.time()
    while time.time() - start < max_wait:
        elapsed = int(time.time() - start)
        current = page.evaluate("() => document.querySelectorAll('img[src*=\"static.dzine.ai/stylar_product/p/\"]').length")
        new_count = current - before_count
        if new_count > 0:
            print(f"  [{label}] Done in {elapsed}s! {new_count} new image(s) (total: {current})", flush=True)
            return new_count
        if elapsed % 10 == 0:
            # Check progress
            progress = page.evaluate("""() => {
                for (var el of document.querySelectorAll('.result-panel *, .material-v2-result-content *')) {
                    var text = (el.innerText || '').trim();
                    if (text.match(/^\\d{1,3}%$/)) return text;
                }
                return null;
            }""")
            p = f" progress={progress}" if progress else ""
            print(f"  [{label}] {elapsed}s...{p}", flush=True)
        page.wait_for_timeout(3000)
    print(f"  [{label}] TIMEOUT after {max_wait}s", flush=True)
    return 0


def get_latest_image_url(page, count=1):
    """Get the URL(s) of the most recent result image(s)."""
    return page.evaluate("""(count) => {
        var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]');
        var urls = [];
        for (var i = Math.max(0, imgs.length - count); i < imgs.length; i++) {
            urls.push(imgs[i].src);
        }
        return urls;
    }""", count)


def download_image(url, name):
    """Download image and return path + size."""
    path = DOWNLOAD_DIR / name
    try:
        urllib.request.urlretrieve(url, str(path))
        size = path.stat().st_size
        fmt = "unknown"
        with open(path, 'rb') as f:
            h = f.read(12)
        if h[:4] == b'RIFF' and h[8:12] == b'WEBP':
            fmt = "WebP"
        elif h[:8] == b'\x89PNG\r\n\x1a\n':
            fmt = "PNG"
        elif h[:2] == b'\xff\xd8':
            fmt = "JPEG"
        print(f"  Downloaded: {path.name} ({size/1024:.1f} KB, {fmt})", flush=True)
        return str(path), size
    except Exception as e:
        print(f"  Download failed: {e}", flush=True)
        return None, 0


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

    before_count = page.evaluate("() => document.querySelectorAll('img[src*=\"static.dzine.ai/stylar_product/p/\"]').length")
    print(f"  Starting images: {before_count}", flush=True)

    # ============================================================
    #  STEP 1: Open Character panel and select Ray
    # ============================================================
    print("\n=== STEP 1: Open Character panel + select Ray ===", flush=True)

    open_sidebar_tool(page, 306)

    # Select Ray using hidden-list JS click (Phase 116 pattern)
    ray_selected = page.evaluate("""() => {
        var list = document.querySelector('.c-character-list');
        if (list) {
            for (var item of list.querySelectorAll('.item, button')) {
                if ((item.innerText || '').trim() === 'Ray') {
                    item.click();
                    return 'selected via hidden list';
                }
            }
        }
        // Fallback: search all buttons
        for (var el of document.querySelectorAll('button')) {
            if ((el.innerText || '').trim() === 'Ray') {
                el.click();
                return 'selected via button fallback';
            }
        }
        return 'Ray not found';
    }""")
    print(f"  Ray: {ray_selected}", flush=True)
    page.wait_for_timeout(2000)

    # Check if CC gen panel appeared
    cc_panel = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};
        var textarea = panel.querySelector('.custom-textarea[contenteditable]');
        var genBtn = panel.querySelector('#character2img-generate-btn, button.generative');
        return {
            hasPrompt: !!textarea,
            promptText: textarea ? (textarea.innerText || '').trim().substring(0, 100) : '',
            hasGenBtn: !!genBtn,
            genBtnText: genBtn ? (genBtn.innerText || '').trim() : '',
            genBtnDisabled: genBtn ? genBtn.disabled : null,
        };
    }""")
    print(f"  CC panel: {json.dumps(cc_panel)}", flush=True)

    ss(page, "P121_01_ray_selected")

    # ============================================================
    #  STEP 2: Enter scene prompt and generate
    # ============================================================
    print("\n=== STEP 2: Enter CC scene prompt ===", flush=True)

    scene_prompt = "Ray sitting at a modern desk reviewing wireless headphones, studio podcast setup in background, warm lighting, professional tech reviewer environment"

    # Type into contenteditable
    prompt_set = page.evaluate("""(prompt) => {
        var textarea = document.querySelector('.custom-textarea[contenteditable]');
        if (!textarea) return {error: 'no contenteditable found'};
        textarea.focus();
        // Clear existing content except @Ray mention
        var mention = textarea.querySelector('.at-name');
        if (mention) {
            // Keep the mention, add scene after it
            var textNode = document.createTextNode(' ' + prompt);
            textarea.appendChild(textNode);
        } else {
            textarea.innerText = '@Ray ' + prompt;
        }
        textarea.dispatchEvent(new Event('input', {bubbles: true}));
        return {ok: true, text: textarea.innerText.substring(0, 100)};
    }""", scene_prompt)
    print(f"  Prompt: {json.dumps(prompt_set)}", flush=True)
    page.wait_for_timeout(1000)

    # Click Generate
    gen_result = page.evaluate("""() => {
        var btn = document.querySelector('#character2img-generate-btn, button.generative.ready');
        if (!btn) return {error: 'no generate button'};
        if (btn.disabled) return {error: 'button disabled', text: (btn.innerText || '').trim()};
        btn.click();
        return {clicked: true, text: (btn.innerText || '').trim()};
    }""")
    print(f"  Generate: {json.dumps(gen_result)}", flush=True)

    if gen_result.get('error'):
        # Try clicking by coordinates
        print("  Trying coordinate click...", flush=True)
        gen_pos = page.evaluate("""() => {
            for (var b of document.querySelectorAll('button.generative, button')) {
                if ((b.innerText || '').includes('Generate') && !b.disabled) {
                    var r = b.getBoundingClientRect();
                    return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                }
            }
            return null;
        }""")
        if gen_pos:
            page.mouse.click(gen_pos['x'], gen_pos['y'])
            print(f"  Clicked at ({gen_pos['x']},{gen_pos['y']})", flush=True)

    page.wait_for_timeout(2000)
    ss(page, "P121_02_cc_generating")

    # Wait for generation
    cc_before = page.evaluate("() => document.querySelectorAll('img[src*=\"static.dzine.ai/stylar_product/p/\"]').length")
    new_cc = wait_for_new_images(page, cc_before, max_wait=90, label="CC")

    ss(page, "P121_03_cc_done")

    # Download CC result
    if new_cc > 0:
        urls = get_latest_image_url(page, new_cc)
        for i, url in enumerate(urls):
            download_image(url, f"dzine_ray_cc_{int(time.time())}_{i}.webp")

    # ============================================================
    #  STEP 3: Place CC result on canvas
    # ============================================================
    print("\n=== STEP 3: Place result on canvas ===", flush=True)

    # Click the latest result to open preview
    page.evaluate("""() => {
        var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]');
        if (imgs.length > 0) {
            var last = imgs[imgs.length - 1];
            last.click();
        }
    }""")
    page.wait_for_timeout(2000)

    # Click place on canvas
    placed = page.evaluate("""() => {
        var btn = document.querySelector('.handle-item.place-on-canvas');
        if (btn) { btn.click(); return true; }
        return false;
    }""")
    print(f"  Placed on canvas: {placed}", flush=True)
    page.wait_for_timeout(2000)

    # ============================================================
    #  STEP 4: Open Img2Img with canvas content
    # ============================================================
    print("\n=== STEP 4: Img2Img with canvas ===", flush=True)

    open_sidebar_tool(page, 252)

    # Click "Describe Canvas" to auto-fill prompt
    autoprompt = page.evaluate("""() => {
        var btn = document.querySelector('button.autoprompt');
        if (!btn) return {error: 'no autoprompt button'};
        var r = btn.getBoundingClientRect();
        btn.click();
        return {clicked: true, x: Math.round(r.x), y: Math.round(r.y)};
    }""")
    print(f"  Describe Canvas: {json.dumps(autoprompt)}", flush=True)
    page.wait_for_timeout(5000)

    # Read auto-generated prompt
    auto_prompt = page.evaluate("""() => {
        var ta = document.querySelector('.img2img-config-panel textarea, TEXTAREA.len-1800');
        if (!ta) return {error: 'no textarea'};
        return {value: ta.value.substring(0, 200), length: ta.value.length};
    }""")
    print(f"  Auto prompt: {json.dumps(auto_prompt)}", flush=True)

    # Modify prompt to add style direction
    style_addition = " Cinematic color grading, dramatic side lighting, premium product review setting."
    page.evaluate("""(addition) => {
        var ta = document.querySelector('.img2img-config-panel textarea, TEXTAREA.len-1800');
        if (ta) {
            ta.value = ta.value + addition;
            ta.dispatchEvent(new Event('input', {bubbles: true}));
        }
    }""", style_addition)
    page.wait_for_timeout(500)

    # Set Normal mode for better quality
    page.evaluate("""() => {
        for (var b of document.querySelectorAll('button')) {
            if ((b.innerText || '').trim() === 'Normal') {
                b.click();
                return;
            }
        }
    }""")
    page.wait_for_timeout(500)

    ss(page, "P121_04_img2img_setup")

    # Generate Img2Img
    i2i_before = page.evaluate("() => document.querySelectorAll('img[src*=\"static.dzine.ai/stylar_product/p/\"]').length")

    gen_i2i = page.evaluate("""() => {
        var btn = document.querySelector('button.generative.ready');
        if (!btn) return {error: 'no button'};
        if (btn.disabled) return {error: 'disabled'};
        btn.click();
        return {clicked: true, text: (btn.innerText || '').trim()};
    }""")
    print(f"  Img2Img generate: {json.dumps(gen_i2i)}", flush=True)

    page.wait_for_timeout(2000)
    new_i2i = wait_for_new_images(page, i2i_before, max_wait=90, label="Img2Img")

    ss(page, "P121_05_img2img_done")

    if new_i2i > 0:
        urls = get_latest_image_url(page, new_i2i)
        for i, url in enumerate(urls):
            download_image(url, f"dzine_img2img_{int(time.time())}_{i}.webp")

    # ============================================================
    #  STEP 5: Style Picker exploration
    # ============================================================
    print("\n=== STEP 5: Style Picker ===", flush=True)

    open_sidebar_tool(page, 197)  # Txt2Img

    # Click the style button
    page.evaluate("""() => {
        var btn = document.querySelector('.c-style button.style, button.style');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(2000)

    # Map available styles
    styles = page.evaluate("""() => {
        var panel = document.querySelector('.style-list-panel');
        if (!panel) return {error: 'no style panel'};

        var r = panel.getBoundingClientRect();
        var categories = [];
        for (var el of panel.querySelectorAll('[class*="category"], [class*="tab"]')) {
            var text = (el.innerText || '').trim();
            if (text.length > 0 && text.length < 30) {
                categories.push(text);
            }
        }

        // Get visible style items
        var items = [];
        for (var el of panel.querySelectorAll('[class*="style-item"]')) {
            var name = (el.innerText || '').trim();
            var active = (el.className || '').includes('active') || (el.className || '').includes('selected');
            if (name.length > 0 && name.length < 40) {
                items.push({name: name, active: active});
            }
        }

        return {
            panelSize: {w: Math.round(r.width), h: Math.round(r.height)},
            categories: categories.slice(0, 15),
            stylesCount: items.length,
            styles: items.slice(0, 30),
        };
    }""")

    print(f"  Style panel: {json.dumps(styles.get('panelSize'))}", flush=True)
    print(f"  Categories: {styles.get('categories', [])}", flush=True)
    print(f"  Styles visible: {styles.get('stylesCount', 0)}", flush=True)
    print(f"  First styles:", flush=True)
    for s in styles.get('styles', [])[:15]:
        act = " [ACTIVE]" if s.get('active') else ""
        print(f"    {s['name']}{act}", flush=True)

    ss(page, "P121_06_style_picker")

    # Close style picker
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # Credits
    credits = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.match(/^[\\d,\\.]+$/) && parseInt(text.replace(/[,\\.]/g, '')) > 100 && r.y < 30 && r.x > 400) {
                return text;
            }
        }
        return null;
    }""")
    print(f"\n  Credits: {credits}", flush=True)

    ss(page, "P121_07_final")
    print(f"\n\n===== PHASE 121 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
