# Video Study: "15 DaVinci Resolve AI Tools That Will REVOLUTIONIZE Your Workflow"

**Source:** https://www.youtube.com/watch?v=zYItBOaD8Ik
**Channel:** Justin Brown - Primal Video (@PrimalVideo)
**Study Date:** 2026-02-13
**Relevance:** DaVinci Resolve Studio AI features for Rayviews Lab (automated Amazon Associates Top 5 product ranking channel)

---

## 1. Video Overview

**Title:** 15 DaVinci Resolve AI Tools That Will REVOLUTIONIZE Your Workflow
**Creator:** Justin Brown - Primal Video (1.8M+ subscribers, 25+ years video production experience)
**Platform:** YouTube
**Published:** November 25, 2025
**Duration:** ~19 minutes
**Focus:** Comprehensive walkthrough of 15 AI-powered features in DaVinci Resolve Studio, presented from a content creator's practical perspective

Justin Brown is a well-established video production educator whose channel focuses on actionable tools and techniques for content creators. His perspective differs from purely technical reviewers: he evaluates tools based on real-world content creation efficiency, making his recommendations particularly relevant for the Rayviews workflow.

This video covers the full suite of DaVinci Resolve Studio AI tools powered by the DaVinci Neural Engine. It overlaps significantly with the previous David Shutt study (`video_study_LiKqDWRdQw0.md`) but brings a content-creator-first perspective with practical workflow integration advice, including tools not covered in the earlier study (AI EQ Matcher, AI Level Matcher, AI Music Remixer as distinct tools).

---

## 2. Complete 15 AI Tools Inventory

Based on video metadata, the Primal Video companion article, and cross-referenced research, here are the 15 AI tools covered by Justin Brown.

### Editing & Timeline Tools

#### 1. AI Multicam SmartSwitch (Studio Only)
- **What it does:** Automatically switches multicam angles based on speaker detection. Audio-only analysis or video-based lip recognition.
- **How to access:** Create multicam clip > click SmartSwitch in viewer
- **Justin Brown's take:** Great for podcasts and interviews. Not relevant for every creator.
- **Rayviews relevance:** NONE. Single-camera voiceover workflow. No multicam footage.

#### 2. AI IntelliCut / Silence Removal (Studio Only -- Resolve 20+)
- **What it does:** Removes silent sections from audio clips automatically. Also splits dialogue per speaker and creates ADR cue lists. Accessible via right-click > Remove Silence, or Timeline > AI Tools > IntelliCut.
- **How to access:** Fairlight page > select clips > right-click > Remove Silence
- **Justin Brown's take:** Massive time saver for talking-head creators. Set volume threshold and let it remove dead air.
- **Rayviews relevance:** LOW. TTS voiceover chunks from ElevenLabs are already pre-trimmed with no silence. Only useful if recording scratch tracks or scratch narration for timing.

#### 3. AI Audio Transcription + Text-Based Editing (Studio Only)
- **What it does:** Transcribes timeline audio, displays it as text, and allows editing by selecting/deleting words in the transcript panel. Multi-voice detection assigns speaker labels.
- **How to access:** Edit page > Timeline > transcript panel (or Timeline > AI Tools > Create Subtitles from Audio)
- **Justin Brown's take:** Powerful for rough-cut assembly. Find specific phrases via search. Delete words to cut footage.
- **Rayviews relevance:** LOW-MEDIUM. TTS voiceover is already scripted. However, text-based search could help locate specific product mentions quickly during QC review. Not a workflow-changing tool for Rayviews.

#### 4. AI IntelliScript (Studio Only -- Resolve 20+)
- **What it does:** Automatically generates a timeline from a written script by matching transcribed audio to script text, placing shots in correct sequence.
- **How to access:** Edit page > Timeline menu > AI Tools > IntelliScript
- **Rayviews relevance:** LOW-MEDIUM. The pipeline already generates `script.txt` and pre-ordered TTS chunks. IntelliScript is designed for multi-take shoots, not pre-sequenced TTS. Worth testing but unlikely to improve the current ordered-chunk workflow.

#### 5. AI Animated Subtitles (Studio Only -- Resolve 20+)
- **What it does:** Auto-generates captions from audio, then applies animated styles. Five built-in styles: Lollipop, Rotate, Slide In, Statement, Word Highlight.
- **How to access:** Timeline > AI Tools > Create Subtitles from Audio > then drag animation effect from Effects panel onto subtitle track
- **Workflow steps:**
  1. Timeline > AI Tools > Create Subtitles from Audio
  2. Choose Language, Caption Preset, max characters per line (default 18)
  3. Click Create and wait for processing
  4. Open Effects panel, search for animation style (e.g., "Word Highlight")
  5. Drag animation onto subtitle track
  6. Customize via Inspector (font, size, color, position)
- **Justin Brown's take:** Word Highlight is the standout -- karaoke-style word tracking keeps eyes on screen. Native solution eliminates need for third-party caption tools.
- **Rayviews relevance:** HIGH. Directly addresses the 40+/50+ audience who may watch with reduced volume. Burnt-in animated subtitles increase watch time 12-25% per multiple studies. Replaces MagicSubtitle plugin (from `video_study_DX0O9S0.md`) with a native solution requiring no plugin dependencies.
- **Implementation note:** Product names and technical terms (model numbers, brand names) must be QC-reviewed after auto-generation. ElevenLabs TTS is clear enough that transcription accuracy should be high.

### Audio Tools

#### 6. AI Voice Isolation (Studio Only)
- **What it does:** Separates spoken voice from background noise using neural engine. Adjustable intensity slider from 0-100%.
- **How to access:** Fairlight page > Inspector > Audio > Voice Isolation slider. Also accessible from Edit page Inspector.
- **Rayviews relevance:** LOW for voiceover (ElevenLabs TTS is studio-clean). MEDIUM if incorporating stock B-roll with ambient audio that needs dialogue extracted.

