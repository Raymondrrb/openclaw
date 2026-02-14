"""Phase 134: Test workflow universality + Expand result placement + Enhance.

P133 confirmed: headphones → BG Remove → Expand → Export works perfectly.
Now test with a DIFFERENT product (keyboard/speaker) to confirm universal.
Also: place expanded result on canvas and try Enhance with layer selected.
Also: test the "Variation" action on expand results.
"""

import base64
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from playwright.sync_api import sync_playwright

SS_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dzine_explore"
SS_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR = Path.home() / "Downloads"


def ss(page, name):
    page.screenshot(path=str(SS_DIR / f"{name}.png"))
    print(f"  SS: {name}", flush=True)


def close_dialogs(page):
    for _ in range(8):
        found = False
        try:
            fit_btn = page.locator('button:has-text("Fit to Content and Continue")')
            if fit_btn.count() > 0 and fit_btn.first.is_visible(timeout=500):
                fit_btn.first.click()
                page.wait_for_timeout(1000)
                print("  [dialog] Fit to Content", flush=True)
                found = True
                continue
        except Exception:
            pass
        try:
            cb = page.locator('text=Do not show again')
            if cb.count() > 0 and cb.first.is_visible(timeout=300):
                cb.first.click()
                page.wait_for_timeout(300)
        except Exception:
            pass
        for text in ["Not now", "Close", "Never show again", "Got it", "Skip",
                      "Later", "Continue", "OK", "Cancel"]:
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


def close_all_panels(page):
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('.c-gen-config.show .ico-close')) el.click();
        for (var el of document.querySelectorAll('.panels.show .ico-close')) el.click();
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


def create_project_from_image(ctx, image_path):
    """Create a new Dzine project from an image file. Returns (page, canvas_url)."""
    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    page.goto("https://www.dzine.ai/home", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(4000)
    close_dialogs(page)

    try:
        with page.expect_file_chooser(timeout=8000) as fc_info:
            page.evaluate("""() => {
                for (var el of document.querySelectorAll('.project-item')) {
                    var text = (el.innerText || '').trim().toLowerCase();
                    if (text.includes('start from an image')) { el.click(); return; }
                }
            }""")
        fc = fc_info.value
        fc.set_files(image_path)
        page.wait_for_timeout(8000)
        close_dialogs(page)
    except Exception as e:
        print(f"  Start from image failed: {e}", flush=True)
        page.close()
        return None, None

    if "/canvas" not in page.url:
        print(f"  Not on canvas: {page.url}", flush=True)
        page.close()
        return None, None

    wait_for_canvas(page)
    close_dialogs(page)
    return page, page.url


def bg_remove(page):
    """Click BG Remove and wait for completion."""
    page.mouse.click(700, 400)
    page.wait_for_timeout(500)

    page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'BG Remove') {
                var r = el.getBoundingClientRect();
                if (r.y > 50 && r.y < 120 && r.width > 0) { el.click(); return; }
            }
        }
    }""")

    start = time.time()
    while time.time() - start < 30:
        status = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                if ((el.innerText || '').trim() === 'Removing background...') return 'removing';
            }
            return 'done';
        }""")
        if status == 'done' and time.time() - start > 2:
            break
        page.wait_for_timeout(1000)
    print(f"  BG Remove: done in {int(time.time()-start)}s", flush=True)
    page.wait_for_timeout(2000)


