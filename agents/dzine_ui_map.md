# Dzine Canvas UI Map -- Automation Quick Reference

Last updated: 2026-02-13 (Parts 21-35)

---

## Home Page / Project Creation

- **URL:** `https://www.dzine.ai/home`
- **"Start from an image" button:** `.project-item` containing text "start from an image", at approximately (435, 469). Clicking triggers a native file chooser -- use `page.expect_file_chooser()` to intercept and set the product image file.
- **"New project" button:** `.project-item` at approximately (741, 469). Creates a blank canvas with no initial image.
- **After creation:** Dzine redirects to `/canvas?id={new_id}` where `{new_id}` is a unique project ID. A project setup dialog may appear offering aspect ratio selection (1:1, 3:4, 9:16, 4:3, 16:9, Custom). Dismiss or select as needed.

```python
# Create project from Amazon product photo
page.goto("https://www.dzine.ai/home")
page.wait_for_timeout(2000)
start_btn = page.locator('.project-item:has-text("start from an image")').first
with page.expect_file_chooser(timeout=5000) as fc_info:
    start_btn.click()
fc = fc_info.value
fc.set_files(str(product_image_path))
# Wait for redirect to /canvas?id=...
page.wait_for_selector('.tool-group:nth-child(5)', timeout=15000)
```

---

## 1. Canvas Layout

- **URL:** `https://www.dzine.ai/canvas?id=<project_id>`
- **Viewport:** 1440x900 (MUST be exact -- all coordinates assume this)
- **4 zones:**
  - Left sidebar (x=0-64, 12 tool icons)
  - Center canvas (`#canvas`, image composition area)
  - Right panel (Results tab / Layers tab, `.header-item.item-result` / `.header-item.item-layers`)
  - Bottom bar (Chat Editor -- prompt + model + generate)
- **Top bar (P150 confirmed):**
  - Size button `button.size` at (123,8) — shows canvas dims (e.g. "999 x 1536")
  - Tools container `div.tools` at (239,6):
    - Move `#tool-move` at (283,6) 36x36
    - Text `#tool-text` at (327,6) 36x36
    - Draw `.tool-item.draw-dropbox` at (371,6) 36x36
    - Shape `.tool-item` at (415,6) 36x36
    - Hand `#tool-hand` at (459,6) 36x36
  - Undo `button.undo` at (914,11) — often DISABLED
  - Redo `button.redo` at (950,11) — often DISABLED
  - Zoom button at (990,11) — shows percentage (e.g. "43%")
  - Export `button.export` in top-right
- **Layer Action Bar (P172 confirmed):**
  Appears when a layer is selected on canvas. Container: `.layer-tools` (`.disabled` when no layer). Located at y~79-82.

  | Tool | Selector | Position | Notes |
  |------|----------|----------|-------|
  | Select | `.item.select-tool` | (405,79) 32x32 | Selection tool |
  | AI Eraser | `.item.remove` | (454,82) 63x27 | Quick eraser |
  | Hand Repair | `.item.hand-repair` | (521,82) 81x27 | Quick hand fix |
  | Expression | `.item.face-editor` | (606,82) 74x27 | Quick expression edit |
  | **BG Remove** | `.item.removebg` | (684,82) 77x27 | Background removal (FREE) |
  | Cutout | `.item.cutout` | (778,79) 32x32 | |
  | (icon) | `.item` | (814,81) 28x28 | |
  | Crop | `.item.crop` | (846,79) 32x32 | |
  | SVG | `.item.svg` | (895,79) 32x32 | |
  | Gen 3D | `.item.gen-3d` | (931,79) 32x32 | |
  | Save as Asset | `.item.save_as_asset` | (967,79) 32x32 | |
  | Download | `.item.download` | (1003,79) 32x32 | |

  **Note:** Action bar shows "Please select a layer" when disabled.

---

## 2. Left Sidebar (all at x=40)

All tool-groups at x=8, width=64. Click center at x=40 (sidebar icon strip center x=20, but x=40 works reliably for all items).

**Verified sidebar order from DOM text content matching (P24):** Upload, Assets, Txt2Img, Img2Img, Character, AI Video, Lip Sync (HOT badge), Video Editor, Motion Control, Enhance & Upscale (NEW badge), Image Editor, Instant Storyboard.

```python
# Click any sidebar tool
page.mouse.click(40, y_position)
page.wait_for_timeout(2500)
```

| # | Tool | y | x | Size | Icon Class | Panel Type |
|---|------|---|---|------|------------|------------|
| 1 | Upload | 81 | 40 | 64x49 | `.tool-item.import` | File picker (no panel) |
| 2 | Assets | 136 | 40 | 64x49 | | `.panels.show` |
| 3 | Txt2Img | 197 | 40 | 64x49 | | `.c-gen-config.show` |
| 4 | Img2Img | 252 | 40 | 64x49 | | `.c-gen-config.show` (`.img2img-config-panel`) |
| 5 | Character | 306 | 40 | 64x49 | | `.panels.show` overview, `.c-gen-config.show` sub-features |
| 6 | AI Video | 361 | 40 | 64x49 | | `.panels.show` + `.c-gen-config.show` (`.ai-video-panel`) |
| 7 | Lip Sync | 427 | 40 | 41x13 | | `.lip-sync-config-panel.show` (wraps entire canvas!) |
| 8 | Video Editor | 490 | 40 | 64x49 | | `.c-gen-config.show` (`.float-video-editor`) |
| 9 | Motion Control | 563 | 40 | 64x25 | | `.c-gen-config.show` (`.float-motion-trans`) |
| 10 | Enhance & Upscale | 630 | 40 | 64x25 | | `.c-gen-config.show` |
| 11 | Image Editor | 698 | 40 | 64x49 | | `.c-gen-config.show` (`.collapse-panel`) |
| 12 | Instant Storyboard | 778 | 40 | 64x25 | | `.c-gen-config.show` (`.float-storyboard-g`) |

---

## 3. Panel Types

### `.c-gen-config.show`
Used by: Txt2Img, Img2Img, Lip Sync (inner config), AI Video, Video Editor, Image Editor, CC sub-features.
Fixed at left side, z-index ~400.

### `.panels.show`
Used by: Assets, Character overview, AI Video, Motion Control, Enhance & Upscale, Storyboard.
Fixed at (80, 49), 264x850. Content swaps dynamically when switching tools.

### Panel Toggle Technique
After page load, clicking a tool may show an intro card instead of the active panel. Fix:
```python
page.mouse.click(40, 778)  # Click distant tool (Storyboard)
page.wait_for_timeout(1500)
page.mouse.click(40, TARGET_Y)  # Click target tool
page.wait_for_timeout(2000)
```
Always toggle from a **distant** tool -- adjacent tools may not trigger the switch.

**CRITICAL: Character sub-panel is sticky.** After opening a Character collapse-option (Generate Images, Insert Character, etc.), the `.collapse-panel` class prevents other sidebar tools from replacing the panel. The only reliable fix is **page reload**:
```python
page.goto(f"https://www.dzine.ai/canvas?id={project_id}")
page.wait_for_timeout(5000)
# Dismiss dialogs, then navigate normally
```
Do NOT try removing `.show` via JS — it breaks panel state permanently until reload.

### Lip Sync Panel (P181 confirmed — updated layout)

`.lip-sync-config-panel.show.lip-sync-panel-v2` — now a compact left panel (not full-canvas overlay as before).

| Element | Position | Notes |
|---------|----------|-------|
| Close | X button at top-right of panel | `.ico-close` |
| Generation Mode: Normal | Radio option | "Basic-quality lip sync" |
| Generation Mode: **Pro** | Radio option (selected) | "Better movement & clarity" (default) |
| Output Quality: **720p** | `button.options.selected` at (116,309) | Default |
| Output Quality: 1080p | `button.options` at (226,309) | Higher quality |
| Generate | `button.generative` at (104,357) 240x48 | **36 credits**, DISABLED until face uploaded |
| Pick a Face Image | `button.pick-image` at (653,404) 270x44 | Opens Pick Image dialog |
| Upload a Face Video | `button.pick-image.pick-video` at (653,498) 270x44 | Opens video upload |

**Precondition:** "Please pick a face image or video." — must upload face first.

**Advanced Lip Sync Capabilities (from video studies):**

| Feature | Details |
|---------|---------|
| Simultaneous faces | Up to 4 faces detected and animated independently |
| Timeline editor | Multi-speaker dialogue ordering — assign voices per face, sequence entries |
| Custom voice import | Upload your own voice recordings (e.g., ElevenLabs TTS output) |
| Built-in TTS voices | Dzine's own text-to-speech voices, selectable per dialogue entry |
| Character limit | 400 characters per dialogue entry |
| Speed slider | Adjustable voice pace for each dialogue segment |
| Language dropdown | Multilingual support — select language per dialogue |
| Generation time | 5-10 minutes for Pro mode |
| Normal mode | 720p output, faster generation |
| Pro mode | 1080p output, better movement and clarity, 36 credits |

**Multi-Speaker Workflow:**
1. Upload face image/video with multiple visible faces
2. Dzine auto-detects up to 4 faces
3. Assign a voice (custom upload or built-in TTS) to each detected face
4. Add dialogue entries per face in the timeline editor
5. Set speed and language per entry
6. Order entries in the timeline for conversation flow
7. Generate (36 credits for Pro) -- 5-10 min processing

