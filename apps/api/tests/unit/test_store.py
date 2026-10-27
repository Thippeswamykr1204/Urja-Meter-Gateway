from datetime import datetime

import pytest
from app.adapter.demo import DemoPortalAdapter
from app.core.config import Settings
from app.domain.models import ConsumptionPoint, QualityFlag
from app.services.catalog import CatalogService
from app.store.sqlite import SQLiteStore


@pytest.mark.asyncio
async def test_sql_geo_filter_happens_before_pagination(tmp_path) -> None:
    store = SQLiteStore(f"sqlite:///{tmp_path}/geo.db")
    service = CatalogService(DemoPortalAdapter(), store, Settings())
    await service.refresh()
    meters, meta, _ = await service.meters(1, 1, None, None, 12.9716, 77.5946, 2)
    assert meta.total == 2
    assert len(meters) == 1
    assert meta.has_next
    await store.aclose()


@pytest.mark.asyncio
async def test_sql_search_and_sort_are_indexed(tmp_path) -> None:
    store = SQLiteStore(f"sqlite:///{tmp_path}/search.db")
    service = CatalogService(DemoPortalAdapter(), store, Settings())
    await service.refresh()
    meters, meta, _ = await service.meters(1, 25, "North feeder", None, sort="name")
    assert meta.total == 2
    assert [meter.status for meter in meters] == ["active", "warning"]
    await store.aclose()


@pytest.mark.asyncio
async def test_store_backup_and_dataset_status_round_trip(tmp_path) -> None:
    store = SQLiteStore(f"sqlite:///{tmp_path}/source.db")
    await store.record_dataset_status("meters", "demo", "empty", datetime(2026, 10, 25), 0)
    await store.set_checkpoint("test", "cursor-1")
    backup = tmp_path / "backup.db"
    await store.backup(str(backup))
    restored = SQLiteStore(f"sqlite:///{backup}")
    status = await restored.dataset_status("meters")
    assert status is not None and status["status"] == "empty"
    assert await restored.ping()
    await restored.aclose()
    await store.aclose()


def test_aggregation_excludes_invalid_values_and_flags_mixed_units() -> None:
    points = [
        ConsumptionPoint(timestamp=datetime(2026, 10, 24), value=2, unit="kWh"),
        ConsumptionPoint(timestamp=datetime(2026, 10, 24, 1), value=None, unit="kWh", quality={"flags": [QualityFlag.MISSING], "issue_count": 1, "notes": []}),
        ConsumptionPoint(timestamp=datetime(2026, 10, 24, 2), value=3, unit="Wh"),
    ]
    aggregated = CatalogService._aggregate(points, "day")
    assert aggregated[0].value is None
    assert QualityFlag.MIXED_UNIT in aggregated[0].quality.flags
