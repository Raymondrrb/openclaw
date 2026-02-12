# DaVinci Resolve Studio Workflow — Rayviews Product Ranking Videos

Professional editing workflow for 8-12 minute Top 5 Amazon product ranking videos.
1080p, 30fps, ElevenLabs voiceover, Dzine product images, free stock B-roll.

---

## 1. Project Setup

### Project Settings (File > Project Settings)

| Setting | Value |
|---------|-------|
| Timeline Resolution | 1920x1080 |
| Timeline Frame Rate | 29.97 fps |
| Playback Frame Rate | Match timeline |
| Color Science | DaVinci YRGB |
| Color Space | Rec.709 Gamma 2.4 |
| Audio Sample Rate | 48000 Hz |

Set timeline frame rate at project creation. Changing it later causes drift.

### Optimized Media (if Edit page is sluggish)

Project Settings > Master Settings > Optimized Media:
- Resolution: Half
- Format: DNxHR SQ or ProRes 422

Generate optimized media: right-click clips in Media Pool > Generate Optimized Media.

---

## 2. Track Layout (House Style)

Consistent across every video. Right-click track headers to rename and color.

### Video Tracks

| Track | Name | Color | Content |
|-------|------|-------|---------|
| V4 | Accents | Purple | Blurred BG duplicates, glows, light leaks |
| V3 | Overlays | Yellow | Rank badges, benefit text, lower thirds |
| V2 | B-Roll | Blue | Stock footage, screen recordings, evidence |
| V1 | Product | Green | Dzine images, Amazon product shots |

### Audio Tracks

| Track | Name | Content | Target |
|-------|------|---------|--------|
| A1 | VO | Voiceover (ElevenLabs chunks) | -16 LUFS |
| A2 | Music | Background music bed | -26 LUFS |
| A3 | SFX | Whooshes, clicks, hits | -18 LUFS |

Lock A1 after placement (padlock icon on track header).

---

## 3. Video Structure

```
HOOK (0-20s) > AVATAR (3-5s) > #5 > #4 > #3 > RESET > #2 > #1 > OUTRO
```

### Minute-by-Minute Rhythm Map (10-min video)

| Time | Section | Duration | Pacing |
|------|---------|----------|--------|
| 0:00-0:20 | Hook | 20s | Fastest: cut every 3-4s, 2+ visual changes in first 5s |
| 0:20-0:25 | Avatar Intro | 5s | Quick branded clip, then gone |
| 0:25-1:55 | Product #5 | 90s | hero(3s) > detail(4s) > b-roll(5s) > hero-zoom(4s) |
| 1:55-3:25 | Product #4 | 90s | Same rhythm, different motion directions |
| 3:25-4:55 | Product #3 | 90s | Same rhythm |
| 4:55-5:30 | Retention Reset | 35s | Pattern interrupt: question, compare chart, or montage |
| 5:30-7:00 | Product #2 | 90s | Add mood variant for visual richness |
| 7:00-9:00 | Product #1 | 120s | Strongest visuals, all 5 variants, longest segment |
| 9:00-9:20 | Outro/CTA | 20s | Affiliate disclosure, subscribe |

### Per-Segment Visual Rhythm (90-second segment)

```
0-3s:   [V1] Hero shot, zoom-in 3%         + [V3] Rank badge top-left
1-4s:   [V3] Product name lower-third
3-8s:   [V2] B-roll lifestyle clip          (first pattern break)
8-12s:  [V1] Detail close-up, pan-left      + [V3] Benefit #1 callout
12-17s: [V1] Usage scene
17-22s: [V2] B-roll context clip            (second pattern break)
22-27s: [V1] Hero shot again, zoom-out      + [V3] Benefit #2 callout
27-30s: [V1] Detail variant, slight rotation
...repeat rhythm, vary motion direction each cycle
```

Never hold any single image unchanged for more than 8 seconds.

---

## 4. Making Static Images Feel Like Video

### A) Ken Burns / Dynamic Zoom (primary technique)

