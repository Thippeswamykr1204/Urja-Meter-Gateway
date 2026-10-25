import asyncio
import json
import math
import sqlite3
from collections.abc import Iterable, Sequence
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
                "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            applied = {row[0] for row in self._connection.execute("SELECT version FROM schema_migrations")}
            for path in sorted(self._migrations_path.glob("*.sql")):
                if path.name in applied:
                    continue
                self._connection.executescript(path.read_text())
                self._connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (path.name, datetime.now(UTC).isoformat()),
                )
            self._connection.commit()

    def _execute(self, sql: str, parameters: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cursor = self._connection.execute(sql, tuple(parameters))
            self._connection.commit()
            return cursor

    def _executemany(self, sql: str, parameters: Sequence[Sequence[Any]]) -> None:
        with self._lock:
            self._connection.executemany(sql, parameters)
            self._connection.commit()

    @staticmethod
    def _quality_json(quality: QualitySummary) -> str:
        return quality.model_dump_json()

    @staticmethod
    def _provenance_json(provenance: Provenance) -> str:
        return provenance.model_dump_json()

    async def upsert_meters(self, meters: Sequence[Meter], seen_at: datetime | None = None) -> None:
        await asyncio.to_thread(self._upsert_meters, list(meters), seen_at or datetime.now(UTC))

    def _upsert_meters(self, meters: list[Meter], seen_at: datetime) -> None:
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
        self._executemany(
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
            self._executemany(
                "INSERT OR REPLACE INTO meter_conflicts(record_id, meter_id, payload_json, quality_json, indexed_at) VALUES (?, ?, ?, ?, ?)",
                conflicts,
            )

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
        self._executemany(
            """
            INSERT INTO readings (meter_id, timestamp, original_timestamp, value, unit, original_value,
              original_unit, quality_json, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(meter_id, timestamp) DO UPDATE SET original_timestamp=excluded.original_timestamp,
              value=excluded.value, unit=excluded.unit, original_value=excluded.original_value,
              original_unit=excluded.original_unit, quality_json=excluded.quality_json,
              indexed_at=excluded.indexed_at
            """,
            [
                (
                    meter_id,
                    point.timestamp.isoformat() if point.timestamp else None,
                    point.original_timestamp,
                    point.value,
                    point.unit,
                    point.original_value,
                    point.original_unit,
                    point.quality.model_dump_json(),
                    datetime.now(UTC).isoformat(),
                )
                for point in points
                if point.timestamp is not None
            ],
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
                quality=json.loads(row["quality_json"]),
            )
            for row in rows
        ]

    async def replace_hierarchy(self, roots: Sequence[HierarchyNode]) -> None:
        await asyncio.to_thread(self._replace_hierarchy, list(roots))

    def _replace_hierarchy(self, roots: list[HierarchyNode]) -> None:
        rows: list[tuple[Any, ...]] = []

        def visit(node: HierarchyNode, path: str) -> None:
            record_id = node.record_id or f"{path}/{node.id}"
            rows.append((record_id, node.id, node.name, node.node_type, node.parent_id, node.meter_count, node.consumption_total, node.quality.model_dump_json()))
            for index, child in enumerate(node.children):
                visit(child, f"{record_id}:{index}")

        for index, root in enumerate(roots):
            visit(root, f"root:{index}")
        with self._lock:
            self._connection.execute("DELETE FROM hierarchy_nodes")
            self._connection.executemany(
                "INSERT INTO hierarchy_nodes(record_id, node_id, name, node_type, parent_id, meter_count, consumption_total, quality_json, indexed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(*row, datetime.now(UTC).isoformat()) for row in rows],
            )
            self._connection.commit()

    async def list_hierarchy(self) -> list[HierarchyNode]:
        return await asyncio.to_thread(self._list_hierarchy)

    def _list_hierarchy(self) -> list[HierarchyNode]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT record_id, node_id, name, node_type, parent_id, meter_count, consumption_total, quality_json FROM hierarchy_nodes ORDER BY record_id"
            ).fetchall()
        nodes = [
            HierarchyNode(
                record_id=row["record_id"], id=row["node_id"], name=row["name"], node_type=row["node_type"],
                parent_id=row["parent_id"], meter_count=row["meter_count"],
                consumption_total=row["consumption_total"], quality=json.loads(row["quality_json"]),
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
                    quality=json.loads(row["quality_json"]),
                ),
            )
            for row in rows
        ]

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

    async def finish_sync(self, run_id: int, status: str, meters: int = 0, readings: int = 0, hierarchy_nodes: int = 0, error: str | None = None) -> None:
        await asyncio.to_thread(self._finish_sync, run_id, status, meters, readings, hierarchy_nodes, error)

    def _finish_sync(self, run_id: int, status: str, meters: int, readings: int, hierarchy_nodes: int, error: str | None) -> None:
        self._execute(
            "UPDATE sync_runs SET finished_at=?, status=?, meters_seen=?, readings_seen=?, hierarchy_nodes_seen=?, error=? WHERE id=?",
            (datetime.now(UTC).isoformat(), status, meters, readings, hierarchy_nodes, error, run_id),
        )

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
