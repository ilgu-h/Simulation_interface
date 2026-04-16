#!/usr/bin/env bash
# Test: Backend health check
# Starts uvicorn on a test port, verifies /health endpoint responds correctly.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PORT="${TEST_PORT:-8099}"
URL="http://localhost:${PORT}"
PID=""

# ── Helpers ──────────────────────────────────────────────────────────────
red()   { printf "\033[31m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
info()  { printf "\033[36m%s\033[0m\n" "$*"; }

cleanup() {
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null || true
    wait "$PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

pass() { green "PASS: $1"; }
fail() { red  "FAIL: $1"; FAILURES=$((FAILURES + 1)); }

FAILURES=0

# ── Start backend ────────────────────────────────────────────────────────
info "Starting backend on port ${PORT}..."
cd "${REPO_ROOT}/backend"
"${REPO_ROOT}/.venv-backend/bin/python" -m uvicorn app.main:app \
  --port "${PORT}" --log-level warning &
PID=$!

# Wait for startup (up to 15 seconds)
for i in $(seq 1 30); do
  if curl -sf "${URL}/health" >/dev/null 2>&1; then
    break
  fi
  if [ "$i" -eq 30 ]; then
    fail "Backend did not start within 15 seconds"
    exit 1
  fi
  sleep 0.5
done
info "Backend started (PID=${PID})"

# ── Test: GET /health ────────────────────────────────────────────────────
RESP=$(curl -sf "${URL}/health")
if echo "$RESP" | grep -q '"status"'; then
  pass "GET /health returns status field"
else
  fail "GET /health missing status field (got: ${RESP})"
fi

if echo "$RESP" | grep -q '"ok"'; then
  pass "GET /health status is ok"
else
  fail "GET /health status is not ok (got: ${RESP})"
fi

# ── Summary ──────────────────────────────────────────────────────────────
echo ""
if [ "$FAILURES" -eq 0 ]; then
  green "All health checks passed."
  exit 0
else
  red "${FAILURES} check(s) failed."
  exit 1
fi
