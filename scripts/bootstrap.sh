#!/usr/bin/env bash
# Bootstrap the host environment for Simulation_interface.
# Idempotent: re-runs are no-ops once each step's artifact exists.
#
# See plan.md §4 Phase 0 for acceptance criteria.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

MINIFORGE_DIR="${HOME}/miniforge3"
STG_ENV_NAME="stg-env"
STG_ENV_FILE="frameworks/symbolic_tensor_graph/environment.yml"
BACKEND_VENV="${REPO_ROOT}/.venv-backend"
LOCAL_BIN="${HOME}/.local/bin"

log()  { printf '\033[1;36m[bootstrap]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[bootstrap]\033[0m %s\n' "$*" >&2; }
fail() { printf '\033[1;31m[bootstrap]\033[0m %s\n' "$*" >&2; exit 1; }

# ---------- 1. System prerequisites ----------
check_prereqs() {
  local missing=()
  for bin in git cmake protoc node curl; do
    command -v "$bin" >/dev/null 2>&1 || missing+=("$bin")
  done
  if (( ${#missing[@]} )); then
    warn "Missing system tools: ${missing[*]}"
    warn "Install on Debian/Ubuntu: sudo apt install -y git cmake protobuf-compiler nodejs curl build-essential"
    fail "Resolve missing prerequisites and re-run."
  fi
  log "System prerequisites OK."
}

# ---------- 2. Submodules ----------
init_submodules() {
  if ! git submodule status frameworks/astra-sim >/dev/null 2>&1; then
    fail "Top-level submodules not registered. See plan.md §4 Phase 0 step 1."
  fi
  log "Initializing analytical-only sub-submodules of astra-sim..."
  git -C frameworks/astra-sim submodule update --init \
    extern/graph_frontend/chakra \
    extern/network_backend/analytical \
    extern/remote_memory_backend/analytical \
    extern/helper/fmt \
    extern/helper/spdlog
  log "Submodules ready."
}

# ---------- 3. Local patches to vendored deps ----------
# These changes are kept in-tree (modified submodule worktrees) until we fork
# upstream. Each patch is idempotent.
apply_vendored_patches() {
  # 3a. cxxopts.hpp — add <cstdint> for GCC 13+ (uint8_t no longer transitively included).
  local cxxopts="frameworks/astra-sim/extern/helper/cxxopts/cxxopts.hpp"
  if [[ -f "$cxxopts" ]] && ! grep -q "^#include <cstdint>" "$cxxopts"; then
    log "Patching $cxxopts to include <cstdint>..."
    sed -i '/^#include <cstring>/i #include <cstdint>' "$cxxopts"
  fi

  # 3b. mlcommons/chakra setup — strip [build_grpc] section + custom cmdclass.
  # PEP 660 editable wheel builds parse setup.cfg before [distutils.commands]
  # entry points are loaded, so the build_grpc options trip an unknown-option
  # error. We pre-generate the protobuf stubs ourselves (next step) and let
  # setuptools build the editable wheel without any custom commands.
  local chakra_setup_cfg="frameworks/chakra/setup.cfg"
  local chakra_setup_py="frameworks/chakra/setup.py"
  if [[ -f "$chakra_setup_cfg" ]] && grep -q "build_grpc" "$chakra_setup_cfg"; then
    log "Stripping [build_grpc] from chakra setup.cfg..."
    cat > "$chakra_setup_cfg" <<'EOF'
# Local patch (Simulation_interface): see scripts/bootstrap.sh for rationale.
EOF
  fi
  if [[ -f "$chakra_setup_py" ]] && grep -q "build_grpc" "$chakra_setup_py"; then
    log "Simplifying chakra setup.py..."
    cat > "$chakra_setup_py" <<'EOF'
# Local patch (Simulation_interface): see scripts/bootstrap.sh for rationale.
from setuptools import setup
setup()
EOF
  fi

  # 3c. Pre-generate chakra et_def_pb2.py via plain protoc.
  local proto_dir="frameworks/chakra/schema/protobuf"
  if [[ -f "$proto_dir/et_def.proto" && ! -f "$proto_dir/et_def_pb2.py" ]]; then
    log "Generating $proto_dir/et_def_pb2.py..."
    protoc --proto_path="$proto_dir" --python_out="$proto_dir" "$proto_dir/et_def.proto"
  fi
}

# ---------- 4. Miniforge ----------
install_miniforge() {
  if [[ -x "${MINIFORGE_DIR}/bin/conda" ]]; then
    log "Miniforge already present at ${MINIFORGE_DIR}."
    return
  fi
  log "Installing Miniforge to ${MINIFORGE_DIR}..."
  local arch installer
  arch="$(uname -m)"
  installer="Miniforge3-Linux-${arch}.sh"
  local url="https://github.com/conda-forge/miniforge/releases/latest/download/${installer}"
  local tmp
  tmp="$(mktemp -d)"
  curl -fsSL "$url" -o "${tmp}/${installer}"
  bash "${tmp}/${installer}" -b -p "${MINIFORGE_DIR}"
  rm -rf "$tmp"
  log "Miniforge installed."
}

# ---------- 5. STG conda env ----------
create_stg_env() {
  # shellcheck disable=SC1091
  source "${MINIFORGE_DIR}/etc/profile.d/conda.sh"
  if conda env list | awk '{print $1}' | grep -qx "${STG_ENV_NAME}"; then
    log "Conda env '${STG_ENV_NAME}' already exists."
    return
  fi
  log "Creating conda env '${STG_ENV_NAME}' from ${STG_ENV_FILE}..."
  conda env create -n "${STG_ENV_NAME}" -f "${STG_ENV_FILE}"
  # tqdm is imported by STG's graph module but missing from environment.yml.
  log "Installing STG runtime extras (tqdm)..."
  "${MINIFORGE_DIR}/envs/${STG_ENV_NAME}/bin/pip" install --quiet tqdm
  log "STG env ready."
}

# ---------- 6. pnpm via corepack ----------
enable_pnpm() {
  mkdir -p "${LOCAL_BIN}"
  if [[ -x "${LOCAL_BIN}/pnpm" ]]; then
    log "pnpm already at ${LOCAL_BIN}/pnpm ($("${LOCAL_BIN}/pnpm" --version))."
  else
    if ! command -v corepack >/dev/null 2>&1; then
      fail "corepack not found. Install Node 16.17+ and re-run."
    fi
    log "Enabling pnpm via corepack into ${LOCAL_BIN}..."
    corepack enable --install-directory "${LOCAL_BIN}"
    log "pnpm enabled ($("${LOCAL_BIN}/pnpm" --version))."
  fi
  case ":$PATH:" in
    *":${LOCAL_BIN}:"*) ;;
    *) warn "Add ${LOCAL_BIN} to PATH (e.g. in ~/.bashrc): export PATH=\"${LOCAL_BIN}:\$PATH\"" ;;
  esac
}

# ---------- 7. Backend venv ----------
create_backend_venv() {
  if [[ ! -d "${BACKEND_VENV}" ]]; then
    log "Creating backend venv at ${BACKEND_VENV}..."
    python3 -m venv "${BACKEND_VENV}"
  else
    log "Backend venv already exists."
  fi
  # shellcheck disable=SC1091
  source "${BACKEND_VENV}/bin/activate"
  python -m pip install --quiet --upgrade pip
  # Pin setuptools <81 so pkg_resources stays available for legacy build deps.
  pip install --quiet "setuptools<81" wheel
  log "Installing Chakra (editable, no build isolation)..."
  pip install --quiet --no-build-isolation -e "${REPO_ROOT}/frameworks/chakra"
  if [[ -f "${REPO_ROOT}/backend/pyproject.toml" ]]; then
    log "Installing backend (editable, dev extras)..."
    pip install --quiet -e "${REPO_ROOT}/backend[dev]"
  else
    warn "backend/pyproject.toml not present yet; skipping backend install."
  fi
  deactivate
  log "Backend venv ready."
}

# ---------- 8. ASTRA-sim build ----------
build_astrasim() {
  bash "${REPO_ROOT}/scripts/build_backends.sh"
}

main() {
  log "Repo root: ${REPO_ROOT}"
  check_prereqs
  init_submodules
  apply_vendored_patches
  install_miniforge
  create_stg_env
  enable_pnpm
  create_backend_venv
  build_astrasim
  log "Bootstrap complete."
  log "Next: see plan.md §4 Phase 0 acceptance criteria, then move to Phase 1."
}

main "$@"
