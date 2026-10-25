from datetime import date
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query, Request, status

from app.adapter.errors import (
    PortalAuthenticationError,
    PortalConfigurationError,
    PortalNotFoundError,
    PortalSchemaDriftError,
    PortalSessionExpiredError,
    PortalTimeoutError,
    PortalUnavailableError,
)
from app.core.errors import ApiProblem
from app.core.security import require_admin_key, require_api_key
from app.domain.models import (
    ApiEnvelope,
    ConsumptionResponse,
    DataQualityReport,
    HierarchyNode,
    Meter,
    Provenance,
    Signal,
    SyncRun,
)
from app.services.catalog import CatalogService

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_key)])


def get_service(request: Request) -> CatalogService:
    return cast(CatalogService, request.app.state.catalog_service)


def map_portal_error(error: Exception) -> ApiProblem:
    if isinstance(error, PortalNotFoundError):
        return ApiProblem(404, "portal_not_found", "Resource not found", "The upstream portal did not find the requested resource.")
    if isinstance(error, PortalConfigurationError):
        return ApiProblem(503, "portal_unconfigured", "Portal integration unavailable", str(error))
    if isinstance(error, (PortalAuthenticationError, PortalSessionExpiredError)):
        return ApiProblem(502, "portal_authentication_failed", "Portal authentication failed", "The upstream portal did not establish a valid session.")
    if isinstance(error, PortalSchemaDriftError):
        return ApiProblem(502, "portal_schema_drift", "Portal response changed", "The upstream response did not match captured evidence shapes.")
    if isinstance(error, PortalTimeoutError):
        return ApiProblem(504, "portal_timeout", "Portal request timed out", "The upstream portal did not respond in time.")
    if isinstance(error, PortalUnavailableError):
        return ApiProblem(503, "portal_unavailable", "Portal unavailable", "The upstream portal is temporarily unavailable.")
    return ApiProblem(502, "portal_error", "Portal request failed", "The upstream portal returned an unexpected response.")


@router.get("/metadata")
async def metadata(request: Request) -> ApiEnvelope[dict[str, object]]:
    return ApiEnvelope(
        data={
            "name": "Flock Energy Urja Meter Ops API",
            "version": request.app.version,
            "mode": request.app.state.settings.app_env,
            "supported_granularities": ["hour", "day", "month"],
            "unverified_portal_behavior": not request.app.state.settings.demo_mode,
        },
        provenance=Provenance(source="index", stale=False),
    )


@router.get("/overview")
async def overview(service: Annotated[CatalogService, Depends(get_service)]) -> ApiEnvelope[dict[str, object]]:
    data = await service.overview()
    provenance = Provenance.model_validate(data.pop("provenance"))
    return ApiEnvelope(data=data, provenance=provenance)


