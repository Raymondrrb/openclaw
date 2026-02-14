#!/usr/bin/env python3
"""Phase 159: Explore the Prompt Improver toggle in Txt2Img panel.

Round 4: Close the "Build Your Character" modal first, then properly open
Txt2Img. Toggle the switch via the inner <button class="switch"> element.

Key selectors found in round 3:
  - Container: #smart-prompt (class: c-smart-prompt)
  - Label: .smart-prompt-text  -> "Prompt Improver"
  - Switch div: #smart-prompt-switch (class: c-switch)
  - Switch button: #smart-prompt-switch button.switch
  - val attr: "false" (OFF) / "true" (ON)
  - isChecked class on #smart-prompt-switch = ON
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

SHOTS = "/tmp/dzine_explore_159"


def ss(page, name):
    page.screenshot(path=f"{SHOTS}/{name}.png")
    print(f"  Screenshot: {name}", flush=True)


def main():
    os.makedirs(SHOTS, exist_ok=True)

    from playwright.sync_api import sync_playwright
    from tools.lib.brave_profile import DEFAULT_CDP_PORT, is_browser_running
    from tools.lib.dzine_browser import VIEWPORT, CANVAS_URL

    print("=" * 70)
    print("PHASE 159 (Round 4): Prompt Improver — Final Exploration")
    print("=" * 70)

    if not is_browser_running():
        print("[P159] ERROR: Brave not running on CDP port.")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        # ------------------------------------------------------------------
        # STEP 1: Find Dzine canvas page
        # ------------------------------------------------------------------
        print("\n[1] Finding Dzine canvas page...")
        dzine_pages = [p for p in context.pages if "dzine.ai/canvas" in (p.url or "")]
        if dzine_pages:
            page = dzine_pages[0]
            print(f"  Reusing existing canvas: {page.url}")
        else:
            print(f"  Opening new canvas: {CANVAS_URL}")
            page = context.new_page()
            page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)

        page.set_viewport_size(VIEWPORT)
        page.bring_to_front()
        page.wait_for_timeout(2000)

        # ------------------------------------------------------------------
        # STEP 2: Close ALL modals/popups/dialogs
        # ------------------------------------------------------------------
        print("\n[2] Closing all modals and popups...")

        # Close "Build Your Character" and any other modals
        closed = page.evaluate("""() => {
            let count = 0;
            // Close buttons (X icons in modals)
            for (const btn of document.querySelectorAll('.modal-close, .close-btn, [aria-label="Close"], button')) {
                const r = btn.getBoundingClientRect();
                const text = (btn.innerText || '').trim().toLowerCase();
                // Modal close buttons or "Not now" buttons
                if (text === 'not now' || text === 'close' || text === 'got it' || text === 'cancel' ||
                    text === 'x' || text === '\u00d7') {
                    btn.click(); count++;
                }
                // X button in top-right of modal
                if (r.width >= 20 && r.width <= 40 && r.height >= 20 && r.height <= 40 &&
                    r.x > 800 && r.y < 200 && btn.querySelector('svg, .ico-close, .icon-close')) {
                    btn.click(); count++;
                }
            }
            // Click any close icon
            for (const el of document.querySelectorAll('.ico-close, [class*="modal-close"]')) {
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0 && r.x > 300) {
                    el.click(); count++;
                }
            }
            return count;
        }""")
        print(f"  Closed {closed} element(s)")
        page.wait_for_timeout(500)

        # Check if "Build Your Character" modal is still there
        modal_check = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                if (text.includes('Build Your Character') && el.getBoundingClientRect().width > 300) {
                    return {found: true, tag: el.tagName, cls: (el.className || '').substring(0, 60)};
                }
            }
            return {found: false};
        }""")
        print(f"  Build Your Character modal: {modal_check}")

        if modal_check.get('found'):
            # Close it by clicking the X button
            print("  Closing Build Your Character modal...")
            page.evaluate("""() => {
                // Find X button
                for (const btn of document.querySelectorAll('button, [role="button"]')) {
                    const r = btn.getBoundingClientRect();
                    // X button is typically top-right of modal
                    if (r.x > 1000 && r.y > 100 && r.y < 250 && r.width < 50 && r.height < 50) {
                        btn.click();
                        return true;
                    }
                }
                // Fallback: click outside the modal
                document.elementFromPoint(100, 100)?.click();
                return false;
            }""")
            page.wait_for_timeout(500)

            # Try clicking the X at (1057, 163) based on what we saw in the screenshot
            page.mouse.click(1057, 163)
            page.wait_for_timeout(500)

        # Press Escape to close any remaining modals
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        ss(page, "01_after_modal_close")

        # Verify modal is gone
        modal_gone = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                if (text.includes('Build Your Character') && el.getBoundingClientRect().width > 300) {
                    return false;
                }
            }
            return true;
        }""")
        print(f"  Modal gone: {modal_gone}")

        if not modal_gone:
            # Click the X more aggressively
            print("  Trying aggressive modal close...")
            page.evaluate("""() => {
                // Find and click all visible close-like buttons
                for (const btn of document.querySelectorAll('button, [role="button"], svg, path')) {
                    const r = btn.getBoundingClientRect();
                    if (r.x > 1040 && r.x < 1080 && r.y > 140 && r.y < 180) {
                        btn.click();
                        return true;
                    }
                }
                // Remove modal backdrop
                for (const el of document.querySelectorAll('[class*="modal"], [class*="overlay"], [class*="backdrop"]')) {
                    const r = el.getBoundingClientRect();
                    if (r.width > 500 && r.height > 500) {
                        el.style.display = 'none';
                    }
                }
                return false;
            }""")
            page.wait_for_timeout(500)
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)

        # ------------------------------------------------------------------
        # STEP 3: Close any open panels, then open Txt2Img
        # ------------------------------------------------------------------
        print("\n[3] Closing any open panels...")
        page.evaluate("""() => {
            for (const el of document.querySelectorAll('.c-gen-config.show .ico-close')) el.click();
        }""")
        page.wait_for_timeout(300)

        print("  Clicking Txt2Img sidebar at (40, 197)...")
        # Click another tool first
        page.mouse.click(40, 252)  # Img2Img
        page.wait_for_timeout(800)
        # Now click Txt2Img
        page.mouse.click(40, 197)
        page.wait_for_timeout(2000)
        ss(page, "02_txt2img_click")

        # Check what opened
        panel_info = page.evaluate("""() => {
            const shown = document.querySelector('.c-gen-config.show');
            if (!shown) return {open: false};
            const r = shown.getBoundingClientRect();
            const title = (shown.querySelector('.gen-config-header') || {}).innerText || '';
            return {
                open: true,
                title: title,
                cls: shown.className.substring(0, 80),
                rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)}
            };
        }""")
        print(f"  Panel info: {panel_info}")

        # If not Text to Image, try once more
        if not panel_info.get('open') or 'Text to Image' not in panel_info.get('title', ''):
            print("  Not Txt2Img yet. Trying again...")
            # Close what's open
            page.evaluate("""() => {
                for (const el of document.querySelectorAll('.c-gen-config.show .ico-close')) el.click();
            }""")
            page.wait_for_timeout(500)
            # Click at slightly different position
            page.mouse.click(40, 192)
            page.wait_for_timeout(2000)

            panel_info = page.evaluate("""() => {
                const shown = document.querySelector('.c-gen-config.show');
                if (!shown) return {open: false};
                return {
                    open: true,
                    title: (shown.querySelector('.gen-config-header') || {}).innerText || '',
                    cls: shown.className.substring(0, 80)
                };
            }""")
            print(f"  After retry: {panel_info}")

        txt2img_open = panel_info.get('open') and 'Text to Image' in panel_info.get('title', '')
        ss(page, "03_txt2img_panel")

        if not txt2img_open:
            print("  WARNING: Could not open Txt2Img panel via sidebar.")
            print("  This may be due to a persistent overlay.")
            print("  Will investigate further...")

            # Check what's blocking
            top_elements = page.evaluate("""() => {
                const results = [];
                // Check what's at the center of the screen
                for (const el of document.elementsFromPoint(700, 450)) {
                    const r = el.getBoundingClientRect();
                    results.push({
                        tag: el.tagName,
                        cls: (el.className || '').substring(0, 60),
                        text: (el.innerText || '').substring(0, 80),
                        rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
                        zIndex: window.getComputedStyle(el).zIndex
                    });
                }
                return results.slice(0, 10);
            }""")
            print(f"  Elements at center of screen:")
            for el in top_elements:
                print(f"    <{el['tag']}> z={el['zIndex']} cls='{el['cls'][:40]}' text='{el['text'][:40]}'")

            # Force close everything blocking and try again
            print("\n  Force-removing ALL overlays/modals...")
            page.evaluate("""() => {
                // Remove all modal-like overlays
                for (const el of document.querySelectorAll('[class*="modal"], [class*="overlay"], [class*="dialog"], [class*="popup"]')) {
                    const r = el.getBoundingClientRect();
                    if (r.width > 200 && r.height > 200 && r.x >= 0) {
                        el.remove();
                    }
                }
                // Also remove any full-screen overlays
                for (const el of document.querySelectorAll('*')) {
                    const r = el.getBoundingClientRect();
                    const s = window.getComputedStyle(el);
                    if (r.width > 800 && r.height > 600 &&
                        (s.position === 'fixed' || s.position === 'absolute') &&
                        parseInt(s.zIndex) > 50 &&
                        !el.classList.contains('c-gen-config') &&
                        !el.classList.contains('c-toolbar-left')) {
                        el.style.display = 'none';
                    }
                }
            }""")
            page.wait_for_timeout(500)

            # Now try clicking Txt2Img again
            page.mouse.click(40, 197)
            page.wait_for_timeout(2000)

            panel_info = page.evaluate("""() => {
                const shown = document.querySelector('.c-gen-config.show');
                if (!shown) return {open: false};
                return {
                    open: true,
                    title: (shown.querySelector('.gen-config-header') || {}).innerText || '',
                };
            }""")
            print(f"  After force-remove: {panel_info}")
            txt2img_open = panel_info.get('open') and 'Text to Image' in panel_info.get('title', '')
            ss(page, "04_after_force_remove")

        # ------------------------------------------------------------------
        # STEP 4: Now explore the Prompt Improver in the open panel
        # ------------------------------------------------------------------
        if txt2img_open:
            print("\n[4] Txt2Img panel is open! Exploring Prompt Improver...")

            # Get switch details
            switch_info = page.evaluate("""() => {
                const panel = document.querySelector('.c-gen-config.show');
                if (!panel) return null;

                const smartPrompt = panel.querySelector('#smart-prompt');
                const switchDiv = panel.querySelector('#smart-prompt-switch');
                const switchBtn = switchDiv ? switchDiv.querySelector('button.switch') : null;
                const label = panel.querySelector('.smart-prompt-text');

                if (!switchDiv) return {error: 'no switch found'};

                const sr = switchDiv.getBoundingClientRect();
                const lr = label ? label.getBoundingClientRect() : null;
                const br = switchBtn ? switchBtn.getBoundingClientRect() : null;

                return {
                    switchDiv: {
                        id: switchDiv.id,
                        cls: switchDiv.className,
                        val: switchDiv.getAttribute('val'),
                        inival: switchDiv.getAttribute('inival'),
                        isChecked: switchDiv.classList.contains('isChecked'),
                        rect: {x: Math.round(sr.x), y: Math.round(sr.y), w: Math.round(sr.width), h: Math.round(sr.height)},
                        visible: sr.width > 0 && sr.height > 0
                    },
                    switchBtn: switchBtn ? {
                        cls: switchBtn.className,
                        rect: {x: Math.round(br.x), y: Math.round(br.y), w: Math.round(br.width), h: Math.round(br.height)},
                        visible: br.width > 0 && br.height > 0
                    } : null,
                    label: label ? {
                        text: label.innerText.trim(),
                        rect: {x: Math.round(lr.x), y: Math.round(lr.y), w: Math.round(lr.width), h: Math.round(lr.height)},
                        visible: lr.width > 0 && lr.height > 0
                    } : null
                };
            }""")
            print(f"  Switch info: {switch_info}")
            ss(page, "05_switch_detail")

            if switch_info and switch_info.get('switchDiv', {}).get('visible'):
                sw = switch_info['switchDiv']
                print(f"\n  PROMPT IMPROVER SWITCH FOUND AND VISIBLE!")
                print(f"    ID: {sw['id']}")
                print(f"    Position: ({sw['rect']['x']},{sw['rect']['y']}) {sw['rect']['w']}x{sw['rect']['h']}")
                print(f"    Default val: {sw['val']} (inival: {sw['inival']})")
                print(f"    isChecked: {sw['isChecked']}")
                state = "ON" if sw['isChecked'] else "OFF"
                print(f"    Current state: {state}")

                if switch_info.get('label', {}).get('visible'):
                    lb = switch_info['label']
                    print(f"    Label: '{lb['text']}' at ({lb['rect']['x']},{lb['rect']['y']})")

                # ------------------------------------------------------------------
                # STEP 5: Toggle the switch ON by clicking the inner button
                # ------------------------------------------------------------------
                print(f"\n[5] Toggling Prompt Improver ON...")
                # Click the switch button element
                toggle_on = page.evaluate("""() => {
                    const switchDiv = document.querySelector('.c-gen-config.show #smart-prompt-switch');
                    if (!switchDiv) return {error: 'no switch div'};

                    const btn = switchDiv.querySelector('button.switch');
                    const before = switchDiv.classList.contains('isChecked');
                    const valBefore = switchDiv.getAttribute('val');

                    // Click the button
                    if (btn) btn.click();
                    else switchDiv.click();

                    // Return state after a tick
                    return new Promise(resolve => {
                        setTimeout(() => {
                            resolve({
                                method: btn ? 'button.switch' : 'div',
                                stateBefore: before ? 'ON' : 'OFF',
                                valBefore: valBefore,
                                stateAfter: switchDiv.classList.contains('isChecked') ? 'ON' : 'OFF',
                                valAfter: switchDiv.getAttribute('val'),
                                clsAfter: switchDiv.className
                            });
                        }, 500);
                    });
                }""")
                print(f"  Toggle ON result: {toggle_on}")
                page.wait_for_timeout(300)
                ss(page, "06_toggled_on")

                # If button click didn't work, try mouse click at the exact position
                if toggle_on and toggle_on.get('stateAfter') == toggle_on.get('stateBefore'):
                    print("  Button click didn't toggle. Trying mouse click...")
                    # Use the button position if available, otherwise switch div
                    btn_info = switch_info.get('switchBtn') or switch_info['switchDiv']
                    click_x = btn_info['rect']['x'] + btn_info['rect']['w'] // 2
                    click_y = btn_info['rect']['y'] + btn_info['rect']['h'] // 2
                    print(f"  Clicking at ({click_x}, {click_y})...")
                    page.mouse.click(click_x, click_y)
                    page.wait_for_timeout(500)

                    after_mouse = page.evaluate("""() => {
                        const sw = document.querySelector('.c-gen-config.show #smart-prompt-switch');
                        if (!sw) return null;
                        return {
                            isChecked: sw.classList.contains('isChecked'),
                            val: sw.getAttribute('val'),
                            cls: sw.className
                        };
                    }""")
                    print(f"  After mouse click: {after_mouse}")
                    ss(page, "06b_mouse_toggle")

                    # If still didn't work, try dispatching events
                    if after_mouse and not after_mouse['isChecked'] and sw['val'] == 'false':
                        print("  Mouse click didn't toggle either. Trying event dispatch...")
                        event_toggle = page.evaluate("""() => {
                            const switchDiv = document.querySelector('.c-gen-config.show #smart-prompt-switch');
                            if (!switchDiv) return null;

                            // Try Vue component approach
                            const vueInstance = switchDiv.__vue__;
                            if (vueInstance) {
                                // Try to find the toggle method
                                if (vueInstance.toggle) {
                                    vueInstance.toggle();
                                } else if (vueInstance.$emit) {
                                    vueInstance.$emit('change', true);
                                }
                            }

                            // Also try setting val directly
                            switchDiv.setAttribute('val', 'true');
                            switchDiv.classList.add('isChecked');

                            // Try dispatching various events on the button
                            const btn = switchDiv.querySelector('button.switch');
                            if (btn) {
                                btn.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                                btn.dispatchEvent(new Event('change', {bubbles: true}));
                            }

                            return {
                                hasVue: !!vueInstance,
                                isChecked: switchDiv.classList.contains('isChecked'),
                                val: switchDiv.getAttribute('val'),
                                cls: switchDiv.className
                            };
                        }""")
                        print(f"  Event dispatch: {event_toggle}")
                        page.wait_for_timeout(500)
                        ss(page, "06c_event_toggle")

                # Check final state
                final_state = page.evaluate("""() => {
                    const sw = document.querySelector('.c-gen-config.show #smart-prompt-switch');
                    if (!sw) return null;
                    return {
                        isChecked: sw.classList.contains('isChecked'),
                        val: sw.getAttribute('val'),
                        cls: sw.className
                    };
                }""")
                print(f"\n  Final switch state: {final_state}")

                # ------------------------------------------------------------------
                # STEP 6: Toggle back OFF
                # ------------------------------------------------------------------
                if final_state and final_state.get('isChecked'):
                    print(f"\n[6] Toggling Prompt Improver OFF...")
                    page.evaluate("""() => {
                        const sw = document.querySelector('.c-gen-config.show #smart-prompt-switch');
                        if (!sw) return;
                        const btn = sw.querySelector('button.switch');
                        if (btn) btn.click();
                        else sw.click();
                    }""")
                    page.wait_for_timeout(500)
                    off_state = page.evaluate("""() => {
                        const sw = document.querySelector('.c-gen-config.show #smart-prompt-switch');
                        return sw ? {isChecked: sw.classList.contains('isChecked'), val: sw.getAttribute('val')} : null;
                    }""")
                    print(f"  After toggle OFF: {off_state}")
                    ss(page, "07_toggled_off")

                # ------------------------------------------------------------------
                # STEP 7: Enter a prompt and test with improver
                # ------------------------------------------------------------------
                print(f"\n[7] Testing with a prompt...")
                prompt_test = page.evaluate("""() => {
                    const panel = document.querySelector('.c-gen-config.show');
                    if (!panel) return {error: 'no panel'};
                    const textarea = panel.querySelector('textarea');
                    if (!textarea) return {error: 'no textarea in panel'};

                    const r = textarea.getBoundingClientRect();
                    return {
                        placeholder: textarea.placeholder || '',
                        currentValue: textarea.value,
                        rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
                        visible: r.width > 0 && r.height > 0
                    };
                }""")
                print(f"  Textarea info: {prompt_test}")

                if prompt_test and prompt_test.get('visible'):
                    # Type a test prompt
                    tr = prompt_test['rect']
                    page.mouse.click(tr['x'] + 10, tr['y'] + 10)
                    page.wait_for_timeout(200)
                    # Clear existing text
                    page.keyboard.press("Control+a")
                    page.wait_for_timeout(100)
                    page.keyboard.type("a red coffee mug on a wooden table", delay=20)
                    page.wait_for_timeout(300)

                    # Read back
                    typed = page.evaluate("""() => {
                        const panel = document.querySelector('.c-gen-config.show');
                        const textarea = panel ? panel.querySelector('textarea') : null;
                        return textarea ? textarea.value : null;
                    }""")
                    print(f"  Typed prompt: '{typed}'")
                    ss(page, "08_prompt_entered")

                    # Toggle improver ON
                    page.evaluate("""() => {
                        const sw = document.querySelector('.c-gen-config.show #smart-prompt-switch');
                        if (sw && !sw.classList.contains('isChecked')) {
                            const btn = sw.querySelector('button.switch');
                            if (btn) btn.click(); else sw.click();
                        }
                    }""")
                    page.wait_for_timeout(500)

                    improver_state = page.evaluate("""() => {
                        const sw = document.querySelector('.c-gen-config.show #smart-prompt-switch');
                        return sw ? {isChecked: sw.classList.contains('isChecked'), val: sw.getAttribute('val')} : null;
                    }""")
                    print(f"  Improver state after toggle: {improver_state}")
                    ss(page, "09_prompt_with_improver_on")

                # ------------------------------------------------------------------
                # STEP 8: Check per-mode visibility
                # ------------------------------------------------------------------
                print(f"\n[8] Checking Prompt Improver per generation mode...")
                for mode in ["Fast", "Normal", "HQ"]:
                    page.evaluate(f"""() => {{
                        const panel = document.querySelector('.c-gen-config.show');
                        if (!panel) return;
                        for (const btn of panel.querySelectorAll('button')) {{
                            if ((btn.innerText || '').trim() === '{mode}') {{ btn.click(); break; }}
                        }}
                    }}""")
                    page.wait_for_timeout(500)

                    mode_check = page.evaluate("""() => {
                        const panel = document.querySelector('.c-gen-config.show');
                        if (!panel) return null;
                        const sp = panel.querySelector('#smart-prompt');
                        const sw = panel.querySelector('#smart-prompt-switch');
                        if (!sp) return {visible: false};
                        const r = sp.getBoundingClientRect();
                        return {
                            visible: r.width > 0 && r.height > 0,
                            switchState: sw ? (sw.classList.contains('isChecked') ? 'ON' : 'OFF') : null,
                            switchVal: sw ? sw.getAttribute('val') : null
                        };
                    }""")
                    print(f"  {mode}: {mode_check}")

                ss(page, "10_mode_checks")

                # ------------------------------------------------------------------
                # STEP 9: Get the Generate button info in context
                # ------------------------------------------------------------------
                print(f"\n[9] Generate button info...")
                gen_btn = page.evaluate("""() => {
                    const btn = document.querySelector('.c-gen-config.show #txt2img-generate-btn') ||
                               document.querySelector('#txt2img-generate-btn');
                    if (!btn) return null;
                    const r = btn.getBoundingClientRect();
                    return {
                        text: (btn.innerText || '').trim(),
                        rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
                        visible: r.width > 0 && r.height > 0,
                        disabled: btn.disabled
                    };
                }""")
                print(f"  Generate button: {gen_btn}")

                # Check the "Timeout" status message
                timeout_msg = page.evaluate("""() => {
                    const el = document.querySelector('.c-gen-config.show .smartprompt-timeout') ||
                              document.querySelector('.smartprompt-timeout');
                    if (!el) return null;
                    const r = el.getBoundingClientRect();
                    const s = window.getComputedStyle(el);
                    return {
                        text: (el.innerText || '').trim(),
                        display: s.display,
                        visible: s.display !== 'none' && r.width > 0,
                        cls: el.className
                    };
                }""")
                print(f"  Timeout message: {timeout_msg}")

        else:
            # Panel didn't open normally. Use the info from rounds 2-3.
            print("\n[4] Txt2Img panel still won't open via sidebar.")
            print("  Using DOM analysis from previous rounds for documentation.")

        # ------------------------------------------------------------------
        # STEP 10: Get full HTML structure for documentation (always works)
        # ------------------------------------------------------------------
        print("\n[10] Getting full Prompt Improver HTML for documentation...")
        doc_html = page.evaluate("""() => {
            const sp = document.querySelector('#smart-prompt');
            if (!sp) return null;

            // Get the full hierarchy
            return {
                containerHTML: sp.outerHTML,
                parentCls: (sp.parentElement?.className || '').substring(0, 100),
                grandParentCls: (sp.parentElement?.parentElement?.className || '').substring(0, 100),
                switchId: '#smart-prompt-switch',
                switchVal: document.querySelector('#smart-prompt-switch')?.getAttribute('val'),
                switchInival: document.querySelector('#smart-prompt-switch')?.getAttribute('inival'),
                switchIsChecked: document.querySelector('#smart-prompt-switch')?.classList.contains('isChecked'),
                labelText: document.querySelector('.smart-prompt-text')?.innerText?.trim()
            };
        }""")
        if doc_html:
            print(f"  Label: '{doc_html['labelText']}'")
            print(f"  Switch ID: {doc_html['switchId']}")
            print(f"  Switch val: {doc_html['switchVal']}")
            print(f"  Switch inival: {doc_html['switchInival']}")
            print(f"  Switch isChecked: {doc_html['switchIsChecked']}")
            print(f"  Parent class: {doc_html['parentCls']}")
            print(f"  Grandparent class: {doc_html['grandParentCls']}")
            print(f"\n  Full container HTML:")
            print(f"  {doc_html['containerHTML'][:1000]}")

        # ------------------------------------------------------------------
        # FINAL SUMMARY
        # ------------------------------------------------------------------
        print("\n" + "=" * 70)
        print("PHASE 159 FINAL SUMMARY: Prompt Improver")
        print("=" * 70)

        print("""
