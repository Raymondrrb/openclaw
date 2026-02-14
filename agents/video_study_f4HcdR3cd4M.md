# Video Study: Consistent Character Sheets in Nano Banana (Prompts Included!)

**Source:** https://www.youtube.com/watch?v=f4HcdR3cd4M
**Creator:** AI Video School
**Duration:** 4:38
**Date:** 2026-02-13
**Relevance:** Demonstrates the EXACT technique needed for the Ray Avatar Plan -- create one master character reference sheet, then use it as an ingredient in every generation to maintain identity consistency across all videos. Covers wardrobe changes, two-character scenes, and the critical rule of ALWAYS including the sheet as an ingredient in video generation.

---

## 1. Character Reference Sheet Structure

### What the Sheet Contains

Generated in **16:9 format** with two rows:

| Row | Views | Purpose |
|-----|-------|---------|
| Top row | Full body: front, left side, right side, back | Body proportions, clothing, posture reference |
| Bottom row | Face close-ups: front, 3/4, side | Facial features, expression, hair reference |

### Why 16:9 Format

The 16:9 aspect ratio provides enough horizontal space to fit all angle views without cramping. Each view gets sufficient resolution for the AI model to extract identity features.

### Generation Quality

Nano Banana Pro produces incredibly detailed character sheets from a single reference photo. The multi-angle views are internally consistent -- same face, same proportions, same lighting across all views.

---

## 2. Character Sheet Generation Workflow

### Step-by-Step

1. **Upload reference photo** -- clean, well-lit photo of the character (or AI-generated portrait)
2. **Select "Create Image" mode** -- not Img2Img, not Chat Editor
3. **Choose Nano Banana Pro** -- best model for structured multi-view generation
4. **Paste character sheet prompt** -- specific prompt available in video description
5. **Set 16:9 aspect ratio** -- critical for fitting all angle views
6. **Set x2 outputs** -- generates two sheets, select the best one
7. **Generate** -- wait for results
8. **Select best sheet** -- verify all angles are present and consistent

### The Character Sheet Prompt

A specific prompt (shared in the video description) reliably generates the multi-angle reference layout. The prompt instructs the model to create:

- Full body views from 4 angles
- Face close-up views from 3 angles
- Consistent lighting across all views
- White or neutral background for clean reference

### Key Settings

| Setting | Value |
|---------|-------|
| Model | Nano Banana Pro |
| Mode | Create Image |
| Aspect Ratio | 16:9 |
| Outputs | x2 (for selection) |
| Input | Single reference photo |

---

## 3. Using the Character Sheet (Sheet-to-Scene)

### Add To Prompt Workflow

1. Generate character sheet (as above)
2. Click **"Add To Prompt"** button on the generated sheet
3. Write a scene prompt describing the desired environment and action
4. Generate -- the sheet serves as the identity reference for the scene

### Example Outputs

- Character in casual clothing at a desk (from character sheet of same person)
- Character in military gear in an outdoor setting (wardrobe change, same face/body)
- Two characters together in one scene (from two separate character sheets)

### Wardrobe Changes

The character sheet anchors **identity** (face, body proportions) while the scene prompt controls **wardrobe and environment**:

| Scene Prompt Specifies | Character Sheet Provides |
|------------------------|-------------------------|
| Clothing / outfit | Face shape and features |
| Environment / setting | Body proportions |
| Lighting / mood | Hair style and color |
| Pose / action | Distinguishing features |

This means Ray can wear different clothing per video while remaining unmistakably the same character -- exactly what the Rayviews pipeline needs.

---

## 4. Using the Character Sheet (Sheet-to-Video)

### The Critical Rule

**ALWAYS include the character sheet as an ingredient when generating video, even when you already have a start frame.**

Without the sheet: video model may drift from character appearance as frames progress.
With the sheet: face, body, and features remain stable throughout the clip.

### Ingredients to Video Workflow

1. **Add start image** -- the scene/frame you want to animate
2. **Add character sheet as ingredient** -- the identity anchor (ALWAYS include this)
3. **Write video prompt** -- describe the desired motion and action
4. **Select "ingredients to video" mode** -- not standard image-to-video
5. **Generate** -- character consistency maintained throughout

### Why This Matters for Rayviews

Every video clip of Ray must look like the same person. Without the character sheet ingredient, subtle drift accumulates: slightly different nose, different eye spacing, different jawline. The sheet acts as a constraint that the video model uses to maintain identity fidelity across every generated frame.

---

## 5. Two-Character Scenes

### How It Works

1. Generate character sheet for Character A (e.g., Ray)
2. Generate character sheet for Character B (e.g., product expert, co-host)
3. Upload **both** character sheets as references
4. Write scene prompt describing both characters interacting
5. Generate -- both characters appear with their own consistent identities

### Rayviews Use Cases

| Use Case | Character A | Character B |
|----------|------------|------------|
| Product discussion | Ray | Product expert |
| Before/after comparison | Ray (casual) | Ray (professional) -- same sheet, different prompts |
| Dual review format | Ray | Co-host character |
| Customer perspective | Ray (reviewer) | Customer character |

