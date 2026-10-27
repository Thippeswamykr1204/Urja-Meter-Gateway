from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: Literal["local", "test", "production"] = "local"
    demo_mode: bool = True
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_read_key: str = "local-development-read-key"
    api_admin_key: str = "local-development-admin-key"
    api_read_keys: str = ""
    api_admin_keys: str = ""
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    trusted_hosts: str = ""
    max_request_body_bytes: int = Field(default=1_048_576, ge=1024, le=10_485_760)
    database_url: str = "sqlite:///./flock_energy.db"
    portal_base_url: str = "https://urja-ops.flockenergy.tech"
    portal_username: str = ""
    portal_password: str = ""
    portal_login_path: str = ""
    portal_meter_list_path: str = ""
    portal_meter_detail_path: str = ""
    portal_consumption_path: str = ""
    portal_hierarchy_path: str = ""
    portal_login_username_field: str = "username"
    portal_login_password_field: str = "password"
    portal_session_cookie_name: str = ""
    portal_login_success_cookie: str = ""
    portal_login_success_marker: str = ""
    portal_login_page_markers: str = ""
    portal_timezone: str = "UTC"
    portal_date_format: str = ""
    portal_number_locale: Literal["auto", "en_US", "de_DE", "fr_FR"] = "auto"
    portal_consumption_unit: str = ""
    portal_reading_kind: Literal["unknown", "interval", "cumulative"] = "unknown"
    portal_timeout_seconds: float = Field(default=10.0, ge=1)
    portal_connect_timeout_seconds: float = Field(default=5.0, ge=0.1)
    portal_read_timeout_seconds: float = Field(default=10.0, ge=0.1)
    portal_write_timeout_seconds: float = Field(default=10.0, ge=0.1)
    portal_pool_timeout_seconds: float = Field(default=5.0, ge=0.1)
    portal_max_concurrency: int = Field(default=4, ge=1)
    portal_max_retries: int = Field(default=2, ge=0, le=5)
    portal_reauth_cooldown_seconds: float = Field(default=10.0, ge=0)
    portal_circuit_failure_threshold: int = Field(default=5, ge=1)
    portal_circuit_reset_seconds: int = Field(default=30, ge=1)
    portal_max_response_bytes: int = Field(default=5_000_000, ge=1024, le=50_000_000)
    rate_limit_per_minute: int = Field(default=120, ge=1)
    rate_limit_max_keys: int = Field(default=10_000, ge=100)
    sync_interval_seconds: int = Field(default=0, ge=0)
    sync_jitter_seconds: int = Field(default=5, ge=0)
    meter_metadata_ttl_seconds: int = Field(default=900, ge=0)
    hierarchy_ttl_seconds: int = Field(default=900, ge=0)
    recent_consumption_ttl_seconds: int = Field(default=300, ge=0)
    closed_history_ttl_seconds: int = Field(default=0, ge=0)
    max_date_range_days: int = Field(default=366, ge=1)
    max_response_records: int = Field(default=10_000, ge=1)
    allow_live_smoke: bool = False
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def sqlite_path(self) -> str:
        prefix = "sqlite:///"
        return self.database_url[len(prefix) :] if self.database_url.startswith(prefix) else self.database_url

    @property
    def portal_login_markers(self) -> tuple[str, ...]:
        return tuple(marker.strip() for marker in self.portal_login_page_markers.split(",") if marker.strip())

    @staticmethod
    def _split_keys(value: str) -> tuple[str, ...]:
        return tuple(item.strip() for item in value.split(",") if item.strip())

    @property
    def accepted_read_keys(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*self._split_keys(self.api_read_key), *self._split_keys(self.api_read_keys))))

    @property
    def accepted_admin_keys(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*self._split_keys(self.api_admin_key), *self._split_keys(self.api_admin_keys))))

    @property
    def allowed_origin_values(self) -> tuple[str, ...]:
        return self._split_keys(self.allowed_origins)

    @property
    def trusted_host_values(self) -> tuple[str, ...]:
        return self._split_keys(self.trusted_hosts)

    def validate_runtime(self) -> None:
        portal_url = urlsplit(self.portal_base_url)
        if portal_url.scheme not in {"http", "https"} or not portal_url.hostname:
            raise ValueError("PORTAL_BASE_URL must be an absolute http or https URL")
        if portal_url.username or portal_url.password:
            raise ValueError("PORTAL_BASE_URL must not contain embedded credentials")
        if self.app_env == "production":
            defaults = {"local-development-read-key", "local-development-admin-key"}
            if any(key in defaults for key in (*self.accepted_read_keys, *self.accepted_admin_keys)):
                raise ValueError("Production requires non-default API read and admin keys")
            if set(self.accepted_read_keys) & set(self.accepted_admin_keys):
                raise ValueError("API read and admin keys must be different")
            if self.demo_mode:
                raise ValueError("Production requires DEMO_MODE=false")
            if portal_url.scheme != "https":
                raise ValueError("Production requires an HTTPS PORTAL_BASE_URL")
            if not self.trusted_host_values:
                raise ValueError("Production requires TRUSTED_HOSTS")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
