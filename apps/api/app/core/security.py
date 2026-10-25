import secrets
from typing import Literal

from fastapi import Request, Security
from fastapi.security import APIKeyHeader

from app.core.config import get_settings
from app.core.errors import ApiProblem

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(
    request: Request,
    x_api_key: str | None = Security(api_key_header),
) -> None:
    settings = getattr(request.app.state, "settings", None) or get_settings()
    if not x_api_key or not any(
        value and secrets.compare_digest(x_api_key, value)
        for value in (settings.api_read_key, settings.api_admin_key)
    ):
        raise ApiProblem(401, "api_key_required", "API key required", "Provide a valid read API key.")


async def require_admin_key(
    request: Request,
    x_api_key: str | None = Security(api_key_header),
) -> None:
    await _require_key(request, x_api_key, "admin")


async def _require_key(request: Request, provided: str | None, kind: Literal["read", "admin"]) -> None:
    settings = getattr(request.app.state, "settings", None) or get_settings()
    expected = settings.api_admin_key if kind == "admin" else settings.api_read_key
    if not expected or not provided or not secrets.compare_digest(provided, expected):
        raise ApiProblem(401, "api_key_required", "API key required", f"Provide a valid {kind} API key.")
