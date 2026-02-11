# Dzine Visual System — Amazon Associates Product Ranking Channel

## Context

This project produces YouTube product ranking videos (Top 5 format) monetized via Amazon Associates (US) tracking links.

Dzine generates:
1. Thumbnail (high CTR)
2. Product showcase images (clean, realistic)
3. Background / transition frames
4. Avatar base portrait (host image for lip sync)

Goal: Consistent, premium visual identity across all videos. No clutter. No AI artifacts. No misleading visuals.

---

## Global Visual Principles

- Clean composition — one main subject only.
- High clarity and sharpness.
- Realistic lighting physics.
- No watermarks.
- No added brand logos.
- No fake discount badges.
- Product must match real Amazon listing.
- Avoid exaggerated, clickbait visuals.

---

## Asset Types

### Thumbnail (2048x1152)

Drive CTR while maintaining trust and compliance.

Rules:
- 3-4 words maximum in headline.
- Text must be readable on mobile.
- Product prominently placed on right side.
- Text placed on left side.
- Strong contrast.
- Minimal background.
- Cinematic but clean.

### Product Showcase (2048x2048)

Clean e-commerce style visuals for product segments.

Rules:
- Centered product.
- Neutral background.
- Accurate proportions.
- No stylization.
- No added accessories.
- When reference image exists: match the real product design accurately.

### Background / Transition (2048x1152)

Clean b-roll frames between product segments.

Rules:
- Minimal.
- No text.
- No objects.
- No distraction.

### Avatar Base Portrait (2048x2048)

Base portrait for host avatar used in 3-6 second intro or transitions.

Rules:
- Friendly but subtle expression.
- Professional look.
- Realistic skin texture.
- No exaggeration.
- Clean background.
- Tech reviewer aesthetic, subtle rim light.

---

## Reference Image Workflow

For product images, use real Amazon product photos as reference:

1. Download the product image from Amazon listing
2. Pass via `--reference-image ./photos/product.png`
3. Dzine uses it as visual reference — the prompt includes "Match the real product design accurately"
4. Result should look like a studio reshoot of the real product, not a reinvention

---

## Quality Checklist (Must Pass Before Approval)

**Thumbnail:**
- Text readable at small size
- No clutter
- Product clearly visible
- High contrast
- No fake claims

**Product image:**
- Accurate proportions
- No distortion
- No added elements
- Clean edges

**Background:**
- Minimal
- No distractions
- No hidden artifacts

**Avatar:**
- Natural facial structure
- No uncanny deformation
- Expression subtle and professional

---

## Amazon Associates Compliance

Never visually imply:
- Official Amazon partnership
- Guaranteed lowest price
- Fake discount tags
- Fake urgency banners

All visuals must support honest product presentation.

---

## Avatar Intro Script Guidelines (for lip sync)

Short introduction clip (3-6 seconds).

Rules:
- 1-2 short sentences.
- Clear and direct.
- No clickbait or false urgency.
- Max 320 characters.

Examples:
> Today I picked 5 Amazon products that are actually worth your money. Let's start with number five.

> Here are 5 Amazon finds that genuinely stand out this week. Let's begin.

---

## Consistency System

For each video:
- Use same lighting style.
- Use similar background tone.
- Maintain consistent thumbnail color palette.
- Keep headline font style consistent across videos.
- Avoid radical visual changes between videos.

---

## CLI Usage

```bash
# Thumbnail
python3 tools/dzine_gen.py --asset-type thumbnail \
  --product-name "Product Name" --key-message "Top Pick" --dry-run

# Product with reference image
python3 tools/dzine_gen.py --asset-type product \
  --product-name "Product Name" --reference-image ./photos/product.png

# Background
python3 tools/dzine_gen.py --asset-type background

# Avatar
python3 tools/dzine_gen.py --asset-type avatar_base
```

---

## Export Recovery Procedure

When Dzine's Download/Export button is disabled or grayed out:
1. Click the generated result image
2. Click "Image Editor" button
3. In the layer panel, click/activate the first layer
4. The Export/Download button should now be enabled
5. If still disabled: tool takes a screenshot as fallback
