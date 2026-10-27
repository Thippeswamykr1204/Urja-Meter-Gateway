import asyncio
import json
import logging
import random
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from time import monotonic
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.adapter.circuit import CircuitBreaker
from app.adapter.errors import (
    PortalAuthenticationError,
    PortalCircuitOpenError,
    PortalConfigurationError,
    PortalError,
    PortalNotFoundError,
    PortalSchemaDriftError,
    PortalSessionExpiredError,
    PortalTimeoutError,
    PortalUnavailableError,
)
from app.adapter.ports import PortalAdapter
from app.core.config import Settings
from app.domain.hierarchy import reconstruct_hierarchy
from app.domain.models import ConsumptionPoint, HierarchyNode, Meter, QualityFlag, QualitySummary
from app.parsers.portal import parse_consumption, parse_meters, parse_payload, payload_has_records

logger = logging.getLogger(__name__)


class HttpPortalAdapter(PortalAdapter):
    """Evidence-driven adapter; paths and session markers come from configuration."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.AsyncClient(
            base_url=settings.portal_base_url.rstrip("/"),
            timeout=httpx.Timeout(
                connect=settings.portal_connect_timeout_seconds,
                read=settings.portal_read_timeout_seconds,
                write=settings.portal_write_timeout_seconds,
                pool=settings.portal_pool_timeout_seconds,
            ),
            follow_redirects=True,
        )
        self._login_lock = asyncio.Lock()
        self._request_limit = asyncio.Semaphore(settings.portal_max_concurrency)
        self._breaker = CircuitBreaker(
            settings.portal_circuit_failure_threshold, settings.portal_circuit_reset_seconds
        )
        self._session_generation = 0
        self._authenticated_at: float | None = None
        self._last_sync_at: float | None = None
        self._reauth_failed_until: float | None = None
        self._login_count = 0
        self._retry_count = 0
        self._portal_latency_seconds: float | None = None

    async def aclose(self) -> None:
        await self.client.aclose()

    def _require_path(self, path: str, name: str) -> str:
        if not path:
            raise PortalConfigurationError(f"{name} is UNVERIFIED; configure it from captured portal evidence")
        parsed = urlsplit(path)
        if parsed.scheme or parsed.netloc or not path.startswith("/"):
            raise PortalConfigurationError(f"{name} must be a relative path on PORTAL_BASE_URL")
        return path

    def _is_login_page(self, response: httpx.Response) -> bool:
        markers = self.settings.portal_login_markers
        if not markers:
            return False
        body = response.text[:50_000]
        url = str(response.url)
        return any(marker in body or marker in url for marker in markers)

    def _is_expired(self, response: httpx.Response) -> bool:
        return response.status_code in {401, 403} or self._is_login_page(response)

    def _login_succeeded(self, response: httpx.Response) -> bool:
        if self.settings.portal_login_success_marker:
            return self.settings.portal_login_success_marker in response.text
        if self.settings.portal_login_success_cookie:
            return self.settings.portal_login_success_cookie in self.client.cookies
        if self.settings.portal_session_cookie_name:
            return self.settings.portal_session_cookie_name in self.client.cookies
        return False

    async def _login(self, expected_generation: int | None = None) -> None:
        path = self._require_path(self.settings.portal_login_path, "PORTAL_LOGIN_PATH")
        if not self.settings.portal_username or not self.settings.portal_password:
            raise PortalConfigurationError("Portal credentials are required for live mode")
        if self._reauth_failed_until is not None and monotonic() < self._reauth_failed_until:
            raise PortalSessionExpiredError("Portal reauthentication is cooling down after a failed session recovery")
        async with self._login_lock:
            if expected_generation is None and self._authenticated_at is not None:
                return
            if expected_generation is not None and self._session_generation != expected_generation:
                return
            if self._reauth_failed_until is not None and monotonic() < self._reauth_failed_until:
                raise PortalSessionExpiredError("Portal reauthentication is cooling down after a failed session recovery")
            try:
                async with self._request_limit:
                    response = await self.client.post(
                        path,
                        data={
                            self.settings.portal_login_username_field: self.settings.portal_username,
                            self.settings.portal_login_password_field: self.settings.portal_password,
                        },
                    )
            except httpx.TimeoutException as exc:
                raise PortalTimeoutError("Portal login timed out") from exc
            except httpx.HTTPError as exc:
                raise PortalUnavailableError("Portal login request failed") from exc
            if response.status_code >= 400 or not self._login_succeeded(response):
                self._reauth_failed_until = monotonic() + self.settings.portal_reauth_cooldown_seconds
                raise PortalAuthenticationError("Portal login was rejected or did not establish a session")
            self._session_generation += 1
            self._authenticated_at = monotonic()
            self._reauth_failed_until = None
            self._login_count += 1

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        value = response.headers.get("Retry-After")
        if not value:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                timestamp = parsedate_to_datetime(value)
            except (TypeError, ValueError, IndexError):
                return None
            if timestamp.tzinfo is None:
                return None
            return max(0.0, timestamp.timestamp() - datetime.now(UTC).timestamp())

    def _remember_reauth_failure(self) -> None:
        self._reauth_failed_until = monotonic() + self.settings.portal_reauth_cooldown_seconds

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(self.settings.portal_max_retries + 1):
            self._breaker.before_call()
            generation = self._session_generation
            started = monotonic()
            try:
                async with self._request_limit:
                    response = await self.client.request(method, path, **kwargs)
                if self._is_expired(response):
                    await self._login(generation)
                    async with self._request_limit:
                        response = await self.client.request(method, path, **kwargs)
                    if self._is_expired(response):
                        self._remember_reauth_failure()
                        raise PortalSessionExpiredError("Portal session remained expired after reauthentication")
                if response.status_code == 404:
                    raise PortalNotFoundError("Portal resource was not found")
                if response.status_code in {408, 429, 500, 502, 503, 504}:
                    self._breaker.record_failure()
                    last_error = PortalUnavailableError(f"Portal returned transient status {response.status_code}")
                    if attempt >= self.settings.portal_max_retries:
                        break
                    self._retry_count += 1
                    delay = self._retry_after(response)
                    await asyncio.sleep(delay if delay is not None else (0.15 * (2**attempt)) + random.uniform(0, 0.1))
                    continue
                if response.status_code >= 400:
                    raise PortalError(f"Portal returned status {response.status_code}")
                self._breaker.record_success()
                self._last_sync_at = monotonic()
                self._portal_latency_seconds = monotonic() - started
                return response
            except PortalCircuitOpenError:
                raise
            except PortalNotFoundError:
                raise
            except PortalSessionExpiredError:
                raise
            except PortalAuthenticationError:
                raise
            except (httpx.TimeoutException, PortalUnavailableError) as exc:
                last_error = PortalTimeoutError("Portal request timed out") if isinstance(exc, httpx.TimeoutException) else exc
                self._breaker.record_failure()
                if attempt >= self.settings.portal_max_retries:
                    break
                self._retry_count += 1
                await asyncio.sleep((0.15 * (2**attempt)) + random.uniform(0, 0.1))
            except httpx.HTTPError as exc:
                last_error = PortalUnavailableError("Portal request failed")
                self._breaker.record_failure()
                if attempt >= self.settings.portal_max_retries:
                    break
                self._retry_count += 1
                await asyncio.sleep((0.15 * (2**attempt)) + random.uniform(0, 0.1))
                logger.debug("portal request retry", extra={"fields": {"error": type(exc).__name__}})
        if last_error is not None:
            raise last_error
        raise PortalUnavailableError("Portal request failed")

    async def _parsed(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self._request(method, path, **kwargs)
        if len(response.content) > self.settings.portal_max_response_bytes:
            raise PortalSchemaDriftError("Portal response exceeded the configured size limit")
        try:
            payload = parse_payload(response.text, response.headers.get("content-type"))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise PortalSchemaDriftError("Portal response was not valid JSON or HTML") from exc
        return payload

    def _parse_settings(self) -> dict[str, Any]:
        return {
            "timezone_name": self.settings.portal_timezone,
            "date_format": self.settings.portal_date_format,
            "number_locale": self.settings.portal_number_locale,
            "target_unit": self.settings.portal_consumption_unit or None,
            "reading_kind": self.settings.portal_reading_kind,
        }

    def _meter_parse_settings(self) -> dict[str, Any]:
        settings = self._parse_settings()
        settings.pop("target_unit", None)
        settings.pop("reading_kind", None)
        return settings

    async def list_meters(self) -> list[Meter]:
        path = self._require_path(self.settings.portal_meter_list_path, "PORTAL_METER_LIST_PATH")
        payload = await self._parsed("GET", path)
        meters = parse_meters(payload, **self._meter_parse_settings())
        if payload_has_records(payload) and not meters:
            raise PortalSchemaDriftError("Meter response was non-empty but matched no known meter shape")
        return meters

    async def get_meter(self, meter_id: str) -> Meter | None:
        template = self._require_path(self.settings.portal_meter_detail_path, "PORTAL_METER_DETAIL_PATH")
        payload = await self._parsed("GET", template.format(id=meter_id, meter_id=meter_id))
        meters = parse_meters(payload, **self._meter_parse_settings())
        if payload_has_records(payload) and not meters:
            raise PortalSchemaDriftError("Meter detail response did not match a known meter shape")
        return meters[0] if meters else None

    async def get_consumption(
        self, meter_id: str, start: date | None = None, end: date | None = None
    ) -> list[ConsumptionPoint]:
        template = self._require_path(self.settings.portal_consumption_path, "PORTAL_CONSUMPTION_PATH")
        path = template.format(id=meter_id, meter_id=meter_id)
        params = {key: value.isoformat() for key, value in {"start": start, "end": end}.items() if value}
        payload = await self._parsed("GET", path, params=params)
        points = parse_consumption(payload, **self._parse_settings())
        if payload_has_records(payload) and not points:
            raise PortalSchemaDriftError("Consumption response was non-empty but matched no known reading shape")
        return points

    async def get_hierarchy(self) -> list[HierarchyNode]:
        path = self._require_path(self.settings.portal_hierarchy_path, "PORTAL_HIERARCHY_PATH")
        payload = await self._parsed("GET", path)
        if isinstance(payload, dict):
            for key in ("hierarchy", "nodes", "data", "results"):
                if isinstance(payload.get(key), list):
                    payload = payload[key]
                    break
        if isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
            if any("children" in item for item in payload):
                return [self._validate_hierarchy(item) for item in payload]
            return reconstruct_hierarchy(payload)
        if payload_has_records(payload):
            raise PortalSchemaDriftError("Hierarchy response did not match a known list or wrapped-list shape")
        return []

    @staticmethod
    def _validate_hierarchy(item: dict[str, Any]) -> HierarchyNode:
        try:
            return HierarchyNode.model_validate(item)
        except ValueError:
            item_id = str(item.get("id") or item.get("node_id") or "unknown")
            return HierarchyNode(
                id=item_id,
                quality=QualitySummary(
                    flags=[QualityFlag.INVALID], issue_count=1, notes=["hierarchy record failed validation"]
                ),
            )

    async def health(self) -> dict[str, object]:
        configured = bool(
            self.settings.portal_login_path
            and self.settings.portal_meter_list_path
            and (
                self.settings.portal_login_success_marker
                or self.settings.portal_login_success_cookie
                or self.settings.portal_session_cookie_name
            )
        )
        return {
            "mode": "live",
            "configured": configured,
            "authenticated": self._authenticated_at is not None,
            "session_age_seconds": monotonic() - self._authenticated_at if self._authenticated_at else None,
            "last_sync_age_seconds": monotonic() - self._last_sync_at if self._last_sync_at else None,
            "session_generation": self._session_generation,
            "login_count": self._login_count,
            "retry_count": self._retry_count,
            "breaker_state": self._breaker.state,
            "portal_latency_seconds": self._portal_latency_seconds,
        }

    async def check_reachability(self) -> bool:
        path = self._require_path(self.settings.portal_meter_list_path, "PORTAL_METER_LIST_PATH")
        await self._request("GET", path)
        return True
