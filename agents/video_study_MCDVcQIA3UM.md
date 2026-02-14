# Video Study: Complete DaVinci Resolve Course (Casey Faris, 5h07m)

**Source:** https://www.youtube.com/watch?v=MCDVcQIA3UM
**Creator:** Casey Faris (Ground Control)
**Duration:** 5:10:54
**Resolve Version:** DaVinci Resolve 20 (free + Studio)
**Relevance:** Core editing workflow for Rayviews pipeline -- timeline assembly, audio mixing, color grading, text overlays, export settings.

---

## 1. Settings, Values, Keyboard Shortcuts

### Essential Keyboard Shortcuts

| Shortcut | Action | Page |
|----------|--------|------|
| I / O | Set in-point / out-point | Edit |
| J / K / L | Reverse / Stop / Forward playback | Edit |
| Shift+L / Shift+J | 2x speed forward / reverse | Edit |
| A | Selection mode (arrow tool) | Edit |
| T | Trim mode | Edit |
| B | Blade mode (split at playhead) | Edit |
| Control+\ | Split clip at playhead | Edit |
| Control+Shift+[ | Ripple trim start to playhead | Edit |
| Control+Shift+] | Ripple trim end to playhead | Edit |
| Alt+S | Add serial node | Color |
| Alt+P | Add parallel node | Color |
| Ctrl+D | Disable/enable selected node | Color |
| Ctrl+Shift+W | Open waveform scope | Color |
| Ctrl+G | Group selected tracks | Fairlight |
| M | Add marker at playhead | All |
| F2 | Rename selected node | Fusion |
| 1 / 2 | Load node into viewer 1 / viewer 2 | Fusion |
| Shift+Space | Search all available nodes | Fusion |
| Alt+Click | Add volume automation control point | Edit/Fairlight |
| Ctrl+Alt+Click | Remove automation point | Fairlight |

### Recommended Custom Shortcuts (Casey's Setup)

| Key | Custom Action |
|-----|---------------|
| Q | Trim clip start to playhead (ripple) |
| W | Trim clip end to playhead (ripple) |
| S | Split clip at playhead |

### Project Settings

| Setting | Recommended Value |
|---------|------------------|
| Timeline resolution | Set at project creation (cannot reliably change later) |
| Frame rate | Set at project creation (1080p @ 29.97 or 30fps) |
| Color Science | DaVinci YRGB Color Managed |
| Intermediate Color Space | HDR DaVinci Wide Gamut (for color managed) |
| Output Color Space | Rec 709 |
| Audio | 48,000 Hz default |

---

## 2. Workflow Steps (Maps to Pipeline Automation)

### Media Page Workflow

1. **Import media** into Media Pool -- drag folders or use Import Media button
2. **Organize into bins** -- create bins for audio, video, images, SFX, music
3. **Smart Bins** -- auto-filter by metadata (file type, resolution, frame rate)
4. **Hover scrub** -- mouse over thumbnails to preview without opening
5. **Metadata tagging** -- add keywords/comments in metadata panel for search
6. **Audio sync** -- right-click two clips > Auto Sync Audio > Based on Waveform (syncs via waveform matching)
7. **DRP export** -- File > Export Project to share/backup entire project as .drp file

### Edit Page Assembly Workflow

1. **Source viewer** -- double-click clip in Media Pool to open in source viewer
2. **Set in/out points** -- I/O to mark region of interest
3. **Insert modes:**
   - **Overwrite** (F10 or drag) -- replaces timeline content at playhead
   - **Insert** (F9) -- pushes existing clips forward to make room
   - **Append to End** (Shift+F12) -- adds after last clip on timeline
   - **Place on Top** -- adds to next available track above playhead
   - **Replace** -- replaces selected clip with source (maintains duration)
4. **Snapping** -- magnet icon toggles snap-to-clip-edges and markers
5. **Delete gaps** -- select empty space + Delete key to close gap
6. **Middle mouse button** -- pan/navigate within timeline

### Trim Tool Operations

