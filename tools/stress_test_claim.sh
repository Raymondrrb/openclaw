#!/usr/bin/env bash
# Quick stress test: 2 workers race to claim_next simultaneously.
#
# Usage:
#   export SUPABASE_URL="https://xxxxx.supabase.co"
#   export SUPABASE_SERVICE_KEY="your_service_role_key"
#   bash tools/stress_test_claim.sh
#
# Expected: one worker gets a run (JSON with id), the other gets null/empty.
# If both get the same run → SKIP LOCKED is broken.

set -euo pipefail

: "${SUPABASE_URL:?Set SUPABASE_URL}"
: "${SUPABASE_SERVICE_KEY:?Set SUPABASE_SERVICE_KEY}"

RPC="$SUPABASE_URL/rest/v1/rpc/rpc_claim_next_run"

TOKEN_A=$(python3 -c "import uuid; print(uuid.uuid4())")
TOKEN_B=$(python3 -c "import uuid; print(uuid.uuid4())")

echo "=== RayVault Quick Claim Test ==="
echo "Target: $SUPABASE_URL"
echo "Token A: ${TOKEN_A:0:12}..."
echo "Token B: ${TOKEN_B:0:12}..."
echo ""

call_rpc () {
  local worker="$1"
  local token="$2"
  curl -sS "$RPC" \
    -H "apikey: $SUPABASE_SERVICE_KEY" \
    -H "Authorization: Bearer $SUPABASE_SERVICE_KEY" \
    -H "Content-Type: application/json" \
    --data "{\"p_worker_id\":\"$worker\",\"p_lock_token\":\"$token\",\"p_lease_minutes\":10,\"p_task_type\":null}"
}

# Fire both in parallel
call_rpc "Mac-Ray-01" "$TOKEN_A" > /tmp/claim_r1.json &
PID1=$!
call_rpc "Mac-Ray-02" "$TOKEN_B" > /tmp/claim_r2.json &
PID2=$!
wait $PID1 $PID2

echo "=== Mac-Ray-01 ==="
cat /tmp/claim_r1.json
echo ""
echo "=== Mac-Ray-02 ==="
cat /tmp/claim_r2.json
echo ""

# Parse results
R1=$(cat /tmp/claim_r1.json | tr -d '"')
R2=$(cat /tmp/claim_r2.json | tr -d '"')

echo ""
if [ "$R1" = "null" ] && [ "$R2" = "null" ]; then
  echo "WARN: Both got null. No eligible runs in DB. Create a 'running' run first."
  exit 1
elif [ "$R1" != "null" ] && [ "$R2" != "null" ]; then
  if [ "$R1" = "$R2" ]; then
    echo "FAIL: Both workers claimed the SAME run! SKIP LOCKED broken."
    exit 1
  else
    echo "OK: Both claimed, but DIFFERENT runs (DB has multiple eligible runs)."
    echo "  For clean test, ensure only 1 running/approved run exists."
  fi
else
  WINNER=""
  [ "$R1" != "null" ] && WINNER="Mac-Ray-01 -> $R1"
  [ "$R2" != "null" ] && WINNER="Mac-Ray-02 -> $R2"
  echo "PASS: Exclusive claim works."
  echo "  Winner: $WINNER"
fi

# Cleanup
rm -f /tmp/claim_r1.json /tmp/claim_r2.json
