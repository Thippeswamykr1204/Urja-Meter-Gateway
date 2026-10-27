import json
import re
from collections import Counter
from collections.abc import Mapping
from typing import Any

from bs4 import BeautifulSoup

from app.domain.models import ConsumptionPoint, Meter, QualityFlag, QualitySummary
from app.parsers.common import clean_text, convert_unit, is_missing, parse_number, parse_timestamp


def parse_payload(payload: str, content_type: str | None = None) -> Any:
    if content_type and "json" in content_type.lower():
        return json.loads(payload)
    stripped = payload.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            pass
    return BeautifulSoup(payload, "html.parser")


def payload_has_records(payload: Any) -> bool:
    if isinstance(payload, Mapping):
        return bool(payload)
    if isinstance(payload, list):
        return bool(payload)
    return bool(payload.get_text(" ", strip=True)) if isinstance(payload, BeautifulSoup) else bool(payload)


def _mapping_value(item: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in item:
            return item[key]
    return None


def _header_key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").casefold())


def _html_rows(payload: BeautifulSoup) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for table in payload.select("table"):
        table_rows = table.select("tr")
        if not table_rows:
            continue
        header_cells = table_rows[0].select("th, td")
        headers = [_header_key(cell.get_text(" ", strip=True)) for cell in header_cells]
        start = 1 if any(headers) else 0
        for html_row in table_rows[start:]:
            cells = [clean_text(cell.get_text(" ", strip=True)) for cell in html_row.select("th, td")]
            if not cells or all(value is None for value in cells):
                continue
            if headers and [_header_key(value) for value in cells] == headers:
                continue
            if headers and len(cells) == len(headers):
                rows.append(dict(zip(headers, cells, strict=False)))
            elif len(cells) >= 3:
                rows.append({"id": cells[0], "serialnumber": cells[1], "status": cells[2]})
    return rows


def _quality(flags: list[QualityFlag], notes: list[str]) -> QualitySummary:
    return QualitySummary(flags=list(dict.fromkeys(flags)), issue_count=len(flags), notes=list(dict.fromkeys(notes))[:10])


def parse_meters(
    payload: Any,
    *,
    timezone_name: str = "UTC",
    date_format: str = "",
    number_locale: str = "auto",
) -> list[Meter]:
    rows: list[Mapping[str, Any]] = []
    if isinstance(payload, Mapping):
        candidate = payload.get("meters", payload.get("data", payload.get("results", [])))
        if isinstance(candidate, list):
            rows = [row for row in candidate if isinstance(row, Mapping)]
    elif isinstance(payload, list):
        rows = [row for row in payload if isinstance(row, Mapping)]
    elif isinstance(payload, BeautifulSoup):
        rows = _html_rows(payload)
    parsed: list[Meter] = []
    for row in rows:
        meter_id = clean_text(_mapping_value(row, "id", "meter_id", "meterId", "meterid"))
        if meter_id is None or is_missing(meter_id):
            continue
        flags: list[QualityFlag] = []
        notes: list[str] = []
        last_seen_result = parse_timestamp(
            _mapping_value(row, "last_seen_at", "lastSeenAt", "last_seen", "lastseenat"), timezone_name, date_format
        )
        source_result = parse_timestamp(
            _mapping_value(row, "source_timestamp", "sourceTimestamp", "updated_at", "updatedat"), timezone_name, date_format
        )
        flags.extend(QualityFlag(value) for value in last_seen_result.flags if value in QualityFlag._value2member_map_)
        notes.extend(last_seen_result.notes)
        latitude = parse_number(_mapping_value(row, "latitude", "lat"), number_locale)
        longitude = parse_number(_mapping_value(row, "longitude", "lng", "lon"), number_locale)
        for result, label in ((latitude, "latitude"), (longitude, "longitude")):
            flags.extend(QualityFlag(value) for value in result.flags if value in QualityFlag._value2member_map_)
            notes.extend(f"{label}: {note}" for note in result.notes)
        parsed.append(
            Meter(
                id=meter_id,
                serial_number=clean_text(_mapping_value(row, "serial_number", "serialNumber", "serial", "serialnumber")),
                name=clean_text(_mapping_value(row, "name", "label")),
                status=clean_text(_mapping_value(row, "status", "state")),
                latitude=latitude.value,
                longitude=longitude.value,
                network_node_id=clean_text(_mapping_value(row, "network_node_id", "node_id", "nodeId", "nodeid")),
                last_seen_at=last_seen_result.value,
                source_timestamp=source_result.value,
                quality=_quality(flags, notes),
            )
        )
    counts = Counter(meter.id for meter in parsed)
    return [
        meter.model_copy(
            update={
                "quality": _quality(
                    [*meter.quality.flags, QualityFlag.DUPLICATE] if counts[meter.id] > 1 else meter.quality.flags,
                    [*meter.quality.notes, "duplicate meter id"] if counts[meter.id] > 1 else meter.quality.notes,
                )
            }
        )
        for meter in parsed
    ]


def parse_consumption(
    payload: Any,
    *,
    timezone_name: str = "UTC",
    date_format: str = "",
    number_locale: str = "auto",
    target_unit: str | None = None,
    reading_kind: str = "unknown",
) -> list[ConsumptionPoint]:
    rows: list[Mapping[str, Any]] = []
    if isinstance(payload, Mapping):
        candidate = payload.get("consumption", payload.get("readings", payload.get("data", payload.get("results", []))))
        if isinstance(candidate, list):
            rows = [row for row in candidate if isinstance(row, Mapping)]
    elif isinstance(payload, list):
        rows = [row for row in payload if isinstance(row, Mapping)]
    elif isinstance(payload, BeautifulSoup):
        rows = _html_rows(payload)
    points: list[ConsumptionPoint] = []
    previous_timestamp = None
    seen: set[tuple[Any, Any]] = set()
    for row in rows:
        timestamp_result = parse_timestamp(
            _mapping_value(row, "timestamp", "time", "date", "reading_at", "readingat"), timezone_name, date_format
        )
        number_result = parse_number(_mapping_value(row, "value", "consumption", "reading"), number_locale)
        explicit_unit = clean_text(_mapping_value(row, "unit", "units"))
        observed_unit = explicit_unit or number_result.unit
        converted_value, normalized_unit, converted, conversion_note = convert_unit(number_result.value, observed_unit, target_unit)
        flags: list[QualityFlag] = []
        notes = [*timestamp_result.notes, *number_result.notes]
        if timestamp_result.flags:
            flags.extend(QualityFlag(value) for value in timestamp_result.flags if value in QualityFlag._value2member_map_)
        if number_result.flags:
            flags.extend(QualityFlag(value) for value in number_result.flags if value in QualityFlag._value2member_map_)
        if observed_unit is None:
            flags.append(QualityFlag.UNKNOWN_UNIT)
            notes.append("unit is unknown or missing")
        elif observed_unit not in {"Wh", "kWh", "MWh", "W", "kW", "MW"}:
            flags.append(QualityFlag.UNKNOWN_UNIT)
            notes.append("unit is not in the documented unit set")
        if converted:
            flags.append(QualityFlag.UNIT_CONVERTED)
            notes.append(conversion_note or "unit converted")
        if observed_unit and target_unit and normalized_unit == observed_unit and observed_unit != target_unit:
            flags.append(QualityFlag.UNKNOWN_UNIT)
            notes.append("unit conversion is not documented")
        if converted_value is not None and converted_value < 0:
            flags.append(QualityFlag.NEGATIVE_VALUE)
            notes.append("negative reading")
        timestamp = timestamp_result.value
        if timestamp is not None and previous_timestamp is not None and timestamp < previous_timestamp:
            flags.append(QualityFlag.OUT_OF_ORDER)
            notes.append("reading is out of order")
        if timestamp is not None:
            previous_timestamp = timestamp
        duplicate_key = (timestamp, converted_value)
        if duplicate_key in seen:
            flags.append(QualityFlag.DUPLICATE)
            notes.append("duplicate reading")
        seen.add(duplicate_key)
        points.append(
            ConsumptionPoint(
                timestamp=timestamp,
                original_timestamp=timestamp_result.original,
                value=converted_value,
                unit=normalized_unit,
                original_value=number_result.value,
                original_unit=observed_unit,
                reading_kind=reading_kind,
                quality=_quality(flags, notes),
            )
        )
    return points
