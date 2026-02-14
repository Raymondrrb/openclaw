# Dzine Workspace Guide — Automation Reference

Last verified: 2026-02-12

## Account

- User: Ramon Reis (Master plan)
- Fast Image Credits: Unlimited
- Video Credits: 9,000
- Browser: OpenClaw Brave (CDP port 18800)

---

## Architecture

Dzine is a canvas-based editor at `https://www.dzine.ai/canvas?id=<project_id>`. Projects are created from the home page (`/home`). The canvas has three main zones:

1. **Left sidebar** — tool switcher (12 tools)
2. **Center canvas** — image composition area with layers
3. **Right panel** — Results / Layers tabs
4. **Bottom bar** — Chat Editor (prompt + model + generate)
5. **Top bar** — project name, canvas tools, undo/redo, zoom, export

---

## Left Sidebar Tools (top to bottom)

| Tool | Purpose | Credits |
|------|---------|---------|
| Upload | Upload images/3D models to canvas | - |
| Assets | Browse uploaded assets | - |
| **Txt2Img** | Text-to-image generation (full controls) | 4 (Normal), 8 (HQ) |
| **Img2Img** | Image-to-image transformation | 4 |
| **Character** | Consistent character management | 4 |
| AI Video | Text/image to video | varies |
| **Lip Sync** (HOT) | Face + audio → talking video | 36 |
| Video Editor | Edit generated videos | - |
| Motion Control | Control motion in videos | varies |
| **Enhance & Upscale** (NEW) | Upscale/enhance images | varies |
| Image Editor | Advanced image editing | - |
| Instant Storyboard | Create storyboards | varies |

---

## Two Generation Modes

### 1. Chat Editor (Bottom Bar)
- **Prompt**: `div.custom-textarea.len-5000[contenteditable='true'][data-prompt='true']`
- **Model selector**: `button.option-btn` → opens `div.option-list`
- **Generate**: `button#chat-editor-generate-btn.generative` (20 credits)
- **Reference upload**: `button.upload-image-btn.image-item` (icon left of prompt)
- **Reference via @**: Type `@` in prompt to reference canvas layers
- **Settings icons** between model and generate: aspect ratio, negative prompt, etc.
- Prompt limit: 5000 chars

### 2. Txt2Img Panel (Left Sidebar)
- **Style selector**: `button.style` → opens style picker (96+ styles)
- **Prompt textarea**: `textarea` inside `.gen-config-form` (1800 char limit)
- **Prompt Improver**: toggle to auto-enhance prompts
- **Aspect Ratio**: 3:4, 1:1, 4:3, canvas (uses current canvas size)
- **Face Match** (NEW): match faces across generations
- **Color Match**: match color palette from reference
- **Non-Explicit**: content safety filter (default ON)
- **Generation Mode**: Fast / Normal / HQ
- **Advanced**: additional settings (negative prompt, seed, etc.)
- **Generate**: `button#txt2img-generate-btn` (4 credits Normal, 8 credits HQ)

**Use Txt2Img for product images** — more control, cheaper per image.

---

## Available Models (Chat Editor)

| Model | Notes |
|-------|-------|
| **Nano Banana Pro** | Default, best for product photography |
| GPT Image 1.5 | OpenAI-based |
| Nano Banana | Older version |
| Seedream 4.5 | |
| Seedream 4.0 | |
| FLUX.2 Pro | |
| FLUX.2 Flex | |
| FLUX.1 Kontext | |
| GPT Image 1.0 | Older |

---

## Available Styles (Txt2Img — 96+)

### Categories
Favorites, My Styles, Recent, All styles, General, Realistic, Illustration, Portrait, 3D, Anime, Line Art, Material Art, Logo & Icon, Character, Scene, Interior, Tattoo, Legacy

### Key Styles for Product Photography
| Style | Best For |
|-------|----------|
| **Dzine General** | All-purpose, good default |
| **Dzine Realistic v3** | High realism |
| **Dzine Realistic v2** | Realism |
| **Realistic Product** | Product photos specifically |
| **Nano Banana Pro** | High quality generation |
| **Film Narrative** | Cinematic product shots |
| **Luminous Portraiture** | Portrait/avatar work |
| **Soft Radiance** | Soft lighting products |

