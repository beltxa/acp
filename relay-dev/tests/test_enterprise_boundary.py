from __future__ import annotations

from pathlib import Path
import sys

from fastapi.testclient import TestClient
import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402


def test_create_app_rejects_unsupported_acp_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACP_UNSUPPORTED_CONFIGURATION", "enabled")
    with pytest.raises(RuntimeError, match="not supported in relay-dev"):
        create_app()


def test_create_app_allows_explicitly_disabled_unsupported_toggle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACP_UNSUPPORTED_CONFIGURATION", "false")
    app = create_app()
    assert app is not None


def test_relay_dev_does_not_expose_ops_failures_route() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/ops/failures")
    assert response.status_code == 404


def test_relay_dev_exposes_only_public_routes() -> None:
    app = create_app()
    public_paths = {route.path for route in app.routes}
    assert public_paths == {
        "/health",
        "/status",
        "/messages",
        "/messages/{message_id}",
        "/pending-deliveries",
        "/pending-deliveries/process",
        "/discover",
        "/identities",
        "/registry",
        "/registry/{agent_id}",
        "/routes",
        "/ops/stats",
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
    }
