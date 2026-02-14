# Cinematic Product B-Roll Techniques — Rayviews Pipeline

Source: Tava Kessler tutorial study + cross-referenced best practices.

## Dzine AI Prompt Guidelines

### Lighting
- Soft overhead lighting with minimal harsh shadows (standard for product shots)
- Rim/backlighting for depth separation — subtle edge light creates cinematic halo
- Specify product material in prompts: glass (transparency/refraction), metals (reflections), fabrics (texture/draping)

### Composition
- **Close-up detail shots** — zoomed in on key features (buttons, textures, logos)
- **3/4 angle hero shots** — slightly above and to the side (standard product angle)
- **Clean backgrounds** — solid colors, gradients, or lifestyle surfaces (marble, wood, fabric)
- **Shallow depth of field** — blurred background, sharp product = most "cinematic" quality

### Prompt Template
```
[product name] on [surface], soft overhead lighting, shallow depth of field, product photography style, [material] texture, studio lighting, 4K
```

## Shot Variety Per Product (Dzine Generation)

For each of the 5 products, generate:
1. **Hero/establishing shot** — full product, clean background (Txt2Img NBP 4K)
2. **Detail/close-up shots** (1-2) — key features mentioned in script
3. **Lifestyle/context shot** — product in use or natural environment

Total: 15-20 images per 5-product video.

## DaVinci Resolve Edit Rules

### Simulating Camera Movement on Stills
- **Ken Burns effect** — 3-7% zoom (per existing spec), slow pan alternating L/R
- **Vertical dolly** — start close on detail, slowly zoom out to reveal full product
- **Overhead to 3/4 transitions** — cut between different Dzine-generated angles

### Color Grading
- Node-based grading — apply consistent cinematic look across all product shots
- Rec.709 film look LUTs (Kodak/Fujifilm) — warm, premium feel for 40+/50+ audience
- **Group grading** — grade one shot, apply to all similar shots for consistency
- Color-correct AI images to match each other (Dzine outputs can vary in color temp)

### Edit Timing
- 3-6 second holds (matches existing spec)
- Simple cross-dissolves or straight cuts — no flashy transitions
- Hold hero shots 4-6s during key benefit callouts in voiceover

## Visual Storytelling Structure
- Open with most visually striking product or category establishing image
- Each product segment has visual variety (different angles across 5 products)
- Close with #1 ranked product in its best light

## Quality Benchmarks
- Consistent lighting style across all products
- Clean, uncluttered compositions
- Professional color grading (warm, slightly desaturated cinematic tones)
- Text overlays max 6 words (per existing spec)

## Automation Opportunities
- **Dzine prompt templates per shot type** — auto-generate from product category + features in products.json
- **DaVinci timeline automation** — keyframe Ken Burns, group grading via scripting API
- **Shot list from script** — extend script_brief to auto-generate (hero, detail, lifestyle) per product