### Custom Styles
- **Quick Style**: Learn from one reference image in seconds
- **Pro Style**: Learn from multiple references in minutes
- Use "Create a style" in the style picker

---

## Character Tool

### Modes
1. **Build Your Character** — Upload reference face photos, name the character, Dzine learns the face
2. **Manage Your Characters** — View/edit saved characters
3. **Generate Images** — "With your character" — generate new images keeping the character consistent
4. **Insert Character** — Place character into existing images
5. **Character Sheet** — Generate turnaround sheets from prompt
6. **Generate 360° Video** — Create 3D rotation from character image

### Workflow for "Ray" Avatar
1. Generate an initial avatar via Txt2Img (realistic portrait prompt)
2. Go to Character → Build Your Character
3. Upload the generated avatar as reference
4. Name it "Ray"
5. For each video: Character → Generate Images → describe the scene/pose
6. Dzine maintains Ray's face consistency across generations

---

## Lip Sync Tool

### Panel Controls
- **Face Input**: "Pick a Face Image" (from canvas) OR "Upload a Face Video"
- **Audio Input**: Upload audio file (MP3/WAV from ElevenLabs)
- **Generation Mode**: Normal (basic) / Pro (better movement & clarity)
- **Output Quality**: 720p / 1080p
- **Cost**: 36 credits per generation

### Workflow for Ray Talking Head Videos
1. Generate Ray avatar image via Character tool (consistent framing)
2. Generate voiceover via ElevenLabs (Thomas Louis voice)
3. In canvas: place Ray avatar image on canvas layer
4. Lip Sync tool → Pick face from canvas layer
5. Upload ElevenLabs audio
6. Set Pro mode + 1080p
7. Generate → exports as video

### Multiple Lip Sync
Available at `/tools/multiple-lip-sync/` — supports multiple speakers in one scene.

---

## Generation Results

After generation, a "Generation Complete!" dialog shows with numbered action buttons per result:

| Action | What it does |
|--------|-------------|
| Variation | Create variations of the result |
| Chat Editor | Send result to chat for further editing |
| Image Editor | Open in detailed editor |
| AI Video | Convert to video |
| Lip Sync | Apply lip sync to face |
| Expression Edit | Change facial expression |
| Face Swap | Swap face in the image |
| Enhance & Upscale | Upscale/enhance quality |

### Result Preview Actions (5 icons at bottom of preview)
1. **Navigate** (arrow) — switch between results
2. **Favorite** (star) — save to favorites
3. **Fullscreen** (expand) — view full size
4. **Download** (arrow down) — download image file
5. **Close** (X) — close preview

---

## Export

- **Button**: `button.export` in top toolbar
- **Disabled** when no content on canvas (no layers)
- **Enabled** after placing results on canvas
- Downloads the full canvas composition as an image

---

## Canvas Structure

- **Canvas size**: configurable via aspect ratio (1:1, 3:4, 9:16, 4:3, 16:9, Custom)
- **Width/Height**: number inputs (default 1536x1536)
- **Layers panel**: shows all layers on canvas (Background + added images)
- **Upload zone**: Accepts JPG, PNG, WEBP, PSD images and GLB, GLTF, OBJ 3D models

---

## Top Processing Tools

Available above the canvas area:
- AI Eraser — remove unwanted elements
- Hand Repair — fix AI-generated hand artifacts
- Expression — change facial expressions
- BG Remove — remove background

Additional icons: crop, perspective, SVG, 3D view, favorites, download layer

---

## URL Structure

| URL | Page |
|-----|------|
| `/home` | Dashboard with recent projects |
| `/projects` | All projects listing |
| `/asset` | Asset & Result library (My Assets, All Results) |
| `/aiTools` | AI Tools hub |
| `/canvas?id=<id>` | Canvas editor (main workspace) |
| `/community/list/all` | Community styles and creations |
| `/pricing/` | Plan details |
| `/tutorials` | Tutorial videos |
| `/api/` | API documentation |