| Action | How |
|--------|-----|
| Ripple trim | Trim mode (T), drag clip edge -- adjusts adjacent clips |
| Slip | Drag center-top of clip -- moves in/out points while keeping duration |
| Slide | Drag center-bottom -- moves clip position, trims neighbors |
| Roll | Drag edit point between two clips -- shifts cut point |

### Inspector Properties (per clip)

- **Transform**: Position X/Y, Zoom X/Y, Rotation angle, Anchor point
- **Cropping**: Left/Right/Top/Bottom pixel crop + softness
- **Composite**: Blend mode (screen, multiply, overlay, etc.) + opacity 0-100%
- **Stabilization**: Built-in, accessible from Inspector panel
- **Retime**: Right-click clip > Retime Controls for speed changes
- **Dynamic Zoom**: Toggle on/off, Ease type selection

### Keyframe Animation

1. Click diamond icon next to any Inspector property to create keyframe
2. Move playhead to new position, change value -- auto-creates second keyframe
3. Open Keyframe Editor panel (diamond icon on timeline toolbar)
4. For easing: switch to Curve mode, select keyframe, flatten Bezier handles
5. Flatten = slow start/stop (ease in/out), pointy = linear (mechanical)

---

## 3. Timeline, Tracks, Rendering

### Timeline Fundamentals

- Timeline is shared across Edit, Cut, Fusion, Color, Fairlight, and Deliver pages
- Changes on any page reflect on all other pages
- Multiple timelines possible per project
- Compound clips: select multiple clips > right-click > New Compound Clip (bundles into single timeline clip)
- Timeline resolution and frame rate set at project creation time

### Track Management

- Add video/audio tracks: right-click track header area > Add Track
- Rename tracks: right-click track header > Rename
- Color tracks: right-click > Change Track Color
- Lock tracks: padlock icon on track header (prevents accidental edits)
- Mute/solo audio tracks: M/S buttons on track headers

### Cut Page (Quick Assembly)

- Dual timeline: top = zoomed-out overview, bottom = zoomed-in detail
- Smart Insert: auto-finds closest edit point
- Sync Bin: for multicam workflows
- Best for quick rough cuts, vlogs; not ideal for precision pipeline work

---

## 4. Audio Mixing (Fairlight Page)

### Page Layout

- Same timeline as Edit page (audio edits reflect in both)
- Full mixer panel with per-track faders, EQ, dynamics, effects, bus routing
- Loudness meter for monitoring output levels
- Sound Library panel for indexing and searching SFX folders

### Track Types and Routing

| Type | Use |
|------|-----|
| Mono | Single-channel audio (VO, single SFX) |
| Stereo | Two-channel audio (music, ambient) |
| Bus | Submix routing (dialogue bus, SFX bus, music bus, main output) |

### Bus Setup

1. Fairlight menu > Bus Format > Add Bus (e.g., "Dialogue Bus", "Music Bus")
2. Route tracks to bus: Track > Bus Output > select target bus
3. Route sub-bus to main: Bus > Bus Output > Bus 1 (main)
4. Apply shared effects on bus (e.g., compressor on all dialogue tracks at once)

### Key Audio Techniques

**Compressor on Dialogue (via Dynamics panel):**
- Double-click green line in mixer to open Dynamics
- Turn on Compressor section
- Set threshold below average level, low ratio (gentle compression)
- Watch gain reduction meter -- aim for small amount of reduction
- Add makeup gain to bring overall level back up
- Result: quieter parts louder, louder parts controlled
- **Preset shortcut:** Dynamics > Default dropdown > "Dialogue Compression" (great starting point)

**EQ (built-in per track):**
- Double-click cyan line in mixer to open EQ
- Left = low frequencies, Right = high frequencies
- Cut high frequencies = muffled/distant sound
- Boost mid-high frequencies = presence/clarity
- For pipeline VO: high-pass at 80 Hz, presence boost at 2.5-5 kHz

**Volume Automation:**
- Alt+click on clip volume line to add control points
- Drag points up/down to automate volume changes
- Ctrl+Alt+click to remove individual automation points
- Range mode (second tool): top of clip = select range, bottom = move clip
- Focus mode: automatically switches between range and move based on cursor position

**Sound Library:**
- Add library folder: Sound Library panel > Add Library > scan folder
- Indexed for search by filename and metadata
- Drag sounds directly from library to timeline

