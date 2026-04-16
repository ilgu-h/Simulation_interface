#!/usr/bin/env bash
# Test: Full end-to-end pipeline
# Starts backend, generates workload, runs simulation, verifies results, compares runs.
# Requires: ASTRA-sim binary built.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PORT="${TEST_PORT:-8099}"
URL="http://localhost:${PORT}"
BINARY="${REPO_ROOT}/frameworks/astra-sim/build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware"
PID=""

# ── Helpers ──────────────────────────────────────────────────────────────
red()   { printf "\033[31m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
info()  { printf "\033[36m%s\033[0m\n" "$*"; }

FAILURES=0
TOTAL=0
pass() { green "PASS: $1"; TOTAL=$((TOTAL + 1)); }
fail() { red  "FAIL: $1"; FAILURES=$((FAILURES + 1)); TOTAL=$((TOTAL + 1)); }

validate_id() {
  [[ "$1" =~ ^[a-zA-Z0-9_-]{1,64}$ ]] || { fail "Unexpected id format: $1"; return 1; }
}

cleanup() {
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null || true
    wait "$PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# ── Preflight ────────────────────────────────────────────────────────────
if [ ! -x "$BINARY" ]; then
  info "SKIP: ASTRA-sim binary not built at ${BINARY}"
  info "Run: FORCE=1 bash scripts/build_backends.sh"
  exit 0
fi

# ── Start backend ────────────────────────────────────────────────────────
info "Starting backend on port ${PORT}..."
cd "${REPO_ROOT}/backend"
"${REPO_ROOT}/.venv-backend/bin/python" -m uvicorn app.main:app \
  --port "${PORT}" --log-level warning &
PID=$!

for i in $(seq 1 30); do
  if curl -sf "${URL}/health" >/dev/null 2>&1; then break; fi
  if [ "$i" -eq 30 ]; then fail "Backend startup timeout"; exit 1; fi
  sleep 0.5
done
pass "Backend started on port ${PORT}"

# ── Helper: wait for run completion ───────────────────────────────────────
wait_for_run() {
  local run_id=$1
  local timeout=${2:-30}
  [[ "$timeout" =~ ^[0-9]+$ ]] || { echo "timeout"; return; }
  local status="unknown"
  for i in $(seq 1 $((timeout * 2))); do
    status=$(curl -sf "${URL}/runs/${run_id}" | \
      python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "unknown")
    if [ "$status" = "succeeded" ] || [ "$status" = "failed" ] || [ "$status" = "cancelled" ]; then
      echo "$status"
      return
    fi
    sleep 0.5
  done
  echo "timeout"
}

# ══════════════════════════════════════════════════════════════════════════
# Phase 1: Run with bundled microbenchmark (50 GB/s bandwidth)
# ══════════════════════════════════════════════════════════════════════════
info "Phase 1: Running reduce_scatter microbenchmark (50 GB/s)..."

RUN_A_BODY='{
  "workload": {
    "kind": "existing",
    "value": "frameworks/astra-sim/examples/workload/microbenchmarks/reduce_scatter/4npus_1MB/reduce_scatter"
  },
  "bundle": {
    "backend": "analytical_cu",
    "system": {
      "scheduling-policy": "LIFO",
      "endpoint-delay": 10,
      "active-chunks-per-dimension": 1,
      "preferred-dataset-splits": 4,
      "all-reduce-implementation": ["ring"],
      "all-gather-implementation": ["ring"],
      "reduce-scatter-implementation": ["ring"],
      "all-to-all-implementation": ["ring"],
      "collective-optimization": "localBWAware",
      "local-mem-bw": 1600,
      "boost-mode": 0
    },
    "network": {
      "topology": ["Ring"],
      "npus_count": [4],
      "bandwidth": [50.0],
      "latency": [500.0]
    },
    "memory": { "memory-type": "NO_MEMORY_EXPANSION" },
    "expected_npus": 4
  }
}'

RESP_A=$(curl -sf -X POST "${URL}/runs" -H "Content-Type: application/json" -d "$RUN_A_BODY")
RUN_ID_A=$(echo "$RESP_A" | python3 -c "import sys,json; print(json.load(sys.stdin)['run_id'])" 2>/dev/null)

if [ -n "$RUN_ID_A" ] && validate_id "$RUN_ID_A"; then
  pass "Run A started: ${RUN_ID_A}"
else
  fail "Run A failed to start or invalid run_id"
  exit 1
fi

STATUS_A=$(wait_for_run "$RUN_ID_A" 30)
if [ "$STATUS_A" = "succeeded" ]; then
  pass "Run A succeeded"
else
  fail "Run A status: ${STATUS_A}"
fi

# Verify summary
SUMMARY_A=$(curl -sf "${URL}/results/${RUN_ID_A}/summary")
E2E_A=$(echo "$SUMMARY_A" | python3 -c "import sys,json; print(json.load(sys.stdin)['end_to_end_cycles'])" 2>/dev/null || echo "0")
if [ "$E2E_A" = "22240" ]; then
  pass "Run A: end_to_end_cycles = 22240 (reference match)"
else
  fail "Run A: end_to_end_cycles = ${E2E_A} (expected 22240)"
fi

# Verify per-NPU stats
STATS_A=$(curl -sf "${URL}/results/${RUN_ID_A}/stats?view=per_npu")
ROWS_A=$(echo "$STATS_A" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
if [ "$ROWS_A" = "4" ]; then
  pass "Run A: per_npu has 4 rows"
else
  fail "Run A: per_npu has ${ROWS_A} rows"
fi

# Verify per-collective stats
COLL_A=$(curl -sf "${URL}/results/${RUN_ID_A}/stats?view=per_collective")
if echo "$COLL_A" | python3 -c "import sys,json; assert len(json.load(sys.stdin)) > 0" 2>/dev/null; then
  pass "Run A: per_collective has data"
else
  fail "Run A: per_collective is empty"
fi

# Verify timeline
TIMELINE_A=$(curl -sf "${URL}/results/${RUN_ID_A}/timeline.json")
if echo "$TIMELINE_A" | grep -q "traceEvents"; then
  pass "Run A: timeline has traceEvents"
else
  fail "Run A: timeline missing traceEvents"
fi

# Verify spec
SPEC_A=$(curl -sf "${URL}/results/${RUN_ID_A}/spec")
if echo "$SPEC_A" | grep -q "bundle"; then
  pass "Run A: spec has bundle"
else
  fail "Run A: spec missing bundle"
fi

# Verify logs endpoint
HTTP_LOG=$(curl -sf -o /dev/null -w "%{http_code}" "${URL}/results/${RUN_ID_A}/logs/events.log" 2>/dev/null || echo "000")
if [ "$HTTP_LOG" = "200" ]; then
  pass "Run A: events log accessible"
else
  fail "Run A: events log returned ${HTTP_LOG}"
fi

# ══════════════════════════════════════════════════════════════════════════
# Phase 2: Run with different bandwidth (100 GB/s)
# ══════════════════════════════════════════════════════════════════════════
info "Phase 2: Running same workload with 100 GB/s bandwidth..."

RUN_B_BODY=$(echo "$RUN_A_BODY" | python3 -c "
import sys, json
b = json.load(sys.stdin)
b['bundle']['network']['bandwidth'] = [100.0]
print(json.dumps(b))
")

RESP_B=$(curl -sf -X POST "${URL}/runs" -H "Content-Type: application/json" -d "$RUN_B_BODY")
RUN_ID_B=$(echo "$RESP_B" | python3 -c "import sys,json; print(json.load(sys.stdin)['run_id'])" 2>/dev/null)

if [ -n "$RUN_ID_B" ] && validate_id "$RUN_ID_B"; then
  pass "Run B started: ${RUN_ID_B}"
else
  fail "Run B failed to start or invalid run_id"
  exit 1
fi

STATUS_B=$(wait_for_run "$RUN_ID_B" 30)
if [ "$STATUS_B" = "succeeded" ]; then
  pass "Run B succeeded"
else
  fail "Run B status: ${STATUS_B}"
fi

# ══════════════════════════════════════════════════════════════════════════
# Phase 3: Compare runs
# ══════════════════════════════════════════════════════════════════════════
info "Phase 3: Comparing Run A vs Run B..."

COMPARE=$(curl -sf "${URL}/results/${RUN_ID_A}/compare?with=${RUN_ID_B}")

# Delta should be non-zero (different bandwidth → different cycles)
DELTA=$(echo "$COMPARE" | python3 -c "import sys,json; print(json.load(sys.stdin)['e2e_delta_cycles'])" 2>/dev/null || echo "0")
if [ "$DELTA" != "0" ]; then
  pass "Compare: e2e_delta_cycles = ${DELTA} (non-zero, different bandwidth)"
else
  fail "Compare: e2e_delta_cycles is 0 (expected non-zero)"
fi

# Config diffs should contain bandwidth
if echo "$COMPARE" | grep -q "bandwidth"; then
  pass "Compare: config_diffs contains bandwidth"
else
  fail "Compare: config_diffs missing bandwidth"
fi

# Delta percentage should exist
DELTA_PCT=$(echo "$COMPARE" | python3 -c "import sys,json; print(json.load(sys.stdin)['e2e_delta_pct'])" 2>/dev/null || echo "none")
if [ "$DELTA_PCT" != "none" ] && [ "$DELTA_PCT" != "0" ]; then
  pass "Compare: e2e_delta_pct = ${DELTA_PCT}%"
else
  fail "Compare: e2e_delta_pct not found or zero"
fi

# ══════════════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════════════
echo ""
echo "─────────────────────────────────────────"
if [ "$FAILURES" -eq 0 ]; then
  green "All ${TOTAL} full pipeline tests passed."
  exit 0
else
  red "${FAILURES}/${TOTAL} test(s) failed."
  exit 1
fi
