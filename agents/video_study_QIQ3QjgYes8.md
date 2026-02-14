# Video Study: INSANE DZINE AI Tools - Lip Sync, Storyboards, Image Generation & More

**Source:** https://www.youtube.com/watch?v=QIQ3QjgYes8
**Creator:** Blog With Ben
**Duration:** 20:01
**Date:** 2026-02-13
**Relevance:** Complete Dzine platform walkthrough with detailed coverage of Lip Sync Pro (multi-speaker, timeline editor), new Instant Storyboard tool, Img2Img slider workflow, and results panel shortcuts. Directly informs Ray avatar talking-head pipeline and product scene composition.

---

## 1. Img2Img Workflow (Detailed)

### Step-by-Step Process

1. **Upload base image** -- click Img2Img in sidebar, upload or drag image
2. **Select style** -- e.g., Dzine Realistic V3 (from style panel)
3. **Type description** -- describe desired output in prompt field
4. **Adjust sliders:**

| Slider | Function | Rayviews Use |
|--------|----------|-------------|
| Style Intensity | How much the chosen style affects output | Low for product fidelity, high for artistic scenes |
| Structure Match | Preserves original image composition | HIGH for product images (keep layout intact) |
| Face Match | Maintains facial features from input | HIGH for Ray avatar consistency across variations |
| Color Match | Preserves original color palette | HIGH for Amazon product color accuracy |

5. **Generate** -- produces 4 variations per generation

### Example Shown

Pencil sketch uploaded → Dzine Realistic V3 style → photorealistic transformation with preserved composition. Demonstrates extreme style transformation capability.

---

## 2. Lip Sync (Complete Documentation)

### Access Methods

1. **Sidebar** -- Lip Sync tool in left panel
2. **Results panel shortcut** -- numbered buttons (1-4) on each generated variation → Lip Sync

### Generation Settings

| Setting | Options | Notes |
|---------|---------|-------|
| Generation Mode | Normal / **Pro** | Pro = better movement and clarity (recommended) |
| Output Quality | 720p / **1080p** | 1080p for production content |
| Cost | 36 credits (Pro 720p) | Higher for Pro 1080p |
| Generation Time | 5-10 minutes | Per clip |
| Max Faces | **4 simultaneous** | All detected faces animated |

### Face Input Options

| Option | Description |
|--------|-------------|
| Pick a Face Image | Upload static image for face source |
| Upload a Face Video | Use video for face reference (more natural movement) |

### Audio Input Options

| Option | Description | Rayviews Use |
|--------|-------------|-------------|
| Built-in TTS | Multiple voice presets, 400 char limit, speed slider | NOT recommended (use ElevenLabs instead) |
| Audio Upload | Upload your own audio file | **RECOMMENDED** -- upload ElevenLabs Thomas Louis audio |

### Built-in TTS Voices (for reference)

| Category | Examples |
|----------|----------|
| Named presets | Britney, James |
| Style presets | Narrator, Social Media, Conversational |
| Speed | Adjustable slider |
| Language | Multi-language dropdown (many languages) |
| Character limit | 400 characters per TTS input |

### Aspect Ratio Cropping (Before Generation)

| Ratio | Use Case |
|-------|----------|
| Original | Keep source image dimensions |
| 1:1 | Square (Instagram) |
| 3:4 | Portrait |
| 4:5 | Instagram portrait |
| 9:16 | Vertical video (Shorts/Reels) |
| **16:9** | **Horizontal video (YouTube)** |

### Multi-Speaker Mode

| Feature | Details |
|---------|---------|
| Subjects | A, B, C, D (up to 4) |
| Per-subject | Separate voice assignment + dialogue text |
| Timeline editor | Drag audio tracks to order speaker sequence |
| Use case | Conversation-style scenes, interview format |

### Workflow for Rayviews Lip Sync

1. Generate Ray avatar image (MidJourney V7 for best emotion)
2. Generate ElevenLabs TTS audio (Thomas Louis, per-segment chunk)
3. Open Lip Sync (via sidebar or results panel shortcut)
4. Upload Ray avatar as face image
5. Upload ElevenLabs audio file (NOT built-in TTS)
6. Set: **Pro** mode, **1080p**, **16:9** aspect ratio
7. Generate (5-10 min wait, 36+ credits)
8. Download result via static.dzine.ai URL

---

## 3. Instant Storyboard (NEW Tool)

### Overview

Combines up to 3 separate images into one cohesive scene with unified lighting, matched shadows, and coherent environment. Available in V1 and V2 versions.

### Interface Elements

