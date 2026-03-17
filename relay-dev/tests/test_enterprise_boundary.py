from __future__ import annotations

from pathlib import Path
import sys

from fastapi.testclient import TestClient
import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402


def test_create_app_rejects_policy_engine_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACP_POLICY_ENGINE_URL", "https://policy.example")
    with pytest.raises(RuntimeError, match="policy engine"):
        create_app()


def test_create_app_rejects_audit_pipeline_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACP_AUDIT_PIPELINE_URL", "https://audit.example")
    with pytest.raises(RuntimeError, match="audit pipeline"):
        create_app()


def test_relay_dev_does_not_expose_ops_failures_route() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/ops/failures")
    assert response.status_code == 404
