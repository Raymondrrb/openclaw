# Benchmark Watchlist

Use these URLs as reference candidates for style/retention and script language analysis.
Priority: channels with natural, human-sounding scripts in the Amazon review / tech top-5 niche.

## URLs to analyze

1. https://www.youtube.com/watch?v=NwEexVMPH3I (Top 5 Drones — NEGATIVE benchmark, generic/robotic style) [ANALYZED 2026-02-16]
2. https://www.youtube.com/watch?v=NjtHXc4O1Z8 (TechVisions — Best TVs 2026, spec-first + award titles) [ANALYZED 2026-02-16]
3. https://www.youtube.com/watch?v=MCDVcQIA3UM (DaVinci tutorial reference — NOT for script patterns, used by davinci_researcher)
4. https://www.youtube.com/watch?v=kACGSU-SCbU (Dave2D — 2026 Gaming Laptops, conversational authority, 301K views) [ANALYZED 2026-02-16]
5. https://www.youtube.com/watch?v=srYOnX3irhw (BTODtv — Best Office Chairs for Long Hours, 263K views, multi-host roundtable) [ANALYZED 2026-02-16]
6. https://www.youtube.com/watch?v=kzhD_gtMuNM (Performance Reviews — Top 5 Vacuums, 73K views, technician expert) [ANALYZED 2026-02-16]
7. https://www.youtube.com/watch?v=dVuF9oFxQvI (Fox Gadget — 41 Gadgets, ~41K views) [NO SUBTITLES — cannot extract transcript]
8. https://www.youtube.com/watch?v=bYG2URoquF8 (Elliot Page — Top 10 Adidas Sneakers 2026, 116K views, casual lifestyle) [ANALYZED 2026-02-16]
9. https://www.youtube.com/watch?v=_WjMMg0tVGE (Ahnestly/BTODtv — Favorite Office Chairs in Under 5 Min, 246K views, Q&A dialogue) [ANALYZED 2026-02-16]

## Analysis status

| Video ID     | Channel             | script_patterns.md        | analysis.md | playbook.md | Transcript |
| ------------ | ------------------- | ------------------------- | ----------- | ----------- | ---------- |
| NwEexVMPH3I  | Generic             | Done (negative benchmark) | Done (prev) | Done (prev) | Done       |
| NjtHXc4O1Z8  | TechVisions         | Done                      | Pending     | Pending     | Done       |
| MCDVcQIA3UM  | Tutorial            | N/A (not a review)        | Done (prev) | Done (prev) | Done       |
| kACGSU-SCbU  | Dave2D              | Done                      | Pending     | Pending     | Done       |
| srYOnX3irhw  | BTODtv              | Done                      | Pending     | Pending     | Done       |
| kzhD_gtMuNM  | Performance Reviews | Done                      | Pending     | Pending     | Done       |
| dVuF9oFxQvI  | Fox Gadget          | N/A (no subtitles)        | N/A         | N/A         | Failed     |
| bYG2URoquF8  | Elliot Page         | Done                      | Pending     | Pending     | Done       |
| \_WjMMg0tVGE | Ahnestly            | Done                      | Pending     | Pending     | Done       |

## Channels to scout for new URLs

- **TechVisions** — concise, spec-first, strong hooks
- **Mark Ellis Reviews** — opinionated, casual tone, trust-building
- **Dave2D** — minimalist script, short sentences, confident pauses
- **ProjectAir** — provocative hooks, conversational style
- **The Tech Chap** — UK accent but script structure is tight, good comparisons

When scouting: pick the best-performing "Top 5" or "Best [X]" video under 12 min from each channel.

## Next URLs to add (scouted 2026-02-16)

- Mark Ellis Reviews: `g589Z55rt-4` (AirPods Pro 3 vs 2 vs 1, 62K views, comparison format)
- Mark Ellis Reviews: `K0LjFsqAMdg` (Sony WF-1000XM6 Review, 25K views, single product deep dive)
- This is Tech Today: `zakPRMGlRbw` (Best Headphones of the Year — Audio Engineer, 96K views)

## Rules

- Analyze one URL per day.
- Save to `reports/benchmarks/video_<id>_analysis.md`.
- Save `reports/benchmarks/video_<id>_playbook.md` with operational rules for Ray.
- Save `reports/benchmarks/video_<id>_script_patterns.md` with language patterns for scriptwriter.
- After each analysis, update `agents/knowledge/natural_language_corpus.md` with new phrases.
- Prioritize URLs that haven't been analyzed yet before re-analyzing old ones.
