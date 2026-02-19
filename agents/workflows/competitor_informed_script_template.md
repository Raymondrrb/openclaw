# Script Template: Top 5 Long-Form (Competitor-Informed)

> **NOTE**: This is ONE template (classic_countdown) among several structure options.
> When `variation_plan.json` exists, its `structure_template` and `product_block_pattern`
> take precedence over this template. This file serves as the fallback/default structure
> and as a reference for the classic countdown format.

Based on analysis of high-performing channels: Mrwhosetheboss, MKBHD, BTODtv, Dave2D, Matt Talks Tech.
See `agents/knowledge/competitor_script_pattern.md` and `agents/knowledge/natural_language_corpus.md`.

Target: 8-12 min narration (~1,300-1,750 words)

Core principle: This is NOT a review. It's a PURCHASE DECISION video.
Every second must answer: "Which one is actually worth buying?"

---

## Section 1: Cold Open (0:00-0:25) — 30-50 words

**Goal:** Prevent abandonment in the first 20 seconds. Create curiosity loop.

```
[Extreme comparison OR impossible promise OR common problem]
[Flash 3 products quickly + 1 mystery]
[The viewer's exact question]
```

### Examples (vary per video):

**Overwhelm hook** (TechVisions style):

```
[Category] in [year] is more confusing than ever.
[Jargon A], [Jargon B], [Jargon C].
So which one is actually worth your money?
```

**Mystery hook** (Mrwhosetheboss style):

```
I tested dozens of [category]... but one of them genuinely [surprising result]
— and it wasn't the most expensive one.
```

**Anti-shill hook** (Performance Reviews style):

```
If you're looking for another shill for one of the big [category] companies,
this is not that video. These are [products] you may never have heard of.
```

**Meta-complaint hook** (Ahnestly — for short-form):

```
"I don't have time to watch a 2-hour [category] review.
Just tell me what is the best [product]."
```

Rules:

- NEVER start with "Hey guys welcome back" or "In today's video"
- NEVER use "Are you looking for the best [X]?"
- Must create a curiosity gap (viewer thinks: "which one?")
- Mention links once, naturally
- Under 25 seconds. No channel bumper.

---

## Section 2: Credibility + Criteria (0:25-1:10) — 60-90 words

Two beats in one section:

### Beat 1: Process proof (0:25-0:45)

Show experience, not authority claims.

```
I [tested/used/compared] these for [time period].
[One specific detail that proves real usage.]
```

This is NOT: "I'm an expert in..."
This IS: "I used these for two weeks at my standing desk..."

### Beat 2: Rules of the game (0:45-1:10)

Define criteria → activates viewer's logical brain → they accept your ranking.

```
I ranked these based on:
1) [Criterion A]: [one-line why it matters]
2) [Criterion B]: [one-line why it matters]
3) [Criterion C]: [one-line why it matters]
```

Rules:

- 3 criteria max (keeps it tight)
- Each criterion maps to evidence in research doc
- Include "at time of recording" caveat for prices/ratings
- Without criteria → ranking feels like random opinion

---

## Section 3: The Product Loop — #5 to #1 (1:10-8:00) — 900-1,200 words

Each product is a MINI-FILM with 6 beats. NOT a spec sheet.

### Per-Product Structure (~90 seconds, 150-200 words)

```
BEAT 1: Problem (1-2 sentences)
"Most [category] have [specific pain point]..."
→ Viewer identifies with the problem.

BEAT 2: Presentation + Award
#[N] — [Product Name] — Best [X]
→ Name + function + why it earned this spot.

BEAT 3: Specs/Demo (2-3 sentences)
[Real numbers first. Not opinion — data.]
[Specific measurement, certification, unique feature.]
→ Establishes authority.

BEAT 4: Micro-Review (3 points max)
- Something good (with evidence)
- Something surprising ("this actually...")
- Small honest limitation ("but...")
→ Builds trust. Limitation is MANDATORY.

BEAT 5: Who Should / Who Shouldn't Buy
"If you [specific scenario], this is your pick."
"If you [opposite scenario], skip this one."
→ Reduces viewer's doubt = increases conversion.

BEAT 6: Hook to Next Product
"But the next one [tease]..."
→ Prevents abandonment between products.
→ NEVER use "Coming in at number [X]" or "Next up"
```

