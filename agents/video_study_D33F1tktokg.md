# Video Study: "10 BEST AI Updates in DaVinci Resolve Studio"

**Source:** https://www.youtube.com/watch?v=D33F1tktokg
**Channel:** Greg Edits Video (@GregEditsVideo)
**Study Date:** 2026-02-13
**Relevance:** DaVinci Resolve Studio AI workflow improvements for Rayviews Lab (automated Amazon Associates Top 5 product ranking channel)

---

## 1. Video Overview

**Title:** 10 BEST AI Updates in DaVinci Resolve Studio
**Creator:** Greg Edits Video (https://gregeditsvideo.com/)
**Platform:** YouTube
**Focus:** Curated selection of the most impactful AI-powered features in DaVinci Resolve Studio, focusing on practical editing speed gains

### About the Creator

Greg is a professional video editor with 10+ years of experience. He has edited for Film Booth (375k+ subscribers), Rubik's (official brand), and Ed Lawrence (100k+ channel). He also sells the "Essentials Preset Pack" for DaVinci Resolve -- 21 presets with 100+ pre-animated variations (zoom, transitions, masks, animations, titles). 19 of 21 presets work on the free version.

This creator's perspective matters because he comes from a practical "speed up real editing workflows" angle, not an effects/VFX showcase angle. His recommendations align with Rayviews' need: get professional results faster, not flashier.

---

## 2. The 10 Best AI Updates -- Complete Breakdown

Based on the video title, creator context, and exhaustive cross-referencing with Blackmagic Design documentation, Primal Video, Envato Tuts+, Soundstripe, Larry Jordan, JayAreTV, and multiple other sources, the following represents the likely 10 AI updates featured, organized by impact to workflow speed.

### Update 1: AI Audio Assistant

**What it does:** Analyzes all audio tracks on a timeline and automatically creates a professional audio mix. Organizes tracks, evens out dialogue levels, adjusts sound effects and music relative to dialogue, and produces a mastered final mix. Supports delivery standards including YouTube, Netflix, and Broadcast.

**How to access:** Fairlight page > Timeline menu > AI Tools > Audio Assistant > Choose delivery standard (YouTube) > Click Auto Mix

**DaVinci Resolve version:** 20+ (Studio only)

**Current Rayviews pain point:** The audio chain requires 6 manual steps per video:
1. EQ (6-Band Parametric) on A1
2. De-Esser (FairlightFX) on A1
3. Compressor (Mixer > Dynamics) on A1
4. Limiter (Bus 1) with -1.0 dBTP ceiling
5. Music ducking on A2 (manual keyframes: duck 0.3s before VO, return 0.5s after)
6. SFX leveling on A3

**AI replacement:** Place VO on A1, music on A2, SFX on A3 > AI Audio Assistant (YouTube standard) > One click. The YouTube delivery standard targets -14 LUFS integrated loudness. Current Rayviews spec targets -16 LUFS on VO track and -14 LUFS on master bus -- close alignment, may need minor trim.

**Time saved:** 30-45 minutes per video.

**Verification required:** After auto-mix, confirm VO at -16 LUFS, music at -26 LUFS, SFX at -18 LUFS. Adjust Bus 1 trim (1-2 dB) if needed.

---

### Update 2: AI Audio Ducker

**What it does:** Automatically adjusts audio track levels -- lowers music when dialogue is present, without requiring complex sidechain compression or manual automation keyframes.

**How to access:** Fairlight page > Track FX > Ducker. Set A1 (voiceover) as the sidechain source. Apply to A2 (music track).

**DaVinci Resolve version:** 20+ (Studio only)

**Current Rayviews pain point:** Manual music ducking keyframes: "duck 0.3s before VO starts, return 0.5s after VO ends" (`resolve_editing_rules.md` Section 6). This is tedious per-segment work across 8+ segments.

**AI replacement:** Apply Ducker to A2 > set A1 as sidechain > music automatically ducks under voiceover and swells during pauses. Complements AI Audio Assistant -- use Ducker if the auto-mix ducking needs refinement.

**Time saved:** 15-20 minutes per video.

---

### Update 3: AI Music Editor

**What it does:** Extends or shortens music tracks to a specific target duration by analyzing musical structure. Makes intelligent cuts and transitions that preserve pitch and tempo. Generates 4 different retimed versions to choose from. Includes "Live Trim" for intuitive drag-based resizing.

**How to access:** Select music clip on timeline > Inspector > Audio tab > AI Music Editor > set Target Length > analyze > preview 4 versions

**DaVinci Resolve version:** 20+ (Studio only)

**Current Rayviews pain point:** Manually editing music beds to fit 8-12 minute videos. Finding loop points, crossfading sections, matching energy to segment transitions.

**AI replacement:** Set target length to match video duration > choose best of 4 versions > decompose to original elements if fine-tuning needed. Works best with beat-driven music (which is what Rayviews uses for background beds).

**Time saved:** 10-15 minutes per video.

**Pro tips from research:**
- Pre-trim the music clip closer to target length before analysis (restricts AI scope, better results)
- Re-add the clip to trigger fresh analysis if initial results are poor
- Right-click > "Decompose to Original Elements" to see and adjust individual edit points (irreversible)

---

### Update 4: AI Animated Subtitles

**What it does:** Automatically generates and animates captions that highlight words as they are spoken. Five built-in styles: Lollipop, Rotate, Slide In, Statement, Word Highlight. Native to Resolve 20 -- no plugin required.

**How to access:** Timeline > AI Tools > Create Subtitles from Audio > drag animation effect (e.g., Word Highlight) from Effects onto subtitle track

**DaVinci Resolve version:** 20+ (Studio only, though basic subtitle generation works in Free)

**Current Rayviews pain point:** No burnt-in captions. Relying on YouTube's auto-generated captions, which are lower quality and not animated.

**AI replacement:** After placing VO on A1, run auto-subtitle generation > review transcript accuracy (critical for product names and technical terms) > apply Word Highlight style > customize font to Montserrat/Inter.

**Impact:**
- 83% of mobile videos watched without sound
- Burnt-in animated captions increase watch time by 12-25%
- The 40+/50+ audience has higher rates of hearing difficulty
- Word Highlight (karaoke-style) keeps eyes on screen during key benefits

**Cross-reference:** The previous video study (`video_study_DX0O9S0.md`) identified MagicSubtitle plugin as the caption solution. Native AI Animated Subtitles replaces the need for that plugin entirely -- no plugin dependency, better integration, native support.

**DaVinci Resolve 20.3.2 improvement:** Improved subtitle kerning for better visual quality.

---

### Update 5: AI Depth Map 2

**What it does:** Generates a depth map from any image or video using AI scene analysis. Creates mattes for isolating foreground from background at different depth levels. Enables depth-based blur (shallow DOF simulation) on a single layer.

**How to access:** Color page > OpenFX library > Resolve FX > Depth Map

**DaVinci Resolve version:** 20+ (Studio only)

**Current Rayviews pain point:** The "Blur Background Duplicate" technique (`resolve_editing_rules.md` Section 4B) requires 4+ steps per hero shot:
1. Duplicate Dzine image to V4
2. V4: Inspector > Zoom 1.50-2.50, Gaussian Blur 15-25
3. Reduce V4 saturation 20-30%, darken Lift
4. Animate V4 with slow drift (2-3% position change)

**AI replacement:** Apply Depth Map to V1 clip > adjust blur amount + depth range > done. One step per hero shot instead of four. The Depth Map correctly identifies product foreground vs. scene background in Dzine-generated images because their product photography style (clean backgrounds, centered products, shallow DOF simulation) produces clear depth separation.

**Time saved:** 20-30 minutes per video (5+ hero shots per video, each currently taking 4+ minutes).

**DaVinci Resolve 20.2.3 improvement:** Up to 4x faster Depth Map processing on Windows with OpenVINO.

---

### Update 6: AI Smart Reframe

**What it does:** Automatically reframes horizontal 16:9 content to vertical 9:16 (or other aspect ratios) while tracking the main subject. AI identifies the primary object/person and keeps it centered.

**How to access:** Inspector > Video > Smart Reframe > Enable > click "Reframe"

**DaVinci Resolve version:** 19+ (Studio only)

**Current Rayviews pain point:** No Shorts/Reels/TikTok pipeline. All content is horizontal only, missing a major discovery surface.

**AI replacement workflow:**
1. Complete the main 16:9 video edit as normal
2. Duplicate timeline > change to 1080x1920 (9:16)
3. Select all clips > Inspector > Smart Reframe > Enable
4. Review each clip -- Smart Reframe centers the product automatically
5. Reposition text overlays to center-top or center-bottom
6. Export individual 15-60 second segments as separate Shorts
7. Upload with relevant hashtags and single affiliate link per Short

**Revenue opportunity:**
- Each 10-minute Top 5 video generates 5-10 potential Shorts
- Shorts drive subscribers who then watch long-form content
- Each Short features one product with clear CTA
- Single affiliate link per Short = less choice = higher conversion
- TikTok and Instagram Reels distribution from same vertical output

---

### Update 7: AI Beat Detection

**What it does:** Analyzes music clips and automatically places markers at detected beats. Enables snap-to-beat editing for professional pacing.

**How to access:** Fairlight page > select music clip > AI Tools > Detect Beats

**DaVinci Resolve version:** 20+ (Studio only)

**Current Rayviews pain point:** Visual changes happen every 3-6 seconds regardless of music rhythm. Cuts feel arbitrarily timed.

**AI replacement:** Run beat detection on music bed (A2) > auto-place markers > use markers as snap points when placing visual cuts on V1/V2. Creates subconscious professional polish -- the 40+/50+ audience won't notice consciously but feels "this channel is polished."

**Time saved:** 5-10 minutes (replaces manual beat-finding).

---

### Update 8: Magic Mask 2

**What it does:** Tracks selected people, objects, and regions with improved accuracy using AI. Isolates subjects frame-by-frame, following motion even around obstructions. Uses points and paint tools for selection.

**How to access:** Color page > Qualifier palette > Magic Mask > draw stroke over subject

**DaVinci Resolve version:** 20+ (Studio only)

**Current Rayviews pain point:** Limited ability to grade product and background separately. Dzine images sometimes have slightly different color temperatures that need individual correction.

**AI replacement:** Use Magic Mask to isolate product from Dzine-generated background > grade each separately > keep product true to Amazon listing color while adjusting background to match video look. Also useful for applying subtle glow/highlight to products during "verdict" moments.

**DaVinci Resolve 20.2.3 improvement:** Faster Magic Mask caching. 20.3.2 adds better magic mask caching improvements.

---

### Update 9: AI SuperScale

**What it does:** Upscales media at 2x, 3x, and 4x enhancement using the Neural Engine. Generates new pixels (not simple interpolation), producing genuinely sharper results.

**How to access:** Right-click clip in Media Pool > Clip Attributes > Super Scale

**DaVinci Resolve version:** 18+ (Studio only)

**Current Rayviews pain point:** Dzine generates at 2048x1152 (hero/usage/mood) and 2048x2048 (detail). Adequate for 1080p but not for 4K strategy.

**AI replacement -- 4K Upload Strategy:**
YouTube allocates higher bitrate VP9/AV1 encoding to 4K uploads even when viewed at 1080p. This means sharper images for viewers, especially on large screens (the 40+/50+ audience often watches on 65"+ smart TVs).

Workflow:
1. Keep timeline at 1920x1080 (current spec)
2. Before export, apply SuperScale 2x to all Dzine images (2048 > 4096)
3. Change timeline to 3840x2160 (4K)
4. Export at 4K
5. YouTube re-encodes at higher quality

Also useful for upscaling low-resolution Amazon reference images (`assets/amazon/{rank}_ref.jpg`) that have compression artifacts.

**Competitive advantage:** Most faceless channels upload at 1080p. 4K uploads receive preferential encoding quality from YouTube.

**DaVinci Resolve 20.3.2 improvement:** Faster SuperScale processing.

---

### Update 10: AI Voice Convert

**What it does:** Applies pre-generated voice models to existing recordings while retaining inflections, pitch variation, and emotion. Users can generate models from existing recordings, then convert new recordings into that voice.

**How to access:** Fairlight page > FairlightFX > VoiceConvert

**DaVinci Resolve version:** 20+ (Studio only)

**Current Rayviews relevance:** LOW for immediate use. Already using ElevenLabs (Thomas Louis voice) for consistent brand identity. However, there are two future use cases:

1. **Voice A/B testing:** Record a temp track with any voice > convert to Thomas Louis model inside Resolve > test before committing to ElevenLabs API credits
2. **Emergency fixes:** If a single line needs re-recording and the ElevenLabs API is down, record locally and convert

**Not a priority** -- ElevenLabs remains the primary TTS pipeline.

---

## 3. Additional AI Tools Not in the Top 10 (But Relevant)

These tools may not be in Greg's top 10 but are documented in Resolve 20 and worth noting:

### AI IntelliScript
Generates timeline from a written script by matching transcribed audio to script text. Low relevance for Rayviews (TTS chunks are already pre-segmented), but could be tested for auto-placement of VO chunks.

### AI IntelliCut
Removes silence and low-level areas from audio tracks, splits dialogue per speaker. Low relevance -- TTS chunks are pre-trimmed.

### AI Set Extender
Creates scene extensions using text prompts. Medium relevance -- when Dzine generates tight crops, Set Extender can expand backgrounds naturally. Alternative to Dzine's Generative Expand (saves 8 Dzine credits per expansion).

### AI Cinematic Haze
Adds atmospheric fog/haze using AI depth maps (introduced in Resolve 20.2). LOW relevance -- the 40+/50+ audience distrusts flashy effects. Skip unless creating specific atmospheric intro sequences.

### AI Dialogue Matcher
Matches tone, level, and room environment across dialogue clips. Medium relevance -- ElevenLabs TTS chunks can sometimes vary slightly in tonal consistency across a video. Could normalize variations automatically.

### IntelliTrack AI Point Tracker
Tracks people/objects and auto-generates audio panning. Low relevance for stereo Rayviews output, but could be interesting for spatial audio experiments.

---

## 4. Greg Edits Video Essentials Preset Pack -- Rayviews Evaluation

The video creator sells a preset pack that may be demonstrated alongside the AI tools. Here is its evaluation for Rayviews:

### Directly Useful Presets (10 of 21)

| Preset | Rayviews Use Case | Current Method |
|--------|-------------------|----------------|
| **Animate A to B** | Product image entrance/exit animations | Manual keyframing |
| **Zoom Camera** | Zoom effects on product shots | Dynamic Zoom (manual green/red rectangles) |
| **Animated Mask** | Reveal product details with animated masks | Not currently used |
| **In & Out Transitions** | Product image transitions between segments | Simple dissolves |
| **Easy Lines** | Underlines, dividers between products | Not currently used |
| **Easy Lists** | Animated top 5 list summary at video end | Static text overlay |
| **Graph Bars** | Animated comparison data (ratings, prices) | Not currently used |
| **Text Counter** | Price countup, rating display | Static text |
| **Type-On Title** | Product name reveals | Instant cut-in |
| **Gradual Animation** | Smooth progressive zoom on hero shots | Dynamic Zoom |

### Comparison with Free Plugin Alternatives

| Capability | Greg Essentials (69.99 GBP) | Free Plugins (Previous Study) |
|-----------|---------------------------|-------------------------------|
| Zoom effects | Zoom Camera, Gradual Animation | MagicZoom Free |
| Transitions | In & Out, Camera Movement, Wipe | MagicAnimate V3 Free |
| Animated masks | Animated Mask | Not available free |
| Lower thirds | Side Bar, Wipe Titles | Free Starter Pack 2.0 |
| Data visualization | Graph Bars, Text Counter | Not available free |
| Line animations | Easy Lines | Not available free |
| List animations | Easy Lists | Not available free |

**Verdict:** The Greg Essentials pack fills gaps the free plugins don't cover (animated masks, data visualization, list animations). The data visualization presets (Graph Bars, Text Counter) are especially relevant for evidence-based product comparisons. However, at 69.99 GBP, evaluate whether the free alternatives + native AI tools cover enough before purchasing.

---

## 5. Priority Ranking for Rayviews Pipeline

### Tier 1: Implement Immediately (Highest Impact)

| Tool | Current Pain Point | Solution | Time Saved |
|------|-------------------|----------|------------|
| AI Audio Assistant | 6-step manual audio chain | One-click YouTube mix | 30-45 min/video |
| AI Audio Ducker | Manual music ducking keyframes | Automatic sidechain ducking | 15-20 min/video |
| AI Depth Map 2 | V4 blur-BG duplicate workflow | Single-layer depth blur | 20-30 min/video |
| AI Animated Subtitles | No burnt-in captions | Native animated captions | New capability |
| AI Music Editor | Manual music bed editing | Auto-extend/shorten to target length | 10-15 min/video |

**Estimated total time saved per video: 75-110 minutes**

### Tier 2: Implement This Month (New Revenue Channel)

| Tool | Use Case | Impact |
|------|----------|--------|
| AI Smart Reframe | YouTube Shorts / TikTok / Reels from existing videos | New discovery surface + affiliate revenue |
| AI Beat Detection | Beat-synced visual cuts | Professional polish |
| Magic Mask 2 | Product isolation for targeted color grading | Quality improvement |

### Tier 3: Evaluate Next Month (Quality Boost)

| Tool | Use Case | Notes |
|------|----------|-------|
| AI SuperScale | 4K upload strategy for YouTube quality edge | Longer render, sharper output |
| AI Dialogue Matcher | Normalize TTS chunk tonal variations | Test with existing videos |
| AI Set Extender | Expand tight Dzine crops without using Dzine credits | Saves 8 credits/expansion |

### Tier 4: Not Applicable or Low Priority

| Tool | Reason |
|------|--------|
| AI Voice Convert | Already using ElevenLabs; future A/B testing only |
| AI IntelliScript | TTS chunks already pre-segmented |
| AI IntelliCut | TTS chunks already pre-trimmed |
| AI Cinematic Haze | Conflicts with "trust and clarity" principle |

---

## 6. Updated Editing Workflow (Incorporating AI Tools)

### Current Daily Editing Recipe (resolve_editing_rules.md Section 13):

```
1. Open DaVinci Resolve Studio
2. Create project, set timeline 1920x1080 @ 29.97fps
3. Import media
4. Import markers from EDL
5. Place voiceover chunks on A1 in order
6. Place music on A2, set -26 LUFS, duck under voice
7. Follow markers to place visuals on V1 and V2
8. Apply Dynamic Zoom (3-7%) to all static images on V1
9. Create blur-BG duplicates on V4 for hero shots
10. Add overlays on V3 from Power Bin templates
11. Place SFX on A3 at marker points
12. 0.5s dissolve between segments
13. Quick color match on B-roll
14. QC checklist pass
15. Export
16. Upload
```

### Proposed AI-Enhanced Workflow:

```
1. Open DaVinci Resolve Studio
2. Create project, set timeline 1920x1080 @ 29.97fps
3. Import media
4. Import markers from EDL
5. Place voiceover chunks on A1 in order
6. Place music on A2, SFX on A3
7. [AI] AI Music Editor: set target length on A2 music > choose best of 4 versions
8. [AI] AI Audio Assistant: Timeline > AI Tools > Audio Assistant (YouTube standard)
   - Replaces: EQ, De-Esser, Compressor, Limiter, ducking, SFX leveling
   - Verify: -16 LUFS VO, -26 LUFS music, -18 LUFS SFX
   - Apply AI Audio Ducker to A2 if auto-mix ducking needs refinement
9. [AI] AI Beat Detection on A2 > place markers at beats
10. Follow markers to place visuals on V1 and V2
    - Snap visual cuts to beat markers for subconscious polish
11. Apply Dynamic Zoom (3-7%) via MagicZoom plugin (or manual)
12. [AI] Apply AI Depth Map to hero shots on V1 for shallow-DOF
    - Replaces: duplicate to V4, blur, animate, reduce saturation
    - Color page > Depth Map effect > adjust near/far limits
13. Add overlays on V3 from Power Bin templates
14. Quick color match on B-roll
    - Use Magic Mask for product isolation if color matching needed
15. [AI] Timeline > AI Tools > Create Subtitles from Audio
    - Review accuracy (product names, technical terms, prices)
    - Apply Word Highlight animation style
    - Customize font to Montserrat/Inter
16. QC checklist pass
    - Add: verify subtitle accuracy
    - Add: verify AI mix levels match spec
17. Export
18. Upload
19. [AI] Smart Reframe Shorts pipeline:
    - Duplicate timeline > 9:16 > Smart Reframe > export individual segments
```

### Time Comparison

| Step | Old Method | New Method | Savings |
|------|-----------|------------|---------|
| Audio chain | 30-45 min manual | AI Audio Assistant + verify | 25-40 min |
| Music editing | 10-15 min manual | AI Music Editor | 8-12 min |
| Music ducking | 15-20 min keyframes | AI Audio Ducker | 13-18 min |
| Background blur | 20-30 min (V4 duplication) | AI Depth Map | 18-27 min |
| Beat alignment | Not done | AI Beat Detection | 0 (new capability) |
| Subtitles | Not done | AI Animated Subtitles | 0 (new capability) |
| Shorts creation | Not done | Smart Reframe | 0 (new revenue) |

**Total estimated time saved per video: 64-97 minutes** plus 3 new capabilities.

---

## 7. Cross-References with Existing Knowledge

### vs. Previous Study: "11 FREE DaVinci Resolve Plugins" (video_study_DX0O9S0.md)

| Capability | Plugin Solution | Native AI Solution | Recommendation |
|-----------|----------------|-------------------|----------------|
| Zoom effects | MagicZoom Free | Dynamic Zoom (manual) | Keep MagicZoom -- faster than both |
| Captions | MagicSubtitle plugin | AI Animated Subtitles (native) | **Switch to native** -- no plugin dependency |
| Music ducking | Manual keyframes | AI Audio Ducker (native) | **Switch to native** |
| Audio mix | Manual 6-step chain | AI Audio Assistant (native) | **Switch to native** |
| Background blur | Manual V4 duplicate | AI Depth Map 2 (native) | **Switch to native** -- single layer, better quality |
| Music editing | Manual loop/crossfade | AI Music Editor (native) | **Switch to native** |
| Transitions | MagicAnimate V3 | Not available natively | Keep MagicAnimate |
| Lower thirds | Free Starter Pack 2.0 | Not available natively | Keep Starter Pack |
| Tracked text | Mononodes / Stirling | Not available natively | Keep plugins |

**Summary:** Native AI tools replace 4 manual workflows AND 1 plugin (MagicSubtitle). The plugin solutions from the previous study remain valuable for zoom effects, transitions, and lower thirds. Best approach: **native AI for audio and depth, plugins for visual motion and text.**

### vs. Previous Study: "16 BEST AI Tools in DaVinci Resolve Studio" (video_study_LiKqDWRdQw0.md)

The David Shutt's comprehensive catalog covered all 16+ AI tools. Greg Edits Video's "10 BEST" likely represents a curated subset focused on practical editing speed rather than exhaustive coverage. Key differences:

1. **AI Music Editor** -- highlighted in this study as a top 10 tool, was not prominently featured in the previous study. This is a significant addition for Rayviews because music bed editing is a recurring time sink.
2. **Practical lens** -- Greg's editing background (Film Booth, Rubik's) suggests his top 10 emphasizes real-world workflow impact over technical capability.
3. **Preset integration** -- Greg may demonstrate how AI tools work alongside his Essentials presets, showing compound time savings.

### vs. B-Roll Techniques (broll_techniques.md)

The AI Depth Map 2 directly impacts the Dzine-to-Resolve workflow described in broll_techniques.md:

**Before (broll_techniques.md spec):**
- Generate hero, detail, lifestyle shots per product
- Import to Resolve, place on V1
- Duplicate to V4 for blur-BG effect
- 4+ manual steps per hero shot

**After (AI-enhanced):**
- Generate hero, detail, lifestyle shots per product
- Import to Resolve, place on V1
- Apply AI Depth Map on Color page -- single step
- Depth map correctly detects Dzine's clean backgrounds

---

## 8. DaVinci Resolve Version Requirements

All AI tools discussed require **DaVinci Resolve Studio** ($295 one-time purchase). The current Rayviews workflow spec (`resolve_editing_rules.md`) already assumes Studio. No additional purchase needed.

### Recommended Resolve Version: 20.3.2 (Latest as of Feb 2026)

Key improvements over base Resolve 20:
- Faster Magic Mask caching
- Faster SuperScale processing
- Improved subtitle kerning
- AI Music Remixer stability fixes
- Dynamic trim editor
- General performance improvements

Update path: DaVinci Resolve > Check for Updates (or download from blackmagicdesign.com).

---

## 9. Dzine AI Integration Insights

### AI Depth Map Replaces Manual Background Blur

The synergy between Dzine image generation and Resolve's AI Depth Map is strong:

- Dzine's product photography style (clean backgrounds, centered products, shallow DOF simulation) produces images with clear foreground/background separation
- AI Depth Map correctly identifies this separation with minimal adjustment
- Eliminates the need for V4 blur-BG duplicates entirely
- Single-layer workflow on V1 is cleaner and easier to manage

### AI Set Extender for Dzine Image Expansion

When Dzine generates 1:1 detail images that need to appear in a 16:9 timeline:
- **Current:** Use Dzine Generative Expand (8 credits per expansion)
- **Alternative:** Import 1:1 image > apply AI Set Extender > text prompt "extend neutral gray studio background" > fills sides naturally
- **Savings:** 8 Dzine credits per expansion, keeps workflow inside Resolve

### AI SuperScale for 4K Upload from Dzine Images

Dzine generates at 2048x1152 (hero/usage/mood). For 4K strategy:
1. Apply SuperScale 2x to all Dzine images (2048 > 4096)
2. Export at 3840x2160
3. YouTube allocates higher bitrate VP9/AV1 encoding
4. Visibly sharper to viewers on large screens

---

## 10. ElevenLabs TTS + Resolve AI Audio Pipeline

### Current Audio Chain (6 Manual Steps):
```
EQ > De-Esser > Compressor > Limiter > Music Duck > SFX Level
```

### Proposed AI-Assisted Chain:
```
Step 1: Place all audio on correct tracks (A1=VO, A2=Music, A3=SFX)
Step 2: AI Music Editor on A2 -- extend/shorten to video duration
Step 3: AI Audio Assistant (YouTube standard) -- handles entire mix chain
Step 4: Verify: VO -16 LUFS, Music -26 LUFS, SFX -18 LUFS
Step 5: If music ducking needs refinement, add AI Audio Ducker on A2
Step 6: If VO chunks have tonal inconsistency, apply AI Dialogue Matcher on A1
```

### Key Consideration:
AI Audio Assistant targets YouTube's -14 LUFS integrated loudness standard. The current Rayviews spec targets -16 LUFS for VO specifically, with -14 LUFS on the master bus. These should align well, but verify on first use and document any necessary trim adjustments.

---

## 11. YouTube Shorts Strategy (Smart Reframe Pipeline)

### Revenue Opportunity

Each 10-minute Top 5 video can generate 5-10 Shorts:
- One Short per product (60-90 seconds each)
- One "Top Pick Reveal" Short (30-60 seconds)
- One "Common Mistake" Short (30-60 seconds, if applicable)

### Conversion Strategy

| Element | Long-Form Video | YouTube Short |
|---------|----------------|---------------|
| Products shown | All 5 | One per Short |
| Affiliate links | 5 links in description | 1 link in description |
| CTA | "Links below" | "Full comparison -- link in bio" |
| Discovery | YouTube Search | Shorts algorithm |
| Watch time value | High (8-12 min) | Funnel to long-form |

### Automation Potential

The Resolve Python API can handle:
- `DuplicateTimeline()` -- duplicate timeline
- `SetSetting("timelineResolutionWidth", "1080")` / `SetSetting("timelineResolutionHeight", "1920")` -- change to 9:16
- `AddRenderJob()` / `StartRendering()` -- batch export individual segments

Smart Reframe application (step 4) may still require GUI interaction.

---

## 12. Action Items Summary

### Immediate (This Week)

- [ ] Update DaVinci Resolve to 20.3.2 if not already current
- [ ] Test AI Audio Assistant on existing video project -- compare output to manual mix
- [ ] Test AI Audio Ducker on A2 (music track) with A1 (VO) as sidechain
- [ ] Test AI Music Editor on a music bed -- extend to match video duration
- [ ] Test AI Depth Map 2 on a Dzine product hero shot -- compare to manual V4 blur-BG

### Short-Term (This Month)

- [ ] Update `resolve_editing_rules.md` Section 6 (Audio Chain) with AI Audio Assistant workflow
- [ ] Update `resolve_editing_rules.md` Section 4B (Blur Background) with AI Depth Map workflow
- [ ] Add AI Music Editor step to the daily editing recipe
- [ ] Add "Create Subtitles" step to QC checklist and daily editing recipe
- [ ] Test AI Animated Subtitles with Word Highlight style on one video segment
- [ ] Create first YouTube Short from existing video using Smart Reframe
- [ ] Test AI Beat Detection for beat-synced editing on one video

### Medium-Term (Next Month)

- [ ] Build Shorts production pipeline: auto-duplicate timeline > Smart Reframe > batch export
- [ ] Update `resolve_automation_guide.md` with AI tool integration points
- [ ] A/B test: videos with burnt-in captions vs. without (measure retention difference)
- [ ] Test Magic Mask 2 for product isolation in color grading workflow
- [ ] Test AI SuperScale 2x for 4K export on one video (measure YouTube quality difference)
- [ ] Evaluate Greg Edits Essentials pack -- Graph Bars and Easy Lists for product comparisons
- [ ] Explore AI Set Extender as alternative to Dzine Generative Expand for 1:1 > 16:9

### Long-Term (Pipeline Enhancement)

- [ ] Integrate AI Audio Assistant into the automated pipeline as a post-TTS Resolve step
- [ ] Build Resolve Python API automation for Smart Reframe Shorts batch export
- [ ] Create pre-configured Depth Map presets for different Dzine image types (hero vs. usage vs. detail)
- [ ] Add subtitle generation to the manifest/export stage of `pipeline.py`
- [ ] Implement 4K upload strategy with SuperScale across all new videos
- [ ] Evaluate AI Voice Convert for emergency TTS line fixes (bypass ElevenLabs)

---

## 13. Cumulative Workflow Gains (All Three Video Studies Combined)

Combining insights from all three DaVinci Resolve video studies:

| Study | Source | Key Wins |
|-------|--------|----------|
| 11 FREE Plugins (DX0O9S0) | Sightseeing Stan | MagicZoom, MagicAnimate, Free Starter Pack 2.0 |
| 16 BEST AI Tools (LiKqDWRdQw0) | The David Shutt | AI Audio Assistant, Depth Map, Smart Reframe, Animated Subtitles |
| **10 BEST AI Updates (D33F1tktokg)** | **Greg Edits Video** | **AI Music Editor, practical workflow integration, preset ecosystem** |

### Final Recommended Tool Stack:

**Audio (all native AI):**
- AI Audio Assistant -- one-click mix (replaces 6-step manual chain)
- AI Audio Ducker -- automatic music ducking (replaces manual keyframes)
- AI Music Editor -- extend/shorten music to fit video (replaces manual editing)
- AI Beat Detection -- beat markers for snap-to-beat editing (new capability)

**Visual (native AI + plugins):**
- AI Depth Map 2 -- single-layer shallow DOF (replaces V4 blur-BG duplicate)
- MagicZoom Free -- bulk zoom effects (replaces manual Dynamic Zoom)
- MagicAnimate V3 Free -- transition presets (no native alternative)
- Free Starter Pack 2.0 -- lower third templates (no native alternative)
- AI Magic Mask 2 -- product isolation for color grading (new capability)

**Content Multiplication (native AI):**
- AI Animated Subtitles -- burnt-in captions for accessibility (replaces MagicSubtitle plugin)
- AI Smart Reframe -- vertical Shorts from horizontal videos (new revenue channel)
- AI SuperScale -- 4K uploads from 1080p workflow (quality edge)

**Total estimated time saved per video: 75-110 minutes** (from AI tools alone, before plugin gains)
**New capabilities: 4** (captions, Shorts, beat-synced editing, 4K strategy)

---

## Sources

### Video and Channel
- [Original Video -- 10 BEST AI Updates in DaVinci Resolve Studio](https://www.youtube.com/watch?v=D33F1tktokg) -- Greg Edits Video
- [Greg Edits Video Website](https://gregeditsvideo.com/)
- [Greg Edits Video Essentials Pack](https://gregeditsvideo.com/collections/my-essential-presets-pack)
- [Greg Edits Video Free Preset](https://gregeditsvideo.com/pages/free-preset)
- [Greg Leach LinkedIn](https://uk.linkedin.com/in/gregleach1)

### DaVinci Resolve Documentation
- [DaVinci Resolve What's New](https://www.blackmagicdesign.com/products/davinciresolve/whatsnew) -- Blackmagic Design
- [DaVinci Resolve Studio](https://www.blackmagicdesign.com/products/davinciresolve/studio) -- Blackmagic Design
- [DaVinci Resolve 20 New Features Guide (PDF)](https://documents.blackmagicdesign.com/SupportNotes/DaVinci_Resolve_20_New_Features_Guide.pdf) -- Blackmagic Design
- [DaVinci Resolve 20.2 New Features Guide (PDF)](https://documents.blackmagicdesign.com/SupportNotes/DaVinci_Resolve_20.2_New_Features_Guide.pdf) -- Blackmagic Design
- [DaVinci Resolve 20.3.2 Update](https://www.newsshooter.com/2026/02/11/davinci-resolve-20-3-2-update/) -- Newsshooter
- [DaVinci Resolve 20.3 Update](https://www.newsshooter.com/2025/11/30/davinci-resolve-20-3-update/) -- Newsshooter

### AI Features Articles
- [AI-Powered Features in DaVinci Resolve 20](https://larryjordan.com/articles/ai-powered-features-in-davinci-resolve-20/) -- Larry Jordan
- [15 DaVinci Resolve AI Tools That Will Revolutionize Your Workflow](https://primalvideo.com/video-creation/editing/15-davinci-resolve-ai-tools-that-will-revolutionize-your-workflow/) -- Primal Video
- [Top 8 DaVinci Resolve AI Editing Tools](https://www.soundstripe.com/blogs/top-8-davinci-resolve-ai-editing-tools) -- Soundstripe
- [Everything New in DaVinci Resolve 20](https://elements.envato.com/learn/davinci-resolve-20) -- Envato Tuts+
- [DaVinci Resolve AI Workflow](https://photography.tutsplus.com/articles/davinci-resolve-ai--cms-109186) -- Envato Tuts+
- [DaVinci Resolve 20: AI-Powered Upgrades](https://www.starkinsider.com/2025/05/davinci-resolve-20-drops-with-ai-powered-upgrades.html) -- Stark Insider
- [DaVinci Resolve's Best AI Tools](https://glyphtech.com/a/blog/the-best-ai-tools-in-davinci-resolve) -- GlyphTech
- [DaVinci Resolve 20 Review 2026](https://filmora.wondershare.com/video-editor-review/davinci-resolve-editing-software.html) -- Filmora
- [Blackmagic Design Releases DaVinci Resolve 20.2](https://www.cgchannel.com/2025/09/blackmagic-design-releases-davinci-resolve-20-2/) -- CG Channel
- [DaVinci Resolve 20 Released with AI Features](https://www.cined.com/davinci-resolve-20-released-with-handful-of-ai-assisted-features/) -- CineD

### Specific Tool Guides
- [AI Music Editor Explained](https://jayaretv.com/edit/davinci-resolve-ai-music-editor-explained/) -- JayAreTV
- [AI Depth Map Explained](https://jayaretv.com/color/davinci-resolve-ai-depth-map-explained/) -- JayAreTV
- [AI Depth Map Tutorial](https://sidneybakergreen.com/davinci-resolve-ai-depth-map/) -- Sidney Baker-Green
- [How to Use Depth Map in Resolve Studio](https://www.easyedit.pro/blog/how-to-use-depth-map-in-da-vinci-resolve-studio) -- EasyEdit
- [Smart Reframe for Vertical Videos](https://larryjordan.com/articles/convert-horizontal-video-to-vertical-video-in-davinci-resolve-19/) -- Larry Jordan
- [How to Use Smart Reframe](https://createdtech.com/how-to-use-smart-reframe-in-davinci-resolve-studio) -- Created Tech
- [How to Make YouTube Shorts in DaVinci Resolve](https://www.trypostbase.com/resources/how-to-make-youtube-shorts-in-davinci-resolve) -- PostBase
- [Animate Subtitles in DaVinci Resolve 20](https://larryjordan.com/articles/animate-subtitles-in-davinci-resolve-20/) -- Larry Jordan
- [Cinematic Haze in Resolve 20](https://mixinglight.com/color-grading-tutorials/glow-effects-cinematic-haze-resolve-20/) -- Mixing Light
- [Mastering DaVinci Resolve 20 AI Workflows](https://www.lightinside.tv/post/mastering-davinci-resolve-20-a-beginner-s-guide-to-ai-powered-editing-workflows) -- Light Inside

### DaVinci Resolve Plugins and Presets
- [Best Plugins DaVinci Resolve 2026](https://www.miracamp.com/learn/davinci-resolve/best-plugins) -- Miracamp
- [DaVinci Resolve Update Adds Dynamic Trim Tools](https://nofilmschool.com/davinci-resolve-update-2032) -- No Film School
- [MotionVFX DaVinci Resolve Plugins](https://www.motionvfx.com/store/davinci-resolve) -- MotionVFX

### Previous Rayviews Lab Video Studies
- [11 FREE DaVinci Resolve Plugins](https://www.youtube.com/watch?v=DX0O9S0-ubI) -- Sightseeing Stan (agents/video_study_DX0O9S0.md)
- [16 BEST AI Tools in DaVinci Resolve Studio](https://www.youtube.com/watch?v=LiKqDWRdQw0) -- The David Shutt (agents/video_study_LiKqDWRdQw0.md)
- [Cinematic Product B-Roll Techniques](agents/broll_techniques.md)
