"""Phase 0 smoke test: /health returns ok."""

from __future__ import annotations

import tempfile

import pytest


@pytest.fixture(scope="session", autouse=True)
def _runs_dir():
    """Point the SQLite registry at a throwaway directory for the test session."""
    import os

    tmp = tempfile.mkdtemp(prefix="sim-test-")
    os.environ["SIM_RUNS_DIR"] = tmp
    yield


async def test_health_ok():
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
