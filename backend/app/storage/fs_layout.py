"""Filesystem layout helpers for per-run artifacts (plan.md §3)."""

from __future__ import annotations

import uuid
from pathlib import Path

from app.storage.registry import RUNS_DIR


def new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def run_dir(run_id: str) -> Path:
    return RUNS_DIR / run_id


def traces_dir(run_id: str) -> Path:
    return run_dir(run_id) / "traces"


def configs_dir(run_id: str) -> Path:
    return run_dir(run_id) / "configs"


def logs_dir(run_id: str) -> Path:
    return run_dir(run_id) / "logs"


def previews_dir(run_id: str) -> Path:
    return run_dir(run_id) / "previews"
