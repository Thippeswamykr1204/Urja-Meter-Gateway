import pytest
from app.core.config import Settings


def test_production_rejects_local_keys() -> None:
    settings = Settings(app_env="production", demo_mode=False)
    with pytest.raises(ValueError, match="non-default"):
        settings.validate_runtime()


def test_production_requires_distinct_read_and_admin_keys() -> None:
    settings = Settings(app_env="production", demo_mode=False, api_read_key="same", api_admin_key="same")
    with pytest.raises(ValueError, match="different"):
        settings.validate_runtime()


def test_production_requires_live_mode_and_trusted_hosts() -> None:
    settings = Settings(
        app_env="production",
        api_read_key="read",
        api_admin_key="admin",
        portal_base_url="https://portal.example.test",
    )
    with pytest.raises(ValueError, match="DEMO_MODE=false"):
        settings.validate_runtime()

    settings.demo_mode = False
    with pytest.raises(ValueError, match="TRUSTED_HOSTS"):
        settings.validate_runtime()


def test_runtime_rejects_invalid_or_credentialed_portal_urls() -> None:
    with pytest.raises(ValueError, match="absolute http or https"):
        Settings(portal_base_url="portal.example.test").validate_runtime()
    with pytest.raises(ValueError, match="embedded credentials"):
        Settings(portal_base_url="https://user:password@portal.example.test").validate_runtime()
