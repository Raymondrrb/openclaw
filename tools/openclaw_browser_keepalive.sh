#!/bin/zsh
set -euo pipefail

# LaunchAgents have a minimal PATH; ensure openclaw is resolvable.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

STATUS_JSON="$(openclaw browser status --json 2>/dev/null || echo '{}')"

/usr/bin/python3 - "$STATUS_JSON" <<'PY'
import json, sys
raw = sys.argv[1] if len(sys.argv) > 1 else '{}'
try:
    s = json.loads(raw)
except Exception:
    print('bad_status_json')
    sys.exit(0)

attach_only = bool(s.get('attachOnly', True))
running = bool(s.get('running', False))

# We only auto-start in non-attach mode (stable mode).
if (not attach_only) and (not running):
    print('starting_browser')
    sys.exit(42)
print('ok')
PY
RC=$?

if [[ "$RC" -eq 42 ]]; then
  openclaw browser start --json >/dev/null 2>&1 || true
fi
