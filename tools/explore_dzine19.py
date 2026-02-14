"""Phase 19: Select Ray character precisely and generate CC images.

FIX: Click at CENTER of Ray element, not to the left.
Previous: clicked at (352, 445) — OUTSIDE element that starts at x=372.
Fix: click at (372 + 240/2, 425 + 40/2) = (492, 445).
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
    path = OUT_DIR / f"M{_N:02d}_{name}.png"
    page.screenshot(path=str(path), full_page=False)
    print(f"  SS: M{_N:02d}_{name}")


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


def wait_gen(page, timeout_s=120, label=""):
    """Wait for generation by checking if Generate button becomes clickable again."""
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        page.wait_for_timeout(5000)
        elapsed = time.monotonic() - start

        # Check button state
        btn_state = page.evaluate("""() => {
            for (const btn of document.querySelectorAll('button')) {
                const text = (btn.innerText || '').trim();
                const rect = btn.getBoundingClientRect();
                if (text.includes('Generate') && rect.x > 60 && rect.x < 400 && rect.y > 400) {
                    if (text.includes('Submitted')) return 'submitted';
                    if (btn.disabled) return 'disabled';
                    return 'ready';
                }
            }
            // Also check for loading/spinner
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                if (text === 'Starting a task...' || text.includes('Generating')) return 'generating';
            }
            return 'unknown';
        }""")
        print(f"  ... {elapsed:.0f}s btn={btn_state}")

        if btn_state == 'ready' and elapsed > 10:
            print(f"  Done in {elapsed:.0f}s!")
            ss(page, f"done_{label}")
            return True

    print(f"  Timed out after {timeout_s}s")
    ss(page, f"timeout_{label}")
    return False


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
        # ============================================================
        # STEP 1: Open CC panel + character dropdown
        # ============================================================
        print("\n===== STEP 1: Open CC Panel =====")

        # First close any open panels
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # Click Character sidebar
        page.mouse.click(40, 306)
        page.wait_for_timeout(1500)

        # Click "Generate Images" button to open CC panel
        page.evaluate("""() => {
            for (const btn of document.querySelectorAll('button')) {
                const text = (btn.innerText || '').trim();
                if (text.includes('Generate Images') && text.includes('With your character')) {
                    btn.click();
                    return;
                }
            }
        }""")
        page.wait_for_timeout(2000)
        ss(page, "cc_panel")

        # ============================================================
        # STEP 2: Select Ray — use JS to click the element directly
        # ============================================================
        print("\n===== STEP 2: Select Ray =====")

        # Find Ray and use JavaScript click on his row/button
        ray_result = page.evaluate("""() => {
            // Find all elements with "Ray" text
            const candidates = [];
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text === 'Ray' && rect.width > 5 && rect.height > 5 &&
                    rect.x > 150 && rect.y > 50) {
                    candidates.push({
                        text, tag: el.tagName,
                        x: Math.round(rect.x), y: Math.round(rect.y),
                        w: Math.round(rect.width), h: Math.round(rect.height),
                        parentTag: el.parentElement?.tagName,
                        parentW: Math.round(el.parentElement?.getBoundingClientRect()?.width || 0),
                        parentH: Math.round(el.parentElement?.getBoundingClientRect()?.height || 0),
                        grandparentTag: el.parentElement?.parentElement?.tagName,
                    });
                }
            }
            return candidates;
        }""")
        print(f"  Ray candidates: {json.dumps(ray_result, indent=2)}")

        # Now click Ray using JS — click his parent element (the row/button container)
        clicked = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const rect = el.getBoundingClientRect();
                if (text === 'Ray' && rect.width > 5 && rect.height > 5 &&
                    rect.x > 150 && rect.y > 50) {
                    // Try clicking the closest clickable ancestor
                    let target = el;
                    // Go up max 3 levels to find a button or clickable div
                    for (let i = 0; i < 4; i++) {
                        if (!target.parentElement) break;
                        target = target.parentElement;
                        const tr = target.getBoundingClientRect();
                        if (tr.width > 100 && tr.height > 20 && tr.height < 80) {
                            // This looks like a row — click it
                            target.click();
                            return {
                                clicked: 'ancestor_' + i,
                                tag: target.tagName,
                                x: Math.round(tr.x), y: Math.round(tr.y),
                                w: Math.round(tr.width), h: Math.round(tr.height)
                            };
                        }
                    }
                    // Fallback: click the element itself
                    el.click();
                    return {clicked: 'direct', tag: el.tagName, x: rect.x, y: rect.y};
                }
            }
            return null;
        }""")
        print(f"  Click result: {clicked}")
        page.wait_for_timeout(2000)
        ss(page, "ray_clicked")

        # Verify: check if "Choose a Character" is now replaced with "Ray"
        header_text = page.evaluate("""() => {
            // The character selector area is at the top of the CC panel
            for (const el of document.querySelectorAll('*')) {
                const rect = el.getBoundingClientRect();
                const text = (el.innerText || '').trim();
                if (rect.x > 60 && rect.x < 300 && rect.y > 50 && rect.y < 120 &&
                    rect.width > 100 && rect.height > 20 && rect.height < 60 &&
                    (text === 'Choose a Character' || text.includes('Ray'))) {
                    return text;
                }
            }
            return null;
        }""")
        print(f"  Header: {header_text}")

        # Check if warning is gone
        warning = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                if (text === 'Please choose a character.' && el.getBoundingClientRect().x > 60) {
                    return true;
                }
            }
            return false;
        }""")
        print(f"  Still showing warning: {warning}")

        if warning:
            # Ray wasn't selected. Try mouse click at exact center.
            print("\n  Trying mouse.click at exact Ray center position...")

            # First find Ray's exact position again
            ray_exact = page.evaluate("""() => {
                for (const el of document.querySelectorAll('*')) {
                    const text = (el.innerText || '').trim();
                    const rect = el.getBoundingClientRect();
                    if (text === 'Ray' && rect.x > 150 && rect.y > 50 && rect.width > 10) {
                        return {x: rect.x, y: rect.y, w: rect.width, h: rect.height};
                    }
                }
                return null;
            }""")

            if ray_exact:
                cx = ray_exact["x"] + ray_exact["w"] // 2
                cy = ray_exact["y"] + ray_exact["h"] // 2
                print(f"  Mouse clicking Ray at ({cx}, {cy})...")
                page.mouse.click(cx, cy)
                page.wait_for_timeout(2000)
                ss(page, "ray_mouse_click")

                # Check again
                warning2 = page.evaluate("""() => {
                    for (const el of document.querySelectorAll('*')) {
                        const text = (el.innerText || '').trim();
                        if (text === 'Please choose a character.' && el.getBoundingClientRect().x > 60) return true;
                    }
                    return false;
                }""")
                print(f"  Warning after mouse click: {warning2}")

                if warning2:
                    # Still not selected. The "Ray" text element might be different from the clickable area.
                    # Try clicking on the avatar image next to Ray
                    print("\n  Trying to click Ray's avatar image...")
                    avatar = page.evaluate("""() => {
                        for (const el of document.querySelectorAll('*')) {
                            const text = (el.innerText || '').trim();
                            const rect = el.getBoundingClientRect();
                            if (text === 'Ray' && rect.x > 150 && rect.y > 50) {
                                // Look for img sibling or nearby img
                                const parent = el.parentElement;
                                if (parent) {
                                    const img = parent.querySelector('img');
                                    if (img) {
                                        const ir = img.getBoundingClientRect();
                                        return {x: ir.x, y: ir.y, w: ir.width, h: ir.height};
                                    }
                                    // Try prev sibling
                                    const prev = el.previousElementSibling;
                                    if (prev) {
                                        const pr = prev.getBoundingClientRect();
                                        return {x: pr.x, y: pr.y, w: pr.width, h: pr.height, tag: prev.tagName};
                                    }
                                }
                                // Click 50px to the left of Ray text (where avatar should be)
                                return {x: rect.x - 40, y: rect.y, w: 30, h: rect.height, guessed: true};
                            }
                        }
                        return null;
                    }""")
                    print(f"  Avatar area: {avatar}")

                    if avatar:
                        ax = avatar["x"] + avatar["w"] // 2
                        ay = avatar["y"] + avatar["h"] // 2
                        print(f"  Clicking avatar at ({ax}, {ay})...")
                        page.mouse.click(ax, ay)
                        page.wait_for_timeout(2000)
                        ss(page, "ray_avatar_click")

                    # Final check
                    warning3 = page.evaluate("""() => {
                        for (const el of document.querySelectorAll('*')) {
                            const text = (el.innerText || '').trim();
                            if (text === 'Please choose a character.' && el.getBoundingClientRect().x > 60) return true;
                        }
                        return false;
                    }""")
                    print(f"  Warning after avatar click: {warning3}")

                    if warning3:
                        # Last resort: use dispatchEvent with full click simulation
                        print("\n  Last resort: dispatchEvent click on Ray row...")
                        page.evaluate("""() => {
                            for (const el of document.querySelectorAll('*')) {
                                const text = (el.innerText || '').trim();
                                const rect = el.getBoundingClientRect();
                                if (text === 'Ray' && rect.x > 150 && rect.y > 50 && rect.width > 10) {
                                    // Try clicking every ancestor up to 5 levels
                                    let target = el;
                                    for (let i = 0; i < 6; i++) {
                                        const evt = new MouseEvent('click', {
                                            bubbles: true, cancelable: true,
                                            clientX: rect.x + 10, clientY: rect.y + 5
                                        });
                                        target.dispatchEvent(evt);
                                        if (target.parentElement) target = target.parentElement;
                                    }
                                    return true;
                                }
                            }
                            return false;
                        }""")
                        page.wait_for_timeout(2000)
                        ss(page, "ray_dispatch")

        # ============================================================
        # STEP 3: Fill scene + set ratio + generate
        # ============================================================
        print("\n===== STEP 3: Fill Scene + Generate =====")

        # Check final selection state
        final_warning = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                if (text === 'Please choose a character.' && el.getBoundingClientRect().x > 60) return true;
            }
            return false;
        }""")

        if final_warning:
            print("  Ray STILL not selected. Taking screenshot for debugging...")
            # Dump the full character dropdown HTML
            dropdown_html = page.evaluate("""() => {
                // Find the dropdown container
                for (const el of document.querySelectorAll('*')) {
                    const text = (el.innerText || '').trim();
                    const rect = el.getBoundingClientRect();
                    if (text.includes('Ray') && text.includes('Anna') && text.includes('Lip Boy') &&
                        rect.width > 200) {
                        return {
                            html: el.outerHTML.substring(0, 3000),
                            tag: el.tagName,
                            cls: (el.className || '').toString().substring(0, 80),
                            x: Math.round(rect.x), y: Math.round(rect.y)
                        };
                    }
                }
                return null;
            }""")
            if dropdown_html:
                print(f"  Dropdown container: {dropdown_html['tag']} cls={dropdown_html['cls']}")
                print(f"  HTML (first 500): {dropdown_html['html'][:500]}")
            ss(page, "debug_dropdown")
        else:
            print("  Ray is selected! Proceeding with scene...")

            # Fill scene textarea
            scene_input = page.evaluate("""() => {
                for (const el of document.querySelectorAll('textarea, [contenteditable=\"true\"]')) {
                    const rect = el.getBoundingClientRect();
                    if (rect.x > 60 && rect.x < 350 && rect.width > 100 && rect.height > 20 && rect.y < 400) {
                        return {x: rect.x, y: rect.y, w: rect.width, h: rect.height};
                    }
                }
                return null;
            }""")

            if scene_input:
                page.mouse.click(scene_input["x"] + 50, scene_input["y"] + 15)
            else:
                page.mouse.click(100, 180)

            page.wait_for_timeout(300)
            page.keyboard.press("Meta+a")
            page.wait_for_timeout(100)

            scene = "Standing behind a modern desk in a minimalist studio, one hand resting on desk, confident smile, looking directly at camera, soft studio lighting, clean white background. Medium shot waist up."
            page.keyboard.type(scene, delay=5)
            page.wait_for_timeout(500)

            # Set aspect ratio to canvas (16:9)
            page.evaluate("""() => {
                for (const el of document.querySelectorAll('*')) {
                    const text = (el.innerText || '').trim();
                    const rect = el.getBoundingClientRect();
                    if (text === 'canvas' && rect.x > 60 && rect.x < 350 && rect.y > 400) {
                        el.click();
                        return;
                    }
                }
            }""")
            page.wait_for_timeout(300)

            ss(page, "ready_to_gen")

            # Click Generate
            gen_btn = page.evaluate("""() => {
                for (const btn of document.querySelectorAll('button')) {
                    const text = (btn.innerText || '').trim();
                    const rect = btn.getBoundingClientRect();
                    if (text.includes('Generate') && rect.x > 60 && rect.x < 350 &&
                        rect.y > 400 && !btn.disabled && rect.width > 100) {
                        btn.click();
                        return {text: text.replace(/\\n/g, ' '), x: rect.x, y: rect.y};
                    }
                }
                return null;
            }""")
            print(f"  Generate clicked: {gen_btn}")

            if gen_btn:
                page.wait_for_timeout(2000)
                close_all_dialogs(page)
                ss(page, "generating")

                success = wait_gen(page, timeout_s=120, label="cc_scene1")
                if success:
                    print("  CC Generation 1 succeeded!")

                    # Generate another scene
                    print("\n  Generating scene 2: holding product...")
                    if scene_input:
                        page.mouse.click(scene_input["x"] + 50, scene_input["y"] + 15)
                    else:
                        page.mouse.click(100, 180)
                    page.wait_for_timeout(300)
                    page.keyboard.press("Meta+a")
                    page.wait_for_timeout(100)

                    scene2 = "Holding a product in right hand, showing it to camera with enthusiastic expression, standing in studio with soft lighting, white background. Medium shot."
                    page.keyboard.type(scene2, delay=5)
                    page.wait_for_timeout(500)

                    page.evaluate("""() => {
                        for (const btn of document.querySelectorAll('button')) {
                            const text = (btn.innerText || '').trim();
                            if (text.includes('Generate') && !btn.disabled &&
                                btn.getBoundingClientRect().x > 60 && btn.getBoundingClientRect().x < 350) {
                                btn.click();
                                return;
                            }
                        }
                    }""")
                    page.wait_for_timeout(2000)
                    close_all_dialogs(page)
                    success2 = wait_gen(page, timeout_s=120, label="cc_scene2")
                    if success2:
                        print("  CC Generation 2 succeeded!")

        ss(page, "final")
        print("\n\n===== PHASE 19 COMPLETE =====")

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
