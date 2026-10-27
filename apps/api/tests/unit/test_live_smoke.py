from app.core.config import Settings
from tools.live_smoke import missing_configuration


def test_missing_configuration_lists_empty_portal_settings_without_values() -> None:
    missing = missing_configuration(
        Settings(
            portal_username="",
            portal_password="",
            portal_login_path="",
            portal_meter_list_path="",
            portal_meter_detail_path="",
            portal_consumption_path="",
            portal_hierarchy_path="",
            portal_session_cookie_name="",
            portal_login_success_cookie="",
            portal_login_success_marker="",
        )
    )

    assert "PORTAL_USERNAME" in missing
    assert "PORTAL_PASSWORD" in missing
    assert "PORTAL_LOGIN_PATH" in missing
    assert "PORTAL_METER_LIST_PATH" in missing
    assert any(item.startswith("one of PORTAL_LOGIN_SUCCESS_MARKER") for item in missing)
    assert all("local-development" not in item for item in missing)