---

## Automation Selectors (Updated 2026-02-12)

### Canvas Editor — Critical Selectors

```python
SELECTORS = {
    # Login state
    "avatar_button": "button.avatar",
    "login_button": 'button:has-text("Log in")',
    "dashboard_button": 'button:has-text("Dashboard")',

    # Chat Editor (bottom bar)
    "chat_prompt": "[contenteditable='true'].custom-textarea.len-5000",
    "chat_prompt_alt": "[contenteditable='true'][data-prompt='true']",
    "chat_generate": "#chat-editor-generate-btn",
    "chat_model_btn": "button.option-btn:has(.option-label)",
    "chat_model_list": "div.option-list",
    "chat_model_item": "div.option-item",
    "chat_ref_upload": "button.upload-image-btn.image-item",

    # Model selection
    "nano_banana_pro": 'div.option-item:has-text("Nano Banana Pro")',
    "model_active": "div.option-item.active",

    # Txt2Img panel
    "txt2img_sidebar": 'text="Txt2Img"',
    "txt2img_style_btn": ".c-style button.style",
    "txt2img_prompt": ".gen-config-form textarea, .base-prompt textarea",
    "txt2img_generate": "#txt2img-generate-btn",
    "txt2img_ratio_1_1": '.c-aspect-ratio button:has-text("1:1")',
    "txt2img_ratio_16_9": '.c-aspect-ratio button:has-text("16:9")',
    "txt2img_mode_fast": 'button:has-text("Fast")',
    "txt2img_mode_normal": 'button:has-text("Normal")',
    "txt2img_mode_hq": 'button:has-text("HQ")',
    "txt2img_advanced": 'text="Advanced"',

    # Img2Img panel
    "img2img_sidebar": 'text="Img2Img"',
    "img2img_structure_match": "[class*='structure']",

    # Character panel
    "character_sidebar": 'text="Character"',
    "build_character": 'text="Build Your Character"',
    "manage_characters": 'text="Manage Your Characters"',
    "generate_with_character": 'text="Generate Images"',
    "insert_character": 'text="Insert Character"',

    # Lip Sync panel
    "lip_sync_sidebar": 'text="Lip Sync"',
    "lip_sync_generate": ".gen-config-body button:has-text('Generate')",
    "lip_sync_pick_face": 'text="Pick a Face Image"',
    "lip_sync_upload_video": 'text="Upload a Face Video"',
    "lip_sync_normal": ".gen-config-body text='Normal'",
    "lip_sync_pro": ".gen-config-body text='Pro'",
    "lip_sync_720p": 'button:has-text("720p")',
    "lip_sync_1080p": 'button:has-text("1080p")',

    # Results
    "results_tab": ".header-item.item-result",
    "layers_tab": ".header-item.item-layers",
    "result_images": ".result-panel img, .material-v2-result-content img, .result-item img",
    "result_empty": 'text="No Results Available"',
    "result_preview": "#result-preview",
    "result_preview_download": "#result-preview button:nth-child(4)",

    # Export
    "export_btn": "button.export",

    # Top tools
    "ai_eraser": 'text="AI Eraser"',
    "hand_repair": 'text="Hand Repair"',
    "expression": 'text="Expression"',
    "bg_remove": 'text="BG Remove"',

    # Canvas
    "canvas": "#canvas",
    "canvas_upload_area": 'text="CLICK, DRAG or PASTE here to upload assets"',

    # Size dialog
    "size_cancel": 'button.cancel:has-text("Cancel")',
    "size_apply": 'button.done:has-text("Apply")',
    "width_input": "input[type='number']:first-of-type",
    "height_input": "input[type='number']:last-of-type",

    # Style picker
    "style_search": ".style-picker input, [placeholder*='Search styles']",
    "style_item": "[class*='style-item']",
}
```

### Navigation Selectors