**Track Groups:**
- Select multiple tracks > Ctrl+G to group
- Link faders, mute, solo controls across grouped tracks
- Useful for grouping all VO tracks or all SFX tracks

**Audio Fade Handles:**
- Fade handles at clip start/end in Edit page
- Drag inward to create fade in/out
- Crossfade: overlap two audio clips, right-click > Crossfade options

### Music Editing Tips

- Split music at similar waveform peaks (on beats) for clean edits
- Use crossfades at music edit points to avoid pops
- M key to mark beat positions for reference

---

## 5. Color Grading (Color Page)

### Color Management Setup

1. Project Settings > Color Management > Color Science: **DaVinci YRGB Color Managed**
2. Resolve Color Management Preset: **HDR DaVinci Wide Gamut Intermediate**
3. Input Color Space: tag per-clip (right-click clip in timeline > Input Color Space)
4. Output Color Space: **Rec 709** (standard display for YouTube)
5. Result: Resolve handles all internal conversions automatically

### Node Graph Architecture

| Node Type | Shortcut | Use |
|-----------|----------|-----|
| Serial | Alt+S | Sequential processing (most common) |
| Parallel | Alt+P | Blended parallel corrections |
| Layer | - | Stacked with masks/mattes |

- **Timeline nodes** vs **Clip nodes**: dots at top-right of node graph toggle between them
- Timeline nodes = global grade applied to all clips (use for overall look)
- Clip nodes = per-clip grade (use for shot matching)
- Node label: right-click node > Node Label (e.g., "Balance", "Look", "Skin Fix")
- Ctrl+D to disable/enable selected node for A/B comparison

### Primary Color Wheels

| Wheel | Affects | Pipeline Use |
|-------|---------|-------------|
| Lift | Shadows/darks | Set black point |
| Gamma | Midtones | Overall brightness feel |
| Gain | Highlights/brights | Set white point |
| Offset | Entire image uniformly | Global color shift |

- Master wheels below each color wheel: luminance-only adjustment per range
- Primary controls: Contrast, Pivot, Temperature, Tint, Saturation, Color Boost, Shadows, Highlights

### Curves

| Curve | Use |
|-------|-----|
| Custom curves | S-curve for filmic contrast (drag shadows down, highlights up) |
| Hue vs Hue | Shift specific colors (e.g., make greens more teal) |
| Hue vs Sat | Saturate/desaturate specific colors |
| Hue vs Lum | Brighten/darken specific colors |
| Lum vs Sat | Control saturation by brightness (e.g., desaturate shadows) |
| Sat vs Sat | Control saturation of already-saturated areas |
| Sat vs Lum | Brighten/darken by saturation level |

- Use eyedropper on image to automatically add control point on correct curve position
- Subtle adjustments preferred -- large shifts look unnatural

### Scopes

| Scope | Reading | Pipeline Use |
|-------|---------|-------------|
| Waveform (Y mode) | 0 = pure black, 1023 = pure white | Check exposure: blacks near 0, whites near 900-1023 |
| Parade (RGB) | Separate R/G/B channels | Balance channels for neutral whites (all three peaks align) |
| Vectorscope | Distance from center = saturation, angle = hue | Check skin tone line, overall saturation |
| Histogram | Distribution of luminance values | Quick exposure overview |

### Windows/Masks (Color Page)

- Shapes: circle (most versatile), rectangle, gradient, polygon, custom curve
- Soft edge = feathered falloff (essential for natural blending)
- Track window to moving subject: one-click Tracker (track forward/backward)
- Use windows to isolate subject for separate grading, or isolate background

### Qualifier (Color-Based Selection)

- Eyedropper tool: click on specific color in image to select it
- HSL qualifier: refine selection by hue, saturation, luminance ranges
- Matte Finesse: clean/denoise/shrink/grow the matte
- Use for: skin tone isolation, sky color shift, product color consistency

### Advanced Wheels

| Wheel Set | Description |
|-----------|-------------|
| Log wheels | Shadow/Midtone/Highlight with adjustable range crossover points |
| HDR wheels | 6-zone split (Dark, Shadow, Light, Highlight, Specular, Black) |

