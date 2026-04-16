#!/usr/bin/env bash
# Test: Workload API endpoints
# Tests GET /workloads/library, GET /workloads/presets, POST /workloads/generate.
# Requires: backend running at BACKEND_URL (default http://localhost:8000).
set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# ── Helpers ──────────────────────────────────────────────────────────────
red()   { printf "\033[31m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
info()  { printf "\033[36m%s\033[0m\n" "$*"; }

FAILURES=0
pass() { green "PASS: $1"; }
fail() { red  "FAIL: $1"; FAILURES=$((FAILURES + 1)); }

# ── Preflight: check backend is reachable ────────────────────────────────
info "Checking backend at ${BACKEND_URL}..."
if ! curl -sf "${BACKEND_URL}/health" >/dev/null 2>&1; then
  red "Backend not reachable at ${BACKEND_URL}. Start it first."
  exit 1
fi

# ── Test 1: GET /workloads/library ────────────────────────────────────────
info "Testing GET /workloads/library..."
RESP=$(curl -sf "${BACKEND_URL}/workloads/library")
HTTP=$(curl -sf -o /dev/null -w "%{http_code}" "${BACKEND_URL}/workloads/library")

if [ "$HTTP" = "200" ]; then
  pass "GET /workloads/library returns 200"
else
  fail "GET /workloads/library returned ${HTTP}"
fi

if echo "$RESP" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
  pass "GET /workloads/library returns valid JSON"
else
  fail "GET /workloads/library is not valid JSON"
fi

if echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); assert isinstance(d, list)" 2>/dev/null; then
  pass "GET /workloads/library returns a JSON array"
else
  fail "GET /workloads/library is not a JSON array"
fi

# ── Test 2: GET /workloads/presets ────────────────────────────────────────
info "Testing GET /workloads/presets..."
RESP=$(curl -sf "${BACKEND_URL}/workloads/presets")

if echo "$RESP" | grep -q "llama-7b"; then
  pass "GET /workloads/presets contains llama-7b"
else
  fail "GET /workloads/presets missing llama-7b"
fi

if echo "$RESP" | grep -q "llama-70b"; then
  pass "GET /workloads/presets contains llama-70b"
else
  fail "GET /workloads/presets missing llama-70b"
fi

if echo "$RESP" | grep -q "gpt3-175b"; then
  pass "GET /workloads/presets contains gpt3-175b"
else
  fail "GET /workloads/presets missing gpt3-175b"
fi

# ── Test 3: POST /workloads/generate (debug model for speed) ──────────────
info "Testing POST /workloads/generate (debug model, 1 NPU)..."
GENERATE_BODY='{
  "model_type": "debug",
  "dp": 1, "tp": 1, "sp": 1, "pp": 1, "ep": 1,
  "dvocal": 1000, "dmodel": 64, "dff": 128,
  "head": 4, "kvhead": 4, "num_stacks": 1,
  "experts": 8, "kexperts": 2,
  "batch": 1, "micro_batch": -1, "seq": 32,
  "weight_sharded": false, "activation_recompute": false,
  "tpsp": false, "mixed_precision": false,
  "chakra_schema_version": "v0.0.4"
}'

HTTP=$(curl -sf -o /tmp/sim_gen_resp.json -w "%{http_code}" \
  -X POST "${BACKEND_URL}/workloads/generate" \
  -H "Content-Type: application/json" \
  -d "$GENERATE_BODY")

if [ "$HTTP" = "200" ]; then
  pass "POST /workloads/generate returns 200"
else
  fail "POST /workloads/generate returned ${HTTP}"
  cat /tmp/sim_gen_resp.json 2>/dev/null || true
fi

if [ -f /tmp/sim_gen_resp.json ]; then
  RESP=$(cat /tmp/sim_gen_resp.json)

  if echo "$RESP" | grep -q "run_id"; then
    pass "Response contains run_id"
  else
    fail "Response missing run_id"
  fi

  if echo "$RESP" | grep -q "trace_files"; then
    pass "Response contains trace_files"
  else
    fail "Response missing trace_files"
  fi

  # Verify trace files exist on disk
  RUN_ID=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('run_id',''))" 2>/dev/null || true)
  if [ -n "$RUN_ID" ]; then
    TRACES_DIR="${REPO_ROOT}/runs/${RUN_ID}/traces"
    if [ -d "$TRACES_DIR" ]; then
      ET_COUNT=$(find "$TRACES_DIR" -name "*.et" | wc -l)
      if [ "$ET_COUNT" -gt 0 ]; then
        pass "Found ${ET_COUNT} .et file(s) on disk at runs/${RUN_ID}/traces/"
      else
        fail "No .et files found in ${TRACES_DIR}"
      fi
    else
      fail "Traces directory not found: ${TRACES_DIR}"
    fi
  fi
fi

rm -f /tmp/sim_gen_resp.json

# ── Summary ──────────────────────────────────────────────────────────────
echo ""
if [ "$FAILURES" -eq 0 ]; then
  green "All workload API tests passed."
  exit 0
else
  red "${FAILURES} test(s) failed."
  exit 1
fi
