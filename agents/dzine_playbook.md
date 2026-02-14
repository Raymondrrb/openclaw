# Dzine Playbook — Browser Automation Guide

## Canvas Environment

### URL Structure
- Canvas editor: `https://www.dzine.ai/canvas?id=<project_id>`
- Current project: `id=19797967`
- Community styles: `/community/list/all`
- Pricing: `/pricing/`
- API docs: `/api/`

### Viewport
- **ALWAYS** set `page.set_viewport_size({"width": 1440, "height": 900})`
- Sidebar positions shift at other viewports — all coordinates below assume 1440x900

### Connection
- CDP port: 18800
- Must launch Brave with `--remote-allow-origins=*`
- `connect_or_launch(headless=False)` from `tools/lib/brave_profile.py`

---

## Sidebar Tool Positions (x, y center) — Confirmed Phase 111

At 1440x900 viewport, all tool-groups at x=8, width=64:

| Tool | Bounding Box (y, h) | Center (x, y) | Label | Icon Class |
|------|---------------------|---------------|-------|------------|
| Upload | y=57, h=49 | (40, 81) | Upload | `.tool-item.import` |
| Assets | y=112, h=49 | (40, 136) | Assets | |
| Txt2Img | y=173, h=49 | (40, 197) | Txt2Img | |
| Img2Img | y=228, h=49 | (40, 252) | Img2Img | |
| Character | y=282, h=49 | (40, 306) | Character | |
| AI Video | y=337, h=49 | (40, 361) | AI Video | |
| Lip Sync | y=391, h=69 | (40, 425) | Lip Sync (HOT) | |
| Video Editor | y=466, h=49 | (40, 490) | Video Editor | |
| Motion Control | y=520, h=61 | (40, 551) | Motion Control | |
| Enhance & Upscale | y=587, h=81 | (40, 628) | Enhance & Upscale (NEW) | |
| Image Editor | y=674, h=49 | (40, 698) | Image Editor | |
| Instant Storyboard | y=736, h=61 | (40, 766) | Instant Storyboard | |

### Tool Opening Technique (Phase 96-98)

- **`page.mouse.click(x, y)` at center of tool-group WORKS reliably** for opening panels
- **`.tool-group.click()` via JavaScript does NOT reliably open panels** — always prefer mouse click
- **Lip Sync blocking issue:** The `lip-sync-config-panel` wraps the entire canvas area (1360x850), blocking toolbar clicks when open. Must close it first (`.ico-close` or `classList.remove('show')`) before switching tools.
- **Switching FROM Lip Sync:** Always close the Lip Sync panel explicitly before clicking a new tool on the sidebar

```python
# Close Lip Sync panel before switching tools
page.evaluate("""() => {
    var panel = document.querySelector('.lip-sync-config-panel.show');
    if (panel) {
        var close = panel.querySelector('.ico-close');
        if (close) { close.click(); return 'closed via X'; }
        panel.classList.remove('show');
        return 'closed via classList';
    }
    return 'not open';
}""")
page.wait_for_timeout(500)
# Now safe to click another sidebar tool
page.mouse.click(40, 252)  # e.g., Img2Img
```

---

## Generation Modes & Credits

| Mode | Credits | Max Prompt | Notes |
|------|---------|-----------|-------|
| Txt2Img | 4-20 | 1800 chars | 4 for Realistic Product, 20 for default |
| Img2Img | 20 | 1800 chars | Requires canvas image, 1K/2K/4K quality |
| Consistent Character | 4 | 1800 chars | Maintains Ray identity, 2 outputs |
| Character Sheet | 4 | 1800 chars | Dzine 3D Render v2, multi-angle sheet |
| Insert Character | 28 | 1800 chars | Mask-based, requires marking area |
| Generate 360° Video | 6 | — | 5s/10s from character image |
| Chat Editor | 20 | 5000 chars | Bottom bar, model selection |
| AI Video (Key Frame) | 56 | 1800 chars | Minimax Hailuo 2.3, 768p, 6s |
| AI Video (Reference) | 85 | 1800 chars | Vidu Q1, 1080p, 5s |
| Lip Sync | 36 | — | Normal/Pro, 720p/1080p |
| Video Editor | 30 | 1000 chars | Runway Gen4, 1-5s |
| Motion Control | 28 | 1800 chars | Kling 2.6, 1080p, 3-30s |
| Insert Object | 4 | 150 chars | Reference image + mask, short prompt |
| Generative Expand | 8 | 1800 chars | 8 aspect ratios, drag edges |
| Hand Repair | 4 | — | Mask only, no prompt |
| Face Swap | 4 | — | Upload face only, no mask |
| Face Repair | 4 | 1800 chars | Mask + prompt + Preserve slider |
| Enhance & Upscale | 9 | — | 1.5x-4x, Precision/Creative |
| Instant Storyboard | 6 | 1000 chars | V1/V2, 2 pics |

**Current plan:** Master ($59.99/mo) — UNLIMITED image credits, 9,000 video credits

---

## Character Sidebar Menu

The Character sidebar (40, 306) is different from other sidebars — it shows a **menu card** with multiple workflow options, not a direct editing panel.

### Menu Options (after double-click or panel toggle)

| Option | Subtitle | Opens | Class |
|--------|----------|-------|-------|
| **Build Your Character** | (blue button) | Character creation wizard | `button.create` |
| **Manage Your Characters** | (button) | Character library | `button.mgmt` |
| **Generate Images** | With your character | CC active panel (4 credits) | `p` card |
| **Insert Character** | Into Images | Mask-based insertion (28 credits) | `p` card |
| **Character Sheet** | From prompt | Multi-angle sheet (4 credits) | `p` card |
| **Generate 360° Video** | From a character image | 360° turnaround video | `p` card |

### Activating the Menu

```python
# Method 1: Double-click (most reliable)
page.mouse.dblclick(40, 306)
page.wait_for_timeout(2000)

# Method 2: Panel toggle
page.mouse.click(40, 197)   # Txt2Img first
page.wait_for_timeout(500)
page.mouse.click(40, 306)   # Character
page.wait_for_timeout(2000)
```

### Clicking a Menu Option

Each option is a clickable card. Use JS to find and click by text:
```python
page.evaluate("""() => {
    for (const el of document.querySelectorAll('*')) {
        var text = (el.innerText || '').trim();
        var r = el.getBoundingClientRect();
        if (text.includes('Generate Images') && text.includes('With your character')
            && r.x > 60 && r.width > 100 && r.height > 30 && r.height < 80) {
            el.click(); return true;
        }
    }
    return false;
}""")
```

---

## Workflow: Consistent Character (Ray)

This is the PRIMARY method for generating Ray images. Maintains character identity across generations.

**Panel class:** `c-gen-config show float-gen-btn float-c2i-gen-btn`

| Element | CSS Class | Notes |
|---------|-----------|-------|
| Title | `.group.title` h5 | "Consistent Character" |
| Slots | `.slots-used-wrapper` | "Slots Used: 1 / 60" |
| Character chooser | `.character-choose` | Dropdown to select character |
| Build character | `.btn-add` | "Build your character" button |
| Prompt label | `.prompt-title` | "Character Action & Scene" |
| Prompt presets | `.preset-prompt-btn` | Quick buttons: Walk, Read, Wave |
| Character list | `.info` / `.name` | Sidebar: Lip Boy, Cat Girl, Cow Cat, Richy, Anna (presets), **Ray** (custom) |
| Control Mode | `.options` buttons | **Camera** (selected) / Pose / Reference |
| Camera settings | `.camera-title` / `.camera-desc` | "Camera" / "Auto, Auto" |
| Aspect Ratio | `.item` divs | 3:4 / 1:1 / 4:3 / **canvas** (selected, 1536×864) |
| Style | button with NEW badge | Opens style selector |
| Non-Explicit | `.config-param` | Safety toggle |
| Generation Mode | `.options` buttons | Fast / **Normal** (selected) / HQ |
| Generate | button | **4 credits** |

### Step-by-Step

1. **Click Character sidebar** → `page.mouse.click(40, 306)`
2. **Wait** → `page.wait_for_timeout(1500)`
3. **Click "Generate Images" button:**
```python
page.evaluate("""() => {
    for (const btn of document.querySelectorAll('button')) {
        const text = (btn.innerText || '').trim();
        if (text.includes('Generate Images') && text.includes('With your character')) {
            btn.click(); return true;
        }
    }
    return false;
}""")
```
4. **Wait** → `page.wait_for_timeout(2000)`
5. **Select Ray character** (BUTTON element — must use JS click):
```python
page.evaluate("""() => {
    for (const el of document.querySelectorAll('*')) {
        const text = (el.innerText || '').trim();
        if (text === 'Ray' && el.tagName === 'BUTTON') {
            el.click(); return true;
        }
    }
    return false;
}""")
```
6. **Wait** → `page.wait_for_timeout(2000)`
7. **Type scene in textarea** (at ~(101, 200)):
```python
page.mouse.click(101, 200)
page.keyboard.press("Meta+a")
page.keyboard.type(scene_text, delay=5)
```
8. **Set aspect ratio to "canvas"** (16:9 = 1536×864):
```python
page.evaluate("""() => {
    for (const el of document.querySelectorAll('*')) {
        if ((el.innerText || '').trim() === 'canvas' &&
            el.getBoundingClientRect().x > 60 && el.getBoundingClientRect().y > 400) {
            el.click(); return true;
        }
    }
    return false;
}""")
```
9. **Click Generate:**
```python
page.evaluate("""() => {
    for (const btn of document.querySelectorAll('button')) {
        const text = (btn.innerText || '').trim();
        if (text.includes('Generate') && !btn.disabled &&
            btn.getBoundingClientRect().x > 60 && btn.getBoundingClientRect().x < 350) {
            btn.click(); return true;
        }
    }
    return false;
}""")
```
10. **Wait for completion:** Generation is ASYNC (~30-40s at Normal quality). Progress shows as percentage text in the Results panel (3% → 75% → done). Two result variants (1 and 2) are generated per CC request. The progress text disappears when generation completes.

### Ray Character Profile
- Name: Ray
- Description: "Ray, a young adult male with light skin and short dark hair, wearing a charcoal gray t-shirt and dark pants, in realistic style." (125/1800 chars)
- Slot: 1 of 60 used
- Presets: Walk, Read, Wave
- Control Mode: Camera / Pose / Reference
- Camera: Auto, Auto (camera movement settings, clickable)
- Generation Mode: Fast / Normal / HQ (prefer Normal)

### CC Full Active Panel Layout (top to bottom, requires scroll)

| Element | Position | Notes |
|---------|----------|-------|
| Header "Consistent Character" | (80,49) | `gen-config-header` |
| Character selector | (92,97) 240x217 | Shows "Ray" with description |
| Character Action & Scene prompt | (92,346) 240x169 | "Ray" auto-filled (4/1800), name rendered as `.character-mark-span` with zero-width space (Ray\u200B) |
| Presets | (101,490) | Walk / Read / Wave |
| **Control Mode** | (100,563) | Camera(selected) / Pose / Reference |
| Camera settings | (100,607) | "Camera Auto, Auto" (clickable) |
| **Aspect Ratio** | (100,711) | 3:4 / 1:1 / 4:3 / canvas(selected) |
| **Style NEW** | (100,771) | Toggle switch (OFF by default, **requires scroll**) |
| **Non-Explicit** | (100,819) | Toggle switch |
| Generate button | (92,~840) 240x48 | **4 credits** |

**Important:** The Style NEW toggle and Non-Explicit toggle are **below the fold** at 1440x900 viewport. The CC panel sidebar does NOT have a traditional scroll container — these elements exist in the DOM but are clipped by the viewport. They were observable via `scrollIntoView` in some DOM states but are NOT reliably accessible via Playwright at 1440x900.

**Style toggle effect:** When ON, adds a model/style selector to CC generation (defaults to "Dzine 3D Render v2"), allowing styled CC output while maintaining character identity. For automation, skip this toggle — the default CC rendering quality is sufficient for pipeline images.

**Automation workaround:** If Style toggle is needed, use Character Sheet workflow instead (which uses Dzine 3D Render v2 by default).

### CC Aspect Ratios

**Default row:** 3:4, 1:1, 4:3, **canvas** (1536×864 = 16:9) ← use this for YouTube

**"More" dropdown** (click "..." at end of ratio row):
| Preset | Ratio | Category |
|--------|-------|----------|
| canvas | 1536×864 | Default |
| Custom | any | Image Dimensions slider |
| Facebook | 16:9 | Socials |
| Instagram | 4:5 | Socials |
| Twitter | 4:3 | Socials |
| TikTok | 9:16 | Socials |
| Desktop | 16:9 | Devices |
| Mobile | 9:16 | Devices |
| TV | 2:1 | Devices |
| Square | 1:1 | Devices |

### CC Output
- **2 images per generation** (selectable via "1" / "2" buttons)
- Result appears in right Results panel
- Progress shown as percentage (21%, 65%, etc.)
- URLs: `https://static.dzine.ai/stylar_product/p/<project_id>/characterchatfal/...`

---

## Workflow: Txt2Img

For product images where character consistency is NOT needed (product shots, backgrounds).

**Important:** After page load, the Txt2Img sidebar shows an intro card ("Creates an image from a text description"). To enter the active editing panel, use the **panel toggle technique**: click Character sidebar first, then Txt2Img sidebar.

### Step-by-Step

1. **Panel toggle** → activate Txt2Img panel:
```python
page.mouse.click(40, 306)  # Character sidebar (any other tool)
page.wait_for_timeout(500)
page.mouse.click(40, 197)  # Txt2Img sidebar
page.wait_for_timeout(2000)
```
2. **Select model** (optional) → click `button.style` at (92, 97)
3. **Fill prompt textarea** at (101, 162), max 1800 chars:
```python
page.mouse.click(101, 175)
page.keyboard.press("Meta+a")
page.keyboard.type(prompt, delay=3)
```
4. **Set Aspect Ratio** → 3:4 / 1:1 / 4:3 / canvas buttons at y~378
5. **Click Generate** (4 credits for Realistic Product, 20 for others)
6. **Wait** → async, result appears in Results panel

### Txt2Img Active Panel Layout (top to bottom)

