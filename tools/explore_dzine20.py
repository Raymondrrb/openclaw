"""Phase 20: Check CC results, test result actions, explore Lip Sync, styles, API.

CC images were submitted in Phase 19 — need to wait for them to finish.
Then test: Variation, Insert Character, Lip Sync, Expression Edit.
Then explore: Community styles, API docs, Pricing.
"""

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from tools.lib.brave_profile import connect_or_launch

OUT_DIR = _ROOT / "artifacts" / "dzine-explore"
OUT_DIR.mkdir(parents=True, exist_ok=True)

_N = 0


def ss(page, name):
    global _N
    _N += 1
    path = OUT_DIR / f"N{_N:02d}_{name}.png"
    page.screenshot(path=str(path), full_page=False)
    print(f"  SS: N{_N:02d}_{name}")


def close_all_dialogs(page):
    for _ in range(5):
        found = False
        for text in ["Not now", "Close", "Never show again", "Got it", "Skip"]:
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


def main():
    print("Connecting...")
    browser, context, should_close, pw = connect_or_launch(headless=False)

    page = None
    for p in context.pages:
        if "canvas?id=19797967" in p.url:
            page = p
            break

    if not page:
        page = context.new_page()
        page.set_viewport_size({"width": 1440, "height": 900})
        page.goto("https://www.dzine.ai/canvas?id=19797967",
                  wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(8000)

    page.set_viewport_size({"width": 1440, "height": 900})
    page.bring_to_front()
    page.wait_for_timeout(1000)
    close_all_dialogs(page)

    try:
        # ================================================================
        # PART 1: CHECK CC GENERATION RESULTS
        # ================================================================
        print("\n" + "=" * 60)
        print("  PART 1: CHECK CC RESULTS")
        print("=" * 60)

        # Close any panel, switch to Results tab
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # Click Results tab in the right panel
        page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text === 'Results' && rect.y < 80 && rect.x > 550 && rect.x < 700) {
                    el.click();
                    return;
                }
            }
        }""")
        page.wait_for_timeout(1000)
        ss(page, "results_panel")

        # Map all result sections in the right panel
        results = page.evaluate("""() => {
            const results = [];
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                // Result headers with type labels
                if ((text === 'Consistent Character' || text === 'Text-to-Image' ||
                     text === 'Character Sheet' || text === 'Chat Editor') &&
                    rect.x > 550 && rect.y > 60 && rect.width > 50 && rect.width < 200 &&
                    el.children.length < 3) {
                    results.push({type: text, x: Math.round(rect.x), y: Math.round(rect.y)});
                }
            }
            return results.sort((a, b) => a.y - b.y);
        }""")
        print(f"\n  Result sections ({len(results)}):")
        for r in results:
            print(f"    y={r['y']} {r['type']}")

        # Check for result images (thumbnails in the right panel)
        result_imgs = page.evaluate("""() => {
            const imgs = [];
            for (const img of document.querySelectorAll('img')) {
                const r = img.getBoundingClientRect();
                if (r.x > 550 && r.y > 60 && r.width > 30 && r.height > 30) {
                    imgs.push({
                        src: img.src.substring(0, 120),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height)
                    });
                }
            }
            return imgs;
        }""")
        print(f"\n  Result images ({len(result_imgs)}):")
        for img in result_imgs:
            print(f"    ({img['x']},{img['y']}) {img['w']}x{img['h']} {img['src'][:80]}")

        # Check for progress indicators (percentage)
        progress = page.evaluate("""() => {
            const items = [];
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text.match(/^\\d{1,3}%$/) && rect.x > 550 && rect.y > 60) {
                    items.push({pct: text, x: Math.round(rect.x), y: Math.round(rect.y)});
                }
            }
            return items;
        }""")
        print(f"\n  Progress indicators: {progress}")

        # Wait for any ongoing generations to complete
        if progress:
            print("  Waiting for generations to complete...")
            for _ in range(24):  # Up to 2 minutes
                page.wait_for_timeout(5000)
                progress = page.evaluate("""() => {
                    const items = [];
                    for (const el of document.querySelectorAll('*')) {
                        const text = (el.innerText || '').trim();
                        const rect = el.getBoundingClientRect();
                        if (text.match(/^\\d{1,3}%$/) && rect.x > 550 && rect.y > 60) {
                            items.push(text);
                        }
                    }
                    return items;
                }""")
                if not progress:
                    print("  All generations complete!")
                    break
                print(f"  ... still generating: {progress}")
            ss(page, "results_complete")

        # Now get all result images after completion
        final_imgs = page.evaluate("""() => {
            const imgs = [];
            for (const img of document.querySelectorAll('img')) {
                const r = img.getBoundingClientRect();
                if (r.x > 550 && r.y > 60 && r.width > 30 && r.height > 30) {
                    imgs.push({
                        src: img.src,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height)
                    });
                }
            }
            return imgs;
        }""")
        print(f"\n  Final result images ({len(final_imgs)}):")
        for img in final_imgs[:10]:
            print(f"    ({img['x']},{img['y']}) {img['w']}x{img['h']}")
            print(f"      {img['src'][:120]}")

        # ================================================================
        # PART 2: VIEW CC RESULT IN DETAIL
        # ================================================================
        print("\n" + "=" * 60)
        print("  PART 2: VIEW CC RESULT")
        print("=" * 60)

        # Find the first Consistent Character result image and click it
        cc_img = None
        for img in final_imgs:
            if "consistent" in img.get("src", "").lower() or "character" in img.get("src", "").lower():
                cc_img = img
                break
        if not cc_img and final_imgs:
            cc_img = final_imgs[0]  # Use first image

        if cc_img:
            print(f"  Clicking CC result at ({cc_img['x']},{cc_img['y']})...")
            page.mouse.click(cc_img["x"] + cc_img["w"]//2, cc_img["y"] + cc_img["h"]//2)
            page.wait_for_timeout(2000)
            ss(page, "cc_result_detail")

            # Check what opened — lightbox/preview?
            preview = page.evaluate("""() => {
                // Look for a large preview image or overlay
                for (const el of document.querySelectorAll('img')) {
                    const r = el.getBoundingClientRect();
                    if (r.width > 300 && r.height > 200 && r.x > 100 && r.x < 800) {
                        return {src: el.src.substring(0, 120), w: r.width, h: r.height,
                                x: Math.round(r.x), y: Math.round(r.y)};
                    }
                }
                return null;
            }""")
            print(f"  Preview: {preview}")

            # Scroll right panel to see CC results (they might be below viewport)
            page.evaluate("""() => {
                // Find the scrollable results container and scroll down
                for (const el of document.querySelectorAll('*')) {
                    const rect = el.getBoundingClientRect();
                    if (rect.x > 550 && rect.width > 200 && rect.height > 500 &&
                        el.scrollHeight > el.clientHeight) {
                        el.scrollTop = 0;  // Scroll to top first
                        return true;
                    }
                }
                return false;
            }""")
            page.wait_for_timeout(500)
            ss(page, "results_scrolled_top")

        # ================================================================
        # PART 3: EXPLORE RESULT ACTION BUTTONS
        # ================================================================
        print("\n" + "=" * 60)
        print("  PART 3: RESULT ACTION BUTTONS")
        print("=" * 60)

        # Get all visible action buttons for the first CC result
        actions = page.evaluate("""() => {
            const actions = [];
            let ccFound = false;
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text === 'Consistent Character' && rect.x > 550) {
                    ccFound = true;
                    continue;
                }
                if (ccFound && rect.x > 550 && rect.y > 60 && rect.width > 100) {
                    if (['Variation', 'Insert Character', 'Chat Editor', 'Image Editor',
                         'AI Video', 'Lip Sync', 'Expression Edit', 'Face Swap',
                         'Enhance & Upscale'].includes(text)) {
                        actions.push({text, x: Math.round(rect.x), y: Math.round(rect.y),
                                     w: Math.round(rect.width), h: Math.round(rect.height)});
                    }
                }
                // Stop at next result section
                if (ccFound && (text === 'Text-to-Image' || text === 'Character Sheet') && rect.x > 550) {
                    break;
                }
            }
            return actions;
        }""")
        print(f"\n  CC result actions ({len(actions)}):")
        for a in actions:
            print(f"    ({a['x']},{a['y']}) {a['w']}x{a['h']} '{a['text']}'")

        # ================================================================
        # PART 4: EXPLORE COMMUNITY STYLES PAGE
        # ================================================================
        print("\n" + "=" * 60)
        print("  PART 4: COMMUNITY STYLES")
        print("=" * 60)

        # Open a new tab for the community page
        community_page = context.new_page()
        community_page.set_viewport_size({"width": 1440, "height": 900})
        print("  Navigating to community styles...")
        community_page.goto("https://www.dzine.ai/community/list/all",
                            wait_until="domcontentloaded", timeout=30000)
        community_page.wait_for_timeout(5000)
        close_all_dialogs(community_page)
        ss(community_page, "community_page")

        # Map the page content
        community_items = community_page.evaluate("""() => {
            const items = [];
            const seen = new Set();
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text && text.length > 2 && text.length < 60 && rect.width > 20 &&
                    rect.height > 10 && el.children.length < 3 && !seen.has(text)) {
                    seen.add(text);
                    items.push({text, x: Math.round(rect.x), y: Math.round(rect.y),
                               w: Math.round(rect.width), h: Math.round(rect.height),
                               tag: el.tagName});
                }
            }
            return items.sort((a, b) => a.y - b.y).slice(0, 50);
        }""")
        print(f"\n  Community page ({len(community_items)} items):")
        for item in community_items:
            print(f"    ({item['x']},{item['y']}) {item['w']}x{item['h']} <{item['tag']}> {item['text']}")

        # Look for style categories/tabs
        categories = community_page.evaluate("""() => {
            const cats = [];
            for (const el of document.querySelectorAll('a, button, [role="tab"]')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text.length > 2 && text.length < 30 && rect.y < 150 && rect.width > 20) {
                    cats.push({text, x: Math.round(rect.x), href: el.href || ''});
                }
            }
            const seen = new Set();
            return cats.filter(c => { if (seen.has(c.text)) return false; seen.add(c.text); return true; });
        }""")
        print(f"\n  Style categories:")
        for cat in categories:
            print(f"    x={cat['x']} '{cat['text']}' → {cat['href'][:60] if cat['href'] else 'button'}")

        # Count style cards
        style_cards = community_page.evaluate("""() => {
            let count = 0;
            for (const img of document.querySelectorAll('img')) {
                const r = img.getBoundingClientRect();
                if (r.width > 100 && r.height > 100 && r.y > 100) count++;
            }
            return count;
        }""")
        print(f"\n  Style cards visible: {style_cards}")

        community_page.close()

        # ================================================================
        # PART 5: EXPLORE API DOCS
        # ================================================================
        print("\n" + "=" * 60)
        print("  PART 5: API DOCUMENTATION")
        print("=" * 60)

        api_page = context.new_page()
        api_page.set_viewport_size({"width": 1440, "height": 900})
        print("  Navigating to API docs...")
        api_page.goto("https://www.dzine.ai/api/",
                      wait_until="domcontentloaded", timeout=30000)
        api_page.wait_for_timeout(5000)
        close_all_dialogs(api_page)
        ss(api_page, "api_page")

        # Map API page content
        api_items = api_page.evaluate("""() => {
            const items = [];
            const seen = new Set();
            for (const el of document.querySelectorAll('h1, h2, h3, h4, p, li, a, button')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text && text.length > 2 && text.length < 100 && rect.width > 20 &&
                    rect.height > 5 && !seen.has(text)) {
                    seen.add(text);
                    items.push({text: text.substring(0, 80), tag: el.tagName,
                               x: Math.round(rect.x), y: Math.round(rect.y)});
                }
            }
            return items.sort((a, b) => a.y - b.y).slice(0, 40);
        }""")
        print(f"\n  API page ({len(api_items)} items):")
        for item in api_items:
            print(f"    ({item['x']},{item['y']}) <{item['tag']}> {item['text']}")

        api_page.close()

        # ================================================================
        # PART 6: EXPLORE PRICING
        # ================================================================
        print("\n" + "=" * 60)
        print("  PART 6: PRICING PAGE")
        print("=" * 60)

        pricing_page = context.new_page()
        pricing_page.set_viewport_size({"width": 1440, "height": 900})
        print("  Navigating to pricing...")
        pricing_page.goto("https://www.dzine.ai/pricing/",
                          wait_until="domcontentloaded", timeout=30000)
        pricing_page.wait_for_timeout(5000)
        close_all_dialogs(pricing_page)
        ss(pricing_page, "pricing_page")

        # Map pricing plans
        pricing = pricing_page.evaluate("""() => {
            const items = [];
            const seen = new Set();
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text && text.length > 2 && text.length < 80 && rect.width > 20 &&
                    rect.height > 5 && el.children.length < 4 && !seen.has(text)) {
                    seen.add(text);
                    items.push({text, tag: el.tagName,
                               x: Math.round(rect.x), y: Math.round(rect.y),
                               w: Math.round(rect.width)});
                }
            }
            return items.sort((a, b) => a.y - b.y).slice(0, 60);
        }""")
        print(f"\n  Pricing page ({len(pricing)} items):")
        for item in pricing:
            print(f"    ({item['x']},{item['y']}) w={item['w']} <{item['tag']}> {item['text']}")

        pricing_page.close()

        # ================================================================
        # PART 7: BACK TO CANVAS — CHECK FINAL CC RESULTS
        # ================================================================
        print("\n" + "=" * 60)
        print("  PART 7: FINAL CC RESULTS CHECK")
        print("=" * 60)

        # Switch back to canvas page
        page.bring_to_front()
        page.wait_for_timeout(1000)

        # Click Results tab
        page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text === 'Results' && rect.y < 80 && rect.x > 550) {
                    el.click();
                    return;
                }
            }
        }""")
        page.wait_for_timeout(1000)

        # Get all CC result images
        cc_results = page.evaluate("""() => {
            const results = [];
            const imgs = document.querySelectorAll('img');
            for (const img of imgs) {
                const r = img.getBoundingClientRect();
                const src = img.src || '';
                if (r.x > 550 && r.y > 60 && r.width > 30 && r.height > 30 &&
                    (src.includes('character') || src.includes('consistent'))) {
                    results.push({
                        src: src.substring(0, 150),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height)
                    });
                }
            }
            return results;
        }""")
        print(f"\n  CC result images ({len(cc_results)}):")
        for img in cc_results:
            print(f"    ({img['x']},{img['y']}) {img['w']}x{img['h']}")
            print(f"      {img['src']}")

        # Check progress again
        progress = page.evaluate("""() => {
            const items = [];
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text.match(/^\\d{1,3}%$/) && rect.x > 550) {
                    items.push({pct: text, y: Math.round(rect.y)});
                }
            }
            return items;
        }""")
        if progress:
            print(f"\n  Still generating: {progress}")
        else:
            print("\n  All generations complete!")

        ss(page, "final_results")

        # ================================================================
        # CREDITS
        # ================================================================
        credits = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                if (text === 'Unlimited' && el.getBoundingClientRect().y < 30) return 'Unlimited';
            }
            return 'unknown';
        }""")
        print(f"\n  Credits: {credits}")

        ss(page, "final")
        print("\n\n===== PHASE 20 COMPLETE =====")

    except Exception as exc:
        print(f"\nFATAL: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        ss(page, "error")
    finally:
        if should_close:
            context.close()
        pw.stop()


if __name__ == "__main__":
    main()
