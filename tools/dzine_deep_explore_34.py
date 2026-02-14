#!/usr/bin/env python3
"""Dzine Deep Exploration Part 34 — Click numbered AI Video button in results.

From P33 screenshot: Results panel has "AI Video: 1, 2, 3" numbered buttons.
Need to click the numbered button (e.g., "1") not the text label "AI Video".
These numbered buttons correspond to which Img2Img variation to use as start frame.
"""

import json
import sys
import base64
import os
sys.path.insert(0, "/Users/ray/Documents/openclaw")
from tools.lib.brave_profile import connect_or_launch


def screenshot(page, name):
    path = f"/Users/ray/Downloads/{name}.png"
    page.screenshot(path=path)
    print(f"  [SS] {path}")


def close_everything(page):
    page.evaluate("""() => {
        var pp = document.querySelector('.pick-panel');
        if (pp) { var c = pp.querySelector('.ico-close, [class*="close"]'); if (c) c.click(); }
        var pid = document.querySelector('.pick-image-dialog');
        if (pid) { var c = pid.querySelector('.ico-close'); if (c) c.click(); }
        var panel = document.querySelector('.c-gen-config.show');
        if (panel) { var close = panel.querySelector('.ico-close, button.close'); if (close) close.click(); }
        for (var el of document.querySelectorAll('.ico-close')) {
            if (el.offsetHeight > 0) try { el.click(); } catch(e) {}
        }
    }""")
    page.wait_for_timeout(300)
    page.keyboard.press('Escape')
    page.wait_for_timeout(300)