**Close before switching tools:**
```python
page.evaluate("""() => {
    var p = document.querySelector('.lip-sync-config-panel.show');
    if (p) { var c = p.querySelector('.ico-close'); if (c) { c.click(); return; } p.classList.remove('show'); }
}""")
```

---

## 4. Key Selectors

### Txt2Img Panel (P171 confirmed)
| Element | Selector / Position | Notes |
|---------|---------------------|-------|
| Style button | `button.style` at (92,97) 192x40 | Opens style picker (79+ styles) |
| Style create | `button.create-style` at (292,97) 40x40 | Create new style shortcut |
| Style name | `.style-name` | Current model name (e.g. "Dzine General") |
| Prompt | `TEXTAREA.len-1800` at (101,162) 222x90 | 1800 chars, supports 20 languages |
| Prompt expand | `.switch-popup.ico-maximize` at (299,252) 24x24 | Full-screen prompt editor |
| Prompt Improver | `.c-switch` 24x16 at (299,297) | Small toggle — auto-improves prompt, OFF by default |
| Aspect ratio | `.c-aspect-ratio .item.canvas` | Default: canvas-size |
| Ratio options | `.c-aspect-ratio` buttons | 999x1536, 3:4, 1:1, 4:3, canvas |
| Ratio presets | `.item.more` | Expands: Custom, Facebook 16:9, Instagram 4:5, Twitter 4:3, TikTok 9:16, Desktop 16:9, Mobile 9:16, TV 2:1, Square 1:1 |
| Face Match | `.c-switch` 36x20 at (288,434) | NEW label, OFF by default |
| Color Match | `.c-switch` 36x20 at (288,482) | OFF by default |
| Non-Explicit | `.c-switch.isChecked` 36x20 at (288,530) | ON by default — filters NSFW content |
| Mode Fast | `button.options` at (104,610) 69x24 | 2 credits |
| Mode Normal | `button.options.selected` at (177,610) 69x24 | 4 credits (default) |
| Mode HQ | `button.options` at (251,610) 69x24 | 8 credits |
| Advanced | `.advanced-btn` at (92,658) 240x39 | Expandable — Seed only (no negative prompt!) |
| Seed | `INPUT.input` at (378,155) 248x40 | "Enter a seed number" placeholder, inside Advanced popup |
| Generate | `#txt2img-generate-btn` / `.generative.ready` at (92,710) 240x48 | Shows credit cost |

**Note:** Txt2Img Advanced only has Seed. Negative Prompt is only available in Img2Img.

### Nano Banana Pro Panel (P182 confirmed — DIFFERENT layout!)

When Nano Banana Pro is selected, the Txt2Img panel changes significantly:

| Element | Selector / Position | Notes |
|---------|---------------------|-------|
| Model | `button.style` showing banana icon + "Nano Banana Pro" | Yellow banana icon |
| Prompt | `TEXTAREA.len-1800` | Same 1800 chars |
| Prompt Improver | `.c-switch` | Toggle, OFF by default |
| **Output Quality** | `button.options` at y=378: 1K (104,378) / **2K** (177,378) / 4K (251,378) | **Replaces Fast/Normal/HQ!** 2K default |
| Aspect Ratio | `.c-aspect-ratio` at y=462: 9:16 (104,466) / **1:1** (168,466) / 16:9 (232,466) / more (296,466) | Default: 2048x2048 at 1:1 |
| Non-Explicit | `.c-switch` | Toggle, OFF by default |
| Generate | `.generative.ready` | **20 credits** at 2K |

**Aspect Ratio Details (P185 confirmed — clicking works via JS):**
- Container: `.c-aspect-ratio` / `.ratios` at (100, 462) 224x32
- 9:16 → `DIV.item` at (104, 466) 60x24
- 1:1 → `DIV.item.selected` at (168, 466) 60x24 (default)
- 16:9 → `DIV.item` at (232, 466) 60x24 — produces **2720x1530** at 2K
- More → dropdown arrow at (296, 466) 24x24

```python
# Click 16:9 aspect ratio (reliable method)
page.evaluate("""() => {
    var panel = document.querySelector('.c-gen-config.show');
    if (!panel) return;
    for (var el of panel.querySelectorAll('[class*="aspect"] *, [class*="ratio"] *')) {
        if ((el.innerText || '').trim() === '16:9') { el.click(); return; }
    }
}""")
```

**4K NBP Confirmed Working (P21):**
- Txt2Img + Nano Banana Pro + 4K + 16:9 = **5440x3060 pixels**
- Costs **40 credits**
- Generate button text: "Generate\n40"

**Key differences from Dzine General:**
- **No Face Match / Color Match** toggles
- **Resolution tiers** (1K/2K/4K) instead of speed modes (Fast/Normal/HQ)
- **20 credits** at default 2K (vs 4 credits Normal for Dzine General)
- **40 credits** at 4K
- **1:1 default** aspect ratio at 2048x2048
- **16:9 produces 2720x1530** at 2K, **5440x3060** at 4K (ideal for YouTube thumbnails and video frames)

**Model selection via style picker (P182 confirmed):**
```python
# Open style picker and click Nano Banana Pro thumbnail
page.evaluate("""() => {
    var panel = document.querySelector('.c-gen-config.show');
    var btn = panel.querySelector('button.style');
    btn.click();
}""")
page.wait_for_timeout(2000)
# Find label "Nano Banana Pro" then click 60px above (thumbnail)
nbp_pos = page.evaluate("""() => {
    var picker = document.querySelector('.style-list-panel');
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
page.keyboard.press('Escape')
```

### Img2Img Panel (P171+P22 confirmed)

**Panel detection:** Text starts with "Image-to-Image" (hyphenated).
**NO file upload** -- uses canvas content as input. Place image on canvas first.

| Element | Selector / Position | Notes |
|---------|---------------------|-------|
| Model | `button.style` at (92,97) 192x40 | Default: "No Style v2", can switch to Nano Banana Pro and others |
| Style create | `button.create-style` at (292,97) 40x40 | Create new style shortcut |
| Prompt | `TEXTAREA.len-1800` at (101,162) 222x90 | 1800 chars, Portuguese placeholder, includes "click Describe Canvas" hint |
| Describe Canvas | `button.autoprompt.visible` at (170,251) 125x26 | Auto-generates prompt from current canvas content |
| Prompt expand | `.switch-popup.ico-maximize` at (299,252) 24x24 | Full-screen prompt editor |
| Structure Match | `.c-slider` at (100,333) 224x32 | Default value 0.5 = "Very similar" (controls structural fidelity to input), has `.ant-slider-handle` thumb |
| Structure value | `INPUT.number` at (100,349) | Numeric input exists but **typing + Enter does NOT propagate** to slider -- use drag instead |
| Color Match | `.c-switch` at (288,393) 36x20 | Toggle (OFF by default) |
| Face Match | `.c-switch` at (288,441) 36x20 | Toggle (OFF by default) |
| Mode Normal | `button.options.selected` at (104,521) 106x24 | 4 credits (default) |
| Mode HQ | `button.options` at (214,521) 106x24 | 8 credits (P23/P24 confirmed) |
| Advanced | `.advanced-btn` at (92,569) 240x39 | Expandable — Negative Prompt + Seed |
| Negative Prompt | `TEXTAREA.len-1800` at (387,169) 230x90 | 1600 chars, "Descreva o que voce nao quer ver na imagem" (Portuguese placeholder) -- **Img2Img only!** |
| Seed | `INPUT.input` at (378,331) 248x40 | "Enter a seed number" placeholder, numeric input |
| Generate | `button.generative.ready` | 4 credits (Normal), yellow button showing credit cost |

Source image = current canvas content. Place image on canvas first.

**Structure Match Slider — Drag Method (P28 confirmed):**

