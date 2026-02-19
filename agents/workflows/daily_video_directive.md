# Daily Video Directive (Amazon US Top 5)

Goal: publish 1 high-quality long video per day (8-12 min) using a single category-of-the-day strategy.

## Core Rules

- Choose one category for the day and keep all Top 5 products in that category.
- Do not mix sibling subcategories in the same ranking list.
  - Example: if the day is `Smart displays`, do not include `Smart speakers`.
  - Example: if the day is `Smart speakers`, do not include `Smart displays`.
- Products must be > USD 100.
- Use Amazon US as the primary source and cross-check with trusted external sources.
- Never repeat products used in the last 15 days (unless Ray explicitly overrides).

## Research Standard (Deep, not shallow)

For each ranked product include:

1. Current Amazon price.
2. Amazon rating + rating_count.
3. Amazon listing URL + availability status.
4. 3 Pros and 3 Cons based on recurring user feedback.
5. Source evidence from:

- Amazon listing/reviews, and
- at least 2 trusted external sources (RTINGS, Tom's Guide, TechRadar, PCMag, The Verge, CNET, Wirecutter, etc.).

6. User Consensus summary (recurring praise vs recurring complaints).

Add sections:

- Source Quality Matrix (source, date, confidence).
- Scoring Method (weighted ranking logic).
- Why #1 beats #2 (clear, evidence-based).

## Affiliate Links Standard

For each product:

1. Open product in new tab.
2. Click yellow SiteStripe button `Get link`.
3. Copy URL from popup and verify `tag=` exists.
4. Save final URL.
5. Close product tab.

If login/session/captcha blocks this flow:

- write `LOGIN_REQUIRED` or `BLOCKER` with exact next action.

## Script Standard (Human-authentic)

- Output: 8-12 min narration (~1,300-1,750 words).
- Voice and tone: natural, specific, and opinionated where justified.
- Avoid generic AI phrasing, repetitive transitions, and vague claims.
- Include one contrarian insight and one real buyer scenario per ranked product.
- Keep every claim tied to research evidence.

Mandatory sections:

- Hook
- Criteria
- #5 to #1 ranking
- Final verdict by buyer profile
- CTA
- Affiliate disclosure + AI disclosure
- "At time of recording" caveat for dynamic prices/ratings

## Dzine Visual Standard

- Use Character `Ray` consistently.
- Outfit may change by category, face identity must remain stable.
- For each ranked product, generate at least 3 approved original images using img2img + NanoBanana Pro.
- Every approved image must include visible price overlay
  (example: `$179.99 · Amazon US · at time of recording`).
- Use short lip-sync inserts, not full talking-head timeline.
- Keep visual mix around 80-90% product/environment visuals and 10-20% avatar lip-sync.

## Editing/Publish Gate

Block publish if any of these fail:

- missing/invalid affiliate links,
- weak factual support,
- script sounds AI-generic,
- fewer than 3 approved visuals per ranked product,
- missing disclosures.
