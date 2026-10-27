from __future__ import annotations

from tools.sanitize_har.main import assert_sanitized, sanitize_har, write_summary


def test_sanitize_har_redacts_credentials_and_preserves_structure(tmp_path) -> None:
    har = {
        "log": {
            "version": "1.2",
            "entries": [
                {
                    "time": 12.5,
                    "timings": {"wait": 4},
                    "request": {
                        "method": "POST",
                        "url": "https://portal.example/login?email=person@example.com",
                        "headers": [{"name": "Authorization", "value": "Bearer super-secret-token"}],
                        "queryString": [{"name": "email", "value": "person@example.com"}],
                        "postData": {
                            "mimeType": "application/x-www-form-urlencoded",
                            "params": [
                                {"name": "username", "value": "person@example.com"},
                                {"name": "password", "value": "correct-horse"},
                                {"name": "csrf_token", "value": "csrf-value"},
                            ],
                        },
                    },
                    "response": {
                        "status": 302,
                        "redirectURL": "https://portal.example/meters?token=session-value",
                        "headers": [
                            {"name": "Set-Cookie", "value": "session=session-value; Path=/; HttpOnly"},
                            {"name": "Content-Type", "value": "text/html"},
                        ],
                        "content": {"mimeType": "text/html", "text": '<input name="password" value="correct-horse">'},
                    },
                }
            ],
        }
    }

    sanitized, summaries, redactor = sanitize_har(har)
    assert_sanitized(sanitized, redactor)

    serialized = str(sanitized)
    assert "correct-horse" not in serialized
    assert "session-value" not in serialized
    assert "person@example.com" not in serialized
    assert summaries[0]["path"] == "/login"
    assert summaries[0]["redirect"] is True
    assert summaries[0]["csrf_names"] == ["csrf_token"]
    assert summaries[0]["cookie_names"] == ["session; Path; HttpOnly"]

    summary_path = tmp_path / "recon-notes.md"
    write_summary(summary_path, summaries, "capture.har")
    summary = summary_path.read_text(encoding="utf-8")
    assert "`/login`" in summary
    assert "correct-horse" not in summary


def test_sanitize_har_sanitizes_json_and_base64_response() -> None:
    har = {
        "log": {
            "entries": [
                {
                    "request": {"method": "GET", "url": "https://portal.example/api"},
                    "response": {
                        "status": 200,
                        "content": {
                            "mimeType": "application/json",
                            "encoding": "base64",
                            "text": "eyJlbWFpbCI6InBlcnNvbkBleGFtcGxlLmNvbSIsInRva2VuIjoic2VjcmV0In0=",
                        },
                    },
                }
            ]
        }
    }

    sanitized, _, redactor = sanitize_har(har)
    assert_sanitized(sanitized, redactor)
    assert sanitized["log"]["entries"][0]["response"]["content"]["encoding"] == "base64"
