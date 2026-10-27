import asyncio

import httpx
import pytest
import respx
from app.adapter.errors import (
    PortalAuthenticationError,
    PortalCircuitOpenError,
    PortalConfigurationError,
    PortalError,
    PortalSchemaDriftError,
    PortalSessionExpiredError,
    PortalUnavailableError,
)
from app.adapter.http import HttpPortalAdapter
from app.core.config import Settings


@pytest.mark.asyncio
@respx.mock
async def test_adapter_reauthenticates_after_login_page_with_200() -> None:
    settings = Settings(
        demo_mode=False,
        portal_base_url="https://portal.test",
        portal_username="operator",
        portal_password="secret",
        portal_login_path="/login",
        portal_meter_list_path="/meters",
        portal_login_success_marker="dashboard",
        portal_login_page_markers="<form>",
        portal_max_retries=0,
    )
    login = respx.post("https://portal.test/login").mock(return_value=httpx.Response(200, text="dashboard"))
    meter = respx.get("https://portal.test/meters").mock(
        side_effect=[httpx.Response(200, text="<form><input name='username'><input type='password'></form>"), httpx.Response(200, json={"meters": [{"id": "M1"}]})]
    )
    adapter = HttpPortalAdapter(settings)
    meters = await adapter.list_meters()
    await adapter.aclose()
    assert meters[0].id == "M1"
    assert login.called
    assert meter.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_login_requires_affirmative_marker() -> None:
    settings = Settings(
        demo_mode=False,
        portal_base_url="https://portal.test",
        portal_username="operator",
        portal_password="secret",
        portal_login_path="/login",
        portal_meter_list_path="/meters",
        portal_login_success_marker="dashboard",
        portal_max_retries=0,
    )
    respx.get("https://portal.test/meters").mock(return_value=httpx.Response(401))
    respx.post("https://portal.test/login").mock(return_value=httpx.Response(200, text="still login"))
    adapter = HttpPortalAdapter(settings)
    with pytest.raises(PortalAuthenticationError):
        await adapter.list_meters()
    await adapter.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_retry_checks_expiry_again() -> None:
    settings = Settings(
        demo_mode=False,
        portal_base_url="https://portal.test",
        portal_username="operator",
        portal_password="secret",
        portal_login_path="/login",
        portal_meter_list_path="/meters",
        portal_login_success_marker="dashboard",
        portal_login_page_markers="<form>",
        portal_max_retries=0,
    )
    respx.get("https://portal.test/meters").mock(return_value=httpx.Response(200, text="<form>login</form>"))
    respx.post("https://portal.test/login").mock(return_value=httpx.Response(200, text="dashboard"))
    adapter = HttpPortalAdapter(settings)
    with pytest.raises(PortalSessionExpiredError):
        await adapter.list_meters()
    await adapter.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_concurrent_expiry_uses_one_login() -> None:
    settings = Settings(
        demo_mode=False,
        portal_base_url="https://portal.test",
        portal_username="operator",
        portal_password="secret",
        portal_login_path="/login",
        portal_meter_list_path="/meters",
        portal_login_success_marker="dashboard",
        portal_login_page_markers="<form>",
        portal_max_retries=0,
    )
    calls = 0

    def meter_response(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, text="<form>login</form>") if calls == 1 else httpx.Response(200, json={"meters": [{"id": "M1"}]})

    meter = respx.get("https://portal.test/meters").mock(side_effect=meter_response)
    login = respx.post("https://portal.test/login").mock(return_value=httpx.Response(200, text="dashboard"))
    adapter = HttpPortalAdapter(settings)
    results = await asyncio.gather(adapter.list_meters(), adapter.list_meters())
    assert all(result[0].id == "M1" for result in results)
    assert login.call_count == 1
    assert meter.call_count == 3
    await adapter.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_reauth_failure_cooldown_prevents_login_storm() -> None:
    settings = Settings(
        demo_mode=False,
        portal_base_url="https://portal.test",
        portal_username="operator",
        portal_password="secret",
        portal_login_path="/login",
        portal_meter_list_path="/meters",
        portal_login_success_marker="dashboard",
        portal_login_page_markers="<form>",
        portal_max_retries=0,
        portal_reauth_cooldown_seconds=60,
    )
    respx.get("https://portal.test/meters").mock(return_value=httpx.Response(200, text="<form>login</form>"))
    login = respx.post("https://portal.test/login").mock(return_value=httpx.Response(200, text="dashboard"))
    adapter = HttpPortalAdapter(settings)
    with pytest.raises(PortalSessionExpiredError):
        await adapter.list_meters()
    with pytest.raises(PortalSessionExpiredError):
        await adapter.list_meters()
    assert login.call_count == 1
    await adapter.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_retry_after_is_honored_for_transient_response() -> None:
    settings = Settings(
        demo_mode=False,
        portal_base_url="https://portal.test",
        portal_username="operator",
        portal_password="secret",
        portal_login_path="/login",
        portal_meter_list_path="/meters",
        portal_login_success_marker="dashboard",
        portal_max_retries=1,
    )
    route = respx.get("https://portal.test/meters").mock(
        side_effect=[httpx.Response(503, headers={"Retry-After": "0"}), httpx.Response(200, json={"meters": [{"id": "M1"}]})]
    )
    adapter = HttpPortalAdapter(settings)
    meters = await adapter.list_meters()
    assert meters[0].id == "M1"
    assert route.call_count == 2
    assert (await adapter.health())["retry_count"] == 1
    await adapter.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_breaker_fails_fast_and_reports_recovery_state() -> None:
    settings = Settings(
        demo_mode=False,
        portal_base_url="https://portal.test",
        portal_username="operator",
        portal_password="secret",
        portal_login_path="/login",
        portal_meter_list_path="/meters",
        portal_login_success_marker="dashboard",
        portal_max_retries=0,
        portal_circuit_failure_threshold=1,
        portal_circuit_reset_seconds=60,
    )
    respx.get("https://portal.test/meters").mock(return_value=httpx.Response(503))
    adapter = HttpPortalAdapter(settings)
    with pytest.raises(PortalUnavailableError):
        await adapter.list_meters()
    with pytest.raises(PortalCircuitOpenError):
        await adapter.list_meters()
    assert (await adapter.health())["breaker_state"] == "open"
    await adapter.aclose()