| Element | Position | Notes |
|---------|----------|-------|
| Header "Text to Image" | (80,49) | `gen-config-header` |
| Model selector | (92,97) 240x40 | `button.style`, shows model name |
| Prompt textarea | (101,162) 222x90 | `textarea`, placeholder varies by locale |
| Char count | (101,256) | "643 / 1800" |
| Prompt Improver | (93,284) | Toggle switch |
| Aspect Ratio label | (100,346) | "Aspect Ratio" + dimension "1536×864" |
| Ratio buttons | (100,374) | 3:4 / 1:1 / 4:3 / **canvas** (= 16:9 1536×864) |
| Face Match NEW | (92,426) | Toggle switch at x=306 (OFF=rgb(68,68,68)) |
| Color Match | (92,474) | Toggle switch at x=306 |
| Non-Explicit | (92,522) | Toggle switch at x=306 |
| Generation Mode | (92,570) | Fast / Normal / HQ buttons at y~610 |
| Advanced | (92,658) | Popup overlay (opens right at x=362) |
| Generate button | (92,710) 240x48 | Credits vary by model (4 for Realistic Product) |

### Face Match NEW (Txt2Img Feature)

Adds a face reference to maintain face identity in Txt2Img (similar to CC but for non-character images).

1. Toggle Face Match ON: click switch at (306, 444)
2. "Pick a Face" button appears at (100, 466) 224x50 — `button.pick-image`
3. Clicking "Pick a Face" opens the same `div.pick-panel` dialog at (440,197) 560x506
4. Upload via `button.upload` in dialog → `expect_file_chooser()` — **same mechanism as CC Reference**
5. "Single face only" constraint
6. When ON + no face: warning "Face Match needs a face image." and Generate button turns yellow (warning state)

### Color Match (Txt2Img Feature)

Toggle at (306, 554). Simple on/off toggle that constrains the output color palette. No additional controls appear — works with the current generation settings.

### Advanced Section (Txt2Img Feature)

Clicking "Advanced" at (92,658) opens a **popup overlay** to the right at (362,65) 280x146 — NOT an inline expansion.

| Setting | Position | Type |
|---------|----------|------|
| Seed | (378,155) 248x40 | `input[type=text]` placeholder="Enter a seed number" |

- CSS class: `.advanced-content.show`
- Arrow icon at (315,674) — `>` chevron that toggles the popup
- Click Advanced again to close
- **Note:** Available settings depend on the model. "Realistic Product" only shows Seed. Other models may show negative prompt, guidance scale, etc.

### Txt2Img "More" Aspect Ratios

Click the "more" button at (296,378) class `item more` (SVG icon after the ratio row).

Opens "Aspect Ratio" popup dialog (similar to CC "more"):

| Section | Presets |
|---------|---------|
| Image Dimensions | 1536×864 (canvas) + **Custom** button |
| Carousel | Scrollable preset thumbnails |
| **Socials** | Facebook 16:9, Instagram 4:5, Twitter 4:3, TikTok 9:16 |
| **Devices** | Desktop 16:9, Mobile 9:16, TV 2:1, Square 1:1 |

Close button (X) at top-right of popup.

```python
# Open "more" ratios
page.evaluate("""() => {
    var el = document.querySelector('.c-aspect-ratio .item.more');
    if (el) { el.click(); return true; }
    return false;
}""")
```

### Style/Model Selector (Txt2Img)

Click `button.style` (the model name button at top of panel, e.g., "Realistic Product") to open the style selector overlay.

**Panel:** `.style-list-panel` at (208, 128) 1024x692 — full-page overlay with search, categories, and style grid.

**Note (Phase 99):** For Img2Img, the selector is opened by clicking `.style-name` instead of `button.style`. The `.style-list-panel` element exists in DOM with content (6234 bytes) but renders at width=0 in some contexts. For Img2Img, use the `.style-name` click which opens the correct full overlay. See the Img2Img section for details.

**Top section:**
- Search bar ("Search styles")
- **Create a style**: Quick Style (swap from 1 reference image) + Pro Style (learn from multiple references)
- **Tabs:** Dzine Styles (curated) | Community (user-created)

**Category sidebar (left, class `.category-item`):**
1. Favorites
2. My Styles
3. Recent
4. All styles
5. General
6. **Realistic** (28+ styles including Dzine Realistic v3/v2/v1, Realistic, Realistic Product, Sleek Simplicity, Studio Photography, CCD Retro, BW Photo, Vintage Vibe, etc.)
7. Illustration
8. Portrait
9. 3D
10. Anime
11. Line Art
12. Material Art
13. Logo & Icon
14. Character
15. Scene
16. Interior
17. Tattoo
18. Legacy

**Style grid:** 6 columns of thumbnail cards with style names. Click to select. Each style changes the generation model/aesthetic.

```python
# Open style selector
page.evaluate("""() => {
    var p = document.querySelector('.c-gen-config.show');
    if (!p) return null;
    var btn = p.querySelector('button.style');
    if (btn) { btn.click(); return true; }
    return null;
}""")
page.wait_for_timeout(2000)

# Select a style by name
page.evaluate("""() => {
    var sp = document.querySelector('.style-list-panel');
    if (!sp) return null;
    for (var el of sp.querySelectorAll('.item-name, .style-name')) {
        if ((el.innerText || '').trim() === 'Realistic Product') {
            el.click();
            return true;
        }
    }
    return null;
}""")
```

### Panel Activation (Important!)

After page load, clicking the Txt2Img sidebar shows an **intro card** ("Creates an image from a text description") instead of the active panel.

To enter the active editing panel, use the **panel toggle technique**:
```python
# Method 1: Panel toggle (click different tool first)
page.mouse.click(40, 252)  # Img2Img or any other sidebar
page.wait_for_timeout(500)
page.mouse.click(40, 197)  # Then Txt2Img
page.wait_for_timeout(2000)

# Method 2: Double-click the sidebar icon
page.mouse.click(40, 197)
page.wait_for_timeout(200)
page.mouse.click(40, 197)
page.wait_for_timeout(2000)
```

Verify active state by checking for header:
```python
header = page.evaluate("""() => {
    for (const el of document.querySelectorAll('.gen-config-header')) {
        if ((el.innerText || '').includes('Text to Image')) return true;
    }
    return false;
}""")
```

### Panel Architecture (Important!)

Dzine uses **two different panel container systems**:

1. **`.c-gen-config.show`** — Used by **Txt2Img only** (class `c-gen-config show float-gen-btn`)
   - Fixed at left side, z-index ~400
   - Contains model selector, prompt, ratio, Face Match, Color Match, Generation Mode, Advanced
   - Panel toggle: click distant sidebar tool first (e.g., Storyboard), then Txt2Img

2. **`.panels.show`** — Used by all other sidebar tools:
   - Img2Img, AI Video, Lip Sync, Motion Control, Storyboard, Enhance & Upscale, Image Editor, Character, Assets
   - Fixed at (80, 49) 264x850
   - Panel content updates dynamically when switching between these tools
   - Toggle: click a DISTANT tool first (not adjacent), wait 1500ms, then target, wait 2000ms

3. **No panel** — Upload sidebar just triggers file picker / drag-and-drop

**Why adjacent tools don't toggle:** Clicking Txt2Img then Img2Img may not switch because they're in the same panel group. Always toggle from a distant tool (e.g., Storyboard at y=766) to a target tool.

### CSS Class Reference (Txt2Img Panel)

| Class | Element |
|-------|---------|
| `gen-config-header` | Panel header |
| `c-style` | Model selector container |
| `style-name` | Model name text |
| `config-param` | Each setting section wrapper |
| `c-aspect-ratio` | Aspect ratio button row |
| `item canvas selected` | Currently selected ratio |
| `item more` | "More" ratios button (SVG icon) |
| `pick-image` | Upload/pick image button |
| `switch` | Toggle switch buttons |
| `advanced-content show` | Advanced popup when visible |
| `generative ready` | Generate button (ready state) |
| `params` | Parent of Advanced section |

---

## Workflow: Chat Editor

Accessible from the bottom bar. 5000 char prompt limit. Same model as Txt2Img.

1. Click "Describe the desired image" text at bottom (y~808)
2. Contenteditable appears at (408, 951) — may be below viewport
3. Type prompt
4. Click yellow send button
5. Wait for async result

**Note:** Chat editor is less reliable for automation — prefer Txt2Img or CC.

---

## CC Reference Mode (Image Upload)

Dzine does NOT use standard `<input type="file">` elements. The upload mechanism uses Vue.js event handlers that dynamically create and destroy a temporary `<input type="file" accept="image/*">`. Playwright's `expect_file_chooser()` intercepts this.

### CC Panel Layout (y=550 to y=900)

| Element | Position | Notes |
|---------|----------|-------|
| Control Mode row | (100,563) 224x32 | Camera / Pose / Reference |
| Camera button | (104,567) 69x24 | `class="options"` (or `selected`) |
| Pose button | (177,567) 69x24 | `class="options"` (BETA) |
| Reference button | (251,567) 69x24 | `class="options"` (or `selected`) |
| Pick Image button | (100,607) 224x40 | `class="pick-image cc-pick-image"` |
| Reference thumbnail | (104,611) 32x32 | `div.image` with background-image URL |
| Trash icon | (292,619) 16x16 | `class="ico-trash"` — remove reference |
| Aspect Ratio | (100,703) 224x32 | 2:3 / 1:1 / 3:2 / Auto(selected) |
| Resolution label | (265,676) | e.g. "1024x683" |
| Style toggle | (288,763) 36x20 | `button.switch` (OFF by default) |
| Style badge | (161,765) | "NEW" label |
| Non-Explicit toggle | (288,811) 36x20 | `button.switch` |
| Generate button | (92,839) 240x48 | `class="generative ready"` id=`character2img-generate-btn` |
| Credits display | (276,853) | "40" credits |
| Generation Mode | (100,887) 224x32 | Fast / Normal(selected) / HQ |

### Setting a Reference Image (File Upload)

1. Activate Reference mode: click Reference button at (251,567)
2. Click Pick Image button at (100,607) — opens `div.pick-panel` dialog at (440,197) 560x506
3. Dialog contains:
   - `button.upload` at (464,261) 524x80 — "Drop or select images here"
   - `div.image-list` with `button.image-item` thumbnails (canvas images)
4. Upload file:
```python
# Find upload button center
upload_btn = page.evaluate("""() => {
    var panel = document.querySelector('.pick-panel');
    if (!panel) return null;
    var btn = panel.querySelector('button.upload');
    if (!btn) return null;
    var r = btn.getBoundingClientRect();
    return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
}""")
# Trigger file chooser
with page.expect_file_chooser(timeout=5000) as fc_info:
    page.mouse.click(upload_btn['x'], upload_btn['y'])
fc = fc_info.value
fc.set_files(str(image_path))
page.wait_for_timeout(5000)
```

### Setting a Reference Image (Canvas Thumbnail)

Instead of uploading, select an existing canvas image as reference:
```python
# Click the first canvas thumbnail in the Pick Image dialog
page.evaluate("""() => {
    var panel = document.querySelector('.pick-panel');
    if (!panel) return false;
    var item = panel.querySelector('button.image-item');
    if (item) { item.click(); return true; }
    return false;
}""")
```

### Verifying Reference Is Set

After upload/selection, the `div.image` inside Pick Image changes from `class="image empty"` to `class="image"` with a background-image URL:
```python
ref_set = page.evaluate("""() => {
    for (const btn of document.querySelectorAll('button')) {
        var classes = (btn.className || '').toString();
        if (!classes.includes('pick-image')) continue;
        var img = btn.querySelector('.image');
        if (!img) continue;
        return !img.classList.contains('empty');
    }
    return false;
}""")
```

### Clearing a Reference

Click the trash icon that appears when a reference is set:
```python
page.evaluate("""() => {
    var trash = document.querySelector('.pick-image .ico-trash');
    if (trash) { trash.click(); return true; }
    return false;
}""")
```

### Generation Mode

Set Fast / Normal / HQ at y=891:
```python
# mode: "Fast", "Normal", or "HQ"
page.evaluate(f"""() => {{
    for (const btn of document.querySelectorAll('button.options')) {{
        var text = (btn.innerText || '').trim();
        var r = btn.getBoundingClientRect();
        if (text === {json.dumps(mode)} && r.y > 880) {{
            btn.click(); return true;
        }}
    }}
    return false;
}}""")
```

## Img2Img (Image-to-Image) Panel — Complete Workflow (Phases 109-110)

Accessible via sidebar icon at (40, 252). Panel class: `c-gen-config show img2img-config-panel float-gen-btn float-i2i-gen-btn`.

### Panel Elements

| Element | Selector | Position | Details |
|---------|----------|----------|---------|
| Model selector | `button.style` / `.style-name` | (92,97) | Shows current model name, click to open model picker |
| Prompt textarea | `TEXTAREA.len-1800` | (101,162) 222x90 | Portuguese placeholder, 1800 char limit |
| Prompt wrapper | `div.prompt-textarea` | (101,158) 222x94 | Click this to focus textarea |
| Char counter | in `.textarea-extend` | (101,252) | Shows "N / 1800" |
| Describe Canvas | `button.autoprompt.visible` | (170,251) | Auto-generates prompt from canvas content (may timeout) |
| Style Intensity | `.c-slider` (Ant Design) | (100,333) | Slider: "Strong" (rightmost) |
| Structure Match | `.c-slider` (Ant Design) | (100,421) | Slider: "Very similar" (mid-right), has suggest marks |
| Color Match | `.c-switch` toggle | (288,481) | Toggle on/off |
| Face Match | `.c-switch` toggle | (288,529) | Toggle on/off |
| Generation Mode | `.options` buttons | (104,609) | "Normal" (selected) / "HQ" |
| Advanced | `.advanced-btn` | (92,657) | Expandable section containing Seed input |
| Negative prompt | `TEXTAREA.len-1800` | (387,169) | Second textarea, placeholder in Portuguese: "Descreva o que voce nao quer ver na imagem" |
| Seed input | `INPUT.input` | (378,331) | Placeholder: "Enter a seed number" |
| Generate button | `button.generative.ready` | (92,709) 240x48 | Credits vary by model (8 for Realistic Product) |

### Key Discovery: Source Image
Img2Img uses the **current canvas content** as input image. No separate upload needed — whatever is displayed on the canvas becomes the source image.

To use Amazon product photos: place product image on canvas first (via Upload/Assets), then run Img2Img.

### Prompt Input
IMPORTANT: The textarea is a standard HTML `<textarea>`, NOT a contentEditable div. But clicking the wrapper `div.prompt-textarea` and using `page.keyboard.type()` works:

```python
# Click prompt wrapper to focus textarea
page.mouse.click(212, 205)  # center of .prompt-textarea
page.wait_for_timeout(500)
page.keyboard.press("Meta+a")
page.keyboard.type("product photo prompt here", delay=10)
```

### Model Selection
Click `.style-name` to open model picker (same modal as Txt2Img with 218 models across 13 categories).

