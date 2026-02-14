# Dzine Browser Automation -- Failures Playbook

Last updated: 2026-02-13

Quick-reference for every known Dzine automation failure. Each entry: Symptom, Root Cause, Fix, Prevention.

---

## 1. Login Expired / Session Lost

**Symptom:** `button.avatar` not found. Page redirects to `/login` or shows `button:has-text("Log in")` instead of the canvas.

**Root Cause:** Dzine session cookie expired or Brave profile lost auth state between runs.

**Fix:**
```python
logged_in = page.locator("button.avatar").count() > 0
if not logged_in:
    # Manual re-login required -- automate cannot bypass OAuth/captcha
    raise RuntimeError("Dzine session expired. Re-login manually in OpenClaw Brave.")
```

**Prevention:** Before every automation run, check for `button.avatar` visibility. Keep the OpenClaw Brave profile alive (don't clear cookies). Re-login manually if the session drops -- there is no programmatic login flow.

---

## 2. Tutorial / Promo Popup Blocking UI

**Symptom:** Clicks on generate buttons, sidebar tools, or canvas elements are silently intercepted. No error, but nothing happens.

**Root Cause:** Dzine shows tutorial dialogs and promotional popups on page load that overlay interactive elements. These have high z-index and intercept pointer events.

**Fix:**
```python
def close_all_dialogs(page):
    for _ in range(5):
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
```

**Prevention:** Call `close_all_dialogs(page)` immediately after every page navigation and before every major interaction sequence.

---

## 3. Generation Timeout

**Symptom:** Progress percentage in the Results panel sticks at a value (e.g., 0%, 21%, 65%) and never reaches 100%. No error displayed.

**Root Cause:** Server-side generation stalled, prompt was invalid, or service is overloaded. Generation is async -- the Generate button returns to "ready" immediately after submission.

**Fix:**
```python
# Poll Results panel for progress, timeout after 120s
import time
start = time.time()
while time.time() - start < 120:
    progress = page.evaluate("""() => {
        var el = document.querySelector('.result-panel .progress, .generating-progress');
        return el ? el.innerText : null;
    }""")
    if progress and '100' in progress:
        break
    page.wait_for_timeout(3000)
else:
    raise TimeoutError("Generation stuck. Retry or change prompt.")
```

**Prevention:** Set a hard timeout (120s for images, 180s for Lip Sync). Monitor the Results panel for progress, not the Generate button state. If stuck at 0% for >30s, abandon and retry with a simplified prompt.

---

## 4. Wrong Panel Active

**Symptom:** Clicked a sidebar tool icon but a different panel opened, or the previous panel stayed visible.

**Root Cause:** Adjacent sidebar tools share panel groups. Clicking Txt2Img then Img2Img may not switch because they're in the same panel group. Single clicks on already-active tools do nothing.

**Fix:** Use the **panel toggle technique** -- click a distant sidebar tool first, wait, then click the target:
```python
# To open Txt2Img reliably:
page.mouse.click(40, 766)   # Click Storyboard (distant tool)
page.wait_for_timeout(500)
page.mouse.click(40, 197)   # Now click Txt2Img
page.wait_for_timeout(2000)
```

Alternative: double-click the target sidebar icon:
```python
page.mouse.dblclick(40, 197)
page.wait_for_timeout(2000)
```

**Prevention:** Always toggle from a distant sidebar tool (e.g., Storyboard at y=766) to the target tool. Never assume a single click will switch between adjacent tools. Verify the panel header text after switching.

---

## 5. Lip Sync Panel Blocking Canvas

**Symptom:** Cannot click sidebar tools, canvas elements, or top toolbar while Lip Sync is open. Clicks silently swallowed.

**Root Cause:** The `lip-sync-config-panel show` class wraps the entire canvas area (1360x850) at a high z-index, intercepting all pointer events.

**Fix:**
```python
page.evaluate("""() => {
    var panel = document.querySelector('.lip-sync-config-panel.show');
    if (panel) {
        var close = panel.querySelector('.ico-close');
        if (close) { close.click(); return 'closed'; }
        panel.classList.remove('show');
        return 'not open';
    }
    return 'not open';
}""")
page.wait_for_timeout(500)
```

**Prevention:** Always close the Lip Sync panel explicitly before switching to any other tool. Check for `.lip-sync-config-panel.show` before any non-Lip-Sync interaction.

---

## 6. Character List Invisible (0x0 Dimensions)

**Symptom:** `.c-character-list` exists in DOM but has zero width and height. "Choose a Character" button click does nothing visible. Character dropdown never appears.

**Root Cause:** The character dropdown renders at 0x0 dimensions and is invisible. Clicking the trigger button via JS does not make it visible.

**Fix:** JS-click the hidden character button directly inside the zero-dimension list:
```python
page.evaluate("""() => {
    var list = document.querySelector('.c-character-list');
    for (var item of list.querySelectorAll('.item, button')) {
        if ((item.innerText || '').trim() === 'Ray') {
            item.click(); return true;
        }
    }
    return false;
}""")
page.wait_for_timeout(2000)
```

**Prevention:** Never rely on the dropdown being visible. Always use `page.evaluate()` to JS-click character items directly inside `.c-character-list`, bypassing the invisible container.

---

## 7. File Chooser Never Triggered

**Symptom:** Clicking upload buttons (Upload sidebar, Assets `.new-file.upload-image`) does nothing. No native file dialog appears. `expect_file_chooser()` times out.

**Root Cause:** Dzine does NOT use standard `<input type="file">` elements on the page. The upload mechanism uses Vue.js event handlers that dynamically create and destroy a temporary `<input type="file" accept="image/*">`. Some upload buttons (sidebar Upload, Assets) do not trigger this mechanism via CDP at all.

**Fix:** Use `expect_file_chooser()` only on buttons that support it (CC Reference upload, Face Match upload, Lip Sync audio upload):
```python
with page.expect_file_chooser(timeout=5000) as fc_info:
    page.mouse.click(upload_btn['x'], upload_btn['y'])
fc = fc_info.value
fc.set_files(str(image_path))
```

For the main canvas upload, use the Img2Img workaround: place images on canvas via result placement, not direct file upload.

**Prevention:** Do not attempt `expect_file_chooser()` on the sidebar Upload icon or Assets upload button -- they do not trigger file choosers via CDP. Use only the panel-specific upload buttons (CC Reference, Face Match, Lip Sync audio). For canvas images, use Img2Img with canvas content as the source.

---

## 8. Textarea Selector Mismatch

**Symptom:** Prompt text not entered. `page.locator('textarea')` finds the wrong element or nothing. Typed text appears in the wrong field or disappears.

**Root Cause:** Different generation modes use different prompt elements:
- **Txt2Img / Img2Img**: standard `<textarea>` with class `.len-1800` (1800 char limit)
- **Chat Editor**: `div.custom-textarea.len-5000[contenteditable='true']` (5000 char limit, NOT a textarea)
- **Character**: `div.custom-textarea[contenteditable='true']` with `@Ray` mention markup

**Fix:** Use mode-specific selectors:
```python
# Txt2Img / Img2Img
page.locator(".gen-config-form textarea, .base-prompt textarea").first.fill("prompt")

# Chat Editor
page.locator("[contenteditable='true'].custom-textarea.len-5000").first.click()
page.keyboard.type("prompt", delay=10)

# Character
page.locator(".custom-textarea[contenteditable='true']").first.click()
page.keyboard.type("scene description", delay=10)
```

**Prevention:** Never use a generic `textarea` selector. Always qualify with the panel class (`.gen-config-form`, `.img2img-config-panel`) or use the specific contenteditable selector for Chat Editor.

---

## 9. Result Image URL Pattern Changed

**Symptom:** Code looking for result images by URL pattern finds nothing. Image count check returns 0 even after generation completes.

**Root Cause:** Different generation modes produce different URL path segments:
- Txt2Img: `faltxt2img`
- Consistent Character: `faltxt2img` (NOT `characterchatfal` as you might expect)
- Character Chat: `characterchatfal`
- Chat Editor (Gemini): `gemini2text2image`
- Img2Img: `img2imgv2`

Full pattern: `static.dzine.ai/stylar_product/p/{project_id}/{model}/{index}_output_{timestamp}_{hash}.webp`

**Fix:** Detect new results by total image count increase, not by URL pattern matching:
```python
before_count = page.locator(".result-panel img, .result-item img").count()
# ... trigger generation and wait ...
after_count = page.locator(".result-panel img, .result-item img").count()
new_images = after_count - before_count
```

**Prevention:** Never match on `/generation/` in URLs (that pattern is wrong). Never assume a specific model slug. Always use count-based detection. The only reliable URL prefix is `/stylar_product/p/`.

---

## 10. page.close() Hangs on CDP

**Symptom:** Script freezes indefinitely on `page.close()` or `pw.stop()`. Process never exits.

**Root Cause:** Known Playwright issue with CDP (Chrome DevTools Protocol) connections. The close handshake can deadlock.

**Fix:**
```python
import threading, os

def _safe_cleanup(page, browser, pw, timeout=5):
    def _close():
        try:
            page.close()
            browser.close()
            pw.stop()
        except Exception:
            pass
    t = threading.Thread(target=_close)
    t.start()
    t.join(timeout)
    if t.is_alive():
        os._exit(0)  # Force exit if stuck
```

**Prevention:** Never call `page.close()` or `pw.stop()` without a timeout wrapper. Use `_safe_cleanup()` from `dzine_browser.py` in production code. For one-off scripts, use `os._exit(0)` as the final line.

---

## 11. Style Picker Renders at 0 Width

**Symptom:** `.style-list-panel` exists in DOM with content (6234+ bytes) but renders at width=0. Clicking `button.style` opens nothing visible.

**Root Cause:** In Img2Img mode, the style selector is opened by clicking `.style-name`, not `button.style`. Using the wrong trigger leaves the panel in the DOM but at zero width.

**Fix:**
```python
# For Img2Img: click .style-name instead of button.style
page.evaluate("""() => {
    var panel = document.querySelector('.img2img-config-panel');
    if (!panel) return null;
    var name = panel.querySelector('.style-name');
    if (name) { name.click(); return true; }
    return null;
}""")
page.wait_for_timeout(2000)
```

For Txt2Img, `button.style` works correctly.

**Prevention:** Use `.style-name` click for Img2Img mode. Use `button.style` click for Txt2Img mode. After opening, verify the panel has non-zero dimensions before attempting to select a style.

---

## 12. Amazon Product Name Regex Matches Model Numbers

**Symptom:** Product name extraction truncates at model numbers containing dashes (e.g., "Sony WH-1000XM5" becomes "Sony WH").

**Root Cause:** Bare `-` in the regex terminator character class matches hyphens inside model numbers. The regex splits on any dash, not just spaced dashes used as separators.

**Fix:** Use spaced dash pattern instead of bare dash:
```python
# Wrong -- matches model number dashes
re.split(r'[\-\—,|]', product_name)

# Correct -- only matches dashes with surrounding spaces
re.split(r'\s+[\-\—]\s+|[,|]', product_name)
```

**Prevention:** Always use `\s+[\-\—]\s+` for dash terminators in product name regex patterns. Test against model numbers like "WH-1000XM5", "AirPods-Pro", "RT-AX86U".

---

## 13. Download Too Small

**Symptom:** Downloaded image file exists but is under 1KB. Image viewers show a broken/empty file.

**Root Cause:** The download URL returned an error page, redirect, or empty response instead of the actual image. This can happen when the generation result hasn't fully propagated to the CDN, or the URL was captured before the image was ready.

**Fix:**
```python
import os

downloaded_path = "/path/to/image.webp"
size = os.path.getsize(downloaded_path)
if size < 1024:  # Less than 1KB
    raise ValueError(f"Download failed: {downloaded_path} is only {size} bytes")
# Retry: wait 5s and re-download from the result URL
```

**Prevention:** Always validate file size after download. Minimum expected size for a Dzine result image is ~50KB (typical: 200KB-2MB). Wait at least 3 seconds after generation completes before downloading. Retry once if the file is under 1KB.

---

## 14. Canvas Not Loaded

**Symptom:** Sidebar tool clicks do nothing. Panel opens but Generate button is disabled. Coordinate-based clicks miss their targets.

**Root Cause:** The canvas editor hasn't fully loaded. The sidebar tool-group icons are the last elements to render. If fewer than 5 `.tool-group` elements are present, the page is still loading.

**Fix:**
```python
# Wait for canvas to fully load
page.wait_for_selector('.tool-group:nth-child(5)', timeout=15000)
page.wait_for_timeout(2000)  # Extra buffer for async DOM setup

# Verify
tool_count = page.locator('.tool-group').count()
if tool_count < 5:
    raise RuntimeError(f"Canvas not loaded: only {tool_count} tool-groups found (need 5+)")
```

**Prevention:** After navigating to `/canvas?id=...`, always wait for at least 5 `.tool-group` elements before any interaction. Set viewport to 1440x900 immediately after page load -- sidebar positions shift at other viewports.

---

## 15. Generation Button Disabled

**Symptom:** Generate button (`#txt2img-generate-btn`, `#chat-editor-generate-btn`, or panel generate) is present but `disabled`. Clicking it does nothing.

**Root Cause:** No content on canvas (for Img2Img), required prompt field is empty, or a prerequisite is not met (e.g., no character selected, no face image for Face Match, Lip Sync missing audio).

**Fix:**
```python
# Check if generate button is enabled
is_disabled = page.evaluate("""() => {
    for (const btn of document.querySelectorAll('button')) {
        var text = (btn.innerText || '').trim();
        if (text.includes('Generate') && !btn.disabled &&
            btn.getBoundingClientRect().x > 60 && btn.getBoundingClientRect().width > 0) {
            return false;  // Found an enabled Generate button
        }
    }
    return true;  // All Generate buttons are disabled
}""")
if is_disabled:
    # Diagnose: check prompt, canvas layers, character selection
    raise RuntimeError("Generate button disabled. Check: prompt filled, canvas has content, character selected.")
```

**Prevention:** Before clicking Generate, verify: (1) prompt textarea is not empty, (2) canvas has at least one layer for Img2Img, (3) character is selected for CC mode, (4) face image is set for Face Match, (5) audio is uploaded for Lip Sync. The button's `disabled` attribute reflects missing prerequisites.

---

## 16. Img2Img Does NOT Preserve Products

**Symptom:** Img2Img with 98% Structure Match generates completely different objects. The output looks nothing like the original product photo -- different shape, different details, different product entirely.

**Root Cause:** Img2Img is a style transfer tool, not a product preservation tool. Even with maximum Structure Match (98%) and Color Match enabled, it transforms the product into something entirely different. The "structure" it preserves is coarse spatial layout (edges, shapes), not fine product details like logos, buttons, ports, or textures.

**Fix:** Use Generative Expand instead of Img2Img for product-faithful images:
1. Amazon photo -> "Start from an image" on Dzine home -> creates new project
2. BG Remove (action bar, ~9s, free, produces transparent background)
3. Generative Expand 16:9 + studio backdrop prompt (8 credits, ~36s, 4 variants)
4. Export PNG 2x (no watermark)

See **SOP 5: PRODUCT_FAITHFUL** in `dzine_sop.md` for the full step-by-step procedure.

**Prevention:** NEVER use Img2Img for product-faithful images. Img2Img is only suitable for artistic style transfers where the output does not need to resemble the input product. For any image where the real product must be recognizable, use BG Remove + Generative Expand (SOP 5).

---

## 17. "Image Not Filling the Canvas" Dialog Blocks Generation

**Symptom:** After clicking Generate for Expand or Img2Img, generation stalls at 0% or 30%. No progress. The generation appears to be running but never completes.

**Root Cause:** A modal dialog "Image Not Filling the Canvas" appears asking whether to continue as-is or fit the image to content. This dialog blocks all generation until dismissed. It is easy to miss because it may appear behind other UI elements or briefly.

**Fix:** Handle in `close_dialogs()`:
```python
fit_btn = page.locator('button:has-text("Fit to Content and Continue")')
if fit_btn.count() > 0 and fit_btn.first.is_visible(timeout=500):
    fit_btn.first.click()
```

**Prevention:** Always check for this dialog before and during generation polling. Add "Fit to Content and Continue" to the `close_all_dialogs()` handler alongside "Not now", "Close", "Got it", etc. Check for it:
- Immediately after BG Remove completes
- Immediately after clicking any Generate button
- During generation polling (if progress stalls at 0% for >10s)

---

## 18. Enhance & Upscale "Please select one layer on canvas"

**Symptom:** Upscale button clicked but nothing happens. Warning text "Please select one layer on canvas" appears in the Enhance & Upscale panel.

**Root Cause:** No layer is selected on the canvas. The Enhance & Upscale feature requires exactly one layer to be selected before it can process the image.

**Fix:** Click on the product image on the canvas to select it before opening the Enhance panel:
```python
# Click canvas center to select the layer
page.mouse.click(700, 400)
page.wait_for_timeout(500)

# Verify selection handles appear
handles = page.locator('.transform-handle, .selection-box, [class*="select"]')
if handles.count() == 0:
    # Try clicking directly on a visible layer element
    page.evaluate("""() => {
        var layers = document.querySelectorAll('.layer-item, [class*="layer"]');
        if (layers.length > 0) layers[0].click();
    }""")
    page.wait_for_timeout(500)

# Now open Enhance & Upscale
page.mouse.click(40, 628)
```

**Prevention:** Always click the canvas center (or the specific product area) and verify that selection handles appear before opening the Enhance & Upscale panel. If the canvas has multiple layers, click the specific layer you want to upscale.

---

## 19. Enhance & Upscale from Sidebar Requires Unlocked Layer

**Symptom:** "Please select one layer on canvas" warning persists even after clicking canvas, double-clicking, using Ctrl+A, clicking in Layers panel, and dispatching JS events. None of these approaches fix the selection requirement.

**Root cause:** Project creation via "Start from an image" creates Layer 1 with the `locked` CSS class (`layer-item locked {uuid}`). Locked layers cannot be selected for Enhance & Upscale via the sidebar.

**Workaround (CONFIRMED P136):** Use the **Results panel numbered buttons** instead. Each result set shows action rows: Chat Editor [1-4], Image Editor [1-4], AI Video [1-4], Lip Sync [1-3], Expression Edit [1-4], Face Swap [1-4], Enhance & Upscale [1-4]. Clicking a numbered button next to "Enhance & Upscale" opens a centered popup dialog with Precision/Creative mode, scale factor (1.5x-4x), format (PNG/JPG), and an "Upscale" button (4 credits). This bypasses the canvas layer selection requirement entirely.

**Alternative:** Export canvas at 4x scale (PNG format) produces acceptable quality without using Enhance credits.