@pytest.mark.asyncio
async def test_adapter_uses_configured_timeout_components() -> None:
    settings = Settings(
        demo_mode=False,
        portal_base_url="https://portal.test",
        portal_connect_timeout_seconds=1.25,
        portal_read_timeout_seconds=2.5,
        portal_write_timeout_seconds=3.75,
        portal_pool_timeout_seconds=4.5,
    )
    adapter = HttpPortalAdapter(settings)
    assert adapter.client.timeout.connect == 1.25
    assert adapter.client.timeout.read == 2.5
    assert adapter.client.timeout.write == 3.75
    assert adapter.client.timeout.pool == 4.5
    await adapter.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_non_empty_unknown_response_raises_schema_drift() -> None:
    settings = Settings(
        demo_mode=False,
        portal_base_url="https://portal.test",
        portal_meter_list_path="/meters",
        portal_max_retries=0,
    )
    respx.get("https://portal.test/meters").mock(
        return_value=httpx.Response(200, json={"unexpected": [{"value": 1}]})
    )
    adapter = HttpPortalAdapter(settings)
    with pytest.raises(PortalSchemaDriftError, match="matched no known meter shape"):
        await adapter.list_meters()
    await adapter.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_malformed_json_response_raises_schema_drift() -> None:
    settings = Settings(
        demo_mode=False,
        portal_base_url="https://portal.test",
        portal_meter_list_path="/meters",
        portal_max_retries=0,
    )
    respx.get("https://portal.test/meters").mock(
        return_value=httpx.Response(200, headers={"content-type": "application/json"}, text="{broken")
    )
    adapter = HttpPortalAdapter(settings)
    with pytest.raises(PortalSchemaDriftError, match="not valid JSON or HTML"):
        await adapter.list_meters()
    await adapter.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_non_transient_status_is_not_retried() -> None:
    settings = Settings(
        demo_mode=False,
        portal_base_url="https://portal.test",
        portal_meter_list_path="/meters",
        portal_max_retries=3,
    )
    route = respx.get("https://portal.test/meters").mock(
        return_value=httpx.Response(400)
    )
    adapter = HttpPortalAdapter(settings)
    with pytest.raises(PortalError, match="status 400"):
        await adapter.list_meters()
    assert route.call_count == 1
    await adapter.aclose()