def generative_expand(page, prompt="Clean white studio backdrop with soft professional lighting, subtle shadow underneath product", aspect="16:9"):
    """Run Generative Expand. Returns list of downloaded file paths."""
    # Open Image Editor → Expand
    open_sidebar_tool(page, 698)
    page.wait_for_timeout(1500)

    page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'Expand') {
                var r = el.getBoundingClientRect();
                if (r.width > 0 && r.y > 70 && r.y < 700) { el.click(); return; }
            }
        }
    }""")
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Set aspect ratio
    page.evaluate(f"""() => {{
        for (var b of document.querySelectorAll('button')) {{
            if ((b.innerText || '').trim() === '{aspect}') {{ b.click(); return; }}
        }}
    }}""")
    page.wait_for_timeout(500)

    # Set prompt
    page.evaluate(f"""(prompt) => {{
        for (var ta of document.querySelectorAll('textarea')) {{
            var r = ta.getBoundingClientRect();
            if (r.width > 100) {{
                ta.value = prompt;
                ta.dispatchEvent(new Event('input', {{bubbles: true}}));
                return;
            }}
        }}
    }}""", prompt)
    page.wait_for_timeout(500)

    # Count images before
    before_count = page.evaluate("""() => {
        var count = 0;
        for (var img of document.querySelectorAll('img')) {
            if ((img.src||'').includes('static.dzine.ai/stylar_product/')) count++;
        }
        return count;
    }""")

    # Click Generate 8 (the visible one in panel, x < 350)
    clicked = page.evaluate("""() => {
        for (var b of document.querySelectorAll('button')) {
            var text = (b.innerText || '').trim();
            var r = b.getBoundingClientRect();
            if (text.includes('Generate') && r.width > 0 && r.x < 350 && r.y > 300 && !b.disabled) {
                b.click();
                return text;
            }
        }
        return null;
    }""")
    print(f"  Expand Generate: {clicked}", flush=True)

    if not clicked:
        return []

    page.wait_for_timeout(2000)
    close_dialogs(page)
    page.wait_for_timeout(1000)
    close_dialogs(page)

    # Wait for results
    start = time.time()
    while time.time() - start < 120:
        elapsed = int(time.time() - start)
        close_dialogs(page)

        current = page.evaluate("""() => {
            var count = 0;
            for (var img of document.querySelectorAll('img')) {
                if ((img.src||'').includes('static.dzine.ai/stylar_product/')) count++;
            }
            return count;
        }""")
        if current > before_count:
            new_count = current - before_count
            print(f"  Expand: done in {elapsed}s! {new_count} new image(s)", flush=True)

            # Download
            urls = page.evaluate(f"""() => {{
                var urls = [];
                var count = 0;
                for (var img of document.querySelectorAll('img')) {{
                    if ((img.src||'').includes('static.dzine.ai/stylar_product/')) {{
                        count++;
                        if (count > {before_count}) urls.push(img.src);
                    }}
                }}
                return urls;
            }}""")
            ts = int(time.time())
            files = []
            for i, url in enumerate(urls[:4]):
                path = DOWNLOAD_DIR / f"dzine_expand_{ts}_{i}.webp"
                try:
                    urllib.request.urlretrieve(url, str(path))
                    files.append(str(path))
                    print(f"  Downloaded: {path.name} ({path.stat().st_size/1024:.1f} KB)", flush=True)
                except Exception as e:
                    print(f"  Download error: {e}", flush=True)
            return files

        if elapsed % 10 == 0:
            progress = page.evaluate("""() => {
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text.match(/^\\d{1,3}%$/)) return text;
                }
                return null;
            }""")
            p = f" {progress}" if progress else ""
            print(f"  Expand: {elapsed}s...{p}", flush=True)
        page.wait_for_timeout(3000)

    print(f"  Expand: TIMEOUT", flush=True)
    return []


def export_canvas(page, format="PNG", scale="2x"):
    """Export the canvas. Returns path to exported file."""
    close_all_panels(page)
    page.wait_for_timeout(500)

    # Click Export button (top right)
    page.evaluate("""() => {
        for (var b of document.querySelectorAll('button')) {
            if ((b.innerText || '').trim() === 'Export') {
                var r = b.getBoundingClientRect();
                if (r.y < 40) { b.click(); return; }
            }
        }
    }""")
    page.wait_for_timeout(2000)

    # Select format
    page.evaluate(f"""() => {{
        for (var b of document.querySelectorAll('button')) {{
            if ((b.innerText || '').trim() === '{format}') {{ b.click(); return; }}
        }}
    }}""")
    page.wait_for_timeout(300)

    # Select scale
    page.evaluate(f"""() => {{
        for (var b of document.querySelectorAll('button')) {{
            if ((b.innerText || '').trim() === '{scale}') {{ b.click(); return; }}
        }}
    }}""")
    page.wait_for_timeout(300)

    # Uncheck watermark
    page.evaluate("""() => {
        var cb = document.querySelector('input[type="checkbox"]');
        if (cb && cb.checked) cb.click();
    }""")
    page.wait_for_timeout(300)

    # Click Export
    export_path = None
    try:
        with page.expect_download(timeout=30000) as dl_info:
            page.evaluate("""() => {
                for (var b of document.querySelectorAll('button')) {
                    if ((b.innerText || '').trim().includes('Export canvas')) { b.click(); return; }
                }
            }""")
        dl = dl_info.value
        ext = format.lower()
        export_path = str(DOWNLOAD_DIR / f"dzine_export_{int(time.time())}.{ext}")
        dl.save_as(export_path)
        print(f"  Exported: {os.path.basename(export_path)} ({os.path.getsize(export_path)/1024:.1f} KB)", flush=True)
    except Exception as e:
        print(f"  Export error: {e}", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    return export_path


def main():
    print("=" * 60, flush=True)
    print("PHASE 134: Universal workflow test + Enhance fix", flush=True)
    print("=" * 60, flush=True)

    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:18800", timeout=15000)
    ctx = browser.contexts[0]

    # Close all dzine tabs
    for p in ctx.pages:
        if "dzine.ai" in (p.url or ""):
            try:
                p.close()
            except Exception:
                pass

    # ============================================================
    #  TEST 1: Download a DIFFERENT product from Amazon
    # ============================================================
    print("\n=== TEST 1: Download different product from Amazon ===", flush=True)

    amz_page = ctx.new_page()
    amz_page.set_viewport_size({"width": 1440, "height": 900})

    # JBL Charge 5 Bluetooth Speaker — very different form factor from headphones
    product_ref = None
    try:
        amz_page.goto("https://www.amazon.com/dp/B08WKRP1HF",
                       wait_until="domcontentloaded", timeout=30000)
        amz_page.wait_for_timeout(4000)
        close_dialogs(amz_page)

        img_url = amz_page.evaluate("""() => {
            var landing = document.querySelector('#landingImage');
            if (!landing) return null;
            var hi = landing.getAttribute('data-old-hires');
            if (hi) return hi;
            var dyn = landing.getAttribute('data-a-dynamic-image');
            if (dyn) {
                try {
                    var keys = Object.keys(JSON.parse(dyn));
                    for (var k of keys) { if (k.includes('SL1500')) return k; }
                    return keys[keys.length - 1];
                } catch(e) {}
            }
            return landing.src;
        }""")

        if img_url:
            fname = f"amazon_speaker_{int(time.time())}.jpg"
            fpath = DOWNLOAD_DIR / fname
            req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            with open(fpath, 'wb') as f:
                f.write(data)
            product_ref = str(fpath)
            print(f"  Downloaded: {fname} ({len(data)/1024:.1f} KB)", flush=True)
        else:
            print("  No product image URL found", flush=True)

        ss(amz_page, "P134_01_amazon_speaker")
    except Exception as e:
        print(f"  Amazon error: {e}", flush=True)
    finally:
        amz_page.close()

    if not product_ref:
        # Fallback to any existing image
        for p in sorted(DOWNLOAD_DIR.glob("amazon_*.jpg"), reverse=True):
            if p.stat().st_size > 10000:
                product_ref = str(p)
                break

    if not product_ref:
        print("  ERROR: No product image!", flush=True)
        sys.exit(1)

    print(f"  Using: {product_ref} ({os.path.getsize(product_ref)/1024:.1f} KB)", flush=True)

    # ============================================================
    #  TEST 2: Full workflow on speaker
    # ============================================================
    print("\n=== TEST 2: Full workflow (speaker) ===", flush=True)

    page, canvas_url = create_project_from_image(ctx, product_ref)
    if not page:
        print("  FAILED to create project!", flush=True)
        sys.exit(1)

    print(f"  Canvas: {canvas_url}", flush=True)
    ss(page, "P134_02_speaker_canvas")

    # BG Remove
    print("\n  BG Remove...", flush=True)
    bg_remove(page)
    ss(page, "P134_03_speaker_bg_removed")

    # Expand with different prompt to test variety
    print("\n  Generative Expand...", flush=True)
    expand_files = generative_expand(
        page,
        prompt="Sleek product photography on gradient dark studio backdrop with dramatic side lighting and subtle reflection underneath",
        aspect="16:9"
    )
    ss(page, "P134_04_speaker_expanded")

    # Export
    print("\n  Export...", flush=True)
    exported = export_canvas(page, "PNG", "2x")

    # ============================================================
    #  TEST 3: Place expanded result on canvas + Enhance
    # ============================================================
    print("\n=== TEST 3: Place result on canvas + Enhance ===", flush=True)

    if expand_files:
        # Click the first result to preview it
        page.evaluate("""() => {
            var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/"]');
            if (imgs.length > 0) imgs[imgs.length - 1].click();
        }""")
        page.wait_for_timeout(2000)

        # Look for "Place on Canvas" or similar button in the result preview
        place_result = page.evaluate("""() => {
            // In the result preview overlay, find the place-on-canvas button
            var preview = document.querySelector('#result-preview');
            if (!preview) return {error: 'no preview'};

            var buttons = [];
            for (var b of preview.querySelectorAll('button, [role="button"]')) {
                var text = (b.innerText || '').trim();
                var title = b.getAttribute('title') || '';
                var r = b.getBoundingClientRect();
                if (r.width > 0) {
                    buttons.push({text: text.substring(0,30), title: title, x: Math.round(r.x+r.width/2), y: Math.round(r.y+r.height/2)});
                }
            }
            return {buttons: buttons};
        }""")
        print(f"  Preview buttons: {json.dumps(place_result)}", flush=True)

        # Click "Place on Canvas" (the icon button)
        page.evaluate("""() => {
            var preview = document.querySelector('#result-preview');
            if (!preview) return;
            for (var b of preview.querySelectorAll('button')) {
                var title = (b.getAttribute('title') || '').toLowerCase();
                var text = (b.innerText || '').toLowerCase();
                if (title.includes('place') || title.includes('canvas') ||
                    text.includes('place') || text.includes('canvas')) {
                    b.click();
                    return 'placed';
                }
            }
            // Try the 3rd button (place icon is usually 3rd)
            var btns = preview.querySelectorAll('button');
            if (btns.length >= 3) { btns[2].click(); return 'clicked_3rd'; }
        }""")
        page.wait_for_timeout(3000)
        close_dialogs(page)

        ss(page, "P134_05_result_placed")

        # Now try Enhance on the placed result
        print("\n  Enhance & Upscale on placed result...", flush=True)

        # Click on canvas to select the placed layer
        page.mouse.click(700, 400)
        page.wait_for_timeout(1000)

        # Open Enhance
        open_sidebar_tool(page, 628)
        page.wait_for_timeout(2000)

        # Check for layer selection warning
        warning = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text === 'Please select one layer on canvas') return true;
            }
            return false;
        }""")
        print(f"  Layer warning: {warning}", flush=True)

        if warning:
            # Try clicking on the Layers tab and selecting a specific layer
            close_all_panels(page)
            page.wait_for_timeout(300)

            # Switch to Layers tab
            page.evaluate("""() => {
                for (var el of document.querySelectorAll('[class*="header-item"]')) {
                    if ((el.innerText || '').trim() === 'Layers') { el.click(); return; }
                }
            }""")
            page.wait_for_timeout(500)

            # Click the first layer in the list
            layer_click = page.evaluate("""() => {
                var items = document.querySelectorAll('.layer-item');
                if (items.length > 0) {
                    items[0].click();
                    return {clicked: true, name: (items[0].innerText || '').trim().substring(0, 30)};
                }
                return {error: 'no layers'};
            }""")
            print(f"  Layer click: {json.dumps(layer_click)}", flush=True)
            page.wait_for_timeout(500)

            # Reopen Enhance
            open_sidebar_tool(page, 628)
            page.wait_for_timeout(2000)

            # Check again
            warning2 = page.evaluate("""() => {
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text === 'Please select one layer on canvas') return true;
                }
                return false;
            }""")
            print(f"  Layer warning after fix: {warning2}", flush=True)

        # Configure Enhance
        for config in ['Precision Mode', '2x', 'PNG']:
            page.evaluate(f"""() => {{
                for (var b of document.querySelectorAll('button, [class*="option"]')) {{
                    if ((b.innerText || '').trim() === '{config}') {{ b.click(); return; }}
                }}
            }}""")
            page.wait_for_timeout(200)

        # Click Upscale
        upscale = page.evaluate("""() => {
            for (var b of document.querySelectorAll('button')) {
                var text = (b.innerText || '').trim();
                if (text === 'Upscale' && !b.disabled) {
                    b.click();
                    return {clicked: true};
                }
            }
            return {error: 'disabled or not found'};
        }""")
        print(f"  Upscale: {json.dumps(upscale)}", flush=True)

        if upscale.get('clicked'):
            page.wait_for_timeout(2000)
            close_dialogs(page)

            # Wait for result
            start = time.time()
            while time.time() - start < 90:
                elapsed = int(time.time() - start)
                close_dialogs(page)

                # Check for enhance result (may show in Results panel)
                enhance_result = page.evaluate("""() => {
                    for (var el of document.querySelectorAll('*')) {
                        var text = (el.innerText || '').trim();
                        if (text.includes('Enhance') && text.includes('Complete')) return text;
                    }
                    // Also check for download prompt
                    for (var el of document.querySelectorAll('a[download], button:has-text("Download")')) {
                        return 'download_available';
                    }
                    return null;
                }""")
                if enhance_result:
                    print(f"  Enhance done: {enhance_result} ({elapsed}s)", flush=True)
                    break
                if elapsed % 10 == 0:
                    print(f"  Enhance: {elapsed}s...", flush=True)
                page.wait_for_timeout(3000)

            ss(page, "P134_06_enhanced")

    # ============================================================
    #  TEST 4: Variation on expand results
    # ============================================================
    print("\n=== TEST 4: Variation action ===", flush=True)

    # Check if there are Variation buttons in the Results panel
    variation_info = page.evaluate("""() => {
        var btns = [];
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'Variation') {
                var r = el.getBoundingClientRect();
                if (r.width > 0) {
                    btns.push({x: Math.round(r.x+r.width/2), y: Math.round(r.y+r.height/2)});
                }
            }
        }
        // Also find the "1 2 3 4" number buttons next to Variation
        var nums = [];
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === '1' || text === '2' || text === '3' || text === '4') {
                var r = el.getBoundingClientRect();
                if (r.width > 0 && r.width < 40 && r.y > 600) {
                    nums.push({text: text, x: Math.round(r.x+r.width/2), y: Math.round(r.y+r.height/2)});
                }
            }
        }
        return {variation: btns, nums: nums.slice(0, 8)};
    }""")
    print(f"  Variation: {json.dumps(variation_info)}", flush=True)

    # ============================================================
    #  SUMMARY
    # ============================================================
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

    print(f"\n{'='*60}", flush=True)
    print(f"PHASE 134 SUMMARY", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"  Credits: {credits}", flush=True)
    print(f"  Product: {product_ref}", flush=True)
    print(f"  Expand files: {len(expand_files)}", flush=True)
    print(f"  Export: {exported}", flush=True)
    print(f"\n  WORKFLOW UNIVERSALITY:", flush=True)
    print(f"  - Works with headphones (P133): YES", flush=True)
    print(f"  - Works with speaker (P134): {'YES' if expand_files else 'NEEDS VERIFICATION'}", flush=True)

    ss(page, "P134_07_final")
    print(f"\n===== PHASE 134 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
