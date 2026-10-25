from datetime import UTC

from app.domain.models import QualityFlag
from app.parsers.common import parse_number, parse_timestamp
from app.parsers.portal import parse_consumption, parse_meters
from bs4 import BeautifulSoup


def test_number_parser_handles_locales_and_embedded_units() -> None:
    assert parse_number("1.234,56", "de_DE").value == 1234.56
    assert parse_number("12,5", "auto").value == 12.5
    result = parse_number("0.5 MWh", "en_US")
    assert result.value == 0.5
    assert result.unit == "MWh"


def test_number_parser_marks_ambiguous_thousands_separator() -> None:
    result = parse_number("1,234", "auto")
    assert "ambiguous_number" in result.flags
    assert result.value is None


def test_timestamp_parser_keeps_original_and_marks_assumption() -> None:
    result = parse_timestamp("24/10/2026 10:00", "Asia/Kolkata", "%d/%m/%Y %H:%M")
    assert result.original == "24/10/2026 10:00"
    assert result.value is not None and result.value.tzinfo == UTC
    assert "assumed_timezone" in result.flags


def test_html_parser_maps_reordered_headers_without_tbody() -> None:
    html = """
    <table><tr><th>Status</th><th>Serial Number</th><th>Meter ID</th></tr>
    <tr><td>active</td><td>SN-1</td><td>M-1</td></tr>
    <tr><th>Status</th><th>Serial Number</th><th>Meter ID</th></tr>
    <tr><td>warning</td><td>SN-2</td><td>M-2</td></tr></table>
    """
    meters = parse_meters(BeautifulSoup(html, "html.parser"))
    assert [meter.id for meter in meters] == ["M-1", "M-2"]
    assert meters[0].serial_number == "SN-1"


def test_duplicate_meter_ids_are_retained_and_flagged() -> None:
    meters = parse_meters({"meters": [{"id": "M-1"}, {"id": "M-1"}]})
    assert len(meters) == 2
    assert all(QualityFlag.DUPLICATE in meter.quality.flags for meter in meters)


def test_reading_quality_distinguishes_missing_invalid_and_negative() -> None:
    points = parse_consumption(
        {
            "readings": [
                {"timestamp": "2026-10-24T00:00:00Z", "value": "-2", "unit": "kWh"},
                {"timestamp": "2026-10-24T01:00:00Z", "value": "N/A", "unit": "kWh"},
                {"timestamp": "not-a-date", "value": "3", "unit": "kWh"},
            ]
        }
    )
    assert QualityFlag.NEGATIVE_VALUE in points[0].quality.flags
    assert QualityFlag.MISSING in points[1].quality.flags
    assert QualityFlag.INVALID in points[2].quality.flags
    assert points[2].timestamp is None