@router.get("/meters")
async def list_meters(
    service: Annotated[CatalogService, Depends(get_service)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    search: str | None = Query(default=None, min_length=1),
    status_filter: str | None = Query(default=None, alias="status"),
    latitude: float | None = Query(default=None, alias="lat", ge=-90, le=90),
    longitude: float | None = Query(default=None, alias="lon", ge=-180, le=180),
    radius_km: float | None = Query(default=None, gt=0, le=500),
    min_lat: float | None = Query(default=None, ge=-90, le=90),
    min_lon: float | None = Query(default=None, ge=-180, le=180),
    max_lat: float | None = Query(default=None, ge=-90, le=90),
    max_lon: float | None = Query(default=None, ge=-180, le=180),
    sort: str = Query(default="id", pattern="^(id|name|status|last_seen_at)$"),
    order: str = Query(default="asc", pattern="^(asc|desc)$"),
) -> ApiEnvelope[list[Meter]]:
    if (latitude is None) != (longitude is None) or (radius_km is not None and (latitude is None or longitude is None)):
        raise ApiProblem(400, "invalid_radius_query", "Invalid radius query", "lat, lon and radius_km must be provided together.")
    bbox_values = (min_lat, min_lon, max_lat, max_lon)
    if any(value is not None for value in bbox_values) and not all(value is not None for value in bbox_values):
        raise ApiProblem(400, "invalid_bbox", "Invalid bounding box", "All four bbox coordinates are required.")
    bbox = cast(tuple[float, float, float, float] | None, bbox_values if all(value is not None for value in bbox_values) else None)
    try:
        meters, page_meta, provenance = await service.meters(
            page, page_size, search, status_filter, latitude, longitude, radius_km, bbox, sort, order == "desc"
        )
    except Exception as error:
        raise map_portal_error(error) from error
    return ApiEnvelope(data=meters, provenance=provenance, meta=page_meta.model_dump())


@router.get("/search")
async def unified_search(
    service: Annotated[CatalogService, Depends(get_service)],
    q: str = Query(min_length=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> ApiEnvelope[list[Meter]]:
    meters, page_meta, provenance = await service.meters(page, page_size, q, None)
    return ApiEnvelope(data=meters, provenance=provenance, meta=page_meta.model_dump())


@router.get("/meters/{meter_id}")
async def get_meter(meter_id: str, service: Annotated[CatalogService, Depends(get_service)]) -> ApiEnvelope[Meter]:
    try:
        meter, provenance = await service.meter(meter_id)
    except Exception as error:
        raise map_portal_error(error) from error
    if meter is None:
        raise ApiProblem(404, "meter_not_found", "Meter not found", f"No meter exists with id '{meter_id}'.")
    return ApiEnvelope(data=meter, provenance=provenance)


@router.get("/meters/{meter_id}/consumption")
async def get_consumption(
    meter_id: str,
    service: Annotated[CatalogService, Depends(get_service)],
    start: date | None = None,
    end: date | None = None,
    granularity: str = Query(default="day", pattern="^(hour|day|month)$"),
) -> ApiEnvelope[ConsumptionResponse]:
    if start and end and start > end:
        raise ApiProblem(400, "invalid_date_range", "Invalid date range", "start must be on or before end.")
    try:
        data = await service.consumption(meter_id, start, end, granularity)
    except PortalNotFoundError as error:
        raise ApiProblem(404, "meter_not_found", "Meter not found", f"No meter exists with id '{meter_id}'.") from error
    except Exception as error:
        raise map_portal_error(error) from error
    return ApiEnvelope(data=data, provenance=data.provenance)


@router.get("/hierarchy")
async def get_hierarchy(service: Annotated[CatalogService, Depends(get_service)]) -> ApiEnvelope[list[HierarchyNode]]:
    try:
        data, provenance = await service.hierarchy()
    except Exception as error:
        raise map_portal_error(error) from error
    return ApiEnvelope(data=list(data), provenance=provenance)


@router.get("/quality")
async def get_quality(service: Annotated[CatalogService, Depends(get_service)]) -> ApiEnvelope[DataQualityReport]:
    report = await service.quality()
    return ApiEnvelope(data=report, provenance=await service.provenance("meters", source="index"))


@router.get("/insights/signals")
async def get_signals(service: Annotated[CatalogService, Depends(get_service)]) -> ApiEnvelope[list[Signal]]:
    return ApiEnvelope(data=await service.signals(), provenance=await service.provenance("consumption", source="index"))


@router.get("/sync/status")
async def sync_status(request: Request) -> ApiEnvelope[SyncRun | dict[str, str]]:
    latest = await request.app.state.store.latest_sync()
    data: SyncRun | dict[str, str] = latest or {"status": "never_run"}
    return ApiEnvelope(data=data, provenance=Provenance(source="index", stale=False), meta={"running": bool(latest and latest.status == "running")})


@router.post("/refresh", dependencies=[Depends(require_admin_key)], status_code=status.HTTP_200_OK)
async def refresh(request: Request, service: Annotated[CatalogService, Depends(get_service)]) -> ApiEnvelope[dict[str, int]]:
    try:
        meters = await service.refresh()
    except Exception as error:
        raise map_portal_error(error) from error
    return ApiEnvelope(data={"meters_indexed": len(meters)}, provenance=await service.provenance("meters", source="index"), meta={"request_id": request.state.request_id})