Tested models:
- **Nano Banana Pro**: Default model, 20 credits
- **Realistic Product**: In "Realistic" category, 8 credits — best for product photography

```python
# Open Img2Img style selector (click the style NAME, not button.style)
page.evaluate("""() => {
    var panel = document.querySelector('.img2img-config-panel');
    if (!panel) return null;
    var name = panel.querySelector('.style-name');
    if (name) { name.click(); return true; }
    return null;
}""")
page.wait_for_timeout(2000)
```

### Generation
- Credits: 8 (Realistic Product), 20 (default Nano Banana Pro)
- Generation is partially async: progress shown in Results panel (0% -> 56% -> 82% -> 95% -> 99%)
- Takes ~60-80 seconds for full completion
- Result appears at top of Results panel with 4 variations
- Result type: `img2imgv2` in the image URL

### Result Actions
Each Img2Img result provides buttons:
- Variation (1, 2, 3, 4) — generate variations of each output
- Chat Editor (1, 2, 3, 4)
- Image Editor (1, 2, 3, 4)
- AI Video
- Lip Sync
- Expression Edit
- Face Swap
- Enhance & Upscale

---

## Results Panel

The right side of the canvas shows Results and Layers as tabs in a shared container (`c-material-library-v2 fixed-width` at z=200).

**Tab headers** at y=65:
- "Results" (h6 at x=1169) — `.header-item.item-results` button in header bar
- "Layers" (h6 at x=1355) — `.header-item.item-layers` button in header bar

### Layers Tab

Shows the canvas layer stack from top to bottom:
- Each layer: `.name-c` div (e.g., "Layer 6", "Layer 5", ... "Layer 1")
- Background: `.layer-color-title` "Background" at the bottom
- Visibility/lock toggles per layer

```python
# Open Layers tab
page.evaluate("() => document.querySelector('.header-item.item-layers')?.click()")
page.wait_for_timeout(1000)
```

### Results Tab

### Result Structure (Phase 91 Confirmed)

Results are in `.c-material-library-v2` panel, class `.result-panel` > `.material-v2-result-content`.

Each generation creates a result group with this DOM hierarchy:
- `.result-item.consistent-character-result` > `.result-content` > `.output-result` > `.result-group.result-length-2`
- Individual result: `.result-content.ratio-gt-133.output-resul`

Each result section contains:
- **Type label:** Text-to-Image, Consistent Character, Character Sheet, etc.
- **Private** badge
- **Result image(s)** — thumbnail(s)
- **9 action rows** per result group, each with `.label` > `.label-text` and `button` "1" / "2":
  1. Variation
  2. Insert Character
  3. Chat Editor
  4. Image Editor
  5. AI Video
  6. Lip Sync
  7. Expression Edit
  8. Face Swap
  9. Enhance & Upscale

For CC results: also has "1" / "2" variant selectors.

### Action Button Behavior

| Action | Behavior | Opens Panel? |
|--------|----------|-------------|
| **Variation** | Direct generation — creates new variation in Results | No |
| **Insert Character** | Opens mask + character editing panel | **Yes** (28 credits) |
| **Chat Editor** | Opens bottom-bar chat for text-guided editing | No (bottom bar) |
| **Image Editor** | Opens Image Editor sidebar tools | **Yes** (sidebar) |
| **AI Video** | Direct generation — creates video from image | No |
| **Lip Sync** | Direct generation — lip sync from image | No |
| **Expression Edit** | Opens expression slider panel | **Yes** (4 credits) |
| **Face Swap** | Direct generation — face swap processing | No |
| **Enhance & Upscale** | Direct generation — upscale processing | No |

**Direct generation** actions create a new result entry in the Results panel with progress indicator. They don't require user input beyond clicking the variant button.

### CC Action Buttons (x positions at 1440x900)

Each CC result shows 9 action rows with variant selectors "1" (x=1274) and "2" (x=1349):

| Action | Label y | Button 1 y | Button 2 y |
|--------|---------|-----------|-----------|
| Variation | 255 | 251 | 251 |
| Insert Character | 291 | 287 | 287 |
| Chat Editor | 327 | 323 | 323 |
| Image Editor | 363 | 359 | 359 |
| AI Video | 399 | 395 | 395 |
| Lip Sync | 435 | 431 | 431 |
| Expression Edit | 471 | 467 | 467 |
| Face Swap | 507 | 503 | 503 |
| Enhance & Upscale | 543 | 539 | 539 |

- Variant buttons are 71x24px, clickable `<BUTTON>` elements
- Click variant "1" or "2" to send that image to the selected action
- Clicking a result image thumbnail places it on the canvas as a new layer (960x540)

### Result Entry Actions

Each result has a header with action icons:

| Icon | Position | Class | Action |
|------|---------|-------|--------|
| **Privacy** | (1209,125) | `button.privacy_level.private` | Toggle Private/Public visibility |
| **Info** | (1364,121) | `button.handle-btn.info` | Show generation details |
| **Delete** | (1392,121) | `button.handle-btn.del` | Delete this result entry |

```python
# Toggle privacy
page.evaluate("""() => {
    var btn = document.querySelector('button.privacy_level');
    if (btn) { btn.click(); return true; }
    return false;
}""")

# Delete a result
page.evaluate("""() => {
    var btn = document.querySelector('button.handle-btn.del');
    if (btn) { btn.click(); return true; }
    return false;
}""")
```

### Per-Variant Action Buttons

Each result variant (the "1"/"2" images) has a row of 4 action buttons (24x24 each):

| Button | Class | Action |
|--------|-------|--------|
| Share | `handle-item share` | Share/publish the image |
| Save as Asset | `handle-item save-as-asset` | Save to project Assets library |
| Download | `handle-item download` | Download single image |
| Place on Canvas | `handle-item place-on-canvas` | Put image on canvas as layer |

```python
# Download a specific result variant
page.evaluate("""() => {
    var btns = document.querySelectorAll('button.handle-item.download');
    if (btns.length > 0) { btns[0].click(); return true; }
    return false;
}""")
```

### Result Image URLs (Phase 91 Confirmed)
- Full pattern: `static.dzine.ai/stylar_product/p/{project_id}/{model}/{index}_output_{timestamp}_{hash}.webp`
- Model types in URLs: `faltxt2img` (CC/Txt2Img), `gemini2text2image` (Gemini-based)
- **IMPORTANT:** Phase 90's detection looking for `/generation/` in URLs was WRONG — the correct pattern is `/stylar_product/p/`
- **Important:** CC results use `faltxt2img` URLs (not `characterchatfal`). Detect new images by total count increase, NOT by URL pattern matching.

---

## Chat Editor Bar

The Chat Editor is a persistent bottom bar on the canvas (always visible):

| Element | Position | Class |
|---------|----------|-------|
| Bar wrapper | (573, 808) 294x68 | `chat-editor-bar-wrapper` |
| Prompt area | (628, 824) | `chat-editor-prompt` — "Describe the desired image" |
| Generate button | (894, 963) 146x32 | `btn-generate` in `chat-editor-footer` |

- **20 credits** per generation, **5000 char** max prompt
- Supports model selection (dropdown)
- The Chat Editor is different from sidebar generation panels — it provides a quick inline editing interface
- Results appear in the Results panel under "Chat Editor" action row

---

## Layers Panel

The right side also has a Layers tab showing canvas layers:
- Layer 1 (image placed on canvas)
- Background (No Fill by default)

Click an image in the results to place it on the canvas as a new layer.

---

## Top Bar

At 1440x900, the top bar shows:

| Element | Position | Clickable | Notes |
|---------|---------|-----------|-------|
| Project name | (56, 8) | Yes | Opens Project Settings dialog |
| Canvas size | (123, 8) | Yes | Opens Project Settings dialog |
| Zoom level | (991, 11) | No | `div.c-scale-ratio` e.g. "77%" — NOT clickable |
| Credits | (1077, 17) | No | "Unlimited" (images) |
| Video credits | (1163, 17) | No | "9,000" |
| Earn Credits | (1213, 12) | Yes | Link |
| **Undo** | (915, 11) | Yes | `button.undo` — same as Cmd+Z |
| **Redo** | (951, 11) | Yes | `button.redo` — same as Cmd+Shift+Z |
| Export | (1328, 12) | Yes | Requires selected canvas layer |
| Results tab | (1096, 49) | Yes | Toggle |
| Layers tab | (1280, 49) | Yes | Toggle |

### Project Settings Dialog (z=1000)

Clicking the project name or canvas size opens a settings dialog:

| Element | Notes |
|---------|-------|
| **Project name** | Text input, default "Untitled" |
| **Aspect ratio** | 6 presets in 2x3 grid |
| **Width** | Number input, e.g. "1536" |
| **Height** | Number input, e.g. "864" |
| Link icon | Between Width/Height — locks aspect ratio |
| **Cancel** | Close without saving |
| **Apply** | Apply changes (yellow button) |

**Aspect Ratio Presets:**
| Row 1 | Row 2 |
|-------|-------|
| 1:1 | 4:3 |
| 3:4 | **16:9** (selected) |
| 9:16 | Custom (pencil icon) |

```python
# Open project settings
page.evaluate("""() => {
    for (const el of document.querySelectorAll('*')) {
        var text = (el.innerText || '').trim();
        var r = el.getBoundingClientRect();
        if (text.includes('1536') && r.y < 35 && r.x > 100) {
            el.click(); return true;
        }
    }
    return false;
}""")
page.wait_for_timeout(1000)

# Change canvas size
page.evaluate("""() => {
    // Click Apply after changing settings
    for (const btn of document.querySelectorAll('button')) {
        if ((btn.innerText || '').trim() === 'Apply') {
            btn.click(); return true;
        }
    }
    return false;
}""")
```

**Export** requires a selected canvas layer. Click a result image first to place it on canvas, then click Export. Without a selected layer, clicking Export shows a `show-message` toast at z=600 instead of the dialog.

### Export Dialog

**CSS:** `.c-export` button at (1328, 12). Clicking opens a dialog (when a layer is selected):

| Element | Options | Notes |
|---------|---------|-------|
| File Type | JPG / **PNG** (selected) / SVG / PSD New | PNG is default |
| Upscale | **1x** / 1.5x / 2x / 3x / 4x | Shows resolution (e.g. "1536×864") |
| Watermark | Checkbox | Toggle watermark on/off |
| **Export canvas as image** | Yellow button | Exports selected layer(s) as single image |
| **Zip and download SHOWN layers** | Button | Downloads visible layers as zip |
| **Zip and download ALL layers** | Button | Downloads all layers as zip |

```python
# Open Export dialog
page.mouse.click(1328, 12)  # Export button in top bar
page.wait_for_timeout(1500)

# Select file type (e.g., PNG)
page.evaluate("""() => {
    for (const el of document.querySelectorAll('*')) {
        var text = (el.innerText || '').trim();
        if (text === 'PNG') { el.click(); return true; }
    }
    return false;
}""")

# Click "Export canvas as image"
page.evaluate("""() => {
    for (const btn of document.querySelectorAll('button')) {
        var text = (btn.innerText || '').trim();
        if (text.includes('Export canvas as image')) { btn.click(); return true; }
    }
    return false;
}""")
```

**Note:** For pipeline automation, direct URL download is preferred over Export (see Image Download Strategy section). Export is useful for final composites with multiple layers.

---

## Lip Sync Panel (Phases 91-98 Confirmed)

Accessible via sidebar icon at (40, 425) using `page.mouse.click(40, 425)`.

**Critical:** The `lip-sync-config-panel show` class wraps the ENTIRE canvas area (1360x850), blocking sidebar toolbar clicks. Must close it explicitly before switching to other tools.

**Panel structure:**
- Outer wrapper: `lip-sync-config-panel show` — covers entire canvas
- Left config panel: `.c-gen-config.show` at (92, 61) 264x382
- Canvas area: `.sync-editor-body` > `.preview-content` > `.preview-inner` > `.pick-wrapper` > `.pick-inner`

**Canvas buttons (inside `.pick-inner`):**
- "Pick a Face Image" — `button.pick-image` (NOT `.pick-video`)
- "Upload a Face Video" — `button.pick-image.pick-video`

| Setting | Options | Position |
|---------|---------|----------|
| Generation Mode: Normal | Basic-quality lip sync | option-title (124, 153) |
| Generation Mode: **Pro** | Better movement & clarity (selected, ico-done) | option (124, 209) |
| Output Quality: **720p** | Button (selected default) | sliding-switch (116, 309) |
| Output Quality: 1080p | Button | (226, 309) |
| Generate | 36 credits | button.generative (104, 357) |
| Close | X button | ico-close (328, 77) |

Warning: "Please pick a face image or video." (class `warning-tips`)

**Note:** Video Editor (sidebar) has its own dedicated panel (class `float-video-editor-gen-btn`), not the Lip Sync panel. They are separate tools.

### Lip Sync Full Workflow (Phases 91-99)

**Step 1: Open Lip Sync tool**
```python
page.mouse.click(40, 425)  # Click Lip Sync sidebar icon
page.wait_for_timeout(2000)
# Verify: lip-sync-config-panel.show should be present
```

**Step 2: Click "Pick a Face Image"**

The `button.pick-image` (NOT `.pick-video`) in the canvas area opens the **"Pick Image" dialog**:
- "Drop or select images here" — file upload area
- "Or choose an image on the canvas" — shows canvas layer thumbnails as clickable images

```python
# Click "Pick a Face Image" button
page.evaluate("""() => {
    var btns = document.querySelectorAll('button.pick-image');
    for (var btn of btns) {
        if (!btn.classList.contains('pick-video')) {
            btn.click(); return true;
        }
    }
    return false;
}""")
page.wait_for_timeout(1500)
```

**Step 3: Select a canvas thumbnail or upload**

Click a canvas thumbnail from the "Pick Image" dialog to proceed.

**Step 4: "Pick a Face" dialog** (`edit-image-dialog`, z=1001)

After selecting an image, the face detection dialog opens:
- Auto-detects faces (yellow rectangle around each face, with "Cancel" on each)
- Status: "1 face selected (Up to 4)"
- **Mark Face Manually** button — for manual selection when auto-detect fails
- **Next** button (yellow) — proceed with selected face(s)
- **Cancel** button — abort

```python
# Click Next to accept detected face(s)
page.evaluate("""() => {
    for (const btn of document.querySelectorAll('button')) {
        if ((btn.innerText || '').trim() === 'Next') {
            btn.click(); return true;
        }
    }
    return false;
}""")
page.wait_for_timeout(1500)
```

**Step 5: Crop step** (same `edit-image-dialog`)

