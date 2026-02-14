# Video Study: "11 FREE DaVinci Resolve Plugins to Edit FASTER!"

**Source:** https://www.youtube.com/watch?v=DX0O9S0-ubI
**Channel:** Sightseeing Stan (@SightseeingStan)
**Study Date:** 2026-02-13
**Relevance:** DaVinci Resolve editing pipeline for Rayviews Lab (automated Amazon Associates Top 5 product ranking channel)

---

## 1. Video Overview

**Title:** 11 FREE DaVinci Resolve Plugins to Edit FASTER!
**Creator:** Sightseeing Stan
**Focus:** Free plugins and tools that accelerate editing workflows in DaVinci Resolve

The video covers plugins that eliminate repetitive manual work -- keyframing, subtitle creation, zoom effects, animation, and audio placement. For Rayviews Lab, which edits 1-2 videos per week with a consistent template (voiceover + product images + B-roll + text overlays), speed gains compound significantly.

---

## 2. Plugin Inventory (Cross-Referenced with Multiple Sources)

### Tier 1 -- Directly Applicable to Rayviews Workflow

#### Magic Zoom (MrAlexTech) -- FREE
- **What it does:** Seamless zoom effects without keyframes or Dynamic Zoom setup
- **Download:** https://www.mralextech.com/magiczoomfree
- **Rayviews application:** Currently applying Dynamic Zoom manually per clip (see `resolve_editing_rules.md` Section 4A). MagicZoom could replace the manual green/red rectangle workflow with preset-based zoom. Apply zoom-in (3-5%) to all product images on V1 in bulk.
- **Speed gain:** Eliminates per-clip Inspector > Dynamic Zoom > Ease In and Out workflow. Estimated 15-20 minutes saved per video (16-19 product images per video).
- **Compatibility:** Works with DaVinci Resolve Free and Studio

#### Magic Animate V3 (MrAlexTech) -- FREE version available
- **What it does:** Preset animation system for transitions -- whip pans, spins, dissolves, bounces. No keyframing required.
- **Download:** https://www.mralextech.com/magicanimatev3-free
- **Paid version:** $29.99 with more presets
- **Rayviews application:** Pattern interrupt animations (Section 10 of resolve_editing_rules.md). Currently manual: "scale shift -- snap zoom 10-15% over 6 frames", "text slam -- key stat bounces in with slight overshoot". MagicAnimate can provide these as drag-and-drop presets.
- **Speed gain:** Pattern interrupts at every segment transition (5 products + reset = 6 transitions per video). 5-10 minutes saved per video.
- **Compatibility:** DaVinci Resolve Free and Studio

#### Magic Subtitle (MrAlexTech) -- FREE version (Studio only for PRO)
- **What it does:** AI-powered automatic caption generation with animated write-on text effects. Generates captions from Resolve's transcript or its own processing.
- **Download:** https://www.mralextech.com/magicsubtitlesprofree
- **Rayviews application:** Accessibility captions for the 40+/50+ audience who may watch with sound off or reduced hearing. Currently no auto-captioning in the pipeline. Adding captions increases watch time and accessibility.
- **Speed gain:** Manual captioning for a 10-minute video takes 60-90 minutes. Auto-generation: under 5 minutes + review.
- **Important:** PRO version requires DaVinci Resolve Studio. Free version may have limitations.
- **YouTube note:** YouTube auto-generates captions, but burnt-in animated subtitles increase engagement by 30-40% per multiple case studies.

#### Video Editor Studio: Free Starter Pack 2.0
- **What it does:** 150+ drag-and-drop elements including titles, gradients, lower thirds, and infographics
- **Download:** https://videoeditorstudio.com/
- **Rayviews application:** Lower thirds for product names, benefit callouts, rank badges. Currently using manual Text+ templates saved to Power Bins (Section 5 of resolve_editing_rules.md). This pack could provide polished pre-animated templates.
- **Speed gain:** Eliminates building overlay templates from scratch. 30-60 minutes saved during initial template setup.

### Tier 2 -- Useful Enhancements

#### Soundly: Place It
- **What it does:** Convolution-based audio environment emulation. Places dialogue in realistic spatial environments.
- **Download:** https://getsoundly.com/tools/
- **Rayviews application:** Limited. ElevenLabs TTS is studio-quality audio that doesn't need spatial processing. However, could be useful if adding ambient room tone to make TTS feel more natural and less "in a vacuum."
- **Consideration:** The 40+/50+ audience expects clean, clear voiceover. Spatial effects could reduce clarity. Use cautiously or skip.

