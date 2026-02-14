# Video Study: Colour Grading For BEGINNERS (DaVinci Resolve Tutorial)

- **Video ID:** _KImTKhy_mI
- **Channel:** Declan Jenkinson
- **Duration:** 20:03
- **Upload Date:** 2025-07-03
- **Views:** 284,182 | **Likes:** 13,926
- **Study Date:** 2026-02-13
- **URL:** https://www.youtube.com/watch?v=_KImTKhy_mI

## Relevance to Rayviews

This is a **DaVinci Resolve color grading tutorial** directly applicable to our post-production workflow. We already use DaVinci Resolve for assembly and export — this video teaches the Color Page techniques we need to create a consistent "Rayviews look" across all videos. Key takeaway: a standardized node chain (WB -> EXP -> SAT) plus PowerGrades gives us repeatable color consistency for Dzine-generated product images and Ray avatar segments.

## Summary

Comprehensive beginner-friendly DaVinci Resolve Color Page tutorial covering the full color grading workflow from project setup to advanced techniques. The presenter (young male, dark teal shirt) teaches via screen recording of Resolve Studio 20 with a circular webcam overlay in the top-right corner. Uses five diverse cinematic B-roll clips as working examples: Japanese torii gate, beach/lake landscape, night city neon scene, tropical greenhouse, and desert Joshua tree. Covers Primaries (Color Wheels and Log Wheels), Curves (Hue vs Hue), Color Warper, AI Cinematic Haze, node chain structure, scopes, color management, Stills Gallery, PowerGrades, and CST nodes. 284K views in ~7 months indicates high demand for this content.

## Editing Style Analysis

### Structure
1. **Hook** (0:00-0:30): Brief talking head introduction to color grading fundamentals
2. **Project Setup** (~0:30-2:00): Color Management settings — DaVinci YRGB color science, Rec.709-A timeline/output color space
3. **Node Chain Foundation** (~2:00-5:00): Building the WB -> EXP -> SAT base node chain, explaining why this order matters
4. **Primaries - Color Wheels** (~5:00-8:00): Lift, Gamma, Gain, Offset wheels for global balance
5. **Primaries - Log Wheels** (~8:00-10:00): Shadow, Midtone, Highlights, Offset for finer per-range control
6. **Curves - Hue vs Hue** (~10:00-12:00): Selective hue shifting (demonstrated on desert sky)
7. **Color Warper** (~12:00-14:00): Advanced chroma manipulation via the Chroma Warp panel
8. **AI Cinematic Haze** (~14:00-16:00): Depth Map + Near Limit + Atmospheric Scattering for depth-based atmospheric effects
9. **Stills Gallery & PowerGrades** (~16:00-18:00): Saving reference grades, creating reusable presets
10. **Window Nodes & CST** (~18:00-19:30): Selective grading with Power Windows, Color Space Transform for camera-specific input
11. **Closing** (~19:30-20:03): CTA for free LUT download, booking link for lessons

### Visual Patterns

**Screen Recording Layout:**
- Full-screen DaVinci Resolve Studio 20 Color Page
- Circular presenter overlay (top-right corner) with teal/green border ring
- Presenter: young male, dark teal shirt, webcam quality, consistent position throughout
- Overlay is small enough to not obstruct key UI elements
- Occasionally switches to full-screen presenter for emphasis on key concepts

**B-Roll Example Footage:**
- Japanese torii gate: woman silhouette walking through red gate, moody natural lighting
- Beach/lake landscape: wide shot, natural daylight, used for exposure and white balance demos
- Night city: neon-lit street, girl with headphones, used for color warper and hue shifting
- Tropical greenhouse: man in tank top among plants, warm/green tones, used for skin tone grading
- Desert Joshua tree: wide desert landscape, used for Hue vs Hue sky color shift demo

**DaVinci Resolve Panels Shown:**
- Primaries - Color Wheels (Lift, Gamma, Gain, Offset)
- Primaries - Log Wheels (Shadow, Midtone, Highlights, Offset)
- Curves panel (Hue vs Hue mode)
- Color Warper (Chroma Warp view)
- Node Graph editor (WB -> EXP -> SAT chain, WINDOW nodes, LUT node)
- Scopes: Vectorscope, Waveform monitor, Parade
- Project Settings: Color Management dialog
- Gallery panel: Stills and PowerGrades

**Transitions:**
- Hard cuts between different Resolve panels and B-roll clips
- No fancy transitions — appropriate for tutorial format
- Smooth mouse movements with occasional zoom-in to highlight specific UI controls

**Text/Graphics:**
- Minimal text overlays — relies on the Resolve UI itself as visual reference
- No animated intros or branded graphics visible
- Chapter labels likely via YouTube chapters (not on-screen)

**Audio:**
- Clear voiceover narration throughout
- No background music during instruction segments
- Direct microphone recording