| Element | Description |
|---------|-------------|
| Image uploads | Up to 3 separate images |
| @mentions | Reference uploaded images in prompt text |
| Prompt area | "Describe your shot" text input |
| Shot angle presets | 4 icons for camera angle selection |
| Output Quality | 720p / 1080p |
| Aspect Ratio | 9:16, 1:1, 16:9 + more |
| Advanced settings | Expandable section for fine-tuning |
| Cost | **15 credits** per generation |

### How @Mentions Work

1. Upload Image 1 (e.g., Ray avatar)
2. Upload Image 2 (e.g., product photo)
3. Upload Image 3 (e.g., environment/background)
4. In prompt: "A person @image1 reviewing a product @image2 at a desk @image3 with soft studio lighting"
5. Dzine composites all three into one coherent scene

### Example from Video

Two separate headshot photos → combined into candlelit dinner scene with:
- Unified lighting across both faces
- Matched shadows on the table
- Coherent restaurant environment
- Natural-looking interaction between subjects

Then Lip Sync applied on top → talking-head conversation in the composite scene.

### Rayviews Use Cases

| Use Case | Image 1 | Image 2 | Image 3 | Prompt |
|----------|---------|---------|---------|--------|
| Product review scene | Ray avatar | Product image | Kitchen background | "Person @1 holding and examining product @2 at a kitchen counter @3 with warm overhead lighting" |
| Desk setup review | Ray avatar | Product image | Desk/office background | "Person @1 showing product @2 on a modern desk @3 with clean natural light" |
| Comparison scene | Product A image | Product B image | Neutral background | "Two products @1 and @2 side by side on a clean surface @3 with studio lighting" |
| Thumbnail scene | Ray avatar (expressive) | Product hero shot | Bold environment | "Person @1 pointing at product @2 in @3 with dramatic lighting" |

---

## 4. Results Panel Shortcut Buttons

### Layout

Each generated image shows numbered buttons (1 through 4, one per variation). Clicking a number reveals action shortcuts that apply to that specific variation.

### Available Shortcuts

| Shortcut | Function | Credits |
|----------|----------|---------|
| Chat Editor | Text-based editing of the variation | 20 |
| AI Editor | Visual editing tools | Varies |
| AI Video | Generate video from the variation | 56-98 |
| Lip Sync | Add lip sync to the variation | 36+ |
| Expression Edit | Adjust facial expression | 4 |
| Face Swap | Replace face in the variation | Varies |
| Enhance & Upscale | Upscale resolution | Varies |

### Chained Workflow Example

1. Generate product scene via Txt2Img or Instant Storyboard
2. Click variation #2 (best result)
3. Click Lip Sync shortcut → add Ray speaking with ElevenLabs audio
4. Click Expression Edit shortcut → adjust to "explaining" expression
5. Click Enhance & Upscale → upscale to 4K for hero thumbnail

All without navigating away from the results panel.

---

## 5. Updated Sidebar Tool Order

| Position | Tool | Status | Notes |
|----------|------|--------|-------|
| 1 | Upload | Standard | Upload images to canvas |
| 2 | Assets | Standard | Manage project assets |
| 3 | Txt2Img | Standard | Text-to-image generation |
| 4 | Img2Img | Standard | Image-to-image transformation |
| 5 | **Instant Storyboard** | **NEW** | Combine 3 images into scene |
| 6 | Character | HOT tag | Build/manage characters |
| 7 | AI Video | Standard | Generate video from image |
| 8 | Lip Sync | Standard | Add lip sync to face |
| 9 | Video Editor | Standard | Edit generated videos |
| 10 | AI Editor | Standard | AI-powered image editing |
| 11 | Face Kit | Standard | Face Swap + Expression Edit |
| 12 | Enhance & Upscale | Standard | Resolution upscaling |
| 13 | **Product Background** | **NEW** | Product isolation + background |

### Changes from Previous Documentation

| Change | Old | New |
|--------|-----|-----|
| Added Instant Storyboard | Not present | Position 5 (after Img2Img) |
| Added Product Background | Not present | Position 13 (last) |
| Face Kit consolidation | Separate Face Swap + Expression Edit | Combined under "Face Kit" |
| Video Editor added | Not documented | Position 9 (after Lip Sync) |

---

## 6. Pipeline-Specific Takeaways

### What Maps Directly to Rayviews Automation

| Video Finding | Pipeline Application |
|--------------|---------------------|
| Lip Sync Pro + audio upload | Upload ElevenLabs audio for Ray talking-head segments (not built-in TTS) |
| Lip Sync 16:9 aspect ratio | Generate YouTube-ready horizontal talking-head clips |
| Lip Sync 5-10 min generation | Factor into pipeline timing — not instant |
| Instant Storyboard @mentions | Combine Ray + product + environment into unified review scenes |
| Storyboard 15 credits | Very affordable for composite scene generation |
| Results panel shortcuts | Chain: generate → lip sync → expression edit from results |
| Face Match slider (Img2Img) | Maintain Ray face consistency through style transformations |
| Structure Match slider | Preserve Amazon product image composition in variations |
| Color Match slider | Preserve Amazon product colors in style variations |
| Multi-speaker Lip Sync | Potential for future conversation-format videos |
| Product Background tool | Isolate products from Amazon images for clean compositions |