- **Mid-Detail slider** in HDR panel: negative values = skin softening (reduces mid-frequency detail)

### Efficient Grading Workflow

1. **Hero shot**: Grade your best-looking clip first (this is the reference)
2. **Grab still**: Right-click viewer > Grab Still (stores in Gallery)
3. **Split-screen compare**: Play/stop still = split-screen view against current clip
4. **Shot match**: Right-click still > Apply Grade (copies entire node tree to current clip)
5. **Copy grade**: Middle mouse button click from graded clip to ungraded clip in thumbnail strip
6. **Reset**: Right-click > Reset All Grades and Nodes (start over)
7. **Group grading**: Pre-clip nodes for clips from same source, post-clip for per-shot adjustment

---

## 6. Export / Delivery (Deliver Page)

### Interface Layout

- Viewer + timeline (read-only, for reference)
- Render Settings panel = where all decisions happen
- Render Queue = job list (add multiple, then Render All)

### Codec Decision Matrix

| Codec | File Size | Quality | Playback | Best For |
|-------|-----------|---------|----------|----------|
| H.265 (HEVC) | Small | Excellent | Hard (CPU intensive) | YouTube upload (primary recommendation) |
| H.264 | Small | Good (slightly blocky) | Easy | Universal compatibility, older systems |
| ProRes 422 HQ | Large | Excellent | Easy | Archive, intermediate, further editing |
| DNxHR | Large | Excellent | Easy | Archive, Windows-focused workflows |

- **Never use uncompressed** -- file sizes are insane, quality difference imperceptible
- H.265 requires Resolve Studio on Windows (free on Mac)

### YouTube Export Recipe (from Casey)

1. Click **H.265 Master** preset at top of render settings
2. Change Resolution from "Timeline" to **Ultra HD** (3840x2160)
3. This up-res tricks YouTube into using better VP9/AV1 compression
4. Set file name (e.g., "movie-YT")
5. Set output location (Browse)
6. Click **Add to Render Queue**
7. Click **Render All**

**Why up-res to Ultra HD:** YouTube applies higher-quality compression codec (VP9 or AV1) to 4K uploads. Even though source is 1080p, the final YouTube player result looks noticeably better than uploading native 1080p.

### Archive Export Recipe

1. Click **ProRes** preset
2. Optionally select ProRes 4444 or ProRes 422 HQ for maximum quality
3. Audio tab: Codec = **Linear PCM**, Bit Depth = **32-bit float**
4. Audio tab: Output Track = **All Timeline Tracks** (renders each Fairlight track as separate audio track in the file)
5. Add to Render Queue

### Render Queue

- Stack multiple render jobs with different settings (YouTube version, archive version, etc.)
- Each job can target different codecs, resolutions, output folders
- **Render All** processes entire queue sequentially
- Single Clip mode (default) = one movie file
- Individual Clips mode = each timeline clip as separate file (useful for clip export/prep)

### Audio Export Settings

| Setting | YouTube | Archive |
|---------|---------|---------|
| Codec | AAC (default) | Linear PCM |
| Bit Depth | 16-bit | 32-bit float |
| Tracks | Main output only | All timeline tracks |
| Sample Rate | 48,000 Hz | 48,000 Hz |

### File Naming

- Custom Name: type directly in field
- Timeline Name: auto-uses timeline name (useful for batch rendering multiple timelines)
- Subfolder option for organized output

---

## 7. Fusion Compositing (Text Overlays & Effects)

### Node Architecture

```
MediaIn (input from timeline) --> [Processing Nodes] --> MediaOut (output to timeline)
```

- Every Fusion composition starts with MediaIn and ends with MediaOut
- Nodes connect left-to-right via flow lines
- Yellow input = background, Green input = foreground, Blue input = mask

### Core Nodes for Pipeline

