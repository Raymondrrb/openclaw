# Dzine Model Selection & Prompt Engineering Guide

Compiled from web research (Feb 2026) + hands-on exploration (Phases 91-152) + deep research (Feb 13 2026) + official Dzine video studies (Zvw0Fk9FVl4, _2IGR79NNF0, f4HcdR3cd4M).

---

## CRITICAL: Seedream 5.0 vs 4.5 for Product Photography

**Seedream 5.0 prioritizes intelligence/reasoning over visual aesthetics.** Despite marketing as 9.5/10 photorealism, independent reviews found:
- AI texture is more obvious in 5.0 than 4.5
- Human anatomy errors are more common
- Text rendering is unstable (3.0 was better for typography)
- Material textures (metal, fabric, wood) feel flatter than 4.5
- 5.0's strengths: web search integration, knowledge-based imagery, example-based editing

**For product review thumbnails and product shots: use Seedream 4.5, not 5.0.**
Seedream 4.5 delivers superior photorealism, material textures, and editing precision.

Use 5.0 only for: knowledge-based imagery, batch transformations via example-based editing, or when web search is needed.

---

## Model Selection Matrix for Product Photography

### Tier 1: Best for Product Images

| Model | Photorealism | Speed | Text Accuracy | Best For | Credits |
|-------|-------------|-------|---------------|----------|---------|
| Seedream 4.5 | 9/10 | ~10s | Good | Product photography, material rendering | 4 (Normal) |
| Realistic Product | High | ~30s | N/A | Studio product shots | 4 (Normal) |
| Dzine Realistic v3 | High | ~30s | N/A | Realistic generation | 4 (Normal) |

### Tier 2: Versatile / Fast

| Model | Photorealism | Speed | Text Accuracy | Best For | Credits |
|-------|-------------|-------|---------------|----------|---------|
| Nano Banana Pro | 7.8/10 | 12-20s | Excellent | Text-heavy, versatile, e-commerce, HEX colors | 4 (Normal) |
| Seedream 5.0 | 7.5/10* | 8-15s | Unstable | Reasoning, example-based editing, web search | TBD |
| GPT Image 1.5 | Good | Varies | Good | Budget, varied styles | 20 (Chat) |
| FLUX.2 Pro | Very Good | 5-10s | Excellent | Ultra-high-res, batch | 4 (Normal) |
| Z-Image Turbo | Good | 3-6s | Good | Rapid prototyping/testing | 2 (Fast?) |

*Seedream 5.0 photorealism is marketed as 9.5/10 but real-world product photography tests show flatter textures and more AI artifacts than 4.5.

### Tier 3: Specialized

| Model | Use Case |
|-------|----------|
| Midjourney | Artistic, stylized |
| Dzine General | All-purpose default |
| Google Imagen 4 | Google's model |
| Ideogram 3.0 | Text/logo generation |
| Qwen Image | Alibaba model |

### Official Dzine Model Comparison (from video Zvw0Fk9FVl4)

Head-to-head category winners across all major Dzine image models:

| Category | Winner | Notes |
|----------|--------|-------|
| Emotion / Portraits | MidJourney V7 | Best emotional depth and facial expressions |
| Image Editing | MidJourney V7 | Most accurate inpainting and modifications |
| Infographics / Text Accuracy | Nano Banana Pro | Cleanest text rendering in complex layouts |
| Context Understanding | Nano Banana Pro | Best at interpreting complex multi-element prompts |
| Character Consistency | Nano Banana Pro | Most reliable across multiple generations |
| Photorealism | Nano Banana Pro | Best overall realism (product photography) |
| Landscapes | Dzine Realistic V3 | Superior natural scenery and environments |
| Character Sheets | Seedream 4.5 | Best multi-pose reference sheet generation |
| Movie Posters with Text | Flux 2 Pro | Best text integration in cinematic compositions |
| Overall (no single winner) | GPT Image 1.5 | Good across categories but never #1 |

