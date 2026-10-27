from app.adapter.errors import (
    PortalAuthenticationError,
    PortalConfigurationError,
    PortalNotFoundError,
    PortalSchemaDriftError,
    PortalSessionExpiredError,
    PortalTimeoutError,
    PortalUnavailableError,
)
from app.api.v1.routes import map_portal_error
from app.core.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


def test_api_returns_documented_envelope_and_requires_key(tmp_path) -> None:
    app = create_app(Settings(demo_mode=True, api_read_key="test-key", api_admin_key="admin-key", database_url=f"sqlite:///{tmp_path}/test.db"))
    with TestClient(app) as client:
        missing = client.get("/api/v1/meters")
        invalid = client.get("/api/v1/meters", headers={"X-API-Key": "wrong-key"})
        response = client.get("/api/v1/meters", headers={"X-API-Key": "test-key"})
    assert missing.status_code == 401
    assert invalid.status_code == 401
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
    assert read_response.status_code == 403
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


def test_request_body_limit_returns_problem_response(tmp_path) -> None:
    app = create_app(
        Settings(
            demo_mode=True,
            api_read_key="test-key",
            api_admin_key="admin-key",
            max_request_body_bytes=1024,
            database_url=f"sqlite:///{tmp_path}/request-size.db",
        )
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/refresh",
            content=b"x" * 1025,
            headers={"X-API-Key": "admin-key"},
        )
    assert response.status_code == 413
    assert response.json()["code"] == "request_too_large"


def test_read_endpoint_supports_etag_and_metrics(tmp_path) -> None:
    app = create_app(Settings(demo_mode=True, api_read_key="test-key", api_admin_key="admin-key", database_url=f"sqlite:///{tmp_path}/test.db"))
    with TestClient(app) as client:
        first = client.get("/api/v1/overview", headers={"X-API-Key": "test-key"})
        cached = client.get("/api/v1/overview", headers={"X-API-Key": "test-key", "If-None-Match": first.headers["ETag"]})
        metrics = client.get("/api/v1/metrics", headers={"X-API-Key": "test-key"})
    assert first.status_code == 200
    assert cached.status_code == 304
    assert cached.headers["X-Request-ID"]
    assert metrics.status_code == 200
    assert "portal" in metrics.json()["data"]


def test_admin_endpoint_rejects_read_key_and_large_date_range(tmp_path) -> None:
    app = create_app(Settings(demo_mode=True, api_read_key="test-key", api_admin_key="admin-key", max_date_range_days=7, database_url=f"sqlite:///{tmp_path}/test.db"))
    with TestClient(app) as client:
        refresh = client.post("/api/v1/refresh", headers={"X-API-Key": "test-key"})
        large = client.get("/api/v1/meters/MTR-1001/consumption?start=2026-01-01&end=2026-02-01", headers={"X-API-Key": "test-key"})
    assert refresh.status_code == 403
    assert large.status_code == 413
    assert large.json()["code"] == "date_range_too_large"


def test_negative_inputs_do_not_cross_auth_or_query_boundaries(tmp_path) -> None:
    app = create_app(
        Settings(
            demo_mode=True,
            api_read_key="test-key",
            api_admin_key="admin-key",
            database_url=f"sqlite:///{tmp_path}/negative.db",
        )
    )
    with TestClient(app) as client:
        missing_admin = client.post("/api/v1/refresh")
        wrong_admin = client.post("/api/v1/refresh", headers={"X-API-Key": "wrong-key"})
        oversized = client.get(
            "/api/v1/meters?page_size=101",
            headers={"X-API-Key": "test-key"},
        )
        oversized_search = client.get(
            f"/api/v1/search?q={'x' * 201}",
            headers={"X-API-Key": "test-key"},
        )
        hostile_search = client.get(
            "/api/v1/search?q=%27%20OR%201%3D1%20--",
            headers={"X-API-Key": "test-key"},
        )
    assert missing_admin.status_code == 401
    assert wrong_admin.status_code == 401
    assert oversized.status_code == 422
    assert oversized_search.status_code == 422
    assert hostile_search.status_code == 200


def test_api_surfaces_all_read_models_and_not_found(tmp_path) -> None:
    app = create_app(Settings(demo_mode=True, api_read_key="test-key", api_admin_key="admin-key", database_url=f"sqlite:///{tmp_path}/all.db"))
    headers = {"X-API-Key": "test-key"}
    with TestClient(app) as client:
        paths = [
            "/api/v1/metadata",
            "/api/v1/overview",
            "/api/v1/meters?page=1&page_size=2",
            "/api/v1/search?q=MTR",
            "/api/v1/meters/MTR-1001",
            "/api/v1/meters/MTR-1001/consumption?start=2026-10-01&end=2026-10-25&granularity=hour",
            "/api/v1/hierarchy",
            "/api/v1/quality",
            "/api/v1/insights/signals",
            "/api/v1/sync/status",
            "/api/v1/metrics",
        ]
        responses = [client.get(path, headers=headers) for path in paths]
        missing = client.get("/api/v1/meters/does-not-exist", headers=headers)
        ready = client.get("/ready")
    assert all(response.status_code == 200 for response in responses)
    assert missing.status_code == 404
    assert ready.status_code == 200
    assert all(response.headers.get("X-Request-ID") for response in responses)


def test_api_validates_geo_queries_and_maps_portal_failures(tmp_path) -> None:
    app = create_app(Settings(demo_mode=True, api_read_key="test-key", api_admin_key="admin-key", database_url=f"sqlite:///{tmp_path}/geo-validation.db"))
    headers = {"X-API-Key": "test-key"}
    with TestClient(app) as client:
        invalid_radius = client.get("/api/v1/meters?lat=1", headers=headers)
        invalid_bbox = client.get("/api/v1/meters?min_lat=1&min_lon=1", headers=headers)
    assert invalid_radius.status_code == 400
    assert invalid_bbox.status_code == 400
    assert map_portal_error(PortalNotFoundError()).status == 404
    assert map_portal_error(PortalConfigurationError()).status == 503
    assert map_portal_error(PortalAuthenticationError()).status == 502
    assert map_portal_error(PortalSessionExpiredError()).status == 502
    assert map_portal_error(PortalSchemaDriftError()).status == 502
    assert map_portal_error(PortalTimeoutError()).status == 504
    assert map_portal_error(PortalUnavailableError()).status == 503
    assert map_portal_error(RuntimeError()).status == 502
