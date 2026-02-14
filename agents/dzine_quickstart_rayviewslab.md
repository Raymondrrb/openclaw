# Dzine Quickstart — RayviewsLab Production Guide

> Audience: 30+ consumers. Goal: trust, clarity, conversions.
> Only faithful product visuals and simple b-roll. No exploration.

---

## 1. Account & Setup

- **User:** Ramon Reis (Master plan, $59.99/mo)
- **Image credits:** Unlimited | **Video credits:** 9,000
- **Browser:** OpenClaw Brave, CDP port 18800
- **Viewport:** MUST be 1440x900 (all coords depend on this)
- **Canvas URL:** `https://www.dzine.ai/canvas?id=<project_id>`

---

## 2. Model Choice

| Use Case | Model | Credits | Why |
|----------|-------|---------|-----|
| **All product images** | Nano Banana Pro | 20 (2K) | Best photorealism + text accuracy on Dzine |
| **Product faithful** | BG Remove + Expand | 8 | Preserves real product from Amazon photo |
| **Ray avatar** | Consistent Character | 4 | Pre-trained "Ray" slot, face consistency |
| **Video (learning)** | Wan 2.1 | 6 | Cheapest, good enough for drafts |
| **Video (production)** | Minimax Hailuo 2.3 | 56-98 | Best motion quality available now |

**Rule:** Always Nano Banana Pro for images. Never economize on image model.

---

## 3. Production Workflows (only these 3)

### A. Product Faithful (real product from Amazon photo)

> **WARNING:** Img2Img does NOT preserve product identity. Use BG Remove + Expand.

1. Home → "Start from an image" → upload Amazon product photo
2. Close all dialogs
3. Click **BG Remove** in top action bar (free, ~11s)
4. Handle "Fit to Content and Continue" dialog if it appears
5. Open **Image Editor** sidebar (40, 698) → click **Expand**
6. Select **16:9** aspect ratio
7. Prompt: `Clean white studio backdrop with soft professional lighting, subtle shadow underneath product`
8. Click Generate (8 credits, 4 variants, ~75s)
9. Download best variant via `static.dzine.ai` URL

**Output:** `assets/dzine/products/{rank:02d}_faithful.webp`

### B. Product B-Roll Video (from faithful image)

1. In Results panel, click **AI Video [1]** on the faithful image result
2. Start frame auto-populates
3. Select **Wan 2.1** (6cr for learning) or **Hailuo 2.3** (56cr for production)
4. Camera: **Static Shot** (default, safest for products)
5. Prompt: `{product_name} on clean surface, subtle ambient light shifts, no camera movement, product showcase`
6. Click Generate
7. Poll for video result (~70s for Wan 2.1)

**Output:** `assets/dzine/products/{rank:02d}_video.mp4`

### C. Ray Avatar Frame (for Lip Sync)

1. Click **Character** sidebar (40, 306)
2. Click **Generate Images** card
3. Select **Ray** character
4. Scene prompt (describe scene only, NOT Ray's appearance):
   `Modern studio with soft cinematic key light, subtle rim light, dark neutral background. Professional tech reviewer standing pose.`
5. Set Control Mode: **Camera** / View: **Auto** / Framing: **Auto**
6. Set aspect ratio: **canvas** (1536x864 = 16:9)
7. Click Generate (4 credits, 2 variants, ~39s)
8. Download best variant

**Output:** `assets/dzine/avatar_frame.png`

---

## 4. Camera Settings (Video)

| Setting | Product Video | Why |
|---------|-------------|-----|
| **Static Shot** | DEFAULT — always use | No distortion, product stays sharp |
| Push In | OK sparingly | Subtle detail reveal |
| Zoom In | OK very light | Must be minimal |
| Pan/Truck/Pedestal/Tilt | FORBIDDEN | Distorts AI-generated products |
| Shake | FORBIDDEN | Unprofessional for 30+ audience |

**Max 1 camera movement per clip. When in doubt: Static Shot.**

---

## 5. Prompt Template — Product-in-Use B-Roll

```
Professional product photograph of {product_name} in a realistic setting.
{scene_description}
Soft key light from upper left, subtle fill light, natural shadows.
85mm equivalent, shallow depth of field, product razor-sharp.
Commercial grade photography. No people, no hands, no text, no watermarks.
```

**Scene variants by category:**
- **Audio:** Modern desk setup, subtle neon ambient, tech workspace
- **Kitchen:** Clean marble countertop, morning light through windows
- **Fitness:** Gym bench surface, dramatic side lighting
- **General:** Dark matte desk, premium studio environment

---

## 6. Export Settings

| Setting | Value |
|---------|-------|
| Format | **PNG** (default) |
| Upscale | **1x** (or 2x for hero shots) |
| Watermark | **OFF** |
| Method | Prefer direct URL download from `static.dzine.ai` |

**Export button:** `button.export` in top-right toolbar.
**Direct download** (preferred): extract `img[src*='static.dzine.ai']` URL from Results panel, fetch with `urllib.request`.

---

## 7. Cost Per Video (5 products)

| Asset | Count | Credits Each | Total |
|-------|-------|-------------|-------|
| Product faithful | 5 | 8 | 40 |
| Product video (Wan 2.1) | 5 | 6 | 30 |
| Avatar frame | 1 | 4 | 4 |
| **Total** | | | **74 image + 30 video** |

All image credits are unlimited on Master plan. Only video credits matter.

---

## 8. Rules

1. Do NOT explore new Dzine features unless explicitly requested
2. Max 3 actions per automation run
3. Prefer reading/writing local docs over browsing Dzine UI
4. Write checkpoint.json after each action
5. Keep outputs compact: ≤ 15 bullets per response
6. Never paste HTML/DOM dumps into chat
7. Store observations in local files incrementally
8. Static Shot is the only safe camera movement for products
