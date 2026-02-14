"""Phase 123: CC Generate Images sub-feature + multiple Amazon angles.
P122: CC overview panel found, but Camera/Pose/Reference at 0,0 = need to enter Generate Images first.

Goal: 1) Enter CC "Generate Images" sub-feature
      2) Select Ray and access Camera/Pose/Reference modes
      3) Map the Reference mode panel in detail
      4) Go to Amazon and grab ALL product image angles
      5) Upload reference image via CC Reference upload button
      6) Generate Ray with product reference
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
    start = time.time()
    while time.time() - start < max_wait:
        elapsed = int(time.time() - start)
        current = page.evaluate("() => document.querySelectorAll('img[src*=\"static.dzine.ai/stylar_product/p/\"]').length")
        new_count = current - before_count
        if new_count > 0:
            print(f"  [{label}] Done in {elapsed}s! {new_count} new image(s)", flush=True)
            return new_count
        if elapsed % 10 == 0:
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
    #  STEP 1: Amazon — get ALL product image angles
    # ============================================================
    print("\n=== STEP 1: Get all Amazon product image angles ===", flush=True)

    amz = ctx.new_page()
    amz.set_viewport_size({"width": 1440, "height": 900})

    try:
        amz.goto("https://www.amazon.com/dp/B0C8PSRWFX", wait_until="domcontentloaded", timeout=30000)
        amz.wait_for_timeout(5000)
        close_dialogs(amz)

        # Get all product image URLs from the image gallery
        all_images = amz.evaluate("""() => {
            var urls = new Set();

            // Method 1: Get from altImages (thumbnail strip)
            var thumbs = document.querySelectorAll('#altImages img, .imageThumbnail img');
            for (var t of thumbs) {
                var src = t.src || '';
                // Convert thumbnail URL to full-size
                // Amazon format: ...I/XXXXX._AC_US40_.jpg -> ...I/XXXXX._AC_SX679_.jpg
                var fullSize = src.replace(/\._[A-Z]{2}_[A-Z]{2}\d+_/, '._AC_SX679_');
                if (fullSize.includes('media-amazon.com/images/I/')) {
                    urls.add(fullSize);
                }
            }

            // Method 2: Get from data attributes
            var mainImg = document.querySelector('#landingImage');
            if (mainImg) {
                // Check data-a-dynamic-image for all variants
                var dynamicData = mainImg.getAttribute('data-a-dynamic-image');
                if (dynamicData) {
                    try {
                        var parsed = JSON.parse(dynamicData);
                        for (var url in parsed) {
                            urls.add(url);
                        }
                    } catch(e) {}
                }
                // Also add the current src
                if (mainImg.src) urls.add(mainImg.src);
                // And hi-res
                var hiRes = mainImg.getAttribute('data-old-hires');
                if (hiRes) urls.add(hiRes);
            }

            // Method 3: Get from colorImages JS data
            var scripts = document.querySelectorAll('script');
            for (var s of scripts) {
                var text = s.textContent || '';
                if (text.includes('colorImages')) {
                    var match = text.match(/'colorImages'\\s*:\\s*\\{\\s*'initial'\\s*:\\s*(\\[.*?\\])/s);
                    if (match) {
                        try {
                            var data = JSON.parse(match[1]);
                            for (var item of data) {
                                if (item.hiRes) urls.add(item.hiRes);
                                if (item.large) urls.add(item.large);
                            }
                        } catch(e) {}
                    }
                }
            }

            return Array.from(urls).filter(u => u.includes('media-amazon.com'));
        }""")

        print(f"  Found {len(all_images)} product image URLs:", flush=True)
        for i, url in enumerate(all_images[:10]):
            print(f"    [{i}] {url[:90]}...", flush=True)

        # Download all angles
        downloaded = []
        for i, url in enumerate(all_images[:8]):  # Max 8 angles
            try:
                ext = '.jpg' if '.jpg' in url.lower() else '.png'
                filename = f"amazon_angle_{i}{ext}"
                filepath = DOWNLOAD_DIR / filename
                urllib.request.urlretrieve(url, str(filepath))
                size = filepath.stat().st_size
                downloaded.append(str(filepath))
                print(f"    Downloaded: {filename} ({size/1024:.1f} KB)", flush=True)
            except Exception as e:
                print(f"    Failed [{i}]: {e}", flush=True)

        # Also screenshot the PDP
        ss(amz, "P123_00_amazon_pdp")

    except Exception as e:
        print(f"  Amazon error: {e}", flush=True)
        downloaded = []

    try:
        amz.close()
    except Exception:
        pass

    print(f"\n  Total angles downloaded: {len(downloaded)}", flush=True)

    # ============================================================
    #  STEP 2: Open CC Character panel → Generate Images
    # ============================================================
    print("\n=== STEP 2: CC → Generate Images sub-feature ===", flush=True)

    open_sidebar_tool(page, 306)

    # Click "Generate Images" button
    clicked = page.evaluate("""() => {
        var btns = document.querySelectorAll('.collapse-option');
        for (var b of btns) {
            var text = (b.innerText || '').trim();
            if (text.includes('Generate Images')) {
                b.click();
                return text;
            }
        }
        return false;
    }""")
    print(f"  Clicked: {clicked}", flush=True)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    # Select Ray
    ray_selected = page.evaluate("""() => {
        var list = document.querySelector('.c-character-list');
        if (list) {
            for (var item of list.querySelectorAll('.item, button')) {
                if ((item.innerText || '').trim() === 'Ray') {
                    item.click();
                    return true;
                }
            }
        }
        return false;
    }""")
    print(f"  Ray selected: {ray_selected}", flush=True)
    page.wait_for_timeout(2000)

    # Map the CC generation panel
    cc_gen = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};
        var text = (panel.innerText || '').substring(0, 1200);
        var elements = [];
        for (var el of panel.querySelectorAll('button, textarea, input, [contenteditable], [class*="upload"], [class*="pick-image"], [class*="option"], [class*="switch"]')) {
            var r = el.getBoundingClientRect();
            if (r.width < 15) continue;
            elements.push({
                tag: el.tagName,
                cls: (el.className || '').toString().substring(0, 60),
                text: (el.innerText || '').trim().substring(0, 35),
                editable: el.getAttribute('contenteditable'),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
            });
        }
        return {fullText: text, elements: elements.slice(0, 30)};
    }""")

    print(f"  CC Gen panel text:\n{cc_gen.get('fullText', '')[:600]}", flush=True)
    print(f"\n  Elements ({len(cc_gen.get('elements', []))}):", flush=True)
    for e in cc_gen.get('elements', []):
        ed = f" [editable]" if e.get('editable') else ""
        print(f"    <{e['tag']}> .{e['cls'][:45]} '{e['text'][:28]}'{ed} ({e['x']},{e['y']}) {e['w']}x{e['h']}", flush=True)

    ss(page, "P123_01_cc_gen_panel")

    # ============================================================
    #  STEP 3: Find and map Camera/Pose/Reference modes
    # ============================================================
    print("\n=== STEP 3: Camera/Pose/Reference modes ===", flush=True)

    modes = page.evaluate("""() => {
        var modes = [];
        for (var b of document.querySelectorAll('button, [class*="mode-item"]')) {
            var text = (b.innerText || '').trim();
            var r = b.getBoundingClientRect();
            if (['Camera', 'Pose', 'Reference'].includes(text) && r.width > 30) {
                modes.push({
                    text: text,
                    cls: (b.className || '').toString().substring(0, 50),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    active: (b.className || '').includes('active') || (b.className || '').includes('selected'),
                });
            }
        }
        return modes;
    }""")

    print(f"  Modes ({len(modes)}):", flush=True)
    for m in modes:
        act = " [ACTIVE]" if m['active'] else ""
        print(f"    '{m['text']}'{act} .{m['cls'][:40]} ({m['x']},{m['y']}) {m['w']}x{m['h']}", flush=True)

    # Click Reference mode
    ref_mode = None
    for m in modes:
        if m['text'] == 'Reference' and m['w'] > 0:
            ref_mode = m
            break

    if ref_mode:
        print(f"\n  Clicking Reference at ({ref_mode['x']},{ref_mode['y']})", flush=True)
        page.mouse.click(ref_mode['x'] + ref_mode['w']//2, ref_mode['y'] + ref_mode['h']//2)
        page.wait_for_timeout(2000)

        # Map what changed
        ref_panel = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {error: 'no panel'};
            var text = (panel.innerText || '').substring(0, 800);
            var uploads = [];
            for (var el of panel.querySelectorAll('[class*="pick-image"], [class*="upload"], button')) {
                var r = el.getBoundingClientRect();
                var t = (el.innerText || '').trim();
                if (r.width > 30 && (t.includes('upload') || t.includes('Upload') || t.includes('image') ||
                    (el.className || '').includes('pick-image') || (el.className || '').includes('upload'))) {
                    uploads.push({
                        cls: (el.className || '').toString().substring(0, 50),
                        text: t.substring(0, 30),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                    });
                }
            }
            return {text: text, uploads: uploads};
        }""")

        print(f"  Reference mode panel:\n{ref_panel.get('text', '')[:500]}", flush=True)
        print(f"\n  Upload buttons ({len(ref_panel.get('uploads', []))}):", flush=True)
        for u in ref_panel.get('uploads', []):
            print(f"    .{u['cls'][:40]} '{u['text'][:25]}' ({u['x']},{u['y']}) {u['w']}x{u['h']}", flush=True)

        ss(page, "P123_02_reference_mode")

        # Try uploading a product reference image
        if downloaded:
            ref_image_path = downloaded[0]
            print(f"\n  Uploading reference: {ref_image_path}", flush=True)

            # Find the CC reference upload button
            upload_btn = page.evaluate("""() => {
                for (var el of document.querySelectorAll('.pick-image, [class*="cc-pick-image"]')) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 50 && r.height > 30) {
                        return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                    }
                }
                // Broader search
                for (var el of document.querySelectorAll('button')) {
                    var text = (el.innerText || '').trim().toLowerCase();
                    if (text.includes('upload') || text.includes('pick')) {
                        var r = el.getBoundingClientRect();
                        if (r.width > 50 && r.y > 400) {
                            return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                        }
                    }
                }
                return null;
            }""")

            if upload_btn:
                print(f"  Upload btn at ({upload_btn['x']},{upload_btn['y']})", flush=True)
                try:
                    with page.expect_file_chooser(timeout=5000) as fc_info:
                        page.mouse.click(upload_btn['x'], upload_btn['y'])
                    fc = fc_info.value
                    fc.set_files(ref_image_path)
                    print("  File chooser triggered and file set!", flush=True)
                    page.wait_for_timeout(3000)
                except Exception as e:
                    print(f"  File chooser error: {e}", flush=True)
                    # Try JS upload approach
                    print("  Trying JS approach...", flush=True)
            else:
                print("  No upload button found", flush=True)

    else:
        print("  Reference mode not found in current panel", flush=True)
        # Maybe we need to scroll or the modes are elsewhere
        # Let's check the full panel content
        full_dump = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return '';
            return (panel.innerText || '').substring(0, 2000);
        }""")
        print(f"  Full panel:\n{full_dump[:800]}", flush=True)

    ss(page, "P123_03_reference_upload")

    # ============================================================
    #  STEP 4: Enter scene prompt and generate
    # ============================================================
    print("\n=== STEP 4: Generate Ray with reference ===", flush=True)

    scene = "Ray holding and examining premium wireless headphones, tech reviewer studio, warm lighting, looking at the product with interest"

    # Enter scene prompt
    page.evaluate("""(prompt) => {
        var textarea = document.querySelector('.custom-textarea[contenteditable]');
        if (textarea) {
            var mention = textarea.querySelector('.at-name');
            if (mention) {
                var textNode = document.createTextNode(' ' + prompt);
                textarea.appendChild(textNode);
            } else {
                textarea.innerText = '@Ray ' + prompt;
            }
            textarea.dispatchEvent(new Event('input', {bubbles: true}));
        }
    }""", scene)
    page.wait_for_timeout(1000)

    # Check and click generate
    before_count = page.evaluate("() => document.querySelectorAll('img[src*=\"static.dzine.ai/stylar_product/p/\"]').length")

    gen = page.evaluate("""() => {
        var btn = document.querySelector('#character2img-generate-btn, button.generative.ready');
        if (!btn) return {error: 'no button'};
        if (btn.disabled) return {error: 'disabled', text: (btn.innerText || '').trim()};
        btn.click();
        return {clicked: true, text: (btn.innerText || '').trim()};
    }""")
    print(f"  Generate: {json.dumps(gen)}", flush=True)

    if gen.get('clicked'):
        page.wait_for_timeout(2000)
        ss(page, "P123_04_cc_generating")

        new_count = wait_for_new_images(page, before_count, max_wait=90, label="CC+Ref")

        if new_count > 0:
            urls = page.evaluate("""(count) => {
                var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]');
                var urls = [];
                for (var i = Math.max(0, imgs.length - count); i < imgs.length; i++) {
                    urls.push(imgs[i].src);
                }
                return urls;
            }""", new_count)
            for i, url in enumerate(urls):
                path = DOWNLOAD_DIR / f"dzine_ray_ref_{int(time.time())}_{i}.webp"
                try:
                    urllib.request.urlretrieve(url, str(path))
                    size = path.stat().st_size
                    print(f"  Downloaded: {path.name} ({size/1024:.1f} KB)", flush=True)
                except Exception as e:
                    print(f"  Download failed: {e}", flush=True)

    ss(page, "P123_05_cc_result")

    # ============================================================
    #  STEP 5: Explore "Insert Character" sub-feature
    # ============================================================
    print("\n=== STEP 5: Insert Character ===", flush=True)

    # Go back to Character overview
    page.evaluate("""() => {
        var back = document.querySelector('.c-gen-config.show .back');
        if (back) { back.click(); return; }
        var close = document.querySelector('.c-gen-config.show .ico-close');
        if (close) close.click();
    }""")
    page.wait_for_timeout(1000)

    open_sidebar_tool(page, 306)

    # Click "Insert Character"
    clicked = page.evaluate("""() => {
        var btns = document.querySelectorAll('.collapse-option');
        for (var b of btns) {
            var text = (b.innerText || '').trim();
            if (text.includes('Insert Character')) {
                b.click();
                return text;
            }
        }
        return false;
    }""")
    print(f"  Clicked: {clicked}", flush=True)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    # Map the Insert Character panel
    ic_panel = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};
        var text = (panel.innerText || '').substring(0, 800);
        var elements = [];
        for (var el of panel.querySelectorAll('button, textarea, input, [contenteditable], [class*="upload"], [class*="pick-image"]')) {
            var r = el.getBoundingClientRect();
            if (r.width < 15) continue;
            elements.push({
                tag: el.tagName,
                cls: (el.className || '').toString().substring(0, 60),
                text: (el.innerText || '').trim().substring(0, 35),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
            });
        }
        return {text: text, elements: elements.slice(0, 20)};
    }""")

    print(f"  Insert Character panel:\n{ic_panel.get('text', '')[:400]}", flush=True)
    print(f"\n  Elements ({len(ic_panel.get('elements', []))}):", flush=True)
    for e in ic_panel.get('elements', []):
        print(f"    <{e['tag']}> .{e['cls'][:45]} '{e['text'][:28]}' ({e['x']},{e['y']}) {e['w']}x{e['h']}", flush=True)

    ss(page, "P123_06_insert_character")

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

    ss(page, "P123_07_final")
    print(f"\n\n===== PHASE 123 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
