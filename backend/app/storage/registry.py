"""SQLModel registry for runs, artifacts, and presets.

Phase 0 only ships the table stubs and engine init. Later phases extend
columns and add accessor functions.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from sqlmodel import Field, SQLModel, create_engine

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNS_DIR = Path(os.environ.get("SIM_RUNS_DIR", REPO_ROOT / "runs"))
DB_PATH = RUNS_DIR / "registry.db"


class Run(SQLModel, table=True):
    id: str = Field(primary_key=True)
    status: str = Field(default="queued")  # queued|building|running|succeeded|failed|cancelled
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Artifact(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="run.id", index=True)
    kind: str  # spec|config|trace|log|stats
    path: str


class Preset(SQLModel, table=True):
    id: str = Field(primary_key=True)
    kind: str  # model|system|network|memory
    payload_json: str


_engine = None


def get_engine():
    global _engine
    if _engine is None:
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
    return _engine


def init_db() -> None:
    SQLModel.metadata.create_all(get_engine())
