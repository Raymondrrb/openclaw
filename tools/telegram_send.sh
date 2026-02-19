#!/bin/zsh
set -euo pipefail

# Helper for sending Telegram messages via OpenClaw using the configured account.
# Avoids the common "Telegram bot token missing" error when multiple accounts are configured.

ACCOUNT="${OPENCLAW_TELEGRAM_ACCOUNT:-tg_main}"

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <chat_id_or_username> <message...>" >&2
  echo "Example: $0 5853624777 \"hello\"" >&2
  exit 2
fi

TARGET="$1"
shift
MESSAGE="$*"

openclaw message send \
  --channel telegram \
  --account "$ACCOUNT" \
  --target "$TARGET" \
  --message "$MESSAGE"