#### Mononodes Tools (Magnifier, Crop, Tracked Image/Text)
- **What it does:** Precision editing utilities -- magnified zoom areas, crop tools, tracked text placement directly on Edit page (no Fusion required).
- **Download:** https://mononodes.com/tools/
- **Rayviews application:** Tracked text on product images (e.g., hovering benefit text that follows a product as it pans). Currently text overlays are static on V3. Tracked text adds professional polish.
- **Speed gain:** Avoids Fusion for simple tracking tasks. 5-10 minutes saved per tracked element.

#### Patrick Stirling Tracked Text Plugin
- **What it does:** Free tracked text preset for lightning-fast text following objects
- **Download:** https://stirlingsupply.co/products/tracked-text-plugin
- **Rayviews application:** Alternative to Mononodes for tracked text. Could attach benefit callouts to products during Ken Burns pan movements.

#### Paper Animator (MrJustinEdits)
- **What it does:** Paper-cut animation and stylization effects
- **Download:** https://mrjustinedits.com/en-eur
- **Rayviews application:** Limited for product review content. Could be used for intro/outro animations or channel branding elements.

#### Slow Shutter (MrJustinEdits)
- **What it does:** Motion trail and slow-shutter visual effects
- **Download:** https://mrjustinedits.com/en-eur
- **Rayviews application:** Not recommended. The 40+/50+ audience distrusts flashy effects (per video_production_strategy.md). Motion trails would conflict with the "trust and clarity" principle.

#### Asset Blaster
- **What it does:** Batch animation presets -- swipes, bounces, glitch effects, VHS effects. Centralized UI for rapid lower-third and overlay animation.
- **Download:** https://www.europeanfilmmaker.com/shop/p/asset-blaster
- **Rayviews application:** Quick animation for rank badges and benefit callouts on V3. Currently these appear with a simple cut; subtle bounce-in or swipe animation adds professionalism without being flashy.

### Tier 3 -- Infrastructure Tool

#### Reactor 3 (Package Manager)
- **What it does:** Community-built plugin manager for DaVinci Resolve. Install third-party content (scripts, fuses, macros, templates, titles) with one click inside Resolve.
- **Install:** Download from steakunderwater.com, drag .lua script into Fusion node graph. Access: Workspace > Scripts > Reactor > Open Reactor.
- **Rayviews application:** Gateway to hundreds of free Fusion macros and scripts. Essential infrastructure -- install this first, then browse for additional tools.
- **Compatibility:** Works with Resolve Free v15-v20+, Resolve Studio v15-v20+
- **Source:** https://gitlab.com/WeSuckLess/Reactor

---

## 3. Actionable Integration Plan for Rayviews Pipeline

### Phase 1: Install Foundation (30 minutes)

1. Install Reactor 3 package manager
2. Install MagicZoom Free
3. Install MagicAnimate V3 Free
4. Install Free Starter Pack 2.0

### Phase 2: Update Resolve Editing Workflow

#### Current workflow (resolve_editing_rules.md Section 13):
```
Step 8: Apply Dynamic Zoom (3-7%) to all static images on V1
Step 10: Add overlays on V3 from Power Bin templates
Step 12: 0.5s dissolve between segments
```

#### Updated workflow with plugins:
```
Step 8: Apply MagicZoom presets to all V1 images (bulk apply via paste attributes)
Step 10a: Drag Free Starter Pack lower thirds to V3 (customise text only)
Step 10b: Apply MagicAnimate bounce-in to benefit callouts
Step 12: Use MagicAnimate transition presets between segments
```

### Phase 3: Update Automation Guide

The `resolve_automation_guide.md` Python scripting section currently notes:
> "No keyframe creation via API" and "Dynamic Zoom rectangle control" as manual-only

With MagicZoom, the workaround is simpler: apply the OFX plugin effect via the API's `SetProperty()` method, or batch-apply via Paste Attributes after setting one clip.

### Phase 4: Caption Pipeline (Optional)

Add MagicSubtitle to the post-production workflow:
1. After voiceover placement on A1, run MagicSubtitle auto-generation
2. Review captions for accuracy (product names, technical terms)
3. Style captions to match channel typography (Montserrat/Inter)
4. Export with burnt-in captions for improved accessibility