**Key takeaway for Rayviews pipeline:** Nano Banana Pro wins 4 of the most important categories for product review content (text accuracy, context understanding, character consistency, photorealism). This validates the user directive to use Nano Banana Pro as the default model.

### Recommendation for Rayviews Pipeline

**USER DIRECTIVE: Always use Nano Banana Pro for ALL image generation. Unlimited credits — never economize.**
**VIDEO: Use Wan 2.1 (6cr) while learning. Production target: Seedance 2.0.**

| Asset Type | Primary Model | Fallback |
|-----------|---------------|----------|
| Product hero | **Nano Banana Pro** | Seedream 4.5 |
| Product usage | **Nano Banana Pro** | Dzine Realistic v3 |
| Product detail | **Nano Banana Pro** | Seedream 4.5 |
| Product mood | **Nano Banana Pro** | Dzine Realistic v3 |
| Thumbnail | **Nano Banana Pro** | Seedream 4.5 |
| Background | **Nano Banana Pro** | Dzine General |
| Avatar (Ray) | CC mode (any) | Dzine Realistic v3 |
| Product faithful | BG Remove + Expand (not model-dependent) | - |
| Prompt testing | **Nano Banana Pro Fast** (2cr, unlimited) | Z-Image Turbo |
| Video (learning) | Wan 2.1 (6cr) | Dzine Video V1 (10cr) |
| Video (production) | **Minimax Hailuo 2.3** (56-98cr) | Seedance Pro (25-120cr) |

---

## Negative Prompts (Img2Img Only)

Img2Img Advanced section has a dedicated **Negative Prompt** textarea (1800 chars). Txt2Img does NOT have negative prompt — only Seed.

Common negative prompts for product photography:
```
no text, no watermarks, no people, no hands, blurry, low quality, distorted, deformed, oversaturated, grain, noise
```

---

## Prompt Engineering

### Universal Structure

```
[Image type] + [Subject] + [Background/Setting] + [Lighting] + [Camera/Technical] + [Mood/Style] + [Restrictions]
```

AI prioritizes first few words. Lead with image type and subject.

### Product Photography Patterns

**Studio White Background (e-commerce):**
```
Professional product photograph of {product_name} on a pure white seamless background.
Studio lighting with soft, even illumination eliminating harsh shadows.
Product positioned at slight 30-degree angle showing dimension.
Sharp focus, color accurate, high resolution, commercial grade.
No additional objects, no text, no watermarks.
```

**Cinematic Hero:**
```
{product_name} on dark matte desk surface, premium studio environment.
Dramatic key light from upper left, subtle rim light on product edges.
85mm equivalent, shallow depth of field, product razor-sharp.
Background softly blurred with bokeh. High-end commercial photography.
```

**Lifestyle Context:**
```
{product_name} on modern desk setup with subtle neon ambient glow.
Soft key light with colored ambient accents, subtle rim light.
50mm equivalent, medium shot, product in natural context.
Modern tech lifestyle, creative workspace feel.
```

### Technical Terms Models Understand

- Camera: "85mm lens", "f/1.8 aperture", "macro photography", "shallow depth of field"
- Lighting: "golden hour backlighting", "rim light", "three-point studio lighting", "soft key light", "high-key lighting"
- Materials: "brushed metal", "matte finish", "glossy surface", "velvet texture"
- Composition: "rule of thirds", "centered product", "three-quarter view"
- Quality: "8k resolution", "commercial grade", "product photography", "studio shot"

### Prompt Optimization Tips

1. Use full sentences, not keyword lists (better for 2026 models)
2. Test with Z-Image Turbo (3-6s) before premium model (8-15s)
3. Generate multiple times — official Dzine tip
4. Prompt Improver toggle (OFF by default) — auto-enhances your prompt
5. Structure Match slider for Img2Img — 0.6 for character scenes (Face Match ON). **WARNING: Img2Img does NOT preserve product identity** even at 98% Structure Match — use BG Remove + Generative Expand (SOP 5) for product-faithful images

