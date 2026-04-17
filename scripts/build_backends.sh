#!/usr/bin/env bash
# Build ASTRA-sim backends.
#   - analytical: produces AstraSim_Analytical_Congestion_Unaware +
#     AstraSim_Analytical_Congestion_Aware via a single CMake project.
#   - ns3 (opt-in, ENABLE_NS3=1): invokes astra-sim's ns-3 build.sh and
#     symlinks the versioned ns3 binary to a stable registry path.
#
# Usage:
#   bash scripts/build_backends.sh                  # analytical
#   bash scripts/build_backends.sh analytical
#   ENABLE_NS3=1 bash scripts/build_backends.sh ns3 # ns-3
#   FORCE=1 bash scripts/build_backends.sh          # rebuild even if built

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="${1:-analytical}"

log()  { printf '\033[1;36m[build]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[build]\033[0m %s\n' "$*" >&2; exit 1; }

BUILD_SH=""
SENTINEL_BIN=""

case "${BACKEND}" in
  analytical)
    BUILD_SH="${REPO_ROOT}/frameworks/astra-sim/build/astra_analytical/build.sh"
    BIN_DIR="${REPO_ROOT}/frameworks/astra-sim/build/astra_analytical/build/bin"
    SENTINEL_BIN="${BIN_DIR}/AstraSim_Analytical_Congestion_Unaware"
    ;;
  ns3)
    if [[ "${ENABLE_NS3:-0}" != "1" ]]; then
      fail "Backend 'ns3' requires ENABLE_NS3=1 (submodule + MPI opt-in)."
    fi
    NS3_DIR="${REPO_ROOT}/frameworks/astra-sim/extern/network_backend/ns-3"
    if [[ ! -d "${NS3_DIR}" ]] || [[ -z "$(ls -A "${NS3_DIR}" 2>/dev/null || true)" ]]; then
      fail "ns-3 submodule not initialized at ${NS3_DIR}. Run 'ENABLE_NS3=1 bash scripts/bootstrap.sh' first."
    fi
    BUILD_SH="${REPO_ROOT}/frameworks/astra-sim/build/astra_ns3/build.sh"
    BIN_DIR="${REPO_ROOT}/frameworks/astra-sim/build/astra_ns3/build/bin"
    SENTINEL_BIN="${BIN_DIR}/AstraSim_NS3"
    ;;
  garnet|htsim)
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

# ns-3 emits a versioned binary (ns3.XX-AstraSimNetwork-default) under the
# ns-3 build tree. Locate it and symlink to the stable registry path so
# backend_adapter.py stays version-agnostic.
if [[ "${BACKEND}" == "ns3" ]]; then
  NS3_BUILD_DIR="${REPO_ROOT}/frameworks/astra-sim/extern/network_backend/ns-3/build"
  real_bin="$(find "${NS3_BUILD_DIR}" -type f -name 'ns3.*-AstraSimNetwork-default' -executable 2>/dev/null | head -n1)"
  if [[ -z "${real_bin}" ]]; then
    fail "ns-3 build finished but AstraSimNetwork binary not found under ${NS3_BUILD_DIR}"
  fi
  mkdir -p "${BIN_DIR}"
  ln -sf "${real_bin}" "${SENTINEL_BIN}"
  log "Symlinked ${SENTINEL_BIN} -> ${real_bin}"
fi

[[ -x "${SENTINEL_BIN}" ]] || fail "Build finished but binary not found at ${SENTINEL_BIN}"
log "Build OK: ${SENTINEL_BIN}"