---

## 4. DaVinci Resolve Editing Insights (Beyond Plugins)

### Color Grading for Product Images (40+/50+ Audience)

**Current spec** (resolve_editing_rules.md Section 7): 3-node chain -- Balance > Match > Look.

**Enhanced approach from research:**
- Use Rec.709 warm film-look LUTs (Kodak/Fujifilm emulation) for premium feel
- Free LUTs: chocolate/caramel toning adds warmth without being dramatic
- Avoid over-grading product photos (existing rule is correct)
- Apply free color grading toolkits: https://pixeltoolspost.com/pages/free-toolkit-for-davinci-resolve

**Product image rule (reinforced):** Keep products true to Amazon listing. Only match white balance and apply light warmth. Never color-shift the product itself.

**B-roll rule (enhanced):** All stock footage must be graded to match. Use Group Pre-Clip grading for clips from the same source. Film-look LUTs make stock footage feel less "stock."

### Python Scripting Automation Improvements

**GitHub reference project:** https://github.com/aman7mishra/DaVinci-Resolve-Python-Automation

Key methods available in the Resolve Python API:
- `CreateProject()` -- project creation
- `SetSetting()` -- resolution/framerate config
- `CreateEmptyTimeline()` -- timeline setup
- `AppendToTimeline()` -- sequential clip placement
- `AddRenderJob()` / `StartRendering()` -- headless render
- `SetCurrentRenderFormatAndCodec()` -- codec selection

**API documentation:** https://deric.github.io/DaVinciResolve-API-Docs/

**Limitation awareness:** The API only supports appending clips to timelines (no repositioning). Multi-track arrangement (V1-V4) still requires manual work or marker-guided placement.

### Dynamic Zoom Best Practices

Two methods for zoom in Resolve:
1. **Transform zoom** (Inspector > Zoom): Precise keyframe control, better for animated sequences
2. **Dynamic Zoom** (Inspector > Dynamic Zoom): Green/red rectangle system, better for Ken Burns on stills

For Rayviews:
- Use Dynamic Zoom for standard product images (3-7% zoom-in)
- Use Transform zoom for snap-zoom pattern interrupts (10-15% over 6 frames)
- MagicZoom plugin can replace both for common cases

### Text and Lower Thirds

Five methods for adding text in Resolve:
1. Text+ (Edit page, most flexible)
2. Fusion titles (animated, node-based)
3. Text effect (simple, fast)
4. Adjustment clip + text (apply to multiple clips)
5. Plugin-based (MagicSubtitle, Starter Pack templates)

For Rayviews: Text+ in Power Bins remains the fastest for templated content. Plugin-based lower thirds add animation polish without Fusion complexity.

---

## 5. Dzine AI Image Generation Insights

### Product Photography with Dzine

Dzine's AI product photography capabilities (from https://www.dzine.ai/tools/ai-product-photography/):
- Background removal and replacement
- Lighting adjustment automation
- Batch-consistent product imagery generation
- 3D and animated product showcases
- Scene generation from product reference images

**Current Rayviews workflow (dzine_rules.md):**
- Upload Amazon product reference image
- Generate hero, usage, detail, mood variants
- Maintain strict product preservation (10 rules)
- 6-section prompt structure