### Pacing (products get LONGER as we approach #1)

| Product | Target Duration | Words   |
| ------- | --------------- | ------- |
| #5      | 60-70s          | 120-140 |
| #4      | 65-75s          | 130-150 |
| #3      | 70-80s          | 140-160 |
| #2      | 80-90s          | 160-180 |
| #1      | 90-110s         | 180-220 |

### Product openers (MUST vary every product)

- Question: "Ever tried to [action] and it just didn't work?"
- Statement: "This one surprised me."
- Contrast: "Unlike the #4, this actually [difference]."
- Data: "$47. That's it. And it does [X]."
- Confession: "Honestly, I didn't expect to like this one."

### Peak behavior (Top 2)

- More screen time
- Stronger emotional language
- Anticipate #1 at least 2 times before reveal
- "The winner isn't what I expected..."

### Short punches (MANDATORY: at least 1 per product, <=4 words)

- "Worth it."
- "Not even close."
- "Here's the catch."
- "Skip this one."
- "That's the problem."

---

## Section 4: Decision Reinforcement (8:00-9:00) — 80-120 words

NOT a recap. A PURCHASE GUIDE.

### Quick comparison (award-based):

```
Quick recap:
- Best [Award A]: [Product]
- Best [Award B]: [Product]
- Best Overall: [Product]
```

### Buyer mapping (scenario-based):

```
So who should buy what?
- If you [specific situation], go with [Product].
- If you [budget concern], the [Product] is the better call.
- If you just want the best and don't mind paying, [Product] is hard to beat.
```

### THE conversion line:

```
"If you only buy one thing from this list... get [#1]."
```

This single sentence is the highest-converting moment in the entire video.

---

## Section 5: Outro (9:00-9:30) — 40-60 words

```
That's the top 5 [category] for [year].
There's no single perfect [product type] for everyone — the right pick depends on [2-3 factors].
Check the links for current pricing.
If this helped, subscribe for more.
[Disclosure: affiliate + AI]
```

Rules:

- Acknowledge no universal winner (builds trust)
- Soft subscribe CTA (not aggressive)
- NEVER: "Thanks for watching!" or "Don't forget to..."
- AI disclosure + affiliate disclosure (mandatory, FTC)
- Under 30 seconds

---

## Style Rules

### Voice

- Sound human: vary sentence length, include opinion, use contractions
- Emotional reactions: surprise, frustration, satisfaction — not just explaining
- Authority first, affiliate after (MKBHD principle: don't seem like a seller = sell more)

### Anti-AI (enforced by script_quality_gate.py)

- Zero tolerance for blacklisted phrases (see SOUL.md)
- No 3+ adjectives in a row
- No repetitive sentence structure across products
- Contractions mandatory ("it's", "don't", "you'll")

### Rhythm

- Spec sentences: 15-35 words (pack the data)
- Opinion sentences: 2-6 words (punch hard)
- Trust sentences: 10-20 words (clear limitation)
- NEVER: 5+ sentences at same length

### Numbers

- Say naturally: "around nine to ten milliseconds" not "9-10ms"
- Prices: always include context ("that's $30 less than the next one")

## Compliance Checklist

- [ ] All prices verified on Amazon US
- [ ] All specs sourced from manufacturer or trusted reviews
- [ ] "At time of recording" caveat included
- [ ] Affiliate disclosure in description
- [ ] AI disclosure in video and description
- [ ] No unverifiable claims
- [ ] Limitation included for every product (including #1)
- [ ] Every product has "who should buy" AND "who should NOT buy"
- [ ] Short punch (<=4 words) in every product section
- [ ] Product openers all different
- [ ] At least 1 cross-product comparison
- [ ] Hook to next product between EVERY product
- [ ] #1 anticipated at least 2 times before reveal
- [ ] Decision reinforcement line: "If you only buy one..."
