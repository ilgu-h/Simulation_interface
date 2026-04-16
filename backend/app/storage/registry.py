"""SQLModel registry for runs, artifacts, and presets."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from sqlmodel import Field, SQLModel, create_engine

REPO_ROOT = Path(__file__).resolve().parents[3]


def get_runs_dir() -> Path:
    return Path(os.environ.get("SIM_RUNS_DIR", REPO_ROOT / "runs"))


RUNS_DIR = get_runs_dir()


class Run(SQLModel, table=True):
    id: str = Field(primary_key=True)
    status: str = Field(default="queued")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Artifact(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="run.id", index=True)
    kind: str
    path: str


class Preset(SQLModel, table=True):
    id: str = Field(primary_key=True)
    kind: str
    payload_json: str


_engine = None


def get_engine():
    global _engine
    if _engine is None:
        runs = get_runs_dir()
        runs.mkdir(parents=True, exist_ok=True)
        db = runs / "registry.db"
        _engine = create_engine(f"sqlite:///{db}", echo=False)
    return _engine


def init_db() -> None:
    SQLModel.metadata.create_all(get_engine())
