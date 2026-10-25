import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, tzinfo
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MISSING_TEXT = {"", "-", "—", "n/a", "na", "null", "none"}
UNIT_PATTERN = re.compile(r"(?:^|\s)([a-zA-ZµΩ]+(?:/[a-zA-Z]+)?)(?:\s|$)")
NUMBER_PATTERN = re.compile(r"[-+]?\d[\d\s.,]*")


@dataclass(slots=True)
class ParseResult:
    value: Any = None
    original: str | None = None
    flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def __iter__(self) -> Iterator[Any]:
        yield self.value
        yield self.original


@dataclass(slots=True)
class NumberResult(ParseResult):
    unit: str | None = None

    def __eq__(self, other: object) -> bool:
        if isinstance(other, (int, float)):
            return bool(self.value == other)
        if isinstance(other, NumberResult):
            return bool(self.value == other.value and self.unit == other.unit)
        return NotImplemented


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", str(value)).strip()
    return cleaned or None


def is_missing(value: Any) -> bool:
    text = clean_text(value)
    return text is None or text.casefold() in MISSING_TEXT


def _number_text(text: str, locale: str, flags: list[str], notes: list[str]) -> str | None:
    match = NUMBER_PATTERN.search(text)
    if match is None:
        return None
    candidate = match.group(0).replace(" ", "")
    if locale in {"de_DE", "fr_FR"}:
        candidate = candidate.replace(".", "").replace(",", ".")
    elif locale == "en_US":
        candidate = candidate.replace(",", "")
    elif "," in candidate and "." in candidate:
        decimal = max(candidate.rfind(","), candidate.rfind("."))
        candidate = candidate[:decimal].replace(",", "").replace(".", "") + "." + candidate[decimal + 1 :]
    elif "," in candidate:
        after = len(candidate) - candidate.rfind(",") - 1
        if after in {1, 2}:
            candidate = candidate.replace(",", ".")
        elif after == 3:
            flags.append("ambiguous_number")
            notes.append("comma may be a decimal or thousands separator")
            return None
        else:
            return None
    elif "." in candidate and len(candidate) - candidate.rfind(".") - 1 == 3:
        flags.append("ambiguous_number")
        notes.append("dot may be a decimal or thousands separator")
        return None
    return candidate


def parse_number(value: Any, locale: str = "auto") -> NumberResult:
    original = clean_text(value)
    if is_missing(value):
        return NumberResult(original=original, flags=["missing"], notes=["numeric value is empty"])
    assert original is not None
    flags: list[str] = []
    notes: list[str] = []
    normalized = _number_text(original, locale, flags, notes)
    if normalized is None:
        return NumberResult(original=original, flags=[*flags, "invalid"], notes=notes or ["numeric value is not parseable"])
    try:
        parsed = float(normalized)
    except ValueError:
        return NumberResult(original=original, flags=["invalid"], notes=["numeric value is not parseable"])
    unit_match = UNIT_PATTERN.search(original)
    unit = unit_match.group(1) if unit_match else None
    return NumberResult(value=parsed, original=original, unit=unit, flags=flags, notes=notes)


def parse_timestamp(value: Any, timezone_name: str = "UTC", date_format: str = "") -> ParseResult:
    original = clean_text(value)
    if is_missing(value):
        return ParseResult(original=original, flags=["missing"], notes=["timestamp is empty"])
    assert original is not None
    parsed: datetime | None = None
    if date_format:
        try:
            parsed = datetime.strptime(original, date_format)
        except ValueError:
            parsed = None
    if parsed is None:
        normalized = original.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            for format_string in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    parsed = datetime.strptime(original, format_string)
                    break
                except ValueError:
                    parsed = None
    if parsed is None:
        return ParseResult(original=original, flags=["invalid"], notes=["timestamp is not parseable"])
    flags: list[str] = []
    notes: list[str] = []
    if parsed.tzinfo is None:
        try:
            timezone: tzinfo = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            timezone = UTC
            notes.append("configured timezone was unavailable; UTC was used")
        parsed = parsed.replace(tzinfo=timezone)
        flags.append("assumed_timezone")
    if "/" in original and not date_format:
        flags.append("ambiguous_date_format")
        notes.append("slash date requires an explicit portal date format")
    return ParseResult(value=parsed.astimezone(UTC), original=original, flags=flags, notes=notes)


def convert_unit(value: float | None, unit: str | None, target_unit: str | None) -> tuple[float | None, str | None, bool, str | None]:
    if value is None or unit is None or target_unit is None or unit == target_unit:
        return value, unit, False, None
    factors = {("Wh", "kWh"): 0.001, ("MWh", "kWh"): 1000.0}
    factor = factors.get((unit, target_unit))
    if factor is None:
        return value, unit, False, None
    return value * factor, target_unit, True, f"converted {unit} to {target_unit}"