```python
NAV_SELECTORS = {
    "sidebar_home": 'a[href="/home"]',
    "sidebar_projects": 'a[href="/projects"]',
    "sidebar_assets": 'a[href="/asset"]',
    "sidebar_ai_tools": 'a[href="/aiTools"]',
    "new_project": 'text="New project"',
    "project_item": "button.project-item",
}
```

---

## Credit Costs

| Action | Credits |
|--------|---------|
| Txt2Img (Fast) | 2 |
| Txt2Img (Normal) | 4 |
| Txt2Img (HQ) | 8 |
| Chat Editor generate | 20 |
| Lip Sync | 36 |
| Enhance & Upscale | varies |
| AI Video | varies |

**Master plan**: Unlimited fast image credits. Use Txt2Img Normal/HQ for product images (4-8 credits each vs 20 for Chat Editor).

---

## Generation Timing

| Mode | Approximate Time |
|------|-----------------|
| Txt2Img Fast | ~15-20s |
| Txt2Img Normal | ~30-40s |
| Txt2Img HQ | ~50-120s ("HQ for this style takes 2 min") |
| Chat Editor | ~30-60s |
| Lip Sync | ~60-180s (varies with video length) |

---

## Known Issues / Tips

1. **Promotional popup** appears on every page load — close with `button:has-text("Not now")`
2. **Size dialog** opens when creating new project — close with Cancel or Apply
3. **Result preview overlay** (`#result-preview`) intercepts clicks — use `force=True` or Escape to close
4. **"Please select a layer"** warning in Character/Lip Sync — must have an image on canvas first
5. **Bottom chat editor** hides when Txt2Img/Img2Img panel is open — the bottom bar changes context
6. **Multiple prompt areas**: Chat Editor uses `len-5000` contenteditable, Txt2Img uses `textarea` (1800 chars)
7. **File inputs** are hidden (`display:none`) — use `set_input_files()` directly
8. **`/tools/z-image/`** is a marketing landing page, NOT the workspace
9. **Enhance & Upscale** button text is "Enhance" in sidebar, class `upscale-tab-btn`
10. **API available** at `/api/` — Text-to-Image, Image-to-Image, Face Swap endpoints

---

## Recommended Pipeline Workflow

### Product Images — Faithful (per video, SOP 5)
**WARNING: Img2Img does NOT preserve product identity.** Even at 98% Structure Match, it generates completely different objects. Use BG Remove + Generative Expand instead:
1. Navigate to `/home` → "Start from an image" → upload Amazon product photo
2. BG Remove (action bar, free, ~11s) → transparent background
3. Image Editor → Expand → 16:9 → prompt: "Clean white studio backdrop with soft professional lighting" → Generate (8 credits, 4 variants, ~75s)
4. Download best variant from Results panel via `static.dzine.ai` URL

### Product Images — Stylized (lifestyle/mood shots, SOP 2)
Use Txt2Img when exact product fidelity is NOT required (stylized/artistic shots):
1. Create project: `/home` → New project → 16:9 canvas
2. Txt2Img panel → Seedream 4.5 model → describe product + environment
3. Results appear in right panel → download from result preview

### Ray Avatar Scenes — Img2Img (SOP 6)
Img2Img is appropriate for character scenes (NOT products):
1. Generate Ray via CC → upload to canvas
2. Img2Img → Structure Match 0.6, Style Intensity 0.6, Face Match ON
3. Describe scene/environment → Generate (16 credits HQ)

### Ray Avatar (per video)
1. Use saved "Ray" character
2. Character → Generate Images → describe slight variation (different clothing/angle)
3. Face Match ensures consistent face
4. Result: talking-head frame for Lip Sync

### Lip Sync (per video)
1. Place Ray avatar on canvas
2. Lip Sync tool → Pick face from canvas
3. Upload ElevenLabs voiceover audio
4. Pro mode + 1080p
5. Generate → video result

### Thumbnail
1. New project at 16:9 (2048x1152)
2. Upload #1 product reference image
3. Txt2Img with thumbnail prompt template
4. Space left for text overlay (added in DaVinci Resolve)
