"""API health endpoint tests."""

import pytest
from fastapi.testclient import TestClient

from fatorx_api.main import app


@pytest.mark.allow_hosts(["127.0.0.1", "::1"])
def test_health_returns_typed_process_status() -> None:
    """The endpoint responds in-process without any external I/O."""

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {
        "status": "ok",
        "service": "fatorx-global-intelligence-api",
    }
