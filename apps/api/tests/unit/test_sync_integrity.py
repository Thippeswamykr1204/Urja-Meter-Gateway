import hashlib
import logging
import shutil
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from app.adapter.demo import DemoPortalAdapter
from app.domain.models import ConsumptionPoint, QualityFlag
from app.services.catalog import CatalogService
from app.store.sqlite import MigrationIntegrityError, SQLiteStore


class FailingAdapter(DemoPortalAdapter):
    async def get_consumption(self, meter_id, start=None, end=None):
        raise RuntimeError("upstream test failure")


@pytest.mark.asyncio
async def test_background_refresh_logs_requests_before_reset(tmp_path, caplog) -> None:
    store = SQLiteStore(f"sqlite:///{tmp_path}/background.db")
    service = CatalogService(FailingAdapter(), store)
    service.sync._requested_refreshes = 3

    with caplog.at_level(logging.WARNING):
        await service.sync._run_background_refresh()

    record = next(
        record
        for record in caplog.records
        if record.message == "background sync request failed"
    )
    assert record.fields["requested_refreshes"] == 3
    await store.aclose()


@pytest.mark.asyncio
async def test_failed_sync_keeps_last_successful_snapshot_and_marks_it_stale(tmp_path) -> None:
    database = f"sqlite:///{tmp_path}/integrity.db"
    store = SQLiteStore(database)
    service = CatalogService(DemoPortalAdapter(), store)
    await service.refresh()
    before = await store.get_meter("MTR-1001")
    failing = CatalogService(FailingAdapter(), store)

    with pytest.raises(RuntimeError):
        await failing.refresh()

    after = await store.get_meter("MTR-1001")
    assert before is not None and after is not None
    assert after.name == before.name
    status = await store.dataset_status("meters")
    assert status is not None and status["stale"] == 1
    latest = await store.latest_sync()
    assert latest is not None and latest.status == "failed"
    await store.aclose()


@pytest.mark.asyncio
async def test_empty_index_is_reported_unavailable(tmp_path) -> None:
    store = SQLiteStore(f"sqlite:///{tmp_path}/empty.db")
    service = CatalogService(DemoPortalAdapter(), store)
    provenance = await service.provenance("meters", source="index")
    assert provenance.stale is True
    assert provenance.data_status == "unavailable"
    await store.aclose()


@pytest.mark.asyncio
async def test_reading_conflict_keeps_latest_value_and_flags_it(tmp_path) -> None:
    store = SQLiteStore(f"sqlite:///{tmp_path}/conflict.db")
    await store.upsert_meters([next(iter(DemoPortalAdapter().meters))])
    timestamp = datetime(2026, 10, 24, tzinfo=UTC)
    await store.upsert_readings("MTR-1001", [ConsumptionPoint(timestamp=timestamp, value=1, unit="kWh")])
    await store.upsert_readings("MTR-1001", [ConsumptionPoint(timestamp=timestamp, value=2, unit="kWh")])
    point = (await store.list_readings("MTR-1001"))[0]
    assert point.value == 2
    assert QualityFlag.CONFLICT in point.quality.flags
    await store.aclose()


@pytest.mark.asyncio
async def test_coverage_ranges_return_only_missing_ranges(tmp_path) -> None:
    store = SQLiteStore(f"sqlite:///{tmp_path}/coverage.db")
    await store.upsert_meters([next(iter(DemoPortalAdapter().meters))])
    await store.mark_coverage("MTR-1001", date(2026, 10, 2), date(2026, 10, 4), "complete")
    assert await store.missing_ranges("MTR-1001", date(2026, 10, 1), date(2026, 10, 6)) == [
        (date(2026, 10, 1), date(2026, 10, 1)),
        (date(2026, 10, 5), date(2026, 10, 6)),
    ]
    await store.aclose()


def test_legacy_database_without_checksums_fails_fast(tmp_path) -> None:
    path = tmp_path / "previous.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    root = Path(__file__).parents[2] / "migrations"
    for name in ("001_initial.sql", "002_meter_conflicts.sql"):
        connection.executescript((root / name).read_text())
        connection.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)", (name, "2026-10-25T00:00:00+00:00"))
    connection.commit()
    connection.close()

    with pytest.raises(MigrationIntegrityError, match="checksum is missing"):
        SQLiteStore(f"sqlite:///{path}")


def test_fresh_database_records_migration_checksums(tmp_path) -> None:
    root = Path(__file__).parents[2] / "migrations"
    store = SQLiteStore(f"sqlite:///{tmp_path}/fresh.db")

    rows = store._connection.execute(
        "SELECT version, checksum FROM schema_migrations ORDER BY version"
    ).fetchall()

    assert rows
    assert all(row[1] for row in rows)
    assert {
        row[0]: row[1]
        for row in rows
    } == {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.glob("*.sql"))
    }
    store.close()


def test_edited_applied_migration_fails_fast(tmp_path) -> None:
    migrations = tmp_path / "migrations"
    source = Path(__file__).parents[2] / "migrations"
    shutil.copytree(source, migrations)
    database = f"sqlite:///{tmp_path}/edited.db"
    store = SQLiteStore(database, migrations)
    store.close()

    path = migrations / "001_initial.sql"
    path.write_text(path.read_text(encoding="utf-8") + "\n-- changed after application\n", encoding="utf-8")

    with pytest.raises(MigrationIntegrityError, match="checksum mismatch.*001_initial.sql"):
        SQLiteStore(database, migrations)


def test_failed_migration_rolls_back_its_schema_changes(tmp_path) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "001_good.sql").write_text(
        "CREATE TABLE good (id INTEGER PRIMARY KEY);\n",
        encoding="utf-8",
    )
    (migrations / "002_bad.sql").write_text(
        "CREATE TABLE partial (id INTEGER PRIMARY KEY);\nTHIS IS NOT SQL;\n",
        encoding="utf-8",
    )
    database = tmp_path / "atomic.db"

    with pytest.raises(sqlite3.OperationalError):
        SQLiteStore(f"sqlite:///{database}", migrations)

    connection = sqlite3.connect(database)
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    applied = {
        row[0]
        for row in connection.execute("SELECT version FROM schema_migrations").fetchall()
    }
    connection.close()

    assert "good" in tables
    assert "partial" not in tables
    assert applied == {"001_good.sql"}


def test_missing_expected_schema_column_fails_after_migrations(tmp_path) -> None:
    database = tmp_path / "missing-column.db"
    store = SQLiteStore(f"sqlite:///{database}")
    store._connection.execute("DROP TABLE sync_snapshot_records")
    store._connection.commit()
    store.close()

    with pytest.raises(MigrationIntegrityError, match="sync_snapshot_records"):
        SQLiteStore(f"sqlite:///{database}")
