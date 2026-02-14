# Video Study: Create Talking AI Characters with Perfect Lip Sync (Dzine Tutorial)

**Source:** https://www.youtube.com/watch?v=_2IGR79NNF0
**Creator:** Wulfranz
**Duration:** 5:08
**Date:** 2026-02-13
**Relevance:** Demonstrates end-to-end workflow for creating realistic AI characters with Nano Banana Pro and animating them with multi-speaker lip sync. Directly applicable to Ray avatar talking-head segments. Also reveals complete AI video model catalog with credit pricing for B-roll generation.

---

## 1. Character Generation with Nano Banana Pro

### Why Nano Banana Pro

Creator tested both Flux 2 and Nano Banana Pro for character generation. Nano Banana Pro was chosen exclusively because:

- **Better context understanding** -- follows complex prompts more accurately
- **More realistic output** -- skin, hair, lighting details are more natural
- **Consistent identity** -- same character looks recognizable across generations

This aligns with the current Rayviews pipeline default (Nano Banana Pro for most generation tasks).

### Img2Img Settings for Character Scenes

Settings visible during podcast studio scene creation:

| Setting | Value | Notes |
|---------|-------|-------|
| Style Intensity | 0.6 (Medium) | Balances style application with source fidelity |
| Structure Match | 0.6 (Very Similar) | Preserves character pose and composition |
| Face Match | ON (toggle) | Critical for maintaining character identity in new scenes |
| Quality | HQ | Higher detail output |
| Cost | 16 credits | Per HQ Img2Img generation |

### Workflow

1. Generate character portrait via Txt2Img with Nano Banana Pro
2. Use Img2Img to place character into desired scene (podcast studio, desk, etc.)
3. Face Match toggle ensures face consistency between portrait and scene
4. Generate multiple variations, select best

---

## 2. Multi-Character Lip Sync

### Core Capability

Lip Sync can detect and animate **up to 4 faces simultaneously** in a single image. Each face receives independent voice and dialogue assignment.

### Multi-Speaker Setup

| Feature | Details |
|---------|---------|
| Max simultaneous faces | 4 |
| Per-face assignment | Separate voice + dialogue text |
| Timeline editor | Drag audio tracks to order speaker sequence |
| Custom voice | Upload own audio files (e.g., ElevenLabs) |
| Built-in TTS | Multiple presets, 400 char limit, speed slider |
| Generation time | 5-10 minutes per complete sequence |

### Timeline Editor

The timeline shows individual audio tracks per speaker (Subject A, B, C, D). Tracks can be:

- **Reordered** by dragging to set conversation flow
- **Timed** to control pauses between speakers
- **Assigned** separate voices for each speaker

### Workflow for Podcast-Style Setup

1. Generate 2-4 character portraits with Nano Banana Pro
2. Create podcast studio scene via Img2Img with all characters (Face Match ON)
3. Open Lip Sync on the composite scene
4. System detects all faces automatically
5. Assign voices to each detected face (upload audio or select TTS)
6. Enter dialogue text per speaker (400 char limit each)
7. Arrange speaker order in timeline editor
8. Set speed per speaker
9. Generate (5-10 minutes)

---

## 3. AI Video Model Catalog (Complete Pricing)

Visible in the Dzine interface during the tutorial:

| Model | Credits | Duration | Notes |
|-------|---------|----------|-------|
| Wan 2.2 Flash | 26-52 | 5s | Fast, affordable |
| Wan 2.1 | 6 | 5s | Cheapest, Uncensored |
| Seedance Pro Fast | 7-35 | 5s | Variable pricing |
| Seedance Lite | TBD | TBD | Lightweight version |
| Kling 2.5 Turbo STD | 30 | 5s | Mid-range |
| Kling 2.1 Master | 215 | 5s | Premium, 1080p |
| Kling 2.1 Std | 43 | 5s | Standard quality |
| Kling 2.1 Pro | 90 | 5s | High quality |
| Kling 1.6 Standard/Pro | TBD | TBD | Older generation |
| Minimax Hailuo 02 | 15-30 | 4s | 1080p, good value |
| Minimax Hailuo | 36 | 6s | Longer clips |
| Luma Ray 2 Flash | 41 | 5s | Fast generation |

### Comparison with Current Pipeline Config

| Current Setting | Value | Catalog Match |
|-----------------|-------|---------------|
| Pipeline default | Minimax Hailuo 2.3 (56-98 credits) | Not directly visible -- may be newer or renamed |
| Budget option | Not configured | Wan 2.1 at 6 credits/5s |
| Mid-range option | Not configured | Minimax Hailuo 02 at 15-30 credits/4s 1080p |
| Premium option | Not configured | Kling 2.1 Master at 215 credits/5s 1080p |

### Cost-Per-Second Analysis

