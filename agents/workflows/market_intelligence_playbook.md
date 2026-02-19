# Market Intelligence Playbook: Multi-Source Product Discovery

Goal: enrich daily product selection with real-time demand signals from
Google Trends, Reddit, and TikTok — beyond Amazon rankings alone.

Target audience: 35+ buyers with high purchase intent and conversion rates.

## Why Multi-Source Matters

Amazon Best Sellers lag 24-48h behind real demand. By the time a product
hits #1, every review channel already covers it. The edge comes from
detecting demand acceleration BEFORE it peaks.

Signal chain: Google Trends spike → Reddit discussion → TikTok virality → Amazon sales surge → YouTube coverage

We want to catch products between steps 1-3, before step 5.

## Step 1: Google Trends Pulse (5 min)

Run the daily trends check for US:

```bash
# Today's trending searches (US)
curl -s "https://trends.google.com/trending/rss?geo=US" | \
  grep -o '<title>[^<]*</title>' | sed 's/<[^>]*>//g' | tail -n +2 | head -20
```

Then check product categories relevant to our rotation:

```bash
# Compare category interest (use today's category + 2 alternates)
# Example: if today's category is "headphones"
open "https://trends.google.com/trends/explore?q=best+headphones+2026,best+earbuds+2026,headphones+review&geo=US&date=now+7-d"
```

### What to look for:

- **Breakout queries** (>5000% growth) — new product launches or viral moments
- **Rising queries** with "best", "review", "vs", "worth it" — buying intent
- **Category spikes** that align with today's rotation category
- **Product-specific surges** — individual models gaining search volume

### 35+ audience signal:

- Queries with "best for home", "comfortable", "easy to use", "quality"
- Price-related: "worth the money", "best under 500", "premium"
- Avoid: "cheap", "budget", "student" (younger demographic)

## Step 2: Reddit Buyer Intent Scan (10 min)

Use the reddit-readonly skill to scan subreddits where 35+ buyers discuss purchases:

```bash
# Key subreddits for product discovery (35+ buyers)
SKILL_DIR="$HOME/.openclaw/workspace/skills/reddit-readonly"

# r/BuyItForLife — quality-focused buyers, high AOV
node "$SKILL_DIR/scripts/reddit-readonly.mjs" search BuyItForLife \
  "best" --limit 10 --sort top --time week

# r/hometheater — high-ticket electronics
node "$SKILL_DIR/scripts/reddit-readonly.mjs" search hometheater \
  "recommendation" --limit 10 --sort top --time week

# r/headphones — audiophile buyers (high AOV)
node "$SKILL_DIR/scripts/reddit-readonly.mjs" search headphones \
  "best 2026" --limit 10 --sort top --time week

# Search all of Reddit for today's category
node "$SKILL_DIR/scripts/reddit-readonly.mjs" search all \
  "best [CATEGORY] 2026 amazon" --limit 10
```

### High-value subreddits by category:

| Category         | Subreddits                                          |
| ---------------- | --------------------------------------------------- |
| Audio            | r/headphones, r/audiophile, r/soundbars             |
| Home theater     | r/hometheater, r/4kTV, r/OLED                       |
| Smart home       | r/smarthome, r/homeautomation, r/amazonecho         |
| Laptops/monitors | r/SuggestALaptop, r/monitors, r/ultrawidemasterrace |
| Kitchen/home     | r/BuyItForLife, r/Cooking, r/espresso, r/coffee     |
| Fitness/health   | r/homegym, r/running, r/GarminWatches               |
| Camera/photo     | r/photography, r/videography, r/Cameras             |
| Gaming           | r/PS5, r/XboxSeriesX, r/NintendoSwitch              |

### What to extract:

1. **Products people actually recommend** (not marketing — real users)
2. **Pain points** with specific products ("I returned the X because...")
3. **"vs" threads** — direct comparisons people want answered
4. **"Is it worth it?" posts** — high purchase intent signals
5. **Complaints about existing reviews** ("every YouTube review is sponsored...")

### How this feeds product selection:

- A product mentioned 3+ times across threads = strong demand signal
- A "vs" comparison post with 50+ comments = video topic with guaranteed audience
- Pain points become script material (honest limitations section)

## Step 3: TikTok Viral Product Detection (10 min)

Use yt-dlp to scan TikTok for viral product reviews:

```bash
# Search for viral product reviews in today's category
yt-dlp "tiktoksearch:best [CATEGORY] 2026 amazon" \
  --simulate --dump-json --playlist-end 20 | \
  jq -s 'sort_by(.view_count) | reverse | .[:10] | .[] |
    {title: .title, views: .view_count, likes: .like_count,
     uploader: .uploader, url: .webpage_url}'

# Check what's viral in product review TikTok generally
yt-dlp "tiktoksearch:amazon must haves 2026" \
  --simulate --dump-json --playlist-end 20 \
  --match-filters "view_count >= 100000" | \
  jq -s 'sort_by(.view_count) | reverse | .[] |
    {title: .title, views: .view_count, url: .webpage_url}'

# Hashtag scan for product discovery
yt-dlp "https://www.tiktok.com/tag/amazonfinds" \
  --simulate --dump-json --playlist-end 30 \
  --match-filters "view_count >= 500000" \
  --dateafter "$(date -u -v-7d +%Y%m%d)" | \
  jq -s 'sort_by(.view_count) | reverse | .[:10]'
```

### High-signal TikTok hashtags:

- `#amazonfinds` — general product discovery
- `#amazonmusthaves` — high conviction recommendations
- `#techtok` — tech product reviews (our core niche)
- `#[category]review` — category-specific
- `#worthit` — purchase intent
- `#over30` / `#adulting` — 35+ audience signals

### What makes a TikTok signal valuable:

- **View/like ratio > 5%** = high engagement, people care about this product
- **Comments asking "where to buy"** = conversion intent
- **Multiple creators reviewing same product** = demand wave
- **"I was wrong about X" narratives** = contrarian angle for our scripts

## Step 4: Cross-Source Signal Scoring

After collecting signals from all sources, score each product opportunity:

| Signal                   | Weight | Score (0-5)                      |
| ------------------------ | ------ | -------------------------------- |
| Amazon BSR movement      | 20%    | How fast is rank improving?      |
| Google Trends velocity   | 20%    | Breakout/rising search interest? |
| Reddit mention frequency | 20%    | Real buyers discussing it?       |
| TikTok virality          | 15%    | Going viral in product reviews?  |
| Brave web/news mentions  | 10%    | Blog/news coverage picking up?   |
| YouTube competition gap  | 15%    | Is there a good review missing?  |

### Bonus signals (+1 each):

- Mentioned in 3+ sources = multi-source confirmation
- Price > $150 = higher affiliate commission potential
- "vs" comparisons appearing = natural video structure
- 35+ audience markers present (subreddit demographic, search terms)

### Disqualifiers (skip product):

- Only trending on TikTok with younger demographic signals
- Price under $100 (below our threshold)
- Already covered by 3+ major review channels this week
- Stock issues on Amazon (out of stock, delivery > 2 weeks)
- Controversial/recall/safety issues detected

## Step 5: Feed Into Daily Category Decision

The cross-source score modifies the category rotation:

1. Run `pick_daily_category.py` as baseline
2. Check if today's category has strong multi-source signals
3. If signals are weak AND another category has breakout signals, document override in `category_override.md`
4. Feed top products into `pipeline.py run-e2e --category CATEGORY`

## Output: Market Intelligence Brief

Save as `reports/market/YYYY-MM-DD_market_intelligence.md`:

```
# Market Intelligence Brief — YYYY-MM-DD

## Signal Summary
- Google Trends: [top 3 relevant breakouts]
- Reddit: [top 3 discussion threads with buyer intent]
- TikTok: [top 3 viral products, view counts]
- Cross-source confirmed: [products appearing in 2+ sources]

## 35+ Audience Conversion Signals
- [Specific signals that indicate our target demographic is buying]

## Category Recommendation
- Rotation pick: [category]
- Signal strength: [strong/moderate/weak]
- Override recommended: [yes/no, reason]

## Top 5 Product Candidates (pre-Gate 1)
1. [Product] — Signal: [sources], Score: [X/5], Why: [1 line]
2. ...

## Contrarian Angles (for script differentiation)
- [Product X]: most reviewers say Y, but Reddit users report Z
- [Product Y]: TikTok viral for wrong reasons, real value is...

## Sources
- [All URLs referenced]
```

## Automation Notes

- Google Trends RSS is free, no auth, no rate limit concerns
- Reddit JSON endpoints: respect 1 req/sec, use small limits first
- TikTok yt-dlp: use --sleep-interval 2, may need cookies for heavy use
- All three can run in the morning cron before the market scout report
