import json
from pathlib import Path

from app.core.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient
from jsonschema.validators import RefResolver, validator_for

OPENAPI_PATH = Path(__file__).parents[4] / "openapi.json"


def test_demo_responses_validate_against_committed_openapi(tmp_path) -> None:
    document = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    app = create_app(
        Settings(
            demo_mode=True,
            api_read_key="test-key",
            api_admin_key="admin-key",
            database_url=f"sqlite:///{tmp_path}/contract.db",
        )
    )
    read_headers = {"X-API-Key": "test-key"}
    admin_headers = {"X-API-Key": "admin-key"}
    cases = [
        ("GET", "/health", "/health", {}),
        ("GET", "/ready", "/ready", {}),
        ("GET", "/api/v1/metadata", "/api/v1/metadata", read_headers),
        ("GET", "/api/v1/overview", "/api/v1/overview", read_headers),
        ("GET", "/api/v1/meters?page=1&page_size=2", "/api/v1/meters", read_headers),
        ("GET", "/api/v1/search?q=MTR", "/api/v1/search", read_headers),
        ("GET", "/api/v1/meters/MTR-1001", "/api/v1/meters/{meter_id}", read_headers),
        (
            "GET",
            "/api/v1/meters/MTR-1001/consumption?start=2026-10-01&end=2026-10-25&granularity=day",
            "/api/v1/meters/{meter_id}/consumption",
            read_headers,
        ),
        ("GET", "/api/v1/hierarchy", "/api/v1/hierarchy", read_headers),
        ("GET", "/api/v1/quality", "/api/v1/quality", read_headers),
        ("GET", "/api/v1/insights/signals", "/api/v1/insights/signals", read_headers),
        ("GET", "/api/v1/sync/status", "/api/v1/sync/status", read_headers),
        ("GET", "/api/v1/metrics", "/api/v1/metrics", read_headers),
        ("POST", "/api/v1/refresh", "/api/v1/refresh", admin_headers),
    ]

    with TestClient(app) as client:
        for method, path, schema_path, headers in cases:
            response = client.request(method, path, headers=headers)
            assert response.status_code == 200, (method, path, response.text)
            schema = document["paths"][schema_path][method.lower()]["responses"]["200"].get("content", {}).get("application/json", {}).get("schema", {})
            if not schema:
                continue
            validator_class = validator_for(schema)
            validator_class.check_schema(schema)
            resolver = RefResolver.from_schema(document)
            errors = list(validator_class(schema, resolver=resolver).iter_errors(response.json()))
            assert not errors, (method, path, [error.message for error in errors])