| Node | Function | Pipeline Use |
|------|----------|-------------|
| Text+ | Text rendering with full typography control | Product names, rank badges, benefit callouts |
| Background | Solid color/gradient rectangle | Backing plates for text overlays |
| Merge | Composites foreground over background | Layering text over backing plate |
| Transform | Position, scale, rotation, flip | Resize/reposition elements |
| Blur | Gaussian/directional blur | Background blur effects |
| Rectangle/Ellipse/Polygon Mask | Shape-based masks | Isolate regions, rounded corners |
| Fast Noise | Procedural noise/fog/clouds | Animated texture backgrounds |
| Tracker | Motion tracking | Attach elements to moving subjects |
| Brightness/Contrast | Brightness, contrast, clip black/white | Exposure adjustments within comp |
| Color Corrector | Full color adjustment | Per-node color tweaks |
| Magic Mask (Studio only) | AI-based subject isolation | Background replacement |

### Merge Node Details

- **Merge shortcut**: Drag output of one node to the white square connector of another -- auto-creates Merge
- Center value in Merge: 0,0 = middle of frame; adjust X/Y to position foreground
- Size value: scale foreground element
- Blend: opacity of foreground layer (0-1)
- Apply Mode: over, in, held out, atop, xor, etc.

### Mask Nodes

- Polygon mask: right-click > **"Remove Polygon Polyline"** to stop Fusion auto-animating the shape
- Soft edge: essential for natural blending (increase from 0 for feathered falloff)
- Masks connect to blue input on any node to limit that node's effect

### Fast Noise (for animated backgrounds)

- Detail: complexity of noise pattern
- Scale: size of noise features
- Seethe Rate: animation speed (higher = faster movement)
- Use as animated texture behind text overlays or as fog/atmosphere

### Text+ Node Details

- Full typography: font, size, color, tracking, leading
- Shading tab: multiple layers of fills, outlines, shadows
- Layout tab: horizontal/vertical centering, text flow
- Keyframe text properties for animations (fly-in, fade, etc.)

### Template Creation Workflow

1. Build node tree (e.g., Background > Merge > Text+ > MediaOut)
2. Select all nodes > right-click > Macro > Create Macro
3. Expose adjustable controls (text content, colors, position)
4. Save to Fusion Templates folder
5. Access from Edit page: Effects Library > Titles

### Viewer Controls

- Press 1 to load selected node into Viewer 1
- Press 2 to load into Viewer 2
- Two-viewer layout for comparing input vs output

---

## 8. Efficiency & Batch Processing Tips

### Batch Zoom/Motion Application

1. Set Dynamic Zoom on one image clip (Inspector > Dynamic Zoom)
2. Cmd+C to copy the clip
3. Select all other image clips on timeline
4. Right-click > **Paste Attributes** (or Alt+V)
5. Check only **Dynamic Zoom** checkbox
6. All selected clips get the same zoom motion

### Power Bins (persistent templates)

- Media page > Master > Power Bins
- Drag any styled element (title, SFX, music bed, transition) into Power Bin
- Available across ALL projects in the same Resolve database
- Use for: rank badge templates, benefit callout templates, disclosure text, standard SFX

### Track Presets (Audio)

1. Set up full audio chain on a track (EQ, compression, effects)
2. Right-click channel strip > Save Track Preset
3. In new projects: right-click > Load Track Preset
4. Save separate presets for VO, music, SFX, and Bus 1 (master limiter)

### Compound Clips

- Select multiple clips > right-click > New Compound Clip
- Bundles into single item on timeline
- Double-click to edit contents
- Useful for packaging per-product segments as reusable units

### Timeline Sharing

- All pages share the same timeline -- edits on any page reflect everywhere
- Color page sees same clips as Edit page
- Fairlight audio changes play back in Edit page
- Fusion compositions embedded in timeline clips
- This means: assemble on Edit, grade on Color, mix on Fairlight, composite in Fusion -- all on the same timeline

### Gallery Stills (Color Page)

- Grab stills for reference grading across clips and projects
- Stills persist in project gallery
- Right-click still > Apply Grade to batch-apply grades
- Middle mouse button click = quick copy grade between adjacent clips in thumbnail strip

### Render Queue Batching

- Stack multiple render jobs with different settings in Render Queue
- Render All processes them sequentially
- Use for: YouTube version + archive version + clip exports in one pass
- Timeline Name option auto-names files when batch rendering multiple timelines

### DRP Project Backup

