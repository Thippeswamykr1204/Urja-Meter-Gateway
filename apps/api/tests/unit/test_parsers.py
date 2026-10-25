import json
from pathlib import Path

from app.domain.models import QualityFlag
from app.parsers.portal import parse_consumption, parse_meters, parse_payload

FIXTURES = Path(__file__).parents[4] / "fixtures" / "portal"


def test_parse_json_meters_normalizes_fields() -> None:
    payload = parse_payload((FIXTURES / "meters.json").read_text(), "application/json")
    meters = parse_meters(payload)
    assert meters[0].id == "MTR-1001"
    assert meters[0].latitude == 12.9716
    assert meters[0].last_seen_at is not None


def test_parse_html_meters_uses_table_columns() -> None:
    payload = parse_payload((FIXTURES / "meters.html").read_text(), "text/html")
    meters = parse_meters(payload)
    assert meters[0].serial_number == "URJA-HTML-1"


def test_parse_consumption_preserves_invalid_values_as_quality_flags() -> None:
    payload = json.loads((FIXTURES / "consumption.json").read_text())
    points = parse_consumption(payload)
    assert points[0].value == 18.2
    assert points[2].value is None
    assert QualityFlag.INVALID in points[2].quality.flags
