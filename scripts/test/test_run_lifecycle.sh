#!/usr/bin/env bash
# Test: Run lifecycle — start, poll, verify results
# Uses the 4-NPU reduce_scatter microbenchmark with reference cycle count.
# Requires: backend running, ASTRA-sim binary built.
set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BINARY="${REPO_ROOT}/frameworks/astra-sim/build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware"

# ── Helpers ──────────────────────────────────────────────────────────────
red()   { printf "\033[31m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
info()  { printf "\033[36m%s\033[0m\n" "$*"; }

FAILURES=0
pass() { green "PASS: $1"; }
fail() { red  "FAIL: $1"; FAILURES=$((FAILURES + 1)); }

validate_id() {
  [[ "$1" =~ ^[a-zA-Z0-9_-]{1,64}$ ]] || { fail "Unexpected id format: $1"; return 1; }
}

# ── Preflight ────────────────────────────────────────────────────────────
if ! curl -sf "${BACKEND_URL}/health" >/dev/null 2>&1; then
  red "Backend not reachable at ${BACKEND_URL}. Start it first."
  exit 1
fi

if [ ! -x "$BINARY" ]; then
  info "SKIP: ASTRA-sim binary not built at ${BINARY}"
  info "Run: FORCE=1 bash scripts/build_backends.sh"
  exit 0
fi

# ── Start a run (4-NPU reduce_scatter microbenchmark) ─────────────────────
info "Starting simulation run..."
RUN_BODY='{
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

RESP=$(curl -sf -X POST "${BACKEND_URL}/runs" \
  -H "Content-Type: application/json" -d "$RUN_BODY")

RUN_ID=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['run_id'])" 2>/dev/null)

if [ -z "$RUN_ID" ]; then
  fail "POST /runs did not return a run_id"
  exit 1
fi
validate_id "$RUN_ID" || exit 1
pass "POST /runs returned run_id=${RUN_ID}"

# ── Poll until succeeded or failed (30s timeout) ─────────────────────────
info "Polling run status (30s timeout)..."
STATUS="unknown"
for i in $(seq 1 60); do
  STATUS=$(curl -sf "${BACKEND_URL}/runs/${RUN_ID}" | \
    python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "unknown")

  if [ "$STATUS" = "succeeded" ] || [ "$STATUS" = "failed" ] || [ "$STATUS" = "cancelled" ]; then
    break
  fi
  sleep 0.5
done

if [ "$STATUS" = "succeeded" ]; then
  pass "Run completed with status: succeeded"
else
  fail "Run ended with status: ${STATUS} (expected succeeded)"
fi

# ── Verify results: summary ──────────────────────────────────────────────
info "Verifying results..."
SUMMARY=$(curl -sf "${BACKEND_URL}/results/${RUN_ID}/summary")

# NPU count
NPU_COUNT=$(echo "$SUMMARY" | python3 -c "import sys,json; print(json.load(sys.stdin)['npu_count'])" 2>/dev/null || echo "0")
if [ "$NPU_COUNT" = "4" ]; then
  pass "Summary npu_count is 4"
else
  fail "Summary npu_count is ${NPU_COUNT} (expected 4)"
fi

# End-to-end cycles (reference: 22240 for reduce_scatter 4NPU 1MB)
E2E=$(echo "$SUMMARY" | python3 -c "import sys,json; print(json.load(sys.stdin)['end_to_end_cycles'])" 2>/dev/null || echo "0")
if [ "$E2E" = "22240" ]; then
  pass "Summary end_to_end_cycles is 22240 (reference match)"
else
  fail "Summary end_to_end_cycles is ${E2E} (expected 22240)"
fi

# ── Verify results: per_npu stats ─────────────────────────────────────────
STATS=$(curl -sf "${BACKEND_URL}/results/${RUN_ID}/stats?view=per_npu")
ROW_COUNT=$(echo "$STATS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

if [ "$ROW_COUNT" = "4" ]; then
  pass "Per-NPU stats has 4 rows"
else
  fail "Per-NPU stats has ${ROW_COUNT} rows (expected 4)"
fi

# ── Verify results: timeline ──────────────────────────────────────────────
TIMELINE=$(curl -sf "${BACKEND_URL}/results/${RUN_ID}/timeline.json")

if echo "$TIMELINE" | grep -q "traceEvents"; then
  pass "Timeline contains traceEvents"
else
  fail "Timeline missing traceEvents"
fi

# ── Verify results: spec ──────────────────────────────────────────────────
SPEC=$(curl -sf "${BACKEND_URL}/results/${RUN_ID}/spec")

if echo "$SPEC" | grep -q "bundle"; then
  pass "Spec contains bundle"
else
  fail "Spec missing bundle"
fi

# ── Verify: GET /runs/{id} metadata ───────────────────────────────────────
META=$(curl -sf "${BACKEND_URL}/runs/${RUN_ID}")

if echo "$META" | grep -q "log_dir"; then
  pass "Run metadata contains log_dir"
else
  fail "Run metadata missing log_dir"
fi

# ── Verify: GET /runs lists our run ───────────────────────────────────────
RUNS_LIST=$(curl -sf "${BACKEND_URL}/runs")

if echo "$RUNS_LIST" | grep -q "$RUN_ID"; then
  pass "GET /runs lists our run"
else
  fail "GET /runs does not list our run"
fi

# ── Summary ──────────────────────────────────────────────────────────────
echo ""
if [ "$FAILURES" -eq 0 ]; then
  green "All run lifecycle tests passed."
  exit 0
else
  red "${FAILURES} test(s) failed."
  exit 1
fi