#### 7. AI Voice Cloning / VoiceConvert (Studio Only -- Resolve 20+)
- **What it does:** Two-part system:
  - **Voice Training:** Creates a custom voice model from ~10 minutes of clean audio. Right-click clips in Media Pool > AI Tools > Voice Training. Choose "Faster" or "Better" quality. Processes locally (no cloud upload).
  - **Voice Convert:** Applies a trained voice model to existing recordings, retaining inflections, pitch variation, and emotion. Clip > AI Tools > Voice Convert > select model > Render.
- **Key parameters:** Type Matching Source (follow original pitch), Pitch Variance, Pitch Change (deepen/raise)
- **Justin Brown's take:** Game-changer for ADR and voice repair. Privacy-first -- all processing is local.
- **Rayviews relevance:** MEDIUM-HIGH (FUTURE). Currently using ElevenLabs Thomas Louis voice. However, VoiceConvert opens a significant opportunity:
  - **Backup voice pipeline:** Train a voice model in Resolve from ElevenLabs outputs. If ElevenLabs service changes pricing or voice availability, Resolve can apply the same voice characteristics to alternative TTS outputs.
  - **Voice consistency fix:** If ElevenLabs chunks vary slightly in tonal quality across a video, VoiceConvert can normalize all chunks to match a single reference chunk.
  - **Brand voice protection:** A locally-trained model means the Rayviews voice identity isn't dependent on a single cloud service.
- **Important limitation:** Training requires ~10 minutes of high-quality source audio. The existing library of ElevenLabs TTS chunks across multiple videos provides this easily.

#### 8. AI Music Remixer (Studio Only)
- **What it does:** Uses the Neural Engine to separate music into stems: vocals, drums, bass, guitar, and "other" (keyboard, horns, etc.). Each stem has independent mute and level controls.
- **How to access:** Select music clip > Inspector > Audio > Music Remixer (enable)
- **Justin Brown's take:** Turn any vocal track into an instrumental. Reduce overpowering instruments to create a vocal pocket. Automate stem changes over time.
- **Rayviews relevance:** HIGH. Directly solves a current workflow pain point:
  - **Problem:** The current EQ approach cuts 2-5 kHz by 3-6 dB on the music bed to create a vocal pocket (`resolve_editing_rules.md` Section 6). This is a crude frequency-based solution that affects ALL instruments in that range.
  - **Solution:** Music Remixer can surgically reduce only the vocal stem and guitar stem (the frequencies that compete with voiceover), while keeping drums, bass, and other instruments intact. This produces a cleaner, more professional sound.
  - **Additional use:** If using royalty-free music that has vocals, Music Remixer can strip them to create instrumental versions automatically.
- **Workflow update for A2 (Music):**
  1. Place music on A2
  2. Inspector > Music Remixer > Enable
  3. Mute "Voice" stem (removes any music vocals)
  4. Reduce "Guitar" stem -6 to -12 dB (creates vocal pocket for VO)
  5. Keep Drums, Bass, Other at full level
  6. Combined with AI Audio Ducker for automatic volume ducking

#### 9. AI Audio Assistant / Producer (Studio Only -- Resolve 20+)
- **What it does:** One-click professional audio mix. Analyzes timeline, classifies tracks (dialogue, music, effects), organizes them, and automixes for chosen delivery standard (YouTube, Netflix, Broadcast).
- **How to access:** Timeline > AI Tools > Audio Assistant > select delivery standard > Auto Mix
- **What it does automatically:** Applies Voice Isolation, Auto Ducker, smart EQ, level balancing, and platform-specific mastering.
- **YouTube delivery standard:** Targets -14 LUFS integrated loudness.
- **Justin Brown's take:** "This is probably the biggest game-changer." Replaces manual EQ, compression, ducking, and leveling in one click. Always duplicate timeline first as backup.
- **Rayviews relevance:** VERY HIGH. This is the single highest-impact tool for the Rayviews workflow.
  - **Current pain:** 6-step manual audio chain: EQ > De-Esser > Compressor > Limiter > Music Duck > SFX Level (`resolve_editing_rules.md` Section 6)
  - **Replacement:** One-click Auto Mix targeting YouTube standard
  - **Speed gain:** 30-45 minutes saved per video
  - **Caution:** YouTube preset targets -14 LUFS integrated. Current spec targets -16 LUFS on VO track, -14 LUFS on master bus. Verify output levels after auto-mix. Minor adjustment (1-2 dB bus trim) may be needed.
  - **Best practice:** Duplicate timeline before running Audio Assistant. Review color-coded track organization and verify Rayviews-specific levels.

#### 10. AI Audio Ducker (Studio Only)
- **What it does:** Automatically lowers music when dialogue is present, without manual keyframes or sidechain compression.
- **How to access:** Fairlight page > Track FX on A2 > Ducker > set A1 (VO) as sidechain source
- **Rayviews relevance:** HIGH. Eliminates manual music ducking keyframes. Current spec: "duck 0.3s before VO starts, return 0.5s after VO ends" with manual curves. AI Ducker automates this entirely.
  - **Speed gain:** 15-20 minutes saved per video
  - **Note:** AI Audio Assistant may already apply ducking. Use AI Audio Ducker as a refinement tool if the auto-mix ducking needs adjustment.

#### 11. AI Dialogue Matcher / EQ Matcher / Level Matcher (Studio Only -- Resolve 20+)
- **What it does:** Three related tools that match audio characteristics between clips:
  - **Dialogue Matcher:** Matches tone, level, and room environment. Takes sonic profile from reference clip, applies to target.
  - **AI EQ Matcher:** Dynamically matches tonal spectrum between clips. Automated EQ adjustments across clip duration.
  - **AI Level Matcher:** Seamlessly intercuts clip sections by matching loudness levels. Capture Level Profile from reference, apply to targets.