- File > Export Project (.drp file) -- portable project backup
- Contains project settings, timeline structure, grades, effects, markers
- Does NOT contain media files (just references them)
- Share with collaborators or archive for safety

---

## Pipeline-Specific Takeaways

### What Maps Directly to Rayviews Automation

| Transcript Knowledge | Pipeline Application |
|---------------------|---------------------|
| Inspector Zoom X/Y = Ken Burns | `item.SetProperty("ZoomX", 1.05)` in Python API |
| Dynamic Zoom Ease In/Out | `DynamicZoomEase = 3` for smooth motion |
| Paste Attributes for batch zoom | Batch apply via API loop on all V1 clips |
| Fairlight bus routing | Route VO to Dialogue Bus, Music to Music Bus, apply shared compression |
| Dialogue Compression preset | Use built-in preset as starting point for VO processing |
| H.265 Master + Ultra HD upres | Optimal YouTube delivery strategy |
| Timeline nodes (Color) | Apply global color look to all clips at once |
| Clip nodes (Color) | Per-product color matching |
| Power Bins | Store rank badge, benefit callout, disclosure templates |
| Track Presets | Load standard VO chain (EQ + compressor) on every project |
| Merge node (Fusion) | Layer text overlays over product images |
| Text+ node | Product names, rank badges, benefit callouts |
| Render Queue batching | Export YouTube + archive versions in single pass |
| Linear PCM + all tracks (archive) | Preserve separate VO/music/SFX for future remixing |

### Critical Settings for Pipeline

| Parameter | Value | Source |
|-----------|-------|--------|
| YouTube codec | H.265 | Casey: "click H.265 master and call it good" |
| YouTube resolution | Ultra HD (3840x2160) upres | Casey: "YouTube uses different compression, video looks better" |
| Dialogue dynamics | Compressor, low ratio, gentle threshold | Casey: "just a little bit of gain reduction" |
| Dialogue preset | "Dialogue Compression" in Dynamics dropdown | Casey: "a really great starting point" |
| EQ for muffled/distant | Cut high frequencies | Casey: "push high side down" |
| Color management | YRGB Color Managed + HDR Wide Gamut | Casey: recommended setup for Resolve 20 |
| Output color space | Rec 709 | Casey: "standard display color space" |
| Archive codec | ProRes 422 HQ | Casey: "ProRes or DNxHR, fantastic for archiving" |
| Archive audio | Linear PCM, 32-bit float, all tracks | Casey: "render each track as separate track" |
| Encoder | Auto (let Resolve choose hardware/software) | Casey: "probably just leave at auto" |
| Container format | QuickTime (default) or MP4 | Casey: "unless you have reason not to, select QuickTime" |

### Differences from Current `resolve_editing_rules.md`

| Topic | Current Rules | Casey's Recommendation | Action |
|-------|--------------|----------------------|--------|
| YouTube codec | H.264 | H.265 Master | Consider upgrading to H.265 for better YouTube quality |
| YouTube resolution | 1920x1080 | 3840x2160 upres | Adopt the 4K upres trick -- YouTube applies better compression |
| Color science | DaVinci YRGB | DaVinci YRGB Color Managed | Already noted in automation guide; current rules use simpler setup |
| Archive format | Not specified | ProRes 422 HQ + Linear PCM + all tracks | Add archive export to pipeline for backup |
| Color management | DaVinci YRGB (simple) | DaVinci YRGB Color Managed + HDR Wide Gamut | Upgrade for automatic color space handling |
| Dialogue processing | 6-step manual chain (EQ → De-Esser → Comp → Limiter → Duck → SFX) | Fairlight Bus + "Dialogue Compression" preset + AI tools | Combine Casey's bus structure with AI Audio Assistant |
| Audio bus routing | Single track processing | Dedicated Dialogue Bus + Music Bus + SFX Bus → Main Bus | Adopt bus-based routing for cleaner mix control |

---

## Cross-Reference: All Video Studies Combined

### How This Course Fits With Previous Studies

