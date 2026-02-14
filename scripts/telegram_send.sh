#!/usr/bin/env bash
# RayVault — Send a message to Telegram via Bot API (MarkdownV2).
#
# Env vars required:
#   TELEGRAM_BOT_TOKEN
#   TELEGRAM_CHAT_ID
#
# Usage:
#   ./scripts/telegram_send.sh "Hello from RayVault"
set -euo pipefail

BOT_TOKEN="${TELEGRAM_BOT_TOKEN:?missing TELEGRAM_BOT_TOKEN}"
CHAT_ID="${TELEGRAM_CHAT_ID:?missing TELEGRAM_CHAT_ID}"
MSG="${1:?missing message argument}"

# Escape MarkdownV2 special characters
escape_md() {
  python3 -c "
import re, sys
s = sys.stdin.read()
s = re.sub(r'([_*\[\]()~\`>#+\-=|{}.!])', r'\\\\\1', s)
print(s, end='')
"
}

ESCAPED="$(printf "%s" "$MSG" | escape_md)"

curl -sS "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
  -d "chat_id=${CHAT_ID}" \
  -d "text=${ESCAPED}" \
  -d "parse_mode=MarkdownV2" >/dev/null
