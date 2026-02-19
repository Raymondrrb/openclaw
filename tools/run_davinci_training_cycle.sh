#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="${PROJECT_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
REPORT_DIR="$BASE_DIR/reports/davinci"
MANUAL_PATH="$BASE_DIR/agents/knowledge/davinci_operator_manual.md"

usage() {
  cat <<'EOF'
Usage:
  run_davinci_training_cycle.sh <youtube_url_or_id> [--date YYYY-MM-DD]

Examples:
  run_davinci_training_cycle.sh https://www.youtube.com/watch?v=MCDVcQIA3UM
  run_davinci_training_cycle.sh MCDVcQIA3UM --date 2026-02-07
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

VIDEO_INPUT=""
DATE_OVERRIDE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --date)
      if [[ $# -lt 2 ]]; then
        echo "ERROR: --date requires YYYY-MM-DD"
        exit 1
      fi
      DATE_OVERRIDE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      if [[ -z "$VIDEO_INPUT" ]]; then
        VIDEO_INPUT="$1"
      else
        echo "ERROR: unknown argument: $1"
        exit 1
      fi
      shift
      ;;
  esac
done

if [[ -z "$VIDEO_INPUT" ]]; then
  echo "ERROR: missing YouTube URL or video id"
  exit 1
fi

mkdir -p "$REPORT_DIR"

DATE_VALUE="${DATE_OVERRIDE:-$(date +%F)}"

if ! python3 - <<'PY' >/dev/null 2>&1
import importlib.util, sys
sys.exit(0 if importlib.util.find_spec("youtube_transcript_api") else 1)
PY
then
  cat <<'EOF'
ERROR: missing dependency: youtube-transcript-api

For security, this script does not auto-install Python packages at runtime.
Install dependencies in your environment first, then rerun.
EOF
  exit 1
fi

VIDEO_ID="$(python3 - "$VIDEO_INPUT" <<'PY'
import re
import sys
from urllib.parse import parse_qs, urlparse

value = sys.argv[1].strip()
if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
    print(value)
    raise SystemExit(0)

try:
    parsed = urlparse(value)
except Exception:
    print("")
    raise SystemExit(0)

host = (parsed.netloc or "").lower()
path = parsed.path or ""

if "youtu.be" in host:
    candidate = path.lstrip("/").split("/")[0]
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
        print(candidate)
        raise SystemExit(0)

if "youtube.com" in host:
    query = parse_qs(parsed.query or "")
    if "v" in query and query["v"]:
        candidate = query["v"][0]
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
            print(candidate)
            raise SystemExit(0)

    parts = [p for p in path.split("/") if p]
    for key in ("shorts", "embed", "live"):
        if key in parts:
            idx = parts.index(key)
            if idx + 1 < len(parts):
                candidate = parts[idx + 1]
                if re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
                    print(candidate)
                    raise SystemExit(0)

print("")
PY
)"

if [[ -z "$VIDEO_ID" ]]; then
  echo "ERROR: could not parse YouTube video id from: $VIDEO_INPUT"
  exit 1
fi

VIDEO_URL="https://www.youtube.com/watch?v=${VIDEO_ID}"
FULL_TXT="$REPORT_DIR/video_${VIDEO_ID}_transcript.txt"
FOCUS_TXT="$REPORT_DIR/video_${VIDEO_ID}_transcript_focus.txt"
ANALYSIS_MD="$REPORT_DIR/video_${VIDEO_ID}_analysis.md"
PLAYBOOK_MD="$REPORT_DIR/video_${VIDEO_ID}_playbook.md"
DAILY_STUDY_MD="$REPORT_DIR/${DATE_VALUE}_davinci_deep_study.md"
DAILY_EXPERIMENTS_MD="$REPORT_DIR/${DATE_VALUE}_davinci_experiments.md"

echo "Video ID: $VIDEO_ID"
echo "Extracting transcript..."
python3 - "$VIDEO_ID" "$FULL_TXT" <<'PY'
import sys
from youtube_transcript_api import YouTubeTranscriptApi

video_id = sys.argv[1]
out_path = sys.argv[2]

api = YouTubeTranscriptApi()
data = api.fetch(video_id, languages=["en", "pt", "en-US"]).to_raw_data()

with open(out_path, "w", encoding="utf-8") as f:
    for item in data:
        f.write(f"[{item['start']:.2f}] {item['text']}\n")

print(f"Transcript lines: {len(data)}")
PY

echo "Building focused transcript..."
python3 - "$FULL_TXT" "$FOCUS_TXT" <<'PY'
import re
import sys

src_path = sys.argv[1]
dst_path = sys.argv[2]

with open(src_path, "r", encoding="utf-8") as f:
    lines = f.read().splitlines()

kw = re.compile(
    r"\b(davinci|resolve|timeline|edit|cut|audio|fairlight|color|node|fusion|subtitle|caption|"
    r"export|render|proxy|deliver|grade|noise|voice|music|mix|transition|retention|hook|shorts?)\b",
    re.I,
)

indexes = []
for i, line in enumerate(lines):
    if kw.search(line):
        indexes.extend(range(max(0, i - 1), min(len(lines), i + 2)))

seen = set()
focused = []
for i in indexes:
    if i not in seen:
        seen.add(i)
        focused.append(lines[i])

focused = focused[:2200]
with open(dst_path, "w", encoding="utf-8") as f:
    f.write("\n".join(focused) + "\n")

print(f"Focused lines: {len(focused)}")
PY

echo "Running davinci_researcher..."
openclaw agent \
  --agent davinci_researcher \
  --message "Study this source deeply and learn from it for Ray's workflow: ${FOCUS_TXT} (derived from ${VIDEO_URL}). Deliver in English: (1) ${ANALYSIS_MD}, (2) ${PLAYBOOK_MD}. Also produce daily docs for ${DATE_VALUE}: ${DAILY_STUDY_MD} and ${DAILY_EXPERIMENTS_MD}. Update ${MANUAL_PATH} with evidence-backed improvements and confidence levels."

missing=0
for file in "$ANALYSIS_MD" "$PLAYBOOK_MD" "$MANUAL_PATH"; do
  if [[ ! -f "$file" ]]; then
    echo "MISSING: $file"
    missing=1
  fi
done

if [[ "$missing" -ne 0 ]]; then
  echo "ERROR: training cycle finished but expected files are missing."
  exit 2
fi

echo "Done."
echo "Generated:"
echo " - $ANALYSIS_MD"
echo " - $PLAYBOOK_MD"
echo " - $DAILY_STUDY_MD"
echo " - $DAILY_EXPERIMENTS_MD"
echo "Updated manual:"
echo " - $MANUAL_PATH"
