#!/usr/bin/env python3
"""Phase 151: Deep-dive — Image Editor sub-tools, Enhance & Upscale sidebar,
Lip Sync details, and export flow.

Expert-level documentation of features critical to our production pipeline.

Goals:
1. Image Editor sidebar — ALL sub-tools (Expand, Inpaint, etc.)
2. Enhance & Upscale sidebar — full interface details
3. Lip Sync — Normal vs Pro details, audio upload, face detection
4. Export dialog — all format options, upscale options, watermark
5. Canvas toolbar tools — AI Eraser, Hand Repair, Expression in detail
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))


def read_panel_full(page, label):
    """Read all content from active panel, including interactive elements."""
    panel = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show') ||
                    document.querySelector('.panels.show');
        if (panel) {
            var items = [];
            for (var el of panel.querySelectorAll('button, input, textarea, select, [contenteditable], [role="button"], [role="tab"], .c-switch, .c-slider, [class*="option"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0 && r.x < 500) {
                    var text = (el.innerText || el.placeholder || el.value || el.title || el.getAttribute('aria-label') || '').trim();
                    items.push({
                        text: text.substring(0, 80),
                        tag: el.tagName,
                        type: el.type || '',
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 50),
                        disabled: el.disabled || false,
                        selected: el.className.includes('active') || el.className.includes('selected')
                    });
                }
            }
            return {
                text: panel.innerText.substring(0, 3000),
                cls: panel.className.substring(0, 80),
                x: Math.round(panel.getBoundingClientRect().x),
                y: Math.round(panel.getBoundingClientRect().y),
                w: Math.round(panel.getBoundingClientRect().width),
                h: Math.round(panel.getBoundingClientRect().height),
                elements: items
            };
        }
        return null;
    }""")
    if panel:
        print(f"\n[{label}] Panel: ({panel['x']},{panel['y']}) {panel['w']}x{panel['h']} cls={panel['cls'][:50]}")
        print(f"[{label}] Text:\n{panel['text'][:1500]}")
        print(f"\n[{label}] Interactive elements: {len(panel['elements'])}")
        for e in panel['elements'][:30]:
            dis = " DISABLED" if e['disabled'] else ""
            sel = " [SEL]" if e['selected'] else ""
            print(f"  ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> '{e['text'][:40]}' cls={e['cls'][:25]}{dis}{sel}")
    else:
        print(f"[{label}] No panel found")
    return panel