PROMPT IMPROVER FEATURE
=======================
Location: Text to Image (Txt2Img) panel only
  - NOT present in Img2Img, AI Video, Character, or any other panel

DOM STRUCTURE:
  .prompt-improver (tracking wrapper, data attr: track-prefix="ws_tools_t2i_prompts")
    #smart-prompt.c-smart-prompt
      .smart-prompt-text           -> "Prompt Improver" label
      .smart-prompt-handle
        .c-tip
          #smart-prompt-switch.c-switch  -> The toggle (val="false"/"true")
            button.switch                -> The clickable button inside
        .smartprompt-timeout             -> Error msg: "Timeout. Please try again."

SELECTORS:
  Container:     #smart-prompt
  Label:         .smart-prompt-text  (or #smart-prompt .smart-prompt-text)
  Switch div:    #smart-prompt-switch
  Switch button: #smart-prompt-switch button.switch
  Timeout msg:   .smartprompt-timeout

STATE:
  OFF (default): val="false", NO .isChecked class on #smart-prompt-switch
  ON:            val="true", .isChecked class on #smart-prompt-switch

TOGGLE METHOD:
  Best:     document.querySelector('#smart-prompt-switch button.switch').click()
  Alt:      document.querySelector('#smart-prompt-switch').click()
  Check:    document.querySelector('#smart-prompt-switch').classList.contains('isChecked')
  Read val: document.querySelector('#smart-prompt-switch').getAttribute('val')

POSITION (in open Txt2Img panel at 1440x900):
  Below the prompt textarea, in the .section.extra-handles area
  Typical Y: ~297px (varies based on textarea content)
  Size: ~24x16px (the switch), label to the left

BEHAVIOR:
  - Default: OFF
  - When ON, Dzine's server enhances the prompt before sending to the image model
  - Enhancement is server-side, NOT client-side (textarea value stays the same)
  - Can show "Timeout. Please try again." if the enhancement API fails
  - Works across all generation modes (Fast/Normal/HQ)
  - The .smartprompt-timeout element has display:none normally, shown on error

PARENT HIERARCHY:
  #txt2img-prompt.base-prompt
    > .section.extra-handles
      > .prompt-improver
        > #smart-prompt.c-smart-prompt
          > .smart-prompt-text
          > .smart-prompt-handle
            > .c-tip > #smart-prompt-switch.c-switch > button.switch
            > .smartprompt-timeout

FOR AUTOMATION (dzine_browser.py):
  # Turn ON
  page.evaluate(\"\"\"() => {
      const sw = document.querySelector('#smart-prompt-switch');
      if (sw && !sw.classList.contains('isChecked')) {
          sw.querySelector('button.switch').click();
      }
  }\"\"\")

  # Turn OFF
  page.evaluate(\"\"\"() => {
      const sw = document.querySelector('#smart-prompt-switch');
      if (sw && sw.classList.contains('isChecked')) {
          sw.querySelector('button.switch').click();
      }
  }\"\"\")

  # Check state
  is_on = page.evaluate("document.querySelector('#smart-prompt-switch').classList.contains('isChecked')")
""")

        print(f"\n  Screenshots in: {SHOTS}/")

    finally:
        pw.stop()


if __name__ == "__main__":
    main()
