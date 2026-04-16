"""Unit tests for the backend adapter registry."""

from __future__ import annotations

from app.build.backend_adapter import get_backend, is_built, list_backends


class TestBackendAdapter:
    def test_list_includes_analytical(self):
        names = [b.name for b in list_backends()]
        assert "analytical_cu" in names
        assert "analytical_ca" in names

    def test_list_includes_stub(self):
        names = [b.name for b in list_backends()]
        assert "ns3" in names

    def test_get_known(self):
        b = get_backend("analytical_cu")
        assert b.label == "Analytical (Congestion Unaware)"
        assert b.network_schema == "analytical"

    def test_get_unknown_raises(self):
        import pytest

        with pytest.raises(KeyError, match="Unknown backend"):
            get_backend("nonexistent_backend_xyz")

    def test_is_built_returns_bool(self):
        b = get_backend("analytical_cu")
        result = is_built(b)
        assert isinstance(result, bool)

    def test_stub_not_built(self):
        b = get_backend("ns3")
        assert not is_built(b)
