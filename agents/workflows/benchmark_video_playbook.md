# Workflow: Benchmark Video Playbook

Goal: keep a live quality benchmark based on high-performing reference videos.
Secondary goal: extract real language patterns that the scriptwriter agent can absorb.

## Inputs

- One YouTube URL.
- Optional niche context (Amazon US reviews over $100).

## Step 0: Extract transcript

- Use the `video-transcript` or `transcript` skill to pull the full transcript/captions.
- If auto-captions are available, use them. Manual captions preferred.
- If transcript extraction fails, proceed with inference but mark all sections Low confidence.
- Save raw transcript as `reports/benchmarks/video_<id>_transcript.txt` for reference.

## Required outputs

1. `reports/benchmarks/video_<id>_analysis.md`
2. `reports/benchmarks/video_<id>_playbook.md`
3. `reports/benchmarks/video_<id>_script_patterns.md` (NEW — for scriptwriter)

## Analysis standard

- Timeline map (hook, body blocks, CTA windows)
- Edit pacing profile (cut cadence and visual rhythm)
- Trust architecture (proof, disclaimers, authority cues)
- Monetization design (CTA order, conversion without trust loss)
- Emulate/Avoid with clear reasoning
- Upgraded adaptation for Ray's current pipeline

## Script pattern extraction (for output #3)

When transcript is available, extract and document:

1. **Hook verbatim** — exact words used in first 15 seconds
2. **Transition phrases** — how the narrator moves between products (or doesn't)
3. **Opinion markers** — phrases where the narrator gives personal opinion vs. stating facts
4. **Sentence length variation** — note shortest and longest sentences, average rhythm
5. **Product intro variety** — how each product section opens (are they all the same or different?)
6. **Trust phrases** — exact words used for limitations, caveats, honest downsides
7. **Banned patterns observed** — any AI-sounding phrases (see scriptwriter SOUL anti-AI blacklist)
8. **Top 5 phrases worth stealing** — natural-sounding phrases Ray's scriptwriter should emulate

Format: actionable, with direct quotes from transcript. Not inference.

## Confidence policy

- Mark each section as High/Medium/Low confidence.
- If transcript is unavailable, explicitly state inference assumptions.
- Sections based on actual transcript text should be marked High confidence.
