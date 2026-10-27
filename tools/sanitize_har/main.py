from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
SECRET_KEY_PATTERN = re.compile(
    r"(?i)(password|passwd|authorization|cookie|token|secret|api[_-]?key|csrf|xsrf|session|user(name)?|login|email)"
)
PAGINATION_PATTERN = re.compile(r"(?i)(page|cursor|offset|limit|size|next|previous|prev)")
COOKIE_ATTRIBUTE_NAMES = {"path", "domain", "expires", "max-age", "samesite", "secure", "httponly", "partitioned"}


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]


@dataclass
class Redactor:
    known_secrets: set[str] = field(default_factory=set)

    def redact(self, category: str, value: str) -> str:
        if not value:
            return value
        self.known_secrets.add(value)
        return f"<REDACTED_{category.upper()}_{_digest(value)}>"

    def text(self, value: str) -> str:
        value = EMAIL_PATTERN.sub(lambda match: self.redact("email", match.group(0)), value)
        value = BEARER_PATTERN.sub(lambda match: self.redact("authorization", match.group(0)), value)
        for secret in sorted(self.known_secrets, key=len, reverse=True):
            if secret and secret in value:
                value = value.replace(secret, self.redact("secret", secret))
        return value


def _is_sensitive_key(key: str) -> bool:
    return bool(SECRET_KEY_PATTERN.search(key))


def _sanitize_value(value: Any, redactor: Redactor, key: str = "") -> Any:
    if isinstance(value, dict):
        return {
            str(item_key): (
                redactor.redact("secret", str(item_value))
                if _is_sensitive_key(str(item_key)) and isinstance(item_value, str)
                else _sanitize_value(item_value, redactor, str(item_key))
            )
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_value(item, redactor, key) for item in value]
    if isinstance(value, str):
        return redactor.text(value)
    return value


def _header_value(headers: list[dict[str, Any]], name: str) -> str | None:
    for header in headers:
        if str(header.get("name", "")).lower() == name.lower():
            return str(header.get("value", ""))
    return None


def _sanitize_cookie(value: str, redactor: Redactor) -> str:
    pieces = [piece.strip() for piece in value.split(";")]
    sanitized: list[str] = []
    for index, piece in enumerate(pieces):
        if "=" not in piece:
            sanitized.append(piece)
            continue
        name, raw_value = piece.split("=", 1)
        if index == 0 or name.strip().lower() not in COOKIE_ATTRIBUTE_NAMES:
            sanitized.append(f"{name.strip()}={redactor.redact('cookie', raw_value.strip())}")
        else:
            sanitized.append(f"{name.strip()}={redactor.text(raw_value.strip())}")
    return "; ".join(sanitized)


def _sanitize_headers(headers: list[dict[str, Any]], redactor: Redactor) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for header in headers:
        name = str(header.get("name", ""))
        value = str(header.get("value", ""))
        lower_name = name.lower()
        if lower_name in {"cookie", "set-cookie"}:
            value = _sanitize_cookie(value, redactor)
        elif _is_sensitive_key(name):
            value = redactor.redact("authorization", value)
        else:
            value = redactor.text(value)
        sanitized.append({**header, "name": name, "value": value})
    return sanitized


