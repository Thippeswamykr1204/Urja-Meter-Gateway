import asyncio
import json
from pathlib import Path

from fastapi import Cookie, FastAPI, Header, HTTPException, Query, Response

ROOT = Path(__file__).parents[2]
FIXTURES = ROOT / "fixtures" / "portal"
app = FastAPI(title="Sanitized Urja mock portal")
SESSIONS: set[str] = set()


def fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text())


async def fault_response(fault: str | None, response: Response) -> None:
    if fault == "slow":
        await asyncio.sleep(2)
    if fault == "rate-limit":
        raise HTTPException(status_code=429, detail="mock rate limit")
    if fault == "500":
        raise HTTPException(status_code=500, detail="mock upstream failure")
    if fault == "404":
        raise HTTPException(status_code=404, detail="mock not found")


def malformed_response() -> Response:
    return Response("<html><table><tr><td>broken", media_type="text/html")


@app.post("/login")
async def login(response: Response, fault: str | None = Header(default=None, alias="X-Mock-Fault")) -> dict[str, str]:
    await fault_response(fault, response)
    if fault == "malformed":
        return malformed_response()
    if fault == "login-200":
        return {"status": "login"}
    SESSIONS.add("mock-session")
    response.set_cookie("mock_session", "mock-session", httponly=True, samesite="lax")
    return {"status": "dashboard"}


def require_session(
    session: str | None,
    fault: str | None,
) -> None:
    if fault == "expired" or session not in SESSIONS:
        raise HTTPException(status_code=401, detail="mock session expired")


@app.get("/meters")
async def meters(
    response: Response,
    mock_session: str | None = Cookie(default=None),
    fault: str | None = Header(default=None, alias="X-Mock-Fault"),
) -> object:
    await fault_response(fault, response)
    if fault == "malformed":
        return malformed_response()
    require_session(mock_session, fault)
    if fault == "login-200":
        return {"status": "login"}
    return fixture("meters.json")


@app.get("/meters/{meter_id}")
async def meter_detail(
    meter_id: str,
    response: Response,
    mock_session: str | None = Cookie(default=None),
    fault: str | None = Header(default=None, alias="X-Mock-Fault"),
) -> object:
    await fault_response(fault, response)
    if fault == "malformed":
        return malformed_response()
    require_session(mock_session, fault)
    meters_data = fixture("meters.json")
    for meter in meters_data["meters"]:  # type: ignore[index]
        if meter["id"] == meter_id:  # type: ignore[index]
            return {"meters": [meter]}
    raise HTTPException(status_code=404, detail="mock meter not found")


@app.get("/consumption/{meter_id}")
async def consumption(
    meter_id: str,
    response: Response,
    mock_session: str | None = Cookie(default=None),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    fault: str | None = Header(default=None, alias="X-Mock-Fault"),
) -> object:
    await fault_response(fault, response)
    if fault == "malformed":
        return malformed_response()
    require_session(mock_session, fault)
    if meter_id not in {"MTR-1001", "MTR-1002"}:
        raise HTTPException(status_code=404, detail="mock meter not found")
    return fixture("consumption.json")


@app.get("/hierarchy")
async def hierarchy(
    response: Response,
    mock_session: str | None = Cookie(default=None),
    fault: str | None = Header(default=None, alias="X-Mock-Fault"),
) -> object:
    await fault_response(fault, response)
    require_session(mock_session, fault)
    return fixture("hierarchy.json")
