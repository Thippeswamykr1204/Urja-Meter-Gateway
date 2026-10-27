from datetime import UTC, datetime

import pytest
from app.adapter.demo import DemoPortalAdapter
from app.domain.models import ConsumptionPoint, QualityFlag
from app.services.catalog import CatalogService
from app.store.sqlite import SQLiteStore


@pytest.mark.asyncio
async def test_catalog_reads_consumption_hierarchy_quality_and_signals(tmp_path) -> None:
    store = SQLiteStore(f"sqlite:///{tmp_path}/catalog.db")
    service = CatalogService(DemoPortalAdapter(), store)
    await service.refresh()
    response = await service.consumption("MTR-1001", None, None, "day")
    roots, hierarchy_provenance = await service.hierarchy()
    report = await service.quality()
    signals = await service.signals()
    overview = await service.overview()
    meter, provenance = await service.meter("MTR-1001")
    assert response.summary.total is not None
    assert response.summary.unit == "kWh"
    assert roots and roots[0].meter_count == 3
    assert hierarchy_provenance.source == "index"
    assert report.total_records > 0
    assert any(signal.kind == "stale_reporter" for signal in signals)
    assert overview["meter_count"] == 3
    assert meter is not None and provenance.source == "index"
    await store.aclose()


def test_aggregate_handles_cumulative_resets_and_unknown_kinds() -> None:
    points = [
        ConsumptionPoint(timestamp=datetime(2026, 10, 24, tzinfo=UTC), value=10, unit="kWh", reading_kind="cumulative"),
        ConsumptionPoint(timestamp=datetime(2026, 10, 24, 1, tzinfo=UTC), value=14, unit="kWh", reading_kind="cumulative"),
        ConsumptionPoint(timestamp=datetime(2026, 10, 24, 2, tzinfo=UTC), value=4, unit="kWh", reading_kind="cumulative"),
    ]
    aggregated = CatalogService._aggregate(points, "hour")
    assert aggregated[1].value == 4
    assert aggregated[2].value is None
    assert QualityFlag.COUNTER_RESET in aggregated[2].quality.flags
