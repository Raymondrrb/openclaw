# Video Script System — Amazon Associates Product Ranking Channel

## Overview

8-12 minute YouTube videos, Top 5 product format, monetized via Amazon Associates (US).

Target: 1,300-1,800 words at ~150 wpm.

---

## Core Structure (Mandatory)

| # | Section | Duration | Words |
|---|---------|----------|-------|
| 1 | Hook | 0:00-0:25 | 100-150 |
| 2 | Avatar Intro | 3-6 sec | 1-2 sentences (max 320 chars) |
| 3 | Product #5 | ~1:30 | 200-300 |
| 4 | Product #4 | ~1:30 | 200-300 |
| 5 | Product #3 | ~1:30 | 200-300 |
| 6 | Retention Reset | ~0:30 | 50-80 |
| 7 | Product #2 | ~1:30 | 200-300 |
| 8 | Product #1 | ~1:30 | 200-300 |
| 9 | Conclusion + CTA | ~0:30 | varies |

---

## Hook Rules

- Open with problem or tension.
- No "In today's video".
- No overhype.
- No fake urgency.
- Imply value without exaggeration.

---

## Product Segment Structure

Each product (200-300 words):

A) **Quick Positioning** — why it made the list
B) **Core Benefits** — 2-3 specific, practical points (no vague adjectives)
C) **Who It's For** — be specific
D) **Honest Downside** — mandatory, builds trust
E) **Transition Line** — bridge to next product

---

## Retention Reset (after Product #3)

50-80 words. Pattern interrupt options:
- Mini story
- Quick comparison
- "Before we continue..."

Optional: avatar appearance (3-4 sec).

---

## Charismatic Channel Signature

Rotate one per video:

**Reality Check**: "Remember, price doesn't always mean better."
**Micro Humor**: "And no, this isn't one of those 'looks cool but breaks in a week' gadgets."
**Micro Comparison**: "It's the kind of upgrade you don't notice until you go back to the old version."

---

## Language Rules

### Banned Hype Words
insane, crazy, unbelievable, mind-blowing, game-changer, jaw-dropping, revolutionary, groundbreaking, epic, life-changing

### Banned AI Cliches
- "When it comes to..."
- "In today's fast-paced world..."
- "Whether you're a beginner or professional..."
- "Let's dive in / without further ado"
- "Smash that like button / hit that bell"
- "In today's video..."

### Rhythm
Vary sentence length. Short sentences. Then longer explanation. Then a punchy line.

---

## Amazon Associates Compliance

**Never say or imply:**
- Official Amazon partnership
- Guaranteed lowest price
- Fake discounts or urgency
- Invented specifications

**Required disclosure** (conclusion):
> "Links in the description may be affiliate links, which means I may earn a small commission at no extra cost to you."

---

## 4-Step Workflow

### Step 1: Viral Pattern Extraction
Analyze 3-5 viral Top 5 videos in the niche. Extract hook structure, pacing, emotional triggers, retention tactics.

```bash
python3 tools/script_gen.py --products products.json --niche "your niche" --step extraction --reference "url1,url2"
```

### Step 2: GPT Structured Draft
Feed extraction notes + product data to GPT. Output: 1,300-1,800 word draft.

```bash
python3 tools/script_gen.py --products products.json --niche "your niche" --step draft --notes extraction.txt
```

### Step 3: Claude Refinement
Remove AI cliches, reduce repetition, tighten sentences, insert charismatic element.

```bash
python3 tools/script_gen.py --step refinement --draft draft.txt --charismatic micro_humor
```

### Step 4: Final Validation
Automated checks + optional LLM review.

```bash
python3 tools/script_gen.py --validate final_script.txt --llm-review
```

---

## Script File Format

For `--validate`, use section markers:

```
[HOOK]
Most Amazon "best seller" lists are recycled...

[AVATAR_INTRO]
Today I picked 5 Amazon finds worth your money. Let's begin.

[PRODUCT_5]
Coming in at number five...

[PRODUCT_4]
...

[PRODUCT_3]
...

[RETENTION_RESET]
Quick note — the last two products...

[PRODUCT_2]
...

[PRODUCT_1]
...

[CONCLUSION]
Thanks for watching. Links in the description may be affiliate links...

AVATAR_INTRO: Today I picked 5 Amazon finds worth your money. Let's begin.
DESCRIPTION: Top 5 Amazon products worth buying. Affiliate links below.
THUMBNAILS:
- Best ANC 2026
- Top 5 Picks
- Worth Your Money
```

---

## Product JSON Format

```json
[
  {
    "rank": 5,
    "name": "Product A",
    "positioning": "budget pick",
    "benefits": ["Great battery life", "Comfortable fit"],
    "target_audience": "commuters who want ANC under $100",
    "downside": "microphone quality is average for calls",
    "amazon_url": "https://amazon.com/dp/..."
  }
]
```

---

## Final Output Checklist

Every script delivery must include:
1. Word count
2. Full structured script (with section markers)
3. Separate avatar intro script
4. YouTube description with affiliate disclosure
5. 3 thumbnail headline options (max 4 words each)
