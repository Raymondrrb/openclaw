"""Phase 22: Find Upload panel (sidebar shifted?) + explore Img2Img
reference upload mechanism + test CC generation with progress monitoring.

Goals:
1. Map ACTUAL sidebar positions (may have shifted since last mapping)
2. Find the Upload panel and how reference images are uploaded
3. Explore Img2Img panel for reference-based generation
4. Test a CC generation and monitor progress to completion
5. Verify CC result images can be downloaded
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
    print("  PART 1: RE-MAP SIDEBAR POSITIONS", flush=True)
    print("=" * 60, flush=True)

    # Get all sidebar items (icons on the left edge)
    sidebar = page.evaluate("""() => {
        const items = [];
        // Look for elements at x < 80 that are interactive
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.x >= 0 && r.x < 80 && r.y > 40 && r.y < 850
                && r.width > 30 && r.width < 80 && r.height > 20 && r.height < 80
                && text && text.length < 30 && !text.includes('\\n')) {
                items.push({
                    text: text,
                    tag: el.tagName,
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                });
            }
        }
        // Deduplicate by y position (within 10px)
        const deduped = [];
        for (const item of items) {
            if (!deduped.some(d => Math.abs(d.y - item.y) < 10)) {
                deduped.push(item);
            }
        }
        return deduped.sort((a, b) => a.y - b.y);
    }""")

    print(f"\n  Sidebar items ({len(sidebar)}):", flush=True)
    for item in sidebar:
        print(f"    ({item['x']},{item['y']}) {item['w']}x{item['h']} "
              f"<{item['tag']}> '{item['text']}'", flush=True)

    # Alternative: check all clickable sidebar icons
    sidebar2 = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('[class*="sidebar"] *, [class*="Sidebar"] *, [class*="sider"] *, [class*="menu"] *')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.x < 80 && r.y > 40 && r.width > 10 && text && text.length < 30) {
                items.push({
                    text: text,
                    y: Math.round(r.y),
                    tag: el.tagName,
                });
            }
        }
        const seen = new Set();
        return items.filter(i => {
            const key = i.text + '|' + Math.round(i.y / 10);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort((a, b) => a.y - b.y);
    }""")

    print(f"\n  Sidebar (class search) ({len(sidebar2)}):", flush=True)
    for item in sidebar2[:20]:
        print(f"    y={item['y']} <{item['tag']}> '{item['text']}'", flush=True)

    ss(page, "P22_01_sidebar")

    print("\n" + "=" * 60, flush=True)
    print("  PART 2: CLICK EACH SIDEBAR POSITION", flush=True)
    print("=" * 60, flush=True)

    # Try clicking at each known position and read the panel title
    positions = [
        (40, 81, "upload?"),
        (40, 136, "assets?"),
        (40, 197, "txt2img?"),
        (40, 252, "img2img?"),
        (40, 306, "character?"),
        (40, 361, "ai_video?"),
        (40, 425, "lip_sync?"),
        (40, 490, "video_editor?"),
        (40, 550, "motion_ctrl?"),
        (40, 627, "enhance?"),
        (40, 698, "image_editor?"),
        (40, 766, "storyboard?"),
    ]

    for x, y, expected in positions:
        page.mouse.click(x, y)
        page.wait_for_timeout(800)
        close_all_dialogs(page)

        # Read the panel title (first text in x>60 area at top)
        panel_title = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const r = el.getBoundingClientRect();
                const text = (el.innerText || '').trim();
                if (r.x > 60 && r.x < 350 && r.y > 50 && r.y < 90
                    && r.width > 100 && text && text.length > 2 && text.length < 40
                    && !text.includes('\\n')) {
                    return text;
                }
            }
            return '(none)';
        }""")

        status = "MATCH" if expected.replace("?", "").lower() in panel_title.lower().replace(" ", "_").replace("&", "") else "???"
        print(f"  ({x},{y}) expected={expected:<15} got='{panel_title}' [{status}]", flush=True)

    print("\n" + "=" * 60, flush=True)
    print("  PART 3: EXPLORE IMG2IMG PANEL (reference upload)", flush=True)
    print("=" * 60, flush=True)

    page.mouse.click(40, 252)  # Img2Img
    page.wait_for_timeout(2000)
    close_all_dialogs(page)

    ss(page, "P22_02_img2img_detail")

    # Map Img2Img panel elements
    i2i_elements = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.x > 60 && r.x < 400 && r.y > 50 && r.y < 900
                && r.width > 20 && r.width < 350 && text
                && text.length > 1 && text.length < 50) {
                items.push({
                    text: text,
                    tag: el.tagName,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    cls: (el.className || '').substring(0, 40),
                });
            }
        }
        const seen = new Set();
        return items.filter(i => {
            const key = i.text + '|' + Math.round(i.y / 5);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort((a, b) => a.y - b.y);
    }""")

    print(f"\n  Img2Img panel ({len(i2i_elements)}):", flush=True)
    for el in i2i_elements[:40]:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'", flush=True)

    # Check for drop zones, upload areas
    drop_zones = page.evaluate("""() => {
        const zones = [];
        for (const el of document.querySelectorAll('[class*="upload"], [class*="Upload"], [class*="drop"], [class*="Drop"], [class*="drag"], [class*="Drag"]')) {
            const r = el.getBoundingClientRect();
            zones.push({
                tag: el.tagName,
                cls: (el.className || '').substring(0, 60),
                x: Math.round(r.x),
                y: Math.round(r.y),
                w: Math.round(r.width),
                h: Math.round(r.height),
                text: (el.innerText || '').trim().substring(0, 40),
            });
        }
        return zones;
    }""")

    print(f"\n  Upload/Drop zones ({len(drop_zones)}):", flush=True)
    for z in drop_zones[:15]:
        print(f"    ({z['x']},{z['y']}) {z['w']}x{z['h']} <{z['tag']}> cls={z['cls'][:30]} '{z['text']}'", flush=True)

    # Check hidden file inputs
    hidden_inputs = page.evaluate("""() => {
        const inputs = [];
        for (const inp of document.querySelectorAll('input')) {
            const type = inp.type || '';
            inputs.push({
                type: type,
                accept: inp.accept || '',
                id: inp.id || '',
                name: inp.name || '',
                hidden: inp.hidden || inp.offsetWidth === 0,
                cls: (inp.className || '').substring(0, 40),
            });
        }
        return inputs;
    }""")

    print(f"\n  All input elements ({len(hidden_inputs)}):", flush=True)
    for inp in hidden_inputs:
        print(f"    type={inp['type']} accept={inp['accept']} hidden={inp['hidden']} "
              f"id={inp['id']} cls={inp['cls']}", flush=True)

    print("\n" + "=" * 60, flush=True)
    print("  PART 4: UPLOAD SIDEBAR PANEL", flush=True)
    print("=" * 60, flush=True)

    page.mouse.click(40, 81)  # Upload
    page.wait_for_timeout(2000)
    close_all_dialogs(page)

    ss(page, "P22_03_upload_panel")

    # Check panel title
    upload_title = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.x > 60 && r.x < 350 && r.y > 50 && r.y < 90
                && r.width > 100 && text && text.length > 2 && text.length < 40
                && !text.includes('\\n')) {
                return text;
            }
        }
        return '(none)';
    }""")
    print(f"\n  Upload panel title: {upload_title}", flush=True)

    # Map full panel
    upload_items = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.x > 60 && r.x < 400 && r.y > 50 && r.y < 900
                && r.width > 20 && r.width < 350 && text
                && text.length > 1 && text.length < 50) {
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
            const key = i.text + '|' + Math.round(i.y / 5);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort((a, b) => a.y - b.y);
    }""")

    print(f"\n  Upload panel elements ({len(upload_items)}):", flush=True)
    for el in upload_items[:30]:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'", flush=True)

    # Check all inputs again after Upload panel
    inputs_now = page.evaluate("""() => {
        const inputs = [];
        for (const inp of document.querySelectorAll('input')) {
            inputs.push({
                type: inp.type || '',
                accept: inp.accept || '',
                hidden: inp.hidden || inp.offsetWidth === 0,
                cls: (inp.className || '').substring(0, 40),
            });
        }
        return inputs;
    }""")
    print(f"\n  Inputs after Upload: {len(inputs_now)}", flush=True)
    for inp in inputs_now:
        print(f"    type={inp['type']} accept={inp['accept']} hidden={inp['hidden']}", flush=True)

    print("\n" + "=" * 60, flush=True)
    print("  PART 5: CC GENERATION TEST", flush=True)
    print("=" * 60, flush=True)

    # Count CC images before
    before = page.evaluate("""() => {
        let count = 0;
        for (const img of document.querySelectorAll('img')) {
            if ((img.src || '').includes('characterchatfal')) count++;
        }
        return count;
    }""")
    print(f"\n  CC images before: {before}", flush=True)

    # 1. Click Character sidebar
    page.mouse.click(40, 306)
    page.wait_for_timeout(1500)
    close_all_dialogs(page)

    # 2. Click "Generate Images"
    clicked = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            const text = (btn.innerText || '').trim();
            if (text.includes('Generate Images') && text.includes('With your character')) {
                btn.click(); return true;
            }
        }
        return false;
    }""")
    print(f"  Generate Images clicked: {clicked}", flush=True)
    page.wait_for_timeout(2000)

    # 3. Select Ray
    ray_selected = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            const text = (el.innerText || '').trim();
            if (text === 'Ray' && el.tagName === 'BUTTON') {
                el.click(); return true;
            }
        }
        return false;
    }""")
    print(f"  Ray selected: {ray_selected}", flush=True)
    page.wait_for_timeout(2000)

    # 4. Type scene
    scene = "Ray sitting at a modern desk, reviewing a pair of wireless headphones. Thoughtful expression, clean workspace with soft ambient lighting. Medium shot, professional reviewer aesthetic."
    page.mouse.click(100, 180)
    page.keyboard.press("Meta+a")
    page.wait_for_timeout(200)
    page.keyboard.type(scene, delay=5)
    page.wait_for_timeout(500)

    # 5. Set canvas (16:9)
    canvas_set = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'canvas' &&
                el.getBoundingClientRect().x > 60 && el.getBoundingClientRect().y > 400) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    print(f"  Canvas ratio set: {canvas_set}", flush=True)
    page.wait_for_timeout(500)

    ss(page, "P22_04_cc_before_generate")

    # 6. Click Generate
    gen_clicked = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            const text = (btn.innerText || '').trim();
            if (text.includes('Generate') && !btn.disabled &&
                btn.getBoundingClientRect().x > 60 && btn.getBoundingClientRect().x < 350) {
                btn.click(); return true;
            }
        }
        return false;
    }""")
    print(f"  Generate clicked: {gen_clicked}", flush=True)

    if gen_clicked:
        # 7. Monitor progress
        print("\n  Monitoring generation progress...", flush=True)
        start = time.monotonic()
        last_pct = ""

        for i in range(40):  # Max 40 polls x 3s = 120s
            page.wait_for_timeout(3000)
            elapsed = time.monotonic() - start

            # Check progress
            progress = page.evaluate("""() => {
                const progs = [];
                for (const el of document.querySelectorAll('*')) {
                    const t = (el.innerText || '').trim();
                    if (/^\\d{1,3}%$/.test(t)) {
                        const r = el.getBoundingClientRect();
                        if (r.width > 0 && r.width < 100) {
                            progs.push({pct: t, y: Math.round(r.y)});
                        }
                    }
                }
                return progs;
            }""")

            # Check for new CC images
            after = page.evaluate("""() => {
                let count = 0;
                const urls = [];
                for (const img of document.querySelectorAll('img')) {
                    const src = img.src || '';
                    if (src.includes('characterchatfal')) {
                        count++;
                        urls.push(src.substring(0, 80));
                    }
                }
                return {count, urls};
            }""")

            pct_str = progress[0]["pct"] if progress else "no progress"
            if pct_str != last_pct or after["count"] > before:
                print(f"    [{elapsed:.0f}s] progress={pct_str} images={after['count']} (was {before})", flush=True)
                last_pct = pct_str

            if after["count"] > before:
                print(f"\n  NEW CC IMAGE(S) FOUND! ({after['count']} vs {before})", flush=True)

                # Get the new URLs
                all_cc = page.evaluate("""() => {
                    const urls = [];
                    for (const img of document.querySelectorAll('img')) {
                        const src = img.src || '';
                        if (src.includes('characterchatfal')) {
                            urls.push(src);
                        }
                    }
                    return urls;
                }""")

                for url in all_cc[:5]:
                    print(f"    {url[:100]}", flush=True)

                ss(page, "P22_05_cc_generated")

                # Download the first new image
                new_url = all_cc[0]
                dest = SS_DIR / "cc_test_generation.webp"
                try:
                    req = urllib.request.Request(new_url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        data = resp.read()
                    dest.write_bytes(data)
                    print(f"\n  Downloaded CC image: {len(data)} bytes → {dest}", flush=True)
                except Exception as exc:
                    print(f"\n  Download failed: {exc}", flush=True)

                break

            if elapsed > 120:
                print("  Timeout waiting for generation", flush=True)
                ss(page, "P22_05_cc_timeout")
                break
    else:
        print("  Skipping generation monitoring (Generate not clicked)", flush=True)

    ss(page, "P22_06_final")
    print(f"\n\n===== PHASE 22 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