---

## 6. UI Details from Frames

### Navigation Path

The video shows: **Flow > Character Reference Sheets > Scenebuilder** view within Nano Banana Pro's workspace. This structured Flow interface helps organize the character-to-scene pipeline.

### Key UI Elements

| Element | Function | Location |
|---------|----------|----------|
| "Add To Prompt" button | Chains generated image as ingredient for next generation | On each result in results panel |
| 16:9 aspect ratio selector | Sets generation format for character sheet | In generation settings |
| x2 output toggle | Generates two variations for selection | In generation settings |
| Scenebuilder view | Structured character → scene → video pipeline | Under Flow in workspace |

---

## 7. Pipeline-Specific Takeaways

### What Maps Directly to Rayviews Automation

| Video Finding | Pipeline Application |
|--------------|---------------------|
| Character sheet as identity anchor | Create ONE master Ray sheet, use in ALL generations |
| 16:9 multi-angle format | Standard Ray reference format (full body + face close-ups) |
| Add To Prompt chaining | Streamlined sheet → scene workflow |
| Sheet as video ingredient (ALWAYS) | Include Ray sheet in every video generation call |
| Wardrobe changes with same identity | Ray wears different outfits per video but remains recognizable |
| Two-character scenes | Enable conversation/dialogue format with dual character sheets |
| Nano Banana Pro for sheets | Confirmed best model for structured multi-view generation |

### Critical Implementation Rules

| Rule | Rationale |
|------|-----------|
| ALWAYS include character sheet in video generation | Prevents identity drift across frames |
| ALWAYS use 16:9 for character sheets | Fits all angle views without cramping |
| ALWAYS use Nano Banana Pro for sheets | Best model for structured multi-view layout |
| ALWAYS generate x2 outputs | Selection improves final sheet quality |
| Save master sheet to persistent storage | Reuse across all pipeline runs without regeneration |

### Comparison with Current Pipeline Approach

| Topic | Current State | Video Finding | Action |
|-------|--------------|---------------|--------|
| Ray character reference | Not yet created | Character sheet technique demonstrated | Generate master Ray sheet immediately |
| Character consistency | Rely on Face Match slider | Sheet as ingredient + Face Match for double consistency | Add sheet ingredient to all generations |
| Video generation | Start frame only | Start frame + character sheet ingredient | Update video generation workflow |
| Wardrobe variation | Not implemented | Scene prompt controls wardrobe, sheet controls identity | Enable per-video wardrobe changes |
| Model for sheets | Seedream 4.5 (from Zvw0Fk9FVl4 study) | Nano Banana Pro demonstrated with excellent results | Test both, compare results |

### Note on Model Choice for Character Sheets

The Zvw0Fk9FVl4 study (Dzine official channel) found Seedream 4.5 best for character sheets. This video demonstrates Nano Banana Pro producing excellent results. Both should be tested with the Ray reference photo to determine which produces better multi-angle consistency for the specific Ray character.

---

## Action Items

### Immediate (This Week)

- [ ] **Generate Ray master character sheet** -- upload reference photo to Nano Banana Pro, use character sheet prompt, 16:9, x2 outputs
- [ ] **Also test with Seedream 4.5** -- compare with Nano Banana Pro results for Ray specifically
- [ ] **Test sheet-to-scene** -- use Ray sheet as ingredient, generate 3 product review environments (desk, kitchen, living room)
- [ ] **Test sheet-to-video** -- generate video with and without character sheet ingredient, compare identity consistency
- [ ] **Test wardrobe changes** -- same Ray sheet, 3 different outfits (casual, professional, outdoor)

### Short-Term (This Month)

- [ ] **Save Ray master sheet** to Supabase storage (rayviewslab-assets bucket) and local pipeline assets
- [ ] **Update dzine_schema.py** -- add character_sheet_url parameter to all generation functions
- [ ] **Update dzine_browser.py** -- auto-upload Ray character sheet as ingredient for every scene and video generation
- [ ] **Build character sheet generation automation** -- upload ref → Nano Banana Pro → prompt → 16:9 → x2 → select best
- [ ] **Test two-character scene** -- Ray + second character for potential dialogue format

### Medium-Term (Next Month)

- [ ] **Build character sheet quality validation** -- automated check for required angles in generated sheet
- [ ] **Create Ray wardrobe library** -- 5-10 outfit variants generated from master sheet
- [ ] **Explore Scenebuilder Flow interface** -- determine if it offers additional automation hooks
- [ ] **Build character sheet refresh workflow** -- regenerate if identity drift detected over time
- [ ] **Document the character sheet prompt** -- save adapted version in dzine_prompt_library.md

---

## Sources

- [AI Video School -- Consistent Character Sheets in Nano Banana](https://www.youtube.com/watch?v=f4HcdR3cd4M)
- [Dzine Canvas Editor](https://www.dzine.ai/canvas)
- [Dzine Pricing](https://www.dzine.ai/pricing)

---

*Analysis: Manual video analysis + frame-level inspection + cross-reference with existing Dzine documentation | Study date: 2026-02-13 | Video duration: 4:38*