After clicking Next on face selection:
- Aspect ratio options: Original, 1:1, 3:4, 4:5, 9:16, 16:9
- Zoom in/out buttons
- "How Cropping Works" info link
- **Next** / **Cancel** buttons

```python
# Click Next to accept crop
page.evaluate("""() => {
    for (const btn of document.querySelectorAll('button')) {
        if ((btn.innerText || '').trim() === 'Next') {
            btn.click(); return true;
        }
    }
    return false;
}""")
page.wait_for_timeout(2000)
```

**Step 6: Face set in panel — audio upload area should appear**

After cropping, the face is set in the Lip Sync panel. The audio upload step follows.

**Alternative shortcut:** Click "Lip Sync 1" button in the Results panel on any result — this goes directly to the "Pick a Face" dialog (Step 4) with that result image, skipping Steps 1-3.

### Lip Sync Audio — Complete Workflow (Phases 103-108)

**After face is set (Step 6 above), the timeline editor appears:**
- `.timeline-editor.show-editor` at bottom (80,650) 1360x249
- Header: play button + "00:00 / 00:05" (`.play-time`)
- Tracks: "Video" (with face thumbnail) + "Speaker A" (with "Pick a voice" button)
- Panel warning changes to: "Please create or upload a voice."

**Step 7: Click "Pick a voice"**
```python
page.evaluate("() => { var e=document.querySelector('.pick-voice'); if(e){var r=e.getBoundingClientRect(); e.click();} }")
page.wait_for_timeout(3000)
```

Opens **"Speaking Voice" dialog** at z=9998 (`.popup-mount-node` > `.voice-picker-wrapper` > `.voice-picker`):

**Two tabs:** "Text to Speech" (default) | "Upload Audio"

#### Text to Speech Tab
- **Explore** button + Language selector: "English" (dropdown)
- **97 voices** in scrollable list (`.c-option`): each has `.name`, `.gender`, `.use_case`, `.play-button`
- Key voices for pipeline:
  | Name | Gender | Use Case |
  |------|--------|----------|
  | James | Male | Narrative Story |
  | Brittney | Female | Narrative Story |
  | Adam Stone | Male | Narrative Story |
  | Johnny Kid | Male | Narrative Story |
  | Joey | Male | Social Media |
  | Hope | Female | Social Media |
  | Finn | Male | Conversational |
  | Arabella | Female | Conversational |
  | Alex | Male | Entertainment Tv |
- James is the best fit for the Rayviews pipeline (male narrative voice)
- **Text area:** `.editable-textarea` (contentEditable div), 4000 char limit
  - IMPORTANT: Must use `page.keyboard.type()` — setting `.textContent` does NOT trigger state update
  - `.model-trigger` shows "Standard Mode" (Powered by Eleven Multi = ElevenLabs)
  - `.speed-control` with speed 1.00
  - `.character-statistics` shows "N/4000"
- **Generate Audio button:** `.gen-audio-btn` — text "Generate Audio Free"
  - Disabled until text is typed (via keyboard events)
  - **FREE** — no credits consumed
  - Generation takes ~10 seconds
- **After generation:** Audio preview appears with waveform (`.audio` section)
  - Play button + duration ("Audio 00:03 / 00:03")
  - **"Regenerate"** button (Free) to redo
  - **"Apply"** button (`.option-btn.apply`) to add to timeline

```python
# TTS workflow
ta = page.locator('.voice-picker-wrapper .editable-textarea')
ta.first.click()
page.keyboard.press("Meta+a")
page.keyboard.type("Script text here", delay=20)
page.wait_for_timeout(1000)
# Click Generate Audio
gen = page.evaluate("() => { var b=document.querySelector('.gen-audio-btn'); if(b&&!b.disabled){var r=b.getBoundingClientRect(); return {x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)};} return null; }")
page.mouse.click(gen['x'], gen['y'])
# Wait for Apply button (~10s)
# Click Apply
```

#### Upload Audio Tab
- "Upload an audio file (up to 5min)."
- Supported formats: MP3, WAV, M4A, AAC, etc.
- Maximum file size: 60MB
- Button: `.upload-btn` — "Select or drag & drop an audio file"
- No `<input type="file">` in DOM — uses JavaScript file chooser
- Use `page.expect_file_chooser()` to intercept when clicking `.upload-btn`

**Step 8: Apply audio to timeline**

After clicking "Apply", the voice picker closes and:
- Timeline shows audio waveform on "Speaker A" track
- Panel warning clears
- Main Generate button becomes enabled (`.generative.ready`)

### Lip Sync Generation (Phase 107-108)

**Step 9: Click Generate**
- Pro mode: **72 credits** | Normal mode: **36 credits**
- Pro: "Better movement & clarity" (max 30s video)
- Normal: "Basic-quality lip sync"
- Generation is **asynchronous** — submits to server, returns to ready in ~18s
- Result appears in Results panel with **"Waiting for 5-10 mins"** badge

**Step 10: Result**
- Result class: `.result-item.lip-sync-result.hasinfo` (320x427)
- Output area: `.output-result.lip-sync.fixed-content` (320x235)
- Action buttons on each result: Lip Sync, Sound Effects, Video Editor, Motion Control
- Video appears once processing completes (5-10 minutes)

### Key Lip Sync Discoveries (Phase 102)

**Canvas thumbnails in "Pick Image" dialog are NOT `<img>` elements!**
- They are `BUTTON.image-item` with CSS `background-image` property
- Dialog container: `.pick-image-dialog` > `.pick-panel` > `.pick-types` > `.images`
- 3 thumbnail buttons at (464,403), (568,403), (672,403) — each 96x96

---

## Consistent Character Panel (Phases 109-116)

Accessible via sidebar icon at (40, 306). Uses `.panels.show` overview, then expands to `.c-gen-config.show` for sub-features.

### Overview Panel
Character panel overview shows 6 sub-features:
| Feature | Description | Credits |
|---------|-------------|---------|
| Build Your Character | Create new character (Quick Mode: 1 image, or Training Mode: multiple) | -- |
| Manage Your Characters | Manage existing characters | -- |
| Generate Images | Generate images with your character | 4 |
| Insert Character | Insert character into existing images (Lasso/Brush/Auto marking) | 28 |
| Character Sheet | Generate turnaround sheet from prompt | 4 |
| Generate 360 Video | Create rotation video from character image | 6 |

### Character Selection -- Critical Pattern (Phase 116)
The character dropdown (`.c-character-list`) exists in DOM but renders at 0x0 dimensions (invisible). Clicking "Choose a Character" button does NOT make it visible when triggered via JS.

