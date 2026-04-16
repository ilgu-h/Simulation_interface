"""Shared pytest fixtures for the backend test suite."""

from __future__ import annotations

import pytest


@pytest.fixture
def app():
    from app.main import app
    from app.storage.registry import init_db

    init_db()
    return app


@pytest.fixture
async def client(app):
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
