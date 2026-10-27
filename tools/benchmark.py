from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parents[1] / "apps" / "api"))

from app.domain.models import ConsumptionPoint, HierarchyNode, Meter  # noqa: E402
from app.services.catalog import CatalogService  # noqa: E402
from app.services.sync import SyncCoordinator  # noqa: E402
from app.store.sqlite import SQLiteStore  # noqa: E402


def elapsed(started: float) -> float:
    return round(time.perf_counter() - started, 4)


async def benchmark_size(size: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"flock-benchmark-{size}-") as temporary:
        store = SQLiteStore(f"sqlite:///{Path(temporary) / 'benchmark.db'}")
        indexed_at = datetime.now(UTC).isoformat()
        meters = [
            Meter(
                id=f"MTR-{index:06d}",
                serial_number=f"SER-{index:06d}",
                name=f"Synthetic meter {index:06d}",
                status="active" if index % 10 else "warning",
                latitude=12.90 + (index % 1000) / 10000,
                longitude=77.50 + (index % 1000) / 10000,
                network_node_id="root",
            )
            for index in range(size)
        ]

        started = time.perf_counter()
        await store.upsert_meters(meters)
        insert_meters_seconds = elapsed(started)

        points = [
            ConsumptionPoint(
                timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=index % 24),
                value=float((index % 50) + 1),
                unit="kWh",
                reading_kind="interval",
            )
            for index in range(size)
        ]
        with store._lock:
            store._connection.executemany(
                """
                INSERT INTO readings(
                    meter_id,
                    timestamp,
                    original_timestamp,
                    value,
                    unit,
                    original_value,
                    original_unit,
                    reading_kind,
                    quality_json,
                    indexed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        meter.id,
                        point.timestamp.isoformat(),
                        point.original_timestamp,
                        point.value,
                        point.unit,
                        point.original_value,
                        point.original_unit,
                        point.reading_kind,
                        point.quality.model_dump_json(),
                        indexed_at,
                    )
                    for meter, point in zip(meters, points, strict=True)
                ],
            )
            store._connection.commit()
        insert_readings_seconds = elapsed(started) - insert_meters_seconds

        started = time.perf_counter()
        listed, total = await store.list_meters(1, 50, sort="name")
        list_seconds = elapsed(started)

        started = time.perf_counter()
        searched, search_total = await store.list_meters(1, 50, search="MTR-00")
        search_seconds = elapsed(started)

        started = time.perf_counter()
        nearby, radius_total = await store.list_meters(
            1,
            50,
            center=(12.95, 77.55, 10),
        )
        radius_seconds = elapsed(started)

        started = time.perf_counter()
        all_readings = await store.all_readings()
        aggregated = CatalogService._aggregate(
            [point for _, point in all_readings],
            "day",
        )
        aggregation_seconds = elapsed(started)

        totals = {meter.id: point.value or 0 for meter, point in zip(meters, points, strict=True)}
        units = {meter.id: point.unit for meter, point in zip(meters, points, strict=True)}
        missing = {meter.id: 0 for meter in meters}
        started = time.perf_counter()
        hierarchy = SyncCoordinator._aggregate_hierarchy(
            [HierarchyNode(id="root", name="Synthetic root", node_type="substation")],
            meters,
            totals,
            units,
            missing,
        )
        hierarchy_seconds = elapsed(started)

        await store.aclose()
        return {
            "meters": size,
            "readings": size,
            "insert_meters_seconds": insert_meters_seconds,
            "insert_readings_seconds": round(insert_readings_seconds, 4),
            "list_seconds": list_seconds,
            "list_rows": len(listed),
            "list_total": total,
            "search_seconds": search_seconds,
            "search_rows": len(searched),
            "search_total": search_total,
            "radius_seconds": radius_seconds,
            "radius_rows": len(nearby),
            "radius_total": radius_total,
            "aggregation_seconds": aggregation_seconds,
            "aggregation_buckets": len(aggregated),
            "hierarchy_seconds": hierarchy_seconds,
            "hierarchy_roots": len(hierarchy),
        }


def write_report(results: list[dict[str, Any]]) -> None:
    lines = [
        "# SQLite benchmark",
        "",
        "The benchmark creates a temporary SQLite database for each dataset size. Each synthetic meter has one interval reading, a coordinate, and a shared synthetic hierarchy root.",
        "",
        "## Measured results",
        "",
        "| Size | Insert meters | Insert readings | List | Search | Radius | Aggregation | Hierarchy rollup |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        lines.append(
            f"| {result['meters']:,} | {result['insert_meters_seconds']:.4f}s | {result['insert_readings_seconds']:.4f}s | {result['list_seconds']:.4f}s | {result['search_seconds']:.4f}s | {result['radius_seconds']:.4f}s | {result['aggregation_seconds']:.4f}s | {result['hierarchy_seconds']:.4f}s |"
        )
    lines.extend(
        [
            "",
            "## Data-scale note",
            "",
            "SQLite remains attractive for a local catalog because indexed list, search, radius, aggregation, and hierarchy operations are measurable in one process without infrastructure. The first strain points are serialized writes, FTS maintenance, in-process aggregation, and keeping a large reading set in Python for rollups.",
            "",
            "At a larger production scale, the concrete migration path is Postgres for transactional storage, PostGIS for spatial filtering, incremental portal cursors instead of full refreshes, durable background work for checkpoints, and a shared rate limiter. Those components are documented rather than built here.",
            "",
            "## Raw result data",
            "",
            "```json",
            json.dumps(results, indent=2),
            "```",
        ]
    )
    (Path(__file__).parents[1] / "docs" / "benchmark.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


async def main() -> None:
    results = [await benchmark_size(size) for size in (10_000, 100_000)]
    write_report(results)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
