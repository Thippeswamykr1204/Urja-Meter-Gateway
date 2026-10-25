import httpx
import pytest
import respx
from app.adapter.errors import PortalAuthenticationError, PortalSessionExpiredError
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
