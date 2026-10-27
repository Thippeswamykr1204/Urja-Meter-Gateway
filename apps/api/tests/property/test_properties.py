from datetime import UTC, datetime
from typing import Any

from app.domain.hierarchy import reconstruct_hierarchy
from app.domain.models import ConsumptionPoint, HierarchyNode, Meter
from app.parsers.common import parse_number, parse_timestamp
from app.services.catalog import CatalogService
from app.services.sync import SyncCoordinator
from hypothesis import given
from hypothesis import settings as hypothesis_settings
from hypothesis import strategies as st


@hypothesis_settings(max_examples=60)
@given(st.decimals(min_value="-100000", max_value="100000", places=2, allow_nan=False, allow_infinity=False))
def test_number_parser_round_trips_plain_decimal_values(value) -> None:
    result = parse_number(format(value, "f"), locale="en_US")
    assert result.value == float(value)
    assert "invalid" not in result.flags


@hypothesis_settings(max_examples=40)
@given(st.datetimes(min_value=datetime(2000, 1, 1), max_value=datetime(2030, 12, 31)))
def test_timestamp_parser_returns_utc_for_naive_values(value: datetime) -> None:
    result = parse_timestamp(value.isoformat(), timezone_name="America/New_York")
    assert result.value is not None
    assert result.value.tzinfo == UTC
    assert "assumed_timezone" in result.flags


@given(st.lists(st.integers(min_value=0, max_value=1000), min_size=1, max_size=20))
def test_interval_aggregation_preserves_a_bucket_sum(values: list[int]) -> None:
    points = [
        ConsumptionPoint(
            timestamp=datetime(2026, 1, 1, hour=index % 24, tzinfo=UTC),
            value=value,
            unit="kWh",
            reading_kind="interval",
        )
        for index, value in enumerate(values)
    ]
    aggregated = CatalogService._aggregate(points, "day")
    assert len(aggregated) == 1
    assert aggregated[0].value == sum(values)


@given(st.integers(min_value=0, max_value=1000), st.integers(min_value=0, max_value=1000))
def test_mixed_unit_aggregation_is_unknown(value_a: int, value_b: int) -> None:
    points = [
        ConsumptionPoint(
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            value=value_a,
            unit="kWh",
            reading_kind="interval",
        ),
        ConsumptionPoint(
            timestamp=datetime(2026, 1, 1, 1, tzinfo=UTC),
            value=value_b,
            unit="Wh",
            reading_kind="interval",
        ),
    ]
    aggregated = CatalogService._aggregate(points, "day")
    assert aggregated[0].value is None
    assert "mixed_unit" in {flag.value for flag in aggregated[0].quality.flags}


@hypothesis_settings(max_examples=60)
@given(
    st.lists(
        st.fixed_dictionaries(
            {
                "id": st.integers(min_value=0, max_value=8),
                "parent_id": st.one_of(st.none(), st.integers(min_value=-1, max_value=8)),
                "name": st.text(max_size=12),
            }
        ),
        max_size=24,
    )
)
def test_hierarchy_reconstruction_stays_finite_for_arbitrary_parent_graphs(records: list[dict[str, Any]]) -> None:
    normalized = [
        {
            "id": str(record["id"]),
            "parent_id": None if record["parent_id"] is None else str(record["parent_id"]),
            "name": record["name"],
        }
        for record in records
    ]
    roots = reconstruct_hierarchy(normalized)
    stack = list(roots)
    visited: set[int] = set()
    count = 0
    while stack:
        node = stack.pop()
        identity = id(node)
        assert identity not in visited
        visited.add(identity)
        count += 1
        stack.extend(node.children)
    assert count <= len(normalized)


@hypothesis_settings(max_examples=40)
@given(st.lists(st.one_of(st.none(), st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False)), min_size=1, max_size=10))
def test_hierarchy_rollup_handles_missing_and_mixed_units(values: list[float | None]) -> None:
    meters = [
        Meter(id=f"M{index}", network_node_id="root")
        for index in range(len(values))
    ]
    readings = {
        meter.id: value
        for meter, value in zip(meters, values, strict=True)
        if value is not None
    }
    units: dict[str, str | None] = {
        meter.id: ("kWh" if index % 2 == 0 else "Wh")
        for index, meter in enumerate(meters)
    }
    missing = {
        meter.id: int(value is None)
        for meter, value in zip(meters, values, strict=True)
    }
    roots = SyncCoordinator._aggregate_hierarchy(
        [HierarchyNode(id="root", name="Root", node_type="substation")],
        meters,
        readings,
        units,
        missing,
    )
    assert roots
    assert roots[0].meter_count == len(meters)
    assert roots[0].missing_reading_count == sum(missing.values())