- **How to access:** Right-click clip > Clip Operations > Level Matching > Capture Level Profile / Apply Level Profile
- **Justin Brown's take:** Essential for multi-location shoots. But also valuable for any project with audio from different sources.
- **Rayviews relevance:** MEDIUM-HIGH. ElevenLabs TTS chunks are generated separately and can vary slightly in tonal quality, volume, and "room feel" between chunks. These three tools solve this:
  1. Generate all VO chunks and place on A1
  2. Identify the best-sounding chunk as reference
  3. Capture Level Profile from reference chunk
  4. Apply to all other chunks for consistent volume
  5. Apply Dialogue Matcher for consistent tonal quality
  - **This replaces:** Manual per-chunk level normalization and the compressor step in the audio chain.

### Color & Visual Effects Tools

#### 12. Magic Mask 2 (Studio Only)
- **What it does:** AI-powered object/person isolation with click-based guidance. Unified mode handles both people and objects. Tracks through occlusions and complex movements.
- **How to access:** Color page > Qualifier palette > Magic Mask > click on subject
- **2026 improvements:** Click-based guidance (simpler than drawing strokes), improved occlusion handling, unified person/object mode.
- **Justin Brown's take:** Perfect for background removal, selective color grading, and isolating subjects.
- **Rayviews relevance:** HIGH. Multiple applications:
  - **Product isolation:** Click on product in Dzine-generated image to isolate from background. Grade product and background separately.
  - **Background replacement:** If Dzine background doesn't match the video's look, isolate product with Magic Mask, grade or replace background.
  - **B-roll enhancement:** Isolate product in stock B-roll footage for targeted color correction.
  - **Verdict emphasis:** During "best pick" verdict, isolate product and apply subtle glow or brightness boost.

#### 13. AI Auto Color / Color Correction (Studio + Free)
- **What it does:** One-click automatic color balance, white balance, and contrast correction using the DaVinci Neural Engine.
- **How to access:** Color page > Primaries palette > "A" button (Auto Color). Also: Auto White Balance, Auto White Level, Auto Black Level.
- **Available in free version:** Yes (unlike most AI tools).
- **Justin Brown's take:** Great starting point. Won't replace manual grading for creative looks, but instantly fixes color problems.
- **Rayviews relevance:** MEDIUM. Useful as a first pass on B-roll footage to quickly balance shots before the Shot Match step (`resolve_editing_rules.md` Section 7, Node 1). Saves time on Node 1 (Primary Balance) which currently requires manual waveform analysis.
  - **Product images:** Already well-exposed from Dzine. Auto Color may not be needed.
  - **B-roll:** Very useful. Stock footage varies wildly in color. Auto Color as Node 1, then Shot Match as Node 2.

#### 14. AI Relight (Studio Only)
- **What it does:** Creates virtual light sources (Directional, Spotlight, Point Source) that can be positioned, colored, and animated. Uses AI depth map to apply lighting realistically.
- **How to access:** Color page > OpenFX library > Resolve FX > Relight
- **Light types:**
  - **Directional Light:** Simulates distant sources (sunlight). Consistent across full frame.
  - **Spotlight:** Cone-shaped, ideal for highlighting subjects.
  - **Point Source:** Omnidirectional bulb, adds depth to specific areas.
- **Justin Brown's take:** Mind-blowing for reshaping any shot's lighting after the fact. Adjust direction, color, and intensity.
- **Rayviews relevance:** MEDIUM. Could enhance Dzine-generated product images:
  - Add warm key light from consistent direction across all products (creates lighting anchor without needing Dzine prompt changes)
  - Spotlight on product during verdict moment for emphasis
  - **Caution:** Must be subtle. The 40+/50+ audience distrusts flashy effects. Use for correction and consistency, not dramatic lighting.

#### 15. AI Smart Reframe (Studio Only)
- **What it does:** Automatically reframes 16:9 content to 9:16 (or other aspect ratios) by tracking and centering the main subject. Modes: Auto, Pan Only, Tilt Only.
- **How to access:** Inspector > Video > Smart Reframe > Enable > click "Reframe"
- **Justin Brown's take:** Ideal for creating Shorts, Reels, and TikTok from existing horizontal content.
- **Rayviews relevance:** HIGH. Enables a "publish once, distribute everywhere" strategy:
  - Each 10-minute Top 5 video generates 5-10 potential Shorts
  - Smart Reframe auto-centers products when converting to vertical
  - YouTube Shorts algorithm provides separate discovery surface
  - Each Short can carry a single affiliate link (higher conversion than choice overload)
- **Workflow:**
  1. Complete 16:9 edit as normal
  2. Duplicate timeline
  3. Change timeline settings to 1080x1920 (9:16)
  4. Select all clips > Inspector > Smart Reframe > Enable
  5. Review each clip (product should be centered)
  6. Reposition text overlays for vertical layout
  7. Export individual 15-60 second segments as separate Shorts

### Additional Tools Covered (Bonus / Quick Mentions)

#### AI SuperScale (Studio Only)
- **What it does:** Upscales media 2x, 3x, or 4x using Neural Engine. Generates new pixel data.
- **How to access:** Right-click clip in Media Pool > Clip Attributes > Super Scale
- **Rayviews relevance:** MEDIUM-HIGH. 4K YouTube upload strategy:
  - YouTube allocates higher bitrate VP9/AV1 encoding to 4K uploads even when viewed at 1080p
  - SuperScale 2x upscales Dzine images from 1080p to 2160p
  - The 40+/50+ audience often watches on 65"+ smart TVs where quality difference is visible
  - **Note:** Uploading at even 1440p triggers higher-quality encoding. May not need full 4K.
  - **Performance cost:** GPU-intensive. Longer render times.

