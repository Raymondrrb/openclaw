"""Phase 135: Codify product-faithful workflow + fix Enhance layer selection.

P128-P134 confirmed: Upload → BG Remove → Generative Expand → Export
is the ONLY workflow that preserves real product appearance.

This phase:
1. Test Enhance fix: try Ctrl+A, double-click canvas, and keyboard layer selection
2. Test downloading multiple Amazon product angles
3. Run full product-faithful workflow with proper Amazon image
4. If Enhance works: test the full chain (Upload → BG Remove → Expand → Enhance → Export)
"""

import json
import os
import re
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
    duration = int(time.time() - start)
    print(f"  BG Remove: done in {duration}s", flush=True)
    page.wait_for_timeout(2000)
    close_dialogs(page)
    return duration


def generative_expand(page, prompt="Clean white studio backdrop with soft professional lighting, subtle shadow underneath product", aspect="16:9"):
    """Run Generative Expand. Returns list of downloaded file paths."""
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

    # Click Generate 8
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

    page.evaluate("""() => {
        for (var b of document.querySelectorAll('button')) {
            if ((b.innerText || '').trim() === 'Export') {
                var r = b.getBoundingClientRect();
                if (r.y < 40) { b.click(); return; }
            }
        }
    }""")
    page.wait_for_timeout(2000)

    page.evaluate(f"""() => {{
        for (var b of document.querySelectorAll('button')) {{
            if ((b.innerText || '').trim() === '{format}') {{ b.click(); return; }}
        }}
    }}""")
    page.wait_for_timeout(300)

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


