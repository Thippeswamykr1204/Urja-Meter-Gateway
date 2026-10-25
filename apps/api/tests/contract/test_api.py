from app.core.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


def test_api_returns_documented_envelope_and_requires_key(tmp_path) -> None:
    app = create_app(Settings(demo_mode=True, api_read_key="test-key", api_admin_key="admin-key", database_url=f"sqlite:///{tmp_path}/test.db"))
    with TestClient(app) as client:
        missing = client.get("/api/v1/meters")
        response = client.get("/api/v1/meters", headers={"X-API-Key": "test-key"})
    assert missing.status_code == 401
    assert response.status_code == 200
    body = response.json()
    assert {"data", "provenance", "meta"} <= body.keys()
    assert body["data"][0]["id"] == "MTR-1001"


def test_api_rejects_inverted_date_range(tmp_path) -> None:
    app = create_app(Settings(demo_mode=True, api_read_key="test-key", api_admin_key="admin-key", database_url=f"sqlite:///{tmp_path}/test.db"))
    with TestClient(app) as client:
        response = client.get("/api/v1/meters/MTR-1001/consumption?start=2026-10-24&end=2026-10-01", headers={"X-API-Key": "test-key"})
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "invalid_date_range"


def test_refresh_requires_admin_key_and_openapi_contains_public_routes(tmp_path) -> None:
    app = create_app(
        Settings(
            demo_mode=True,
            api_read_key="test-key",
            api_admin_key="admin-key",
            database_url=f"sqlite:///{tmp_path}/test.db",
        )
    )
    with TestClient(app) as client:
        read_response = client.post("/api/v1/refresh", headers={"X-API-Key": "test-key"})
        admin_response = client.post("/api/v1/refresh", headers={"X-API-Key": "admin-key"})
        schema = client.get("/openapi.json").json()
    assert read_response.status_code == 401
    assert admin_response.status_code == 200
    assert "/api/v1/overview" in schema["paths"]
    assert "/api/v1/insights/signals" in schema["paths"]


def test_rate_limit_response_keeps_cors_headers(tmp_path) -> None:
    app = create_app(
        Settings(
            demo_mode=True,
            api_read_key="test-key",
            api_admin_key="admin-key",
            rate_limit_per_minute=1,
            database_url=f"sqlite:///{tmp_path}/test.db",
        )
    )
    with TestClient(app) as client:
        headers = {"X-API-Key": "test-key", "Origin": "http://localhost:5173"}
        client.get("/api/v1/overview", headers=headers)
        response = client.get("/api/v1/overview", headers=headers)
    assert response.status_code == 429
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
