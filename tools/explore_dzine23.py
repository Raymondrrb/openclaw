"""Phase 23: Debug CC generation + find upload mechanism.

Goals:
1. Check CC panel state — is a generation actually pending?
2. Look at the CC generate button state (enabled/disabled/text)
3. Check if Upload sidebar triggers a file chooser
4. Try intercepting file chooser in Img2Img panel
5. Check Img2Img panel for drag-and-drop zones
6. Look at screenshots to understand what's actually visible
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
    path = SS_DIR / f"{name}.png"
    page.screenshot(path=str(path))
    print(f"  SS: {name}", flush=True)

def close_all_dialogs(page):
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


def main():
    print("Connecting...", flush=True)
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:18800", timeout=15000)
    ctx = browser.contexts[0]
    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)
    close_all_dialogs(page)

    print("\n" + "=" * 60, flush=True)
    print("  PART 1: CC PANEL STATE DEBUG", flush=True)
    print("=" * 60, flush=True)

    # Open Character panel
    page.mouse.click(40, 306)
    page.wait_for_timeout(2000)
    close_all_dialogs(page)

    ss(page, "P23_01_character_panel")

    # Map everything in the panel
    panel = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.x > 60 && r.x < 400 && r.y > 50 && r.y < 900
                && r.width > 15 && r.width < 350 && text
                && text.length > 0 && text.length < 80) {
                items.push({
                    text: text.substring(0, 60),
                    tag: el.tagName,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    disabled: el.disabled || false,
                    cls: (el.className || '').substring(0, 30),
                });
            }
        }
        const seen = new Set();
        return items.filter(i => {
            const key = i.text + '|' + Math.round(i.y / 3);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort((a, b) => a.y - b.y);
    }""")

    print(f"\n  CC panel elements ({len(panel)}):", flush=True)
    for el in panel[:40]:
        dis = " DISABLED" if el.get('disabled') else ""
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} "
              f"<{el['tag']}>{dis} '{el['text']}'", flush=True)

    print("\n" + "=" * 60, flush=True)
    print("  PART 2: TRY CC GENERATION FLOW (detailed)", flush=True)
    print("=" * 60, flush=True)

    # Step 2a: Check if "Generate Images" button exists and click it
    gen_images_btn = page.evaluate("""() => {
        const btns = [];
        for (const btn of document.querySelectorAll('button')) {
            const text = (btn.innerText || '').trim();
            const r = btn.getBoundingClientRect();
            if (text.includes('Generate') && r.x > 60 && r.x < 400) {
                btns.push({
                    text: text.substring(0, 60),
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                    disabled: btn.disabled,
                });
            }
        }
        return btns;
    }""")

    print(f"\n  Generate buttons in CC panel:", flush=True)
    for btn in gen_images_btn:
        print(f"    ({btn['x']},{btn['y']}) w={btn['w']} disabled={btn['disabled']} '{btn['text']}'", flush=True)

    # Click "Generate Images" to open the CC generation sub-panel
    clicked = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            const text = (btn.innerText || '').trim();
            if (text.includes('Generate Images') && text.includes('With your character')) {
                btn.click(); return 'gen_images';
            }
        }
        // If not found, look for any "Generate" button
        for (const btn of document.querySelectorAll('button')) {
            const text = (btn.innerText || '').trim();
            if (text.includes('Generate') && !btn.disabled) {
                return 'found: ' + text.substring(0, 40);
            }
        }
        return 'not_found';
    }""")
    print(f"\n  Click result: {clicked}", flush=True)
    page.wait_for_timeout(2000)

    ss(page, "P23_02_after_gen_images_click")

    # Check what's visible now
    panel2 = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.x > 60 && r.x < 400 && r.y > 50 && r.y < 900
                && r.width > 15 && r.width < 350 && text
                && text.length > 0 && text.length < 60
                && !text.includes('\\n')) {
                items.push({
                    text: text,
                    tag: el.tagName,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                });
            }
        }
        const seen = new Set();
        return items.filter(i => {
            const key = i.text + '|' + Math.round(i.y / 3);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort((a, b) => a.y - b.y);
    }""")

    print(f"\n  After 'Generate Images' click ({len(panel2)}):", flush=True)
    for el in panel2[:40]:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'", flush=True)

    # Select Ray
    ray = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            const text = (el.innerText || '').trim();
            if (text === 'Ray' && el.tagName === 'BUTTON') {
                el.click(); return true;
            }
        }
        return false;
    }""")
    print(f"\n  Ray selected: {ray}", flush=True)
    page.wait_for_timeout(2000)

    ss(page, "P23_03_ray_selected")

    # Check textarea / prompt area
    textareas = page.evaluate("""() => {
        const areas = [];
        for (const el of document.querySelectorAll('textarea, [contenteditable="true"]')) {
            const r = el.getBoundingClientRect();
            areas.push({
                tag: el.tagName,
                x: Math.round(r.x),
                y: Math.round(r.y),
                w: Math.round(r.width),
                h: Math.round(r.height),
                placeholder: el.placeholder || '',
                value: (el.value || el.innerText || '').substring(0, 50),
                contenteditable: el.contentEditable,
            });
        }
        return areas;
    }""")

    print(f"\n  Text areas ({len(textareas)}):", flush=True)
    for ta in textareas:
        print(f"    ({ta['x']},{ta['y']}) {ta['w']}x{ta['h']} <{ta['tag']}> "
              f"placeholder='{ta['placeholder'][:30]}' value='{ta['value']}'", flush=True)

    # Type a simple scene
    if textareas:
        ta = textareas[0]
        page.mouse.click(ta['x'] + 10, ta['y'] + 10)
        page.keyboard.press("Meta+a")
        page.wait_for_timeout(200)
        page.keyboard.type("Ray giving thumbs up, modern studio, warm lighting", delay=5)
        page.wait_for_timeout(500)

    # Set canvas ratio
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'canvas' &&
                el.getBoundingClientRect().x > 60 && el.getBoundingClientRect().y > 400) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(500)

    ss(page, "P23_04_ready_to_generate")

    # Find and describe the Generate button precisely
    gen_btn_info = page.evaluate("""() => {
        const btns = [];
        for (const btn of document.querySelectorAll('button')) {
            const text = (btn.innerText || '').trim();
            const r = btn.getBoundingClientRect();
            if (r.x > 60 && r.x < 350 && r.y > 300 && r.y < 800
                && text.includes('Generate') && r.width > 50) {
                btns.push({
                    text: text,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    disabled: btn.disabled,
                    cls: (btn.className || '').substring(0, 40),
                });
            }
        }
        return btns;
    }""")

    print(f"\n  Generate buttons ready to click:", flush=True)
    for btn in gen_btn_info:
        print(f"    ({btn['x']},{btn['y']}) {btn['w']}x{btn['h']} "
              f"disabled={btn['disabled']} cls={btn['cls']} '{btn['text']}'", flush=True)

    # Count images before
    before_count = page.evaluate("""() => {
        let count = 0;
        for (const img of document.querySelectorAll('img')) {
            if ((img.src || '').includes('characterchatfal')) count++;
        }
        return count;
    }""")
    print(f"\n  CC images before generation: {before_count}", flush=True)

    # Click Generate
    gen_clicked = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            const text = (btn.innerText || '').trim();
            const r = btn.getBoundingClientRect();
            if (text.includes('Generate') && !btn.disabled
                && r.x > 60 && r.x < 350 && r.y > 300) {
                btn.click();
                return {text: text, x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"  Clicked: {gen_clicked}", flush=True)

    if gen_clicked:
        page.wait_for_timeout(2000)
        ss(page, "P23_05_after_generate")

        # Check for any toast/notification
        toasts = page.evaluate("""() => {
            const items = [];
            for (const el of document.querySelectorAll('[class*="toast"], [class*="Toast"], [class*="notification"], [class*="Notification"], [class*="message"], [class*="Message"], [role="alert"]')) {
                const text = (el.innerText || '').trim();
                if (text && text.length < 100) {
                    items.push(text);
                }
            }
            return items;
        }""")
        if toasts:
            print(f"  Toasts/Notifications: {toasts}", flush=True)

        # Check for "Starting a task" or similar
        task_msg = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                if (text.includes('Starting') || text.includes('Generating') ||
                    text.includes('Queue') || text.includes('task')) {
                    const r = el.getBoundingClientRect();
                    if (r.width > 0 && r.width < 400 && text.length < 60) {
                        return text;
                    }
                }
            }
            return null;
        }""")
        if task_msg:
            print(f"  Task message: {task_msg}", flush=True)

        # Monitor for 60 seconds
        print("\n  Monitoring for 60s...", flush=True)
        start = time.monotonic()
        for i in range(20):
            page.wait_for_timeout(3000)
            elapsed = time.monotonic() - start

            after = page.evaluate("""() => {
                let count = 0;
                for (const img of document.querySelectorAll('img')) {
                    if ((img.src || '').includes('characterchatfal')) count++;
                }
                return count;
            }""")

            # Check Results panel scrolled to top for new items
            new_results = page.evaluate("""() => {
                const items = [];
                for (const el of document.querySelectorAll('*')) {
                    const text = (el.innerText || '').trim();
                    const r = el.getBoundingClientRect();
                    if (r.x > 1050 && r.x < 1400 && r.y > 60 && r.y < 200
                        && text && text.length < 40 && r.width > 50) {
                        items.push({text: text, y: Math.round(r.y)});
                    }
                }
                const seen = new Set();
                return items.filter(i => {
                    if (seen.has(i.text)) return false;
                    seen.add(i.text);
                    return true;
                });
            }""")

            progress = page.evaluate("""() => {
                for (const el of document.querySelectorAll('*')) {
                    const t = (el.innerText || '').trim();
                    if (/^\\d{1,3}%$/.test(t)) {
                        const r = el.getBoundingClientRect();
                        if (r.width > 0 && r.width < 100 && r.x > 1050) {
                            return t;
                        }
                    }
                }
                return 'none';
            }""")

            print(f"    [{elapsed:.0f}s] cc_images={after} progress={progress} "
                  f"top_results={[r['text'] for r in new_results[:3]]}", flush=True)

            if after > before_count:
                print(f"\n  NEW IMAGE! {after} vs {before_count}", flush=True)
                ss(page, "P23_06_new_image")
                break

            if elapsed > 60:
                ss(page, "P23_06_timeout")
                break

    print("\n" + "=" * 60, flush=True)
    print("  PART 3: EXPLORE UPLOAD MECHANISM", flush=True)
    print("=" * 60, flush=True)

    # Click the Upload sidebar
    page.mouse.click(40, 81)
    page.wait_for_timeout(1500)
    close_all_dialogs(page)

    ss(page, "P23_07_upload_sidebar")

    # Check what panel opened — look at y > 50 x > 60
    upload_panel = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.x > 60 && r.x < 350 && r.y > 50 && r.y < 100
                && r.width > 100 && text && text.length > 2 && text.length < 40
                && !text.includes('\\n')) {
                return text;
            }
        }
        return '(none)';
    }""")
    print(f"\n  Panel after Upload click: '{upload_panel}'", flush=True)

    # The Upload button might not open a panel — it might open a file dialog
    # Let's check if it opens a file chooser
    # First, set up a file chooser listener
    print("\n  Testing file chooser on Upload sidebar...", flush=True)

    # Try with page.expect_file_chooser
    try:
        with page.expect_file_chooser(timeout=3000) as fc:
            page.mouse.click(40, 81)
        print(f"  File chooser opened! Multiple: {fc.value.is_multiple}", flush=True)
    except Exception:
        print("  No file chooser from Upload sidebar click", flush=True)

    # Try the hidden upload-image button
    print("\n  Testing hidden 'upload-image' button...", flush=True)
    try:
        with page.expect_file_chooser(timeout=3000) as fc:
            page.evaluate("""() => {
                const btn = document.querySelector('button.new-file.upload-image');
                if (btn) { btn.click(); return true; }
                return false;
            }""")
        print(f"  File chooser opened from hidden button! Multiple: {fc.value.is_multiple}", flush=True)
    except Exception:
        print("  No file chooser from hidden upload button", flush=True)

    # Try Img2Img panel — check if clicking the panel area opens a file chooser
    page.mouse.click(40, 252)  # Img2Img
    page.wait_for_timeout(1500)

    print("\n  Testing Img2Img panel for upload area...", flush=True)

    # Look for any visible upload prompt in the panel area
    img2img_upload = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const text = (el.innerText || '').trim().toLowerCase();
            const r = el.getBoundingClientRect();
            if (r.x > 60 && r.x < 400 && r.y > 50 && r.y < 300
                && (text.includes('upload') || text.includes('drop') ||
                    text.includes('drag') || text.includes('image') ||
                    text.includes('click') || text.includes('browse'))
                && text.length < 50) {
                items.push({
                    text: (el.innerText || '').trim(),
                    tag: el.tagName,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                });
            }
        }
        const seen = new Set();
        return items.filter(i => {
            const key = i.text + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });
    }""")

    print(f"  Upload-related elements in Img2Img ({len(img2img_upload)}):", flush=True)
    for el in img2img_upload[:10]:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'", flush=True)

    # The Img2Img textarea area — check if there's an image drop zone above it
    # The panel shows prompt at y=149, so there might be an image upload area above
    img2img_top = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.x > 80 && r.x < 350 && r.y > 60 && r.y < 160
                && r.width > 50 && r.height > 20 && text.length < 40) {
                items.push({
                    text: text || '(empty)',
                    tag: el.tagName,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    cls: (el.className || '').substring(0, 40),
                });
            }
        }
        return items;
    }""")

    print(f"\n  Img2Img top area ({len(img2img_top)}):", flush=True)
    for el in img2img_top[:15]:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> "
              f"cls='{el['cls']}' '{el['text']}'", flush=True)

    # Check if Img2Img has a Nano Banana Pro style selector that could be clicked
    # to reveal an upload area
    page.mouse.click(144, 110)  # Click on Nano Banana Pro area
    page.wait_for_timeout(1000)

    ss(page, "P23_08_nano_banana_clicked")

    # Check what opened
    style_menu = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.width > 100 && r.y > 50 && r.y < 600
                && text && text.length < 50 && text.length > 2
                && !text.includes('\\n')
                && r.x > 60 && r.x < 500) {
                items.push({
                    text: text,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                });
            }
        }
        const seen = new Set();
        return items.filter(i => {
            const key = i.text;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort((a, b) => a.y - b.y);
    }""")

    print(f"\n  After clicking Nano Banana ({len(style_menu)}):", flush=True)
    for el in style_menu[:20]:
        print(f"    ({el['x']},{el['y']}) w={el['w']} '{el['text']}'", flush=True)

    # Close any style menu
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    ss(page, "P23_09_final")
    print(f"\n\n===== PHASE 23 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