def close_panels(page):
    """Close all open panels."""
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('.c-gen-config.show .ico-close, .panels.show .ico-close')) el.click();
        var p = document.querySelector('.lip-sync-config-panel.show');
        if (p) { var c = p.querySelector('.ico-close'); if (c) c.click(); }
    }""")
    page.wait_for_timeout(500)


def open_sidebar_tool(page, y, name):
    """Open a sidebar tool by clicking at (40, y) with toggle technique."""
    print(f"\n{'='*60}")
    print(f"Opening {name} (y={y})")
    print(f"{'='*60}")
    close_panels(page)
    # Toggle via distant tool first
    page.mouse.click(40, 197 if y != 197 else 766)
    page.wait_for_timeout(1000)
    page.mouse.click(40, y)
    page.wait_for_timeout(3000)


def main():
    from playwright.sync_api import sync_playwright
    from tools.lib.brave_profile import DEFAULT_CDP_PORT, is_browser_running
    from tools.lib.dzine_browser import close_all_dialogs, VIEWPORT

    print("=" * 70)
    print("PHASE 151: Deep-dive — Image Editor, Enhance, Lip Sync, Export")
    print("=" * 70)

    if not is_browser_running():
        print("[P151] ERROR: Brave not running.")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        dzine_pages = [p for p in context.pages if "dzine.ai/canvas" in (p.url or "")]
        if not dzine_pages:
            print("[P151] No Dzine canvas found.")
            return

        page = dzine_pages[0]
        page.set_viewport_size(VIEWPORT)
        page.bring_to_front()
        page.wait_for_timeout(1500)
        print(f"[P151] Canvas: {page.url}")

        close_all_dialogs(page)
        page.wait_for_timeout(500)

        # ============================================================
        # 1. IMAGE EDITOR — All sub-tools
        # ============================================================
        open_sidebar_tool(page, 698, "Image Editor")
        page.screenshot(path=os.path.expanduser("~/Downloads/p151_image_editor.png"))
        read_panel_full(page, "ImageEditor")

        # Check for sub-tool tabs/buttons within Image Editor
        subtabs = page.evaluate("""() => {
            var items = [];
            var panel = document.querySelector('.c-gen-config.show') || document.querySelector('.panels.show');
            if (!panel) return items;
            for (var el of panel.querySelectorAll('[class*="tab"], [class*="collapse"], [class*="menu"], [class*="feature"]')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 0 && text.length > 0 && text.length < 50) {
                    items.push({
                        text: text.substring(0, 50),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 60)
                    });
                }
            }
            return items;
        }""")
        print(f"\n[ImageEditor] Sub-tabs/features: {len(subtabs)}")
        for s in subtabs[:15]:
            print(f"  ({s['x']},{s['y']}) {s['w']}x{s['h']} '{s['text'][:40]}' cls={s['cls'][:40]}")

        # Check for collapse panels (expandable sections)
        collapse = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('.collapse-panel [class*="collapse-header"], .collapse-panel [class*="title"], .collapse-panel > div > div:first-child')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 0 && text.length > 0 && text.length < 60 && r.x > 60 && r.x < 400) {
                    items.push({
                        text: text.substring(0, 50),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 50),
                        expanded: el.className.includes('active') || el.className.includes('expanded')
                    });
                }
            }
            return items;
        }""")
        print(f"\n[ImageEditor] Collapse sections: {len(collapse)}")
        for c in collapse[:10]:
            exp = " [EXPANDED]" if c['expanded'] else ""
            print(f"  ({c['x']},{c['y']}) {c['w']}x{c['h']} '{c['text'][:40]}' cls={c['cls'][:40]}{exp}")

        # Click each sub-tool to see its options
        # Find clickable section headers
        section_headers = page.evaluate("""() => {
            var items = [];
            var panel = document.querySelector('.c-gen-config.show') || document.querySelector('.panels.show');
            if (!panel) return items;
            for (var el of panel.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                // Section headers are typically bold/larger text at specific positions
                if (r.width > 150 && r.height < 40 && r.height > 12 && r.x > 70 && r.x < 200 && r.y > 60 && r.y < 800 &&
                    text.length > 2 && text.length < 30 && el.childElementCount === 0) {
                    var s = window.getComputedStyle(el);
                    if (parseInt(s.fontSize) >= 13 || s.fontWeight > 400) {
                        items.push({
                            text: text,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            cls: (el.className || '').substring(0, 40),
                            fontSize: s.fontSize,
                            fontWeight: s.fontWeight
                        });
                    }
                }
            }
            // Deduplicate
            var unique = [], seen = new Set();
            for (var item of items) {
                if (!seen.has(item.text)) { seen.add(item.text); unique.push(item); }
            }
            return unique;
        }""")
        print(f"\n[ImageEditor] Section headers: {len(section_headers)}")
        for s in section_headers[:15]:
            print(f"  ({s['x']},{s['y']}) {s['w']}x{s['h']} '{s['text']}' size={s['fontSize']} weight={s['fontWeight']}")

        # ============================================================
        # 2. ENHANCE & UPSCALE SIDEBAR
        # ============================================================
        open_sidebar_tool(page, 628, "Enhance & Upscale")
        page.screenshot(path=os.path.expanduser("~/Downloads/p151_enhance_sidebar.png"))
        read_panel_full(page, "EnhanceSidebar")

        # ============================================================
        # 3. LIP SYNC — Detailed interface
        # ============================================================
        open_sidebar_tool(page, 425, "Lip Sync")
        page.wait_for_timeout(2000)
        page.screenshot(path=os.path.expanduser("~/Downloads/p151_lip_sync.png"))

        # Lip Sync has its own panel type
        lip = page.evaluate("""() => {
            var panel = document.querySelector('.lip-sync-config-panel.show') ||
                        document.querySelector('.c-gen-config.show') ||
                        document.querySelector('.panels.show');
            if (panel) {
                return {
                    text: panel.innerText.substring(0, 3000),
                    cls: panel.className.substring(0, 80),
                    x: Math.round(panel.getBoundingClientRect().x),
                    w: Math.round(panel.getBoundingClientRect().width),
                    h: Math.round(panel.getBoundingClientRect().height)
                };
            }
            return null;
        }""")
        if lip:
            print(f"\n[LipSync] Panel: x={lip['x']} w={lip['w']} h={lip['h']} cls={lip['cls'][:50]}")
            print(f"[LipSync] Content:\n{lip['text'][:2000]}")

        # Get all interactive elements in Lip Sync
        lip_elements = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('button, input, textarea, select, [contenteditable], [role="button"], [role="tab"], .c-switch, label, [class*="option"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0 && r.x > 60 && r.x < 500 && r.y > 30 && r.y < 900) {
                    var text = (el.innerText || el.placeholder || el.value || el.title || '').trim();
                    if (text.length > 0 || el.tagName === 'BUTTON' || el.tagName === 'INPUT') {
                        items.push({
                            text: text.substring(0, 80),
                            tag: el.tagName,
                            type: el.type || '',
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            cls: (el.className || '').substring(0, 50),
                            disabled: el.disabled || false,
                            selected: el.className.includes('active') || el.className.includes('selected')
                        });
                    }
                }
            }
            return items;
        }""")
        print(f"\n[LipSync] Interactive: {len(lip_elements)}")
        for e in lip_elements[:30]:
            dis = " DISABLED" if e['disabled'] else ""
            sel = " [SEL]" if e['selected'] else ""
            print(f"  ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> '{e['text'][:40]}' cls={e['cls'][:25]}{dis}{sel}")

        # Close Lip Sync (it wraps entire canvas)
        page.evaluate("""() => {
            var p = document.querySelector('.lip-sync-config-panel.show');
            if (p) {
                var c = p.querySelector('.ico-close');
                if (c) c.click();
                else p.classList.remove('show');
            }
        }""")
        page.wait_for_timeout(500)

        # ============================================================
        # 4. EXPORT DIALOG — Full details
        # ============================================================
        print(f"\n{'='*60}")
        print("Opening Export Dialog")
        print(f"{'='*60}")

        close_panels(page)

        # Click Export button
        page.evaluate("""() => {
            var btn = document.querySelector('button.export');
            if (btn && !btn.disabled) { btn.click(); return true; }
            return false;
        }""")
        page.wait_for_timeout(2000)

        page.screenshot(path=os.path.expanduser("~/Downloads/p151_export.png"))

        export = page.evaluate("""() => {
            // Find the export dialog
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text.includes('Export') && text.includes('JPG') && text.length < 500) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 200 && r.height > 200) {
                        // Get all interactive elements
                        var items = [];
                        for (var child of el.querySelectorAll('button, input, [role="button"], [class*="option"], label, [class*="check"]')) {
                            var cr = child.getBoundingClientRect();
                            var ct = (child.innerText || child.value || '').trim();
                            if (cr.width > 0 && ct.length > 0) {
                                items.push({
                                    text: ct.substring(0, 60),
                                    tag: child.tagName,
                                    x: Math.round(cr.x), y: Math.round(cr.y),
                                    w: Math.round(cr.width), h: Math.round(cr.height),
                                    cls: (child.className || '').substring(0, 40),
                                    selected: child.className.includes('active') || child.className.includes('selected')
                                });
                            }
                        }
                        return {
                            text: text.substring(0, 800),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            cls: (el.className || '').substring(0, 60),
                            elements: items
                        };
                    }
                }
            }
            return null;
        }""")
        if export:
            print(f"[Export] Dialog: ({export['x']},{export['y']}) {export['w']}x{export['h']}")
            print(f"[Export] Content:\n{export['text'][:600]}")
            print(f"\n[Export] Elements: {len(export['elements'])}")
            for e in export['elements'][:20]:
                sel = " [SEL]" if e['selected'] else ""
                print(f"  ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> '{e['text'][:40]}' cls={e['cls'][:30]}{sel}")
        else:
            print("[Export] Dialog not found (Export button may be disabled)")

        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # ============================================================
        # 5. CANVAS TOOLBAR — AI Eraser, Hand Repair, Expression detail
        # ============================================================
        print(f"\n{'='*60}")
        print("5. CANVAS TOOLBAR TOOLS — Detail")
        print(f"{'='*60}")

        # Click AI Eraser to see its interface
        print("\n[5a] AI Eraser...")
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('button')) {
                if ((el.innerText || '').trim() === 'AI Eraser') { el.click(); return true; }
            }
            return false;
        }""")
        page.wait_for_timeout(2000)
        page.screenshot(path=os.path.expanduser("~/Downloads/p151_ai_eraser.png"))

        eraser = page.evaluate("""() => {
            var items = [];
            // Check for any toolbar or panel that appeared
            for (var el of document.querySelectorAll('button, [role="button"], input[type="range"], .c-slider, [class*="brush"]')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || el.title || el.placeholder || '').trim();
                if (r.width > 0 && r.y > 30 && r.y < 120 && r.x > 100 && r.x < 800) {
                    items.push({
                        text: text.substring(0, 50),
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 50),
                        value: (el.value || '').substring(0, 20)
                    });
                }
            }
            return items;
        }""")
        print(f"[5a] AI Eraser toolbar: {len(eraser)}")
        for e in eraser[:15]:
            val = f" value={e['value']}" if e['value'] else ""
            print(f"  ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> '{e['text'][:30]}' cls={e['cls'][:30]}{val}")

        # Exit AI Eraser
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('button')) {
                var text = (el.innerText || '').trim();
                if (text === 'Exit' || text === 'Done' || text === 'Cancel') { el.click(); return text; }
            }
            return null;
        }""")
        page.wait_for_timeout(1000)

        # Click Hand Repair
        print("\n[5b] Hand Repair...")
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('button')) {
                if ((el.innerText || '').trim() === 'Hand Repair') { el.click(); return true; }
            }
            return false;
        }""")
        page.wait_for_timeout(2000)
        page.screenshot(path=os.path.expanduser("~/Downloads/p151_hand_repair.png"))

        hand_repair = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('button, [role="button"], input')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || el.title || '').trim();
                if (r.width > 0 && r.y > 30 && r.y < 120 && r.x > 100 && r.x < 800) {
                    items.push({
                        text: text.substring(0, 50),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 50)
                    });
                }
            }
            return items;
        }""")
        print(f"[5b] Hand Repair: {len(hand_repair)}")
        for e in hand_repair[:10]:
            print(f"  ({e['x']},{e['y']}) {e['w']}x{e['h']} '{e['text'][:30]}' cls={e['cls'][:30]}")

        # Exit Hand Repair
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('button')) {
                var text = (el.innerText || '').trim();
                if (text === 'Exit' || text === 'Done' || text === 'Cancel') { el.click(); return; }
            }
        }""")
        page.wait_for_timeout(1000)

        # Click Expression
        print("\n[5c] Expression Edit (toolbar)...")
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('button')) {
                if ((el.innerText || '').trim() === 'Expression') { el.click(); return true; }
            }
            return false;
        }""")
        page.wait_for_timeout(2000)
        page.screenshot(path=os.path.expanduser("~/Downloads/p151_expression.png"))

        expression = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('button, [role="button"], input, .c-slider, [class*="expression"]')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || el.title || '').trim();
                if (r.width > 0 && r.y > 30 && r.y < 300 && r.x > 60 && r.x < 800) {
                    items.push({
                        text: text.substring(0, 80),
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 50)
                    });
                }
            }
            return items;
        }""")
        print(f"[5c] Expression: {len(expression)}")
        for e in expression[:15]:
            print(f"  ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> '{e['text'][:40]}' cls={e['cls'][:30]}")

        # Check for expression presets
        presets = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('[class*="preset"], [class*="expression-item"], [class*="emoji"]')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || el.title || '').trim();
                if (r.width > 0 && r.y > 60 && r.y < 300) {
                    items.push({
                        text: text.substring(0, 30),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 50)
                    });
                }
            }
            return items;
        }""")
        if presets:
            print(f"\n[5c] Expression presets: {len(presets)}")
            for p in presets[:10]:
                print(f"  ({p['x']},{p['y']}) {p['w']}x{p['h']} '{p['text']}' cls={p['cls'][:30]}")

        # Exit Expression
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('button')) {
                var text = (el.innerText || '').trim();
                if (text === 'Exit' || text === 'Done' || text === 'Back' || text === 'Cancel') { el.click(); return; }
            }
        }""")
        page.wait_for_timeout(1000)

        # ============================================================
        # 6. CHARACTER PANEL — Full sub-features list
        # ============================================================
        open_sidebar_tool(page, 306, "Character")
        page.screenshot(path=os.path.expanduser("~/Downloads/p151_character.png"))
        read_panel_full(page, "Character")

        # ============================================================
        # SUMMARY
        # ============================================================
        page.screenshot(path=os.path.expanduser("~/Downloads/p151_final.png"), full_page=True)

        print("\n" + "=" * 70)
        print("PHASE 151 SUMMARY")
        print("=" * 70)
        print("  Check ~/Downloads/p151_*.png for screenshots")

    finally:
        pw.stop()


if __name__ == "__main__":
    main()
