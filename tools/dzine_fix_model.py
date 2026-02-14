#!/usr/bin/env python3
"""Fix Nano Banana Pro model selection in Dzine style picker."""

import json
import sys
import time
sys.path.insert(0, "/Users/ray/Documents/openclaw")
from tools.lib.brave_profile import connect_or_launch


def screenshot(page, name):
    path = f"/Users/ray/Downloads/{name}.png"
    page.screenshot(path=path)
    print(f"  [SS] {path}")


def main():
    print("=" * 70)
    print("FIX NANO BANANA PRO MODEL SELECTION")
    print("=" * 70)

    browser, context, _, _pw = connect_or_launch()
    page = context.pages[0]
    print(f"Connected. URL: {page.url}")

    if "dzine.ai/canvas" not in page.url:
        page.goto("https://www.dzine.ai/canvas?id=19861203")
        page.wait_for_timeout(5000)

    # Navigate to Txt2Img
    page.mouse.click(40, 766)  # distant
    page.wait_for_timeout(1500)
    page.mouse.click(40, 197)  # Txt2Img
    page.wait_for_timeout(2500)

    # Check current model
    current = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return 'NO PANEL';
        var sn = panel.querySelector('.style-name');
        return sn ? (sn.innerText || '').trim() : 'unknown';
    }""")
    print(f"  Current model: {current}")

    # Open style picker
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return false;
        var btn = panel.querySelector('button.style');
        if (btn) { btn.click(); return true; }
        return false;
    }""")
    page.wait_for_timeout(2000)

    # APPROACH 1: Click "General" category in left sidebar
    print("\n  Step 1: Click 'General' category...")
    gen_clicked = page.evaluate("""() => {
        var picker = document.querySelector('.style-list-panel');
        if (!picker) return 'no picker';
        var items = picker.querySelectorAll('*');
        for (var i = 0; i < items.length; i++) {
            var el = items[i];
            var text = (el.innerText || '').trim();
            var rect = el.getBoundingClientRect();
            if (text === 'General' && rect.x < 200 && rect.height > 15 && rect.height < 45) {
                el.click();
                return 'clicked General at y=' + Math.round(rect.y);
            }
        }
        return 'not found';
    }""")
    print(f"    Result: {gen_clicked}")
    page.wait_for_timeout(1500)
    screenshot(page, "p182_general_category")

    # APPROACH 2: Map individual items in the grid
    print("\n  Step 2: Mapping individual style cards...")
    card_map = page.evaluate("""() => {
        var picker = document.querySelector('.style-list-panel');
        if (!picker) return [];
        var results = [];
        // Get all small text elements that look like style names
        var allEls = picker.querySelectorAll('span, p, div, a');
        for (var el of allEls) {
            var text = (el.innerText || '').trim();
            if (!text || text.length < 3 || text.length > 30) continue;
            // Must not contain newline
            if (text.indexOf('\\n') >= 0) continue;
            var rect = el.getBoundingClientRect();
            // Must be in the content area (x > 200) and visible
            if (rect.x < 200 || rect.height === 0) continue;
            // Small height = text label
            if (rect.height > 30) continue;
            results.push({
                text: text,
                x: Math.round(rect.x),
                y: Math.round(rect.y),
                w: Math.round(rect.width),
                h: Math.round(rect.height),
                tag: el.tagName
            });
        }
        // Deduplicate by text+y
        var seen = {};
        var unique = [];
        for (var r of results) {
            var key = r.text + '_' + r.y;
            if (!seen[key]) {
                seen[key] = true;
                unique.push(r);
            }
        }
        return unique.slice(0, 40);
    }""")
    print(f"  Found {len(card_map)} style labels:")
    nbp_item = None
    for item in card_map:
        marker = ""
        if item["text"] == "Nano Banana Pro":
            marker = " <<<<< TARGET"
            nbp_item = item
        print(f"    '{item['text']}' at ({item['x']},{item['y']}) {item['w']}x{item['h']}{marker}")

    # APPROACH 3: Click Nano Banana Pro by finding its label and clicking parent card
    if nbp_item:
        print(f"\n  Step 3: Clicking Nano Banana Pro at ({nbp_item['x']},{nbp_item['y']})...")
        # Click slightly above the text label (on the thumbnail) for better card selection
        click_x = nbp_item["x"] + nbp_item["w"] // 2
        click_y = nbp_item["y"] - 60  # thumbnail is above the label
        print(f"    Mouse click at ({click_x}, {click_y})")
        page.mouse.click(click_x, click_y)
        page.wait_for_timeout(1500)
    else:
        # If not visible, try scrolling
        print("\n  Nano Banana Pro not visible. Trying scroll...")
        page.evaluate("""() => {
            var picker = document.querySelector('.style-list-panel');
            if (!picker) return;
            var scrollable = null;
            var divs = picker.querySelectorAll('div');
            for (var d of divs) {
                if (d.scrollHeight > d.clientHeight + 100 && d.clientHeight > 200) {
                    scrollable = d;
                    break;
                }
            }
            if (scrollable) scrollable.scrollTop = 0;
        }""")
        page.wait_for_timeout(500)

        # After scrolling to top, check again
        card_map2 = page.evaluate("""() => {
            var picker = document.querySelector('.style-list-panel');
            if (!picker) return [];
            var results = [];
            var allEls = picker.querySelectorAll('span, p, div, a');
            for (var el of allEls) {
                var text = (el.innerText || '').trim();
                if (text === 'Nano Banana Pro') {
                    var rect = el.getBoundingClientRect();
                    if (rect.height > 0) {
                        results.push({x: Math.round(rect.x), y: Math.round(rect.y), h: Math.round(rect.height)});
                    }
                }
            }
            return results;
        }""")
        print(f"    Nano Banana Pro elements: {json.dumps(card_map2)}")
        if card_map2:
            click_x = card_map2[0]["x"] + 50
            click_y = card_map2[0]["y"] - 60
            print(f"    Mouse click at ({click_x}, {click_y})")
            page.mouse.click(click_x, click_y)
            page.wait_for_timeout(1500)

    # Close picker
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # Verify
    new_model = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return 'NO PANEL';
        var sn = panel.querySelector('.style-name');
        return sn ? (sn.innerText || '').trim() : 'unknown';
    }""")
    print(f"\n  Model after selection: {new_model}")

    if "Nano Banana" in new_model:
        print("  SUCCESS! Nano Banana Pro is now selected!")
    else:
        print(f"  Model did not change. Trying alternative approach...")

        # APPROACH 4: Use Playwright locator API directly
        print("\n  Step 4: Using Playwright locator...")
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return;
            var btn = panel.querySelector('button.style');
            if (btn) btn.click();
        }""")
        page.wait_for_timeout(2000)

        # Click General category
        page.evaluate("""() => {
            var picker = document.querySelector('.style-list-panel');
            if (!picker) return;
            var items = picker.querySelectorAll('*');
            for (var el of items) {
                var text = (el.innerText || '').trim();
                var rect = el.getBoundingClientRect();
                if (text === 'General' && rect.x < 200 && rect.height > 15 && rect.height < 45) {
                    el.click();
                    break;
                }
            }
        }""")
        page.wait_for_timeout(1500)

        # Use Playwright's locator API to find and click the Nano Banana Pro card
        try:
            nbp_locator = page.locator('.style-list-panel [class*="style-item"]').filter(has_text="Nano Banana Pro")
            count = nbp_locator.count()
            print(f"    Locator found {count} matching elements")

            if count > 0:
                # Get the first match that's a reasonable size (individual card, not container)
                for i in range(count):
                    el = nbp_locator.nth(i)
                    box = el.bounding_box()
                    if box and box["height"] < 200:
                        print(f"    Clicking match {i}: {box['width']:.0f}x{box['height']:.0f} at ({box['x']:.0f},{box['y']:.0f})")
                        el.click(timeout=3000)
                        break
        except Exception as e:
            print(f"    Locator error: {e}")

        page.wait_for_timeout(1000)
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        final_model = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return 'NO PANEL';
            var sn = panel.querySelector('.style-name');
            return sn ? (sn.innerText || '').trim() : 'unknown';
        }""")
        print(f"\n  Final model: {final_model}")

        if "Nano Banana" in final_model:
            print("  SUCCESS on second attempt!")
        else:
            # APPROACH 5: Search and click
            print("\n  Step 5: Search approach...")
            page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (panel) {
                    var btn = panel.querySelector('button.style');
                    if (btn) btn.click();
                }
            }""")
            page.wait_for_timeout(2000)

            # Find and clear search input, type model name
            search = page.locator('.style-list-panel input[type="text"]').first
            search.click()
            page.wait_for_timeout(300)
            search.fill("")
            page.wait_for_timeout(300)
            search.fill("Nano Banana Pro")
            page.wait_for_timeout(2000)

            screenshot(page, "p182_search_nbp")

            # Now map what's visible after search
            search_results = page.evaluate("""() => {
                var picker = document.querySelector('.style-list-panel');
                if (!picker) return [];
                var items = picker.querySelectorAll('[class*="style-item"]');
                var results = [];
                for (var item of items) {
                    var rect = item.getBoundingClientRect();
                    if (rect.height > 0 && rect.height < 200 && rect.y > 100 && rect.y < 800) {
                        results.push({
                            text: (item.innerText || '').trim().substring(0, 40),
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            w: Math.round(rect.width),
                            h: Math.round(rect.height)
                        });
                    }
                }
                return results;
            }""")
            print(f"    Search results ({len(search_results)}):")
            for sr in search_results:
                print(f"      '{sr['text'][:30]}' at ({sr['x']},{sr['y']}) {sr['w']}x{sr['h']}")

            # Click the first small result (individual card, not container)
            for sr in search_results:
                if sr["h"] < 180 and "Nano Banana Pro" in sr["text"]:
                    cx = sr["x"] + sr["w"] // 2
                    cy = sr["y"] + sr["h"] // 2
                    print(f"    Clicking at ({cx}, {cy})")
                    page.mouse.click(cx, cy)
                    break
            else:
                # Click first small card
                for sr in search_results:
                    if sr["h"] < 180 and sr["w"] < 180:
                        cx = sr["x"] + sr["w"] // 2
                        cy = sr["y"] + sr["h"] // 2
                        print(f"    Clicking first small card at ({cx}, {cy})")
                        page.mouse.click(cx, cy)
                        break

            page.wait_for_timeout(1500)
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)

            last_model = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return 'NO PANEL';
                var sn = panel.querySelector('.style-name');
                return sn ? (sn.innerText || '').trim() : 'unknown';
            }""")
            print(f"\n  Model after search approach: {last_model}")

    screenshot(page, "p182_model_final")

    # If we have Nano Banana Pro, generate a test image
    final_check = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return '';
        var sn = panel.querySelector('.style-name');
        return sn ? (sn.innerText || '').trim() : '';
    }""")

    if "Nano Banana" in final_check:
        print("\n" + "=" * 70)
        print("GENERATING WITH NANO BANANA PRO!")
        print("=" * 70)

        # Fill prompt
        prompt = "Premium wireless over-ear headphones with brushed aluminum cups and plush memory foam ear cushions on a clean white studio background. Professional product photography, three-point soft lighting, razor-sharp focus, color accurate, 8K commercial grade. No text, no watermarks."

        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return;
            var ta = panel.querySelector('textarea');
            if (ta) { ta.focus(); ta.click(); }
        }""")
        page.wait_for_timeout(300)
        page.keyboard.press("Meta+a")
        page.wait_for_timeout(200)
        page.keyboard.press("Delete")
        page.wait_for_timeout(200)
        page.keyboard.type(prompt, delay=2)
        page.wait_for_timeout(500)

        # Normal mode
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return;
            for (var btn of panel.querySelectorAll('button')) {
                var text = (btn.innerText || '').trim();
                var cls = (typeof btn.className === 'string') ? btn.className : '';
                if (text === 'Normal' && cls.includes('options') && !cls.includes('selected')) {
                    btn.click();
                    break;
                }
            }
        }""")
        page.wait_for_timeout(300)

        # Count before
        before = page.evaluate("""() => document.querySelectorAll("img[src*='static.dzine.ai/stylar_product/p/']").length""")

        # Generate
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return;
            var btn = panel.querySelector('.generative.ready');
            if (btn && !btn.disabled) btn.click();
        }""")
        print("  Generating...")

        start = time.time()
        while time.time() - start < 90:
            page.wait_for_timeout(3000)
            elapsed = int(time.time() - start)
            after = page.evaluate("""() => document.querySelectorAll("img[src*='static.dzine.ai/stylar_product/p/']").length""")
            if after > before:
                print(f"  COMPLETE! ({elapsed}s, +{after-before} images)")
                break
            progress = page.evaluate("""() => {
                for (var el of document.querySelectorAll('*')) {
                    var txt = (el.innerText || '').trim();
                    if (/^[0-9]{1,3}%$/.test(txt)) {
                        var r = el.getBoundingClientRect();
                        if (r.x > 1000) return txt;
                    }
                }
                return '';
            }""")
            if progress:
                print(f"    {progress} ({elapsed}s)")
        else:
            print(f"  TIMEOUT ({int(time.time()-start)}s)")

        screenshot(page, "p182_nbp_result")

        # Get latest URLs
        urls = page.evaluate("""() => {
            var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]');
            var urls = [];
            for (var img of imgs) urls.push(img.src);
            return urls.slice(-4);
        }""")
        print("  Results:")
        for u in urls:
            print(f"    {u[:150]}")

    print("\nDone.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