def download_amazon_product_images(ctx, asin):
    """Download product image from Amazon using the OpenClaw browser.
    Returns list of downloaded file paths."""
    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})
    files = []

    try:
        url = f"https://www.amazon.com/dp/{asin}"
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)
        close_dialogs(page)

        # Extract main product image
        img_url = page.evaluate("""() => {
            var landing = document.querySelector('#landingImage');
            if (!landing) return null;
            // Try data-old-hires first (highest res)
            var hi = landing.getAttribute('data-old-hires');
            if (hi) return hi;
            // Try data-a-dynamic-image (JSON with multiple sizes)
            var dyn = landing.getAttribute('data-a-dynamic-image');
            if (dyn) {
                try {
                    var keys = Object.keys(JSON.parse(dyn));
                    // Prefer SL1500
                    for (var k of keys) { if (k.includes('SL1500')) return k; }
                    return keys[keys.length - 1];
                } catch(e) {}
            }
            return landing.src;
        }""")

        if img_url:
            fname = f"amazon_ref_{asin}_{int(time.time())}.jpg"
            fpath = DOWNLOAD_DIR / fname
            req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            with open(fpath, 'wb') as f:
                f.write(data)
            files.append(str(fpath))
            print(f"  Main image: {fname} ({len(data)/1024:.1f} KB)", flush=True)

        # Try to get additional product angles by clicking thumbnail images
        alt_count = page.evaluate("""() => {
            var thumbs = document.querySelectorAll('#altImages .a-button-thumbnail img, .imageThumbnail img');
            return thumbs.length;
        }""")
        print(f"  Alt thumbnails found: {alt_count}", flush=True)

        # Click up to 3 additional angles (skip first = main image)
        for idx in range(1, min(alt_count, 4)):
            page.evaluate(f"""() => {{
                var thumbs = document.querySelectorAll('#altImages .a-button-thumbnail img, .imageThumbnail img');
                if (thumbs.length > {idx}) thumbs[{idx}].click();
            }}""")
            page.wait_for_timeout(1500)

            alt_url = page.evaluate("""() => {
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

            if alt_url and alt_url != img_url:
                fname = f"amazon_ref_{asin}_alt{idx}_{int(time.time())}.jpg"
                fpath = DOWNLOAD_DIR / fname
                try:
                    req = urllib.request.Request(alt_url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        data = resp.read()
                    with open(fpath, 'wb') as f:
                        f.write(data)
                    files.append(str(fpath))
                    print(f"  Alt angle {idx}: {fname} ({len(data)/1024:.1f} KB)", flush=True)
                except Exception as e:
                    print(f"  Alt download error: {e}", flush=True)

        ss(page, "P135_01_amazon")
    except Exception as e:
        print(f"  Amazon error: {e}", flush=True)
    finally:
        page.close()

    return files


def try_enhance(page):
    """Try multiple approaches to fix Enhance & Upscale layer selection.
    Returns True if Enhance was successfully initiated."""

    print("\n  --- Enhance Approach 1: Ctrl+A to select all ---", flush=True)
    page.keyboard.press("Meta+a")
    page.wait_for_timeout(1000)

    # Check if something is selected (selection handles appear)
    has_selection = page.evaluate("""() => {
        // Look for selection handles (transform handles on canvas)
        var handles = document.querySelectorAll('.transform-handle, [class*="selection"], [class*="handle"]');
        return handles.length > 0;
    }""")
    print(f"  Selection after Ctrl+A: {has_selection}", flush=True)

    # Open Enhance
    open_sidebar_tool(page, 628)
    page.wait_for_timeout(2000)

    warning = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Please select one layer on canvas') return true;
        }
        return false;
    }""")
    print(f"  Warning after Ctrl+A: {warning}", flush=True)

    if not warning:
        return True

    # Approach 2: Click directly on product on canvas
    print("\n  --- Enhance Approach 2: Click product on canvas ---", flush=True)
    close_all_panels(page)
    page.wait_for_timeout(500)

    # Click center of canvas where the product should be
    page.mouse.click(700, 400)
    page.wait_for_timeout(500)
    # Double-click to enter selection
    page.mouse.dblclick(700, 400)
    page.wait_for_timeout(1000)

    open_sidebar_tool(page, 628)
    page.wait_for_timeout(2000)

    warning2 = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Please select one layer on canvas') return true;
        }
        return false;
    }""")
    print(f"  Warning after double-click: {warning2}", flush=True)

    if not warning2:
        return True

    # Approach 3: Use Layers panel to click specific layer with JS
    print("\n  --- Enhance Approach 3: Layers panel + JS selection ---", flush=True)
    close_all_panels(page)
    page.wait_for_timeout(500)

    # Switch to Layers tab
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').trim() === 'Layers') { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(500)

    # Get layer info
    layers_info = page.evaluate("""() => {
        var items = document.querySelectorAll('.layer-item, [class*="layer-item"]');
        var result = [];
        for (var item of items) {
            var r = item.getBoundingClientRect();
            result.push({
                text: (item.innerText || '').trim().substring(0, 40),
                classes: (item.className || '').toString().substring(0, 100),
                x: Math.round(r.x + r.width/2),
                y: Math.round(r.y + r.height/2),
                w: Math.round(r.width),
                h: Math.round(r.height)
            });
        }
        return result;
    }""")
    print(f"  Layers: {json.dumps(layers_info, indent=2)}", flush=True)

    if layers_info:
        # Click the first layer
        ly = layers_info[0]
        page.mouse.click(ly['x'], ly['y'])
        page.wait_for_timeout(500)

        # Also try dispatching a mousedown + mouseup (some canvas libs need this)
        page.evaluate(f"""() => {{
            var items = document.querySelectorAll('.layer-item, [class*="layer-item"]');
            if (items.length > 0) {{
                var item = items[0];
                item.dispatchEvent(new MouseEvent('mousedown', {{bubbles: true, clientX: {ly['x']}, clientY: {ly['y']}}}));
                item.dispatchEvent(new MouseEvent('mouseup', {{bubbles: true, clientX: {ly['x']}, clientY: {ly['y']}}}));
                item.dispatchEvent(new MouseEvent('click', {{bubbles: true, clientX: {ly['x']}, clientY: {ly['y']}}}));
            }}
        }}""")
        page.wait_for_timeout(500)

    # After layer selection, click on the canvas layer itself too
    page.mouse.click(700, 400)
    page.wait_for_timeout(500)

    # Reopen Enhance
    open_sidebar_tool(page, 628)
    page.wait_for_timeout(2000)

    warning3 = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Please select one layer on canvas') return true;
        }
        return false;
    }""")
    print(f"  Warning after layer JS: {warning3}", flush=True)

    if not warning3:
        return True

    # Approach 4: Place an expand result on canvas first via double-click
    print("\n  --- Enhance Approach 4: Double-click result to place ---", flush=True)
    close_all_panels(page)
    page.wait_for_timeout(500)

    # Switch to Results tab
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').includes('Result')) { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(500)

    # Double-click the latest result image to place it on canvas
    placed = page.evaluate("""() => {
        var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/"]');
        if (imgs.length === 0) return {error: 'no results'};
        var last = imgs[imgs.length - 1];
        var r = last.getBoundingClientRect();
        // Double-click to place on canvas
        last.dispatchEvent(new MouseEvent('dblclick', {
            bubbles: true,
            clientX: r.x + r.width/2,
            clientY: r.y + r.height/2
        }));
        return {placed: true, x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
    }""")
    print(f"  Place result: {json.dumps(placed)}", flush=True)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    # Now click the newly placed layer on canvas
    page.mouse.click(700, 400)
    page.wait_for_timeout(1000)

    # Open Enhance
    open_sidebar_tool(page, 628)
    page.wait_for_timeout(2000)

    warning4 = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Please select one layer on canvas') return true;
        }
        return false;
    }""")
    print(f"  Warning after place+click: {warning4}", flush=True)

    if not warning4:
        return True

    # Approach 5: Use the Enhance panel directly (it might work after placement)
    print("\n  --- Enhance Approach 5: Check panel state ---", flush=True)
    panel_state = page.evaluate("""() => {
        var result = {};
        // Check for Upscale button
        var upscale = document.querySelector('button.generative.ready');
        result.upscale_ready = upscale ? {
            text: (upscale.innerText || '').trim(),
            disabled: upscale.disabled,
            visible: upscale.getBoundingClientRect().width > 0
        } : null;

        // Check what options are visible
        var options = [];
        for (var el of document.querySelectorAll('button, [class*="option"]')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.x > 60 && r.x < 400 && r.width > 0 && text.length > 0 && text.length < 30) {
                options.push({text: text, x: Math.round(r.x), y: Math.round(r.y)});
            }
        }
        result.options = options.slice(0, 20);

        // Count canvas layers via fabric.js
        result.canvas_objects = null;
        try {
            var c = document.querySelector('canvas.lower-canvas');
            if (c && c.__fabric_canvas__) {
                result.canvas_objects = c.__fabric_canvas__.getObjects().length;
            }
        } catch(e) {}

        return result;
    }""")
    print(f"  Panel state: {json.dumps(panel_state, indent=2)}", flush=True)
    ss(page, "P135_enhance_debug")

    return False


def main():
    print("=" * 60, flush=True)
    print("PHASE 135: Product-faithful workflow codification", flush=True)
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
    #  TEST 1: Download real Amazon product images (multiple angles)
    # ============================================================
    print("\n=== TEST 1: Amazon product images (Sony WH-1000XM5) ===", flush=True)

    # Sony WH-1000XM5 — well-known product with good images
    product_images = download_amazon_product_images(ctx, "B09XS7JWHH")

    if not product_images:
        # Fallback
        for p in sorted(DOWNLOAD_DIR.glob("amazon_ref_*.jpg"), reverse=True):
            if p.stat().st_size > 10000:
                product_images = [str(p)]
                break

    if not product_images:
        print("  ERROR: No product images!", flush=True)
        sys.exit(1)

    main_image = product_images[0]
    print(f"\n  Using main: {main_image} ({os.path.getsize(main_image)/1024:.1f} KB)", flush=True)
    print(f"  Total angles: {len(product_images)}", flush=True)

    # ============================================================
    #  TEST 2: Full product-faithful workflow
    # ============================================================
    print("\n=== TEST 2: Full product-faithful workflow ===", flush=True)

    page, canvas_url = create_project_from_image(ctx, main_image)
    if not page:
        print("  FAILED to create project!", flush=True)
        sys.exit(1)

    print(f"  Canvas: {canvas_url}", flush=True)
    ss(page, "P135_02_canvas")

    # BG Remove
    print("\n  BG Remove...", flush=True)
    bg_time = bg_remove(page)
    ss(page, "P135_03_bg_removed")

    # Generative Expand with studio backdrop
    print("\n  Generative Expand...", flush=True)
    expand_files = generative_expand(
        page,
        prompt="Professional product photography studio backdrop, clean gradient lighting from above, subtle shadow beneath product, editorial quality commercial shot",
        aspect="16:9"
    )
    ss(page, "P135_04_expanded")

    # Export original canvas (with BG removed product)
    print("\n  Export BG-removed version...", flush=True)
    export_bg = export_canvas(page, "PNG", "2x")

    # ============================================================
    #  TEST 3: Fix Enhance & Upscale
    # ============================================================
    print("\n=== TEST 3: Enhance & Upscale fix attempts ===", flush=True)

    enhance_worked = try_enhance(page)
    print(f"\n  ENHANCE RESULT: {'SUCCESS' if enhance_worked else 'STILL BLOCKED'}", flush=True)

    if enhance_worked:
        # Configure and run Enhance
        for config in ['Precision Mode', '2x']:
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
        print(f"  Upscale click: {json.dumps(upscale)}", flush=True)

        if upscale.get('clicked'):
            page.wait_for_timeout(2000)
            close_dialogs(page)

            start = time.time()
            while time.time() - start < 90:
                elapsed = int(time.time() - start)
                close_dialogs(page)

                # Check for enhance completion or download
                done = page.evaluate("""() => {
                    for (var el of document.querySelectorAll('img')) {
                        var src = (el.src || '');
                        if (src.includes('static.dzine.ai/stylar_product/') && src.includes('enhance')) {
                            return src;
                        }
                    }
                    // Check for completion text
                    for (var el of document.querySelectorAll('*')) {
                        var text = (el.innerText || '').trim().toLowerCase();
                        if (text.includes('enhance') && (text.includes('complete') || text.includes('done'))) {
                            return 'complete';
                        }
                    }
                    return null;
                }""")
                if done:
                    print(f"  Enhance done in {elapsed}s: {done[:60] if isinstance(done, str) else done}", flush=True)
                    break
                if elapsed % 10 == 0:
                    print(f"  Enhance: {elapsed}s...", flush=True)
                page.wait_for_timeout(3000)

            ss(page, "P135_05_enhanced")

    # ============================================================
    #  TEST 4: Place expand result on canvas (for later use)
    # ============================================================
    print("\n=== TEST 4: Place expand result on canvas ===", flush=True)

    # Switch to Results tab
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').includes('Result')) { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(500)

    # Get result image info
    result_info = page.evaluate("""() => {
        var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/"]');
        var result = [];
        for (var img of imgs) {
            var r = img.getBoundingClientRect();
            var parent = img.parentElement;
            var grandparent = parent ? parent.parentElement : null;
            result.push({
                src: (img.src || '').substring(0, 80),
                x: Math.round(r.x + r.width/2),
                y: Math.round(r.y + r.height/2),
                w: Math.round(r.width),
                h: Math.round(r.height),
                parentTag: parent ? parent.tagName : null,
                parentClasses: parent ? (parent.className || '').toString().substring(0, 60) : null,
                gpClasses: grandparent ? (grandparent.className || '').toString().substring(0, 60) : null,
            });
        }
        return result;
    }""")
    print(f"  Results panel images: {len(result_info)}", flush=True)
    for ri in result_info[:4]:
        print(f"    ({ri['x']}, {ri['y']}) {ri['w']}x{ri['h']} parent={ri.get('parentClasses','')[:30]}", flush=True)

    # Try all placement methods
    if result_info:
        last = result_info[-1]

        # Method 1: Native double-click on the image element
        print(f"\n  Placement Method 1: Double-click result at ({last['x']}, {last['y']})...", flush=True)
        page.mouse.dblclick(last['x'], last['y'])
        page.wait_for_timeout(3000)
        close_dialogs(page)

        # Check if canvas layer count changed
        layer_count = page.evaluate("""() => {
            var items = document.querySelectorAll('.layer-item, [class*="layer-item"]');
            return items.length;
        }""")
        print(f"  Layers after double-click: {layer_count}", flush=True)

        ss(page, "P135_06_result_placed")

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
    print(f"PHASE 135 SUMMARY", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"  Credits remaining: {credits}", flush=True)
    print(f"  Amazon images downloaded: {len(product_images)}", flush=True)
    print(f"  BG Remove: {bg_time}s", flush=True)
    print(f"  Expand results: {len(expand_files)}", flush=True)
    print(f"  Export: {'YES' if export_bg else 'NO'}", flush=True)
    print(f"  Enhance fixed: {'YES' if enhance_worked else 'NO'}", flush=True)

    ss(page, "P135_07_final")
    print(f"\n===== PHASE 135 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
