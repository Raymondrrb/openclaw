# DaVinci Resolve Editing Rules — Amazon Product Ranking Videos

## Technical Specs

| Setting        | Value             |
|----------------|-------------------|
| Resolution     | 1920x1080         |
| Frame rate     | 30fps             |
| Export codec   | H.264             |
| Export bitrate | 20–40 Mbps VBR    |
| Audio          | AAC 320 kbps      |

---

## Audio Targets

| Track | Content   | LUFS   | Peak  | Notes                          |
|-------|-----------|--------|-------|--------------------------------|
| A1    | Voiceover | -16    | -1 dB | Always on top                  |
| A2    | Music     | -26    | —     | Duck under voice automatically |
| A3    | SFX       | -18    | —     | Whoosh on transitions, click on benefits |

- Fade music in over first 2s
- Fade music out over last 3s
- Music stays ducked under voice for entire duration

---

## Video Structure (Mandatory)

```
HOOK (0–20s) → AVATAR (3–5s) → #5 → #4 → #3 → RESET → #2 → #1 → OUTRO
```

### 1. Hook (0–20s)
- Strong promise, fast pacing
- No long intro, no channel name
- Best product shot or bold claim

### 2. Avatar Intro (3–5s max)
- Quick branded intro clip
- Then disappear — do NOT use avatar throughout

### 3. Product Segments (#5 through #1)

Each segment must contain:
- Short intro (product name + rank)
- 2 strong benefits (overlay text, max 6 words each)
- 1 honest drawback
- Quick verdict

### 4. Retention Reset (after #3)
- Pattern interrupt before top 2
- Question to audience or quick comparison

### 5. Signature Moment (1 per video)
- Unique recurring moment
- Example: "If you only buy one thing from this list, make it #2."
- Placed after the middle segment

### 6. Outro
- Affiliate disclosure on screen
- Exact text: "As an Amazon Associate I earn from qualifying purchases."

---

## Pacing Rules

- Visual change every **3–6 seconds**. Never hold a static image longer than 6s.
- Use **light zoom (3–7%)** on all static images:
  - `zoom_in`: 100% → 103-107% over clip duration
  - `zoom_out`: 107% → 100% over clip duration
  - `ken_burns`: slow zoom + slight pan
- Video clips play at native speed, no zoom applied.
- **Between segments**: 0.5s cross-dissolve
- **Within segments**: hard cut

---

## Overlay Guidelines

All overlays: **one at a time, max 6 words**. No clutter.

### Rank Badge
- Position: top-left
- Duration: 3s from segment start
- Style: bold number, consistent brand color

### Product Name
- Position: lower-left
- Duration: 3s, appears 1s after segment start
- Style: semi-transparent bar, white text

### Benefits (2 per product)
- Position: lower-left
- Duration: 3s each, staggered
- Click SFX when each benefit appears
- Max 6 words per benefit

### Affiliate Disclosure
- Position: lower-left
- Duration: 6s, in last 8s of video
- Text: "As an Amazon Associate I earn from qualifying purchases."

### Signature Moment
- Position: center
- Duration: 4s
- Placed at 60% through the middle segment

---

## SFX Rules

- **Whoosh**: subtle, on every segment transition
- **Click**: when highlighting key benefits (on overlay appear)
- No SFX stacking — one at a time
- All SFX at -18 LUFS

---

## Visual Priority Order

For each product segment, assign visuals in this order:
1. Amazon real product image
2. Dzine enhanced image
3. Optional short clip
4. Background (fallback)

---

## Style Rules

- Consistent font across all overlays (2–3 brand colors only)
- Avoid clutter — one overlay at a time
- Keep amazon photos true-to-color
- Dzine images: slight desaturation if needed to match real photos

---

## Conversion Rules

- Emphasize VALUE vs PRICE
- Sound helpful and slightly opinionated
- Avoid sounding salesy — prioritize trust
- Encourage clicks naturally
- Do not overhype

---

## Folder Structure

```
artifacts/videos/<video_id>/
├── audio/
│   ├── voiceover.wav
│   ├── music_bed.wav
│   └── sfx/
│       ├── whoosh.wav
│       └── click.wav
├── visuals/
│   ├── thumbnail.png
│   ├── avatar_intro.mp4
│   ├── backgrounds/
│   └── products/
│       ├── 01/ … 05/
│       │   ├── amazon_*.png
│       │   ├── dzine_*.png
│       │   └── clips/
├── resolve/
│   ├── edit_manifest.json
│   ├── markers.csv
│   └── notes.md
├── exports/
├── script.txt
└── products.json
```

---

## Edit Manifest JSON

```json
{
  "video_id": "my-video",
  "resolution": [1920, 1080],
  "fps": 30,
  "total_duration_s": 540.0,
  "intro": {
    "hook": { "start_s": 0, "end_s": 15 },
    "avatar": { "file": "visuals/avatar_intro.mp4", "start_s": 15, "end_s": 19 }
  },
  "segments": [
    {
      "rank": 5,
      "product_name": "Product Name",
      "start_s": 19, "end_s": 97,
      "overlays": [],
      "visuals": [],
      "sfx": []
    }
  ],
  "music": { "file": "audio/music_bed.wav", "volume_lufs": -26, "duck_under_voice": true },
  "outro": { "start_s": 507, "end_s": 540 }
}
```

---

## Resolve Workflow

1. Create project, set timeline 1920x1080 @ 30fps
2. Import all media from video folder
3. Import `markers.csv` (Edit > Import > Timeline Markers)
4. V1: Place visuals per manifest
5. V2: Fusion titles for overlays
6. V3: Avatar intro clip (first 4s only)
7. A1: Voiceover
8. A2: Music bed at -26 LUFS, duck under voice
9. A3: SFX at marker points
10. Apply light zoom (3-7%) via Dynamic Zoom
11. 0.5s dissolve between segments
12. Export: H.264, 1080p, 20-40 Mbps VBR, AAC 320kbps