| Model | Credits/Second | Quality Tier |
|-------|---------------|-------------|
| Wan 2.1 | 1.2 | Budget |
| Seedance Pro Fast | 1.4-7.0 | Variable |
| Wan 2.2 Flash | 5.2-10.4 | Mid-budget |
| Kling 2.5 Turbo STD | 6.0 | Mid-range |
| Minimax Hailuo 02 | 3.75-7.5 | Mid-range 1080p |
| Minimax Hailuo | 6.0 | Standard |
| Kling 2.1 Std | 8.6 | Standard |
| Luma Ray 2 Flash | 8.2 | Standard |
| Kling 2.1 Pro | 18.0 | High |
| Kling 2.1 Master | 43.0 | Premium 1080p |

---

## 4. Additional Features Demonstrated

### Built-in Prompt Improver

- Toggle in the generation interface
- Auto-enhances prompts with detail, style cues, and quality modifiers
- Useful for quick generation but may alter product-specific details
- Test before enabling for pipeline use

### Custom Voice Import

- Lip Sync accepts uploaded audio files
- For Rayviews: upload ElevenLabs Thomas Louis audio (stability 0.50, similarity 0.75)
- Maintains voice branding consistency that built-in TTS cannot provide
- Audio file should be pre-generated externally (300-450 word chunks)

---

## 5. Pipeline-Specific Takeaways

### What Maps Directly to Rayviews Automation

| Video Finding | Pipeline Application |
|--------------|---------------------|
| Nano Banana Pro for characters | Confirms default model choice for Ray avatar generation |
| Img2Img Face Match ON | Use when placing Ray into product review scenes |
| Style Intensity 0.6 / Structure Match 0.6 | Starting point for character-scene Img2Img settings |
| Multi-face lip sync (4 faces) | Enables potential dual-character review format |
| Timeline editor for speaker order | Sequence dialogue in conversation-format segments |
| Custom voice upload | Upload ElevenLabs audio (NOT built-in TTS) |
| 5-10 min generation time | Factor into pipeline timing estimates |
| 16 credits HQ Img2Img | Budget for character scene generation |
| AI video model catalog | Optimize B-roll model selection by quality-to-credit ratio |

### Optimal Img2Img Settings for Ray Avatar Scenes

| Slider | Recommended | Rationale |
|--------|-------------|-----------|
| Style Intensity | 0.5-0.6 | Enough to adapt scene, not so much it changes character |
| Structure Match | 0.6-0.7 | Preserve character pose and framing |
| Face Match | ON (always) | Critical for Ray identity consistency |
| Quality | HQ (always) | Unlimited credits, no reason to economize |
| Cost | 16 credits | Negligible with Master plan |

### Video Model Selection for B-Roll

| B-Roll Type | Recommended Model | Credits | Rationale |
|-------------|------------------|---------|-----------|
| Simple product animation | Wan 2.1 | 6/5s | Cheapest, adequate for simple motion |
| Product demo clip | Minimax Hailuo 02 | 15-30/4s | 1080p, good quality-to-cost |
| Environment/lifestyle | Minimax Hailuo 2.3 | 56-98 | Current default, proven quality |
| Hero product reveal | Kling 2.1 Pro | 90/5s | Premium quality for key moments |

---

## Action Items

### Immediate (This Week)

- [ ] **Test character-to-scene workflow** -- generate Ray portrait with Nano Banana Pro, then Img2Img into product review environment with settings from video (0.6/0.6/Face Match ON)
- [ ] **Test multi-character lip sync** -- create two-character scene, assign separate voices, verify timeline editor workflow
- [ ] **Cross-reference AI video model catalog** -- verify which models are available in current Dzine account, check Minimax Hailuo 2.3 naming
- [ ] **Update dzine_schema.py** -- add Img2Img default settings (style_intensity=0.6, structure_match=0.6, face_match=True) for character scenes

### Short-Term (This Month)

- [ ] **Test budget B-roll models** -- compare Wan 2.1 (6 credits) vs Seedance Pro Fast (7-35 credits) vs Minimax Hailuo 02 (15-30 credits) for simple product animations
- [ ] **Build conversation-format template** -- two-character scene with alternating lip sync for product discussion format
- [ ] **Test prompt improver** -- enable/disable comparison on 10 product-specific prompts to measure impact on image fidelity

### Medium-Term (Next Month)

- [ ] **Implement video model routing** -- add model selection logic based on clip type (budget/standard/premium) to pipeline config
- [ ] **Build multi-speaker lip sync automation** -- extend dzine_browser.py to handle face detection, voice assignment, timeline ordering
- [ ] **Create Ray + co-host character pair** -- standardize two-character setup for future conversation-format videos

---

## Sources

- [Wulfranz -- Create Talking AI Characters with Perfect Lip Sync](https://www.youtube.com/watch?v=_2IGR79NNF0)
- [Dzine Canvas Editor](https://www.dzine.ai/canvas)
- [Dzine Pricing](https://www.dzine.ai/pricing)

---

*Analysis: Manual video analysis + frame-level inspection + cross-reference with existing Dzine documentation | Study date: 2026-02-13 | Video duration: 5:08*
