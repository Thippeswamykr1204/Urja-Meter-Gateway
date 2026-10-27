from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from app.adapter.http import HttpPortalAdapter
from app.core.config import Settings


def is_configured(value: str) -> bool:
    return bool(value.strip())


def missing_configuration(settings: Settings) -> list[str]:
    missing = [
        field_name.upper()
        for field_name, field_info in type(settings).model_fields.items()
        if field_name.startswith("portal_")
        and field_info.annotation is str
        and not is_configured(str(getattr(settings, field_name)))
    ]

    if not any(
        (
            settings.portal_login_success_marker,
            settings.portal_login_success_cookie,
            settings.portal_session_cookie_name,
        )
    ):
        missing.append(
            "one of PORTAL_LOGIN_SUCCESS_MARKER, "
            "PORTAL_LOGIN_SUCCESS_COOKIE, or PORTAL_SESSION_COOKIE_NAME"
        )

    return missing


def safe_health(health: dict[str, object]) -> dict[str, object]:
    allowed = {
        "mode",
        "configured",
        "authenticated",
        "session_age_seconds",
        "last_sync_age_seconds",
        "session_generation",
        "login_count",
        "retry_count",
        "breaker_state",
        "portal_latency_seconds",
    }
    return {key: value for key, value in health.items() if key in allowed}


async def run() -> int:
    settings = Settings()
    settings.validate_runtime()

    if settings.demo_mode:
        print(
            "Refusing live smoke: DEMO_MODE must be false.",
            file=sys.stderr,
        )
        return 2

    if not settings.allow_live_smoke:
        print(
            "Refusing live smoke: ALLOW_LIVE_SMOKE must be true.",
            file=sys.stderr,
        )
        return 2

    missing = missing_configuration(settings)
    if missing:
        print("Refusing live smoke; incomplete configuration:", file=sys.stderr)
        for item in missing:
            print(f"- {item}", file=sys.stderr)
        return 2

    adapter = HttpPortalAdapter(settings)
    result: dict[str, Any] = {
        "status": "started",
        "operations": {},
    }

    try:
        meters = await adapter.list_meters()
        result["operations"]["meter_list"] = {
            "status": "ok",
            "count": len(meters),
        }

        if is_configured(settings.portal_meter_detail_path) and meters:
            detail = await adapter.get_meter(meters[0].id)
            result["operations"]["meter_detail"] = {
                "status": "ok",
                "returned": detail is not None,
            }
        else:
            result["operations"]["meter_detail"] = {
                "status": "skipped",
                "reason": (
                    "PORTAL_METER_DETAIL_PATH is UNVERIFIED or "
                    "the meter list was empty"
                ),
            }

        if is_configured(settings.portal_consumption_path) and meters:
            points = await adapter.get_consumption(meters[0].id)
            result["operations"]["consumption"] = {
                "status": "ok",
                "count": len(points),
            }
        else:
            result["operations"]["consumption"] = {
                "status": "skipped",
                "reason": (
                    "PORTAL_CONSUMPTION_PATH is UNVERIFIED or "
                    "the meter list was empty"
                ),
            }

        if is_configured(settings.portal_hierarchy_path):
            hierarchy = await adapter.get_hierarchy()
            result["operations"]["hierarchy"] = {
                "status": "ok",
                "root_count": len(hierarchy),
            }
        else:
            result["operations"]["hierarchy"] = {
                "status": "skipped",
                "reason": "PORTAL_HIERARCHY_PATH is UNVERIFIED",
            }

        result["health"] = safe_health(await adapter.health())
        result["status"] = "ok"
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as error:
        result["status"] = "failed"
        result["error_type"] = type(error).__name__
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1
    finally:
        await adapter.aclose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
