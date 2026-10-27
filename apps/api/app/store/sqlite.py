import asyncio
import hashlib
import json
import math
import sqlite3
import uuid
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from threading import Lock
from typing import Any

from app.domain.models import (
    ConsumptionPoint,
    HierarchyNode,
    Meter,
    Provenance,
    QualityFlag,
    QualitySummary,
    SyncRun,
)


class MigrationIntegrityError(RuntimeError):
    """Raised when an applied migration no longer matches its recorded checksum."""


EXPECTED_SCHEMA: dict[str, set[str]] = {
    "schema_migrations": {"version", "applied_at", "checksum"},
    "meters": {
        "id", "serial_number", "name", "status", "latitude", "longitude",
        "network_node_id", "last_seen_at", "source_timestamp", "quality_json",
        "provenance_json", "indexed_at", "last_seen_in_source", "deleted_at",
    },
    "readings": {
        "meter_id", "timestamp", "original_timestamp", "value", "unit",
        "original_value", "original_unit", "quality_json", "indexed_at",
        "reading_kind",
    },
    "hierarchy_nodes": {
        "record_id", "node_id", "name", "node_type", "parent_id", "meter_count",
        "consumption_total", "quality_json", "indexed_at", "consumption_unit",
        "consumption_share", "missing_reading_count", "mixed_units",
    },
    "sync_runs": {
        "id", "started_at", "finished_at", "status", "meters_seen",
        "readings_seen", "hierarchy_nodes_seen", "error", "duration_seconds",
        "records_rejected", "portal_latency_seconds", "checkpoint", "partial",
    },
    "meter_conflicts": {
        "record_id", "meter_id", "payload_json", "quality_json", "indexed_at",
    },
    "dataset_status": {
        "data_type", "status", "source", "fetched_at", "indexed_at",
        "portal_timestamp", "stale", "partial", "records_seen",
        "records_rejected", "error",
    },
    "coverage_ranges": {
        "meter_id", "start_date", "end_date", "status", "fetched_at",
    },
    "sync_checkpoints": {"name", "position", "updated_at"},
    "reading_conflicts": {
        "conflict_id", "meter_id", "timestamp", "previous_json", "incoming_json",
        "indexed_at",
    },
    "sync_snapshot_records": {
        "run_id", "data_type", "record_key", "payload_json",
    },
}


