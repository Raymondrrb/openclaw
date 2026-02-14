"""Phase 21: Test image download from static.dzine.ai URLs + explore
Enhance & Upscale and Image Editor tools.

Goals:
1. Download a CC result image via its static URL → verify it works
2. Open Enhance & Upscale on a result → map the UI
3. Open Image Editor on a result → map the UI
4. Test BG Remove on a result → map the UI
5. Check file input elements for reference image upload
"""

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.lib.brave_profile import connect_or_launch

CANVAS_URL = "https://www.dzine.ai/canvas?id=19797967"
SS_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dzine_explore"
SS_DIR.mkdir(parents=True, exist_ok=True)

def ss(page, name):
    path = SS_DIR / f"{name}.png"
    page.screenshot(path=str(path))
    print(f"  SS: {name}")
    return path

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

def get_result_images(page):
    return page.evaluate("""() => {
        const results = [];
        for (const img of document.querySelectorAll('img')) {
            const src = img.src || '';
            if (src.includes('static.dzine.ai/stylar_product/p/')) {
                const r = img.getBoundingClientRect();
                results.push({
                    src: src,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                });
            }
        }
        return results;
    }""")

def get_all_buttons(page, y_min=0, y_max=9999):
    return page.evaluate(f"""() => {{
        const btns = [];
        for (const btn of document.querySelectorAll('button')) {{
            const r = btn.getBoundingClientRect();
            const text = (btn.innerText || '').trim().substring(0, 50);
            if (r.width > 0 && r.y >= {y_min} && r.y <= {y_max} && text) {{
                btns.push({{
                    text: text,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    disabled: btn.disabled,
                }});
            }}
        }}
        return btns;
    }}""")

def get_file_inputs(page):
    return page.evaluate("""() => {
        const inputs = [];
        for (const inp of document.querySelectorAll('input[type="file"]')) {
            const r = inp.getBoundingClientRect();
            inputs.push({
                accept: inp.accept || '',
                multiple: inp.multiple,
                x: Math.round(r.x),
                y: Math.round(r.y),
                w: Math.round(r.width),
                h: Math.round(r.height),
                visible: r.width > 0 && r.height > 0,
                id: inp.id || '',
                name: inp.name || '',
            });
        }
        return inputs;
    }""")


