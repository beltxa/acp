from __future__ import annotations

from pathlib import Path
import sys

from fastapi.testclient import TestClient
import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import _ENTERPRISE_BOUNDARY_ENV_VARS, create_app  # noqa: E402


@pytest.mark.parametrize(
    ("env_var", "feature"),
    sorted(_ENTERPRISE_BOUNDARY_ENV_VARS.items()),
)
def test_create_app_rejects_enterprise_configuration(
    monkeypatch: pytest.MonkeyPatch,
    env_var: str,
    feature: str,
) -> None:
    monkeypatch.setenv(env_var, "enabled")
    with pytest.raises(RuntimeError, match=feature):
        create_app()


def test_create_app_allows_explicitly_disabled_enterprise_toggle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACP_HA_ENABLED", "false")
    app = create_app()
    assert app is not None


def test_relay_dev_does_not_expose_ops_failures_route() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/ops/failures")
    assert response.status_code == 404


def test_relay_dev_does_not_expose_enterprise_route_prefixes() -> None:
    app = create_app()
    public_paths = {route.path for route in app.routes}
    blocked_prefixes = ("/policy", "/federation", "/audit", "/observability", "/trust-registry")
    for path in public_paths:
        assert not path.startswith(blocked_prefixes)