---

## Style Catalog (P152+P163 confirmed — 79 styles)

### Categories (17 total)
Favorites, My Styles, Recent, All styles, General, Realistic, Illustration, Portrait, 3D, Anime, Line Art, Material Art, Logo & Icon, Character, Scene, Interior, Tattoo, Legacy

### Complete Style List (in picker order)

**Generation Models (Row 1-3):**
Dzine General, Dzine 3D Render v2, Dzine Realistic v3, Dzine Realistic v2, Realistic, FLUX.1, GPT Image 1.5, Z-Image Turbo, Seedream 4.5, FLUX.2 Pro, FLUX.2 Flex, Nano Banana Pro, Midjourney, Nano Banana, Seedream 4.0, GPT Image 1.0, Google Imagen 4, Ideogram 3.0, Seedream 3.0, Qwen Image

**Product-Specific:**
Realistic Product

**Artistic Styles (59 total):**
Warm Fables, Impasto Comics, Film Narrative, Metallic Fluid, Battlecraft, Monotone Vogue, Retro Sticker, Playful Enamel, Graffiti Splash, Classic Dotwork, Colorful Felt, Bold Collage, Line & Wash, Luminous Narratives, Piece of Holiday, 3D Pixel, Arcane Elegance, Retro Sci-Fi, Impressionist, Furry, Shimmering Glow, Impressionist Harmony, Minimalist Cutesy, Y2k Games, Elegant B&W, Simplified Scenic, Memphis Illustration, Neo-Digitalism, Neo-Tokyo Noir, Glass World, Miniatures, Bold Linework, B&W Drawing, Paper Cutout, Floral Tattoo, Vintage Engraving, Color Block Chic, Nouveau Classic, Mystical Escape, Cheerful Storybook, Fantasy Hero, Soft Radiance, Bedtime Story, Ceramic Lifelike, Retro Radiance, Luminous Portraiture, Tiny World, Illustrated Drama, Neon Futurism, Narrative Chromatism, Romantic Nostalgia, Rubber Hose Classic, Linear Cartoon, Impasto Realms, Line Scape, Sleek Simplicity, Retro Noir Chromatics, The End

### Custom Style Creation

**Quick Style:** "Instantly swap a style from one reference image in seconds" — upload 1 reference, applies style transfer instantly.

**Pro Style:** "Carefully learn a style from reference images in minutes" — dialog: Style Name input (placeholder "e.g. Morden Simplicity"), upload 3-10 images, Training Guide link, Cancel/Train buttons. Requires training time.

---

## Video Model Catalog (P170 confirmed, 36+ models)

Complete catalog from model selector popup, sorted by credits (cheapest first):