**Enhancement opportunities:**
1. **Batch consistency:** Use the same lighting prompt prefix across all products in a single video. Dzine outputs can vary in color temperature -- establish a "lighting anchor" prompt section.
2. **Z-Image tool** (https://www.dzine.ai/tools/z-image/): Text-to-image generation with high controllability. May produce more consistent results than the canvas Txt2Img mode.
3. **Generative Expand:** Use to convert 1:1 detail images to 16:9 when needed (8 credits per expansion, per dzine_playbook.md).

### Prompt Optimization for Product Videos

**What works (from broll_techniques.md + research):**
```
[product name] on [surface], soft overhead lighting, shallow depth of field,
product photography style, [material] texture, studio lighting, 4K
```

**Enhanced prompts for consistency:**
- Add "warm key light from 45 degrees left" to every hero prompt (creates consistent lighting direction)
- Add "neutral gray gradient background" for tech products (matches cinematic dark desk surface spec)
- Specify "no text, no labels, no watermarks" in every prompt (Dzine sometimes adds text)
- Use "professional product photography, 85mm lens, f/2.8" for consistent depth-of-field look

---

## 6. ElevenLabs TTS Best Practices

### Current Rayviews Config (elevenlabs_voice_profile.md):
- Voice: Thomas Louis (IHw7aBJxrIo1SxkG9px5)
- Model: eleven_multilingual_v2
- Stability: 0.50, Similarity: 0.75, Style: 0.00
- Target pace: 155 WPM

### Research Findings:

**Voice selection matters most.** Per ElevenLabs blog research:
1. Voice selection > model selection > settings tuning
2. Professional Voice Clones (PVCs) sound more natural than generic voices
3. Eleven V2 model gives best balance of quality and stability
4. Consistency across videos solidifies brand identity

**The current Rayviews setup already follows best practices:**
- Custom voice (Thomas Louis) = consistent brand identity
- Stability 0.50 = balanced between robotic and chaotic
- Fixed settings = consistency across videos
- 155 WPM = natural conversational pace for 40+/50+ audience

**Potential improvements:**
1. **Script formatting for TTS:** Add explicit pause markers `[pause]` between product segments. ElevenLabs respects SSML-like cues. Add a period + line break between sections for natural pauses.
2. **Emphasis markers:** Bold or capitalize key product names/verdicts in the script text. TTS models subtly emphasize capitalized words.
3. **Chunk boundaries:** Current 300-450 word chunks (per MEMORY.md). Ensure chunks never break mid-sentence or mid-product-name. Break at natural section boundaries.

---

## 7. YouTube Channel Growth for 40+/50+ Amazon Shoppers

### Content Format Optimization

**What works for this demographic (from research):**
- Top 5 / Best Of lists (high search volume, buyer intent)
- Product comparisons with clear rankings
- Evidence-based recommendations (trust signals)
- Calm, informative tone (not hype)
- Practical demonstrations over flashy editing

**Rayviews already aligns with these principles.** The video_production_strategy.md correctly identifies:
> "Values clarity over style. Prefers practical demonstration. Distrusts flashy or over-edited content."

### Video Description Optimization

**Best practices for Amazon affiliate YouTube descriptions:**
1. **First 2 lines:** Keywords + value promise (above the fold)
2. **Affiliate links:** Place in top section with clear labels
3. **Timestamps/chapters:** Add for every product section (helps YouTube algorithm)
4. **Disclosure:** "As an Amazon Associate I earn from qualifying purchases" at top
5. **Pinned comment:** Duplicate the top affiliate links in a pinned comment

**Example description template:**
```
Best [Category] 2026 -- Top 5 Picks Ranked

As an Amazon Associate I earn from qualifying purchases.

[Product #1 Name]: [amzn.to link]
[Product #2 Name]: [amzn.to link]
...

TIMESTAMPS
0:00 Introduction
0:25 #5 [Product Name]
1:55 #4 [Product Name]
3:25 #3 [Product Name]
4:55 Why These Rankings
5:30 #2 [Product Name]
7:00 #1 [Product Name]
9:00 Final Verdict

Research sources: Wirecutter, RTINGS, PCMag
```

### Thumbnail Strategy

**For 40+/50+ audience:**
- High contrast, readable text at small sizes
- Product as hero (70% of frame, per dzine_rules.md)
- 2-3 word overlay max ("BEST 2026" or "#1 PICK")
- Avoid cluttered compositions
- Test text readability at 200px width (YouTube mobile search)

### Click-Through Rate (CTR) Optimization

- Hyperlink images in descriptions (not just text links)
- Clear product labels next to each link
- Add call-to-action at end of video: "Links are in the description below"
- Verbal mention of links 2-3 times during video (not just once at end)

---

## 8. Amazon Affiliate Conversion Optimization

### Link Placement Strategy

1. **Description:** All 5 products with clear labels + amzn.to short links
2. **Pinned comment:** Top 3 products (reduces scroll abandonment)
3. **Verbal CTA:** Mention "check the links below" after each product segment
4. **On-screen CTA:** Brief "Link in description" overlay during verdict moments

### Conversion Rate Best Practices

- **Target buying intent:** Use titles like "Best X for [specific use case]" rather than generic "Top 5 X"
- **Address objections:** Each product segment should acknowledge the downside (builds trust, per script_rules.md)
- **Price anchoring:** Mention price range in the intro to qualify viewers early
- **Urgency without hype:** "These are the current best picks based on expert testing" (not "LIMITED TIME!")

### Compliance Reminders (Amazon Associates TOS)

- Always disclose affiliate relationships (on-screen + description)
- Never show fake prices, discounts, or availability badges
- Never imply Amazon endorsement
- Use SiteStripe amzn.to short links (not direct product URLs with ?tag= when possible)
- Current pipeline handles this via QA gates and dzine_rules.md compliance section

---

## 9. Automation Opportunities Identified

### New Automations Enabled by Free Plugins

| Task | Current Method | Plugin Method | Time Saved |
|------|---------------|---------------|------------|
| Zoom on product images | Manual Dynamic Zoom per clip | MagicZoom bulk apply | 15-20 min |
| Segment transitions | Manual dissolve + snap zoom | MagicAnimate presets | 5-10 min |
| Benefit callout animation | Static text cut-in | MagicAnimate bounce-in | 5-10 min |
| Lower thirds | Power Bin templates | Free Starter Pack 2.0 | 10-15 min (setup) |
| Captions | None (YouTube auto) | MagicSubtitle burnt-in | 60-90 min (new feature) |
| Plugin discovery | Manual search | Reactor package manager | Ongoing |

**Estimated total time saved per video: 35-55 minutes** (plus caption capability as new feature)

### DaVinci Resolve Python API Enhancements

The current `resolve_automation_guide.md` can be extended with:

1. **OFX plugin parameter setting:** After installing MagicZoom, the Python API may allow setting its parameters via `SetProperty()` on timeline items.
2. **Fusion comp import:** Pre-build MagicAnimate transition comps as `.comp` files, import via `ImportFusionComp()` API call.
3. **Render automation:** Current headless mode (`-nogui`) works for batch rendering. Add to the pipeline as a `render` stage after `edit_prep`.

### Dzine Batch Generation Consistency

New approach for consistent product imagery:
1. Define a "lighting anchor" prompt block per video (consistent across all 5 products)
2. Generate all hero shots first, then all usage shots, then all details (same-type batching = more consistent style)
3. Use Dzine's Enhance & Upscale (9 credits) on the best images to reach 4K for YouTube 4K upload trick

---

## 10. Competitive Intelligence

### What Top Product Review Channels Do (from resolve_editing_rules.md Section 11)

| Channel | Technique | Rayviews Adaptation |
|---------|-----------|-------------------|
| MrWhoseTheBoss | Blur-BG, text slams, 3-5s cuts | Already in spec. Plugin-based text slams via MagicAnimate would match quality. |
| MKBHD | Minimal, product-as-hero, color consistency | Already aligned. Enhance with consistent film-look LUT across all products. |
| Project Farm | Evidence-first, data visualization | Already aligned via research_agent.py evidence pipeline. Add on-screen data tables. |
| Linus Tech Tips | Fast B-roll, aggressive zooms, SFX timing | B-roll density already specified. MagicZoom can add variety to zoom patterns. |

### Faceless Channel Market Dynamics

Research shows faceless Amazon affiliate channels are growing:
- One ElevenLabs user: 6k subscribers and ~8 million views in 3 months
- Product review videos target users with buying intent = higher conversion rates
- Faceless channels trade personality for privacy and lower costs
- Winning formats: product reviews, top-10/top-5 lists, comparisons
- Monetizable before YouTube Partner Program (1,000 subs / 4,000 watch hours) via affiliate links

---

## 11. Action Items Summary

### Immediate (This Week)

- [ ] Install Reactor 3 package manager in DaVinci Resolve
- [ ] Install MagicZoom Free, MagicAnimate V3 Free, Free Starter Pack 2.0
- [ ] Test MagicZoom on existing product images -- compare to manual Dynamic Zoom
- [ ] Test MagicAnimate transition presets for segment transitions

### Short-Term (This Month)

- [ ] Update `resolve_editing_rules.md` Section 4A with MagicZoom workflow
- [ ] Update `resolve_editing_rules.md` Section 10 with MagicAnimate pattern interrupts
- [ ] Create new Power Bin templates from Free Starter Pack 2.0 lower thirds
- [ ] Add video description template to pipeline (timestamps + affiliate links format)
- [ ] Test MagicSubtitle for caption generation on one video

### Medium-Term (Next Month)

- [ ] Explore Reactor library for additional free Fusion macros
- [ ] Test Mononodes tracked text for benefit callouts that follow product pans
- [ ] Add free film-look LUT to color grading workflow (Node 3: Look)
- [ ] Update `resolve_automation_guide.md` with plugin-aware Python scripting
- [ ] Add pinned comment strategy to YouTube upload checklist

### Long-Term (Pipeline Enhancement)

- [ ] Integrate MagicSubtitle into the pipeline as a post-TTS automation step
- [ ] Develop consistent "lighting anchor" prompt system for Dzine batch generation
- [ ] Explore 4K upscale workflow (Dzine Enhance + Resolve Super Scale) for YouTube quality boost
- [ ] Build pre-configured Fusion comps for all overlay types (rank badge, benefit callout, disclosure)

---

## Sources

### Video and Channel
- [Original Video](https://www.youtube.com/watch?v=DX0O9S0-ubI) -- Sightseeing Stan
- [Sightseeing Stan Channel](https://www.youtube.com/@SightseeingStan)

### Plugin Resources
- [MagicZoom Free](https://www.mralextech.com/magiczoomfree)
- [MagicAnimate V3](https://www.mralextech.com/magicanimate)
- [MagicSubtitles Pro/Free](https://www.mralextech.com/magicsubtitlesprofree)
- [MrAlexTech Free Plugins](https://www.mralextech.com/freeresolveplugins)
- [Free Starter Pack 2.0](https://videoeditorstudio.com/)
- [Mononodes Tools](https://mononodes.com/tools/)
- [Stirling Supply Tracked Text](https://stirlingsupply.co/products/tracked-text-plugin)
- [MrJustinEdits](https://mrjustinedits.com/en-eur)
- [Reactor 3 (GitLab)](https://gitlab.com/WeSuckLess/Reactor)
- [Reactor Install Guide](https://creativevideotips.com/tutorials/install-fusion-reactor-for-resolve)

### DaVinci Resolve Resources
- [Resolve Python API Docs](https://deric.github.io/DaVinciResolve-API-Docs/)
- [Resolve Scripting API v20.3](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8)
- [Python Automation GitHub](https://github.com/aman7mishra/DaVinci-Resolve-Python-Automation)
- [Free Color Grading Toolkit](https://pixeltoolspost.com/pages/free-toolkit-for-davinci-resolve)
- [Free DaVinci Resolve LUTs](https://fixthephoto.com/davinci-resolve-luts)
- [Blackmagic Official Training](https://www.blackmagicdesign.com/products/davinciresolve/training)
- [Best Free Plugins 2026](https://www.miracamp.com/learn/davinci-resolve/best-plugins)
- [Free Effects for Resolve 19](https://easyedit.pro/blog/best-free-effects-templates-and-plugins-made-for-da-vinci-resolve-19)

### Dzine AI
- [Dzine AI Platform](https://www.dzine.ai/)
- [Dzine Product Photography](https://www.dzine.ai/tools/ai-product-photography/)
- [Dzine Z-Image Generator](https://www.dzine.ai/tools/z-image/)
- [Dzine AI Review](https://www.unite.ai/dzine-review/)

### ElevenLabs
- [ElevenLabs YouTube Voices](https://elevenlabs.io/blog/the-5-best-ai-voices-for-youtube-automation-and-faceless-videos)
- [ElevenLabs YouTube Use Cases](https://elevenlabs.io/use-cases/youtube)
- [ElevenLabs Review 2026](https://nerdynav.com/elevenlabs-review/)

### YouTube and Affiliate Marketing
- [YouTube Affiliate Marketing Guide (AAWP)](https://getaawp.com/blog/youtube-affiliate-marketing/)
- [Amazon Affiliate for YouTube (TubeBuddy)](https://www.tubebuddy.com/blog/amazon-affiliate-for-youtube/)
- [YouTube Channel Growth Guide 2025](https://onewrk.com/youtube-channel-growth-guide-2025/)
- [Faceless Channel Ideas (ClickBank)](https://www.clickbank.com/blog/faceless-youtube-channel-ideas/)
- [Amazon Affiliate Marketing Tips (Flintzy)](https://www.flintzy.com/blog/a-guide-to-amazon-affiliate-marketing-for-youtube-creators/)
- [Free Templates (Mixkit)](https://mixkit.co/free-davinci-resolve-templates/)
- [Free Templates (Envato)](https://elements.envato.com/video-templates/compatible-with-davinci-resolve)
