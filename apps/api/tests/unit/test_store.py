import pytest
from app.adapter.demo import DemoPortalAdapter
from app.core.config import Settings
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
