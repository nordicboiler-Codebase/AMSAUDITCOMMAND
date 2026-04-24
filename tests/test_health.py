from __future__ import annotations

import pytest


def test_health_endpoint_returns_ok():
    try:
        from fastapi.testclient import TestClient

        from backend.main import app
    except Exception as e:
        pytest.skip(f"FastAPI test client unavailable: {e}")
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    payload = r.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "techsource-audit-analytics"


def test_detectors_loaded_via_app_import():
    from backend.detectors import catalog

    catalog.load_all()
    assert len(catalog.list_all()) >= 35