**Fast method — Dynamic Zoom (no keyframes):**
1. Select clip on timeline
2. Inspector > Dynamic Zoom > On
3. Viewer dropdown (bottom-left) > Dynamic Zoom
4. Green rectangle = start frame, Red = end frame
5. Drag red rectangle inward ~5% for subtle zoom-in
6. Ease: **Ease In and Out** (smooth, cinematic)

| Zoom | Values |
|------|--------|
| Subtle | 1.00 > 1.03-1.05 |
| Standard | 1.00 > 1.05-1.07 |
| Snap zoom (pattern interrupt) | 1.00 > 1.10-1.15 over 6 frames |

Vary direction per cut: zoom-in, zoom-out, pan-left, pan-right.
Never repeat the same motion on consecutive cuts.

**Keyframe method (precise control):**
1. Inspector > Transform > Zoom: click diamond icon to set keyframe
2. Move playhead, set new Zoom value (auto-creates keyframe)
3. Keyframe Editor: right-click between keyframes > Smooth

### B) Blur Background Duplicate (cinematic depth)

For every product image on V1:
1. Duplicate clip to V4 (below V1)
2. V4 clip (background): Inspector > Zoom 1.50-2.50, Gaussian Blur 15-25
3. Optionally reduce V4 saturation 20-30%, darken Lift slightly
4. V1 clip (foreground): stays sharp, centered, original scale
5. Animate V4 with slow drift (2-3% position change over clip)

Creates shallow-DOF look from flat images. Use on hero shots and #1 product.

### C) B-Roll Integration

- Keep clips 3-6 seconds
- Color-grade to match your video's look
- Insert every 8-12 seconds as visual bridges
- Never use more than 3s of any single stock clip
- Prefer clips with natural movement (hands using product, environment)

---

## 5. Text and Overlays

### Typography

| Element | Font | Size | Position |
|---------|------|------|----------|
| Rank badge | Montserrat Bold | 90-120px | Top-left |
| Product name | Montserrat Bold | 60-80px | Lower-left |
| Benefit callout | Inter Medium | 45-55px | Lower-left |
| Evidence source | Inter Regular | 30-36px | Lower-right |
| Disclosure | Inter Regular | 28-32px | Lower-left |

Rules:
- Max 6 words per overlay
- 1 overlay visible at a time
- Always use: dark semi-transparent backing plate (60-80% opacity) OR drop shadow (3-5px offset, 50% opacity)
- Safe zones: 60px from edges, 120px from bottom (progress bar)
- Display 3-4 seconds, +1s per extra 2-3 words

### Overlay Templates

**Rank Badge:**
- "#5 PICK" or "#1 BEST" — bold, accent color background, rounded corners
- 3s duration, appears at segment start

**Benefit Callout:**
- "[icon] 40-hour battery" — clean, white text on dark plate
- Click SFX on appear
- 3s each, staggered by 4s

**Evidence Callout:**
- "According to RTINGS..." or "Wirecutter's #1 Pick" — smaller, subtle
- Lower-right, 3s, appears during evidence discussion

**Downside Label:**
- "Downside: No wireless charging" — amber/yellow accent
- 3s, appears during downside mention

### How to Save Templates

**Edit page Text+ (fastest):**
1. Effects Library > Titles > Text+, drag to V3
2. Style in Inspector (font, size, color, background)
3. Drag finished title into a **Power Bin** (Media page > Master > Power Bins)
4. Power Bins persist across all projects

---

## 6. Audio Chain (Fairlight Page)

### Voiceover (A1) — Signal Chain

Apply in Mixer panel (Fairlight > Mixer button):

**1. EQ (6-Band Parametric, built-in)**

| Band | Type | Freq | Gain | Q |
|------|------|------|------|---|
| 1 | High Pass | 80 Hz | - | 12 dB/oct |
| 3 | Bell | 2.5 kHz | +1 dB | 1.0 |
| 4 | Bell | 4-5 kHz | +2-3 dB | 1.2 |
| 6 | Low Pass | 13 kHz | - | 12 dB/oct |

Band 4 is the presence/clarity boost. Band 6 cuts hiss.

**2. De-Esser** (Effects Library > FairlightFX > De-Esser)

- Frequency: 5-8 kHz, narrow band
- Amount: -3 to -5 dB on peaks
- Apply BEFORE compression

