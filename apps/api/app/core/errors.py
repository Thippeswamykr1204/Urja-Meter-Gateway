from dataclasses import dataclass
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


@dataclass(slots=True)
class ApiProblem(Exception):
    status: int
    code: str
    title: str
    detail: str
    extra: dict[str, Any] | None = None


def problem_response(request: Request, problem: ApiProblem) -> JSONResponse:
    payload: dict[str, Any] = {
        "type": f"https://api.flockenergy.tech/problems/{problem.code}",
        "title": problem.title,
        "status": problem.status,
        "detail": problem.detail,
        "code": problem.code,
        "request_id": getattr(request.state, "request_id", "-"),
    }
    if problem.extra:
        payload.update(problem.extra)
    return JSONResponse(payload, status_code=problem.status, media_type="application/problem+json")