### Pacing
- Steady tutorial pace — explanatory, not rushed
- Each technique gets 2-3 minutes of dedicated explanation
- Demonstrates on actual footage before moving to next concept
- 10 major topics in 20 minutes = ~2 minutes per concept

## Key Insights for Rayviews Pipeline

### 1. Node Chain Template: WB -> EXP -> SAT
The foundational node chain structure (White Balance -> Exposure -> Saturation) should be our **standard starting template** for every Rayviews video in DaVinci Resolve. This ensures consistent processing order and makes troubleshooting easier. We can save this as a PowerGrade and apply it to every new project.

### 2. Log Wheels for Dzine Image Matching
Dzine-generated product images and Ray avatar segments will have different exposure characteristics. The Log Wheels (Shadow/Midtone/Highlights) give us **per-range control** to match these disparate sources into a cohesive look. Shadows for matching dark areas, Midtones for skin tones on the Ray avatar, Highlights for product reflections.

### 3. Hue vs Hue for Product Color Consistency
When Dzine generates multiple product image variants, colors may shift slightly between generations. Hue vs Hue curves let us **selectively correct specific hues** without affecting the rest of the image. Critical for maintaining accurate product colors that match Amazon listings.

### 4. PowerGrades = Rayviews Brand Consistency
Creating a "Rayviews" PowerGrade preset means every video gets the same color treatment automatically. This is the key to visual brand consistency across 50+ videos without manual per-video grading. Save the grade once, apply everywhere.

### 5. Color Management: Rec.709-A for YouTube
The tutorial confirms Rec.709-A as the correct output color space for YouTube delivery. DaVinci YRGB as the color science. This matches our existing export spec (1080p 30fps, 20-40 Mbps) and ensures colors display correctly on viewers' screens.

### 6. AI Cinematic Haze for Depth on Flat Images
AI Cinematic Haze uses depth estimation to add atmospheric scattering. This could add **subtle depth and dimension** to flat Dzine-generated product images that lack natural atmospheric perspective. The Near Limit and Atmospheric Scattering controls allow fine-tuning to keep it subtle.

### 7. CST Node for Mixed Sources
When combining Dzine images (sRGB), screen recordings, and potentially phone footage, a CST (Color Space Transform) node at the start of the chain handles the **input color space conversion** properly. This prevents color shifts when mixing sources.

### 8. Scopes for Objective Grading
Vectorscope and Waveform monitors provide **objective measurement** of color and exposure. Rather than eyeballing, we can use scopes to ensure consistent levels across all product segments — particularly important for maintaining the -16 LUFS/-1 dB peak audio alongside visually consistent video.

## What to Adopt

| Technique | How to Implement in Rayviews |
|-----------|-------------------------------|
| WB -> EXP -> SAT node chain | Create as default node tree in Resolve project template |
| Log Wheels per-range control | Use to match Dzine images and Ray avatar exposure |
| Hue vs Hue curves | Correct per-product color drift from Dzine generation |
| PowerGrades | Save "Rayviews Standard" grade, apply to all projects |
| Rec.709-A color space | Set in project settings template (already matches our spec) |
| AI Cinematic Haze | Subtle application on flat product images for depth |
| CST node | Add before WB node when mixing sRGB (Dzine) and other sources |
| Scopes (Vectorscope + Waveform) | Use as QA check before export for consistent levels |

## What to Improve Upon

| Their Approach | Our Adaptation |
|----------------|----------------|
| Tutorial teaches manual per-clip grading | We need batch-applicable PowerGrades for speed |
| Generic B-roll examples | Our footage is product images + avatar — different grading needs |
| No mention of AI-generated image grading | We need specific Dzine output color correction techniques |
| Single-clip workflow | We have 25-35 clips per video — need efficient timeline workflow |
| No mention of skin tone consistency | Ray avatar skin tones must match across all segments |
| Full creative grading (cinematic looks) | We need subtle, natural grading — trust over aesthetics |

## Production Replication with Our Tools

To implement this color grading workflow:
1. **Project Template** (DaVinci Resolve): Create project with DaVinci YRGB color science, Rec.709-A timeline/output, node chain template (CST -> WB -> EXP -> SAT)
2. **PowerGrade** (DaVinci Resolve): Grade one reference video, save as "Rayviews Standard" PowerGrade
3. **Per-Product Adjustment** (DaVinci Resolve): Use Log Wheels and Hue vs Hue for per-clip tweaks after applying PowerGrade
4. **Avatar Consistency** (DaVinci Resolve): Create separate "Ray Skin Tone" PowerGrade focused on consistent skin rendering
5. **QA Check** (DaVinci Resolve): Verify all clips pass Vectorscope/Waveform consistency check before export

Total time investment: ~30 minutes for initial PowerGrade creation, then ~5-10 minutes per video for per-clip adjustments.

## Analysis Metadata
- Frames analyzed: 241 sampled
- Method: Visual frame analysis
- Focus: Color grading workflow, DaVinci Resolve techniques, production pipeline applicability
