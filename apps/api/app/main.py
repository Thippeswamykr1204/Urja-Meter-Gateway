import asyncio
import hashlib
import json
import logging
import random
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from app.adapter.demo import DemoPortalAdapter
from app.adapter.http import HttpPortalAdapter
from app.adapter.ports import PortalAdapter
from app.api.v1.routes import router
from app.core.config import Settings, get_settings
from app.core.errors import ApiProblem, problem_response
from app.core.logging import configure_logging, request_id_context
from app.core.rate_limit import InMemoryRateLimiter
from app.services.catalog import CatalogService
from app.store.sqlite import SQLiteStore

logger = logging.getLogger(__name__)
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


async def _scheduled_sync(service: CatalogService, settings: Settings) -> None:
    while True:
        await asyncio.sleep(settings.sync_interval_seconds + random.uniform(0, settings.sync_jitter_seconds))
        service.sync.request_background_refresh()


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    app_settings.validate_runtime()
    configure_logging(app_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        store = await asyncio.to_thread(SQLiteStore, app_settings.database_url)
        adapter: PortalAdapter = DemoPortalAdapter() if app_settings.demo_mode else HttpPortalAdapter(app_settings)
        service = CatalogService(adapter, store, app_settings)
        app.state.settings = app_settings
        app.state.adapter = adapter
        app.state.store = store
        app.state.catalog_service = service
        app.state.request_metrics = {
            "requests_total": 0,
            "errors_total": 0,
            "latency_total_seconds": 0.0,
            "latency_max_seconds": 0.0,
            "status_counts": {},
        }
        app.state.rate_limiter = InMemoryRateLimiter(
            app_settings.rate_limit_per_minute, max_keys=app_settings.rate_limit_max_keys
        )
        try:
            await service.refresh()
        except Exception as error:
            logger.warning("startup sync failed", extra={"fields": {"error": str(error)}})
        sync_task: asyncio.Task[None] | None = None
        if app_settings.sync_interval_seconds > 0:
            sync_task = asyncio.create_task(_scheduled_sync(service, app_settings))
        yield
        if sync_task is not None:
            sync_task.cancel()
            await asyncio.gather(sync_task, return_exceptions=True)
        await service.sync.shutdown()
        close = getattr(adapter, "aclose", None)
        if close is not None:
            await close()
        await store.aclose()

    app = FastAPI(
        title="Flock Energy — Urja Meter Ops API",
        version="0.2.0",
        description="A clean, read-only API facade over the evidence-driven Urja Meter Ops integration.",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    @app.middleware("http")
    async def request_context(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        candidate_request_id = request.headers.get("X-Request-ID", "")
        request_id = candidate_request_id if _REQUEST_ID_PATTERN.fullmatch(candidate_request_id) else str(uuid.uuid4())
        request.state.request_id = request_id
        token = request_id_context.set(request_id)
        started = perf_counter()
        try:
            rate_limiter = getattr(request.app.state, "rate_limiter", None)
            content_length = request.headers.get("content-length")
            too_large = False
            if content_length is not None:
                try:
                    too_large = int(content_length) > app_settings.max_request_body_bytes
                except ValueError:
                    too_large = True
            if too_large:
                response: Response = problem_response(
                    request,
                    ApiProblem(
                        413,
                        "request_too_large",
                        "Request too large",
                        "The request body exceeds the configured limit.",
                    ),
                )
            elif rate_limiter and request.url.path.startswith("/api/"):
                key = request.client.host if request.client else "unknown"
                if not rate_limiter.allow(key):
                    response = JSONResponse(
                        {
                            "type": "https://api.flockenergy.tech/problems/rate_limited",
                            "title": "Too many requests",
                            "status": 429,
                            "detail": "Retry after the rate limit window.",
                            "code": "rate_limited",
                            "request_id": request_id,
                        },
                        status_code=429,
                        media_type="application/problem+json",
                    )
                else:
                    response = await call_next(request)
            else:
                response = await call_next(request)
            if request.method == "GET" and request.url.path.startswith("/api/"):
                body = getattr(response, "body", None)
                if body is None and hasattr(response, "body_iterator"):
                    chunks = [chunk async for chunk in response.body_iterator]
                    body = b"".join(chunks)
                    response = Response(
                        content=body,
                        status_code=response.status_code,
                        headers=dict(response.headers),
                        media_type=response.media_type,
                    )
                if body:
                    try:
                        payload = json.loads(body)

                        def stable(value: Any) -> Any:
                            if isinstance(value, dict):
                                return {key: (0 if key in {"age_seconds", "generated_at"} else stable(item)) for key, item in value.items()}
                            if isinstance(value, list):
                                return [stable(item) for item in value]
                            return value

                        etag_body = json.dumps(stable(payload), sort_keys=True, separators=(",", ":")).encode()
                    except (TypeError, ValueError):
                        etag_body = body
                    etag = f'"{hashlib.sha256(etag_body).hexdigest()}"'
                    response.headers["ETag"] = etag
                    if request.headers.get("if-none-match") == etag:
                        response = Response(status_code=304, headers={"ETag": etag})
            response.headers["X-Request-ID"] = request_id
            origin = request.headers.get("origin")
            if origin in app_settings.allowed_origin_values:
                response.headers["Access-Control-Allow-Origin"] = origin
            metrics = getattr(request.app.state, "request_metrics", None)
            if metrics is not None:
                duration = perf_counter() - started
                status_key = str(response.status_code)
                metrics["requests_total"] += 1
                metrics["errors_total"] += int(response.status_code >= 500)
                metrics["latency_total_seconds"] += duration
                metrics["latency_max_seconds"] = max(metrics["latency_max_seconds"], duration)
                status_counts = metrics["status_counts"]
                status_counts[status_key] = status_counts.get(status_key, 0) + 1
            return response
        finally:
            request_id_context.reset(token)

    @app.exception_handler(ApiProblem)
    async def api_problem_handler(request: Request, exc: ApiProblem) -> JSONResponse:
        return problem_response(request, exc)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        problem = ApiProblem(
            422,
            "validation_error",
            "Validation error",
            "The request did not match the API contract.",
            {"errors": exc.errors()},
        )
        return problem_response(request, problem)

    @app.exception_handler(Exception)
    async def unexpected_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unexpected request failure", extra={"fields": {"error": str(exc)}})
        return problem_response(
            request,
            ApiProblem(500, "internal_error", "Internal server error", "The request could not be completed."),
        )

    @app.get("/health")
    async def health(request: Request) -> dict[str, object]:
        return {"status": "ok", "request_id": request.state.request_id}

    @app.get("/ready")
    async def ready(request: Request) -> JSONResponse:
        store_ok = await request.app.state.store.ping()
        portal_health = await request.app.state.adapter.health()
        reachable = True
        checker = getattr(request.app.state.adapter, "check_reachability", None)
        if checker is not None:
            try:
                reachable = await checker()
            except Exception:
                reachable = False
        latest = await request.app.state.store.latest_sync()
        ready_state = store_ok and bool(portal_health.get("configured")) and reachable
        if request.app.state.settings.demo_mode:
            ready_state = store_ok and reachable
        payload: dict[str, Any] = {
            "status": "ready" if ready_state else "not_ready",
            "store_reachable": store_ok,
            "portal": {**portal_health, "reachable": reachable},
            "last_sync": latest.model_dump(mode="json") if latest else None,
            "request_id": request.state.request_id,
        }
        return JSONResponse(payload, status_code=200 if ready_state else 503)

    if app_settings.trusted_host_values:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(app_settings.trusted_host_values))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(app_settings.allowed_origin_values),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
