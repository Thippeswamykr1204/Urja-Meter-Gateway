import httpx
import pytest
from app.adapter.http import HttpPortalAdapter
from app.core.config import Settings
from tools.mock_portal.server import app


@pytest.mark.asyncio
async def test_mock_portal_supports_cookie_login_and_hierarchy() -> None:
    transport = httpx.ASGITransport(app=app)
    settings = Settings(
        demo_mode=False,
        portal_base_url="http://mock.test",
        portal_username="operator",
        portal_password="secret",
        portal_login_path="/login",
        portal_meter_list_path="/meters",
        portal_meter_detail_path="/meters/{id}",
        portal_consumption_path="/consumption/{id}",
        portal_hierarchy_path="/hierarchy",
        portal_session_cookie_name="mock_session",
        portal_login_page_markers="status=login",
        portal_max_retries=0,
    )
    adapter = HttpPortalAdapter(settings)
    await adapter.client.aclose()
    adapter.client = httpx.AsyncClient(base_url=settings.portal_base_url, transport=transport, follow_redirects=True)
    meters = await adapter.list_meters()
    hierarchy = await adapter.get_hierarchy()
    await adapter.aclose()
    assert meters[0].id == "MTR-1001"
    assert hierarchy[0].id == "grid"
