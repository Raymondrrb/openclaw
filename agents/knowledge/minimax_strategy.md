# Minimax Strategy — Rayviews Integration Plan

Updated: 2026-02-16

## Why Minimax

Two use cases for Rayviews:

### 1. MiniMax M2.5 — Cheap LLM for routine agent tasks

- **Pricing**: $0.30/MTok input, $1.20/MTok output (standard)
- **Comparison**: 1/17th the cost of Opus 4.6 ($5/$25), 1/3rd of Haiku
- **Best for**: market_scout, benchmark_analyst, quality_gate, cron jobs, heartbeats
- **NOT for**: scriptwriter (needs Opus-level creativity), davinci_editor (needs precision)

### 2. Hailuo 2.3 — Video generation API for B-roll

- **Pricing**: ~$0.045/sec at 768p via fal.ai ($0.27 per 6-sec clip)
- **Resolution**: 720p-1080p at 25fps
- **Duration**: 6-10 seconds per clip
- **Features**: text-to-video, image-to-video, physics engine, motion dynamics
- **Best for**: product showcase B-roll, transition clips, thumbnail backgrounds
- **NOT for**: full video production (too short, no voiceover sync)

## Model Routing Strategy (when API key is configured)

Based on Kevin Simback's cost optimization guide (38K views, Feb 2026):

| Task Type         | Model        | Cost/MTok   | Rationale                          |
| ----------------- | ------------ | ----------- | ---------------------------------- |
| Scriptwriter      | Opus 4.6     | $5/$25      | Creative writing needs frontier    |
| SEO package       | Sonnet 4.5   | $3/$15      | Good enough for SEO                |
| Market scout      | MiniMax M2.5 | $0.30/$1.20 | Routine data extraction            |
| Benchmark analyst | MiniMax M2.5 | $0.30/$1.20 | Pattern extraction                 |
| Quality gate      | Haiku 4.5    | $0.25/$1.25 | Simple validation                  |
| Heartbeats        | Haiku 4.5    | $0.25/$1.25 | Keep-alive, minimal reasoning      |
| Cron triggers     | MiniMax M2.5 | $0.30/$1.20 | Routine automation                 |
| DaVinci editor    | Sonnet 4.5   | $3/$15      | Needs precision but not creativity |

### Estimated monthly cost

- **Current** (all Sonnet 4.5): ~$150-300/month with 8 crons + heartbeats
- **Optimized** (routed): ~$30-60/month (80% reduction)
- **With prompt caching**: ~$20-40/month (additional 30% off cached system prompts)

## Prompt Caching Setup

SOUL.md files (3K-14K tokens each) are re-sent with every API call. With caching:

- First call: full price
- Subsequent calls within TTL: 90% off on cached portion
- Set heartbeat interval to 55 min (matches Anthropic extended cache TTL)

## Video Generation Workflow (future)

When ready to integrate Hailuo for B-roll:

1. Script identifies B-roll moments (e.g., "product rotating", "hands unboxing")
2. Generate text prompts describing each 6-sec clip
3. Call Hailuo API: text-to-video or image-to-video
4. Download 720p clips → feed to DaVinci timeline
5. Cost: ~$2-5 per video (8-15 B-roll clips)

### API Integration Points

- `platform.minimax.io` — direct API (unit-based pricing)
- `fal.ai/models/fal-ai/minimax/` — per-second pricing, simpler
- `replicate.com/minimax/video-01` — alternative provider

## Tools to Evaluate

### ClawRouter (2.4K GitHub stars in 11 days)

- Smart model routing for OpenClaw
- Classifies prompts: Simple → Medium → Complex → Heavy
- Routes to cheapest capable model
- Profiles: Auto, Eco (95% savings on simple), Premium, Free

### OpenRouter

- 300+ models, 1 API
- Built-in routing classifier
- Good if we don't want multi-provider config complexity

### ClawVault (Pedro @sillydarket — 73K views article)

- Primitives as markdown + YAML frontmatter
- Tasks, decisions, lessons — all as editable files
- Trigger-based autonomy > cron-based
- Multi-agent collaboration via shared filesystem
- `clawhub install agent-autonomy-primitives`
- Relevant for Rayviews: could replace/enhance current task management

## Action Items

1. [ ] When Anthropic API key is added: configure model routing in openclaw.json
2. [ ] Enable prompt caching for SOUL.md/AGENTS.md files
3. [ ] Evaluate ClawRouter for automatic routing
4. [ ] Create MiniMax API account at platform.minimax.io
5. [ ] Test Hailuo video generation for 1 product B-roll sequence
6. [ ] Benchmark M2.5 vs Haiku on quality_gate and market_scout tasks

## Sources

- Kevin Simback: "How to Reduce OpenClaw Model Costs by up to 90%" (X article, 38K views, Feb 2026)
- Pedro @sillydarket: "Solving Long-Term Autonomy for Openclaw & General Agents" (X article, 73K views, Feb 2026)
- MiniMax M2.5 pricing: artificialanalysis.ai, llm-stats.com
- Hailuo 2.3: minimax.io/news/minimax-hailuo-23
- Video API docs: platform.minimax.io/docs/api-reference/video-generation-t2v
