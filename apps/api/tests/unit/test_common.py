from datetime import UTC

from app.parsers.common import clean_text, parse_number, parse_timestamp


def test_clean_text_collapses_whitespace() -> None:
    assert clean_text("  North\n feeder ") == "North feeder"


def test_parse_number_accepts_units_and_commas() -> None:
    assert parse_number("1,240.50 kWh") == 1240.5


def test_parse_timestamp_returns_utc_and_original() -> None:
    parsed, original = parse_timestamp("2026-10-24T10:00:00Z")
    assert original == "2026-10-24T10:00:00Z"
    assert parsed is not None and parsed.tzinfo == UTC