**3. Compressor** (Mixer > Dynamics)

| Setting | Value |
|---------|-------|
| Threshold | adjust for -3 dB avg reduction |
| Ratio | 2:1 |
| Attack | 10-20 ms |
| Release | 100-150 ms |
| Make-Up Gain | +3 dB |

**4. Limiter** (on Bus 1 / Main output)

- Ceiling: -1.0 dBTP (prevents clipping on any codec)
- Release: Auto

**5. Loudness Meter** (Fairlight > Meters > Loudness)

- Target: -14 LUFS Integrated on Bus 1
- Individual VO track: -16 LUFS

### Music Bed (A2)

- Level: -26 LUFS under voice, swell to -18 LUFS during transitions
- EQ: cut 2-5 kHz by 3-6 dB (creates vocal pocket)
- Duck 0.3s before VO starts, return 0.5s after VO ends
- Use 200-500ms fade curves (not hard cuts)
- Fade in over first 2s, fade out over last 3s

### SFX (A3)

- Whoosh: subtle, on every segment transition
- Click: when benefit overlay appears
- Level: -18 LUFS
- Never stack SFX — one at a time
- Apply 3-10 frame audio crossfades on every edit point

### Saving Audio Presets

1. Set up the full chain on A1
2. Right-click the channel strip > Save Track Preset
3. For new projects: right-click > Load Track Preset
4. Also save Bus 1 preset (limiter + loudness target)

---

## 7. Color (Quick Grade)

### Node Chain (per clip)

```
Node 1: Balance  >  Node 2: Match  >  Node 3: Look (optional)
```

**Node 1 — Primary Balance:**
- Open Waveform scope (Ctrl+Shift+W)
- Lift blacks to 0 IRE, highlights to 90-95 IRE
- Neutralize WB with Temp/Tint sliders

**Node 2 — Shot Match:**
1. Grade your best product shot first
2. Right-click thumbnail > Grab Still (Ctrl+Alt+G)
3. On other clips: right-click still > Shot Match to This Clip
4. Refine with RGB curves if needed

**Product image rule:** Don't overgrade product photos. Keep them clean and true to the Amazon listing. Only match white balance.

**B-roll rule:** Grade ALL stock to match your look. Unmatched stock screams amateur. Use Group Pre-Clip for clips from the same source.

---

## 8. Export (Deliver Page)

| Setting | Value |
|---------|-------|
| Format | MP4 |
| Codec | H.264 |
| Encoder | Hardware (NVIDIA/AMD) if available |
| Resolution | 1920x1080 |
| Frame Rate | 29.97 fps |
| Quality | Restrict to 20 Mbps CBR |
| Profile | High |
| Audio Codec | AAC |
| Audio Bitrate | 320 kbps |
| Network Optimization | On |

H.264 over H.265: faster encode, YouTube re-encodes everything to VP9/AV1 anyway. Save time.

Network Optimization: moves moov atom to front for faster YouTube processing.

---

## 9. Quality Control Checklist

### Before Export

**Visuals:**
- [ ] No static image held > 8 seconds without motion
- [ ] Text readable at 480px width (mobile test)
- [ ] No wrong product shown for segment
- [ ] Blur-BG duplicates don't show hard edges
- [ ] All overlays within safe zones

**Audio:**
- [ ] No clipping (check Bus 1 limiter — never exceeds -1 dBTP)
- [ ] VO loudness consistent across chunks
- [ ] Music not overpowering VO (test on laptop speakers, no headphones)
- [ ] Audio crossfades on all edit points (no pops/clicks)
- [ ] De-esser not over-processing (check S sounds)

**Pacing:**
- [ ] Hook grabs within 5 seconds (no "hey guys", no logo)
- [ ] Visual change every 3-8 seconds throughout
- [ ] Pattern interrupt at retention reset point
- [ ] Segments balanced (no single product > 2:30)

**Compliance:**
- [ ] Affiliate disclosure on screen in last 8 seconds
- [ ] Exact text: "As an Amazon Associate I earn from qualifying purchases."
- [ ] No fake discount badges or urgency claims in visuals