### Critical Implementation Notes

| Topic | Note |
|-------|------|
| Audio preference | ALWAYS upload ElevenLabs audio, never use built-in TTS (voice inconsistency) |
| Lip Sync mode | ALWAYS use Pro (Normal quality not suitable for production) |
| Lip Sync output | ALWAYS use 1080p (720p too low for YouTube) |
| Lip Sync ratio | ALWAYS use 16:9 for YouTube landscape format |
| Storyboard images | Max 3 images per generation — plan compositions accordingly |
| Face Match | Keep HIGH for any Ray avatar Img2Img variation |
| Credits budget | Lip Sync Pro 1080p ~ 36+ credits per clip. Storyboard ~ 15 credits. Unlimited images but video credits are finite (9K). |

### Workflow: Full Ray Talking-Head Segment

```
1. Txt2Img (MidJourney V7) → Ray avatar hero shot [4-40 credits]
2. Instant Storyboard → Ray + product + environment composite [15 credits]
3. Expression Edit → Set appropriate expression for segment [4 credits]
4. Lip Sync Pro → Upload ElevenLabs audio, 1080p, 16:9 [36+ credits]
5. Download → static.dzine.ai URL, no auth [0 credits]
Total: ~60-95 credits per segment
```

With 9,000 video credits and unlimited image credits, this supports approximately 95-150 talking-head segments before needing to account for video credit budget.

---

## 7. Comparison with Previous Dzine Documentation

| Topic | Previous Docs | Video Finding | Update Needed |
|-------|--------------|---------------|---------------|
| Sidebar tools | 12 tools | 13 tools (+ Instant Storyboard, Product Background) | Yes — update dzine_playbook.md |
| Lip Sync details | Basic (Normal/Pro, 720p/1080p, 36 credits) | Full (multi-speaker, timeline, TTS, audio upload, aspect ratios, 4-face) | Yes — update dzine_workspace_guide.md |
| Instant Storyboard | Not documented | Full workflow with @mentions, 3 images, 15 credits | Yes — add to all Dzine docs |
| Results panel | Not documented in detail | Full shortcut button mapping per variation | Yes — add to dzine_playbook.md |
| Img2Img sliders | Mentioned | Full slider names and functions documented | Yes — update dzine_workspace_guide.md |
| Face Kit | Separate Face Swap + Expression Edit | Consolidated under "Face Kit" in sidebar | Yes — update sidebar mapping |

---

## Action Items

### Immediate (This Week)

- [ ] **Test Lip Sync Pro** -- generate Ray talking-head with ElevenLabs audio upload, Pro mode, 1080p, 16:9
- [ ] **Test Instant Storyboard** -- combine Ray avatar + product image + environment into unified review scene
- [ ] **Update dzine_workspace_guide.md** -- add Instant Storyboard, update sidebar order, add Lip Sync details
- [ ] **Update dzine_playbook.md** -- add results panel shortcuts, chained workflow documentation

### Short-Term (This Month)

- [ ] **Build Lip Sync automation** in dzine_browser.py -- navigate to Lip Sync, upload face + audio, set Pro/1080p/16:9, generate
- [ ] **Build Instant Storyboard automation** -- multi-image upload, @mention prompt composition, generate
- [ ] **Map results panel shortcut selectors** -- CSS selectors for each shortcut button per variation
- [ ] **Test multi-speaker Lip Sync** -- two subjects with separate ElevenLabs voices for conversation format
- [ ] **Test Product Background tool** -- isolate Amazon product images for clean compositions

### Medium-Term (Next Month)

- [ ] **Integrate chained workflow** -- automated generate → storyboard → lip sync → expression edit pipeline
- [ ] **Build Lip Sync credit budget tracker** -- track video credit consumption per pipeline run (9K total)
- [ ] **Evaluate Video Editor tool** -- determine if useful for post-lip-sync editing within Dzine

---

## Sources

- [Blog With Ben — INSANE DZINE AI Tools](https://www.youtube.com/watch?v=QIQ3QjgYes8)
- [Dzine Canvas Editor](https://www.dzine.ai/canvas)
- [Dzine Pricing](https://www.dzine.ai/pricing)

---

*Analysis: Manual video analysis + cross-reference with existing Dzine documentation | Study date: 2026-02-13 | Video duration: 20:01*