def _sanitize_url(url: str, redactor: Redactor) -> str:
    parts = urlsplit(url)
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        query.append((key, redactor.redact("query", value) if _is_sensitive_key(key) else redactor.text(value)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def _sanitize_post_data(post_data: dict[str, Any], redactor: Redactor) -> dict[str, Any]:
    result = dict(post_data)
    params = result.get("params")
    if isinstance(params, list):
        result["params"] = [
            {
                **param,
                "value": (
                    redactor.redact("form", str(param.get("value", "")))
                    if _is_sensitive_key(str(param.get("name", "")))
                    else redactor.text(str(param.get("value", "")))
                ),
            }
            for param in params
        ]
    if isinstance(result.get("text"), str):
        text = result["text"]
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            result["text"] = redactor.text(text)
        else:
            result["text"] = json.dumps(_sanitize_value(parsed, redactor), separators=(",", ":"), sort_keys=True)
    return result


def _decode_content(content: dict[str, Any]) -> str:
    text = str(content.get("text", ""))
    if content.get("encoding") == "base64":
        try:
            return base64.b64decode(text).decode("utf-8", errors="replace")
        except (ValueError, UnicodeError):
            return text
    return text


def _sanitize_content(content: dict[str, Any], redactor: Redactor) -> dict[str, Any]:
    result = dict(content)
    text = _decode_content(content)
    mime_type = str(content.get("mimeType", "")).lower()
    if "json" in mime_type:
        try:
            text = json.dumps(_sanitize_value(json.loads(text), redactor), indent=2, sort_keys=True)
        except json.JSONDecodeError:
            text = redactor.text(text)
    else:
        text = redactor.text(text)
    if content.get("encoding") == "base64":
        result["text"] = base64.b64encode(text.encode("utf-8")).decode("ascii")
    else:
        result["text"] = text
    return result


def _field_names(entry: dict[str, Any]) -> tuple[list[str], list[str]]:
    request = entry.get("request", {})
    query_names = [str(item.get("name", "")) for item in request.get("queryString", [])]
    form_names: list[str] = []
    post_data = request.get("postData", {})
    if isinstance(post_data, dict):
        form_names.extend(str(item.get("name", "")) for item in post_data.get("params", []) if item.get("name"))
        text = post_data.get("text")
        if isinstance(text, str):
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                form_names.extend(key for key, _ in parse_qsl(text, keep_blank_values=True))
            else:
                if isinstance(payload, dict):
                    form_names.extend(str(key) for key in payload)
    return sorted(set(query_names)), sorted(set(form_names))


def _cookie_summary(headers: list[dict[str, Any]]) -> list[str]:
    result: list[str] = []
    for header in headers:
        if str(header.get("name", "")).lower() != "set-cookie":
            continue
        pieces = [piece.strip() for piece in str(header.get("value", "")).split(";")]
        if pieces:
            result.append("; ".join(piece.split("=", 1)[0] if "=" in piece else piece for piece in pieces))
    return result


def _path(url: str) -> str:
    return urlsplit(url).path or "/"


def _entry_summary(entry: dict[str, Any], index: int) -> dict[str, Any]:
    request = entry.get("request", {})
    response = entry.get("response", {})
    query_names, form_names = _field_names(entry)
    response_headers = response.get("headers", [])
    csrf_names = sorted(
        {
            name
            for name in (*query_names, *form_names)
            if re.search(r"(?i)(csrf|xsrf)", name)
        }
    )
    pagination = sorted(
        {
            name
            for name in (*query_names, *form_names)
            if PAGINATION_PATTERN.search(name)
        }
    )
    redirect_url = str(response.get("redirectURL", ""))
    status = int(response.get("status", 0) or 0)
    return {
        "index": index,
        "method": str(request.get("method", "GET")).upper(),
        "path": _path(str(request.get("url", ""))),
        "status": status,
        "content_type": _header_value(response_headers, "content-type") or str(response.get("content", {}).get("mimeType", "")),
        "redirect": bool(redirect_url or 300 <= status < 400),
        "redirect_path": _path(redirect_url) if redirect_url else "",
        "query_names": query_names,
        "form_names": form_names,
        "pagination_names": pagination,
        "csrf_names": csrf_names,
        "cookie_names": _cookie_summary(response_headers),
        "response_headers": sorted(str(header.get("name", "")) for header in response_headers),
        "time_ms": entry.get("time"),
        "timings": entry.get("timings", {}),
    }


def sanitize_har(har: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], Redactor]:
    redactor = Redactor()
    sanitized = dict(har)
    log = dict(har.get("log", {}))
    entries: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for index, original in enumerate(log.get("entries", []), start=1):
        entry = dict(original)
        request = dict(entry.get("request", {}))
        response = dict(entry.get("response", {}))
        request["url"] = _sanitize_url(str(request.get("url", "")), redactor)
        request["headers"] = _sanitize_headers(list(request.get("headers", [])), redactor)
        if isinstance(request.get("queryString"), list):
            request["queryString"] = [
                {
                    **item,
                    "value": redactor.redact("query", str(item.get("value", "")))
                    if _is_sensitive_key(str(item.get("name", "")))
                    else redactor.text(str(item.get("value", ""))),
                }
                for item in request["queryString"]
            ]
        if isinstance(request.get("postData"), dict):
            request["postData"] = _sanitize_post_data(request["postData"], redactor)
        response["headers"] = _sanitize_headers(list(response.get("headers", [])), redactor)
        if isinstance(response.get("content"), dict):
            response["content"] = _sanitize_content(response["content"], redactor)
        if response.get("redirectURL"):
            response["redirectURL"] = _sanitize_url(str(response["redirectURL"]), redactor)
        entry["request"] = request
        entry["response"] = response
        entries.append(entry)
        summaries.append(_entry_summary(entry, index))
    log["entries"] = entries
    sanitized["log"] = log
    return sanitized, summaries, redactor


def assert_sanitized(payload: Any, redactor: Redactor) -> None:
    serialized = json.dumps(payload, sort_keys=True)
    for secret in redactor.known_secrets:
        if len(secret) >= 4 and secret in serialized:
            raise ValueError("sanitized HAR still contains a captured secret")
    if EMAIL_PATTERN.search(serialized) or BEARER_PATTERN.search(serialized):
        raise ValueError("sanitized HAR still contains a credential-shaped value")


def _fixture_extension(summary: dict[str, Any]) -> str:
    content_type = str(summary.get("content_type", "")).lower()
    if "html" in content_type:
        return ".html"
    if "json" in content_type:
        return ".json"
    if "javascript" in content_type:
        return ".js"
    return ".txt"


def _fixture_name(summary: dict[str, Any]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", f"{summary['method']}-{summary['path']}".lower()).strip("-")
    return f"{summary['index']:03d}-{slug or 'response'}{_fixture_extension(summary)}"


def write_summary(destination: Path, summaries: list[dict[str, Any]], source_name: str) -> None:
    lines = [
        "# Sanitized portal reconnaissance notes",
        "",
        f"Generated on **{date.today().isoformat()}** from `{source_name}`.",
        "",
        "Only request and response structure is recorded here. Credential values, cookie values, personal-looking values, and query/form values are redacted.",
        "",
        "## Captured entries",
        "",
        "| # | Method | Path | Status | Content type | Redirect | Query names | Form names | Pagination | CSRF names | Set-Cookie names/attributes | Response headers | Time (ms) | Timing details |",
        "|---:|---|---|---:|---|---|---|---|---|---|---|---|---:|---|",
    ]
    for summary in summaries:
        def join(values: list[str]) -> str:
            return ", ".join(values) if values else "—"

        timing_details = ", ".join(
            f"{key}={value}"
            for key, value in sorted(summary["timings"].items())
        ) or "—"
        lines.append(
            "| {index} | {method} | `{path}` | {status} | {content_type} | {redirect} | {query} | {form} | {pagination} | {csrf} | {cookies} | {headers} | {time} | {timings} |".format(
                index=summary["index"],
                method=summary["method"],
                path=summary["path"],
                status=summary["status"],
                content_type=summary["content_type"] or "—",
                redirect="yes" if summary["redirect"] else "no",
                query=join(summary["query_names"]),
                form=join(summary["form_names"]),
                pagination=join(summary["pagination_names"]),
                csrf=join(summary["csrf_names"]),
                cookies=join(summary["cookie_names"]),
                headers=join(summary["response_headers"]),
                time=summary["time_ms"] if summary["time_ms"] is not None else "—",
                timings=timing_details,
            )
        )
    lines.extend(
        [
            "",
            "## Capture notes",
            "",
            "- Redirect targets are recorded as paths only.",
            "- Query and form values are intentionally omitted from this summary.",
            "- Portal behavior remains `UNVERIFIED` until these structures are reviewed against the application contract.",
        ]
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_response_fixtures(destination: Path, sanitized_har: dict[str, Any], summaries: list[dict[str, Any]]) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    entries = sanitized_har.get("log", {}).get("entries", [])
    for entry, summary in zip(entries, summaries, strict=True):
        content = entry.get("response", {}).get("content", {})
        text = _decode_content(content)
        destination.joinpath(_fixture_name(summary)).write_text(text + ("\n" if text and not text.endswith("\n") else ""), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sanitize a browser HAR and write structural reconnaissance notes.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True, help="Destination for the sanitized HAR")
    parser.add_argument("--summary", type=Path, default=Path("docs/recon-notes.md"))
    parser.add_argument("--fixtures-dir", type=Path, help="Optional directory for sanitized response bodies")
    args = parser.parse_args()

    har = json.loads(args.source.read_text(encoding="utf-8"))
    sanitized, summaries, redactor = sanitize_har(har)
    assert_sanitized(sanitized, redactor)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(sanitized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_summary(args.summary, summaries, args.source.name)
    if args.fixtures_dir:
        write_response_fixtures(args.fixtures_dir, sanitized, summaries)
    print(f"Sanitized {len(summaries)} HAR entries; wrote structure only to {args.output} and {args.summary}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