| Study | Focus | Key Contribution |
|-------|-------|-----------------|
| **This course (Casey Faris)** | Complete Resolve foundations | Workflow understanding, settings, bus routing, export tricks, Fusion templates |
| video_study_LiKqDWRdQw0 (David Shutt) | 16 AI tools in Resolve Studio | AI Audio Assistant, AI Depth Map 2, AI Animated Subtitles, Smart Reframe |
| video_study_zYItBOaD8Ik (Justin Brown) | 15 AI tools workflow | AI Music Remixer (stem-based), Voice Cloning, Audio Matchers, Relight |
| video_study_DX0O9S0 (Sightseeing Stan) | Free plugins | MagicZoom, MagicAnimate, MagicSubtitle, Free Starter Pack 2.0 |

### Synthesis: Definitive Editing Workflow

Combining Casey's foundational workflow with AI tools from the other studies, the optimal pipeline editing workflow is:

**Phase 1: Project Setup (Casey foundation)**
1. Create project: 1920x1080 @ 29.97fps
2. Color Science: DaVinci YRGB Color Managed, HDR Wide Gamut intermediate, Rec 709 output
3. Set up track layout: V1-V4 (product/B-roll/overlays/accents), A1-A3 (VO/music/SFX)
4. Create Fairlight buses: Dialogue Bus, Music Bus, SFX Bus → Bus 1 (main)
5. Load Track Presets for each bus (saved from previous projects)

**Phase 2: Media Import (Casey foundation)**
6. Import media into organized bins (VO chunks, product images, music, SFX)
7. Import timeline markers from EDL (if using automation)
8. Place VO chunks on A1 sequentially
9. Place music bed on A2

**Phase 3: Visual Assembly (Casey + MagicZoom plugin)**
10. Place product images on V1 with Dynamic Zoom (3-7%)
11. **MagicZoom**: Batch-apply zoom presets to all V1 clips (saves 15-20 min)
12. Place B-roll on V2 at pattern-interrupt points
13. Place overlays on V3 (rank badges, benefit text from Power Bins)
14. **AI Depth Map 2**: Single-layer background blur on hero shots (replaces V4 duplicate workflow)

**Phase 4: Audio Mix (Casey bus routing + AI tools)**
15. **AI Music Remixer**: Stem-based vocal pocket on music track (mute vocals, reduce guitar -6dB)
16. **AI Audio Ducker**: Automatic music ducking under VO
17. **AI Audio Assistant**: One-click YouTube standard mix → -14 LUFS master
18. Fine-tune bus fader levels if needed: VO -16 LUFS, music -26 LUFS, SFX -18 LUFS
19. "Dialogue Compression" preset on Dialogue Bus as safety net

**Phase 5: Color (Casey node workflow + AI tools)**
20. Timeline Node: Global look (warm, slightly desaturated for 40+ audience)
21. Clip Node 1 (Balance): **AI Auto Color** as starting point, refine with waveform
22. Clip Node 2 (Match): Grab Still from hero shot, Apply Grade to batch
23. Product images: minimal grading (true to Amazon listing)

**Phase 6: Polish (Fusion + plugins)**
24. **AI Animated Subtitles**: Word Highlight style for accessibility
25. Verify 0.5s dissolves at segment transitions (MagicAnimate presets)
26. QC checklist pass

