#!/bin/zsh
set -euo pipefail

BRAVE_BIN="/Applications/Brave Browser 2.app/Contents/MacOS/Brave Browser"
TARGET_URL="${1:-https://vercel.com/login}"
MODE="${2:-isolated}"

# MODE:
# - isolated: dedicated stable profile just for Vercel troubleshooting/login.
# - default: use normal Brave profile, but with safe rendering flags for this launch.
SAFE_PROFILE_DIR="$HOME/.config/newproject/vercel-safe-brave"

if [[ "$MODE" == "default" ]]; then
  PROFILE_ARGS=()
  PROFILE_DESC="default Brave profile"
else
  mkdir -p "$SAFE_PROFILE_DIR"
  PROFILE_ARGS=(--user-data-dir="$SAFE_PROFILE_DIR")
  PROFILE_DESC="$SAFE_PROFILE_DIR"
fi

nohup "$BRAVE_BIN" \
  "${PROFILE_ARGS[@]}" \
  --no-first-run \
  --disable-features=UseSkiaRenderer,Vulkan \
  --disable-extensions \
  --disable-gpu \
  --new-window \
  "$TARGET_URL" \
  >"$HOME/.config/newproject/vercel-safe-brave.nohup.out" 2>&1 &

echo "Opened URL in Brave safe mode."
echo "URL: $TARGET_URL"
echo "Mode: $MODE"
echo "Profile: $PROFILE_DESC"
