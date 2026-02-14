#!/usr/bin/env python3
"""Dzine Deep Exploration Part 15 — Camera Button Activation + NBP 16:9 Gen + Expression Edit.

1. Fix camera button click (click card container, not text)
2. Generate NBP image at 16:9 (confirmed working)
3. Explore Expression Edit feature
4. Explore remaining sidebar tools: Motion Control, Enhance & Upscale, Video Editor
"""

import json
import sys
import time
sys.path.insert(0, "/Users/ray/Documents/openclaw")
from tools.lib.brave_profile import connect_or_launch


def screenshot(page, name):
    path = f"/Users/ray/Downloads/{name}.png"
    page.screenshot(path=path)
    print(f"  [SS] {path}")


def close_dialogs(page):
    page.evaluate("""() => {
        for (var i = 0; i < 5; i++) {
            for (var text of ['Not now', 'Close', 'Never show again', 'Got it', 'Skip', 'Later']) {
                for (var btn of document.querySelectorAll('button')) {
                    if ((btn.innerText || '').trim() === text && btn.offsetHeight > 0) btn.click();
                }
            }
        }
    }""")


def main():
    print("=" * 70)
    print("DZINE DEEP EXPLORATION PART 15")
    print("Camera Activation + NBP 16:9 + Expression Edit + Sidebar Tools")
    print("=" * 70)

    browser, context, _, _pw = connect_or_launch()
    page = context.pages[0]
    print(f"Connected. URL: {page.url}")

    if "dzine.ai/canvas" not in page.url:
        page.goto("https://www.dzine.ai/canvas?id=19861203")
        page.wait_for_timeout(5000)
        close_dialogs(page)
        page.wait_for_timeout(1000)

    # ================================================================
    # TASK 1: Fix Camera Button Click — Deep Analysis
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 1: Camera Movement Button — Active State Analysis")
    print("=" * 70)

    # Navigate to AI Video panel from sidebar
    page.mouse.click(40, 358)  # AI Video sidebar
    page.wait_for_timeout(2500)

    # Open Camera section
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return false;
        var camBtn = panel.querySelector('.camera-movement-btn');
        if (camBtn) { camBtn.click(); return true; }
        for (var el of panel.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Camera' && el.getBoundingClientRect().height < 60) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    # Click Free Selection tab
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return false;
        for (var el of panel.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Free Selection') { el.click(); return true; }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    # Deep map the camera movement cards — get FULL class hierarchy
    cards = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return [];
        var results = [];
        var knownMovements = ['Truck Left', 'Truck Right', 'Pan Left', 'Pan Right',
            'Push In', 'Pull Out', 'Pedestal Up', 'Pedestal Down',
            'Tilt Up', 'Tilt Down', 'Zoom In', 'Zoom Out',
            'Shake', 'Tracking Shot', 'Static Shot'];

        for (var el of panel.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            for (var m of knownMovements) {
                if (t === m) {
                    var rect = el.getBoundingClientRect();
                    // Only the card-sized elements (74x38 or 160x46), not tiny text labels
                    if (rect.height >= 30 && rect.height <= 50 && rect.width >= 60) {
                        var cls = (typeof el.className === 'string') ? el.className : '';
                        // Walk up parents to find container with active state
                        var parentCls = '';
                        var p = el.parentElement;
                        for (var i = 0; i < 3 && p; i++) {
                            var pc = (typeof p.className === 'string') ? p.className : '';
                            if (pc) parentCls += ' > ' + pc.substring(0, 40);
                            p = p.parentElement;
                        }
                        results.push({
                            text: m,
                            tag: el.tagName,
                            cls: cls.substring(0, 60),
                            parents: parentCls,
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            w: Math.round(rect.width),
                            h: Math.round(rect.height),
                            hasActiveChild: !!(el.querySelector('.active, .selected, [class*="active"]')),
                            clsInclActive: cls.includes('active') || cls.includes('selected')
                        });
                    }
                    break;
                }
            }
        }
        return results;
    }""")

    print(f"  Camera cards ({len(cards)}):")
    for c in cards:
        act = " [ACTIVE]" if c.get('clsInclActive') else ""
        child = " [HAS_ACTIVE_CHILD]" if c.get('hasActiveChild') else ""
        print(f"    '{c['text']}' at ({c['x']},{c['y']}) {c['w']}x{c['h']}")
        print(f"      cls: {c['cls']}")
        print(f"      parents: {c['parents']}")
        print(f"      {act}{child}")

    # Check which movements are currently selected by looking at all state indicators
    selected = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return [];
        var results = [];
        // Look for ANY element with active/selected/checked state in the camera area
        for (var el of panel.querySelectorAll('[class*="active"], [class*="selected"], [class*="checked"]')) {
            var rect = el.getBoundingClientRect();
            if (rect.height > 0 && rect.y > 60 && rect.y < 550) {
                var cls = (typeof el.className === 'string') ? el.className : '';
                var text = (el.innerText || '').trim();
                if (text.length < 30) {
                    results.push({
                        text: text,
                        cls: cls.substring(0, 60),
                        tag: el.tagName,
                        x: Math.round(rect.x),
                        y: Math.round(rect.y),
                        w: Math.round(rect.width),
                        h: Math.round(rect.height)
                    });
                }
            }
        }
        return results;
    }""")

    print(f"\n  Elements with active/selected state ({len(selected)}):")
    for s in selected:
        print(f"    [{s['tag'][:4]}] '{s['text'][:20]}' at ({s['x']},{s['y']}) {s['w']}x{s['h']} cls={s['cls']}")

    # Now try clicking Static Shot using mouse.click on the card center
    print("\n  Clicking Static Shot via mouse.click on card center...")
    # Static Shot card was at approximately (726, 472) 152x38 based on Part 14
    # Or the container at (722, 468) 160x46
    static_pos = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return null;
        for (var el of panel.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            if (t === 'Static Shot') {
                var rect = el.getBoundingClientRect();
                if (rect.height >= 30 && rect.height <= 50 && rect.width >= 100) {
                    return {x: Math.round(rect.x + rect.width / 2), y: Math.round(rect.y + rect.height / 2)};
                }
            }
        }
        return null;
    }""")

    if static_pos:
        print(f"  Card center at ({static_pos['x']}, {static_pos['y']})")
        page.mouse.click(static_pos['x'], static_pos['y'])
        page.wait_for_timeout(800)

        # Check state after click
        after_click = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return [];
            var results = [];
            for (var el of panel.querySelectorAll('[class*="active"], [class*="selected"], [class*="checked"]')) {
                var rect = el.getBoundingClientRect();
                if (rect.height > 0 && rect.y > 60 && rect.y < 550) {
                    var text = (el.innerText || '').trim();
                    var cls = (typeof el.className === 'string') ? el.className : '';
                    if (text.length < 30) {
                        results.push({text: text, cls: cls.substring(0, 60), y: Math.round(rect.y)});
                    }
                }
            }
            return results;
        }""")
        print(f"  Active elements after click ({len(after_click)}):")
        for a in after_click:
            print(f"    '{a['text'][:20]}' cls={a['cls']}")
    else:
        print("  Static Shot card not found!")

    # Also try: first deselect all, then select Static Shot
    print("\n  Deselecting ALL movements first...")
    deselected = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return 0;
        var count = 0;
        for (var el of panel.querySelectorAll('[class*="active"]')) {
            var text = (el.innerText || '').trim();
            var rect = el.getBoundingClientRect();
            if (rect.height >= 30 && rect.height <= 50 && rect.y > 100 && rect.y < 550) {
                el.click();
                count++;
            }
        }
        return count;
    }""")
    print(f"  Deselected {deselected} items")
    page.wait_for_timeout(500)

    # Now click Static Shot again
    if static_pos:
        page.mouse.click(static_pos['x'], static_pos['y'])
        page.wait_for_timeout(800)

    screenshot(page, "p186_camera_fix")

    # Final state check
    final_state = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return [];
        var results = [];
        var movements = ['Truck Left', 'Truck Right', 'Pan Left', 'Pan Right',
            'Push In', 'Pull Out', 'Pedestal Up', 'Pedestal Down',
            'Tilt Up', 'Tilt Down', 'Zoom In', 'Zoom Out',
            'Shake', 'Tracking Shot', 'Static Shot'];
        for (var el of panel.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            for (var m of movements) {
                if (t === m) {
                    var rect = el.getBoundingClientRect();
                    if (rect.height >= 30 && rect.height <= 50 && rect.width >= 60) {
                        var cls = (typeof el.className === 'string') ? el.className : '';
                        results.push({
                            text: m,
                            active: cls.includes('active') || cls.includes('selected'),
                            cls: cls.substring(0, 50)
                        });
                    }
                    break;
                }
            }
        }
        return results;
    }""")

    print(f"\n  Final movement states:")
    for s in final_state:
        status = "ACTIVE" if s['active'] else "off"
        print(f"    {s['text']}: {status} (cls: {s['cls']})")

    # ================================================================
    # TASK 2: Generate NBP Image at 16:9
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 2: Generate Image at 16:9 with Nano Banana Pro")
    print("=" * 70)

    # Navigate to Txt2Img
    page.mouse.click(40, 197)  # Txt2Img sidebar
    page.wait_for_timeout(2500)

    # Verify Nano Banana Pro
    model = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return 'NO PANEL';
        var sn = panel.querySelector('.style-name');
        return sn ? (sn.innerText || '').trim() : 'unknown';
    }""")
    print(f"  Model: {model}")

    if model != "Nano Banana Pro":
        print("  WARNING: Wrong model! Selecting Nano Banana Pro...")
        # Click style selector to open picker
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return;
            var style = panel.querySelector('.style');
            if (style) style.click();
        }""")
        page.wait_for_timeout(1500)
        # Find and click Nano Banana Pro
        nbp_pos = page.evaluate("""() => {
            var picker = document.querySelector('.style-list-panel');
            if (!picker) return null;
            for (var el of picker.querySelectorAll('span, div')) {
                if ((el.innerText || '').trim() === 'Nano Banana Pro') {
                    var r = el.getBoundingClientRect();
                    if (r.height < 30 && r.height > 0) return {x: r.x + r.width/2, y: r.y - 60};
                }
            }
            return null;
        }""")
        if nbp_pos:
            page.mouse.click(nbp_pos['x'], nbp_pos['y'])
            page.wait_for_timeout(1000)

    # Click 16:9
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return;
        for (var el of panel.querySelectorAll('[class*="aspect"] *, [class*="ratio"] *')) {
            if ((el.innerText || '').trim() === '16:9') {
                el.click();
                return;
            }
        }
    }""")
    page.wait_for_timeout(500)

    # Fill prompt for product shot
    prompt = "Premium wireless headphones with gold accents on a clean white marble desk, warm afternoon sunlight from a window, shallow depth of field, living room background with bookshelf, product photography, ultra sharp details, 16:9 composition"
    page.evaluate("""(p) => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return;
        var ta = panel.querySelector('textarea');
        if (ta) {
            ta.focus();
            ta.value = p;
            ta.dispatchEvent(new Event('input', {bubbles: true}));
        }
    }""", prompt)
    page.wait_for_timeout(300)

    # Click Generate
    gen_clicked = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return false;
        for (var btn of panel.querySelectorAll('button')) {
            if ((btn.innerText || '').includes('Generate')) {
                btn.click();
                return true;
            }
        }
        return false;
    }""")
    print(f"  Generate clicked: {gen_clicked}")

    if gen_clicked:
        print("  Waiting for generation (60s max)...")
        page.wait_for_timeout(45000)  # NBP takes ~30-45s
        screenshot(page, "p186_nbp_16_9_result")
        print("  Generation complete.")

    # ================================================================
    # TASK 3: Explore Expression Edit
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 3: Expression Edit Feature")
    print("=" * 70)

    # Click Expression Edit from results panel action
    expr_clicked = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'Expression Edit') {
                var rect = el.getBoundingClientRect();
                if (rect.height > 0 && rect.height < 50 && rect.width > 100) {
                    el.click();
                    return true;
                }
            }
        }
        return false;
    }""")
    print(f"  Expression Edit clicked: {expr_clicked}")
    page.wait_for_timeout(2000)

    # Map the Expression Edit panel
    expr_panel = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {text: 'NO PANEL'};
        var text = panel.innerText || '';
        var buttons = [];
        for (var btn of panel.querySelectorAll('button, [class*="item"], [class*="option"]')) {
            var t = (btn.innerText || '').trim();
            var rect = btn.getBoundingClientRect();
            if (t && t.length < 30 && rect.height > 0 && rect.height < 60) {
                var cls = (typeof btn.className === 'string') ? btn.className : '';
                buttons.push({
                    text: t,
                    tag: btn.tagName,
                    cls: cls.substring(0, 40),
                    x: Math.round(rect.x),
                    y: Math.round(rect.y),
                    w: Math.round(rect.width),
                    h: Math.round(rect.height)
                });
            }
        }
        return {panelText: text.substring(0, 600), buttons: buttons};
    }""")

    print(f"  Panel text:")
    for line in expr_panel.get('panelText', '').split('\n')[:20]:
        line = line.strip()
        if line:
            print(f"    > {line[:60]}")

    if expr_panel.get('buttons'):
        print(f"\n  Buttons ({len(expr_panel['buttons'])}):")
        for b in expr_panel['buttons']:
            print(f"    [{b['tag'][:4]}] '{b['text'][:25]}' at ({b['x']},{b['y']}) {b['w']}x{b['h']}")

    screenshot(page, "p186_expression_edit")

    # ================================================================
    # TASK 4: Explore sidebar tools — Motion Control
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 4: Motion Control Sidebar Tool")
    print("=" * 70)

    page.mouse.click(40, 540)  # Motion Control sidebar
    page.wait_for_timeout(2000)

    mc_panel = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {text: 'NO PANEL'};
        var text = panel.innerText || '';
        return {panelText: text.substring(0, 600)};
    }""")

    print(f"  Motion Control panel text:")
    for line in mc_panel.get('panelText', '').split('\n')[:15]:
        line = line.strip()
        if line:
            print(f"    > {line[:60]}")

    screenshot(page, "p186_motion_control")

    # ================================================================
    # TASK 5: Enhance & Upscale sidebar tool
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 5: Enhance & Upscale Sidebar Tool")
    print("=" * 70)

    page.mouse.click(40, 608)  # Enhance & Upscale sidebar
    page.wait_for_timeout(2000)

    eu_panel = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {text: 'NO PANEL'};
        var text = panel.innerText || '';
        return {panelText: text.substring(0, 600)};
    }""")

    print(f"  Enhance & Upscale panel text:")
    for line in eu_panel.get('panelText', '').split('\n')[:15]:
        line = line.strip()
        if line:
            print(f"    > {line[:60]}")

    screenshot(page, "p186_enhance_upscale")

    print("\n" + "=" * 70)
    print("EXPLORATION PART 15 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
