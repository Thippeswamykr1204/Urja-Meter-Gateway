import asyncio
import logging
import random
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
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


async def _scheduled_sync(service: CatalogService, settings: Settings) -> None:
    while True:
        await asyncio.sleep(settings.sync_interval_seconds + random.uniform(0, settings.sync_jitter_seconds))
        await service.background_refresh()


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
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        token = request_id_context.set(request_id)
        try:
            rate_limiter = getattr(request.app.state, "rate_limiter", None)
            if rate_limiter and request.url.path.startswith("/api/"):
                key = request.client.host if request.client else "unknown"
                if not rate_limiter.allow(key):
                    response: Response = JSONResponse(
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
            response.headers["X-Request-ID"] = request_id
            origin = request.headers.get("origin")
            if origin in {"http://localhost:5173", "http://127.0.0.1:5173"}:
                response.headers["Access-Control-Allow-Origin"] = origin
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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