def main():
    print("=" * 70)
    print("DZINE DEEP EXPLORATION PART 34")
    print("Click Numbered AI Video Button + Generate")
    print("=" * 70)

    browser, context, _, _pw = connect_or_launch()
    page = context.pages[0]
    print(f"Connected. URL: {page.url}")

    if "dzine.ai/canvas" not in page.url:
        page.goto("https://www.dzine.ai/canvas?id=19861203")
        page.wait_for_timeout(6000)

    close_everything(page)
    page.wait_for_timeout(500)

    credits_before = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            if (t.match(/^Unlimited\\s*\\/\\s*[\\d.,]+$/)) return t;
        }
        return 'unknown';
    }""")
    print(f"  Credits before: {credits_before}")

    # ================================================================
    # Step 1: Map ALL numbered buttons in the AI Video row
    # ================================================================
    print("\n" + "=" * 70)
    print("Step 1: Find numbered AI Video buttons in results")
    print("=" * 70)

    # Map the results panel action rows with their numbered buttons
    action_rows = page.evaluate("""() => {
        var rows = [];
        // Look for the results panel right side
        var rp = document.querySelector('.result-panel, [class*="result-panel"]');
        if (!rp) {
            // Fallback: search in the right area of the page
            rp = document;
        }

        // Find all elements that contain "AI Video" as part of a row with numbers
        for (var el of rp.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            // Match pattern like "AI Video 1 2 3" or rows containing AI Video as label + numbered buttons
            if (text === 'AI Video' && el.offsetHeight > 0 && el.offsetHeight < 25) {
                var rect = el.getBoundingClientRect();
                var parent = el.parentElement;
                // Find sibling numbered buttons
                var numBtns = [];
                if (parent) {
                    for (var sib of parent.querySelectorAll('*')) {
                        var st = (sib.innerText || '').trim();
                        if (st.match(/^\\d$/) && sib.offsetHeight > 0) {
                            var sr = sib.getBoundingClientRect();
                            numBtns.push({
                                num: st,
                                x: Math.round(sr.x + sr.width/2),
                                y: Math.round(sr.y + sr.height/2),
                                w: Math.round(sr.width),
                                h: Math.round(sr.height),
                                tag: sib.tagName.toLowerCase(),
                                cls: (typeof sib.className === 'string') ? sib.className.substring(0, 30) : ''
                            });
                        }
                    }
                }
                rows.push({
                    label: text,
                    labelX: Math.round(rect.x),
                    labelY: Math.round(rect.y),
                    numBtns: numBtns
                });
            }
        }
        return rows;
    }""")

    print(f"  AI Video rows ({len(action_rows)}):")
    for row in action_rows:
        print(f"    Label at ({row['labelX']}, {row['labelY']})")
        for btn in row.get('numBtns', []):
            print(f"      [{btn['num']}] at ({btn['x']}, {btn['y']}) {btn['w']}x{btn['h']} {btn['tag']}.{btn['cls']}")

    # Find button "1" in the AI Video row (use first variation)
    target_btn = None
    for row in action_rows:
        for btn in row.get('numBtns', []):
            if btn['num'] == '1':
                target_btn = btn
                break
        if target_btn:
            break

    if target_btn:
        print(f"\n  Clicking AI Video [1] at ({target_btn['x']}, {target_btn['y']})...")
        page.mouse.click(target_btn['x'], target_btn['y'])
        page.wait_for_timeout(3000)

        screenshot(page, "p341_after_ai_video_click")

        # Check what happened
        panel = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {noPanel: true};
            var text = (panel.innerText || '').substring(0, 50).trim();
            var sel = panel.querySelector('.custom-selector-wrapper');
            var model = sel ? (sel.innerText || '').trim().split('\\n')[0] : '';
            var genBtn = null;
            for (var btn of panel.querySelectorAll('button')) {
                if ((btn.innerText || '').includes('Generate')) {
                    genBtn = {text: (btn.innerText || '').trim(), disabled: btn.disabled};
                }
            }
            var warning = '';
            for (var el of panel.querySelectorAll('*')) {
                var t = (el.innerText || '').trim();
                if ((t.includes('upload') || t.includes('key frame') || t.includes('Please')) && el.offsetHeight > 0 && el.offsetHeight < 30) {
                    warning = t; break;
                }
            }
            return {panel: text, model: model, genBtn: genBtn, warning: warning};
        }""")
        print(f"  Panel: {json.dumps(panel)}")

        # Check for pick dialog
        has_dialog = page.evaluate("""() => {
            var pp = document.querySelector('.pick-panel');
            return pp && pp.offsetHeight > 0 ? 'pick-panel open' : 'closed';
        }""")
        print(f"  Dialog: {has_dialog}")

        # If AI Video panel opened with start frame ready, we can generate
        if not panel.get('noPanel') and panel.get('genBtn') and not panel['genBtn'].get('disabled'):
            # Check if Wan 2.1 is selected
            if 'Wan' not in panel.get('model', ''):
                print("  Need to switch to Wan 2.1...")
                sel_pos = page.evaluate("""() => {
                    var p = document.querySelector('.c-gen-config.show');
                    var sel = p ? p.querySelector('.custom-selector-wrapper') : null;
                    if (!sel) return null;
                    var rect = sel.getBoundingClientRect();
                    return {cx: Math.round(rect.x + rect.width/2), cy: Math.round(rect.y + rect.height/2)};
                }""")
                if sel_pos:
                    page.mouse.click(sel_pos['cx'], sel_pos['cy'])
                    page.wait_for_timeout(2000)
                    page.evaluate("""() => {
                        for (var el of document.querySelectorAll('.panel-body')) {
                            if (el.scrollHeight > el.clientHeight + 30) el.scrollTop = el.scrollHeight;
                        }
                    }""")
                    page.wait_for_timeout(800)
                    wan = page.evaluate("""() => {
                        for (var el of document.querySelectorAll('*')) {
                            var t = (el.innerText || '').trim();
                            if (t.startsWith('Wan 2.1') && el.offsetHeight > 20 && el.offsetHeight < 120 && el.offsetWidth > 40) {
                                var r = el.getBoundingClientRect();
                                if (r.y > 0 && r.y < window.innerHeight) return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                            }
                        }
                        return null;
                    }""")
                    if wan:
                        page.mouse.click(wan['x'], wan['y'])
                        page.wait_for_timeout(2000)
                        print("  Wan 2.1 selected!")

            # Generate
            print("\n  >>> GENERATING Wan 2.1 VIDEO...")
            gen_pos = page.evaluate("""() => {
                var p = document.querySelector('.c-gen-config.show');
                if (!p) return null;
                for (var btn of p.querySelectorAll('button')) {
                    if ((btn.innerText || '').includes('Generate') && !btn.disabled) {
                        var r = btn.getBoundingClientRect();
                        return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                    }
                }
                return null;
            }""")
            if gen_pos:
                page.mouse.click(gen_pos['x'], gen_pos['y'])
                print("  Generation started! Waiting ~90s...")

                for i in range(15):
                    page.wait_for_timeout(10000)
                    secs = (i + 1) * 10
                    s = page.evaluate("""() => {
                        var vids = 0;
                        for (var v of document.querySelectorAll('video')) {
                            if (v.src && v.src.includes('static.dzine.ai')) vids++;
                        }
                        return {v: vids};
                    }""")
                    print(f"  [{secs}s] videos={s.get('v', 0)}")
                    if secs >= 70 and s.get('v', 0) > 0:
                        break

                screenshot(page, "p341_generation_done")

                # Download video
                vid_url = page.evaluate("""() => {
                    var latest = '';
                    for (var v of document.querySelectorAll('video')) {
                        if (v.src && v.src.includes('static.dzine.ai')) latest = v.src;
                    }
                    return latest;
                }""")
                if vid_url:
                    save_path = "/Users/ray/Documents/openclaw/artifacts/dzine/wan21_chain.mp4"
                    os.makedirs(os.path.dirname(save_path), exist_ok=True)
                    print(f"  Downloading from {vid_url[:60]}...")
                    b64 = page.evaluate("""(url) => {
                        return fetch(url).then(r => r.blob()).then(b => new Promise((resolve) => {
                            var reader = new FileReader();
                            reader.onload = () => resolve(reader.result);
                            reader.readAsDataURL(b);
                        })).catch(e => 'error: ' + e.message);
                    }""", vid_url)
                    if b64 and not b64.startswith('error:'):
                        data = b64.split(',', 1)[1]
                        with open(save_path, 'wb') as f:
                            f.write(base64.b64decode(data))
                        fsize = os.path.getsize(save_path)
                        print(f"  >>> Video saved: {save_path} ({fsize} bytes)")
                    else:
                        print(f"  Download error: {(b64 or '')[:80]}")
                else:
                    print("  No video URL found in DOM")

        elif panel.get('noPanel'):
            print("  No panel opened. The click might have triggered a different action.")
            # Check if the image was placed on canvas (for use by sidebar AI Video)
            screenshot(page, "p341_no_panel")
        else:
            print(f"  Panel opened but not ready: {panel.get('warning', 'unknown')}")

    else:
        print("  No AI Video [1] button found!")

    # ================================================================
    # Credits
    # ================================================================
    print("\n" + "=" * 70)
    print("Final Credits")
    print("=" * 70)
    credits_after = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            if (t.match(/^Unlimited\\s*\\/\\s*[\\d.,]+$/)) return t;
        }
        return 'unknown';
    }""")
    print(f"  Credits: {credits_after}")

    print("\n" + "=" * 70)
    print("EXPLORATION PART 34 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
