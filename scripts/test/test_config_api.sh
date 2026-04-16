#!/usr/bin/env bash
# Test: Config validation and materialization API endpoints
# Tests POST /configs/validate (valid, NPU mismatch, Switch error) and POST /configs/materialize.
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

# ── Preflight ────────────────────────────────────────────────────────────
if ! curl -sf "${BACKEND_URL}/health" >/dev/null 2>&1; then
  red "Backend not reachable at ${BACKEND_URL}. Start it first."
  exit 1
fi

# ── Shared config bundle ─────────────────────────────────────────────────
VALID_BUNDLE='{
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
}'

# ── Test 1: Valid config → ok: true ───────────────────────────────────────
info "Testing POST /configs/validate (valid config)..."
RESP=$(curl -sf -X POST "${BACKEND_URL}/configs/validate" \
  -H "Content-Type: application/json" -d "$VALID_BUNDLE")

if echo "$RESP" | python3 -c "import sys,json; assert json.load(sys.stdin)['ok'] == True" 2>/dev/null; then
  pass "Valid config returns ok: true"
else
  fail "Valid config did not return ok: true (got: ${RESP})"
fi

if echo "$RESP" | python3 -c "import sys,json; assert json.load(sys.stdin)['total_npus'] == 4" 2>/dev/null; then
  pass "total_npus is 4"
else
  fail "total_npus is not 4"
fi

# ── Test 2: NPU mismatch → ok: false ─────────────────────────────────────
info "Testing POST /configs/validate (NPU mismatch)..."
MISMATCH_BUNDLE=$(echo "$VALID_BUNDLE" | python3 -c "
import sys, json
b = json.load(sys.stdin)
b['expected_npus'] = 8
print(json.dumps(b))
")

RESP=$(curl -sf -X POST "${BACKEND_URL}/configs/validate" \
  -H "Content-Type: application/json" -d "$MISMATCH_BUNDLE")

if echo "$RESP" | python3 -c "import sys,json; assert json.load(sys.stdin)['ok'] == False" 2>/dev/null; then
  pass "NPU mismatch returns ok: false"
else
  fail "NPU mismatch did not return ok: false"
fi

if echo "$RESP" | grep -qi "error\|mismatch"; then
  pass "NPU mismatch response contains error message"
else
  fail "NPU mismatch response missing error message"
fi

# ── Test 3: Switch with 1 NPU → error ────────────────────────────────────
info "Testing POST /configs/validate (Switch with 1 NPU)..."
SWITCH_BUNDLE=$(echo "$VALID_BUNDLE" | python3 -c "
import sys, json
b = json.load(sys.stdin)
b['network']['topology'] = ['Switch']
b['network']['npus_count'] = [1]
b['expected_npus'] = 1
print(json.dumps(b))
")

RESP=$(curl -sf -X POST "${BACKEND_URL}/configs/validate" \
  -H "Content-Type: application/json" -d "$SWITCH_BUNDLE")

if echo "$RESP" | python3 -c "
import sys, json
data = json.load(sys.stdin)
issues = data.get('issues', [])
has_error = any(i['severity'] == 'error' for i in issues)
assert has_error
" 2>/dev/null; then
  pass "Switch with 1 NPU produces error"
else
  fail "Switch with 1 NPU did not produce error"
fi

# ── Test 4: Materialize → run_id + files ──────────────────────────────────
info "Testing POST /configs/materialize..."
RESP=$(curl -sf -X POST "${BACKEND_URL}/configs/materialize" \
  -H "Content-Type: application/json" -d "$VALID_BUNDLE")

if echo "$RESP" | grep -q "run_id"; then
  pass "Materialize returns run_id"
else
  fail "Materialize missing run_id"
fi

# Extract run_id and verify files
RUN_ID=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('run_id',''))" 2>/dev/null || true)

if [ -n "$RUN_ID" ]; then
  CONFIG_DIR="${REPO_ROOT}/runs/${RUN_ID}/configs"

  if [ -f "${CONFIG_DIR}/network.yml" ]; then
    pass "network.yml exists on disk"
  else
    fail "network.yml not found at ${CONFIG_DIR}/network.yml"
  fi

  if [ -f "${CONFIG_DIR}/system.json" ]; then
    pass "system.json exists on disk"
  else
    fail "system.json not found"
  fi

  if [ -f "${CONFIG_DIR}/memory.json" ]; then
    pass "memory.json exists on disk"
  else
    fail "memory.json not found"
  fi

  # Verify network.yml contains Ring topology
  if grep -q "Ring" "${CONFIG_DIR}/network.yml" 2>/dev/null; then
    pass "network.yml contains Ring topology"
  else
    fail "network.yml missing Ring topology"
  fi
fi

# ── Test 5: GET /backends ─────────────────────────────────────────────────
info "Testing GET /backends..."
RESP=$(curl -sf "${BACKEND_URL}/backends")

if echo "$RESP" | grep -q "analytical_cu"; then
  pass "GET /backends contains analytical_cu"
else
  fail "GET /backends missing analytical_cu"
fi

if echo "$RESP" | grep -q "analytical_ca"; then
  pass "GET /backends contains analytical_ca"
else
  fail "GET /backends missing analytical_ca"
fi

# ── Summary ──────────────────────────────────────────────────────────────
echo ""
if [ "$FAILURES" -eq 0 ]; then
  green "All config API tests passed."
  exit 0
else
  red "${FAILURES} test(s) failed."
  exit 1
fi