**File:**
- [ ] Render completed without errors
- [ ] No missing media warnings
- [ ] File size reasonable (150-300 MB for 10-min 1080p)

---

## 10. Pattern Interrupt Techniques

Deploy every 60-90 seconds (aligned with retention reset and segment transitions):

1. **Scale shift** — snap zoom 10-15% over 6 frames, then hold
2. **Music drop** — duck music to silence for 1-2s, voice tone shifts
3. **Split-screen compare** — two products side by side, 2-4 seconds
4. **Text slam** — key stat bounces in with slight overshoot (0.3-0.5s)
5. **Quick montage** — 4-5 rapid product flashes (1s each) before reveal
6. **Evidence callout** — show source page screenshot briefly
7. **Direct question** — "But here is the catch..." with visual pause

---

## 11. Reference Channels (Study Their Editing)

| Channel | Style | Learn From |
|---------|-------|-----------|
| MrWhoseTheBoss | High-energy, frequent cuts (3-5s), heavy graphics | Pacing, blur-BG technique, text slams |
| MKBHD | Clean, minimal, product-as-hero | Composition restraint, color consistency |
| Project Farm | Evidence-first, test-driven | Trust through data visualization |
| Linus Tech Tips | Fast B-roll insertions (3-6s), aggressive zooms | B-roll density, SFX timing |

---

## 12. Folder Structure

```
artifacts/videos/<video_id>/
  inputs/
    products.json
    niche.txt
    seo.json
  script/
    script.txt
    manual_brief.txt
    script_review_notes.md
    prompts/
  assets/
    dzine/
      thumbnail.png
      products/
        05_hero.png, 05_usage1.png, 05_detail.png
        01_hero.png, 01_usage1.png, 01_detail.png, 01_usage2.png, 01_mood.png
      prompts/
    amazon/
      05_ref.jpg, 04_ref.jpg, ...
    broll/
      (manually downloaded stock clips)
  audio/
    voice/chunks/
      01.mp3, 02.mp3, ...
    music/
    sfx/
      whoosh.wav, click.wav
  resolve/
    markers.edl
    markers.csv
    notes.md
    edit_manifest.json
    broll_plan.txt
  export/
```

---

## 13. Daily Editing Recipe

1. Open DaVinci Resolve Studio
2. Create new project: `rayviews_<video_id>`, timeline 1920x1080 @ 29.97fps
3. Import media from `artifacts/videos/<video_id>/`
4. Import markers: right-click timeline > Timelines > Import > Timeline Markers from EDL > select `markers.edl`
5. Place voiceover chunks on A1 in order
6. Place music on A2, set -26 LUFS, duck under voice
7. Follow markers to place visuals on V1 (product images) and V2 (B-roll)
8. Apply Dynamic Zoom (3-7%) to all static images on V1
9. Create blur-BG duplicates on V4 for hero shots
10. Add overlays on V3 from Power Bin templates (rank badge, benefits, disclosure)
11. Place SFX on A3 at marker points (whoosh on transitions, click on benefits)
12. 0.5s dissolve between segments
13. Quick color match on B-roll (Color page > Shot Match)
14. QC checklist pass
15. Export: Deliver > YouTube_1080p_30 preset
16. Upload to YouTube

---

## Training Resources

### Official Blackmagic Design (free)

| Book | Focus | Priority |
|------|-------|----------|
| The Editor's Guide to DaVinci Resolve 20 | Timeline editing, delivery | #1 |
| The Fairlight Audio Guide to DaVinci Resolve 20 | VO chain, loudness, mixing | #2 |
| The Beginner's Guide to DaVinci Resolve 20 | Full overview | #3 (if new) |
| The Colorist Guide to DaVinci Resolve 20 | Shot matching, stock normalization | #4 |

Download from: blackmagicdesign.com/products/davinciresolve/training
Each includes downloadable project files for hands-on practice.

### Focus Areas (in priority order)

1. Edit page fundamentals (timeline management, trim modes, markers)
2. Fairlight audio workflows (EQ, compression, loudness metering)
3. Dynamic Zoom and Inspector keyframes
4. Color page shot matching (Node 2 workflow above)
5. Fusion basics only for animated title templates
6. Deliver page export presets