| Model | Credits | Duration | Resolution | Tags |
|-------|---------|----------|------------|------|
| Wan 2.1 | 6 | 5s | 720p | Uncensored |
| Seedance Pro Fast | 7-35 | 5s | — | Uncensored |
| Wan 2.5 | 7-21 | /s | 1080p | Uncensored |
| Dzine Video V1 | 10 | 5s | — | Uncensored |
| Seedance 1.5 Pro | 12-56 | 5s | — | Uncensored |
| Wan 2.6 | 14-21 | /s | 1080p | Uncensored |
| Seedance Lite | 15-80 | 5s | 1080p | — |
| Dzine Video V2 | 20 | 5s | — | Uncensored |
| Wan 2.2 Flash | 20-50 | 5s | — | — |
| Seedance Pro | 25-120 | 5s | 1080p | Uncensored |
| Motion Control (Kling 2.6) | 28 | 3-30s | 1080p | — |
| Video Editor (Runway Gen4) | 30 | 1-5s | 720p | — |
| Kling 2.5 Turbo STD | 30 | 5s | 720p | — |
| Kling 2.1 Std | 37 | 5s | — | — |
| Kling 1.6 standard | 37 | 5s | — | — |
| Luma Ray 2 flash | 45 | 5s | — | — |
| Runway Gen4 turbo | 46 | 5s | — | — |
| Wan 2.2 | 50-100 | 5s | — | Uncensored |
| PixVerse V5 | 50 | 5s | 1080p | — |
| Minimax Hailuo 2.3 | 56-98 | 6s | — | Uncensored |
| Minimax Hailuo 02 | 56-98 | 6s | 1080p | — |
| Minimax Hailuo | 56 | 6s | — | — |
| Kling 2.5 Turbo Pro | 65 | 5s | 1080p | — |
| Kling 2.1 Pro | 75 | 5s | 1080p | — |
| Kling 1.6 pro | 75 | 5s | 1080p | — |
| Kling 2.6 | 85-170 | 5s | 1080p | — |
| AI Video Reference (Vidu Q1) | 85 | 5s | 1080p | — |
| Sora 2 | 100 | 4s | — | — |
| Kling 3.0 | 126-168 | 5s | 1080p | — |
| Kling Video O1 | 140 | 5s | 1080p | — |
| Luma Ray 2 | 146 | 5s | — | — |
| Google Veo 3.1 Fast | 200-304 | 8s | 1080p | — |
| Kling 2.1 Master | 215 | 5s | 1080p | — |
| Google Veo 3 Fast | 225 | 8s | — | — |
| Sora 2 Pro | 300-500 | 4s | 1080p | — |
| Google Veo 3.1 | 400-800 | 8s | 1080p | — |
| Google Veo 3 | 600 | 8s | — | — |

### Video Model Quick Reference — Credit Tiers (from video _2IGR79NNF0)

Budget tier (testing/learning):
- Wan 2.1: 6 credits/5s (Uncensored) -- cheapest option
- Seedance Pro Fast: 7-35 credits/5s
- Seedance Lite: 15-80 credits/5s (1080p)

Mid tier (production candidates):
- Wan 2.2 Flash: 26-52 credits/5s -- good balance of cost and quality
- Kling 2.5 Turbo STD: 30 credits/5s
- Minimax Hailuo 02: 15-30 credits/4s (1080p) -- older Hailuo, cheaper
- Kling 2.1 Std: 43 credits/5s
- Luma Ray 2 Flash: 41 credits/5s

High tier (premium quality):
- Minimax Hailuo 2.3: 56-98 credits/6s (Uncensored) -- **current production model**
- Kling 2.1 Pro: 90 credits/5s (1080p)
- Kling 2.1 Master: 215 credits/5s (1080p) -- highest Kling quality

Ultra tier (special use only):
- Sora 2 Pro: 300-500 credits/4s (1080p)
- Google Veo 3.1: 400-800 credits/8s (1080p)
- Google Veo 3: 600 credits/8s

### Camera Motion Presets (14 types, max 3 combinations per clip)
Truck (L/R), Pan (L/R), Dolly (In/Out), Pedestal (Up/Down), Tilt (Up/Down), Zoom (In/Out), Arc (L/R)

---

## Video Models for Product Showcases

### Seedance 2.0 (Primary — for product B-roll)

**Release: February 24, 2026** — not yet available on Dzine canvas.

| Parameter | Value |
|-----------|-------|
| Duration | 4-15 seconds |
| Resolution | 2K native |
| Aspect Ratios | 16:9, 4:3, 1:1, 3:4, 9:16 |
| Audio | Native sync supported |
| Input limits | 30MB/image, 50MB/video, 15MB/audio. Up to 9 images + 3 videos + 3 audio |
| Credits | **Disputed**: early docs say ~6-8, third-party refs say 180-240. Verify on launch. |

**Strengths:** Preserves logos/packaging/color grading. @mention reference system (`@Image1 for appearance, @Video1 for camera motion`). Camera orbit support ("camera orbits around the product").

**Weaknesses:** Water/liquid is inconsistent. Max 15s. Not as physics-realistic as Sora 2.

### Kling 3.0 (Alternative — for brand-visible product B-roll)