The numeric input field does NOT work (typing + Enter doesn't propagate to the Ant Design slider). Use handle drag instead:

- **Handle:** `.ant-slider-handle` at (212, 341) 10x10px
- **Rail:** `.ant-slider-rail` at (100, 335) 224x12px
- **Rail range:** x=100 (value 0.0) to x=324 (value 1.0)
- **Label text** (Very similar / Similar / Less similar / Different) does NOT update dynamically during drag

```python
# Drag Structure Match slider to desired value (0.0 to 1.0)
target_value = 0.2  # example: 20%
handle_x, handle_y = 212, 341  # current handle position
rail_left, rail_right = 100, 324
target_x = rail_left + (rail_right - rail_left) * target_value

page.mouse.move(handle_x, handle_y)
page.mouse.down()
page.mouse.move(target_x, handle_y, steps=15)
page.mouse.up()
# Tested: drag to 20% -> value=0.2, drag to 80% -> value=0.8
```

**Img2Img Slider Confirmed Values (from video studies):**

> **WARNING:** Img2Img does NOT preserve product identity. Even at 98% Structure Match, it generates completely different objects. For product-faithful images, use BG Remove + Generative Expand (SOP 5). Img2Img is only suitable for **character scenes** (Ray avatar) and **artistic style transfers**.

| Slider | Value | Effect | Use Case |
|--------|-------|--------|----------|
| Style Intensity | 0.6 | Medium — balanced style transfer | Character scenes |
| Style Intensity | 0.2-0.3 | Low — minimal style override | When fidelity matters more |
| Structure Match | 0.6 | Very similar — preserves layout/composition | Character scenes (Ray avatar) |
| Face Match | ON | Preserves facial identity | Always ON for Ray scenes |
| Color Match | ON/OFF toggle | Preserves color palette | ON for consistent lighting |

**Generation Mode:**
- Normal: 4 credits per generation
- HQ: 8-16 credits per generation (higher fidelity)

**Key differences vs Txt2Img:**
- Img2Img has Negative Prompt (1800 chars)
- Only 2 modes: Normal (4 credits) / HQ (8 credits) (no Fast mode)
- NO quality tiers (1K/2K/4K) -- unlike Txt2Img with Nano Banana Pro
- Generates 4 variations per run

### Character Panel — Overview (P172+P24 confirmed)
Panel class: `.c-gen-config.show.collapse-panel`
Sidebar: y=306. Panel opens with title "Character".
2 buttons + 4 collapse-options:

| Feature | Selector / Position | Description |
|---------|---------------------|-------------|
| Build Your Character | `button.create` at (92,97) 240x40 | Opens dialog: Quick Mode (1 image) or Training Mode (multiple images) |
| Manage Your Characters | `button.mgmt` at (92,145) 240x40 | List/edit/delete saved characters |
| Generate Images | `.collapse-option.has-guide` at (92,218) 240x80 | "With your character" — CC generation (4 credits) |
| Insert Character | `.collapse-option` at (92,310) 240x80 | "Into images" — mask + character (28 credits) |
| Character Sheet | `.collapse-option` at (92,402) 240x80 | "From prompt" — multi-pose sheet (4 credits) |
| Generate 360° Video | `.collapse-option` at (92,494) 240x80 | "From a character image" — 360° turnaround (6 credits) |

**Character List (hidden DOM, P24 confirmed):**
`.c-character-list` exists but has 0x0 dimensions. Access via JS:
- Preset characters: Lip Boy, Cat Girl, Cow Cat, Richy, Anna (3D cartoon avatar style)
- Custom character: **Ray** (our trained character)
- Slots: 1 / 60 used

**Build Your Character Dialog (P172 confirmed):**
`.popup-mount-node` full-page overlay (1440x900)
- **Quick Mode**: "Just upload one image! Generate your character in seconds — ideal for quick tests or simple needs."
- **Training Mode**: "Upload multiple images. Our AI deeply learns your character — best for unique, high-quality results."

### Consistent Character (CC) — Generate Images sub-panel (P173 confirmed)

**Activation:** Click "Generate Images" collapse-option in Character panel. Panel header: "Consistent Character".

**Character Selector:**
- Shows: 5 presets (Lip Boy, Cat Girl, Cow Cat, Richy, Anna) + custom characters
- Custom character: **Ray** (Slots Used: 1 / 60)
- `button.btn.add` at (279,142) — add another character
- `button.btn.remove` at (303,142) — remove character

**After selecting Ray (P173 confirmed):**

| Element | Selector / Position | Notes |
|---------|---------------------|-------|
| Back button | `button.back` at (92,65) | Return to Character overview |
| Character Description | `TEXTAREA.len-1800` at (101,191) 222x54 | Auto-filled: "YouTube host presenting headphones, professional studio, confident" (66 chars) |
| Restore | Button near description | Reset description to trained default |
| Description expand | `.switch-popup.ico-maximize` at (299,245) | Full-screen editor |
| Scene prompt | `DIV.custom-textarea.len-1800` at (101,323) 222x90 | contenteditable div, auto-inserts "@Ray" |
| Scene expand | `.switch-popup.ico-maximize` at (299,413) | Full-screen editor |
| Quick Actions | Walk (101,454), Read (137,454), Wave (175,454) | Preset scene buttons |
| Control Mode | Camera (104,531, **default**), Pose (177,531), Reference (251,531) | `button.options` |
| Camera preset | "Auto, Auto" below Control Mode | Camera angle selection |
| Aspect Ratio | 999x1536, 3:4, 1:1, 4:3, canvas | Standard options |
| Style toggle | `.c-switch` at (288,735) | NEW label, OFF by default |
| Non-Explicit | `.c-switch.isChecked` at (288,783) | ON by default |
| Mode Fast | `button.options` at (104,863) | 2 credits |
| Mode Normal | `button.options.selected` at (177,863) | 4 credits (default) |
| Mode HQ | `button.options` at (251,863) | 8 credits |
| Generate | `.generative.ready` at (92,839) 240x48 | "Generate 4" (Normal mode) |

**Character selection via JS (works reliably):**
```python
# Open CC Generate panel
page.mouse.click(40, 778)  # distant tool first (Storyboard)
page.wait_for_timeout(1500)
page.mouse.click(40, 306)  # Character sidebar
page.wait_for_timeout(2500)
# Click Generate Images option
page.evaluate("""() => {
    var p = document.querySelector('.c-gen-config.show') || document.querySelector('.panels.show');
    for (var o of p.querySelectorAll('.collapse-option')) {
        if ((o.innerText || '').includes('Generate Images')) { o.click(); return true; }
    }
    return false;
}""")
page.wait_for_timeout(3000)
# Select Ray
page.evaluate("""() => {
    var list = document.querySelector('.c-character-list');
    for (var item of list.querySelectorAll('.item, button, div')) {
        if ((item.innerText || '').trim() === 'Ray') { item.click(); return true; }
    }
    return false;
}""")
page.wait_for_timeout(2000)
```

### Insert Character Sub-Panel (P172 confirmed)
| Element | Position / Notes |
|---------|-----------------|
| Selection tools | Lasso / Brush / Auto (same as Image Editor tools) |
| Select/Unselect | Mode toggle for selection |
| Choose a Character | Character picker (same hidden `.c-character-list`) |
| Character Action & Scene | Prompt textarea, 0/1800 chars |
| Quick Actions | Walk, Read, Wave buttons |
| Camera | "Auto, Auto" — camera angle presets |
| Generate | 28 credits, DISABLED until editing area marked |

Precondition: "Please mark the editing area." — user must lasso/brush an area on canvas first.

### Character Sheet Sub-Panel (P172 confirmed)
| Element | Notes |
|---------|-------|
| Model | Dzine 3D Render v2 (hardcoded, not user-selectable) |
| Prompt | 0/1800 chars |
| Aspect Ratio | 1536x864, 16:9, 2:1, 4:3 |
| Face Match | Toggle (NEW label) |
| Generation Mode | Fast / Normal / HQ |
| Advanced | Expandable section |
| Generate | 4 credits |

Generates multi-pose character sheet from text prompt. Useful for creating consistent reference images.

### Character Tool — Generate Panel (P28 confirmed)

Full details of the Character Generate sub-panel when opened from sidebar:

**Character List:**
- Lip Boy (Preset), Cat Girl (Preset), Cow Cat (Preset), Richy (Preset), Anna (Preset), Ray (custom)

**Pose Presets:** Walk, Read, Wave

**Camera Types:** Camera (default selected), Pose, Reference

**View:** Auto (default), Front View, Back View, Left View, Right View

**Framing:** Auto (default), Close Up, Upper Body, Full Body, Wide Shot

**Image Upload:** Pick Image, Custom

**Style:** Dzine 3D Render v2

**Quality:** Fast / Normal (default selected) / HQ

**Cost:** 4 credits (Normal)

**Generate button text:** "Generate 4" (generates 4 images)

### Image Editor Panel (P151+P154+P24 confirmed)
Panel class: `.c-gen-config.show.collapse-panel`
Sidebar: y=698. Panel opens with title "Image Editor".
Two sections: **AI Editor** and **Face Kit**:

| Section | Sub-tool | Button class | Position (P28) | Notes |
|---------|----------|-------------|----------------|-------|
| AI Editor | Local Edit | `collapse-option has-guide` | (149, 197) | Inpainting with selection |
| AI Editor | Insert Object | `collapse-option` | — | Add objects to canvas, 4 credits |
| AI Editor | AI Eraser | `collapse-option` | — | Remove objects, 9 credits |
| AI Editor | Hand Repair | `collapse-option` | (275, 329) | Fix hand anatomy |
| AI Editor | Expand | `collapse-option` | — | Generative expand/outpaint, 8 credits |
| Face Kit | Face Swap | `collapse-option has-guide` | — | Swap faces, 4 credits |
| Face Kit | Face Repair | `collapse-option` | (275, 633) | Fix face quality |
| Face Kit | Expression Edit | `collapse-option` | (149, 765) | Change expressions, 4 credits |
| Product Background | Background | Below Face Kit | — | Generate product backgrounds |

#### Local Edit Sub-Panel (P154 confirmed)
| Element | Selector / Position | Notes |
|---------|---------------------|-------|
| Lasso tool | `.item.lasso.active` at (104,137) | Default selection mode |
| Brush tool | `.item.brush` at (177,137) | Paint selection area |
| Auto tool | `.item.auto` at (251,137) | AI auto-select region |
| Select/Unselect | Buttons at y=196 | Toggle select/deselect mode |
| Invert | Button at (252,196) | Invert selection mask |
| Clear | Button at (288,196) | Clear selection |
| Prompt | `textarea` at (101,265) 222x90 | 1800 chars, "Describe desired content in marked area (supports 20 languages)" |
| Style | "No Style v2" button | Default style for inpainting |
| Control Method | Prompt / Balanced / Image | 3 control modes |
| Generate | `.generative` at (92,540) | 4 credits, DISABLED until area marked |

#### Insert Object Sub-Panel (P154+P28 confirmed)
| Element | Selector / Position | Notes |
|---------|---------------------|-------|
| Selection tools | Lasso / Brush / Auto | Same as Local Edit |
| Select/Unselect/Invert | Mode toggles | Toggle select/deselect/invert mode |
| Reference Object | `.pick-image` | "Pick an image" — upload object reference |
| Prompt | `textarea` at (101,371) 222x50 | Portuguese: "Descreva o objeto de referencia (opcional)" |
| Generate | `.generative` at (92,466) | 4 credits, DISABLED until area marked |

#### Generative Expand Sub-Panel (P169+P28+P154 confirmed)
| Element | Selector / Position | Notes |
|---------|---------------------|-------|
| Expand Aspect Ratio | Grid of 9 buttons in `.c-options` | 1:1, 4:3, 3:2, 16:9, 2:1, 3:4, 2:3, 9:16, 1:2 |
| Prompt | `textarea.len-1800` at (109,230) | Optional, 1800 chars, "Describe image content (optional) (supports 20 languages)" |
| Generate | `div.btn-generate` or `.generative.ready` | 8 credits, yellow bg when ready. Button class changes when enabled. |
| Canvas mode | Edge-dragging | "Expand your canvas by dragging the edges" — interactive expansion |
| Panel body | `#expand-generate-btn-panel` | Contains all controls |
| Back button | `button.back` | Returns to Image Editor overview |

**Behavior notes (P154):**
- Clicking a ratio button **immediately resizes the canvas** (e.g. 9:16 changes canvas to 1536x2731)
- Generation **automatically removes background first** ("Removing background..." spinner visible) — no need to BG Remove separately before expanding
- Panel navigates back to Image Editor overview after generation starts
- Results appear in Results panel (4 variants)
- URL pattern: `static.dzine.ai/stylar_product/p/{project_id}/outpaint/{n}_output_{timestamp}.webp`

#### AI Eraser Sub-Panel (P169+P28 confirmed)
| Element | Selector / Position | Notes |
|---------|---------------------|-------|
| Selection tools | Lasso / Brush / Auto | Same as Local Edit |
| Select/Unselect | Mode toggle | Toggle select/deselect mode |
| Selection Guide | Banner at top | Tooltip for selection |
| Prompt | `textarea` 222x90 | Optional, max 1800 chars, "Describe what you want to remove in marked area" |
| Generate | `.generative` | 9 credits, DISABLED until area marked |

#### Hand Repair Sub-Panel (P169 confirmed)
| Element | Selector / Position | Notes |
|---------|---------------------|-------|
| Selection tools | Lasso / Brush / Auto | Same as others |
| Generate | `.generative` | 4 credits, DISABLED until area marked |
| Notes | No prompt, no style | Simplest sub-tool — just mark and generate |

#### Face Swap Sub-Panel (P169+P28 confirmed)
| Element | Selector / Position | Notes |
|---------|---------------------|-------|
| New Face upload | `.pick-image` / `.upload-image-btn` | "Upload a Face Image" button |
| Status message | Text | "Please upload a new face" when no face uploaded |
| Generate | `.generative` | 4 credits, DISABLED until face uploaded |

#### Face Repair Sub-Panel (P169 confirmed)
| Element | Selector / Position | Notes |
|---------|---------------------|-------|
| Selection tools | Lasso / Brush / Auto | Same as others |
| Prompt | `textarea` 222x90 | "Describe desired facial features (supports 20 languages)" |
| Preserve Original Face | `.c-slider` | Slider: "Strongly similar" |
| Generate | `.generative` | 4 credits, DISABLED until area marked |

#### Expression Edit Sub-Panel (P169 confirmed, updated from video studies)
Comprehensive facial expression control with fine-grained sliders. 4 credits per generation.

**Two modes:**
- **Custom mode**: Fine-grained control via individual sliders (Eyes, Mouth, Head sections)
- **Template mode**: Pre-made expression presets (happy, sad, surprised, etc.) — one-click application

| Section | Slider | Range | Labels |
|---------|--------|-------|--------|
| - | Choose face | - | "Choose a face from the canvas" / Pick Image dialog |
| - | Mode | Custom / Template | Two tabs |
| Eyes | Eye Openness | slider, default 0 | Closed <-> Open |
| Eyes | Horiz. Eye Gaze | slider, default 0 | Left <-> Right |
| Eyes | Vert. Eye Gaze | slider, default 0 | Up <-> Down |
| Eyes | Eyebrow | slider, default 0 | Lower <-> Higher |
| Eyes | Wink | slider, default 0 | No Wink <-> Wink |
| Mouth | Lip Openness | slider, default 0 | Closed <-> Open |
| Mouth | Pouting | slider, default 0 | Left <-> Right |
| Mouth | Pursing | slider, default 0 | Relaxed <-> Pursed |
| Mouth | Grin | slider, default 0 | Neutral <-> Grin |
| Head Angles | Yaw | slider, default 0 | Left <-> Right rotation |
| Head Angles | Pitch | slider, default 0 | Down <-> Up tilt |
| Head Angles | Roll | slider, default 0 | Counter-clockwise <-> Clockwise |

Pick Image dialog: "Drop or select images here" OR "choose an image on the canvas" (shows canvas layer thumbnails).

**Cost:** 4 credits per expression edit generation. Available both from Image Editor panel and from Results panel action buttons.

#### Product Background
**NOT a sub-tool in Image Editor.** The Image Editor panel contains exactly 8 sub-tools: Local Edit, Insert Object, AI Eraser, Hand Repair, Expand, Face Swap, Face Repair, Expression Edit. Product Background is a separate feature — either accessed via BG Remove in the top action bar, or via the Dzine Product Background web tool at `dzine.ai/tools/ai-product-background-generator/`.

### Enhance & Upscale Sidebar (P151 confirmed)
Panel class: `.c-gen-config.show`

| Element | Selector / Position | Notes |
|---------|---------------------|-------|
| Image tab | `button.options.selected` at (96,101) | Default tab |
| Video tab | `button.options` at (214,101) | Video upscaling |
| Precision Mode | `button.option.selected` at (104,189) | Default enhance mode |
| Creative Mode | `button.option` at (104,217) | Alternative mode |
| Scale 1.5x | `button.options.selected` at (104,305) | Default |
| Scale 2x/3x/4x | `button.options` at (159/214/269,305) | |
| Format PNG | `button.options` at (104,401) | |
| Format JPG | `button.options.selected` at (214,401) | Default format |
| Upscale | `button.generative.ready` at (92,457) | DISABLED until canvas layer selected |

Requires selecting a layer on canvas first: "Please select one layer on canvas"

### Chat Editor (Bottom Bar)
| Element | Selector | Notes |
|---------|----------|-------|
| Prompt | `[contenteditable='true'].custom-textarea.len-5000` | 5000 chars |
| Prompt alt | `[contenteditable='true'][data-prompt='true']` | |
| Model button | `button.option-btn` at (400,963) | Opens `div.option-list` |
| Model item | `div.option-item` | e.g. `:has-text("Nano Banana Pro")` |
| Ref upload | `button.upload-image-btn.image-item` | |
| Generate | `#chat-editor-generate-btn` at (894,963) | 20 credits |

### Layers Panel (P173 confirmed)

Switch to Layers tab: click `.header-item` containing "Layer" text (or `.header-item.layers`).

**Layer system limitations (confirmed via research):**
- **No blend modes** — layers are simple stacking composites, not Photoshop-style blends
- **No layer groups/folders** — flat list only
- **No layer masks** — masking is done via AI tools (Generative Fill, Insert Object, BG Remove)
- **No layer effects** — no drop shadow, stroke, glow, etc.
- **No drag-to-reorder** — layer order determined by creation order (newest on top)
- **PSD export available** — Export dialog offers PSD format to preserve layer structure for external editing
- **Place on canvas**: `.handle-item.place-on-canvas` — creates a new layer from a result image

| Element | Selector | Notes |
|---------|----------|-------|
| Layers tab | `.header-item.layers` | Right panel tab |
| Layer item | `.layer-item` | Each layer row, 314x64 |
| Locked layer | `.layer-item.locked` | Lock icon shown |
| Background | `.layer-item.layer-color-picker-` | Special layer: "Background No Fill" |

Example canvas state:
- Layer 2 (locked) at (1108,109) — top layer
- Layer 1 (locked) at (1108,185) — middle layer
- Background "No Fill" at (1109,262) — always bottom

Click a layer row to select it on canvas (enables BG Remove, Export, etc.).

### Results Panel (Right)
| Element | Selector | Notes |
|---------|----------|-------|
| Results tab | `.header-item.item-result` | |
| Layers tab | `.header-item.item-layers` | |
| Result images | `.result-panel img, .material-v2-result-content img, .result-item img` | |
| Image URLs | `img[src*='static.dzine.ai/stylar_product/p/']` | Full-res, no auth needed |
| Progress | Text matching `/^\d{1,3}%$/` in Results panel | 3% -> 75% -> gone |
| No results | `text="No Results Available"` | |
| Preview | `#result-preview` | Blocks clicks -- Escape to close |
| Preview download | `#result-preview button:nth-child(4)` | |
| Privacy toggle | `button.privacy_level.private` | Per result entry |
| Delete result | `button.handle-btn.del` | |

Result actions per image (9 total): Variation, Insert Character, Chat Editor, Image Editor, AI Video, Lip Sync, Expression Edit, Face Swap, Enhance & Upscale.

**Complete Results Panel Action Chain (P34/P35 confirmed):**

*Image-to-Image results (per variation, numbered 1-4):*
- Variation: 1, 2, 3
- Chat Editor
- Image Editor: 1, 2, 3, 4
- AI Video: 1, 2, 3, 4

*Txt2Img result actions:*
Chat Editor, Image Editor, AI Video, Lip Sync, Expression Edit, Face Swap, Enhance & Upscale.

*Image-to-Video result actions (P34/P35 confirmed):*
- Lip Sync at (1250, 436)
- Sound Effects at (1250, 472)
- Video Editor at (1250, 508)
- Motion Control at (1250, 544)
- Download at (1250, 734)
- Video Enhance & Upscale at (1250, 810)

**WARNING (P35 confirmed):** Lip Sync and Sound Effects buttons on video results did NOT open sidebar panels when clicked via coordinates. They may require a different UI approach (JS click, or clicking from a different panel state).

(Download appears in the video result actions list at (1250, 734), separate from image download.)

### Style Picker (P171 confirmed)
| Element | Selector | Notes |
|---------|----------|-------|
| Panel | `.style-list-panel` at (208,128) 1024x692 | Opens on `button.style` click |
| Search input | `.style-list-panel input[type="text"]` | Search by name |
| Style item | `[class*='style-item']` | Clickable thumbnails |
| Categories (18) | Favorites, My Styles, Recent, All styles, General, Realistic, Illustration, Portrait, 3D, Anime, Line Art, Material Art, Logo & Icon, Character, Scene, Interior, Tattoo, Legacy | Left sidebar tabs |
| Quick Style | `div:has-text("Quick Style")` | "Instantly swap a style from one reference image in seconds" |
| Pro Style | `div:has-text("Pro Style")` | "Carefully learn a style from reference images in minutes" |
| Subsections | "Dzine Styles" / "Community" | Toggle between official and user styles |
| My Styles tab | Shows Quick Styles list, "No Recent Styles" if empty | User-created styles |

Close: press `Escape` or click outside panel.

### Export
| Element | Selector | Notes |
|---------|----------|-------|
| Export button | `button.export` | Disabled when no canvas layers |
| Size cancel | `button.cancel:has-text("Cancel")` | |
| Size apply | `button.done:has-text("Apply")` | |
| Width | `input[type='number']:first-of-type` | |
| Height | `input[type='number']:last-of-type` | |

### Canvas
| Element | Selector |
|---------|----------|
| Canvas | `#canvas` |
| Upload zone | `text="CLICK, DRAG or PASTE here to upload assets"` |

---

## 5. Dialog Handling

Promotional popups and tutorials appear on every page load. Close them before any interaction:

```python
def close_all_dialogs(page):
    for _ in range(8):
        found = False
        for text in ["Not now", "Close", "Never show again", "Got it", "Skip", "Later"]:
            try:
                btn = page.locator(f'button:has-text("{text}")')
                if btn.count() > 0:
                    btn.first.click(timeout=1000)
                    found = True
            except:
                pass
        if not found:
            break
```

Other dismissals:
- Size dialog: `button.cancel:has-text("Cancel")` or `button.done:has-text("Apply")`
- Result preview: press `Escape`
- AI Eraser tutorial: can push sidebar to negative x -- always close after load

---

## Generation Workflow (P174 confirmed end-to-end)

**Txt2Img Fast test:** 2 credits, 18 seconds, 2 images generated.

**Result URL pattern:** `https://static.dzine.ai/stylar_product/p/{project_id}/outpaint/{n}_output_{timestamp}.webp`

**Polling technique:**
```python
before = page.evaluate("""() => document.querySelectorAll("img[src*='static.dzine.ai/stylar_product/p/']").length""")
# ... click Generate ...
while time.time() - start < 90:
    time.sleep(3)
    after = page.evaluate("""() => document.querySelectorAll("img[src*='static.dzine.ai/stylar_product/p/']").length""")
    if after > before:
        break
```

**Progress indicator:** Right panel shows `{n}%` text (e.g. "25%") during generation. Match with regex `/^\d{1,3}%$/` on elements with `x > 1000`.

**Results per generation:** Fast=2 images, Normal=2 images, HQ=2 images.

**Result actions (per image):** Variation, Chat Editor, Image Editor, AI Video, Lip Sync, Expression Edit, Face Swap, Enhance & Upscale — each with numbered buttons [1][2].

**Important:** After navigating away from Character sub-panel, RELOAD the page before using other tools.

---

## 6. Credit Costs

| Action | Credits | Time |
|--------|---------|------|
| Txt2Img Fast (Dzine General) | 2 | ~15-20s |
| Txt2Img Normal (Dzine General) | 4 | ~30-40s |
| Txt2Img HQ (Dzine General) | 8 | ~50-120s |
| Img2Img Normal (Dzine General) | 4 | ~30-40s |
| Img2Img HQ (Dzine General) | 8 | ~50-120s |
| **Nano Banana Pro 1K** | **20** | ~40-50s |
| **Nano Banana Pro 2K** | **20** | ~40-50s |
| **Nano Banana Pro 4K** | **40** | ~60-90s |
| Chat Editor | 20 | ~30-60s |
| CC Generate | 4 | ~39s (2 images) |
| CC Insert Character | 28 | |
| CC Character Sheet | 4 | |
| CC 360 Video | 6 | |
| Lip Sync | 36 | ~60-180s |
| Video Editor | 30 (Runway default) | varies |
| BG Remove | 0 (free) | ~11s |
| Generative Expand | 8 | ~75s |
| Insert Object | 4 | ~30s |
| AI Eraser | 9 | ~30s |
| Hand Repair | 4 | ~20s |
| Face Swap | 4 | ~20s |
| Face Repair | 4 | ~20s |
| Expression Edit | 4 | ~20s |
| Enhance & Upscale | 4 | ~25s |
| AI Video (Wan 2.1) | 6 | ~60s |
| AI Video (Seedance Pro Fast) | 7-35 | ~60s |
| AI Video (Minimax Hailuo 2.3) | 56-98 | ~120s |
| AI Video (Reference/Vidu Q1) | 85 | ~120s |
| Motion Control (Kling 2.6) | 28 | varies |
| Sound Effects (post-video) | 5 | ~30s |

Master plan: Unlimited fast image credits. Prefer Txt2Img Normal (4 credits) over Chat Editor (20 credits) for product images.

**Credits display format (P21-22 confirmed):**
- Header shows: "Unlimited / 8.788" (example)
- Format: **image credits / video credits** (display units, multiply by 1000 for actual credits)
- Location: header bar (x > 900, y < 50)

**Credit tracking (P24):**
- Before P24: 8.788
- After Hailuo 2.3 video: 8.732 (used 0.056 = 56 credits)

---

## BG Remove (P177 confirmed end-to-end)

- **Location:** Layer Action Bar at y~82 (see Canvas Layout section), positioned after AI Eraser, Hand Repair, Expression
- **Selector:** `.item.removebg` at (684,82) 77x27
- **Precondition:** A layer MUST be selected first. Select via Layers panel: `document.querySelector('.layer-item').click()`
- **Behavior:** Click -> "Removing background..." overlay appears -> transparent checkerboard background replaces original background (~9 seconds)
- **Credits:** None (free feature)
- **Result:** Product isolated with transparent background, ready for Generative Expand or Export
- **Post-action:** May trigger "Image Not Filling the Canvas" dialog -- must click "Fit to Content and Continue" (yellow button) to proceed

```python
# Click BG Remove
bg_btn = page.locator('button:has-text("BG Remove")').first
bg_btn.click()
# Wait for background removal to complete (~9s)
page.wait_for_timeout(10000)
# Handle "Image Not Filling the Canvas" dialog if it appears
fit_btn = page.locator('button:has-text("Fit to Content and Continue")')
if fit_btn.count() > 0 and fit_btn.first.is_visible(timeout=2000):
    fit_btn.first.click()
```

---

## Export Dialog (P151 confirmed)

- **Triggered by:** Export button in the top right of canvas (y<40), selector `button.export`
- **Precondition:** Canvas must have at least one layer; button is disabled when canvas is empty
- **Dialog:** Full-screen overlay at (0,0) 1440x900
- **Layout:**
  - File Type buttons at y=320: JPG (544,320), **PNG** (634,320, active by default), SVG (724,320), PSD (814,320, "New" badge)
  - Upscale buttons at y=398: **1x** (544,398, active by default), 1.5x, 2x, 3x, 4x — shows canvas dimensions (e.g. "999 x 1536")
  - Watermark toggle at y=454: `button.watermark.watermark-remove` at (544,454)
  - Three download options:
    1. **"Export canvas as image"** at (544,494) — `button.generate.ready` — main export
    2. **"Zip and download SHOWN layers"** at (544,550) — exports visible layers as ZIP
    3. **"Zip and download ALL layers"** at (544,606) — exports all layers as ZIP

```python
# Open export dialog
page.locator('button.export').click()
page.wait_for_timeout(1000)

# Select PNG format (already default)
page.evaluate("""() => {
    for (var btn of document.querySelectorAll('button')) {
        if ((btn.innerText || '').trim() === 'PNG' && !btn.className.includes('active')) btn.click();
    }
}""")

# Select 2x upscale
page.evaluate("""() => {
    for (var btn of document.querySelectorAll('button')) {
        if ((btn.innerText || '').trim() === '2x') { btn.click(); return; }
    }
}""")

# Ensure watermark is unchecked (check button class)
page.evaluate("""() => {
    var btn = document.querySelector('button.watermark');
    if (btn && !btn.className.includes('watermark-remove')) btn.click();
}""")

# Click export
with page.expect_download(timeout=30000) as dl_info:
    page.evaluate("""() => {
        for (var btn of document.querySelectorAll('button')) {
            if ((btn.innerText || '').trim() === 'Export canvas as image') { btn.click(); return; }
        }
    }""")
download = dl_info.value
download.save_as(str(output_path))
```

---

## Results Panel Actions (P138/P138b confirmed)

- **Location:** Right side panel, below the result thumbnails
- **Toggle:** Click "Results" tab header (vs "Layers")
- **Actions per result set:** Each row has a label (x=1120, width=146px, height=16px) and numbered buttons [1] [2] [3] [4] corresponding to the 4 result images.
- **WARNING:** Y positions shift by ~28px depending on whether left sidebar panels are open or closed. Values below are for sidebar panels open (primary) and closed (in parentheses).

| Action | Label y | Center y | Shifted y (panels closed) |
|--------|---------|----------|---------------------------|
| Chat Editor | 649 | 657 | ~621 |
| Image Editor | 685 | 693 | ~657 |
| AI Video | 721 | 729 | ~693 |
| Lip Sync | 757 | 765 | ~729 |
| Expression Edit | 793 | 801 | ~765 |
| Face Swap | 829 | 837 | ~801 |
| Enhance & Upscale | 865 | 873 | ~837 |

- **Numbered button X coords:** [1] at x~1291, [2] at x~1328, [3] at x~1366, [4] at x~1403
- **Button classes:** `"btn"` = numbered buttons (clickable), `"selected-btn"` = icon/label button (DO NOT click -- opens sidebar panel, not popup)
- **Parent container class:** `"btn-container"`
- **Icon button** at (1246, ~888) opens sidebar panel, NOT the popup -- avoid this

**IMPORTANT:** MUST click numbered buttons via JavaScript (`el.click()`), not mouse coordinates, because positions shift with sidebar state.

```python
# Enhance a specific result (bypasses canvas layer selection)
# Switch to Results tab
page.evaluate("""() => {
    for (var el of document.querySelectorAll('[class*="header-item"]')) {
        if ((el.innerText || '').includes('Result')) { el.click(); return; }
    }
}""")
page.wait_for_timeout(500)

# Click Enhance & Upscale button [1] via JS (reliable regardless of sidebar state)
page.evaluate("""() => {
    var btns = document.querySelectorAll('.btn-container .btn');
    for (var btn of btns) {
        var row = btn.closest('[class*="action"]') || btn.parentElement;
        if (row && (row.innerText || '').includes('Enhance')) {
            btn.click(); return true;
        }
    }
    return false;
}""")
page.wait_for_timeout(2000)
# Popup dialog opens at center screen -> configure and click Upscale
```

---

## AI Video Panel (P140-P146 confirmed)

- **Sidebar icon:** #6 at y=361
- **Panel class:** `.ai-video-panel`
- **Activation:** Click sidebar icon at `(40, 361)`. Opens both `.panels.show` and `.c-gen-config.show`.

### Modes

Two top-level modes:
- **Key Frame** (default) -- generate video from a start frame image
- **Reference** -- generate video from a reference image

### Frame Modes (Key Frame)

- **Start and Last** -- provide a start frame (and optionally a last frame)
- **AnyFrame** -- provide any reference frame

### Model Selector

- **Trigger:** `.custom-selector-wrapper` -- click to open `.selector-panel`
- **Popup:** 695x583 overlay with scrollable `.panel-body`
- **Catalog sorted by credit cost:**

| Model | Credits | Duration | Resolution |
|-------|---------|----------|------------|
| Wan 2.1 | 6 | 5s | 540x832 (720p) |
| Seedance Pro Fast | 7-35 | 5s | - |
| Wan 2.5 | 7-21 | /s | 1080p |
| Dzine Video V1 | 10 | 5s | - |
| Seedance 1.5 Pro | 12-56 | 5s | - |
| Dzine Video V2 | 20 | 5s | - |
| Kling 2.5 Turbo STD | 30 | 5s | 720p |
| Runway Gen4 turbo | 46 | 5s | - |
| Minimax Hailuo 2.3 | 56-98 | 6s | - |
| Sora 2 | 100 | 4s | - |
| Google Veo 3.1 Fast | 200-304 | 8s | 1080p |

### Key Controls (Key Frame Mode)

| Element | Selector / Position | Notes |
|---------|---------------------|-------|
| Start Frame upload | `button.pick-image.has-guide` at (101, 218) | Opens Pick Image dialog |
| End Frame upload | `button.pick-image.disabled` at (218, 218) | Disabled until start frame set |
| Prompt | `textarea.len-1800` at (101, 299) | 1800 chars |
| Model selector | `.custom-selector-wrapper` at (92, 434) 240x48 | Click center (212, 458) to open model overlay |
| Resolution/Duration | Text display (e.g. "Auto · 720p · 5s") | Read-only, model-dependent |
| Camera section | `.camera-movement-btn` at (92, 554) 240x48 | Click center (212, 578) to expand motion presets |
| Video credits | Text at panel bottom | e.g. "8.850 video credits left" + "Buy more" link |
| Generate | `.generative.ready` | Shows credit cost for selected model |

### Model Selector Popup (P170 confirmed)

Trigger: click center of `.custom-selector-wrapper` at (212, 458).
Overlay: scrollable popup with all video models, organized by name/credits/duration/resolution/tags.

**Complete catalog (36+ models, sorted by credits):**

| Model | Credits | Duration | Resolution | Tags |
|-------|---------|----------|------------|------|
| Wan 2.1 | 6 | 5s | 720p | Uncensored |
| Seedance Pro Fast | 7-35 | 5s | — | Uncensored |
| Wan 2.5 | 7-21 | /s | 1080p | Uncensored |
| Dzine Video V1 | 10 | 5s | — | Uncensored |
| Seedance 1.5 Pro | 12-56 | 5s | — | Uncensored |
| Wan 2.6 | 14-21 | /s | 1080p | Uncensored |
| Seedance Lite | 15-80 | 5s | 1080p | — |
| Dzine Video V2 | 20 | 5s | — | Uncensored |
| Wan 2.2 Flash | 20-50 | 5s | — | — |
| Seedance Pro | 25-120 | 5s | 1080p | Uncensored |
| Kling 2.5 Turbo STD | 30 | 5s | 720p | — |
| Kling 2.1 Std | 37 | 5s | — | — |
| Kling 1.6 standard | 37 | 5s | — | — |
| Luma Ray 2 flash | 45 | 5s | — | — |
| Runway Gen4 turbo | 46 | 5s | — | — |
| Wan 2.2 | 50-100 | 5s | — | Uncensored |
| PixVerse V5 | 50 | 5s | 1080p | — |
| Minimax Hailuo 2.3 | 56-98 | 6s | — | Uncensored |
| Minimax Hailuo 02 | 56-98 | 6s | 1080p | — |
| Minimax Hailuo | 56 | 6s | — | — |
| Kling 2.5 Turbo Pro | 65 | 5s | 1080p | — |
| Kling 2.1 Pro | 75 | 5s | 1080p | — |
| Kling 1.6 pro | 75 | 5s | 1080p | — |
| Kling 2.6 | 85-170 | 5s | 1080p | — |
| Sora 2 | 100 | 4s | — | — |
| Kling 3.0 | 126-168 | 5s | 1080p | — |
| Kling Video O1 | 140 | 5s | 1080p | — |
| Luma Ray 2 | 146 | 5s | — | — |
| Google Veo 3.1 Fast | 200-304 | 8s | 1080p | — |
| Kling 2.1 Master | 215 | 5s | 1080p | — |
| Google Veo 3 Fast | 225 | 8s | — | — |
| Sora 2 Pro | 300-500 | 4s | 1080p | — |
| Google Veo 3.1 | 400-800 | 8s | 1080p | — |
| Google Veo 3 | 600 | 8s | — | — |

**IMPORTANT (P24 confirmed):** `el.click()` via JavaScript does NOT work for video model selection. Must use `page.mouse.click()` on the specific model item. Default model is Minimax Hailuo 2.3 (56 credits) -- expensive. Scroll and click Wan 2.1 (6 credits) for testing.

To select a model via automation:
```python
# Open model selector
page.mouse.click(212, 458)
page.wait_for_timeout(1000)
# Click desired model by mouse (JS click does NOT work for model items)
pos = page.evaluate("""(name) => {
    for (var el of document.querySelectorAll('*')) {
        if ((el.innerText || '').trim().startsWith(name) && el.offsetHeight > 0 && el.offsetHeight < 60) {
            var r = el.getBoundingClientRect();
            return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
        }
    }
    return null;
}""", model_name)
if pos:
    page.mouse.click(pos['x'], pos['y'])
```

### Camera Motion Presets (P185 confirmed, fully mapped)

Trigger: click center of `.camera-movement-btn` at (212, 578).
Expands to show preset buttons. **Maximum 3 camera movement combinations per clip** (UI enforced).

**Two tabs:** "Cinematic Shots" (default) / "Free Selection"

#### Cinematic Shots Tab (P185 confirmed)
Pre-made camera movement presets with preview thumbnails:

| Preset | Row | Position |
|--------|-----|----------|
| Debut | 1 | (195, 88) |
| Freedom | 1 | (290, 88) |
| Left Circling | 1 | (385, 88) |
| Right Circling | 2 | (195, 155) |
| Upward Tilt | 2 | (290, 155) |
| Left Walking | 2 | (385, 155) |
| Right Walking | 3 | (195, 218) |
| Downward Tilt | 3 | (290, 218) |
| Stage Left | 3 | (385, 218) |

#### Free Selection Tab (P185 confirmed)

Grid of 15 individual camera movements:

**Row 1 (y~232):** 6 movements, each 74x38 card:
| Movement | Position (x,y) | Product Video? |
|----------|---------------|----------------|
| Truck Left | (390, 232) | FORBIDDEN (distortion) |
| Truck Right | (468, 232) | FORBIDDEN (distortion) |
| Pan Left | (558, 232) | Secondary (slow, human only) |
| Pan Right | (636, 232) | Secondary (slow, human only) |
| Push In | (726, 232) | ALLOWED (subtle, product detail) |
| Pull Out | (804, 232) | Avoid |

**Row 2 (y~352):** 6 movements, each 74x38 card:
| Movement | Position (x,y) | Product Video? |
|----------|---------------|----------------|
| Pedestal Up | (390, 352) | FORBIDDEN (unnatural) |
| Pedestal Down | (468, 352) | FORBIDDEN (unnatural) |
| Tilt Up | (558, 352) | FORBIDDEN (unless reveal) |
| Tilt Down | (636, 352) | FORBIDDEN (unless reveal) |
| Zoom In | (726, 352) | ALLOWED (very light only) |
| Zoom Out | (804, 352) | Avoid |

**Row 3 (y~468):** 3 movements, each 160x46 card:
| Movement | Position (x,y) | Product Video? |
|----------|---------------|----------------|
| Shake | (390, 472) | FORBIDDEN |
| Tracking Shot | (558, 472) | Secondary (very slow only) |
| **Static Shot** | (726, 472) | **PRIMARY DEFAULT** |

Each card has: container `selection-item` (160x112, thumbnail+card) → `selection-options` (160x46, clickable) → `option` (inner card) → `option-name` (text label).

**Active state (P189 confirmed): `selected-option` class on `.option` child, NOT on parent `.selection-item`.**

The Camera row in the left panel also shows the selected movement name (e.g., "Static shot").

**Clicking via `page.mouse.click()` on `.selection-options` center WORKS (P189 confirmed):**
```python
# Select a camera movement (e.g., Static Shot)
movement_name = "Static Shot"
pos = page.evaluate("""(name) => {
    var items = document.querySelectorAll('.selection-item');
    for (var item of items) {
        if ((item.innerText || '').trim().includes(name)) {
            var opts = item.querySelector('.selection-options');
            if (opts) {
                var rect = opts.getBoundingClientRect();
                return {x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)};
            }
        }
    }
    return null;
}""", movement_name)
if pos:
    page.mouse.click(pos['x'], pos['y'])

# Verify selection
is_selected = page.evaluate("""(name) => {
    var items = document.querySelectorAll('.selection-item');
    for (var item of items) {
        if ((item.innerText || '').includes(name)) {
            return !!item.querySelector('.option.selected-option');
        }
    }
    return false;
}""", movement_name)
```

**IMPORTANT:** `el.click()` via JavaScript does NOT work for camera buttons. Must use `page.mouse.click(x, y)`.

**Max 2 combinations for production. Default: Static Shot only. If uncertain: Static Shot.**

### Reference Mode (P155 confirmed)

| Element | Selector / Position | Notes |
|---------|---------------------|-------|
| Upload slot | `.pick-image` at (105,162) 51x51 | Upload reference image |
| Prompt | `textarea` at panel | 1800 chars, supports "@" mentions |
| Hints | "2 pics" / "2 pics" / "3 pics" | Layout preset thumbnails |
| Model | "Vidu Q1" (auto-selected) | Reference mode uses different model |
| Settings | "16:9 · 1080p · 5s" | Higher quality than Key Frame |
| Generate | `.generative` | 85 credits! Very expensive |

**@ Mention System (Reference mode):** Use "@" in prompt to reference uploaded elements:
- `@Image1` for appearance/character
- `@Video1` for camera motion/style
- Supports: Character, Object, Background, Layout references

### Start Frame Auto-populate (P180 confirmed end-to-end)

**BEST METHOD:** Click the **AI Video** numbered button [1-4] in the results actions row. This opens the AI Video panel AND auto-populates the start frame.

```python
# Click AI Video [1] for the first result set (auto-populates start frame)
page.evaluate("""() => {
    var containers = document.querySelectorAll('.btn-container');
    for (var c of containers) {
        var parent = c.parentElement;
        var parentText = (parent ? parent.innerText || '' : '').trim();
        if (parentText.startsWith('AI Video')) {
            var rect = c.getBoundingClientRect();
            if (rect.height > 0 && rect.y > 0 && rect.y < 900) {
                var btns = c.querySelectorAll('.btn');
                if (btns.length > 0) { btns[0].click(); return true; }
            }
        }
    }
    return false;
}""")
page.wait_for_timeout(3000)
# Panel opens with start frame populated, Generate ready
```

**Alternative: Pick Image Dialog** — clicking `button.pick-image` opens a full-page dialog:
- "Drop or select images here" — triggers file chooser (unreliable via CDP)
- **"Or choose an image on the canvas"** — shows 3 canvas layer thumbnails (RELIABLE)

### AI Video Generation (P180+P34+P35 confirmed end-to-end)

**Test result (P34):** Wan 2.1, 6 credits, generated in ~70s, saved as MP4 (1.5MB).
- Button [1] at (1313, 834) in AI Video results row triggers generation
- Panel opens with: Key Frame tab (Start and Last / AnyFrame sub-tabs), Reference tab
- Start frame auto-populated from the clicked variation
- Prompt auto-generated from image content (e.g., "Premium wireless headphones slowly rotating..."), 154/1600 chars
- Wan 2.1 pre-selected, Auto 720p 5s, Camera controls available
- Generate button: 6 credits
- Video URL pattern: `https://static.dzine.ai/stylar_product/p/{project_id}/wanimage2v...mp4`
- Download via fetch -> blob -> base64 -> file
- Credits: 8.732 -> 8.726 (6 credits used in P34)
- Result item class: `.result-item.image-to-video-result.hasinfo.completed`

**WARNING (P35 confirmed): Clicking AI Video [1] again QUEUES ANOTHER generation (not just opens panel). Each click costs 6 credits. Be very careful with repeat clicks.**

**Post-generation actions (P35 updated):**
- Lip Sync at (1250, 436)
- Sound Effects at (1250, 472)
- Video Editor at (1250, 508)
- Motion Control at (1250, 544)
- Download at (1250, 734)
- Video Enhance & Upscale at (1250, 810)

Video action buttons are full-width (not numbered like image actions).
Note: Lip Sync and Sound Effects at those coordinates did NOT open sidebar panels in P35 testing -- may need JS click or different panel state.

### Sound Effects Dialog (P189 confirmed)

**Trigger:** Click "Sound Effects" button on a video result in the Results panel.
**Dialog class:** `sound-effects-popup` / `sound-effects-panel` / `dialog`
**Layout:** Center-screen popup over blur backdrop.

| Element | Notes |
|---------|-------|
| Prompt | textarea, 300 chars max, "Enter your prompt (optional)" |
| Negative Prompt | textarea, 300 chars max, "Negative prompt (optional)" |
| Generate | 5 video credits |

**Cost:** 5 video credits. Adds AI-generated sound effects to the video.

```python
# Open Sound Effects dialog
page.evaluate("""() => {
    for (var item of document.querySelectorAll('[class*="result-item"]')) {
        var cls = (typeof item.className === 'string') ? item.className : '';
        if (cls.includes('video') || cls.includes('i2v')) {
            for (var btn of item.querySelectorAll('.btn, button')) {
                if ((btn.innerText || '').trim() === 'Sound Effects') {
                    btn.click(); return true;
                }
            }
        }
    }
    return false;
}""")
page.wait_for_timeout(2000)
# Dialog opens: .sound-effects-popup
# Fill prompt (optional)
page.evaluate("""(prompt) => {
    var popup = document.querySelector('.sound-effects-popup');
    if (!popup) return;
    var ta = popup.querySelector('textarea');
    if (ta) { ta.focus(); ta.value = prompt; ta.dispatchEvent(new Event('input', {bubbles: true})); }
}""", sound_prompt)
# Click Generate (5 video credits)
page.evaluate("""() => {
    var popup = document.querySelector('.sound-effects-popup');
    if (!popup) return;
    for (var btn of popup.querySelectorAll('button')) {
        if ((btn.innerText || '').includes('Generate')) { btn.click(); return; }
    }
}""")
```

### Face Swap from Results (P187 confirmed)

Clicking "Face Swap" on an image result opens the Face Swap sub-panel:
- Auto-places result image on canvas
- Panel: "New Face" (upload face image) + "Target Face" (re-detect faces)
- Cost: 4 credits
- "Please click re-detect faces" if canvas was modified

### Video URL Pattern

Generated video URLs follow:
```
static.dzine.ai/stylar_product/p/{project}/wanimage2video/...mp4
```

### Result

- Result appears in `.result-item.image-to-video-result`
- Post-generation actions (P24 updated): **Lip Sync**, **Sound Effects**, **Video Editor**, **Motion Control**

### Credit System

- Video credits are **separate** from image credits (Master plan provides 8.850 video credits)
- Credits display in header bar alongside image credits

---

## Video Editor Panel (P149 confirmed)

- **Sidebar icon:** #8 at y=490
- **Panel class:** `.c-gen-config.show.float-gen-btn.float-video-editor`
- **Purpose:** Edit existing videos with AI (requires video upload first)
- **Default model:** Runway Gen4 Aleph, 30 credits
- **Settings:** Auto, 720p, 1-5s
- **Prompt:** 1000 chars max
- **Advanced:** Seed number input, expand popup
- **Toolbar:** AI Eraser + select-tool (disabled until video uploaded)
- **Generate:** DISABLED until video uploaded
- **Credit type:** Video credits (shared pool with AI Video)

| Element | Selector / Position | Notes |
|---------|---------------------|-------|
| Video upload | `button.upload-image-btn.image-item` at (105,242) | "Select or Drag a video to edit" |
| Prompt | `.custom-textarea.len-1000` at (101,305) | 1000 chars |
| Model display | Text at (92,440) | Shows current model name |
| Advanced | `button.advanced-btn` at (92,560) | Seed, expand |
| Generate | `button.generative.ready` at (92,648) | 30 credits, DISABLED without video |

---

## Motion Control Panel (P149+P28 confirmed)

- **Sidebar icon:** #9 at y=563
- **Panel class:** `.c-gen-config.show.float-gen-btn.float-motion-trans`
- **Purpose:** Apply motion to character image based on motion video reference
- **Default model:** Kling 2.6 Motion (NOT the same as AI Video's Kling models)
- **Two upload slots:** Motion Video + Character Image
- **Prompt:** 1800 chars max (optional, describes desired video)
- **Character Orientation:** "Matches Video" (default selected) / "Matches Image"
- **Resolution:** Auto / 720p / 1080p (selected)
- **Duration:** 3~30s (selected)
- **Cost:** 28 credits
- **Generate:** DISABLED until video uploaded

| Element | Selector / Position | Notes |
|---------|---------------------|-------|
| Motion Video upload | First upload area | Source motion reference |
| Character Image upload | Second upload area | Character to animate |
| Prompt | `.custom-textarea.len-1800` at (101,328) | Optional description |
| Orientation Video | `button.option.selected` at (108,499) | "Matches Video" (default) |
| Orientation Image | `button.option` at (108,527) | "Matches Image" |
| Resolution | Auto / 720p / **1080p** (selected) | Default: 1080p |
| Duration | 3~30s | Default: 3~30s (selected) |
| Buy more | Button at (291, 652) | Opens credit purchase |
| Generate | `button.generative.ready` at (92,676) | 28 credits |

---

## Instant Storyboard Panel (P149 confirmed, updated from video studies)

- **Sidebar icon:** #12 at y=778
- **Panel class:** `.c-gen-config.show.float-gen-btn.float-storyboard-g`
- **Purpose:** Generate multi-panel storyboard layouts from prompt — combines up to 3 separate images into a unified scene with consistent lighting and shadows
- **Versions:** V1 / V2 (V2 selected by default via `button.options.selected`)
- **Reference:** Optional image upload slot — up to 3 images combined
- **Prompt:** 1000 chars max, supports "@" for reference elements (Character, Object, Background, Layout)
- **Hints:** 3 preset "2 pics" layout thumbnails
- **Aspect Ratio:** 1536x1536 (default), 9:16, 1:1, 16:9
- **Cost:** 15 credits per generation (image credits, not video)
- **Generate:** DISABLED until prompt entered

| Element | Selector / Position | Notes |
|---------|---------------------|-------|
| V1 button | `button.options` at (96,101) | Version 1 |
| V2 button | `button.options.selected` at (214,101) | Version 2 (default) |
| Ref upload | `button.upload-image-btn.image-item` at (105,162) | Optional — up to 3 images |
| Prompt | `.custom-textarea.len-1000` at (101,242) | 1000 chars, supports @mentions |
| Aspect Ratio | Buttons at y=519 area | 9:16, 1:1, 16:9, 1536x1536 |
| Generate | `button.generative.ready` at (92,519) | 15 credits |

**@Mention System (from video studies):**
- Upload images to the reference slots (up to 3)
- In the prompt, use `@Image1`, `@Image2`, `@Image3` to reference uploaded images
- Example: `@Image1 and @Image2 standing in a modern office, professional lighting, unified scene`
- Dzine unifies lighting, shadows, and scale across all referenced images
- Useful for combining separately generated characters into a single coherent scene

---

## Chat Editor — Model Catalog (P149+P20 confirmed, 9 total)

Bottom bar models (opened via `button.option-btn`, displayed in `div.option-list`):

| Model | Notes |
|-------|-------|
| GPT Image 1.5 | Latest, likely default |
| Nano Banana Pro | Dzine's own model |
| Nano Banana | Lighter version (default in Chat Editor) |
| Seedream 4.5 | ByteDance |
| Seedream 4.0 | ByteDance |
| FLUX.2 Pro | Black Forest Labs |
| FLUX.2 Flex | Black Forest Labs |
| FLUX.1 Kontext | Black Forest Labs |
| GPT Image 1.0 | OpenAI original |

- Cost: 20 credits per generation (uses image credits)
- Prompt: 5000 chars max via contenteditable div
- Position: prompt at (408,951) 632x40, model btn at (400,963), generate at (894,963)

```python
# Open AI Video panel
page.mouse.click(40, 361)
page.wait_for_timeout(2000)

# Upload start frame
upload_btn = page.locator('button.pick-image.has-guide').first
with page.expect_file_chooser(timeout=5000) as fc_info:
    upload_btn.click()
fc = fc_info.value
fc.set_files(str(start_frame_path))
page.wait_for_timeout(2000)

# Fill prompt
page.locator('textarea.len-1800').click()
page.keyboard.press('Meta+a')
page.keyboard.type(video_prompt, delay=3)

# Click generate
gen_btn = page.locator('.generative.ready').first
gen_btn.click()
```

---

## Enhance & Upscale Popup Dialog (P177 confirmed)

- **Trigger:** Click a numbered `"btn"` button (e.g. [1]) next to "Enhance & Upscale" in the Results panel
- **Location:** Center-screen modal with blur backdrop
- **Contents:**
  - **Title:** "Enhance & Upscale" with X close button
  - **Enhance Mode:** Precision (default, radio) / Creative
  - **Scale Factor:** Shows target resolution (e.g. "1499 × 2304"), 1.5x (default) / 2x / 3x / 4x buttons
  - **Format:** PNG (default) / JPG
  - **Upscale button:** at approximately (600, 600), text "Upscale\n4" (4 credits)
- **Processing:** Starts at 43% immediately, completes in ~25 seconds
- **Result:** New enhanced image appears in Results panel (count increments by 1). URL follows same `static.dzine.ai` pattern.
- **Download size:** ~107KB at 1.5x scale (would be larger at 2x+)
- **Post-enhance:** A "Chat Editor" input may appear at bottom of canvas (cosmetic, ignore)

```python
# After popup opens, select options and click Upscale
# Optional: select 2x scale (default is 1.5x)
page.evaluate("""() => {
    for (var el of document.querySelectorAll('button, [role="button"]')) {
        if ((el.innerText || '').trim() === '2x') { el.click(); return true; }
    }
    return false;
}""")
page.wait_for_timeout(500)

# Click Upscale button (4 credits)
page.evaluate("""() => {
    for (var btn of document.querySelectorAll('button')) {
        if ((btn.innerText || '').includes('Upscale')) { btn.click(); return true; }
    }
    return false;
}""")

# Poll for completion (~25s)
import time
before = page.locator('img[src*="static.dzine.ai/stylar_product/p/"]').count()
start = time.time()
while time.time() - start < 60:
    current = page.locator('img[src*="static.dzine.ai/stylar_product/p/"]').count()
    if current > before:
        break
    page.wait_for_timeout(3000)
```

---

## Additional UI Features (from video studies)

### AI Expand (Outpaint)

AI Expand is the outpainting feature accessible via Image Editor > Expand sub-tool. It extends images beyond their original boundaries while maintaining visual consistency.

- **Access:** Image Editor sidebar (y=698) > Expand collapse-option
- **Cost:** 8 credits per generation (produces 4 variants)
- **Aspect ratios:** 1:1, 4:3, 3:2, 16:9, 2:1, 3:4, 2:3, 9:16, 1:2
- **Interactive mode:** Drag canvas edges to define expansion area
- **Prompt:** Optional — describe what should appear in the expanded area
- **Use case for pipeline:** Expand product images from 1:1 Amazon photos to 16:9 for video frames

### Built-in Prompt Improver

A toggle switch that auto-enhances prompts before sending to the generation model. Available in Txt2Img and Img2Img panels.

- **Selector:** `.c-switch` (small toggle, OFF by default)
- **Position:** Near the prompt textarea, below the expand icon
- **Behavior:** When ON, Dzine automatically rewrites/enhances your prompt with more detail before generation
- **Recommendation:** Keep OFF for product photography (we want precise control), may be useful for creative/artistic shots where more AI interpretation is acceptable

---

## Download from Results (P21-22 findings)

- **Download button** found in result hover actions at approximately (1250, 1240)
- **Standard `page.expect_download()` times out** -- download likely uses blob URL or client-side download mechanism
- **Alternative approaches to explore:**
  1. Right-click save on result image
  2. Extract image URL from DOM (`img[src*='static.dzine.ai']`) and fetch directly via HTTP (no auth needed for static URLs)
  3. Use the Layer Action Bar download button (`.item.download` at (1003,79)) after placing result on canvas
  4. Use Export dialog for canvas-based download