#### AI Speed Warp (Studio Only)
- **What it does:** AI-powered optical flow retiming for smooth slow-motion or speed changes. Generates intermediate frames.
- **How to access:** Inspector > Speed Change > Retime Process > Speed Warp
- **Rayviews relevance:** MEDIUM. Can create smooth slow-motion B-roll from standard 30fps stock footage (e.g., slow-mo of hands using a product). Adds professional polish.

---

## 3. What's New vs. Previous Study (David Shutt -- `video_study_LiKqDWRdQw0.md`)

### Tools Covered in Both Videos

| Tool | David Shutt Coverage | Justin Brown Coverage | New Insights |
|------|---------------------|----------------------|-------------|
| AI Audio Assistant | Listed as #14 | Deep practical demo | YouTube delivery standard detail, duplicate-timeline-first advice |
| AI Audio Ducker | Listed as #16 | Covered as part of audio chain | Same coverage |
| AI Animated Subtitles | Listed as Bonus | Full walkthrough | Step-by-step workflow with Word Highlight as recommended style |
| AI Smart Reframe | Listed as #6 | Full Shorts workflow | Auto/Pan/Tilt mode options, practical Shorts production advice |
| Magic Mask 2 | Listed as #8 | Covered with 2026 improvements | Click-based guidance vs. stroke-based, unified person/object mode |
| AI Voice Isolation | Listed as #13 | Covered | Same |
| AI SuperScale | Listed as Bonus | Mentioned | Same, 1440p trigger note |
| AI Speed Warp | Listed as Bonus | Covered | Same |
| AI IntelliScript | Listed as #1 | Covered | Same |
| AI IntelliCut | Listed as #3 | Covered | Same |

### Tools NEW in This Study (Not in David Shutt Study)

| Tool | Why It Matters |
|------|---------------|
| **AI Music Remixer** | Stem separation for surgical vocal-pocket creation on music bed. Major improvement over crude EQ-based approach. |
| **AI Voice Cloning / VoiceConvert** | Voice model training from ElevenLabs output. Brand voice backup and cross-chunk consistency. |
| **AI EQ Matcher** | Dynamic tonal spectrum matching between VO chunks. Finer than Level Matcher. |
| **AI Level Matcher** | Loudness matching between clips via captured profile. Better than manual normalization. |
| **AI Dialogue Matcher** | Room environment and tone matching. Fixes TTS chunk tonal drift. |
| **AI Relight** | Virtual light sources for product emphasis and lighting consistency. |
| **AI Auto Color** | One-click color correction baseline. Works in free version too. |

### Tools in David Shutt Study NOT in This Video

| Tool | Status |
|------|--------|
| AI Depth Map 2 | Not explicitly listed in Justin Brown's 15. Still available and highly relevant. |
| AI Object Removal | Not covered by Justin Brown. Still useful for watermark removal. |
| AI Face Refinement | Not covered. Not relevant (faceless channel). |
| AI Cinematic Haze | Not covered. Not recommended for 40+/50+ audience. |
| AI Set Extender | Not covered. Still useful for Dzine 1:1 to 16:9 conversion. |
| AI Beat Detection | Not explicitly covered as separate tool. |
| AI Dialogue Separator | Not covered. Not relevant for TTS. |
| AI Scene Cut Detection | Not covered. Not relevant for product images. |

---

## 4. Priority Ranking for Rayviews Pipeline

### Tier 1: Implement Immediately (Highest Impact)

| # | Tool | Current Pain Point | Solution | Time Saved |
|---|------|-------------------|----------|------------|
| 1 | AI Audio Assistant | 6-step manual audio chain | One-click YouTube auto-mix | 30-45 min/video |
| 2 | AI Music Remixer | Crude EQ-based vocal pocket | Surgical stem-level control | 10-15 min/video + quality boost |
| 3 | AI Audio Ducker | Manual music ducking keyframes | Automatic sidechain ducking | 15-20 min/video |
| 4 | AI Animated Subtitles | No burnt-in captions | Native Word Highlight captions | New capability (+12-25% watch time) |
| 5 | AI Smart Reframe | No Shorts pipeline | Auto vertical reframe | New revenue channel |

**Estimated total: 55-80 minutes saved per video + 2 new capabilities**

### Tier 2: Implement This Month (Good ROI)

| # | Tool | Use Case | Notes |
|---|------|----------|-------|
| 6 | AI Dialogue Matcher + Level Matcher | Normalize TTS chunk tonal/volume variations | Test on existing videos first |
| 7 | Magic Mask 2 | Product isolation for targeted color grading | Replaces manual masking |
| 8 | AI Depth Map 2 (from previous study) | Single-layer background blur | Replaces V4 blur-BG workflow (20-30 min saved) |
| 9 | AI Auto Color | Quick first-pass on B-roll footage | Node 1 replacement for stock clips |
| 10 | AI SuperScale | 4K/1440p YouTube uploads for quality boost | Longer render, better viewer experience |

### Tier 3: Evaluate Later (Strategic Value)

| # | Tool | When to Implement |
|---|------|------------------|
| 11 | AI Voice Cloning (VoiceConvert) | After accumulating 10+ minutes of ElevenLabs VO. Brand voice backup. |
| 12 | AI Relight | When establishing lighting consistency across products becomes a bottleneck |
| 13 | AI Speed Warp | When adding B-roll with slow-motion needs |
| 14 | AI EQ Matcher | If Dialogue Matcher alone doesn't fix TTS chunk tonal drift |

### Tier 4: Not Applicable

