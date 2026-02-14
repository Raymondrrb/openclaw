"""Phase 73: Quick check for remaining Expression Edit Custom sliders below Pursing.
Also check if scrolling the left panel reveals Head Adjustments.
Then explore remaining unexplored features: AI Video, Motion Control, Video Editor, Instant Storyboard.
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


def main():
    print("Connecting...", flush=True)
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:18800", timeout=15000)
    ctx = browser.contexts[0]
    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
    print("  Waiting 12s for full canvas load...", flush=True)
    page.wait_for_timeout(12000)
    close_dialogs(page)

    # ============================================================
    #  PART 1: EXPRESSION EDIT — SCROLL CUSTOM FOR HEAD SLIDERS
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: EXPRESSION EDIT — CHECK FOR HEAD ADJUSTMENTS", flush=True)
    print("=" * 60, flush=True)

    # Click face on canvas to select image layer
    page.mouse.click(550, 350)
    page.wait_for_timeout(1000)

    # Click Expression in layer-tools toolbar
    expr = page.evaluate("""() => {
        var bar = document.querySelector('.layer-tools');
        if (!bar) return null;
        for (const btn of bar.querySelectorAll('*')) {
            if ((btn.innerText || '').trim() === 'Expression') {
                btn.click();
                return true;
            }
        }
        return null;
    }""")
    print(f"  Expression clicked: {expr}", flush=True)
    page.wait_for_timeout(5000)
    close_dialogs(page)

    # Verify Expression Edit is open
    is_open = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Expression Edit'
                && el.offsetParent !== null
                && el.getBoundingClientRect().height < 40) return true;
        }
        return false;
    }""")
    print(f"  Expression Edit open: {is_open}", flush=True)

    if is_open:
        # Get ALL text content in the left panel by dumping innerHTML
        all_labels = page.evaluate("""() => {
            var labels = [];
            // Find all slider/section labels in the expression panel
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                // Panel is at x=0-200, but check for any panel content
                if (r.x >= 0 && r.x <= 200 && r.width > 30 && r.height >= 10
                    && r.height <= 25 && text.length > 1 && text.length < 30
                    && text.indexOf('\\n') === -1
                    && el.children.length === 0) {  // leaf nodes only
                    labels.push({
                        text: text,
                        y: Math.round(r.y),
                        x: Math.round(r.x),
                        visible: r.y > 0 && r.y < 2000,  // visible in DOM even if off-screen
                    });
                }
            }
            var seen = new Set();
            return labels.filter(function(l) {
                if (seen.has(l.text)) return false;
                seen.add(l.text);
                return true;
            }).sort(function(a,b) { return a.y - b.y; });
        }""")
        print(f"\n  All unique leaf text labels in panel ({len(all_labels)}):", flush=True)
        for l in all_labels:
            print(f"    y={l['y']} x={l['x']} vis={l['visible']} '{l['text']}'", flush=True)

        # Also check if there's a scrollable container we missed
        scroll_info = page.evaluate("""() => {
            var results = [];
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                if (r.x >= 0 && r.x <= 30 && r.width > 150 && r.width < 300
                    && r.height > 200) {
                    if (el.scrollHeight > el.clientHeight + 5
                        || el.style.overflow === 'auto'
                        || el.style.overflow === 'scroll'
                        || el.style.overflowY === 'auto'
                        || el.style.overflowY === 'scroll') {
                        var cs = window.getComputedStyle(el);
                        results.push({
                            tag: el.tagName,
                            classes: (el.className || '').toString().substring(0, 40),
                            scrollHeight: el.scrollHeight,
                            clientHeight: el.clientHeight,
                            overflow: cs.overflow,
                            overflowY: cs.overflowY,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                        });
                    }
                }
            }
            return results;
        }""")
        print(f"\n  Scrollable containers ({len(scroll_info)}):", flush=True)
        for s in scroll_info:
            print(f"    ({s['x']},{s['y']}) {s['w']}x{s['h']} scrollH={s['scrollHeight']} "
                  f"clientH={s['clientHeight']} overflow={s['overflow']} overflowY={s['overflowY']} "
                  f"<{s['tag']}> c='{s['classes'][:30]}'", flush=True)

        # Try scrolling with JS if we find a container
        if scroll_info:
            for s in scroll_info:
                page.evaluate(f"""() => {{
                    var els = document.querySelectorAll('{s['tag']}.{s['classes'].split(' ')[0]}');
                    for (var el of els) {{
                        var r = el.getBoundingClientRect();
                        if (Math.abs(r.x - {s['x']}) < 5 && Math.abs(r.y - {s['y']}) < 5) {{
                            el.scrollTop = el.scrollHeight;
                            return true;
                        }}
                    }}
                    return false;
                }}""")
                page.wait_for_timeout(500)

            # Re-read labels after scrolling
            after_scroll = page.evaluate("""() => {
                var labels = [];
                for (const el of document.querySelectorAll('*')) {
                    var r = el.getBoundingClientRect();
                    var text = (el.innerText || '').trim();
                    if (r.x >= 0 && r.x <= 200 && r.width > 30 && r.height >= 10
                        && r.height <= 25 && text.length > 1 && text.length < 30
                        && text.indexOf('\\n') === -1
                        && el.children.length === 0) {
                        labels.push({text: text, y: Math.round(r.y)});
                    }
                }
                var seen = new Set();
                return labels.filter(function(l) {
                    if (seen.has(l.text)) return false;
                    seen.add(l.text);
                    return true;
                }).sort(function(a,b) { return a.y - b.y; });
            }""")
            print(f"\n  After scroll to bottom ({len(after_scroll)}):", flush=True)
            for l in after_scroll:
                print(f"    y={l['y']} '{l['text']}'", flush=True)

            ss(page, "P73_01_custom_scrolled_bottom")

        # Cancel out
        page.evaluate("""() => {
            for (const el of document.querySelectorAll('button')) {
                if ((el.innerText || '').trim() === 'Cancel'
                    && el.getBoundingClientRect().y < 50
                    && el.getBoundingClientRect().width > 0) {
                    el.click(); return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(2000)

    # ============================================================
    #  PART 2: SIDEBAR TOOLS — AI VIDEO, MOTION CONTROL, etc.
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: SIDEBAR — AI VIDEO", flush=True)
    print("=" * 60, flush=True)

    # Click AI Video in left sidebar
    ai_video = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'AI Video' && r.x < 60 && r.y > 100) {
                el.click();
                return {x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"  AI Video clicked: {ai_video}", flush=True)
    page.wait_for_timeout(2000)
    close_dialogs(page)
    ss(page, "P73_02_ai_video")

    # Dump AI Video panel
    av_items = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x >= 60 && r.x <= 350 && r.y >= 40 && r.y <= 900
                && r.width > 15 && r.height > 10 && r.width < 350) {
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 60 && text.indexOf('\\n') === -1) {
                    items.push({
                        tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 45),
                        classes: (el.className || '').toString().substring(0, 30),
                    });
                }
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.text.substring(0, 15) + '|' + i.x + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y; }).slice(0, 40);
    }""")
    print(f"  AI Video panel ({len(av_items)}):", flush=True)
    for el in av_items:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:22]}' '{el['text'][:40]}'", flush=True)

    # ============================================================
    #  PART 3: MOTION CONTROL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: SIDEBAR — MOTION CONTROL", flush=True)
    print("=" * 60, flush=True)

    mc = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Motion Control' && r.x < 60 && r.y > 100) {
                el.click();
                return {x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"  Motion Control clicked: {mc}", flush=True)
    page.wait_for_timeout(2000)
    close_dialogs(page)
    ss(page, "P73_03_motion_control")

    mc_items = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x >= 60 && r.x <= 350 && r.y >= 40 && r.y <= 900
                && r.width > 15 && r.height > 10 && r.width < 350) {
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 60 && text.indexOf('\\n') === -1) {
                    items.push({
                        tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 45),
                        classes: (el.className || '').toString().substring(0, 30),
                    });
                }
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.text.substring(0, 15) + '|' + i.x + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y; }).slice(0, 40);
    }""")
    print(f"  Motion Control panel ({len(mc_items)}):", flush=True)
    for el in mc_items:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:22]}' '{el['text'][:40]}'", flush=True)

    # ============================================================
    #  PART 4: VIDEO EDITOR
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: SIDEBAR — VIDEO EDITOR", flush=True)
    print("=" * 60, flush=True)

    ve = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Video Editor' && r.x < 60 && r.y > 100) {
                el.click();
                return {x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"  Video Editor clicked: {ve}", flush=True)
    page.wait_for_timeout(2000)
    close_dialogs(page)
    ss(page, "P73_04_video_editor")

    ve_items = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x >= 60 && r.x <= 350 && r.y >= 40 && r.y <= 900
                && r.width > 15 && r.height > 10 && r.width < 350) {
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 60 && text.indexOf('\\n') === -1) {
                    items.push({
                        tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 45),
                        classes: (el.className || '').toString().substring(0, 30),
                    });
                }
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.text.substring(0, 15) + '|' + i.x + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y; }).slice(0, 40);
    }""")
    print(f"  Video Editor panel ({len(ve_items)}):", flush=True)
    for el in ve_items:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:22]}' '{el['text'][:40]}'", flush=True)

    # ============================================================
    #  PART 5: INSTANT STORYBOARD
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: SIDEBAR — INSTANT STORYBOARD", flush=True)
    print("=" * 60, flush=True)

    isb = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if ((text === 'Instant Storyboard' || text === 'Instant\nStoryboard')
                && r.x < 60 && r.y > 100) {
                el.click();
                return {x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        // Broader — maybe text wraps
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.includes('Storyboard') && r.x < 60 && r.y > 300) {
                el.click();
                return {x: Math.round(r.x), y: Math.round(r.y), note: 'broad'};
            }
        }
        return null;
    }""")
    print(f"  Instant Storyboard clicked: {isb}", flush=True)
    page.wait_for_timeout(2000)
    close_dialogs(page)
    ss(page, "P73_05_instant_storyboard")

    isb_items = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x >= 60 && r.x <= 400 && r.y >= 40 && r.y <= 900
                && r.width > 15 && r.height > 10 && r.width < 400) {
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 60 && text.indexOf('\\n') === -1) {
                    items.push({
                        tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 50),
                        classes: (el.className || '').toString().substring(0, 30),
                    });
                }
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.text.substring(0, 15) + '|' + i.x + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y; }).slice(0, 40);
    }""")
    print(f"  Instant Storyboard panel ({len(isb_items)}):", flush=True)
    for el in isb_items:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:22]}' '{el['text'][:45]}'", flush=True)

    # ============================================================
    #  PART 6: ENHANCE & UPSCALE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 6: SIDEBAR — ENHANCE & UPSCALE", flush=True)
    print("=" * 60, flush=True)

    enh = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if ((text.includes('Enhance') && text.includes('Upscale'))
                && r.x < 60 && r.y > 100) {
                el.click();
                return {x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"  Enhance & Upscale clicked: {enh}", flush=True)
    page.wait_for_timeout(2000)
    close_dialogs(page)
    ss(page, "P73_06_enhance_upscale")

    enh_items = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x >= 60 && r.x <= 350 && r.y >= 40 && r.y <= 900
                && r.width > 15 && r.height > 10 && r.width < 350) {
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 60 && text.indexOf('\\n') === -1) {
                    items.push({
                        tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 45),
                        classes: (el.className || '').toString().substring(0, 30),
                    });
                }
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.text.substring(0, 15) + '|' + i.x + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y; }).slice(0, 40);
    }""")
    print(f"  Enhance & Upscale panel ({len(enh_items)}):", flush=True)
    for el in enh_items:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:22]}' '{el['text'][:40]}'", flush=True)

    print(f"\n\n===== PHASE 73 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
