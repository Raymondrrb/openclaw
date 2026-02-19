# YouTube Trend Scan (Manual)

Purpose: Generate a daily trend list for a specific review niche.

Prereqs:

1. Create a YouTube Data API key.
2. Set it as `YOUTUBE_API_KEY`.

Recommended (persistent + safer for automation):

```
mkdir -p "$HOME/.config/newproject"
cat > "$HOME/.config/newproject/youtube.env" <<'EOF'
YOUTUBE_API_KEY=YOUR_KEY_HERE
EOF
chmod 600 "$HOME/.config/newproject/youtube.env"
```

Then in each new terminal session (or your shell profile), you can load it:

```
set -a
source "$HOME/.config/newproject/youtube.env"
set +a
```

Example:

```
export YOUTUBE_API_KEY="YOUR_KEY"
python3 /Users/ray/Documents/Rayviews/tools/youtube_trends.py \
  --query "open ear earbuds review" \
  --region US \
  --published-hours 48 \
  --duration medium \
  --max-results 25 \
  --out "/Users/ray/Documents/Rayviews/reports/trends/open_ear_earbuds_$(date +%F).json"
```

Batch (daily):

```
export YOUTUBE_API_KEY="YOUR_KEY"
export TREND_CONFIG="/Users/ray/Documents/Rayviews/config/trend_queries.json"
python3 /Users/ray/Documents/Rayviews/tools/youtube_trends_batch.py
```

Notes:

- Use duration=medium to focus on 4–20 minute videos.
- Rank by viewsPerHour to spot viral growth.
- Use the inspiration workflow to extract structure only.