| Tool | Reason |
|------|--------|
| AI Multicam SmartSwitch | No multicam footage |
| AI IntelliCut | TTS chunks already pre-trimmed |
| AI IntelliScript | TTS chunks already sequenced |
| Text-Based Editing | TTS already scripted (marginal QC use) |

---

## 5. Updated Editing Workflow (Combining Both Video Studies)

### Current Daily Editing Recipe (resolve_editing_rules.md Section 13):
```
1.  Open DaVinci Resolve Studio
2.  Create project, timeline 1920x1080 @ 29.97fps
3.  Import media
4.  Import markers from EDL
5.  Place voiceover chunks on A1 in order
6.  Place music on A2, set -26 LUFS, duck under voice
7.  Follow markers to place visuals on V1 (product images) and V2 (B-roll)
8.  Apply Dynamic Zoom (3-7%) to all static images on V1
9.  Create blur-BG duplicates on V4 for hero shots
10. Add overlays on V3 from Power Bin templates
11. Place SFX on A3 at marker points
12. 0.5s dissolve between segments
13. Quick color match on B-roll
14. QC checklist pass
15. Export
16. Upload
```

### Proposed AI-Enhanced Workflow (integrating all three studies):
```
1.  Open DaVinci Resolve Studio
2.  Create project, timeline 1920x1080 @ 29.97fps
3.  Import media
4.  Import markers from EDL
5.  Place voiceover chunks on A1 in order
6.  Place music on A2 (enable Music Remixer: mute vocals, reduce guitar -6dB)
7.  Place SFX on A3 at marker points
8.  [AI] Duplicate timeline as backup
9.  [AI] Timeline > AI Tools > Audio Assistant (YouTube delivery standard)
    - Replaces: manual EQ, De-Esser, Compressor, Limiter, ducking, SFX leveling
    - Verify: VO -16 LUFS, Music -26 LUFS, SFX -18 LUFS
10. [AI] If music ducking needs refinement: apply AI Audio Ducker on A2
11. [AI] If VO chunks have tonal inconsistency: apply Dialogue Matcher on A1
12. Follow markers to place visuals on V1 and V2
13. Apply MagicZoom presets to V1 images (or manual Dynamic Zoom 3-7%)
14. [AI] Apply AI Depth Map to hero shots on V1 for shallow-DOF
    - Replaces: V4 blur-BG duplicate workflow
15. Add overlays on V3 from Power Bin templates + MagicAnimate transitions
16. 0.5s dissolve between segments
17. [AI] Color page: Auto Color on B-roll (Node 1), Shot Match (Node 2)
18. [AI] Magic Mask for product isolation if needed (targeted grading)
19. [AI] Timeline > AI Tools > Create Subtitles from Audio
    - Apply Word Highlight animation style
    - QC: verify product names, model numbers, brand names
    - Customize font to Montserrat/Inter
20. QC checklist pass (add: verify subtitle accuracy, verify AI mix levels)
21. Export (consider 1440p+ for YouTube quality encoding boost)
22. Upload to YouTube
23. [AI] Duplicate timeline > 9:16 > Smart Reframe > export Shorts
```

### Time Savings Summary (All Three Studies Combined)

| Workflow Step | Old Method | New Method | Savings |
|--------------|-----------|------------|---------|
| Audio chain (EQ/Comp/Limit) | Manual 6-step chain | AI Audio Assistant | 30-45 min |
| Music vocal pocket | EQ cut 2-5 kHz | Music Remixer stem control | 10-15 min |
| Music ducking | Manual keyframes | AI Audio Ducker | 15-20 min |
| Background blur | V4 duplicate workflow | AI Depth Map 2 | 20-30 min |
| Zoom effects | Manual Dynamic Zoom per clip | MagicZoom bulk apply | 15-20 min |
| Segment transitions | Manual dissolve + snap zoom | MagicAnimate presets | 5-10 min |
| B-roll color correction | Manual waveform analysis | Auto Color + Shot Match | 10-15 min |
| Captions | None (YouTube auto) | AI Animated Subtitles | New feature |
| Vertical content | None | AI Smart Reframe | New channel |

**Total estimated time saved per video: 105-155 minutes (1.75-2.6 hours)**

---

## 6. Deep Dive: AI Music Remixer for Rayviews

This is the most significant NEW tool identified in this study that was not covered in the David Shutt video.

### Current Problem

The `resolve_editing_rules.md` Section 6 (Music Bed) specifies:
```
EQ: cut 2-5 kHz by 3-6 dB (creates vocal pocket)
```

This is a frequency-domain approach: it cuts ALL audio content in the 2-5 kHz range, including drums, bass harmonics, and instruments that don't actually compete with the voiceover. The result is a "hollowed out" music bed that sounds noticeably processed.

### Music Remixer Solution