class SQLiteStore:
    """One configured connection protected by a lock; async callers use a worker thread."""

    def __init__(self, database_url: str, migrations_path: Path | None = None) -> None:
        path = database_url.removeprefix("sqlite:///")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA busy_timeout=5000")
        for name, function in {
            "radians": math.radians,
            "sin": math.sin,
            "cos": math.cos,
            "asin": math.asin,
            "sqrt": math.sqrt,
        }.items():
            self._connection.create_function(name, 1, function)
        root = Path(__file__).parents[2]
        self._migrations_path = migrations_path or root / "migrations"
        self._migrate()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    async def aclose(self) -> None:
        await asyncio.to_thread(self.close)

    def _migrate(self) -> None:
        with self._lock:
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL, checksum TEXT)"
            )
            columns = {
                row[1] for row in self._connection.execute("PRAGMA table_info(schema_migrations)").fetchall()
            }
            if "checksum" not in columns:
                self._connection.execute("ALTER TABLE schema_migrations ADD COLUMN checksum TEXT")
            self._connection.commit()

            paths = sorted(self._migrations_path.glob("*.sql"))
            checksums = {path.name: self._migration_checksum(path) for path in paths}
            applied_rows = {
                row["version"]: row["checksum"]
                for row in self._connection.execute("SELECT version, checksum FROM schema_migrations")
            }

            for version, checksum in applied_rows.items():
                if checksum is None:
                    raise MigrationIntegrityError(
                        f"Migration checksum is missing for applied migration {version}. "
                        "Delete the local database or add a new migration; "
                        "an existing migration cannot be verified safely."
                    )

            applied = {
                row["version"]: row["checksum"]
                for row in self._connection.execute("SELECT version, checksum FROM schema_migrations")
            }
            unknown_migrations = sorted(set(applied) - set(checksums))
            if unknown_migrations:
                raise MigrationIntegrityError(
                    "Applied migrations are missing from the configured migrations directory: "
                    + ", ".join(unknown_migrations)
                )
            for path in sorted(self._migrations_path.glob("*.sql")):
                checksum = checksums[path.name]
                if path.name in applied:
                    if applied[path.name] != checksum:
                        raise MigrationIntegrityError(
                            f"Migration checksum mismatch for {path.name}: the applied migration does not "
                            f"match the current file. Delete the local database or add a new migration; "
                            f"do not edit an applied migration. Expected {applied[path.name]}, found {checksum}."
                        )
                    continue
                self._connection.execute("BEGIN IMMEDIATE")
                try:
                    for statement in self._migration_statements(path.read_text(encoding="utf-8")):
                        self._connection.execute(statement)
                    self._connection.execute(
                        "INSERT INTO schema_migrations(version, applied_at, checksum) VALUES (?, ?, ?)",
                        (path.name, datetime.now(UTC).isoformat(), checksum),
                    )
                    self._connection.commit()
                except Exception:
                    self._connection.rollback()
                    raise

            self._verify_schema()

    @staticmethod
    def _migration_checksum(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _migration_statements(sql: str) -> list[str]:
        statements: list[str] = []
        buffer: list[str] = []
        for line in sql.splitlines(keepends=True):
            buffer.append(line)
            candidate = "".join(buffer)
            if sqlite3.complete_statement(candidate):
                statement = candidate.strip()
                if statement and any(
                    line.strip() and not line.lstrip().startswith("--") for line in statement.splitlines()
                ):
                    statements.append(statement)
                buffer = []
        remainder = "".join(buffer).strip()
        if remainder:
            if not sqlite3.complete_statement(f"{remainder};"):
                raise sqlite3.OperationalError("Migration ended with an incomplete SQL statement")
            statements.append(remainder)
        return statements

    def _verify_schema(self) -> None:
        missing_tables: list[str] = []
        missing_columns: list[str] = []

        for table, expected_columns in EXPECTED_SCHEMA.items():
            table_exists = self._connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if table_exists is None:
                missing_tables.append(table)
                continue

            columns = {
                row[1]
                for row in self._connection.execute(
                    f"PRAGMA table_info({table})"
                ).fetchall()
            }
            for column in sorted(expected_columns - columns):
                missing_columns.append(f"{table}.{column}")

        if missing_tables or missing_columns:
            details: list[str] = []
            if missing_tables:
                details.append(
                    f"missing tables: {', '.join(sorted(missing_tables))}"
                )
            if missing_columns:
                details.append(
                    f"missing columns: {', '.join(missing_columns)}"
                )
            raise MigrationIntegrityError(
                "SQLite schema verification failed ("
                + "; ".join(details)
                + "). Delete the local database or add a new migration."
            )

    def _execute(self, sql: str, parameters: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cursor = self._connection.execute(sql, tuple(parameters))
            self._connection.commit()
            return cursor

    def _executemany(self, sql: str, parameters: Sequence[Sequence[Any]]) -> None:
        with self._lock:
            self._connection.executemany(sql, parameters)
            self._connection.commit()

    def _upsert_meters_in_transaction(self, meters: list[Meter], seen_at: datetime) -> None:
        now = seen_at.isoformat()
        unique_meters: list[Meter] = []
        conflicts: list[tuple[str, str, str, str, str]] = []
        seen_ids: set[str] = set()
        for index, meter in enumerate(meters):
            if meter.id not in seen_ids:
                unique_meters.append(meter)
                seen_ids.add(meter.id)
            else:
                conflicts.append(
                    (
                        f"{meter.id}#duplicate#{index}", meter.id, meter.model_dump_json(),
                        meter.quality.model_dump_json(), now,
                    )
                )
        self._connection.executemany(
            """
            INSERT INTO meters (
              id, serial_number, name, status, latitude, longitude, network_node_id,
              last_seen_at, source_timestamp, quality_json, provenance_json,
              indexed_at, last_seen_in_source, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(id) DO UPDATE SET
              serial_number=excluded.serial_number, name=excluded.name, status=excluded.status,
              latitude=excluded.latitude, longitude=excluded.longitude,
              network_node_id=excluded.network_node_id, last_seen_at=excluded.last_seen_at,
              source_timestamp=excluded.source_timestamp, quality_json=excluded.quality_json,
              provenance_json=excluded.provenance_json, indexed_at=excluded.indexed_at,
              last_seen_in_source=excluded.last_seen_in_source, deleted_at=NULL
            """,
            [
                (
                    meter.id,
                    meter.serial_number,
                    meter.name,
                    meter.status,
                    meter.latitude,
                    meter.longitude,
                    meter.network_node_id,
                    meter.last_seen_at.isoformat() if meter.last_seen_at else None,
                    meter.source_timestamp.isoformat() if meter.source_timestamp else None,
                    self._quality_json(meter.quality),
                    self._provenance_json(meter.provenance),
                    now,
                    now,
                )
                for meter in unique_meters
            ],
        )
        if conflicts:
            self._connection.executemany(
                "INSERT OR REPLACE INTO meter_conflicts(record_id, meter_id, payload_json, quality_json, indexed_at) VALUES (?, ?, ?, ?, ?)",
                conflicts,
            )

    @staticmethod
    def _quality_json(quality: QualitySummary) -> str:
        return quality.model_dump_json()

    @staticmethod
    def _provenance_json(provenance: Provenance) -> str:
        return provenance.model_dump_json()

    async def upsert_meters(self, meters: Sequence[Meter], seen_at: datetime | None = None) -> None:
        await asyncio.to_thread(self._upsert_meters, list(meters), seen_at or datetime.now(UTC))

    def _upsert_meters(self, meters: list[Meter], seen_at: datetime) -> None:
        with self._lock:
            self._upsert_meters_in_transaction(meters, seen_at)
            self._connection.commit()

    async def tombstone_missing_meters(self, ids: Sequence[str], seen_at: datetime | None = None) -> None:
        await asyncio.to_thread(self._tombstone_missing_meters, list(ids), seen_at or datetime.now(UTC))

    def _tombstone_missing_meters(self, ids: list[str], seen_at: datetime) -> None:
        if not ids:
            return
        placeholders = ",".join("?" for _ in ids)
        self._execute(
            f"UPDATE meters SET deleted_at=? WHERE deleted_at IS NULL AND id NOT IN ({placeholders})",
            [seen_at.isoformat(), *ids],
        )

    async def list_meters(
        self,
        page: int,
        page_size: int,
        search: str | None = None,
        status: str | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        center: tuple[float, float, float] | None = None,
        sort: str = "id",
        descending: bool = False,
    ) -> tuple[list[Meter], int]:
        return await asyncio.to_thread(
            self._list_meters, page, page_size, search, status, bbox, center, sort, descending
        )

    def _list_meters(
        self,
        page: int,
        page_size: int,
        search: str | None,
        status: str | None,
        bbox: tuple[float, float, float, float] | None,
        center: tuple[float, float, float] | None,
        sort: str,
        descending: bool,
    ) -> tuple[list[Meter], int]:
        clauses = ["deleted_at IS NULL"]
        params: list[Any] = []
        if search:
            tokens = [token for token in search.split() if token.isalnum() or "-" in token]
            if tokens:
                clauses.append("id IN (SELECT id FROM meters_fts WHERE meters_fts MATCH ?)")
                params.append(" AND ".join(f'"{token.replace(chr(34), "")}"*' for token in tokens))
        if status:
            clauses.append("status = ?")
            params.append(status)
        if bbox:
            min_lat, min_lon, max_lat, max_lon = bbox
            clauses.append("latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?")
            params.extend([min_lat, max_lat, min_lon, max_lon])
        if center:
            lat, lon, radius = center
            lat_delta = radius / 111.0
            lon_delta = radius / (111.0 * max(0.01, abs(math.cos(math.radians(lat)))))
            clauses.append("latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?")
            params.extend([lat - lat_delta, lat + lat_delta, lon - lon_delta, lon + lon_delta])
        clause = " AND ".join(clauses)
        allowed_sort = {"id": "id", "name": "name", "status": "status", "last_seen_at": "last_seen_at"}
        order = allowed_sort.get(sort, "id")
        direction = "DESC" if descending else "ASC"
        distance_expression = (
            "6371.0 * 2.0 * asin(sqrt("
            "sin(radians((latitude - ?) / 2.0)) * sin(radians((latitude - ?) / 2.0)) + "
            "cos(radians(?)) * cos(radians(latitude)) * "
            "sin(radians((longitude - ?) / 2.0)) * sin(radians((longitude - ?) / 2.0))"
            "))"
        )
        count_params = list(params)
        if center:
            clauses.append(f"{distance_expression} <= ?")
            clause = " AND ".join(clauses)
            count_params.extend([center[0], center[0], center[0], center[1], center[1], center[2]])
        select_params: list[Any] = []
        if center:
            select_params.extend([center[0], center[0], center[0], center[1], center[1]])
            distance_select = f"{distance_expression} AS distance_km"
        else:
            distance_select = "NULL AS distance_km"
        select_params.extend(count_params)
        select_params.extend([page_size, (page - 1) * page_size])
        with self._lock:
            total = int(self._connection.execute(f"SELECT COUNT(*) FROM meters WHERE {clause}", count_params).fetchone()[0])
            rows = self._connection.execute(
                f"""
                SELECT *, {distance_select}
                FROM meters WHERE {clause}
                ORDER BY {order} {direction} LIMIT ? OFFSET ?
                """,
                select_params,
            ).fetchall()
        return [self._meter_from_row(row) for row in rows], total

    async def get_meter(self, meter_id: str) -> Meter | None:
        return await asyncio.to_thread(self._get_meter, meter_id)

    async def all_meters(self) -> list[Meter]:
        return await asyncio.to_thread(self._all_meters)

    def _all_meters(self) -> list[Meter]:
        with self._lock:
            rows = self._connection.execute("SELECT * FROM meters WHERE deleted_at IS NULL ORDER BY id").fetchall()
        return [self._meter_from_row(row) for row in rows]

    def _get_meter(self, meter_id: str) -> Meter | None:
        with self._lock:
            row = self._connection.execute("SELECT * FROM meters WHERE id=? AND deleted_at IS NULL", (meter_id,)).fetchone()
        return self._meter_from_row(row) if row else None

    async def upsert_readings(self, meter_id: str, points: Sequence[ConsumptionPoint]) -> None:
        await asyncio.to_thread(self._upsert_readings, meter_id, list(points))

    def _upsert_readings(self, meter_id: str, points: list[ConsumptionPoint]) -> None:
        with self._lock:
            self._upsert_readings_in_transaction(meter_id, points)
            self._connection.commit()

    def _upsert_readings_in_transaction(self, meter_id: str, points: list[ConsumptionPoint]) -> None:
        indexed_at = datetime.now(UTC).isoformat()
        for point in points:
            if point.timestamp is None:
                continue
            timestamp = point.timestamp.isoformat()
            existing = self._connection.execute(
                "SELECT * FROM readings WHERE meter_id=? AND timestamp=?", (meter_id, timestamp)
            ).fetchone()
            incoming = point
            if existing is not None:
                previous = {
                    "timestamp": existing["timestamp"],
                    "original_timestamp": existing["original_timestamp"],
                    "value": existing["value"],
                    "unit": existing["unit"],
                    "original_value": existing["original_value"],
                    "original_unit": existing["original_unit"],
                }
                current = {
                    "timestamp": timestamp,
                    "original_timestamp": point.original_timestamp,
                    "value": point.value,
                    "unit": point.unit,
                    "original_value": point.original_value,
                    "original_unit": point.original_unit,
                }
                if previous != current:
                    quality = QualitySummary(
                        flags=list(dict.fromkeys([*point.quality.flags, QualityFlag.CONFLICT])),
                        issue_count=point.quality.issue_count + 1,
                        notes=[*point.quality.notes, "latest value retained; previous value stored in reading_conflicts"],
                    )
                    incoming = point.model_copy(update={"quality": quality})
                    self._connection.execute(
                        "INSERT INTO reading_conflicts(conflict_id, meter_id, timestamp, previous_json, incoming_json, indexed_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (uuid.uuid4().hex, meter_id, timestamp, json.dumps(previous), incoming.model_dump_json(), indexed_at),
                    )
            self._connection.execute(
                """
                INSERT INTO readings (meter_id, timestamp, original_timestamp, value, unit, original_value,
                  original_unit, reading_kind, quality_json, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(meter_id, timestamp) DO UPDATE SET original_timestamp=excluded.original_timestamp,
                  value=excluded.value, unit=excluded.unit, original_value=excluded.original_value,
                  original_unit=excluded.original_unit, reading_kind=excluded.reading_kind,
                  quality_json=excluded.quality_json,
                  indexed_at=excluded.indexed_at
                """,
                (
                    meter_id,
                    timestamp,
                    incoming.original_timestamp,
                    incoming.value,
                    incoming.unit,
                    incoming.original_value,
                    incoming.original_unit,
                    incoming.reading_kind,
                    incoming.quality.model_dump_json(),
                    indexed_at,
                ),
            )

    async def list_readings(self, meter_id: str, start: date | None = None, end: date | None = None) -> list[ConsumptionPoint]:
        return await asyncio.to_thread(self._list_readings, meter_id, start, end)

    def _list_readings(self, meter_id: str, start: date | None, end: date | None) -> list[ConsumptionPoint]:
        clauses = ["meter_id=?"]
        params: list[Any] = [meter_id]
        if start:
            clauses.append("timestamp >= ?")
            params.append(datetime.combine(start, datetime.min.time(), UTC).isoformat())
        if end:
            clauses.append("timestamp < ?")
            params.append(datetime.combine(end, datetime.max.time(), UTC).isoformat())
        with self._lock:
            rows = self._connection.execute(
                f"SELECT * FROM readings WHERE {' AND '.join(clauses)} ORDER BY timestamp", params
            ).fetchall()
        return [
            ConsumptionPoint(
                timestamp=self._parse_datetime(row["timestamp"]),
                original_timestamp=row["original_timestamp"],
                value=row["value"],
                unit=row["unit"],
                original_value=row["original_value"],
                original_unit=row["original_unit"],
                reading_kind=row["reading_kind"],
                quality=json.loads(row["quality_json"]),
            )
            for row in rows
        ]

    async def replace_hierarchy(self, roots: Sequence[HierarchyNode]) -> None:
        await asyncio.to_thread(self._replace_hierarchy, list(roots))

    def _replace_hierarchy(self, roots: list[HierarchyNode]) -> None:
        with self._lock:
            self._replace_hierarchy_in_transaction(roots)
            self._connection.commit()

    def _replace_hierarchy_in_transaction(self, roots: list[HierarchyNode]) -> None:
        rows: list[tuple[Any, ...]] = []

        def visit(node: HierarchyNode, path: str) -> None:
            record_id = node.record_id or f"{path}/{node.id}"
            rows.append((record_id, node.id, node.name, node.node_type, node.parent_id, node.meter_count, node.consumption_total, node.consumption_unit, node.consumption_share, node.missing_reading_count, int(node.mixed_units), node.quality.model_dump_json()))
            for index, child in enumerate(node.children):
                visit(child, f"{record_id}:{index}")

        for index, root in enumerate(roots):
            visit(root, f"root:{index}")
        self._connection.execute("DELETE FROM hierarchy_nodes")
        self._connection.executemany(
            "INSERT INTO hierarchy_nodes(record_id, node_id, name, node_type, parent_id, meter_count, consumption_total, consumption_unit, consumption_share, missing_reading_count, mixed_units, quality_json, indexed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(*row, datetime.now(UTC).isoformat()) for row in rows],
        )

    async def list_hierarchy(self) -> list[HierarchyNode]:
        return await asyncio.to_thread(self._list_hierarchy)

    def _list_hierarchy(self) -> list[HierarchyNode]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT record_id, node_id, name, node_type, parent_id, meter_count, consumption_total, consumption_unit, consumption_share, missing_reading_count, mixed_units, quality_json FROM hierarchy_nodes ORDER BY record_id"
            ).fetchall()
        nodes = [
            HierarchyNode(
                record_id=row["record_id"], id=row["node_id"], name=row["name"], node_type=row["node_type"],
                parent_id=row["parent_id"], meter_count=row["meter_count"],
                consumption_total=row["consumption_total"], quality=json.loads(row["quality_json"]),
                consumption_unit=row["consumption_unit"], consumption_share=row["consumption_share"],
                missing_reading_count=row["missing_reading_count"], mixed_units=bool(row["mixed_units"]),
            )
            for row in rows
        ]
        by_id: dict[str, list[HierarchyNode]] = {}
        for node in nodes:
            by_id.setdefault(node.id, []).append(node)
        roots: list[HierarchyNode] = []
        for node in nodes:
            parent = by_id.get(node.parent_id or "", [None])[0]
            if parent is None or parent is node or node in parent.children or self._hierarchy_cycle(node, parent, by_id):
                if parent is not None and self._hierarchy_cycle(node, parent, by_id):
                    node.quality.flags = list(dict.fromkeys([*node.quality.flags, QualityFlag.CYCLE]))
                    node.quality.issue_count += 1
                    node.quality.notes.append("cycle relationship retained")
                roots.append(node)
            else:
                parent.children.append(node)
        return roots

    @staticmethod
    def _hierarchy_cycle(node: HierarchyNode, parent: HierarchyNode, by_id: dict[str, list[HierarchyNode]]) -> bool:
        visited: set[str] = set()
        current: HierarchyNode | None = parent
        while current is not None:
            if current.id == node.id or current.id in visited:
                return True
            visited.add(current.id)
            current = by_id.get(current.parent_id or "", [None])[0]
        return False

    async def overview(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._overview)

    def _overview(self) -> dict[str, Any]:
        with self._lock:
            total = int(self._connection.execute("SELECT COUNT(*) FROM meters WHERE deleted_at IS NULL").fetchone()[0])
            statuses = {
                row["status"] or "unknown": row["count"]
                for row in self._connection.execute(
                    "SELECT status, COUNT(*) AS count FROM meters WHERE deleted_at IS NULL GROUP BY status"
                ).fetchall()
            }
            trend_rows = self._connection.execute(
                "SELECT substr(timestamp, 1, 10) AS day, SUM(value) AS total FROM readings WHERE value IS NOT NULL GROUP BY day ORDER BY day DESC LIMIT 30"
            ).fetchall()
        return {
            "meter_count": total,
            "status_counts": statuses,
            "load_trend": [{"date": row["day"], "total": row["total"]} for row in reversed(trend_rows)],
        }

    async def quality_rows(self) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._quality_rows)

    def _quality_rows(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT quality_json FROM meters UNION ALL SELECT quality_json FROM readings UNION ALL SELECT quality_json FROM meter_conflicts"
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    async def latest_indexed_at(self, data_type: str) -> datetime | None:
        return await asyncio.to_thread(self._latest_indexed_at, data_type)

    def _latest_indexed_at(self, data_type: str) -> datetime | None:
        table = {"meters": "meters", "hierarchy": "hierarchy_nodes", "consumption": "readings"}.get(data_type)
        if table is None:
            return None
        with self._lock:
            row = self._connection.execute(f"SELECT MAX(indexed_at) FROM {table}").fetchone()
        return self._parse_datetime(row[0]) if row and row[0] else None

    async def all_readings(self) -> list[tuple[str, ConsumptionPoint]]:
        return await asyncio.to_thread(self._all_readings)

    def _all_readings(self) -> list[tuple[str, ConsumptionPoint]]:
        with self._lock:
            rows = self._connection.execute("SELECT * FROM readings ORDER BY meter_id, timestamp").fetchall()
        return [
            (
                row["meter_id"],
                ConsumptionPoint(
                    timestamp=self._parse_datetime(row["timestamp"]),
                    original_timestamp=row["original_timestamp"], value=row["value"], unit=row["unit"],
                    original_value=row["original_value"], original_unit=row["original_unit"],
                    reading_kind=row["reading_kind"],
                    quality=json.loads(row["quality_json"]),
                ),
            )
            for row in rows
        ]

    async def commit_snapshot(
        self,
        run_id: int,
        meters: Sequence[Meter],
        readings: Mapping[str, Sequence[ConsumptionPoint]],
        roots: Sequence[HierarchyNode],
        source: str,
        fetched_at: datetime,
        partial: bool = False,
        records_rejected: int = 0,
    ) -> None:
        await asyncio.to_thread(
            self._commit_snapshot,
            run_id,
            list(meters),
            {meter_id: list(points) for meter_id, points in readings.items()},
            list(roots),
            source,
            fetched_at,
            partial,
            records_rejected,
        )

    def _commit_snapshot(
        self,
        run_id: int,
        meters: list[Meter],
        readings: Mapping[str, Sequence[ConsumptionPoint]],
        roots: list[HierarchyNode],
        source: str,
        fetched_at: datetime,
        partial: bool,
        records_rejected: int,
    ) -> None:
        indexed_at = datetime.now(UTC)
        fetched_text = fetched_at.isoformat()
        indexed_text = indexed_at.isoformat()
        with self._lock:
            try:
                self._connection.execute("BEGIN")
                self._connection.execute("DELETE FROM sync_snapshot_records WHERE run_id=?", (run_id,))
                self._connection.executemany(
                    "INSERT INTO sync_snapshot_records(run_id, data_type, record_key, payload_json) VALUES (?, ?, ?, ?)",
                    [
                        (run_id, "meters", meter.id, meter.model_dump_json()) for meter in meters
                    ]
                    + [
                        (run_id, "readings", f"{meter_id}:{point.timestamp.isoformat()}", point.model_dump_json())
                        for meter_id, points in readings.items()
                        for point in points
                        if point.timestamp is not None
                    ]
                    + [
                        (run_id, "hierarchy", root.record_id or root.id, root.model_dump_json())
                        for root in roots
                    ],
                )
                self._upsert_meters_in_transaction(meters, indexed_at)
                self._tombstone_missing_meters_in_transaction([meter.id for meter in meters], indexed_at)
                for meter_id, points in readings.items():
                    point_list = list(points)
                    self._upsert_readings_in_transaction(meter_id, point_list)
                    dated = [point.timestamp.date() for point in point_list if point.timestamp is not None]
                    if dated:
                        self._connection.execute(
                            "INSERT OR REPLACE INTO coverage_ranges(meter_id, start_date, end_date, status, fetched_at) VALUES (?, ?, ?, 'complete', ?)",
                            (meter_id, min(dated).isoformat(), max(dated).isoformat(), fetched_text),
                        )
                self._replace_hierarchy_in_transaction(roots)
                for data_type, count in (
                    ("meters", len(meters)),
                    ("consumption", sum(len(points) for points in readings.values())),
                    ("hierarchy", self._count_hierarchy_rows(roots)),
                ):
                    status = "empty" if count == 0 else ("partial" if partial else "available")
                    self._connection.execute(
                        """
                        INSERT INTO dataset_status(data_type, status, source, fetched_at, indexed_at, stale, partial, records_seen, records_rejected, error)
                        VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, NULL)
                        ON CONFLICT(data_type) DO UPDATE SET status=excluded.status, source=excluded.source,
                          fetched_at=excluded.fetched_at, indexed_at=excluded.indexed_at, stale=0,
                          partial=excluded.partial, records_seen=excluded.records_seen,
                          records_rejected=excluded.records_rejected, error=NULL
                        """,
                        (data_type, status, source, fetched_text, indexed_text, int(partial), count, records_rejected),
                    )
                self._connection.execute(
                    "INSERT INTO sync_checkpoints(name, position, updated_at) VALUES ('full', ?, ?) ON CONFLICT(name) DO UPDATE SET position=excluded.position, updated_at=excluded.updated_at",
                    (indexed_text, indexed_text),
                )
                self._connection.execute("DELETE FROM sync_snapshot_records WHERE run_id=?", (run_id,))
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

    def _tombstone_missing_meters_in_transaction(self, ids: list[str], seen_at: datetime) -> None:
        if not ids:
            self._connection.execute(
                "UPDATE meters SET deleted_at=? WHERE deleted_at IS NULL",
                (seen_at.isoformat(),),
            )
            return
        placeholders = ",".join("?" for _ in ids)
        self._connection.execute(
            f"UPDATE meters SET deleted_at=? WHERE deleted_at IS NULL AND id NOT IN ({placeholders})",
            [seen_at.isoformat(), *ids],
        )

    @staticmethod
    def _count_hierarchy_rows(roots: Sequence[HierarchyNode]) -> int:
        return sum(1 + SQLiteStore._count_hierarchy_rows(node.children) for node in roots)

    async def mark_datasets_stale(self, error: str) -> None:
        await asyncio.to_thread(self._mark_datasets_stale, error)

    def _mark_datasets_stale(self, error: str) -> None:
        with self._lock:
            self._connection.execute(
                "UPDATE dataset_status SET stale=1, error=?, status=CASE WHEN status='empty' THEN 'empty' ELSE 'stale' END",
                (error[:500],),
            )
            self._connection.commit()

    async def dataset_status(self, data_type: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._dataset_status, data_type)

    def _dataset_status(self, data_type: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute("SELECT * FROM dataset_status WHERE data_type=?", (data_type,)).fetchone()
        return dict(row) if row else None

    async def record_dataset_status(
        self,
        data_type: str,
        source: str,
        status: str,
        fetched_at: datetime,
        records_seen: int,
        partial: bool = False,
        records_rejected: int = 0,
    ) -> None:
        await asyncio.to_thread(
            self._record_dataset_status,
            data_type,
            source,
            status,
            fetched_at,
            records_seen,
            partial,
            records_rejected,
        )

    def _record_dataset_status(
        self,
        data_type: str,
        source: str,
        status: str,
        fetched_at: datetime,
        records_seen: int,
        partial: bool,
        records_rejected: int,
    ) -> None:
        indexed_at = datetime.now(UTC)
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO dataset_status(data_type, status, source, fetched_at, indexed_at, stale, partial, records_seen, records_rejected, error)
                VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, NULL)
                ON CONFLICT(data_type) DO UPDATE SET status=excluded.status, source=excluded.source,
                  fetched_at=excluded.fetched_at, indexed_at=excluded.indexed_at, stale=0,
                  partial=excluded.partial, records_seen=excluded.records_seen,
                  records_rejected=excluded.records_rejected, error=NULL
                """,
                (data_type, status, source, fetched_at.isoformat(), indexed_at.isoformat(), int(partial), records_seen, records_rejected),
            )
            self._connection.commit()

    async def missing_ranges(self, meter_id: str, start: date, end: date) -> list[tuple[date, date]]:
        return await asyncio.to_thread(self._missing_ranges, meter_id, start, end)

    def _missing_ranges(self, meter_id: str, start: date, end: date) -> list[tuple[date, date]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT start_date, end_date FROM coverage_ranges WHERE meter_id=? AND status='complete' AND end_date >= ? AND start_date <= ? ORDER BY start_date",
                (meter_id, start.isoformat(), end.isoformat()),
            ).fetchall()
        cursor = start
        missing: list[tuple[date, date]] = []
        for row in rows:
            covered_start = max(cursor, date.fromisoformat(row["start_date"]))
            covered_end = min(end, date.fromisoformat(row["end_date"]))
            if covered_start > cursor:
                missing.append((cursor, covered_start.fromordinal(covered_start.toordinal() - 1)))
            if covered_end >= cursor:
                cursor = covered_end.fromordinal(covered_end.toordinal() + 1)
            if cursor > end:
                break
        if cursor <= end:
            missing.append((cursor, end))
        return missing

    async def mark_coverage(self, meter_id: str, start: date, end: date, status: str, fetched_at: datetime | None = None) -> None:
        await asyncio.to_thread(self._mark_coverage, meter_id, start, end, status, fetched_at or datetime.now(UTC))

    def _mark_coverage(self, meter_id: str, start: date, end: date, status: str, fetched_at: datetime) -> None:
        with self._lock:
            self._connection.execute(
                "INSERT OR REPLACE INTO coverage_ranges(meter_id, start_date, end_date, status, fetched_at) VALUES (?, ?, ?, ?, ?)",
                (meter_id, start.isoformat(), end.isoformat(), status, fetched_at.isoformat()),
            )
            self._connection.commit()

    async def set_checkpoint(self, name: str, position: str | None) -> None:
        await asyncio.to_thread(self._set_checkpoint, name, position)

    def _set_checkpoint(self, name: str, position: str | None) -> None:
        with self._lock:
            now = datetime.now(UTC).isoformat()
            self._connection.execute(
                "INSERT INTO sync_checkpoints(name, position, updated_at) VALUES (?, ?, ?) ON CONFLICT(name) DO UPDATE SET position=excluded.position, updated_at=excluded.updated_at",
                (name, position, now),
            )
            self._connection.commit()

    async def backup(self, destination: str) -> None:
        await asyncio.to_thread(self._backup, destination)

    def _backup(self, destination: str) -> None:
        target = sqlite3.connect(destination)
        try:
            with self._lock:
                self._connection.backup(target)
        finally:
            target.close()

    async def begin_sync(self) -> int:
        return await asyncio.to_thread(self._begin_sync)

    def _begin_sync(self) -> int:
        cursor = self._execute(
            "INSERT INTO sync_runs(started_at, status) VALUES (?, 'running')",
            (datetime.now(UTC).isoformat(),),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not return a sync run id")
        return int(cursor.lastrowid)

    async def finish_sync(
        self,
        run_id: int,
        status: str,
        meters: int = 0,
        readings: int = 0,
        hierarchy_nodes: int = 0,
        error: str | None = None,
        records_rejected: int = 0,
        portal_latency_seconds: float | None = None,
        checkpoint: str | None = None,
        partial: bool = False,
    ) -> None:
        await asyncio.to_thread(
            self._finish_sync,
            run_id,
            status,
            meters,
            readings,
            hierarchy_nodes,
            error,
            records_rejected,
            portal_latency_seconds,
            checkpoint,
            partial,
        )

    def _finish_sync(
        self,
        run_id: int,
        status: str,
        meters: int,
        readings: int,
        hierarchy_nodes: int,
        error: str | None,
        records_rejected: int,
        portal_latency_seconds: float | None,
        checkpoint: str | None,
        partial: bool,
    ) -> None:
        finished_at = datetime.now(UTC)
        with self._lock:
            row = self._connection.execute("SELECT started_at FROM sync_runs WHERE id=?", (run_id,)).fetchone()
            started_at = datetime.fromisoformat(row[0]) if row else finished_at
            duration = max(0.0, (finished_at - started_at).total_seconds())
            self._connection.execute(
                "UPDATE sync_runs SET finished_at=?, status=?, meters_seen=?, readings_seen=?, hierarchy_nodes_seen=?, error=?, duration_seconds=?, records_rejected=?, portal_latency_seconds=?, checkpoint=?, partial=? WHERE id=?",
                (finished_at.isoformat(), status, meters, readings, hierarchy_nodes, error, duration, records_rejected, portal_latency_seconds, checkpoint, int(partial), run_id),
            )
            self._connection.commit()

    async def latest_sync(self) -> SyncRun | None:
        return await asyncio.to_thread(self._latest_sync)

    def _latest_sync(self) -> SyncRun | None:
        with self._lock:
            row = self._connection.execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1").fetchone()
        if row is None:
            return None
        return SyncRun(
            id=row["id"], started_at=datetime.fromisoformat(row["started_at"]), finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
            status=row["status"], meters_seen=row["meters_seen"], readings_seen=row["readings_seen"], hierarchy_nodes_seen=row["hierarchy_nodes_seen"], error=row["error"],
            duration_seconds=row["duration_seconds"], records_rejected=row["records_rejected"],
            portal_latency_seconds=row["portal_latency_seconds"], checkpoint=row["checkpoint"], partial=bool(row["partial"]),
        )

    async def ping(self) -> bool:
        return await asyncio.to_thread(self._ping)

    def _ping(self) -> bool:
        with self._lock:
            self._connection.execute("SELECT 1").fetchone()
        return True

    @staticmethod
    def _meter_from_row(row: sqlite3.Row) -> Meter:
        return Meter.model_validate(
            {
                "id": row["id"], "serial_number": row["serial_number"], "name": row["name"], "status": row["status"],
                "latitude": row["latitude"], "longitude": row["longitude"], "network_node_id": row["network_node_id"],
                "last_seen_at": row["last_seen_at"], "source_timestamp": row["source_timestamp"],
                "quality": json.loads(row["quality_json"]), "provenance": json.loads(row["provenance_json"]),
            }
        )

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        parsed = datetime.fromisoformat(value)
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)

    @staticmethod
    def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        from math import asin, cos, radians, sin, sqrt

        earth_radius = 6371.0
        lat_delta = radians(lat2 - lat1)
        lon_delta = radians(lon2 - lon1)
        value = sin(lat_delta / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(lon_delta / 2) ** 2
        return earth_radius * 2 * asin(sqrt(value))
