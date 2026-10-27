import asyncio
import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from time import monotonic

from app.adapter.ports import PortalAdapter
from app.core.config import Settings
from app.domain.models import ConsumptionPoint, HierarchyNode, Meter, QualityFlag, QualitySummary
from app.store.sqlite import SQLiteStore

logger = logging.getLogger(__name__)


class SyncCoordinator:
    """Owns refresh single-flight, task lifetime, checkpoints, and recovery."""

    def __init__(self, adapter: PortalAdapter, store: SQLiteStore, settings: Settings) -> None:
        self.adapter = adapter
        self.store = store
        self.settings = settings
        self._sync_lock = asyncio.Lock()
        self._tasks: set[asyncio.Task[None]] = set()
        self._requested_refreshes = 0
        self._shutdown = False
        self._refresh_count = 0
        self._failure_count = 0
        self._last_duration_seconds: float | None = None

    async def refresh(self) -> list[Meter]:
        async with self._sync_lock:
            run_id = await self.store.begin_sync()
            started = monotonic()
            try:
                fetched_at = datetime.now(UTC)
                meters = list(await self.adapter.list_meters())
                readings: dict[str, list[ConsumptionPoint]] = {}
                rejected = 0
                for meter in meters:
                    points = list(await self.adapter.get_consumption(meter.id))
                    readings[meter.id] = points
                    rejected += sum(point.timestamp is None for point in points)
                roots = list(await self.adapter.get_hierarchy())
                reading_totals, reading_units, missing_readings = self._reading_totals(readings)
                roots = self._aggregate_hierarchy(roots, meters, reading_totals, reading_units, missing_readings)
                source = "live" if (await self.adapter.health()).get("mode") == "live" else "demo"
                await self.store.commit_snapshot(
                    run_id,
                    meters,
                    readings,
                    roots,
                    source,
                    fetched_at,
                    partial=False,
                    records_rejected=rejected,
                )
                health = await self.adapter.health()
                latency = health.get("portal_latency_seconds")
                await self.store.finish_sync(
                    run_id,
                    "success",
                    len(meters),
                    sum(len(points) for points in readings.values()),
                    self._node_count(roots),
                    records_rejected=rejected,
                    portal_latency_seconds=float(latency) if isinstance(latency, (int, float)) else None,
                    checkpoint=datetime.now(UTC).isoformat(),
                )
                self._refresh_count += 1
                self._last_duration_seconds = monotonic() - started
                return meters
            except Exception as error:
                self._failure_count += 1
                safe_error = type(error).__name__
                await self.store.mark_datasets_stale(safe_error)
                await self.store.finish_sync(run_id, "failed", error=safe_error)
                logger.exception("sync failed", extra={"fields": {"sync_run_id": run_id, "error": safe_error}})
                raise

    def request_background_refresh(self) -> None:
        if self._shutdown:
            return
        self._requested_refreshes += 1
        if any(not task.done() for task in self._tasks):
            return
        task = asyncio.create_task(self._run_background_refresh())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def background_refresh(self) -> None:
        self.request_background_refresh()

    async def _run_background_refresh(self) -> None:
        while self._requested_refreshes and not self._shutdown:
            requested_refreshes = self._requested_refreshes
            self._requested_refreshes = 0
            try:
                await self.refresh()
            except Exception:
                logger.warning(
                    "background sync request failed",
                    extra={"fields": {"requested_refreshes": requested_refreshes}},
                )

    async def shutdown(self) -> None:
        self._shutdown = True
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    def metrics(self) -> dict[str, object]:
        return {
            "refresh_count": self._refresh_count,
            "failure_count": self._failure_count,
            "running": self._sync_lock.locked(),
            "queued_refreshes": self._requested_refreshes,
            "last_duration_seconds": self._last_duration_seconds,
        }

    @staticmethod
    def _reading_totals(
        readings: Mapping[str, Sequence[ConsumptionPoint]],
    ) -> tuple[dict[str, float], dict[str, str | None], dict[str, int]]:
        totals: dict[str, float] = {}
        units: dict[str, str | None] = {}
        missing: dict[str, int] = {}
        for meter_id, points in readings.items():
            missing[meter_id] = sum(point.value is None for point in points)
            valid = [
                point
                for point in points
                if point.value is not None
                and point.reading_kind == "interval"
                and QualityFlag.INVALID not in point.quality.flags
            ]
            observed_units = {point.unit for point in valid if point.unit}
            if len(observed_units) != 1:
                units[meter_id] = next(iter(observed_units)) if len(observed_units) == 1 else None
                continue
            unit = next(iter(observed_units))
            units[meter_id] = unit
            totals[meter_id] = sum(point.value for point in valid if point.unit == unit and point.value is not None)
        return totals, units, missing

    @staticmethod
    def _aggregate_hierarchy(
        roots: Sequence[HierarchyNode],
        meters: Sequence[Meter],
        readings_by_meter: dict[str, float],
        units_by_meter: dict[str, str | None],
        missing_by_meter: dict[str, int],
    ) -> list[HierarchyNode]:
        assigned: set[str] = set()

        def enrich(node: HierarchyNode) -> HierarchyNode:
            children = [enrich(child) for child in node.children]
            child_meter_ids = {child.id for child in children if child.node_type == "meter"}
            direct = [
                meter
                for meter in meters
                if (meter.network_node_id == node.id or meter.id == node.id) and meter.id not in child_meter_ids
            ]
            assigned.update(meter.id for meter in direct)
            child_units = {child.consumption_unit for child in children if child.consumption_unit}
            direct_units = {units_by_meter.get(meter.id) for meter in direct if units_by_meter.get(meter.id)}
            units = child_units | direct_units
            mixed = len(units) > 1 or any(child.mixed_units for child in children)
            direct_values = [readings_by_meter[meter.id] for meter in direct if meter.id in readings_by_meter]
            direct_total = sum(direct_values) if direct_values else None
            child_totals = [child.consumption_total for child in children if child.consumption_total is not None]
            total_values = [value for value in [direct_total, *child_totals] if value is not None]
            total = sum(total_values) if total_values and not mixed else None
            missing = sum(missing_by_meter.get(meter.id, 0) for meter in direct) + sum(
                child.missing_reading_count for child in children
            )
            quality_flags = [*node.quality.flags, *( [QualityFlag.MIXED_UNIT] if mixed else [] )]
            quality_notes = [*node.quality.notes, *(["node contains multiple units"] if mixed else [])]
            return node.model_copy(
                update={
                    "children": children,
                    "meter_count": len(direct) + sum(child.meter_count for child in children),
                    "consumption_total": total,
                    "consumption_unit": next(iter(units)) if len(units) == 1 else None,
                    "mixed_units": mixed,
                    "missing_reading_count": missing,
                    "quality": QualitySummary(
                        flags=list(dict.fromkeys(quality_flags)),
                        issue_count=node.quality.issue_count + int(mixed),
                        notes=quality_notes,
                    ),
                }
            )

        enriched = [enrich(root) for root in roots]
        unassigned = [meter for meter in meters if meter.id not in assigned]
        if unassigned:
            enriched.append(
                HierarchyNode(
                    id="unassigned",
                    name="Unassigned",
                    node_type="synthetic",
                    meter_count=len(unassigned),
                    quality=QualitySummary(
                        flags=[QualityFlag.ORPHAN], issue_count=len(unassigned), notes=["meter has no observed hierarchy node"]
                    ),
                    children=[
                        HierarchyNode(
                            id=meter.id,
                            name=meter.name,
                            node_type="meter",
                            parent_id="unassigned",
                            meter_count=1,
                            consumption_total=readings_by_meter.get(meter.id),
                            consumption_unit=units_by_meter.get(meter.id),
                            missing_reading_count=missing_by_meter.get(meter.id, 0),
                        )
                        for meter in unassigned
                    ],
                )
            )
        grand_total = sum(node.consumption_total or 0 for node in enriched)

        def add_share(node: HierarchyNode) -> HierarchyNode:
            children = [add_share(child) for child in node.children]
            return node.model_copy(
                update={
                    "children": children,
                    "consumption_share": node.consumption_total / grand_total if grand_total and node.consumption_total is not None else None,
                }
            )

        return [add_share(root) for root in enriched]

    @staticmethod
    def _node_count(roots: Sequence[HierarchyNode]) -> int:
        return sum(1 + SyncCoordinator._node_count(node.children) for node in roots)