**Working solution**: JS-click the hidden button directly:
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
```

### Available Characters
- Slots Used: 1 / 60
- **Ray** -- custom character (NOT preset), auto-populates 155-char description about studio/headphones
- 5 presets: Lip Boy, Cat Girl, Cow Cat, Richy, Anna

### Generate Images Sub-feature
After selecting character, panel shows:
| Element | Selector / Position | Details |
|---------|---------------------|---------|
| Character | Shows name + avatar thumb | @mention tag in prompt |
| Description | 155/1800 chars | Auto-populated, "Restore" button |
| Action & Scene prompt | `.custom-textarea` | @Ray mention, 1800 char limit |
| Quick Actions | Walk, Read, Wave | Preset action buttons |
| Control Mode | Camera / Pose / Reference | Camera: Auto, Auto |
| Aspect Ratio | 1536x864, 3:4, 1:1, 4:3, canvas | |
| Style | NEW toggle | Non-Explicit toggle |
| Generation Mode | Fast / Normal / HQ | |
| Generate | `.generative` | 4 credits |

Generation: ~39 seconds, produces 2 images. Result actions: Variation, Insert Character, Chat Editor, Image Editor, AI Video, Lip Sync, Expression Edit, Face Swap, Enhance & Upscale.

### Insert Character Sub-feature
| Element | Details |
|---------|---------|
| Mark area | Lasso (default) / Brush / Auto selection |
| Invert / Clear | Selection tools |
| Character Direction | Auto / Front / Back / Left / Right View |
| Camera Shot | Auto / Full Body / Upper Body |
| Generate | 28 credits |

### Character Sheet Sub-feature
| Element | Details |
|---------|---------|
| Model | "Dzine 3D Render v2" (selector) |
| Prompt | TEXTAREA.len-1800 |
| Aspect Ratio | 16:9 (default) / 2:1 / 4:3 |
| Face Match | NEW toggle |
| Generation Mode | Fast / Normal (default) / HQ |
| Generate | 4 credits |

### Generate 360 Video Sub-feature
| Element | Details |
|---------|---------|
| Character Image | "Generate from canvas" button (`.pick-image`) |
| Duration | 5s (default) / 10s |
| Generate | 6 credits |

---

## AI Video Panel

Accessible via sidebar icon at (40, 361).

**Panel class:** `.panels.show` at (80, 49) 264x850. Opens with panel toggle (click distant tool first, wait 1500ms, then AI Video, wait 2000ms). Confirmed working in Phase 77.

**Note:** Uses `.panels.show` class (same as Motion Control, Storyboard, etc.), NOT `.c-gen-config` (which is Txt2Img only). Panel toggle from a distant tool (e.g., Storyboard → AI Video) is required.

**Panel class also uses `.c-gen-config.show` with class `ai-video-panel`** — both `.panels.show` and `.c-gen-config.show` are active simultaneously for AI Video.

**Two modes with DIFFERENT models and pricing:**

### Key Frame Mode (default)
| Setting | Options | Position |
|---------|---------|----------|
| Mode tab | Key Frame (active) | (96, 101) |
| Frame type: Start and Last | Two keyframes | (92, 157) |
| Frame type: AnyFrame | Upload keyframes at any timeline position | (212, 157) |
| Start Frame | Upload area (`.pick-image`) | (101, 218) |
| End Frame | Upload area (disabled until Start set) | (218, 218) |
| Prompt | 0/1800 chars | (101, 389) |
| Model | **Minimax Hailuo 2.3** (`.selected-btn-content`) | (92, 434) |
| Settings | Auto · 768p · 6s (`.metadata`) | (92, 494) |
| Camera | Preset movements (`.camera-movement-btn`) | (92, 544) |
| Generate | **56 credits** | (176, 665) |

### Reference Mode
| Setting | Options | Position |
|---------|---------|----------|
| Mode tab | Reference (active) | (214, 101) |
| Image | Upload reference image | (101, ~180) |
| Prompt | 0/1800 chars | (101, ~350) |
| Hints | Preset thumbnails (2/2/3 pics) | below prompt |
| Model | **Vidu Q1** (different from Key Frame!) | (92, ~450) |
| Settings | 16:9 · 1080p · 5s | (92, ~500) |
| Generate | **85 credits** | (176, ~600) |

### Camera Controls (Key Frame mode only)

Clicking Camera button opens an adjacent panel at ~(344, 65) with preset camera movements.
Class: `.camera-movement-wrapper` → `.camera-movement-btn` (active state when open).

**Tabs:**
- **Cinematic Shots** (default) — `.tab.selected` — grid of preset camera movements
- **Free Selection** — `.tab` — freeform camera path drawing (no presets, interactive canvas)

**Cinematic Shots presets** (class `.camera-item`, name under `.camera-name`):
1. Debut
2. Freedom
3. Left Circling
4. Right Circling
5. Upward Tilt
6. Downward Tilt
7. Left Walking
8. Right Walking
9. Stage Left
10. Stage Right
11. Scenic Shot

Each preset has a preview thumbnail. Click to select. Camera movement is applied to the generated video.

### Video Model Selector

Clicking the model button (`.selected-btn-content`) opens a `selector-panel medium` overlay at ~(362, 65) with z=9999.

**Filter toggles:** Video Model | Uncensored | Star/Last Frame

**Complete model list (34 models, confirmed Phase 81):**
| Model | Credits | Resolution | Tags |
|-------|---------|------------|------|
| **Minimax Hailuo 2.3** (HOT, default) | 56-98 / 6s | — | Uncensored |
| Kling Video O1 | 140 / 5s | 1080p | — |
| Kling 3.0 | 126-168 / 5s | 1080p | — |
| Kling 2.6 | 85-170 / 5s | 1080p | — |
| Dzine Video V2 | 20 / 5s | — | Uncensored |
| Seedance 1.5 Pro | 12-56 / 5s | — | Uncensored |
| Seedance Pro | 25-120 / 5s | 1080p | Uncensored |
| Wan 2.6 | 14-21 / s | 1080p | Uncensored |
| Wan 2.5 | 7-21 / s | 1080p | Uncensored |
| Sora 2 | 100 / 4s | — | — |
| Sora 2 Pro | 300-500 / 4s | 1080p | — |
| PixVerse V5 | 50 / 5s | 1080p | — |
| Runway Gen4 turbo | 46 / 5s | — | — |
| Google Veo 3.1 Fast | 200-304 / 8s | 1080p | — |
| Google Veo 3.1 | 400-800 / 8s | 1080p | — |
| Google Veo 3 Fast | 225 / 8s | — | — |
| Google Veo 3 | 600 / 8s | — | — |
| Luma Ray 2 | 146 / 5s | — | — |
| Dzine Video V1 | 10 / 5s | — | Uncensored |
| Wan 2.2 | 50-100 / 5s | — | Uncensored |
| Wan 2.2 Flash | 20-50 / 5s | — | — |
| Wan 2.1 | 6 / 5s | — | Uncensored |
| Seedance Pro Fast | 7-35 / 5s | — | Uncensored |
| Seedance Lite | 15-80 / 5s | 1080p | — |
| Kling 2.1 Master | 215 / 5s | 1080p | — |
| Kling 2.5 Turbo Pro | 65 / 5s | 1080p | — |
| Kling 2.5 Turbo STD | 30 / 5s | — | — |
| Kling 2.1 Std | 37 / 5s | — | — |
| Kling 2.1 Pro | 75 / 5s | 1080p | — |
| Kling 1.6 standard | 37 / 5s | — | — |
| Kling 1.6 pro | 75 / 5s | 1080p | — |
| Minimax Hailuo 02 | 56-98 / 6s | 1080p | — |
| Minimax Hailuo | 56 / 6s | — | — |
| Luma Ray 2 flash | 45 / 5s | — | — |

**Budget picks:** Wan 2.1 (6 credits), Seedance Pro Fast (7-35), Dzine Video V1 (10), Seedance 1.5 Pro (12-56)

**AI Video Settings** — Click the `.metadata` row (e.g., "Auto · 768p · 6s") to expand settings popup to the right.

Settings popup appears at x~378, contains button groups:

| Setting | Options | Class |
|---------|---------|-------|
| Aspect Ratio | Auto / 1:1 / 16:9 / 9:16 | `.size-btn` |
| Quality | 720p / 1080p | `.quality-btn` |
| Duration | 5s / 10s | `.duration-btn` |

Note: "Auto" may be disabled for certain models (e.g., Kling Video O1 only supports fixed ratios). Available options vary by model. Some models also show Sound toggle and Sound/Negative Prompt fields (0/300 chars each).

**Model sharing:** Both Key Frame and Reference modes share the same 34 models. The **default** differs: Key Frame defaults to Minimax Hailuo 2.3 (56 credits, 768p, 6s), Reference defaults to Vidu Q1 (85 credits, 1080p, 5s). Camera controls only available in Key Frame mode.

Video credits: 9,000 available. "Please enter your prompt."

---

## Video Editor Panel

Accessible via sidebar icon at (40, 490).

**Panel class:** `.c-gen-config show float-gen-btn float-video-editor-gen-btn` — uses the `.c-gen-config` system (same as Txt2Img and AI Video). Opens reliably with distant panel toggle (Storyboard → Video Editor).

| Setting | Value | Position |
|---------|-------|----------|
| Input | "Select or Drag a video to edit" | (93, 110) `.video-editor-picker` |
| Prompt | 0/1000 chars | (93, 293) |
| Model | Runway Gen4 Aleph | (92, 440) `.selected-btn-content` |
| Settings | Auto · 720p · 1~5s | (92, 500) `.metadata` |
| Advanced | Toggle button | (92, 560) `.advanced-btn` |
| Generate | **30 credits** | (176, 662) |

"Please upload your video." Requires input video.

**Note:** Earlier exploration (Phase 74) found this tool opened the Lip Sync panel instead — this was due to insufficient panel toggle. With proper distant toggle it opens its own panel.

### Video Editor Models

Video Editor shares the **same 34-model library** as AI Video. Models are displayed in `.selector-panel` via `.selected-btn-content` click. Default is Runway Gen4 Aleph (30 credits). However, Video Editor shows different pricing per model (e.g., Runway Gen4 Aleph = 150 credits/5s, Kling Video O1 = 20 credits/s in the model selector).

### Video Editor Advanced

Same as Txt2Img — `.advanced-content.show` at (362, 65) 280x146. Contains only a **Seed** input field. The available advanced options depend on the selected model/style.

---

## Motion Control Panel

Accessible via sidebar icon at (40, 550). Panel class: `panels show` at (80, 49). Use **panel toggle** to open.

| Setting | Options | Position/Class |
|---------|---------|----------------|
| Model | **Kling 2.6 Motion** (dropdown) | `selected-btn-content` (102, 107) |
| Motion Video | Upload area | `video-upload-container` (104, 169) |
| Character Image | Upload area | `image-upload-wrap` (218, 169) |
| Prompt | 0/1800 chars | `prompt-textarea` (101, 324) |
| Final Result Should | Character Orientation Matches (2 options) | `c-option` (108, 499/527) |
| Settings | Auto · 1080p · 3~30s | `metadata` (152, 579) |
| Generate | 28 credits | `btn-generate` (80, 627) |
| Video credits | 9,000 left | shown in generate area |
| Close | X button | `ico-close` (316, 65) |

Requires both a Motion Video reference and Character Image upload.

---

## Instant Storyboard Panel

Accessible via sidebar icon at (40, 766). Panel class: `panels show` at (80, 49). Use **panel toggle** to open.

| Setting | Options | Position/Class |
|---------|---------|----------------|
| Version: V1 | Button | `options` (96, 101) |
| Version: **V2** | Button (selected) | `options selected` (214, 101) |
| Image Upload | Reference image(s) | `upload-image-btn` (105, 162) 68x68 |
| Prompt | 0/1000 chars, supports **@** mentions | `prompt-textarea` (101, 238) |
| Hints | 3 preset layouts (all "2 pics") | `storyboard-preset-wrap` (105, 369) |
| Refresh | Refresh hints | `preset-refresh` (295, 379) |
| Aspect Ratio | 1536×1536 default | `config-param` (92, 430) |
| Ratio presets | **9:16** / 1:1 / 16:9 / ... | buttons below |
| Generate | 6 credits | yellow button |

**@ Mentions:** Prompt supports `@` to reference elements: Character, Object, Background, or Layout.

**Hints:** 3 storyboard preset thumbnails from `static.dzine.ai/tools/instant_storyboard/storyboard_*`. Each shows "2 pics" layout. Click to select, refresh button randomizes.

"Please enter your prompt." Generates 2-panel storyboard.

---

## Image Editor Panel

Accessible via sidebar icon at (40, 698). **Panel class:** `c-gen-config show collapse-panel`. Contains **3 sections**:

### AI Editor
| Tool | Position | CSS Class | Description |
|------|---------|-----------|-------------|
| Local Edit | (92, 137) | `collapse-option has-guide` | Edit specific regions |
| Insert Object | (218, 137) | `collapse-option` | Add objects to scene |
| AI Eraser | (92, 269) | `collapse-option` | Remove elements via mask |
| Hand Repair | (218, 269) | `collapse-option` | Fix hand/finger artifacts |
| Expand | (92, 401) | `collapse-option` | Extend image boundaries |

### Face Kit
| Tool | Position | CSS Class | Description |
|------|---------|-----------|-------------|
| Face Swap | (92, 573) | `collapse-option has-guide` | Replace face |
| Face Repair | (218, 573) | `collapse-option` | Fix facial artifacts |
| Expression Edit | (92, 705) | `collapse-option` | Change facial expression |

### Product Background
| Tool | Position | CSS Class | Description |
|------|---------|-----------|-------------|
| Background | (92, 877) | `subtool-item` | Change product background |

All tools require a **selected layer** on the canvas. Tools with `has-guide` have tutorial overlays.

### Local Edit Sub-tool (Detail)

Opened by clicking "Local Edit" in Image Editor. **Panel class:** `c-gen-config show`. Allows targeted editing of specific regions.

| Element | Position | CSS Class | Notes |
|---------|----------|-----------|-------|
| Header "Local Edit" | (172,61) | `gen-config-header` | with back arrow |
| Instruction | (104,109) | `select-tips` | "Mark an area for editing" |
| Mask: **Lasso** | (104,137) | `item lasso active` | Selected by default |
| Mask: Brush | (177,137) | `item brush` | Paint mask |
| Mask: Auto | (251,137) | `item auto` | Auto-detect regions |
| Select mode | (108,200) | `selection-item selected` | **Select** / Unselect |
| Prompt | (93,253) 238x134 | `prompt-content` | 0/1800 chars |
| Style | (92,400) | `c-style` / `button.style` | "No Style v2" (selectable) |
| Control Method | (100,460) | `group` | **Prompt** (selected) / Balanced / Image |
| Generate | (176,554) | `consume-tip` | **4 credits** |
| Warning | (92,596) | `warning-tips` | "Please mark the editing area." |

### AI Eraser Sub-tool (Detail)

Opened by clicking "AI Eraser" in Image Editor. Removes marked regions and fills intelligently.

| Element | Position | Notes |
|---------|----------|-------|
| Header "AI Eraser" | (174,61) | `gen-config-header` with back arrow |
| Selection Guide | (223,97) | Help text |
| Mask tools | (104,167) | **Lasso** (active) / Brush / Auto |
| Selection mode | (108,230) | **Select** / Unselect |
| Prompt | (93,283) 238x134 | "What to fill" 0/1800 chars |
| Generate | (92,430) 240x48 | **9 credits** |
| Warning | (92,486) | "Please mark the editing area." |

### Insert Object Sub-tool (Detail)

Opened by clicking "Insert Object" in Image Editor. Adds an object from a reference image into a masked area.

| Element | Position | Notes |
|---------|----------|-------|
| Header "Insert Object" | (92,61) | `gen-config-header` with back arrow + close |
| Instruction | (104,109) | "Mark an area for editing" |
| Mask tools | (104,137) | **Lasso** (active) / Brush / Auto |
| Selection mode | (108,200) | **Select** / Unselect |
| **Reference Object** | (100,260) | Section label |
| Pick Image button | (100,288) 224x50 | `button.upload` "Pick an image — Object image for insertion" |
| Prompt | (92,358) 238x94 | "Descreva o objeto de referencia (opcional)" **0/150 chars** |
| Generate | (92,466) 240x48 | **4 credits** |
| Warning | (92,522) | "Please mark the editing area." |

**Key differences from Local Edit:**
- Has a **Reference Object** image upload — you provide an image of the object to insert
- Much shorter prompt limit: **150 chars** (vs 1800 for Local Edit)
- No Style selector or Control Method
- Same mask tools (Lasso/Brush/Auto) and selection modes
- Canvas shows "Circle around the area you want to select" instruction overlay

### Generative Expand Sub-tool (Detail)

Opened by clicking "Expand" in Image Editor. Extends image boundaries using AI fill.

| Element | Position | Notes |
|---------|----------|-------|
| Header "Generative Expand" | (92,61) | `gen-config-header` with back arrow + close |
| Expand Aspect Ratio | (100,105) | Section label |
| Ratio row 1 | (100,133) | 1:1, 4:3, 3:2, **16:9** (active), 2:1 |
| Ratio row 2 | (150,162) | 3:4, 2:3, 9:16, 1:2 |
| Prompt | (92,209) 240x152 | Optional, 0/1800 chars, multilingual |
| Generate | (92,373) 240x48 | **8 credits** |

**Canvas interaction:** When Expand is active, the canvas shows **drag handles** (white bars) on all 4 edges. Drag edges outward to define expansion area. The instruction reads "Expand your canvas by dragging the edges."

**8 aspect ratio presets** (in 2x4 grid):
| Row 1 | Row 2 |
|-------|-------|
| 1:1 | 3:4 |
| 4:3 | 2:3 |
| 3:2 | 9:16 |
| **16:9** (default) | 1:2 |
| 2:1 | |

### Hand Repair Sub-tool (Detail)

Opened by clicking "Hand Repair" in Image Editor. Fixes hand/finger artifacts in generated images.

| Element | Position | Notes |
|---------|----------|-------|
| Header "Hand Repair" | (165,61) | `gen-config-header` with back arrow + close |
| Mask tools | (104,137) | **Lasso** (active) / Brush / Auto |
| Selection mode | (108,200) | **Select** / Unselect |
| Generate | (92,252) 240x48 | **4 credits** |
| Warning | (92,308) | "Please mark the editing area." |

**Key notes:**
- **No prompt field** — simplest Image Editor sub-tool
- Just mask the hand area and generate — AI fixes hand/finger issues automatically
- Same mask tools as other sub-tools (Lasso/Brush/Auto)

### Face Swap Sub-tool (Detail)

Opened by clicking "Face Swap" in Image Editor. Replaces face in the selected layer with an uploaded face.

**Panel class:** `c-gen-config show`

| Element | Position | Notes |
|---------|----------|-------|
| Header "Face Swap" h5 | (169,61) | `gen-config-header` with back arrow + close |
| "New Face" section | (100,105) | `.group` label |
| Upload button | (100,133) 224x50 | `.pick-image.has-guide` "Upload a Face Image" |
| Generate | (92,203) 240x48 | **4 credits** |
| Warning | (92,259) | "Please upload a new face." |

**Key notes:**
- **No mask tools** — no need to select area, AI detects the face automatically
- **No prompt** — just upload a new face image and generate
- Uses same `pick-image` upload mechanism as CC Reference (expect_file_chooser)
- Simplest Face Kit tool

### Face Repair Sub-tool (Detail)

Opened by clicking "Face Repair" in Image Editor. Repairs facial artifacts while preserving identity.

| Element | Position | Notes |
|---------|----------|-------|
| Header "Face Repair" | (166,61) | `gen-config-header` with back arrow + close |
| Mask tools | (104,137) | **Lasso** (active) / Brush / Auto |
| Selection mode | (108,200) | **Select** / Unselect |
| Prompt | (92,252) 240x136 | Optional description, 0/1800 chars |
| **Preserve Original Face** | (100,408) | Slider control |
| Slider label | (100,452) | "Strongly similar" (default position) |
| Generate | (92,488) 240x48 | **4 credits** |
| Warning | (92,544) | "Please mark the editing area." |

**Key notes:**
- Has a **Preserve Original Face** slider — controls how much of the original face to keep
- Default: "Strongly similar" (slider near right/high preservation)
- Prompt is optional (0/1800 chars) — describe desired facial characteristics
- Mask the face area first, then generate

### Product Background Sub-tool

Located below Face Kit in Image Editor panel. The Image Editor panel has a scrollable container (`div.subtools` at (92,97) 252x802, scrollHeight=912) — Product Background is at the bottom.

**Image Editor Full Structure (after scroll):**
1. **AI Editor:** Local Edit, Insert Object, AI Eraser, Hand Repair, Expand
2. **Face Kit:** Face Swap, Face Repair, Expression Edit
3. **Product Background:** Background

The "Background" tool is a `div.subtool-item` (NOT a button), click it to open the BG replacement panel.

```python
# Scroll Image Editor panel to reveal Product Background
page.evaluate("""() => {
    var panel = document.querySelector('.subtools');
    if (panel) { panel.scrollTop = panel.scrollHeight; return true; }
    return false;
}""")
page.wait_for_timeout(500)
# Click Background
page.evaluate("""() => {
    for (const el of document.querySelectorAll('.subtool-item')) {
        var text = (el.innerText || '').trim();
        if (text === 'Background') { el.click(); return true; }
    }
    return false;
}""")
```

- Requires a selected layer on canvas
- Good for isolating products from review site images
- Also accessible via "BG Remove" toolbar shortcut (see Layer Tools Toolbar below)

### Expression Edit Panel (Detail)

**Panel class:** `c-gen-config show face-edit-panel float-gen-btn`

Opens in **full-screen mode** — replaces the normal canvas layout. Top bar shows "Expression Edit" label with **Done** (705, 8) and **Cancel** (783, 8) buttons. Close with Cancel to discard or Done to apply (4 credits).

**Face preview:** `.face-preview` (240x216) — "Choose a face from the canvas"

**Modes:** Custom (selected) | Template buttons (toggle at y~258, class `sliding-switch`)

**Custom Mode — Eyes Adjustments (`.group-info`, collapsible ^):**
| Control (`.name`) | Left (`.mark.left`) | Right (`.mark.right`) | Default (`.value`) |
|---------|-------|---------|---------|
| Eye Openness | Closed | Open | 0 |
| Horiz. Eye Gaze | Left | Right | 0 |
| Vert. Eye Gaze | Up | Down | 0 |
| Eyebrow | Lower | Higher | 0 |
| Wink | No Wink | Wink | 0 |

**Custom Mode — Mouth Adjustments (`.group-info`, collapsible ^):**
| Control (`.name`) | Left (`.mark.left`) | Right (`.mark.right`) | Default (`.value`) |
|---------|-------|---------|---------|
| Lip Openness | Closed | Open | 0 |
| Pouting | Left | Right | 0 |
| Pursing | Closed | Pout | 0 |
| Grin | Narrow | Wide | 0 |
| Smile | Frown | Laugh | 0 |
| Roundness | Flat | Round | 0 |

**Custom Mode — Head Angles (collapsible ^):**
| Control | Range | Default |
|---------|-------|---------|
| Head Pitch | Up ↔ Down | 0 |
| Head Yaw | Left ↔ Right | 0 |
| Head Roll | Left ↔ Right | 0 |

Total: **14 sliders** in 3 sections (5 eyes + 6 mouth + 3 head). All default to 0 (center).

**Template Mode:**
- **AI Strength** slider: 0.75 default, label "Aggressive"
- **12 preset tiles** in 3×4 grid (class `tile-template`):

| Tile | Class | Icon/URL |
|------|-------|----------|
| Reset | `tile-item-content reset` | Undo icon (ico-reset) |
| Upload | `tile-item-content upload` | Image icon (ico-image) |
| Cry | `tile-item-content emoji` | `static.dzine.ai/assets/cry-*.webp` |
| Sad | `tile-item-content emoji` | `static.dzine.ai/assets/sad-*.webp` |
| Disgusted | `tile-item-content emoji` | `static.dzine.ai/assets/disgusted-*.webp` |
| Angry | `tile-item-content emoji` | `static.dzine.ai/assets/angry-*.webp` |
| Smile | `tile-item-content emoji` | `static.dzine.ai/assets/smile-*.webp` |
| Wink Smile | `tile-item-content emoji` | `static.dzine.ai/assets/wink_smile-*.webp` |
| Laugh | `tile-item-content emoji` | `static.dzine.ai/assets/laugh-*.webp` |
| Surprised | `tile-item-content emoji` | `static.dzine.ai/assets/suprised-*.webp` |
| Shout | `tile-item-content emoji` | `static.dzine.ai/assets/shout-*.webp` |
| Dismissive | `tile-item-content emoji` | `static.dzine.ai/assets/dismissive-*.webp` |

Click any template tile to apply that expression preset. Adjust AI Strength for intensity.

### Expression Edit Access Methods

1. **Layer Tools toolbar (MOST RELIABLE):** Select image layer with face → click "Expression" button (class `item face-editor`) in the layer-tools bar. Enters full-screen Expression Edit mode.
2. **Results panel:** Click "Expression Edit" → "1" or "2" button (y=467)
3. **Image Editor sidebar:** Scroll to Face Kit → Expression Edit

```python
# Recommended: Click face on canvas → toolbar Expression
page.mouse.click(550, 350)   # Click face on canvas
page.wait_for_timeout(1000)
page.evaluate("""() => {
    var bar = document.querySelector('.layer-tools');
    if (!bar) return null;
    for (const btn of bar.querySelectorAll('*')) {
        if ((btn.innerText || '').trim() === 'Expression') {
            btn.click(); return true;
        }
    }
    return null;
}""")
page.wait_for_timeout(5000)