@pytest.mark.asyncio
async def test_absolute_upstream_path_is_rejected() -> None:
    settings = Settings(
        demo_mode=False,
        portal_base_url="https://portal.test",
        portal_meter_list_path="https://other.test/meters",
    )
    adapter = HttpPortalAdapter(settings)
    with pytest.raises(PortalConfigurationError, match="relative path"):
        await adapter.list_meters()
    await adapter.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_login_accepts_configured_cookie_signal() -> None:
    settings = Settings(
        demo_mode=False,
        portal_base_url="https://portal.test",
        portal_username="operator",
        portal_password="secret",
        portal_login_path="/login",
        portal_login_success_cookie="session",
    )
    respx.post("https://portal.test/login").mock(
        return_value=httpx.Response(200, headers={"set-cookie": "session=ok; Path=/"})
    )
    adapter = HttpPortalAdapter(settings)
    await adapter._login()
    assert (await adapter.health())["authenticated"] is True
    await adapter.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_login_without_credentials_is_configuration_error() -> None:
    settings = Settings(
        demo_mode=False,
        portal_base_url="https://portal.test",
        portal_username="",
        portal_password="",
        portal_login_path="/login",
        portal_meter_list_path="/meters",
        portal_login_success_marker="dashboard",
        portal_max_retries=0,
    )
    respx.get("https://portal.test/meters").mock(return_value=httpx.Response(401))
    adapter = HttpPortalAdapter(settings)
    with pytest.raises(PortalConfigurationError, match="credentials"):
        await adapter.list_meters()
    await adapter.aclose()


def test_retry_after_parses_numeric_and_http_date_values() -> None:
    assert HttpPortalAdapter._retry_after(httpx.Response(429, headers={"Retry-After": "0"})) == 0
    assert HttpPortalAdapter._retry_after(httpx.Response(429, headers={"Retry-After": "not-a-date"})) is None
    assert HttpPortalAdapter._retry_after(httpx.Response(429)) is None


@pytest.mark.asyncio
@respx.mock
async def test_detail_and_consumption_schema_drift_are_rejected() -> None:
    settings = Settings(
        demo_mode=False,
        portal_base_url="https://portal.test",
        portal_meter_detail_path="/meters/{id}",
        portal_consumption_path="/meters/{id}/consumption",
        portal_max_retries=0,
    )
    respx.get("https://portal.test/meters/M1").mock(
        return_value=httpx.Response(200, json={"unexpected": [{"value": 1}]})
    )
    respx.get("https://portal.test/meters/M1/consumption").mock(
        return_value=httpx.Response(200, json={"unexpected": [{"value": 1}]})
    )
    adapter = HttpPortalAdapter(settings)
    with pytest.raises(PortalSchemaDriftError, match="detail response"):
        await adapter.get_meter("M1")
    with pytest.raises(PortalSchemaDriftError, match="Consumption response"):
        await adapter.get_consumption("M1")
    await adapter.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_hierarchy_accepts_nested_and_empty_shapes() -> None:
    settings = Settings(
        demo_mode=False,
        portal_base_url="https://portal.test",
        portal_hierarchy_path="/hierarchy",
        portal_max_retries=0,
    )
    route = respx.get("https://portal.test/hierarchy").mock(
        side_effect=[
            httpx.Response(200, json=[{"id": "root", "children": [{"id": "child"}]}]),
            httpx.Response(200, json=[]),
        ]
    )
    adapter = HttpPortalAdapter(settings)
    roots = await adapter.get_hierarchy()
    assert roots[0].children[0].id == "child"
    assert await adapter.get_hierarchy() == []
    assert route.call_count == 2
    await adapter.aclose()
