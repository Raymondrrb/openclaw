"""Phase 100: Catalog ALL Img2Img models + Lip Sync face→audio complete.
A) Img2Img: Open style selector, scroll through all categories, catalog every model
B) Lip Sync: mouse-click Pick Face → select canvas thumb → face detect → crop → AUDIO
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


def dismiss_popups(page):
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'Skip' && el.getBoundingClientRect().width > 20) {
                el.click(); return;
            }
        }
    }""")
    page.wait_for_timeout(500)
    close_dialogs(page)


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
    #  PART A: IMG2IMG MODELS — FULL CATALOG
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART A: IMG2IMG MODEL CATALOG", flush=True)
    print("=" * 60, flush=True)

    # Open Img2Img
    page.mouse.click(40, 252)
    page.wait_for_timeout(3000)
    close_dialogs(page)
    dismiss_popups(page)

    # Click style-name to open selector
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        var sn = panel?.querySelector('.style-name');
        if (sn) sn.click();
    }""")
    page.wait_for_timeout(3000)
    close_dialogs(page)
    ss(page, "P100_01_style_selector")

    # Map the style selector structure
    selector_info = page.evaluate("""() => {
        // Find the style selector overlay
        for (var el of document.querySelectorAll('*')) {
            var cs = window.getComputedStyle(el);
            var z = parseInt(cs.zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (r.width > 600 && r.height > 400 && r.x > 100 && z >= 400) {
                // This is the style selector
                // Get categories from sidebar
                var categories = [];
                for (var cat of el.querySelectorAll('*')) {
                    var cr = cat.getBoundingClientRect();
                    var text = (cat.innerText || '').trim();
                    // Sidebar items are on the left side
                    if (cr.x < 400 && cr.width > 30 && cr.width < 200
                        && cr.height > 10 && cr.height < 40
                        && text.length > 1 && text.length < 30
                        && text.indexOf('\\n') === -1) {
                        categories.push(text);
                    }
                }
                categories = [...new Set(categories)];

                // Get visible model names
                var models = [];
                for (var child of el.querySelectorAll('*')) {
                    var cr = child.getBoundingClientRect();
                    var text = (child.innerText || '').trim();
                    var cls = (child.className || '').toString();
                    // Model names are below the style thumbnails
                    if (cr.x > 400 && cr.y > 300 && cr.height < 25
                        && cr.height > 8 && text.length > 2 && text.length < 40
                        && text.indexOf('\\n') === -1
                        && !text.includes('Search') && !text.includes('Create')
                        && !text.includes('Quick') && !text.includes('Pro Style')
                        && !text.includes('Instantly') && !text.includes('Carefully')) {
                        models.push(text);
                    }
                }
                models = [...new Set(models)];

                return {categories: categories, visibleModels: models};
            }
        }
        return null;
    }""")
    if selector_info:
        print(f"\n  Categories ({len(selector_info.get('categories', []))}):", flush=True)
        for c in selector_info.get('categories', []):
            print(f"    {c}", flush=True)
        print(f"\n  Visible models ({len(selector_info.get('visibleModels', []))}):", flush=True)
        for m in selector_info.get('visibleModels', []):
            print(f"    {m}", flush=True)

    # Now click each category and read the models
    categories = [
        "General", "Realistic", "Illustration", "Portrait", "3D",
        "Anime", "Line Art", "Material Art", "Logo & Icon", "Character",
        "Scene", "Interior", "Tattoo",
    ]

    all_models = {}
    for cat_name in categories:
        # Click category
        clicked = page.evaluate("""(catName) => {
            // Find the style selector overlay
            for (var el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                if (r.width > 600 && r.height > 400 && r.x > 100) {
                    for (var item of el.querySelectorAll('*')) {
                        var text = (item.innerText || '').trim();
                        var ir = item.getBoundingClientRect();
                        if (text === catName && ir.x < 400 && ir.width > 30 && ir.height > 10 && ir.height < 40) {
                            item.click();
                            return true;
                        }
                    }
                }
            }
            return false;
        }""", cat_name)

        if not clicked:
            print(f"  {cat_name}: not found", flush=True)
            continue

        page.wait_for_timeout(1500)

        # Read models in this category (scroll through all)
        models = page.evaluate("""() => {
            var models = [];
            var seen = new Set();
            // Find the scrollable content area
            for (var el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                if (r.width > 500 && r.height > 300 && r.x > 350) {
                    // This is the content area — find all model name elements
                    for (var child of el.querySelectorAll('*')) {
                        var text = (child.innerText || '').trim();
                        var cr = child.getBoundingClientRect();
                        var cls = (child.className || '').toString();
                        // Model names: small text below thumbnails
                        if (text.length > 2 && text.length < 40
                            && cr.height < 25 && cr.height > 8
                            && cr.y > 280
                            && text.indexOf('\\n') === -1
                            && !text.includes('Search') && !text.includes('Create')
                            && !text.includes('Quick') && !text.includes('Pro Style')
                            && !text.includes('Dzine Styles') && !text.includes('Community')
                            && !text.includes('Instantly') && !text.includes('Carefully')
                            && !seen.has(text)) {
                            seen.add(text);
                            models.push(text);
                        }
                    }
                    break;
                }
            }
            return models;
        }""")
        all_models[cat_name] = models
        print(f"  {cat_name} ({len(models)}): {models}", flush=True)

        # Scroll down in the content area to find more models
        more = page.evaluate("""() => {
            // Find the scrollable grid area
            var scrollable = null;
            for (var el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var cs = window.getComputedStyle(el);
                if (r.width > 500 && r.height > 300 && r.x > 350
                    && (cs.overflowY === 'auto' || cs.overflowY === 'scroll')) {
                    scrollable = el;
                    break;
                }
            }
            if (!scrollable) return null;

            // Scroll down
            scrollable.scrollTop += 500;
            return true;
        }""")
        if more:
            page.wait_for_timeout(1000)
            more_models = page.evaluate("""() => {
                var models = [];
                var seen = new Set();
                for (var el of document.querySelectorAll('*')) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 500 && r.height > 300 && r.x > 350) {
                        for (var child of el.querySelectorAll('*')) {
                            var text = (child.innerText || '').trim();
                            var cr = child.getBoundingClientRect();
                            if (text.length > 2 && text.length < 40
                                && cr.height < 25 && cr.height > 8
                                && cr.y > 280
                                && text.indexOf('\\n') === -1
                                && !text.includes('Search') && !text.includes('Create')
                                && !text.includes('Quick') && !text.includes('Pro Style')
                                && !text.includes('Dzine Styles') && !text.includes('Community')
                                && !text.includes('Instantly') && !text.includes('Carefully')
                                && !seen.has(text)) {
                                seen.add(text);
                                models.push(text);
                            }
                        }
                        break;
                    }
                }
                return models;
            }""")
            new_models = [m for m in more_models if m not in all_models[cat_name]]
            if new_models:
                all_models[cat_name].extend(new_models)
                print(f"    +scrolled: {new_models}", flush=True)

            # Scroll back to top
            page.evaluate("""() => {
                for (var el of document.querySelectorAll('*')) {
                    var r = el.getBoundingClientRect();
                    var cs = window.getComputedStyle(el);
                    if (r.width > 500 && r.height > 300 && r.x > 350
                        && (cs.overflowY === 'auto' || cs.overflowY === 'scroll')) {
                        el.scrollTop = 0;
                        break;
                    }
                }
            }""")
            page.wait_for_timeout(500)

    # Print summary
    print(f"\n\n  === COMPLETE MODEL CATALOG ===", flush=True)
    total = 0
    for cat, models in all_models.items():
        print(f"\n  {cat} ({len(models)}):", flush=True)
        for m in models:
            print(f"    - {m}", flush=True)
        total += len(models)
    print(f"\n  TOTAL: {total} models", flush=True)

    # Close style selector
    page.evaluate("""() => {
        // Find close button in the overlay
        for (var el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.width > 600 && r.height > 400 && r.x > 100) {
                var close = el.querySelector('.ico-close, [class*="close"]');
                if (close) { close.click(); return; }
            }
        }
    }""")
    page.wait_for_timeout(1000)

    # ============================================================
    #  PART B: LIP SYNC — FACE → AUDIO
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART B: LIP SYNC FACE → AUDIO", flush=True)
    print("=" * 60, flush=True)

    # Close Img2Img panel
    page.evaluate("""() => {
        var c = document.querySelector('.c-gen-config.show .ico-close');
        if (c) c.click();
    }""")
    page.wait_for_timeout(500)

    # Open Lip Sync
    page.mouse.click(40, 425)
    page.wait_for_timeout(3000)
    close_dialogs(page)
    dismiss_popups(page)

    # Click "Pick a Face Image" with mouse
    coords = page.evaluate("""() => {
        for (var btn of document.querySelectorAll('button.pick-image')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text.includes('Face Image') && !text.includes('Video') && r.width > 100) {
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
            }
        }
        return null;
    }""")
    if coords:
        page.mouse.click(coords['x'], coords['y'])
        print(f"  Clicked Pick a Face Image at ({coords['x']},{coords['y']})", flush=True)
    else:
        print("  Pick a Face Image button not found!", flush=True)
    page.wait_for_timeout(3000)
    close_dialogs(page)
    ss(page, "P100_02_pick_image")

    # Find "Pick Image" dialog and click first canvas thumbnail
    thumb_clicked = page.evaluate("""() => {
        // Find overlay with "Pick Image" or similar
        for (var el of document.querySelectorAll('*')) {
            var cs = window.getComputedStyle(el);
            var z = parseInt(cs.zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > 400 && r.width > 300 && r.height > 200) {
                // Find canvas thumbnails
                var imgs = el.querySelectorAll('img');
                for (var img of imgs) {
                    var ir = img.getBoundingClientRect();
                    var src = img.src || '';
                    if (ir.width > 50 && ir.height > 50 && ir.y > 300 && src.includes('stylar_product')) {
                        return {
                            x: Math.round(ir.x + ir.width/2),
                            y: Math.round(ir.y + ir.height/2),
                            src: src.substring(0, 80),
                        };
                    }
                }
            }
        }
        return null;
    }""")

    if thumb_clicked:
        print(f"  Clicking canvas thumb at ({thumb_clicked['x']},{thumb_clicked['y']})", flush=True)
        page.mouse.click(thumb_clicked['x'], thumb_clicked['y'])
        page.wait_for_timeout(4000)
        close_dialogs(page)
        ss(page, "P100_03_face_detect")

        # Check for face detection
        face_status = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var t = (el.innerText || '').trim();
                if (t.includes('face selected')) return 'face: ' + t;
                if (t === 'Mark Face Manually') return 'face detection active';
            }
            return 'no face dialog';
        }""")
        print(f"  {face_status}", flush=True)

        if 'face' in face_status.lower():
            # Next 1: face → crop
            print("  NEXT 1: face → crop", flush=True)
            n1 = page.evaluate("""() => {
                for (var btn of document.querySelectorAll('button')) {
                    var t = (btn.innerText || '').trim();
                    var r = btn.getBoundingClientRect();
                    if (t === 'Next' && r.width > 30 && r.y > 500) {
                        return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                    }
                }
                return null;
            }""")
            if n1:
                page.mouse.click(n1['x'], n1['y'])
                page.wait_for_timeout(2000)

                # Next 2: crop → done
                print("  NEXT 2: crop → done", flush=True)
                n2 = page.evaluate("""() => {
                    for (var btn of document.querySelectorAll('button')) {
                        var t = (btn.innerText || '').trim();
                        var r = btn.getBoundingClientRect();
                        if (t === 'Next' && r.width > 30 && r.y > 500) {
                            return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                        }
                    }
                    return null;
                }""")
                if n2:
                    page.mouse.click(n2['x'], n2['y'])
                    page.wait_for_timeout(5000)
                    close_dialogs(page)
                    ss(page, "P100_04_face_set")

                    # Check panel state — face should now be set
                    panel_state = page.evaluate("""() => {
                        var p = document.querySelector('.c-gen-config.show');
                        if (!p) return null;
                        var text = (p.innerText || '').trim();
                        var hasWarning = text.includes('Please pick');

                        // Find face preview
                        var faceImg = null;
                        for (var img of p.querySelectorAll('img')) {
                            var r = img.getBoundingClientRect();
                            var src = img.src || '';
                            if (r.width > 30 && r.height > 30 && src.includes('stylar_product')) {
                                faceImg = src.substring(0, 100);
                            }
                        }

                        // Check for audio upload elements
                        var audioEls = [];
                        for (var el of p.querySelectorAll('*')) {
                            var cls = (el.className || '').toString();
                            var t = (el.innerText || '').trim();
                            var r = el.getBoundingClientRect();
                            if (r.width > 0 && (cls.includes('audio') || cls.includes('voice')
                                || t.includes('Audio') || t.includes('audio')
                                || t.includes('Upload') || t.includes('upload')
                                || t.includes('Record') || t.includes('Browse'))) {
                                audioEls.push({
                                    classes: cls.substring(0, 40),
                                    text: t.substring(0, 40),
                                    y: Math.round(r.y),
                                });
                            }
                        }

                        return {
                            text: text.substring(0, 400),
                            hasWarning: hasWarning,
                            faceImg: faceImg,
                            audioEls: audioEls,
                        };
                    }""")

                    if panel_state:
                        print(f"\n  Panel warning: {panel_state.get('hasWarning')}", flush=True)
                        print(f"  Face preview: {panel_state.get('faceImg')}", flush=True)
                        print(f"  Audio elements: {panel_state.get('audioEls')}", flush=True)
                        print(f"  Full text: {panel_state['text'][:250]}", flush=True)

                    # Check canvas area for audio UI
                    canvas_audio = page.evaluate("""() => {
                        var items = [];
                        var seen = new Set();
                        for (var el of document.querySelectorAll('*')) {
                            var r = el.getBoundingClientRect();
                            var text = (el.innerText || '').trim();
                            var cls = (el.className || '').toString();
                            if (r.x > 300 && r.x < 1100 && r.y > 50 && r.y < 850
                                && r.width > 30 && r.height > 10
                                && (text.length > 0 || el.tagName === 'BUTTON' || el.tagName === 'INPUT')
                                && r.height < 100) {
                                var key = (text || cls).substring(0,20) + '|' + Math.round(r.y/10);
                                if (!seen.has(key) && text.length < 80) {
                                    seen.add(key);
                                    items.push({
                                        x: Math.round(r.x), y: Math.round(r.y),
                                        w: Math.round(r.width), h: Math.round(r.height),
                                        text: text.substring(0, 60),
                                        tag: el.tagName,
                                        classes: cls.substring(0, 30),
                                    });
                                }
                            }
                        }
                        items.sort(function(a,b){return a.y - b.y});
                        return items.slice(0, 25);
                    }""")
                    print(f"\n  Canvas elements ({len(canvas_audio)}):", flush=True)
                    for c in canvas_audio:
                        print(f"    ({c['x']},{c['y']}) {c['w']}x{c['h']} <{c['tag']}> '{c['text'][:40]}' c='{c['classes'][:20]}'", flush=True)

    ss(page, "P100_05_final")
    print(f"\n\n===== PHASE 100 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