# Verify full-screen mode (Done button visible in top bar)
in_expr = page.evaluate("""() => {
    for (const el of document.querySelectorAll('button')) {
        var text = (el.innerText || '').trim();
        var r = el.getBoundingClientRect();
        if (text === 'Done' && r.x > 500 && r.x < 800 && r.y < 40 && r.width > 0)
            return true;
    }
    return false;
}""")
```

---

## Workflow: Insert Character (from Results Panel)

Adds a character (Ray) into an existing generated image. Accessed via the "Insert Character" action button in the Results panel (NOT from sidebar).

### How to Access

1. Generate an image (CC, Txt2Img, etc.)
2. In the Results panel, find "Insert Character" row
3. Click variant "1" or "2" button → opens Insert Character editing panel

### Insert Character Panel Layout

| Element | Position | Notes |
|---------|----------|-------|
| Header "Insert Character" | (153,61) | |
| Mask tools | (104,137) | Lasso (active) / Brush / Auto |
| Mask mode | (104,196) | Select / Unselect |
| "Choose a Character" | (92,252) 240x40 | Opens character gallery |
| Character prompt | (92,304) | "Character Action & Scene" 0/1800 |
| Preset prompts | (101,468) | Walk / Read / Wave |
| Camera control | (92,505) | "Camera Auto, Auto" |
| Generate button | (92,566) 240x48 | **28 credits** |
| Warning | (92,626) | "Please mark the editing area." |

### Step-by-Step

1. Click "Insert Character" → "1" button in Results panel
2. Select mask mode: **Lasso** (draw freehand), **Brush** (paint), **Auto** (AI detection)
3. Mark the area where character should be inserted
4. Click "Choose a Character" → select **Ray** (BUTTON element, same as CC)
5. After Ray selected: prompt auto-fills with "Ray", description shows (125 chars)
6. Add scene description in "Character Action & Scene" textarea or use presets (Walk/Read/Wave)
7. Click Generate (28 credits)

### Notes
- Requires masking an area first — Generate won't work without a marked editing area
- Same character library as Consistent Character
- Ray's description auto-populates when selected
- "Restore" button available to reset character selection
- 28 credits per generation (more expensive than CC's 4 credits)

---

## Workflow: Character Sheet

Generates a multi-angle reference sheet for a character. Accessed from the Character sidebar menu (click "Character Sheet — From prompt").

### Character Sheet Panel Layout

**Panel class:** `c-gen-config show float-gen-btn float-cs-gen-btn`

| Element | Position | Notes |
|---------|----------|-------|
| Header "Character Sheet" | (80,49) | `gen-config-header` |
| Back arrow | (92,61) | Returns to Character menu |
| Model | (92,97) 240x40 | **Dzine 3D Render v2** (via `button.style`) |
| Prompt textarea | (101,~150) | 0/1800 chars |
| Aspect Ratio | (100,305) | 1536×864 default, class `aspect-ratio-option` |
| Ratio buttons | (104,337) | **16:9** / 2:1 / 4:3 |
| Face Match NEW | (100,393) | Toggle switch (new feature) |
| Generation Mode | (100,469) | Fast / **Normal** (selected) / HQ |
| Advanced | (104,533) | Popup with seed (same as Txt2Img) |
| Generate button | (92,573) 240x48 | **4 credits** |
| Warning | (92,~630) | "Please enter your prompt." |

### Key Differences from CC Generate Images

- Uses **Dzine 3D Render v2** model (not user-selectable)
- Aspect ratios are **16:9 / 2:1 / 4:3** (no "canvas" option, no 3:4 or 1:1)
- No character selection — uses prompt only
- **4 credits** (same as CC)
- Generates a sheet with multiple poses/angles of the character

### Step-by-Step

1. Open Character sidebar menu (double-click at 40,306)
2. Click "Character Sheet — From prompt" card
3. Enter character description in prompt
4. Select ratio (16:9 for YouTube)
5. Click Generate (4 credits)

---

## Workflow: Generate 360° Video

Generates a 360° turnaround video from a character image. Accessed from the Character sidebar menu (click "Generate 360° Video — From a character image").

### Panel Layout

| Element | Position | Notes |
|---------|----------|-------|
| Header "Generate 360° Video" | (92,61) | `gen-config-header` |
| Character Image | (100,133) 224x50 | `button.pick-image` "Generate from canvas" |
| Duration | (100,239) | **5s** (selected) / 10s |
| Generate button | (92,291) 240x48 | **6 credits** |

### Notes
- Requires a character image on canvas (click "Generate from canvas" to pick from canvas layer)
- Uses video credits (9,000 available on Master plan)
- Simple panel — just pick image, set duration, generate
- 6 credits per generation (video credits, not image credits)

---

## Workflow: Motion Control (Detail)

Accessible via sidebar icon at (40, 550). Uses Kling 2.6 engine for precise motion control.

### Full Panel Layout

| Element | Position | Notes |
|---------|----------|-------|
| Header "Motion Control" | (80,49) | `gen-config-header` |
| Model | (92,97) | **Kling 2.6 Motion** (fixed) |
| Motion Video upload | (104,169) 102x122 | Video reference upload zone |
| Character Image upload | (218,169) 102x122 | Character image upload zone |
| Prompt | (92,315) 240x136 | 0/1800 chars |
| Final Result Should | (104,475) | **Character Orientation Matches Video** (selected) / Character Orientation Matches Image |
| Settings | (92,579) | Auto · 1080p · 3~30s |
| Video credits | (92,640) | "9,000 video credits left" |
| Generate button | (92,676) 240x48 | **28 credits** (video) |
| Warning | (92,736) | "Please upload your video." |

### Two Upload Zones
- **Motion Video** (left): Reference video that defines the motion
- **Character Image** (right): The character to animate
- Both are required for generation

---

## Workflow: Assets Sidebar

The Assets sidebar (40, 136) provides a file manager for uploaded images and project assets.

### Assets Panel Layout

| Element | Notes |
|---------|-------|
| Header "Assets" | Shows storage usage in `.capacity` div (e.g., "12MB / 100GB") |
| Path breadcrumb | "My Assets" button (`.root-folder.cur-path`) |
| **Favorites** folder | `.file-item.folder` — 0 items (user-favorited assets) |
| **Uploads** folder | `.file-item.folder` — 0 items (manually uploaded files) |

### Notes on Upload Sidebar

The **Upload** sidebar icon (40, 81) does NOT have its own panel. It inherits/keeps the last active panel open. Upload to canvas is done via:
- Assets sidebar → Uploads folder → upload there
- Drag-and-drop onto canvas (browser native)
- Result images in Results panel (click to place on canvas)

### Upload Mechanism (Phase 114-115 Investigation)
- NO `input[type="file"]` elements exist on the page
- NO `window.showOpenFilePicker` API available
- Upload sidebar icon (`.tool-item.import`) does not open any panel or trigger file chooser
- Assets panel `.new-file.upload-image` button does not trigger file chooser via CDP
- Drag-and-drop containers exist in DOM (`.drag-drop`, `.drop-area-content`, `.drop-box`) but are invisible
- **Status: Upload mechanism still under investigation** -- may require native OS file dialog interaction or drag-and-drop simulation

---

## Layers Panel

Accessible via "Layers" tab at (1280, 49) in top bar.

- **Layer selection:** Click the layer BUTTON (314x64px) in the Layers panel
- Layers listed top-to-bottom: newest first
- Each layer shows: thumbnail, name ("Layer N"), opacity (100%), visibility toggle (eye icon), 3-dot menu
- **Background** layer at bottom (No Fill by default)
- Clicking a result image in Results panel creates a new layer and places the image on canvas
- Layer BUTTON class: `layer-item [locked] <id>` — "locked" class prevents editing
- **No right-click context menu** on layers
- **Opacity control:** Clicking the "100%" percentage or the 3-dot area opens an inline **Opacity slider** dropdown
- The eye icon (rightmost) toggles layer **visibility** on/off

### Layer Deletion

- **Delete key** and **Backspace key** both delete the selected layer **immediately without confirmation**
- **Ctrl+Z (Cmd+Z)** undoes the deletion — works reliably
- For automation: always verify layer count before/after if deletion is intentional

**Important:** Many tools (Enhance, Image Editor, Export) require a selected layer. Click the layer in the Layers panel — clicking on the canvas image does NOT reliably select the layer.

### Top Bar Toolbar Icons

At 1440x900, between canvas size and undo/redo, the top bar shows tool icons (all `button.tool-item`, 36x36px):

| Icon | Position | ID | Class | Action |
|------|---------|-----|-------|--------|
| Play (triangle) | (195, 6) | — | `tool-item` | Preview/play |
| **Cursor (arrow)** | (239, 6) | `tool-move` | `tool-item active` | Select/move tool (default) |
| Move/resize | (283, 6) | `tool-move` | `tool-item` | Transform tool |
| **Text (T)** | (327, 6) | `tool-text` | `tool-item` | Add/edit text layer |
| **Pen** | (371, 6) | — | `tool-item draw-dropbox` | Drawing tool (has dropdown) |
| Magic wand | (415, 6) | — | `tool-item` | AI tool |
| **Hand** | (459, 6) | `tool-hand` | `tool-item` | Pan/move canvas |

```python
# Click Text tool
page.evaluate("""() => {
    var btn = document.getElementById('tool-text');
    if (btn) { btn.click(); return true; }
    return false;
}""")

