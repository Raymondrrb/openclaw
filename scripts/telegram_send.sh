#!/usr/bin/env bash
# RayVault — Send a message to Telegram via Bot API (HTML + <pre>).
#
# Accepts either a text argument or a file path.
# Uses HTML parse_mode with <pre> to preserve alignment and avoid
# MarkdownV2 escape hell. Truncates to 3800 chars (Telegram limit
# is 4096), preserving the end of the message (where the verdict is).
#
# Env vars required:
#   TELEGRAM_BOT_TOKEN
#   TELEGRAM_CHAT_ID
#
# Usage:
#   ./scripts/telegram_send.sh "Hello from RayVault"
#   ./scripts/telegram_send.sh state/status_summary.txt
set -euo pipefail

BOT_TOKEN="${TELEGRAM_BOT_TOKEN:?missing TELEGRAM_BOT_TOKEN}"
CHAT_ID="${TELEGRAM_CHAT_ID:?missing TELEGRAM_CHAT_ID}"
INPUT="${1:?missing message or file path}"
MAX_CHARS="${2:-3800}"

# If input is a file, read it; otherwise treat as literal message
if [ -f "$INPUT" ]; then
    RAW="$(cat "$INPUT")"
else
    RAW="$INPUT"
fi

# HTML-escape and truncate (preserve the end = verdict + history)
BODY="$(python3 -c "
import html, sys
s = sys.argv[1]
mx = int(sys.argv[2])
if len(s) > mx:
    s = '...(truncated)...\n' + s[-mx:]
print(html.escape(s), end='')
" "$RAW" "$MAX_CHARS")"

curl -sS "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
  -d "chat_id=${CHAT_ID}" \
  --data-urlencode "text=<pre>${BODY}</pre>" \
  -d "parse_mode=HTML" >/dev/null

echo "Sent to Telegram (${#BODY} chars)"