The Music Remixer decomposes the track into five stems:
1. **Voice** (any vocals in the music) -- MUTE entirely
2. **Drums** -- keep at full level (percussive, doesn't compete with VO frequency range)
3. **Bass** -- keep at full level (low frequencies, doesn't compete)
4. **Guitar** -- reduce -6 to -12 dB (mid-range frequencies compete with voice)
5. **Other** (keyboard, horns, strings) -- reduce -3 to -6 dB if competing

This produces a cleaner, more musical vocal pocket because:
- Drums and bass retain their full impact (energy, rhythm)
- Only the instruments that actually compete with voice frequencies are reduced
- The reduction is stem-based, not frequency-based, so it sounds natural

### Workflow Integration

```
Current resolve_editing_rules.md Section 6 (Music Bed):
  Level: -26 LUFS under voice, swell to -18 LUFS during transitions
  EQ: cut 2-5 kHz by 3-6 dB (creates vocal pocket)
  Duck 0.3s before VO starts, return 0.5s after VO ends

Updated workflow:
  1. Place music on A2
  2. Inspector > Music Remixer > Enable
  3. Mute "Voice" stem
  4. Reduce "Guitar" stem -6 to -12 dB
  5. Keep Drums, Bass, Other at default
  6. Level: -26 LUFS under voice, swell to -18 LUFS during transitions
  7. Apply AI Audio Ducker (sidechain from A1) for automatic ducking
  8. REMOVE the old EQ step (no longer needed)
```

---

## 7. Deep Dive: AI Voice Cloning as Brand Insurance

### The Opportunity

Rayviews depends on ElevenLabs Thomas Louis voice (ID: IHw7aBJxrIo1SxkG9px5) for brand identity. This creates a single point of failure:
- ElevenLabs could discontinue the voice
- Pricing could increase significantly
- The voice model could be updated with different characteristics
- Service outages could block video production

### DaVinci Resolve Voice Training as Backup

**Source material:** Rayviews has already generated many videos' worth of ElevenLabs VO chunks. The Voice Training feature needs ~10 minutes of clean audio. A single video produces 8-12 minutes of VO.

**Training process:**
1. Collect the best-quality VO chunks from 2-3 videos (selecting chunks with varied pacing and tone)
2. Import into Resolve Media Pool
3. Right-click > AI Tools > Voice Training
4. Name: "Rayviews_Thomas_Louis_Backup"
5. Select "Better" quality (longer training, superior results)
6. Wait for background processing to complete

**Result:** A locally-stored voice model that can convert any audio into the Rayviews voice character. This works as:
- Emergency backup if ElevenLabs is unavailable
- Quality normalizer for inconsistent TTS chunks
- Test bed for script revisions (convert scratch narration into final-quality voice)

### Privacy Advantage

All Resolve AI voice processing is local. No audio data leaves the machine. The voice model stays on the Rayviews production machine and cannot be accessed by third parties.

---

## 8. Deep Dive: AI Dialogue/Level/EQ Matchers for TTS Consistency

### The Problem

ElevenLabs TTS chunks are generated independently (300-450 words each, per MEMORY.md). Each chunk goes through the ElevenLabs API separately, and subtle variations can occur:
- Slight volume differences between chunks
- Minor tonal quality shifts (warmer/cooler)
- Different "room feel" characteristics
- Pacing variations despite same settings

These are usually subtle but noticeable on careful listening, especially for the 40+/50+ audience who often listens on quality speakers or headphones.

### Three-Tool Solution

**Step 1: AI Level Matcher (volume consistency)**
1. Identify the best-sounding VO chunk (clearest, best volume)
2. Right-click > Clip Operations > Level Matching > Capture Level Profile
3. Select all other VO chunks
4. Right-click > Clip Operations > Level Matching > Apply Level Profile
5. All chunks now match the reference volume

**Step 2: AI EQ Matcher (tonal consistency)**
1. Same reference chunk as above
2. Apply EQ matching to normalize tonal spectrum
3. Dynamic EQ adjustments follow the clip content

**Step 3: AI Dialogue Matcher (if still needed)**
1. Matches room environment, reverb characteristics, and overall sonic profile
2. Apply after Level and EQ matching for final polish
3. Makes all chunks sound like they were recorded in the same session

### Expected Result

All TTS voiceover chunks sound like a single continuous recording, eliminating the "chunk boundary" effect where listeners can hear where one TTS generation ended and another began.

---

## 9. Cross-Reference with Existing Knowledge

### vs. broll_techniques.md

| Current Spec | Enhancement from This Study |
|-------------|---------------------------|
| Shallow DOF via blur-BG duplicate on V4 | AI Depth Map 2: single-layer depth blur, no duplication |
| Product color correction: "keep clean and true to listing" | Magic Mask 2: isolate product, grade background separately |
| "Consistent lighting style across all products" | AI Relight: add virtual key light from consistent direction |

### vs. video_study_DX0O9S0.md (Free Plugins)

| Plugin Solution | Native AI Alternative | Recommendation |
|----------------|----------------------|----------------|
| MagicSubtitle (plugin) | AI Animated Subtitles (native) | **Use native** -- no plugin dependency, built-in Word Highlight |
| Manual music EQ pocket | AI Music Remixer (native) | **Use native** -- stem-based is superior to frequency-based |
| Manual music ducking | AI Audio Ducker (native) | **Use native** -- automatic, no keyframes |
| MagicZoom (plugin) | Dynamic Zoom (manual) | **Keep MagicZoom** -- still faster for bulk application |
| MagicAnimate V3 (plugin) | No native equivalent | **Keep plugin** -- for transitions and pattern interrupts |
| Free Starter Pack 2.0 (plugin) | No native equivalent | **Keep plugin** -- for lower thirds templates |

### vs. video_study_LiKqDWRdQw0.md (David Shutt 16 AI Tools)

The David Shutt study and this Justin Brown study overlap on ~10 tools but differ in coverage depth and practical orientation:

| Aspect | David Shutt Study | Justin Brown Study |
|--------|------------------|-------------------|
| Perspective | Technical/comprehensive | Content-creator/practical |
| Tools count | 16 (more tools listed) | 15 (more workflow depth) |
| Unique tools | Depth Map, Object Removal, Face Refinement, Cinematic Haze, Set Extender, Beat Detection | Music Remixer, Voice Cloning, EQ/Level/Dialogue Matchers, Relight, Auto Color |
| Strongest on | Editing and color tools | Audio tools |
| Workflow advice | Updated editing recipe | Duplicate-timeline-first, delivery standard details |

**Combined coverage provides the most complete picture.** Key additions from this study:
1. Music Remixer for stem-based vocal pocket (major quality improvement)
2. Voice Cloning as brand insurance
3. Audio matchers (Level/EQ/Dialogue) for TTS chunk consistency
4. AI Relight for product lighting consistency
5. Auto Color for quick B-roll correction baseline

---

## 10. Action Items Summary

### Immediate (This Week)

- [ ] Test AI Audio Assistant on existing video project -- compare output to manual 6-step audio chain
- [ ] Test AI Music Remixer on music bed -- compare stem-based vocal pocket to EQ-based approach
- [ ] Test AI Audio Ducker on A2 with A1 as sidechain -- compare to manual ducking keyframes
- [ ] Test AI Animated Subtitles with Word Highlight on one video segment -- QC product name accuracy

### Short-Term (This Month)

- [ ] Update `resolve_editing_rules.md` Section 6 (Audio Chain) with AI Audio Assistant + Music Remixer workflow
- [ ] Update `resolve_editing_rules.md` Section 6 (Music Bed) to replace EQ approach with Music Remixer stem approach
- [ ] Add "Create Subtitles" step to QC checklist and daily editing recipe (Step 19)
- [ ] Test AI Level Matcher + Dialogue Matcher on a set of TTS VO chunks for consistency improvement
- [ ] Create first YouTube Short from existing video using Smart Reframe
- [ ] Test AI Auto Color as Node 1 replacement for B-roll color correction

### Medium-Term (Next Month)

- [ ] Begin AI Voice Training: collect 10+ minutes of best ElevenLabs VO chunks across multiple videos
- [ ] Train "Rayviews_Thomas_Louis_Backup" voice model in Resolve (choose "Better" quality)
- [ ] Test AI Relight for consistent product lighting across all 5 products in a single video
- [ ] Build Shorts production pipeline: duplicate timeline > Smart Reframe > batch export
- [ ] Implement 1440p+ export strategy for YouTube quality encoding boost
- [ ] Update `resolve_automation_guide.md` with AI tool integration points

### Long-Term (Pipeline Enhancement)

- [ ] Integrate AI Audio Assistant into pipeline as post-TTS automation step
- [ ] Build Resolve Python API automation for Smart Reframe Shorts batch export
- [ ] A/B test: videos with burnt-in Word Highlight captions vs. without (measure retention)
- [ ] Evaluate VoiceConvert as TTS consistency normalizer (apply trained model to variable chunks)
- [ ] Add subtitle generation to manifest/export stage of `pipeline.py`

---

## 11. Comprehensive Tool Availability Summary

All tools require **DaVinci Resolve Studio** ($295 one-time) unless noted:

| Tool | Resolve 19 | Resolve 20 | Free Version |
|------|-----------|-----------|-------------|
| AI Multicam SmartSwitch | Studio | Studio | No |
| AI IntelliCut | No | Studio | No |
| AI Audio Transcription | Studio | Studio | No |
| AI IntelliScript | No | Studio | No |
| AI Animated Subtitles | No | Studio | No |
| AI Voice Isolation | Studio | Studio | No |
| AI VoiceConvert / Voice Training | No | Studio | No |
| AI Music Remixer | Studio | Studio | No |
| AI Audio Assistant | No | Studio | No |
| AI Audio Ducker | Studio | Studio | No |
| AI Dialogue/EQ/Level Matcher | No | Studio | No |
| Magic Mask 2 | Studio | Studio | No |
| AI Auto Color | Studio | Studio | **Yes** |
| AI Relight | Studio | Studio | No |
| AI Smart Reframe | Studio | Studio | No |
| AI SuperScale | Studio | Studio | No |
| AI Speed Warp | Studio | Studio | No |
| AI Depth Map 2 | Studio | Studio | No |

The current Rayviews workflow already uses DaVinci Resolve Studio. No additional purchase required for any of these tools.

---

## Sources

### Video
- [Original Video -- 15 DaVinci Resolve AI Tools That Will REVOLUTIONIZE Your Workflow](https://www.youtube.com/watch?v=zYItBOaD8Ik) -- Justin Brown, Primal Video
- [Primal Video Companion Article](https://primalvideo.com/video-creation/editing/15-davinci-resolve-ai-tools-that-will-revolutionize-your-workflow/) -- Primal Video
- [Class Central Course Listing](https://www.classcentral.com/course/youtube-15-davinci-resolve-ai-tools-that-will-revolutionize-your-workflow-505043)

### Justin Brown / Primal Video
- [Primal Video Website](https://primalvideo.com/) -- Video Tech, Tools & AI
- [About Justin Brown](https://primalvideo.com/about/) -- 25+ years video production
- [8 Mind-Blowing DaVinci Resolve AI Tools (earlier video)](https://primalvideo.com/video-creation/editing/davinci-resolve-ai-tools/)

### DaVinci Resolve Official
- [DaVinci Resolve What's New](https://www.blackmagicdesign.com/products/davinciresolve/whatsnew) -- Blackmagic Design
- [DaVinci Resolve Studio](https://www.blackmagicdesign.com/products/davinciresolve/studio) -- Blackmagic Design
- [DaVinci Resolve 20 New Features Guide (PDF)](https://documents.blackmagicdesign.com/SupportNotes/DaVinci_Resolve_20_New_Features_Guide.pdf) -- Blackmagic Design

### Audio Tools
- [How to Use AI Audio Assistant in DaVinci Resolve 20](https://www.downloadsource.net/how-to-use-ai-audio-assistant-in-davinci-resolve-20/n/24665/) -- Download Source
- [AI Audio Mixing in Resolve 20](https://www.beyond-the-pixels.com/post/ai-audio-mixing-just-got-a-whole-lot-smarter-in-davinci-resolve-20-studio) -- Beyond the Pixels
- [DaVinci Resolve 20 Audio -- AI EQ, Levels, Dialogue Matchers](http://jason-yadlovski.squarespace.com/blog/2025/6/23/davinci-resolve-20-audio-ai-eq-ai-levels-amp-ai-dialogue-matchers-game-changer-or-gimmick) -- Jason Yadlovski
- [DaVinci Resolve AI Level Matcher Explained](https://jayaretv.com/fairlight/davinci-resolve-ai-level-matcher-explained/) -- JayAreTV
- [Blackmagic DaVinci Resolve 20 AI Audio Features](https://www.mixonline.com/technology/news-products/blackmagic-davinci-resolve-20-adds-ai-audio-features) -- Mix Online

### Voice Cloning
- [DaVinci Resolve AI Voice Convert Explained](https://jayaretv.com/edit/davinci-resolve-ai-voice-convert-explained/) -- JayAreTV
- [How to Create Your Own AI Voice in DaVinci Resolve](https://www.downloadsource.net/how-to-create-your-own-ai-voice-in-davinci-resolve-voice-convert/n/24811/) -- Download Source

### Music Remixer
- [DaVinci Resolve's AI Music Remixer Feature](https://www.alliandwill.com/blog/davinci-resolves-new-ai-music-remixer-feature-is-really-good) -- Alli and Will
- [Remix Music & Sync to the Beat in Fairlight](https://vfxstudy.com/tutorials/remix-music-sync-to-the-beat-in-fairlight/) -- VFXstudy
- [How to Remix Music with DaVinci Resolve AI](https://epictutorials.com/blogs/articles/how-to-remix-music-with-davinci-resolve-studio-ai-on-ipad) -- Epic Tutorials

### Color & Visual Effects
- [Magic Mask in DaVinci Resolve: AI Revolution in Post-Production](https://foro3d.com/en/2026/january/davinci-resolves-magic-mask-ai-revolution-in-post-production.html) -- Foro3D
- [DaVinci Resolve AI Magic Mask v2 Explained](https://jayaretv.com/color/davinci-resolve-ai-magic-mask-2-explained/) -- JayAreTV
- [AI Relight in DaVinci Resolve](https://filmora.wondershare.com/video-editor-review/relight-davinci-resolve.html) -- Filmora
- [Four Automatic Color Correction Features in DaVinci Resolve 20](https://larryjordan.com/articles/the-automatic-color-correction-features-in-davinci-resolve-20-v/) -- Larry Jordan
- [AI-Powered Features in DaVinci Resolve 20](https://larryjordan.com/articles/ai-powered-features-in-davinci-resolve-20/) -- Larry Jordan

### Smart Reframe & Vertical Video
- [DaVinci Resolve Smart Reframe](https://www.capcut.com/resource/davinci-resolve-smart-reframe) -- CapCut
- [Convert Horizontal to Vertical in DaVinci Resolve](https://larryjordan.com/articles/convert-horizontal-video-to-vertical-video-in-davinci-resolve-19/) -- Larry Jordan

### Subtitles
- [Mastering Animated Subtitles in DaVinci Resolve](https://apexphotostudios.com/blogs/news/mastering-animated-subtitles-in-davinci-resolve-a-step-by-step-guide) -- Apex Photo Studios
- [Animate Subtitles in DaVinci Resolve 20](https://larryjordan.com/articles/animate-subtitles-in-davinci-resolve-20/) -- Larry Jordan
- [How to Create Animated Subtitles in DaVinci Resolve](https://www.downloadsource.net/how-to-create-animated-subtitles-in-davinci-resolve/n/24676/) -- Download Source

### Super Scale & Upscaling
- [Upscale HD to 4K: Super Scale in DaVinci Resolve](https://www.motionvfx.com/know-how/how-to-super-scale-in-davinci-resolve/) -- MotionVFX
- [4K/8K DaVinci Resolve Upscale Guide](https://www.videoproc.com/video-editor/davinci-resolve-upscale.htm) -- VideoProc
- [Super Scale Best Practice for YouTube (Blackmagic Forum)](https://forum.blackmagicdesign.com/viewtopic.php?f=21&t=186348) -- Blackmagic Forum

### General DaVinci Resolve 20 Coverage
- [DaVinci Resolve 20: Unleashing the Power of AI](https://glyphtech.com/a/blog/davinci-resolve-20-unleashing-the-power-of-ai) -- GlyphTech
- [DaVinci Resolve 20: AI-Powered Upgrades](https://www.starkinsider.com/2025/05/davinci-resolve-20-drops-with-ai-powered-upgrades.html) -- Stark Insider
- [DaVinci Resolve 20 Upgrades with AI-Driven Tools](https://www.digitalmediaworld.tv/post/davinci-resolve-20-upgrades-with-ai-driven-tools-audio-and-cloud-innovation) -- Digital Media World
- [Top 8 DaVinci Resolve AI Editing Tools](https://www.soundstripe.com/blogs/top-8-davinci-resolve-ai-editing-tools) -- Soundstripe
- [How to Use DaVinci Resolve's AI Tools](https://skimai.com/how-to-use-davinci-resolves-ai-tools/) -- Skim AI
- [DaVinci Resolve AI Workflow](https://photography.tutsplus.com/articles/davinci-resolve-ai--cms-109186) -- Envato Tuts+

### Previous Rayviews Video Studies
- [video_study_DX0O9S0.md](../agents/video_study_DX0O9S0.md) -- 11 FREE DaVinci Resolve Plugins (Sightseeing Stan)
- [video_study_LiKqDWRdQw0.md](../agents/video_study_LiKqDWRdQw0.md) -- 16 BEST AI Tools in DaVinci Resolve Studio (The David Shutt)
- [broll_techniques.md](../agents/broll_techniques.md) -- Cinematic Product B-Roll Techniques
- [resolve_editing_rules.md](../agents/resolve_editing_rules.md) -- DaVinci Resolve Studio Workflow
- [resolve_automation_guide.md](../agents/resolve_automation_guide.md) -- DaVinci Resolve Automation Guide