# Click Hand (pan) tool
page.evaluate("""() => {
    var btn = document.getElementById('tool-hand');
    if (btn) { btn.click(); return true; }
    return false;
}""")
```

### Layer Tools Toolbar (below top bar)

When a layer is selected, a secondary toolbar appears at y=65-82 (class `layer-tools`, z=330):

**Complete toolbar (12 buttons, confirmed Phase 83):**

| Tool | Position | Class | Type |
|------|---------|-------|------|
| Select tool | x=405 | `.select-tool` | Icon (32x32) |
| AI Eraser | x=454 | `.remove` | Text label |
| Hand Repair | x=521 | `.hand-repair` | Text label |
| Expression | x=606 | `.face-editor` | Text label |
| BG Remove | x=684 | `.removebg` | Text label |
| Cutout | x=778 | `.cutout` | Icon (32x32) |
| (unknown) | x=814 | `.item` | Icon (28x28) |
| Crop | x=846 | `.crop` | Icon (32x32) |
| SVG | x=895 | `.svg` | Icon (32x32) |
| 3D | x=931 | `.gen-3d` | Icon (32x32) |
| Save as Asset | x=967 | `.save_as_asset` | Icon (32x32) |
| Download | x=1003 | `.download` | Icon (32x32) |

```python
# Click BG Remove
page.evaluate("""() => {
    var btn = document.querySelector('.layer-tools .removebg');
    if (btn) { btn.click(); return true; }
    // Fallback
    var bar = document.querySelector('.layer-tools');
    if (!bar) return false;
    for (const el of bar.querySelectorAll('button')) {
        if ((el.innerText || '').trim() === 'BG Remove') {
            el.click(); return true;
        }
    }
    return false;
}""")
```

These are quick-access shortcuts that bypass the Image Editor sidebar navigation.

---

## Image Download Strategy

**Direct URL download is the preferred method** for pipeline automation:

- Result image URLs from `static.dzine.ai` serve **full resolution** without authentication
- CC images: 1536×864 (16:9 canvas setting)
- Txt2Img images: up to 2720×1530 (2K quality)
- CC generates 2 variants per generation (1_output and 2_output) — both are full-res
- Use `urllib.request` to download directly (no cookies/auth needed)
- No need for Export button or canvas interaction

---

## Enhance & Upscale Panel

Accessible via sidebar icon at (40, 628). Panel class: `.panels.show`.

| Setting | Options | Selector |
|---------|---------|----------|
| Mode | **Image** (default) / Video | `.options` buttons |
| Enhance Mode | **Precision Mode** / Creative Mode | `.option` radio buttons |
| Scale Factor | **1.5x** / 2x / 3x / 4x | `.options` buttons |
| Format | PNG / **JPG** | `.options` buttons |
| Upscale | Button | `.generative.ready` |

Requires: select one layer on canvas first. Warning: "Please select one layer on canvas"

- **Upscale button** (`button.generative.ready`) — shows "Upscale" text + credit icon
- 9 credits per upscale (Image mode)
- Scale Factor label also shows output dimensions (e.g., "1802 x 291") next to "Scale Factor" header
- Help icons (ico-help) next to Enhance Mode and Scale Factor
- No model selector — uses fixed Dzine upscale engine

### Video Mode

Switch to Video mode by clicking the "Video" tab button at (214, 101).

| Setting | Options | Position/Class |
|---------|---------|----------------|
| Sub-tab: **Enhance** | Tab (selected) | top tabs |
| Sub-tab: Upscale | Tab | top tabs |
| Source Video | "Upload or Drag a video" | upload area |
| Scale: **1x** | Button (selected) | scale buttons |
| Scale: 3x | Button | scale buttons |
| Scale: 4x | Button | scale buttons |
| Cost | "Free:2" | label below scale |
| **Enhance** | Yellow button | bottom |

- Video mode has only 3 scale options (1x/3x/4x — no 1.5x or 2x)
- "Free:2" means 2 free enhancements available
- No model selector — uses fixed Dzine video upscale engine
- No Precision/Creative mode toggle in Video mode
- No format selection (PNG/JPG) — video output only

---

## Dialog Handling

Dzine shows tutorial dialogs and popups that block the UI. Always run before interacting:

```python
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
```

**Critical:** The AI Eraser tutorial dialog can push the sidebar to negative x coordinates. Always close dialogs after page load/reload.

---

## Text Layer Editing

When a text layer is selected (click Layer with "T" icon in Layers panel), a **text toolbar** appears below the top bar:

| Element | Position | Notes |
|---------|----------|-------|
| Font selector | (~250, 45) | Dropdown, default "Inter" |
| Font size | (~330, 45) | Dropdown, e.g. "128" |
| Alignment | (~370, 45) | Left / Center / Right / Justify buttons |
| **Bold (B)** | (~450, 45) | Toggle |
| **Italic (I)** | (~480, 45) | Toggle |

The text toolbar has CSS class `c-text-tool` at (471,65) 499x48.

### Creating a Text Layer

1. Click Text tool icon (`#tool-text`) at (327, 6)
2. Click on the canvas where you want the text
3. Type the text content
4. Use the toolbar to change font, size, alignment

### Editing an Existing Text Layer

1. Select the text layer in Layers panel
2. Double-click the text on canvas to enter edit mode
3. Blue selection handles appear around the text
4. Modify text content, font, or size via toolbar

---

## Canvas Interaction Notes

- **No right-click context menu** — right-clicking on canvas produces no popup menu (confirmed Phase 83)
- **No keyboard shortcuts panel** — pressing "?" produces nothing (confirmed Phase 83)
- **Zoom:** Use **Cmd+scroll wheel** to zoom in/out on canvas. Zoom level shown in `div.c-scale-ratio` at (991,11). Plain scroll does NOT zoom (canvas pans instead). Cmd+=/-/0 keyboard shortcuts do NOT work in Dzine.
- **Canvas click** selects the canvas area but does NOT reliably select a specific layer — use the Layers panel instead
- **Layer selection** happens via clicking a layer BUTTON in the Layers panel (right side)
- **Dragging on canvas** moves/resizes the selected layer (when cursor tool is active)

### Layer Toolbar (`.layer-tools`)

Horizontal toolbar at y~65-82 that appears when any tool/panel is active. Contains 12 buttons:

| Button | Class | Text | Position |
|--------|-------|------|----------|
| Select tool | `.select-tool` | (icon) | x=405 |
| AI Eraser | `.remove` | AI Eraser | x=454 |
| Hand Repair | `.hand-repair` | Hand Repair | x=521 |
| Expression | `.face-editor` | Expression | x=606 |
| BG Remove | `.removebg` | BG Remove | x=684 |
| Cutout | `.cutout` | (icon) | x=778 |
| Unknown | `.item` | (icon, 28x28) | x=814 |
| Crop | `.crop` | (icon) | x=846 |
| SVG | `.svg` | (icon) | x=895 |
| 3D | `.gen-3d` | (icon) | x=931 |
| Save as Asset | `.save_as_asset` | (icon) | x=967 |
| Download | `.download` | (icon) | x=1003 |

Toolbar shows `disabled` class when no layer is selected. Icon-only buttons have tooltips on hover.

### Text Tool

Press **T** to activate text mode, then click canvas to create a text box. A text editing toolbar appears at (471, 65):

| Control | Class | Description |
|---------|-------|-------------|
| Font family | `.font-family` | Dropdown, default "Inter" |
| Font size | `.font-size-value` | Input field (e.g., "128") |
| Alignment | `.font-rcl` | Right/Center/Left alignment buttons |
| Bold/Italic | `.font-style` | B and I formatting buttons |
| Color | `.color` | Color picker swatch |

Container class: `.c-text-tool`. Press **Escape** to exit text editing mode. Text appears as a canvas layer that can be moved/resized.

### Keyboard Shortcuts (Confirmed)

| Key | Action |
|-----|--------|
| **V** | Move/Select tool (`tool-move`) |
| **T** | Text tool (`tool-text`) |
| **H** | Hand/Pan tool (`tool-hand`) |
| **Cmd+Z** | Undo (button.undo at 915,11) |
| **Cmd+Shift+Z** | Redo (button.redo at 951,11) |
| **Cmd+scroll** | Zoom in/out |
| **Delete/Backspace** | Delete selected layer (no confirm) |
| **Escape** | Close current panel/dialog |

**Not working:** Space (no pan toggle), Cmd+=/Cmd+-/Cmd+0 (no zoom), ? (tooltip only)

### Result Panel Action Types (Complete List)

9 action types available per result in the Results panel:

1. **Variation** — generate variations of the image
2. **Insert Character** — add character into the image (28 credits)
3. **Chat Editor** — edit via text prompt (20 credits)
4. **Image Editor** — open in Image Editor sidebar
5. **AI Video** — convert to video (56 credits)
6. **Lip Sync** — add lip sync animation (36 credits)
7. **Expression Edit** — change facial expression (4 credits)
8. **Face Swap** — swap faces (4 credits)
9. **Enhance & Upscale** — upscale resolution (9 credits)

Each action has "1" and "2" buttons to select which variant to process.

---

## Troubleshooting

### Sidebar not visible
- Check if you're in a tool mode (AI Eraser, etc.) — click "Exit" button in top bar
- Set viewport to 1440x900
- Close all dialogs
- If still hidden, reload page + close dialogs

### "Please select a layer" in top bar
- Most top bar tools need a canvas layer selected
- Click on an image on the canvas, or place a result image first

### "Please choose a character" warning
- Ray wasn't selected in the CC dropdown
- Re-click "Choose a Character" and then click the Ray BUTTON element via JS

### Generation seems stuck
- Generation is async — button goes "ready" immediately after submission
- Check the Results panel for progress percentage
- Typical generation time: 30-90 seconds
- If stuck at 0%, the prompt might be invalid or the service is overloaded

### CDP connection timeout
- Kill stale Playwright processes: `pkill -9 -f "node"` (Playwright uses node)
- Ensure browser launched with `--remote-allow-origins=*` (quote `*` in zsh)
- Check: `curl -s http://127.0.0.1:18800/json/version`

### page.close() or pw.stop() hangs
- Known Playwright issue with CDP connections
- `page.close()` and `pw.stop()` can block indefinitely
- Solution: use threading timeout or `os._exit(0)` for scripts
- For production code, use `_safe_cleanup()` in `dzine_browser.py`

### Export recovery
- If download/export is disabled: click result → Image Editor → activate first layer → retry
- Screenshot fallback: capture the result element directly

---

## Model / Style Catalog

The model picker is a large overlay opened by clicking `button.style` (the model name) in Txt2Img/Img2Img panels.

### Overlay Structure

| Element | Position | Notes |
|---------|----------|-------|
| Search bar | top center | "Search styles" input |
| Close button (X) | top right | Closes overlay |
| Categories sidebar | left (208-380) | Scrollable list |
| "+ Create a style" | top of content | Opens style creation |
| **Quick Style** card | (420,218) | "Instantly swap a style from one reference image in seconds" |
| **Pro Style** card | (820,218) | "Carefully learn a style from reference images in minutes" |
| Tabs | below cards | **Dzine Styles** / Community |
| Model grid | main area | 6 columns, scrollable, thumbnail + name |

CSS: `style-list-panel` at (208,128) 1024x692, inner `style-list` at (400,296) 820x582.

### Categories (18) with Model Counts

| Category | Models | Key Styles |
|----------|--------|------------|
| Favorites | user | User-favorited |
| My Styles | user | Custom created |
| Recent | user | Recently used |
| **All styles** | 78 | Everything (excluding Legacy) |
| **General** | 17 | Dzine General, GPT Image 1.5, Z-Image Turbo, Seedream 4.5/4.0/3.0, FLUX.2 Pro/Flex, FLUX.1, Nano Banana Pro/Banana, Midjourney, GPT Image 1.0, Google Imagen 4, Ideogram 3.0, Qwen Image |
| **Realistic** | 26 | Dzine Realistic v3/v2/v1, Realistic, Realistic Product, Sleek Simplicity, Studio Photography, CCD Retro, Natural Serenity, Dzine Kodak Photo, Dzine Cinematic, BW Photo, Fish-eye Lens, Dzine Jewelry v1, Realistic Jewelry, Shining Jewelry, Plush Toy, Vintage Vibe, Cosmic Vistas, Dynamic Splash, Green Tint, Silhouette, Spotlight Fusion, Blurred Echo, Blurry Selfie, Nature's Canvas |
| **Illustration** | 61 | Graffiti Splash, Line & Wash, Piece of Holiday, Impressionist, Illustrated Drama, ... |
| **Portrait** | 40 | Impasto Comics, Film Narrative, Monotone Vogue, Luminous Narratives, Furry, ... |
| **3D** | 19 | Dzine 3D Render v2, 3D Pixel, Soft Pop, Playful Pop, Everything Kawaii, ... |
| **Anime** | 12 | Neo-Tokyo Noir, Narrative Chromatism, Aquarelle Life, Neon Portraiture, Digital Ukiyo-e, ... |
| **Line Art** | 19 | Line Scape, Simple Playful, Whimsical Coloring, Manga Sketch, Sketch Elegance, ... |
| **Material Art** | 14 | Metallic Fluid, Playful Enamel, Colorful Felt, Bold Collage, Glass World, ... |
| **Logo & Icon** | 21 | Battlecraft, Retro Sticker, Neo-Digitalism, Miniatures, Majestic Logo, ... |
| **Character** | 15 | Fantasy Hero, Soft Radiance, Linear Cartoon, Mystical Sovereignty, Storytime Whimsy, ... |
| **Scene** | 17 | Warm Fables, Arcane Elegance, Retro Sci-Fi, Mystical Escape, Tiny World, ... |
| **Interior** | 14 | Minimalist, Wood Tone, Interior Design Insight, Modern Glamorous, Scandi, ... |
| **Tattoo** | 9 | Classic Dotwork, Elegant B&W, B&W Drawing, Floral Tattoo, Apocalyptic Horror, ... |
| **Legacy** | 78 | Legacy versions of all styles (e.g., "Dzine General (legacy)") |

### Key Models for Pipeline

| Model | Category | Best For |
|-------|----------|----------|
| **Realistic Product** | Realistic | Product shots (currently selected default) |
| **Dzine General** | General | All-purpose generation |
| GPT Image 1.5 | General | OpenAI model, good quality |
| Z-Image Turbo | General | Fast turbo mode |
| Seedream 4.5 | General | Latest Seedream |
| FLUX.2 Pro | General | High quality |
| FLUX.2 Flex | General | Flexible generation |
| Nano Banana Pro | General | Fast, good default |
| Midjourney | General | MJ-style aesthetics |
| Google Imagen 4 | General | Google model |
| Ideogram 3.0 | General | Text-in-image specialist |
| Dzine Realistic v3 | Realistic | Photorealistic |
| Dzine Cinematic | Realistic | Cinematic look |
| Studio Photography | Realistic | Studio lighting |
| Dzine 3D Render v2 | 3D | Used by CC Style toggle |
| No Style v2 | General | Neutral/no style applied |

### Custom Styles

The picker also supports creating custom styles:
- **Quick Style:** Upload one reference image → instant style extraction
- **Pro Style:** Upload multiple references → trained style (takes minutes)

### Selecting a Model

```python
# 1. Click the model name to open picker
page.evaluate("""() => {
    var btn = document.querySelector('button.style');
    if (btn) { btn.click(); return true; }
    return false;
}""")
page.wait_for_timeout(2000)

# 2. Click a category (optional)
page.evaluate("""() => {
    for (const el of document.querySelectorAll('*')) {
        var text = (el.innerText || '').trim();
        var r = el.getBoundingClientRect();
        if (text === 'Realistic' && r.x > 200 && r.x < 400 && r.height < 40) {
            el.click(); return true;
        }
    }
    return false;
}""")
page.wait_for_timeout(1000)

# 3. Click desired model in the grid (by thumbnail text label)
page.evaluate(f"""() => {{
    for (const el of document.querySelectorAll('*')) {{
        var text = (el.innerText || '').trim();
        var r = el.getBoundingClientRect();
        if (text === {json.dumps(model_name)} && r.x > 400 && r.y > 300) {{
            el.click(); return true;
        }}
    }}
    return false;
}}""")

# 4. Or use search
page.evaluate("""() => {
    var input = document.querySelector('.style-list-panel input[type="text"]');
    if (input) { input.focus(); input.value = ''; return true; }
    return false;
}""")
page.keyboard.type("Realistic Product", delay=20)
page.wait_for_timeout(1000)
```

---

