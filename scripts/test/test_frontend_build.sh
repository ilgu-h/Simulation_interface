#!/usr/bin/env bash
# Test: Frontend TypeScript build and lint
# Verifies that the frontend compiles without errors and passes ESLint.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FRONTEND="${REPO_ROOT}/frontend"

# ── Helpers ──────────────────────────────────────────────────────────────
red()   { printf "\033[31m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
info()  { printf "\033[36m%s\033[0m\n" "$*"; }

FAILURES=0
pass() { green "PASS: $1"; }
fail() { red  "FAIL: $1"; FAILURES=$((FAILURES + 1)); }

cd "$FRONTEND"

# ── Install dependencies ─────────────────────────────────────────────────
info "Installing frontend dependencies..."
if pnpm install --frozen-lockfile 2>/dev/null || pnpm install; then
  pass "pnpm install"
else
  fail "pnpm install"
  exit 1
fi

# ── Lint ──────────────────────────────────────────────────────────────────
info "Running ESLint..."
if pnpm lint 2>&1; then
  pass "pnpm lint (ESLint)"
else
  fail "pnpm lint (ESLint)"
fi

# ── Build (includes TypeScript type-check) ────────────────────────────────
info "Building frontend (TypeScript + Next.js)..."
START=$(date +%s)
if pnpm build 2>&1; then
  END=$(date +%s)
  pass "pnpm build (completed in $((END - START))s)"
else
  fail "pnpm build"
fi

# ── Summary ──────────────────────────────────────────────────────────────
echo ""
if [ "$FAILURES" -eq 0 ]; then
  green "All frontend checks passed."
  exit 0
else
  red "${FAILURES} check(s) failed."
  exit 1
fi
