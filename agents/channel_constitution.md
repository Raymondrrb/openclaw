# Rayviews Channel Constitution

Single source of truth for channel identity, content rules, and quality standards.
Every pipeline stage references this document. Violations are hard failures.

---

## Core Promise

"Smart buying decisions, without the noise."

We help viewers cut through Amazon's 10,000 results and fake reviews to find the 5 products that actually hold up under expert testing.

## Target Viewer

- Age: 28-50
- Mindset: risk-reduction buyer (not impulse, not bargain-hunter)
- Context: home, comfort, productivity upgrades
- Trigger: "I need a [thing] but I don't want to waste money on the wrong one"
- They want confidence in their purchase, not entertainment

## Presenter

- Ray (avatar for intro + mid-video clarity moments)
- Avatar screen time: 20-40 seconds max per video
- Rest of video: B-roll, product shots, comparison graphics
- Avatar purpose: trust anchor, not entertainment persona

## Tone

- Calm, confident, practical, anti-hype
- Advisor energy — the friend who did the research and gives it to you straight
- Never salesy, never "influencer voice"
- State facts, acknowledge trade-offs, let the viewer decide
- Mix short punchy lines with natural explanations

### Forbidden Phrases

- "game-changer", "revolutionary", "hands down", "blow your mind"
- "In today's video", "Without further ado", "Let's dive in"
- "I was blown away", "This changed my life"
- "insane", "crazy", "unbelievable", "mind-blowing"
- "smash that like button", "what's up guys"

---

## Pricing Rules

- Default range: $120-$300
- Hard floor: $100 (no product below this unless cluster override)
- Cluster overrides: specific clusters (e.g., travel accessories) may set lower floors
- Rationale: products below $100 have thin margins, attract impulse buyers (not our audience), and generate low commissions

## Content Strategy

- Weekly clusters: 5 videos per cluster, thematically linked
- 6-week no-repeat: a cluster cannot be used again within 6 weeks
- Each micro-niche within a cluster has its own buyer pain, intent phrase, and price range
- Clusters are defined in `data/clusters.json`

## Research Rules

- EXACTLY 3 sources: Wirecutter (nytimes.com), RTINGS (rtings.com), PCMag (pcmag.com)
- No fallbacks, no other domains. Security agent enforces this.
- Max 2 pages per source
- If fewer than 2 sources produce data, stop with ACTION REQUIRED
- Evidence-first: every claim must be attributed to a specific source
- No generic filler claims ("great sound", "good value" without attribution)

## Ranking Structure

Every Top 5 uses these buyer-centric labels:

1. **No-Regret Pick** — highest confidence, broadest appeal
2. **Best Value** — best performance-per-dollar
3. **Best Upgrade** — premium pick for those willing to spend more
4. **Best for Specific Scenario** — niche winner (e.g., "best for small rooms")
5. **Best Alternative** — strong runner-up, different trade-offs

## Script Identity

Every script includes these segments:

1. **[HOOK]** (100-150 words) — Problem or tension. Never "In today's video."
2. **[MISTAKE_SEGMENT]** (60-90 words) — "The mistake 90% of buyers make when choosing {niche}..."
3. **Product sections** (#5 through #1) — Each includes:
   - Positioning label
   - 2-3 attributed benefits
   - "Buy this if..." / "Avoid this if..."
   - Honest downside (mandatory)
4. **[RETENTION_RESET]** (50-80 words) — Pattern interrupt after product #3
5. **[NO_REGRET_RECOMMENDATION]** (30-50 words) — Final confident recommendation before conclusion
6. **[CONCLUSION]** — Recap, CTA, FTC disclosure

## Visual Rules

- Avatar: 20-40 seconds total (intro + mid-video clarity moments)
- Rest: B-roll, product shots, comparison graphics
- Visual change every 3-6 seconds
- Zoom: 3-7% only (subtle, never distracting)
- Max 6-word text overlays
- Max 2 benefits per visual segment

## Mandatory Per Video

- Honest downside for every product (no exceptions)
- FTC affiliate disclosure (must contain: "affiliate", "commission", "no extra cost")
- All spec claims attributed to named source
- No invented measurements or test results

---

## Technical Specs

- Voice: 150 WPM, Thomas Louis, stability 0.50, similarity 0.75
- Audio: voiceover -16 LUFS/-1 dB peak, music -26 LUFS, SFX -18 LUFS
- Export: 1080p 30fps, 20-40 Mbps
- TTS chunks: 300-450 words, max 1 retry