| Parameter | Value |
|-----------|-------|
| Duration | 3-15 seconds (user-selectable) |
| Resolution | Native 4K |
| Credits on Dzine | 126-168 |
| Multi-shot | Up to 6 camera cuts per generation |
| Audio | Multi-language sync + 3-person dialogue |
| Text rendering | Precise logos and titles |

**Use when:** Product shots require legible brand names/logos. At 126-168 credits, may be more cost-effective than Seedance 2.0 (180-240) for high-fidelity product B-roll.

### Wan 2.6 (Secondary — for multi-shot consistency)

| Parameter | Value |
|-----------|-------|
| Duration | 2-6 seconds |
| Resolution | 480p (100cr), 720p (200cr), 1080p Ultra (300cr) |
| Multi-shot | Yes — maintains consistency across shots |
| Reference video | Yes — match existing style/motion |

**Use when:** Multiple angles of same product in sequence with matching visual style.

### Budget-Tier (for testing)

| Model | Credits | Duration | Use Case |
|-------|---------|----------|----------|
| Wan 2.1 | 6 | 5s | Cheapest test clips |
| Seedance Pro Fast | 7-35 | 5s | Fast draft |
| Dzine Video V1 | 10 | 5s | Basic video |

---

## Face Match & Consistent Character

### Face Match (for style transforms preserving identity)

1. Start Image-to-Image project
2. Upload reference image
3. **Enable "Face Match"** in generation settings
4. Select style + write prompt
5. Adjust style intensity slider
6. Generate — AI preserves facial identity while applying style

### Consistent Character (for recurring Ray across videos)

**Image-based training (recommended):**
1. Click "Build Your Character" > "Start with Images"
2. Upload 4-30 photos from different angles (high-res, clear face, varied angles)
3. Name character, begin training
4. After training, include name in any prompt

**Key rules:**
- Keep descriptions consistent across generations
- Can change clothing/environment, NOT inherent features
- Do NOT remove style keywords — they anchor identity
- Fast Mode for previews, HQ Mode for final
- Lasso selections slightly larger than actual area
- Advanced CC Training requires Master plan ($59.99/mo)

### Generation Modes

| Mode | Quality | Credits | Use For |
|------|---------|---------|---------|
| Fast | Lower precision | Fewer | Testing/preview |
| Normal | Balanced | Standard | Most work |
| HQ | Highest accuracy | Most | Final output |

---

## Product Background Tool

AI tool that removes existing background and replaces with generated or template background, adjusting lighting/shadows for realistic compositing.

### Workflow
1. Upload product image
2. Browse template categories (sleek/modern, studio, outdoor, etc.) OR write custom prompt
3. AI removes background, composites product, adjusts lighting/shadows
4. Download result

### Key Features
- Custom prompt backgrounds (beyond templates)
- Automatic lighting/shadow adjustment (not just background swap)
- Batch processing for consistent treatment across all 5 products

### When to Use
- Consistent product-on-background shots for video segments
- Lifestyle context shots from Amazon images
- Batch processing with unified visual treatment

### When to Avoid
- Pixel-perfect accuracy needed for tiny details (AI can blur fine edges)
- Complex transparent elements (glass bottles, clear cases)

---

## Credit System

### Plans (Feb 2026)

| Plan | Price | Image Credits | Video Credits | Concurrent Jobs |
|------|-------|--------------|---------------|-----------------|
| Free | $0 | 32 regular/day | None | Limited |
| Beginner | $8.99/mo | 900 fast/mo | Limited | 1 image |
| Creator | $19.99/mo | 3,000 fast + unlimited regular | 3,000 (~500 videos) | 5 image, 3 video |
| Master | $59.99/mo | Unlimited fast | 9,000 (~1,500 videos) | 12 image |

**Current plan: Master** ($59.99/mo) — unlimited image credits, 9,000 video credits.

### Per-Operation Costs

