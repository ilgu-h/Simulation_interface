#!/usr/bin/env bash
# Build ASTRA-sim backends. Currently builds the analytical backend
# (which produces both AstraSim_Analytical_Congestion_Unaware and
# AstraSim_Analytical_Congestion_Aware binaries via a single CMake project).
#
# Usage:
#   bash scripts/build_backends.sh                # analytical
#   bash scripts/build_backends.sh analytical
#   FORCE=1 bash scripts/build_backends.sh        # rebuild even if binaries exist

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="${1:-analytical}"

log()  { printf '\033[1;36m[build]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[build]\033[0m %s\n' "$*" >&2; exit 1; }

case "${BACKEND}" in
  analytical)
    BUILD_SH="${REPO_ROOT}/frameworks/astra-sim/build/astra_analytical/build.sh"
    BIN_DIR="${REPO_ROOT}/frameworks/astra-sim/build/astra_analytical/build/bin"
    SENTINEL_BIN="${BIN_DIR}/AstraSim_Analytical_Congestion_Unaware"
    ;;
  ns3|garnet|htsim)
    fail "Backend '${BACKEND}' not enabled in Phase 0 (skipped to keep clones small)."
    ;;
  *)
    fail "Unknown backend: ${BACKEND}"
    ;;
esac

if [[ -x "${SENTINEL_BIN}" && "${FORCE:-0}" != "1" ]]; then
  log "Backend '${BACKEND}' already built (FORCE=1 to rebuild)."
  exit 0
fi

log "Building ASTRA-sim backend: ${BACKEND}"
bash "${BUILD_SH}"
[[ -x "${SENTINEL_BIN}" ]] || fail "Build finished but binary not found at ${SENTINEL_BIN}"
log "Build OK: ${SENTINEL_BIN}"
