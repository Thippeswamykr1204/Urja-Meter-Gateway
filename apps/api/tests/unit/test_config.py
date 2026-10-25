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