| Operation | Credits |
|-----------|---------|
| Txt2Img | 4-20 |
| Consistent Character | 4 |
| Img2Img | 20 |
| Chat Editor | 20 |
| Insert Object | 4 |
| Generative Expand | 8 |
| Hand/Face Repair | 4 |
| Face Swap | 4 |
| Enhance & Upscale | 9 |
| AI Video (Key Frame) | 56 |
| AI Video (Reference) | 85 |
| Motion Control | 28 |
| Lip Sync | 36 |

### Header Display
- **Image credits**: shown as "Unlimited" in header
- **Video credits**: shown as decimal (e.g. "8.850") in header
- **Both at (y=17)** in span.txt class in header bar

---

## API Status

### Dzine Native API
Dzine has an API page at `dzine.ai/api/` but endpoints are **not yet publicly documented**. When available, this would replace Playwright automation. For now, browser automation via CDP is the only option.

### 1min.ai API Wrapper (Fallback for Img2Img)
Working third-party API that wraps Dzine for image generation:
- **Endpoint:** `POST https://api.1min.ai/api/features` with `API-KEY` header
- **Styles:** `GET https://api.1min.ai/api/dzine/styles` returns 200+ styles with `style_code`
- **Parameters:** `style_code`, `style_intensity` (0-1), `structure_match` (0-1), `color_match`, `face_match`, `seed`, `output_format`
- **Limitations:** Img2Img/style-transfer only (no Txt2Img, no CC, no video). Separate pricing. S3 presigned URLs expire in 7 days.
- **Use case:** Fallback when browser automation fails for style transfer operations.

---

## Sources

- [Seedream 5.0 Review](https://www.dzine.ai/blog/seedream-5-0-review/)
- [Seedream 5.0 Preview Guide (WaveSpeed)](https://wavespeed.ai/blog/posts/seedream-5-0-preview-complete-guide-intelligent-image-generation/)
- [Seedream 5.0 Review (SeaArt)](https://www.seaart.ai/blog/seedream-5-0-review)
- [Seedream 4.5 Common Errors](https://z-image.ai/blog/seedream-4-5-errors-2026)
- [Seedream 4.5 vs Nano Banana Pro](https://www.dzine.ai/blog/seedream-4-5-vs-nano-banana-pro/)
- [Nano Banana Pro vs Flux.2](https://www.dzine.ai/blog/flux-2-vs-nano-banana-pro/)
- [Model Comparison](https://wavespeed.ai/blog/posts/seedream-5-0-vs-nano-banana-pro-gpt-image-flux-klein-qwen-image-comparison-2026/)
- [AI Product Photography](https://www.dzine.ai/tools/ai-product-photography/)
- [AI Product Background Generator](https://www.dzine.ai/tools/ai-product-background-generator/)
- [Consistent Character Guide](https://www.dzine.ai/blog/ultimate-guide-to-creating-consistent-characters-with-ai-2/)
- [OpenArt vs Dzine CC](https://www.animationandvideo.com/2025/07/openart-versus-dzine-ai-consistent.html)
- [Seedance 2.0 Guide](https://www.dzine.ai/blog/seedance-2-0-guide/)
- [Seedance 1.5 Pro vs Wan 2.6](https://www.seaart.ai/blog/seedance-15-pro-vs-wan-26-review)
- [Dzine Pricing](https://www.dzine.ai/pricing/)
- [Dzine AI Review (TechFixAI)](https://techfixai.com/dzine-ai-review/)
- [Dzine AI Review (AIChief)](https://aichief.com/ai-productivity-tools/dzine-ai/)
- [Dzine Official Model Comparison (YouTube Zvw0Fk9FVl4)](https://www.youtube.com/watch?v=Zvw0Fk9FVl4)
- [Dzine AI Video Model Catalog (YouTube _2IGR79NNF0)](https://www.youtube.com/watch?v=_2IGR79NNF0)
- [Consistent Character Sheets in Nano Banana (YouTube f4HcdR3cd4M)](https://www.youtube.com/watch?v=f4HcdR3cd4M)