def main():
    print("Connecting...")
    browser, context, should_close, pw = connect_or_launch(headless=False)

    page = context.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    try:
        # Navigate to canvas
        page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        close_all_dialogs(page)

        print("\n" + "=" * 60)
        print("  PART 1: DOWNLOAD TEST")
        print("=" * 60)

        # Get all result images
        images = get_result_images(page)
        print(f"\n  Total result images: {len(images)}")

        # Find CC images specifically
        cc_images = [i for i in images if "characterchatfal" in i["src"]]
        print(f"  CC images: {len(cc_images)}")

        if cc_images:
            test_url = cc_images[0]["src"]
            print(f"\n  Testing download from: {test_url[:80]}...")

            dest = SS_DIR / "test_download.webp"
            try:
                req = urllib.request.Request(test_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = resp.read()
                dest.write_bytes(data)
                print(f"  Downloaded: {len(data)} bytes → {dest}")
                print(f"  Content type: webp")
                print(f"  File size OK: {len(data) > 1024}")
            except Exception as exc:
                print(f"  Download FAILED: {exc}")

            # Also test with a txt2img image
            txt2img = [i for i in images if "gemini2text2image" in i["src"] or "faltxt2img" in i["src"]]
            if txt2img:
                test_url2 = txt2img[0]["src"]
                dest2 = SS_DIR / "test_download_txt2img.webp"
                try:
                    req2 = urllib.request.Request(test_url2, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req2, timeout=30) as resp2:
                        data2 = resp2.read()
                    dest2.write_bytes(data2)
                    print(f"\n  Txt2Img download: {len(data2)} bytes → {dest2}")
                except Exception as exc2:
                    print(f"\n  Txt2Img download FAILED: {exc2}")

        print("\n" + "=" * 60)
        print("  PART 2: FILE INPUT ELEMENTS (for reference upload)")
        print("=" * 60)

        file_inputs = get_file_inputs(page)
        print(f"\n  File inputs found: {len(file_inputs)}")
        for fi in file_inputs:
            print(f"    accept={fi['accept']} multiple={fi['multiple']} "
                  f"visible={fi['visible']} id={fi['id']} ({fi['x']},{fi['y']})")

        # Click Txt2Img to check for upload area
        page.mouse.click(40, 197)  # Txt2Img sidebar
        page.wait_for_timeout(2000)
        close_all_dialogs(page)

        file_inputs_txt = get_file_inputs(page)
        print(f"\n  File inputs after Txt2Img panel: {len(file_inputs_txt)}")
        for fi in file_inputs_txt:
            print(f"    accept={fi['accept']} multiple={fi['multiple']} "
                  f"visible={fi['visible']} id={fi['id']} ({fi['x']},{fi['y']})")

        ss(page, "P21_01_txt2img_panel")

        # Click Img2Img to check its upload
        page.mouse.click(40, 252)  # Img2Img sidebar
        page.wait_for_timeout(2000)
        close_all_dialogs(page)

        file_inputs_i2i = get_file_inputs(page)
        print(f"\n  File inputs after Img2Img panel: {len(file_inputs_i2i)}")
        for fi in file_inputs_i2i:
            print(f"    accept={fi['accept']} multiple={fi['multiple']} "
                  f"visible={fi['visible']} id={fi['id']} ({fi['x']},{fi['y']})")

        ss(page, "P21_02_img2img_panel")

        print("\n" + "=" * 60)
        print("  PART 3: ENHANCE & UPSCALE TOOL")
        print("=" * 60)

        # Click on a result image first, then use Enhance & Upscale action
        # First scroll results to find a CC image
        page.mouse.click(40, 306)  # Character sidebar (has Results panel)
        page.wait_for_timeout(1500)
        close_all_dialogs(page)

        # Back to results: look for Enhance & Upscale in sidebar
        page.mouse.click(40, 627)  # Enhance & Upscale sidebar
        page.wait_for_timeout(2000)
        close_all_dialogs(page)

        ss(page, "P21_03_enhance_panel")

        # Map the Enhance panel UI
        enhance_elements = page.evaluate("""() => {
            const items = [];
            const panel = document.querySelector('.ant-layout-sider') ||
                          document.querySelector('[class*="sider"]');
            for (const el of document.querySelectorAll('*')) {
                const r = el.getBoundingClientRect();
                const text = (el.innerText || '').trim().substring(0, 60);
                if (r.x > 60 && r.x < 400 && r.y > 50 && r.y < 800
                    && r.width > 20 && r.width < 350 && text
                    && !text.includes('\\n') && text.length > 1 && text.length < 40) {
                    items.push({
                        text: text,
                        tag: el.tagName,
                        x: Math.round(r.x),
                        y: Math.round(r.y),
                        w: Math.round(r.width),
                    });
                }
            }
            // Deduplicate by text+y
            const seen = new Set();
            return items.filter(i => {
                const key = i.text + '|' + i.y;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            });
        }""")

        print(f"\n  Enhance panel elements ({len(enhance_elements)}):")
        for el in enhance_elements[:30]:
            print(f"    ({el['x']},{el['y']}) w={el['w']} <{el['tag']}> {el['text']}")

        # Check for upload area in enhance
        file_inputs_enh = get_file_inputs(page)
        print(f"\n  File inputs in Enhance: {len(file_inputs_enh)}")
        for fi in file_inputs_enh:
            print(f"    accept={fi['accept']} visible={fi['visible']}")

        print("\n" + "=" * 60)
        print("  PART 4: IMAGE EDITOR TOOL")
        print("=" * 60)

        page.mouse.click(40, 698)  # Image Editor sidebar
        page.wait_for_timeout(2000)
        close_all_dialogs(page)

        ss(page, "P21_04_image_editor_panel")

        editor_elements = page.evaluate("""() => {
            const items = [];
            for (const el of document.querySelectorAll('*')) {
                const r = el.getBoundingClientRect();
                const text = (el.innerText || '').trim().substring(0, 60);
                if (r.x > 60 && r.x < 400 && r.y > 50 && r.y < 800
                    && r.width > 20 && r.width < 350 && text
                    && !text.includes('\\n') && text.length > 1 && text.length < 40) {
                    items.push({
                        text: text,
                        tag: el.tagName,
                        x: Math.round(r.x),
                        y: Math.round(r.y),
                        w: Math.round(r.width),
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

        print(f"\n  Image Editor elements ({len(editor_elements)}):")
        for el in editor_elements[:30]:
            print(f"    ({el['x']},{el['y']}) w={el['w']} <{el['tag']}> {el['text']}")

        print("\n" + "=" * 60)
        print("  PART 5: TOP BAR TOOLS (with canvas layer)")
        print("=" * 60)

        # Check what's in the top bar
        top_bar = page.evaluate("""() => {
            const items = [];
            for (const el of document.querySelectorAll('*')) {
                const r = el.getBoundingClientRect();
                const text = (el.innerText || '').trim();
                if (r.y >= 0 && r.y < 60 && r.x > 60 && r.x < 1200
                    && r.width > 20 && r.width < 200 && text
                    && text.length > 1 && text.length < 30
                    && !text.includes('\\n')) {
                    items.push({
                        text: text,
                        tag: el.tagName,
                        x: Math.round(r.x),
                        y: Math.round(r.y),
                        w: Math.round(r.width),
                    });
                }
            }
            const seen = new Set();
            return items.filter(i => {
                const key = i.text + '|' + Math.round(i.x / 10);
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            });
        }""")

        print(f"\n  Top bar items ({len(top_bar)}):")
        for el in sorted(top_bar, key=lambda e: e['x']):
            print(f"    x={el['x']} <{el['tag']}> {el['text']}")

        print("\n" + "=" * 60)
        print("  PART 6: UPLOAD SIDEBAR (for ref images)")
        print("=" * 60)

        page.mouse.click(40, 81)  # Upload sidebar
        page.wait_for_timeout(2000)
        close_all_dialogs(page)

        ss(page, "P21_05_upload_panel")

        upload_elements = page.evaluate("""() => {
            const items = [];
            for (const el of document.querySelectorAll('*')) {
                const r = el.getBoundingClientRect();
                const text = (el.innerText || '').trim().substring(0, 60);
                if (r.x > 60 && r.x < 400 && r.y > 50 && r.y < 800
                    && r.width > 20 && r.width < 350 && text
                    && !text.includes('\\n') && text.length > 1 && text.length < 40) {
                    items.push({
                        text: text,
                        tag: el.tagName,
                        x: Math.round(r.x),
                        y: Math.round(r.y),
                        w: Math.round(r.width),
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

        print(f"\n  Upload panel elements ({len(upload_elements)}):")
        for el in upload_elements[:20]:
            print(f"    ({el['x']},{el['y']}) w={el['w']} <{el['tag']}> {el['text']}")

        file_inputs_upload = get_file_inputs(page)
        print(f"\n  File inputs in Upload panel: {len(file_inputs_upload)}")
        for fi in file_inputs_upload:
            print(f"    accept={fi['accept']} visible={fi['visible']} "
                  f"id={fi['id']} ({fi['x']},{fi['y']}) {fi['w']}x{fi['h']}")

        print("\n" + "=" * 60)
        print("  PART 7: RESULT CONTEXT MENU / RIGHT-CLICK")
        print("=" * 60)

        # Check if right-clicking a result shows a context menu
        images_now = get_result_images(page)
        if images_now:
            # Scroll results panel to show images
            page.evaluate("""() => {
                const panels = document.querySelectorAll('[class*="result"], [class*="Result"]');
                for (const p of panels) {
                    if (p.scrollHeight > p.clientHeight) {
                        p.scrollTop = 0;
                        return true;
                    }
                }
                return false;
            }""")
            page.wait_for_timeout(500)

            images_now = get_result_images(page)
            visible = [i for i in images_now if 0 < i["y"] < 900]
            if visible:
                img = visible[0]
                print(f"\n  Right-clicking result at ({img['x']},{img['y']})...")
                page.mouse.click(img['x'], img['y'], button="right")
                page.wait_for_timeout(1000)

                ss(page, "P21_06_context_menu")

                # Check for context menu items
                ctx_menu = page.evaluate("""() => {
                    const items = [];
                    for (const el of document.querySelectorAll('[class*="menu"], [class*="context"], [role="menu"], [role="menuitem"]')) {
                        const r = el.getBoundingClientRect();
                        const text = (el.innerText || '').trim().substring(0, 60);
                        if (r.width > 0 && text) {
                            items.push({
                                text: text,
                                tag: el.tagName,
                                role: el.getAttribute('role') || '',
                                x: Math.round(r.x),
                                y: Math.round(r.y),
                            });
                        }
                    }
                    return items;
                }""")

                print(f"  Context menu items: {len(ctx_menu)}")
                for item in ctx_menu[:10]:
                    print(f"    ({item['x']},{item['y']}) <{item['tag']}> role={item['role']} {item['text'][:40]}")

                # Close context menu
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)

        print("\n" + "=" * 60)
        print("  PART 8: CHECK GENERATION STATUS & CREDITS")
        print("=" * 60)

        # Check credits display
        credits_info = page.evaluate("""() => {
            const results = [];
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                if ((text.includes('Unlimited') || text.includes('credits') ||
                     text.includes('Credits') || /^\\d{1,5}$/.test(text)) &&
                    text.length < 30) {
                    const r = el.getBoundingClientRect();
                    if (r.width > 0 && r.width < 200) {
                        results.push({
                            text: text,
                            x: Math.round(r.x),
                            y: Math.round(r.y),
                        });
                    }
                }
            }
            const seen = new Set();
            return results.filter(i => {
                if (seen.has(i.text)) return false;
                seen.add(i.text);
                return true;
            });
        }""")

        print(f"\n  Credits info:")
        for c in credits_info:
            print(f"    ({c['x']},{c['y']}) {c['text']}")

        ss(page, "P21_07_final")

        print(f"\n\n===== PHASE 21 COMPLETE =====")

    finally:
        # page.close() and pw.stop() hang on CDP connections
        # os._exit() is the only reliable cleanup method
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)


if __name__ == "__main__":
    main()