**Phase 7: Delivery (Casey's export strategy)**
27. **YouTube export**: H.265 Master → upres to 3840x2160 (Ultra HD) → Render Queue
28. **Archive export**: ProRes 422 HQ + Linear PCM 32-bit float + all tracks → Render Queue
29. **Shorts** (optional): AI Smart Reframe → 9:16 version → Render Queue
30. **Render All**: Process entire queue

### Time Budget Comparison

| Phase | Manual (Old) | AI-Enhanced (New) | Saved |
|-------|-------------|-------------------|-------|
| Visual assembly | 45-60 min | 25-35 min | 20-25 min |
| Audio mix | 45-60 min | 5-10 min | 40-50 min |
| Color grading | 20-30 min | 10-15 min | 10-15 min |
| Polish | 15-20 min | 10-15 min | 5 min |
| Export | 5 min (1 job) | 5 min (3 jobs queued) | 0 min |
| **Total** | **130-175 min** | **55-80 min** | **75-95 min** |

---

## About the Creator

**Casey Faris** — Blackmagic Certified DaVinci Resolve Trainer (one of ~250 globally). 13+ years teaching Resolve. 554K+ subscribers, 18.7M views.

Professional background: Executive Producer and Editor of "Graveyard Carz" (Discovery Channel). Professional colorist, compositor, and DP. Presented for Blackmagic Design at NAB, VidCon, and ResolveCon.

Founder of **Ground Control** (groundcontrol.film) — paid courses ($199 each): "Make A Film in DaVinci Resolve (End to End)", Fusion 101-401, Color 101, Fairlight 101.

Free companion resources for this course: practice media download at groundcontrol.film/intro-to-resolve-2025-project-media-free-download.

---

## Action Items

### Immediate (This Week)

- [ ] **Test H.265 + 4K upres export** — encode a test video with Casey's YouTube recipe (H.265 Master → 3840x2160) and compare YouTube playback quality vs current H.264 @ 1080p
- [ ] **Set up Fairlight bus routing** — create Dialogue Bus, Music Bus, SFX Bus template. Save as Track Preset for reuse
- [ ] **Load "Dialogue Compression" preset** — test on ElevenLabs TTS output and measure before/after LUFS
- [ ] **Create Power Bins** — save rank badge template, benefit callout template, FTC disclosure text into Power Bins for cross-project reuse

### Short-Term (This Month)

- [ ] **Update `resolve_editing_rules.md`** — incorporate Casey's bus routing, H.265 export, 4K upres, and Color Managed workflow
- [ ] **Build Fusion macro templates** — product name lower-third, rank badge overlay, benefit callout (Background + Text+ + Merge). Save to Templates folder
- [ ] **Add archive export** to pipeline: ProRes 422 HQ + Linear PCM 32-bit float + separate tracks. Preserve original audio stems for future remixing
- [ ] **Test Color Managed workflow** — switch from simple YRGB to YRGB Color Managed + HDR Wide Gamut + Rec 709 output. Verify product image colors remain accurate

### Medium-Term (Next Month)

- [ ] **Automate via Python API** — script project creation with all Casey settings (resolution, color science, bus routing, track layout). Add to `resolve_packager` agent
- [ ] **Template timeline** — create DRP template with pre-configured V1-V4 + A1-A3 + buses + track presets + Power Bins. Import as starting point for each new video
- [ ] **Render Queue automation** — script 3-job render queue (YouTube H.265 4K + archive ProRes + Shorts 9:16) via API

### Long-Term (Pipeline Enhancement)

- [ ] **Headless rendering** — `DaVinciResolve -nogui` for server-side batch rendering of completed timelines
- [ ] **Fusion template library** — build comprehensive set of pipeline-specific Fusion macros (per-product segment, hook sequence, outro sequence)
- [ ] **Color grading presets** — create and save Gallery Stills per niche category (kitchen products = warm, tech = cool neutral, outdoor = natural green)

---

## Sources

- [Casey Faris YouTube Course](https://www.youtube.com/watch?v=MCDVcQIA3UM)
- [Ground Control](https://www.groundcontrol.film/)
- [Ground Control Free Practice Media](https://www.groundcontrol.film/intro-to-resolve-2025-project-media-free-download)
- [Ground Control End-to-End Course](https://www.groundcontrol.film/end-to-end)
- [Blackmagic DaVinci Resolve](https://www.blackmagicdesign.com/products/davinciresolve)
- [Blackmagic Official Training](https://www.blackmagicdesign.com/products/davinciresolve/training)
- [DaVinci Resolve Scripting API (Unofficial Docs)](https://deric.github.io/DaVinciResolve-API-Docs/)
- [DaVinci Resolve 20.3.2 Release](https://www.newsshooter.com/2026/02/11/davinci-resolve-20-3-2-update/)
- [Casey Faris on CreativeLive](https://www.creativelive.com/class/how-to-edit-video-in-davinci-resolve-casey-faris)
- [Blackmagic Free Webinar Series 2026](https://ymcinema.com/2026/02/09/blackmagic-free-davinci-resolve-training/)

---

*Analysis: Manual transcript extraction + web research | Study date: 2026-02-13 | Video duration: 5:10:54 | Transcript: 8,751 lines*