## Header Bar

The top bar contains project info, zoom, credits, and action buttons.

| Element | Position (x) | CSS Class | Content |
|---------|-------------|-----------|---------|
| Project name | 56 | `.project` (button) | "Untitled" — click to rename |
| Project name text | 68 | `.project-name` (span) | Editable project title |
| Canvas size | 123 | `.size` (button) | "1536 × 864" — click to change |
| Size info | 125 | `.size-info` (span) | Canvas dimensions |
| Zoom | 991 | `.c-scale-ratio` (div) | "77%" — shows current zoom level |
| Image credits | 1077 | `.txt` (span) | "Unlimited" (Master plan) |
| Results tab | 1096 | `.header-item.item-results` (button) | Opens Results panel (right) |
| Video credits | 1163 | `.txt` (span) | "9,000" remaining |
| Earn Credits | 1213 | `.to-refer` (a) | Referral link |
| Layers tab | 1280 | `.header-item.item-layers` (button) | Opens Layers panel (right) |
| Export | 1328 | `.c-export` (div) | Opens Export dialog |

### Results & Layers Tabs

The right sidebar toggles between **Results** and **Layers** panels via header buttons:
- Results: shows generated images with numbered buttons (1, 2) for each result set
- Layers: shows canvas layer stack with visibility/lock controls

---

## Chat Editor Bar

Always visible at the bottom center of the canvas.

| Element | CSS Class | Notes |
|---------|-----------|-------|
| Wrapper | `.chat-editor-bar-wrapper` | Outer container |
| Bar | `.chat-editor-bar` | Inner bar, class includes `hide show show-bar` |
| Inner | `.chat-editor-bar-inner` | Content wrapper |
| Preview | `.selected-layers-preview` | Shows selected layer count |
| Layer count | `.layer-image-count` | Number badge (e.g., "1") |
| Prompt text | `.chat-editor-prompt` | "Describe the desired image" placeholder |

### Expanded Chat Panel

Clicking the chat bar expands it into a full panel:
- Panel wrapper: `.chat-editor-panel-wrapper` at z=199, (392, 709) 656x167
- Bar collapses to height=0 when panel opens
- Uses selected canvas layer(s) as context

| Element | CSS Class | Notes |
|---------|-----------|-------|
| Image list | `.chat-editor-image-list` | Shows selected canvas images (IMG_1, IMG_2...) |
| Add image | `.add-image-wrapper.can-add` | Drag/click to add reference |
| Image tag | `.image-tag` / `.tag-text` | Label like "IMG_1" |
| Prompt input | `.custom-textarea.len-5000` | contentEditable div, 5000 char limit |
| Model param | `.chat-param` / `.option-btn.active` | Shows model name (e.g., "Nano Banana Pro") |
| Option labels | `.option-label` | Model, aspect ratio ("Auto"), quality ("2K") |
| Word count | `.words-nums` | "0/5000" |
| Cost | `.consume-tip` | "20" credits |
| Generate | button text "Generate" | Submits generation |

### Chat Model Selector

Clicking the model `.option-label` opens a dropdown (`.list-header` "Model"):

| Model | Class |
|-------|-------|
| GPT Image 1.5 | `.option-item` |
| **Nano Banana Pro** | `.option-item.active` (default) |
| Nano Banana | `.option-item` |
| Seedream 4.5 | `.option-item` |
| Seedream 4.0 | `.option-item` |
| FLUX.2 Pro | `.option-item` |
| FLUX.2 Flex | `.option-item` |
| FLUX.1 Kontext | `.option-item` |
| GPT Image 1.0 | `.option-item` |

```python
# Open chat editor
page.mouse.click(628, 824)  # Click the prompt area
page.wait_for_timeout(1500)
# Chat panel opens at z=199 — lower than most overlays

# Type a prompt (contentEditable div, not input/textarea)
page.mouse.click(408, 784)  # Click the textarea area
page.keyboard.type("A product photo on white background", delay=20)

# Open model selector dropdown
page.evaluate("""() => {
    var labels = document.querySelectorAll('.option-label');
    for (var l of labels) {
        if ((l.innerText || '').trim() === 'Nano Banana Pro') {
            l.click(); return;
        }
    }
}""")
page.wait_for_timeout(1500)
# Click desired model
page.evaluate("""() => {
    var items = document.querySelectorAll('.option-item');
    for (var item of items) {
        if ((item.innerText || '').trim() === 'FLUX.2 Pro') {
            item.click(); return;
        }
    }
}""")
```

---

## Complete Txt2Img Model List (78 Models)

All models available under "All styles" category:

### Foundation Models (20)
| Model | Notes |
|-------|-------|
| Dzine General | Default all-purpose |
| Dzine 3D Render v2 | 3D rendering |
| Dzine Realistic v3 | Latest photorealistic |
| Dzine Realistic v2 | Previous realistic |
| Realistic | Base realistic |
| FLUX.1 | FLUX first generation |
| GPT Image 1.5 | OpenAI latest |
| Z-Image Turbo | Fast generation |
| Seedream 4.5 | Latest Seedream |
| FLUX.2 Pro | FLUX 2 high quality |
| FLUX.2 Flex | FLUX 2 flexible |
| Nano Banana Pro | Fast, good default |
| Midjourney | MJ-style aesthetics |
| Nano Banana | Basic fast model |
| Seedream 4.0 | Previous Seedream |
| GPT Image 1.0 | Original GPT Image |
| Google Imagen 4 | Google's model |
| Ideogram 3.0 | Text-in-image specialist |
| Seedream 3.0 | Older Seedream |
| Qwen Image | Alibaba model |

### Style Models (58)
Realistic Product, Warm Fables, Impasto Comics, Film Narrative, Metallic Fluid, Battlecraft, Monotone Vogue, Retro Sticker, Playful Enamel, Graffiti Splash, Classic Dotwork, Colorful Felt, Bold Collage, Line & Wash, Luminous Narratives, Piece of Holiday, 3D Pixel, Arcane Elegance, Retro Sci-Fi, Impressionist, Furry, Shimmering Glow, Impressionist Harmony, Minimalist Cutesy, Y2k Games, Elegant B&W, Simplified Scenic, Memphis Illustration, Neo-Digitalism, Neo-Tokyo Noir, Glass World, Miniatures, Bold Linework, B&W Drawing, Paper Cutout, Floral Tattoo, Vintage Engraving, Color Block Chic, Nouveau Classic, Mystical Escape, Cheerful Storybook, Fantasy Hero, Soft Radiance, Bedtime Story, Ceramic Lifelike, Retro Radiance, Luminous Portraiture, Tiny World, Illustrated Drama, Neon Futurism, Narrative Chromatism, Romantic Nostalgia, Rubber Hose Classic, Linear Cartoon, Impasto Realms, Line Scape, Sleek Simplicity, Retro Noir Chromatics

---

## Workflow: Character Sheet to Scene Pipeline (from video f4HcdR3cd4M)

Technique for generating consistent characters across multiple scenes using Nano Banana Pro character sheets as "ingredients."

### When to Use
- Creating multiple scenes featuring the same character (e.g., Ray in different settings)
- Ensuring wardrobe consistency across video segments
- Two-character scenes requiring both identities preserved
- Alternative to CC (Consistent Character) system when more control is needed

### Steps

1. **Prepare reference photo** -- have a clear, well-lit photo of the character
2. **Open Txt2Img** -- click sidebar Txt2Img at `(40, 197)`. This is "Create Image" mode.
3. **Select Nano Banana Pro** -- open style picker, click "Nano Banana Pro"
4. **Set 16:9 aspect ratio** -- click 16:9 in the ratio selector (produces 2720x1530 at 2K)
5. **Set x2 outputs** -- ensure 2 variants are generated per run
6. **Enter character sheet prompt:**
   ```
   Character reference sheet of [detailed character description].
   Top row: front view, left side view, right side view, back view — full body poses.
   Bottom row: face close-ups showing neutral, smiling, serious, and surprised expressions.
   White background, clean illustration, consistent proportions across all views.
   Professional character design reference sheet.
   ```
7. **Generate** -- 20 credits (2K). Wait for 2 outputs.
8. **Select best sheet** -- review both variants, pick the one with most consistent faces across views
9. **Click "Add To Prompt"** on the selected sheet -- this loads it as an "ingredient"
10. **Write scene prompt** -- describe ONLY the scene/action, NOT the character's appearance:
    ```
    [Character] walking through a modern kitchen, morning light, casual pose, photorealistic
    ```
11. **Generate scene** -- character appears consistent with the sheet

### Key Rules

- **ALWAYS keep the character sheet as ingredient** even when a start frame exists. Removing it breaks consistency.
- **Scene prompts only** -- the sheet handles identity; you handle the scene.
- **Wardrobe changes** -- generate a NEW character sheet with different outfit in prompt. Face/body stay consistent; only clothing changes.
- **Two-character scenes** -- upload BOTH character sheets as ingredients. Both identities are preserved in the generated scene.

### Automation Code Pattern

```python
# 1. Generate character sheet
page.mouse.click(40, 197)  # Txt2Img
page.wait_for_timeout(2000)
# Select Nano Banana Pro (see UI map for style picker method)
# Set 16:9 ratio
page.evaluate("""() => {
    var panel = document.querySelector('.c-gen-config.show');
    if (!panel) return;
    for (var el of panel.querySelectorAll('[class*="aspect"] *, [class*="ratio"] *')) {
        if ((el.innerText || '').trim() === '16:9') { el.click(); return; }
    }
}""")
# Fill character sheet prompt and generate...

# 2. After generation, click "Add To Prompt" on best result
# This makes the sheet an ingredient for subsequent generations

# 3. Clear prompt, write scene prompt, generate again
# Character consistency is maintained by the ingredient sheet
```

---

## Workflow: Multi-Character Lip Sync Pipeline

End-to-end pipeline for creating multi-character talking-head videos with Dzine Lip Sync.

### When to Use
- Creating dialogue scenes between two characters
- Product review segments where Ray talks to camera with background characters
- Multi-speaker narration overlaid on character scenes

### Steps

1. **Generate characters** -- use CC mode (SOP 4) or Character Sheet Pipeline (above) to create character images
2. **Place characters in scene** -- use Instant Storyboard or Txt2Img to generate a scene with both characters visible
3. **Open Lip Sync panel** -- click sidebar at `(40, 427)`. Panel: `.lip-sync-config-panel`
4. **Select Pro mode** -- click Pro radio option for 1080p output
5. **Upload face image** -- click `button.pick-image` at (653,404), upload the scene image containing visible faces
6. **Auto-detect faces** -- Dzine detects up to 4 faces in the image
7. **Assign voices per face:**
   - For Ray: upload ElevenLabs TTS audio file (Thomas Louis voice, pre-generated)
   - For other characters: use built-in TTS voices or upload custom audio
8. **Add dialogue entries** -- each entry: select face, type text (400 chars max), set speed, set language
9. **Order timeline** -- arrange dialogue entries in conversation order
10. **Set output quality** -- 720p (faster) or 1080p (36 credits)
11. **Generate** -- 36 credits, 5-10 min processing time
12. **Download result** -- video appears in Results panel

### Credit Budget

| Step | Credits |
|------|---------|
| Character generation (CC) | 4 per character |
| Scene generation (Txt2Img) | 4-20 depending on model |
| Lip Sync (Pro, 1080p) | 36 |
| **Total per dialogue scene** | **~44-60** |

---

## Workflow: Instant Storyboard Pipeline

Combine separately generated images into a unified scene with consistent lighting and shadows.

### When to Use
- Placing two separately generated characters into one scene
- Combining a product image with a background/environment
- Creating composite scenes from multiple reference images

### Steps

1. **Prepare images** -- generate or collect up to 3 separate images (characters, products, backgrounds)
2. **Open Storyboard panel** -- click sidebar at `(40, 778)`. Panel: `.float-storyboard-g`
3. **Select V2** -- click V2 button (default, better quality)
4. **Upload reference images** -- click `button.upload-image-btn.image-item` at (105,162). Upload up to 3 images.
5. **Write prompt with @mentions:**
   ```
   @Image1 and @Image2 standing together in a modern living room, soft natural lighting,
   professional photograph, unified shadows and color grading
   ```
   Each `@ImageN` references the Nth uploaded image.
6. **Set aspect ratio** -- select 16:9 for YouTube frames, or 1:1 for thumbnails
7. **Generate** -- 15 credits. Dzine unifies lighting, shadows, and scale across all referenced images.
8. **Download result** -- fetch from `static.dzine.ai` URL

### Key Notes

- Dzine handles lighting/shadow unification automatically -- no manual compositing needed
- Scale differences between characters are normalized
- Works best when individual images have clean backgrounds (use BG Remove first)
- @mentions are essential -- without them, Dzine may not incorporate all uploaded images

### Automation Code Pattern

```python
# Open Storyboard panel
page.mouse.click(40, 778)
page.wait_for_timeout(2000)

# Upload reference images
upload_btn = page.locator('button.upload-image-btn.image-item').first
with page.expect_file_chooser(timeout=5000) as fc_info:
    upload_btn.click()
fc = fc_info.value
fc.set_files([str(image1_path), str(image2_path)])
page.wait_for_timeout(3000)

# Fill prompt with @mentions
prompt_area = page.locator('.custom-textarea.len-1000').first
prompt_area.click()
page.keyboard.press('Meta+a')
page.keyboard.type(
    "@Image1 and @Image2 in a professional studio setting, "
    "unified lighting, consistent shadows, photorealistic",
    delay=3
)

# Generate (15 credits)
gen_btn = page.locator('button.generative.ready').first
gen_btn.click()
# Poll for result...
```

---

## Best Practices for Automation

1. **Always use JS evaluate for clicks** — CSS selectors are fragile on Dzine's dynamic DOM
2. **Never use `page.go_back()`** — breaks canvas context
3. **Wait after every major action** — Dzine DOM updates are async (min 1-2s)
4. **Close dialogs before every interaction** — tutorials appear randomly
5. **Use position-based clicks** for sidebar icons (stable across sessions)
6. **Use text-based JS evaluate** for panel elements (handles DOM changes)
7. **Monitor Results panel** for generation progress, not Generate button state
8. **Rate limit generations** — Dzine may throttle rapid requests
9. **Close extra tabs before starting** — explore scripts create new tabs each run; 67+ tabs degrades performance. Always clean up:

```python
# Tab cleanup at script start
pages = ctx.pages
for p in pages:
    url = p.url or ""
    if "dzine.ai" in url and kept_one:
        p.close()
    elif url in ("", "about:blank", "chrome://newtab/"):
        p.close()
```
