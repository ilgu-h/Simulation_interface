FROM ubuntu:22.04 AS base

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake protobuf-compiler git curl ca-certificates \
    python3 python3-dev python3-venv python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Miniforge for STG's conda env.
ARG MINIFORGE_VERSION=latest
RUN curl -fsSL "https://github.com/conda-forge/miniforge/releases/${MINIFORGE_VERSION}/download/Miniforge3-Linux-$(uname -m).sh" -o /tmp/mf.sh \
    && bash /tmp/mf.sh -b -p /opt/miniforge3 \
    && rm /tmp/mf.sh
ENV PATH="/opt/miniforge3/bin:$PATH"

# Node 20 + corepack/pnpm.
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && corepack enable \
    && corepack prepare pnpm@9 --activate

WORKDIR /app

# Copy dependency specs first for layer caching.
COPY backend/pyproject.toml backend/pyproject.toml
COPY frameworks/symbolic_tensor_graph/environment.yml frameworks/symbolic_tensor_graph/environment.yml
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/

# STG conda env.
RUN conda env create -n stg-env -f frameworks/symbolic_tensor_graph/environment.yml \
    && conda clean -afy \
    && /opt/miniforge3/envs/stg-env/bin/pip install --quiet tqdm

# Backend venv.
RUN python3 -m venv .venv-backend \
    && .venv-backend/bin/pip install --quiet --upgrade pip "setuptools<81" wheel

# Frontend deps.
RUN cd frontend && pnpm install --frozen-lockfile=false

# Copy full source.
COPY . .

# Patch vendored deps (same as bootstrap.sh §3).
RUN if grep -q "build_grpc" frameworks/chakra/setup.cfg 2>/dev/null; then \
      echo "# Patched for PEP 660" > frameworks/chakra/setup.cfg; \
      printf 'from setuptools import setup\nsetup()\n' > frameworks/chakra/setup.py; \
    fi \
    && if [ ! -f frameworks/chakra/schema/protobuf/et_def_pb2.py ]; then \
         protoc --proto_path=frameworks/chakra/schema/protobuf \
                --python_out=frameworks/chakra/schema/protobuf \
                frameworks/chakra/schema/protobuf/et_def.proto 2>/dev/null || true; \
       fi \
    && if [ -f frameworks/astra-sim/extern/helper/cxxopts/cxxopts.hpp ] \
       && ! grep -q "^#include <cstdint>" frameworks/astra-sim/extern/helper/cxxopts/cxxopts.hpp; then \
         sed -i '/^#include <cstring>/i #include <cstdint>' \
             frameworks/astra-sim/extern/helper/cxxopts/cxxopts.hpp; \
       fi

# Install editable packages.
RUN .venv-backend/bin/pip install --quiet --no-build-isolation -e frameworks/chakra \
    && .venv-backend/bin/pip install --quiet -e backend[dev]

# Build ASTRA-sim analytical.
RUN bash scripts/build_backends.sh analytical

# Frontend build.
RUN cd frontend && pnpm build

# Runtime defaults.
ENV STG_PYTHON=/opt/miniforge3/envs/stg-env/bin/python
EXPOSE 8000 3000
