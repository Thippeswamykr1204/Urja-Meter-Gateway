import asyncio
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from statistics import median

from app.adapter.errors import PortalNotFoundError
from app.adapter.ports import PortalAdapter
from app.core.config import Settings
from app.domain.models import (
    ConsumptionPoint,
    ConsumptionResponse,
    ConsumptionSummary,
    DataQualityReport,
    HierarchyNode,
    Meter,
    PageMeta,
    Provenance,
    QualityFlag,
    QualitySummary,
    Signal,
)
from app.domain.quality import quality_report
from app.store.sqlite import SQLiteStore


class CatalogService:
    def __init__(self, adapter: PortalAdapter, store: SQLiteStore, settings: Settings | None = None) -> None:
        self.adapter = adapter
        self.store = store
        self.settings = settings or Settings()
        self._sync_lock = asyncio.Lock()

    async def refresh(self) -> list[Meter]:
        async with self._sync_lock:
            run_id = await self.store.begin_sync()
            try:
                meters = list(await self.adapter.list_meters())
                await self.store.upsert_meters(meters)
                await self.store.tombstone_missing_meters([meter.id for meter in meters])
                reading_count = 0
                reading_totals: dict[str, float] = defaultdict(float)
                for meter in meters:
                    points = list(await self.adapter.get_consumption(meter.id))
                    await self.store.upsert_readings(meter.id, points)
                    reading_count += len(points)
                    reading_totals[meter.id] = sum(point.value or 0 for point in points)
                roots = list(await self.adapter.get_hierarchy())
                roots = self._aggregate_hierarchy(roots, meters, reading_totals)
                await self.store.replace_hierarchy(roots)
                await self.store.finish_sync(run_id, "success", len(meters), reading_count, self._node_count(roots))
                return meters
            except Exception as error:
                await self.store.finish_sync(run_id, "failed", error=str(error))
                raise

    async def background_refresh(self) -> None:
        if self._sync_lock.locked():
            return
        try:
            await self.refresh()
        except Exception:
            return

    async def meters(
        self,
        page: int,
        page_size: int,
        search: str | None,
        status: str | None,
        lat: float | None = None,
        lon: float | None = None,
        radius_km: float | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        sort: str = "id",
        descending: bool = False,
    ) -> tuple[list[Meter], PageMeta, Provenance]:
        center = (lat, lon, radius_km) if lat is not None and lon is not None and radius_km is not None else None
        meters, total = await self.store.list_meters(page, page_size, search, status, bbox, center, sort, descending)
        provenance = await self.provenance("meters", source="index")
        if provenance.stale:
            asyncio.create_task(self.background_refresh())
        return meters, PageMeta(page=page, page_size=page_size, total=total, has_next=page * page_size < total), provenance

    async def meter(self, meter_id: str) -> tuple[Meter | None, Provenance]:
        meter = await self.store.get_meter(meter_id)
        if meter is None:
            meter = await self.adapter.get_meter(meter_id)
            if meter is not None:
                await self.store.upsert_meters([meter])
        return meter, await self.provenance("meters", source="index" if meter else "live")

    async def consumption(
        self,
        meter_id: str,
        start: date | None,
        end: date | None,
        granularity: str,
    ) -> ConsumptionResponse:
        meter = await self.store.get_meter(meter_id)
        if meter is None:
            meter = await self.adapter.get_meter(meter_id)
            if meter is None:
                raise PortalNotFoundError(f"Meter {meter_id} was not found")
            await self.store.upsert_meters([meter])
        points = await self.store.list_readings(meter_id, start, end)
        source = "index"
        if not points:
            points = list(await self.adapter.get_consumption(meter_id, start, end))
            await self.store.upsert_readings(meter_id, points)
            source = "live" if (await self.adapter.health()).get("mode") == "live" else "demo"
        else:
            provenance = await self.provenance("consumption", source="index")
            if provenance.stale:
                asyncio.create_task(self.background_refresh())
        aggregated = self._aggregate(points, granularity)
        values = [point.value for point in aggregated if point.value is not None]
        units = {point.unit for point in aggregated if point.unit}
        quality = self._quality_for_points(aggregated)
        summary = ConsumptionSummary(
            total=sum(values) if values else None,
            average=sum(values) / len(values) if values else None,
            minimum=min(values) if values else None,
            maximum=max(values) if values else None,
            point_count=len(aggregated),
            missing_count=sum(point.value is None for point in aggregated),
            unit=next(iter(units)) if len(units) == 1 else None,
        )
        provenance = await self.provenance("consumption", source=source)
        return ConsumptionResponse(
            meter_id=meter_id,
            granularity=granularity,
            points=aggregated,
            summary=summary,
            provenance=provenance,
            quality=quality,
        )

    async def hierarchy(self) -> tuple[Sequence[HierarchyNode], Provenance]:
        roots = await self.store.list_hierarchy()
        provenance = await self.provenance("hierarchy", source="index")
        if roots:
            if provenance.stale:
                asyncio.create_task(self.background_refresh())
            return roots, provenance
        roots = list(await self.adapter.get_hierarchy())
        meters = await self.store.all_meters()
        all_readings = await self.store.all_readings()
        reading_totals: dict[str, float] = defaultdict(float)
        for meter_id, point in all_readings:
            reading_totals[meter_id] += point.value or 0
        roots = self._aggregate_hierarchy(roots, meters, reading_totals)
        await self.store.replace_hierarchy(roots)
        source = "live" if (await self.adapter.health()).get("mode") == "live" else "demo"
        return roots, await self.provenance("hierarchy", source=source)

    async def overview(self) -> dict[str, object]:
        data = await self.store.overview()
        signals = await self.signals()
        return {**data, "signal_count": len(signals), "provenance": (await self.provenance("meters", source="index")).model_dump(mode="json")}

    async def quality(self) -> DataQualityReport:
        raw = [QualitySummary.model_validate(item) for item in await self.store.quality_rows()]
        issue_count, by_flag, recent_issues = quality_report(raw, len(raw))
        examples: dict[str, list[str]] = defaultdict(list)
        for quality in raw:
            for flag in quality.flags:
                if len(examples[flag.value]) < 3:
                    examples[flag.value].extend(quality.notes[:1])
        return DataQualityReport(
            total_records=len(raw), issue_count=issue_count, by_flag=by_flag,
            recent_issues=recent_issues, examples=dict(examples),
        )

    async def signals(self) -> list[Signal]:
        meters = await self.store.all_meters()
        grouped: dict[str, list[ConsumptionPoint]] = defaultdict(list)
        for meter_id, point in await self.store.all_readings():
            grouped[meter_id].append(point)
        signals: list[Signal] = []
        now = datetime.now(UTC)
        for meter in meters:
            if meter.last_seen_at and now - meter.last_seen_at > timedelta(hours=24):
                signals.append(Signal(meter_id=meter.id, kind="stale_reporter", detail="Last seen more than 24 hours ago", severity="warning"))
            points = grouped.get(meter.id, [])
            values = [point.value for point in points if point.value is not None]
            if len(values) >= 4:
                baseline = median(values[:-1])
                if baseline and values[-1] > baseline * 2:
                    signals.append(Signal(meter_id=meter.id, kind="rolling_median_spike", timestamp=points[-1].timestamp, detail="Latest value is more than twice the prior median", severity="warning"))
            zero_run = 0
            for point in points:
                if point.value == 0:
                    zero_run += 1
                else:
                    zero_run = 0
                if zero_run >= 3:
                    signals.append(Signal(meter_id=meter.id, kind="zero_run", timestamp=point.timestamp, detail="Three or more consecutive zero readings", severity="info"))
                    break
            for point in points:
                if point.value is not None and point.value < 0:
                    signals.append(Signal(meter_id=meter.id, kind="negative_value", timestamp=point.timestamp, detail="Negative reading retained from source", severity="warning"))
        return signals

    async def provenance(self, data_type: str, source: str) -> Provenance:
        indexed_at = await self.store.latest_indexed_at(data_type)
        fetched_at = indexed_at or datetime.now(UTC)
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=UTC)
        age = max(0.0, (datetime.now(UTC) - fetched_at).total_seconds())
        ttl = {
            "meters": self.settings.meter_metadata_ttl_seconds,
            "hierarchy": self.settings.hierarchy_ttl_seconds,
            "consumption": self.settings.recent_consumption_ttl_seconds,
        }.get(data_type, 0)
        return Provenance(source=source, fetched_at=fetched_at, stale=ttl > 0 and age > ttl, age_seconds=age)

    @staticmethod
    def _aggregate(points: Sequence[ConsumptionPoint], granularity: str) -> list[ConsumptionPoint]:
        def key(point: ConsumptionPoint) -> datetime | None:
            if point.timestamp is None:
                return None
            if granularity == "hour":
                return point.timestamp.replace(minute=0, second=0, microsecond=0)
            if granularity == "month":
                return point.timestamp.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            return point.timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
        buckets: dict[object, list[ConsumptionPoint]] = defaultdict(list)
        for point in points:
            buckets[key(point)].append(point)
        aggregated: list[ConsumptionPoint] = []
        for bucket, values in sorted(
            buckets.items(), key=lambda item: (item[0] is None, item[0] or datetime.min.replace(tzinfo=UTC))
        ):
            valid = [point.value for point in values if point.value is not None]
            template = values[0]
            aggregated.append(
                template.model_copy(
                    update={
                        "timestamp": bucket,
                        "value": sum(valid) if valid else None,
                        "quality": QualitySummary(
                            flags=list(dict.fromkeys(flag for point in values for flag in point.quality.flags)),
                            issue_count=sum(point.quality.issue_count for point in values),
                            notes=[note for point in values for note in point.quality.notes][:10],
                        ),
                    }
                )
            )
        return aggregated

    @staticmethod
    def _quality_for_points(points: Sequence[ConsumptionPoint]) -> QualitySummary:
        return QualitySummary(
            flags=list(dict.fromkeys(flag for point in points for flag in point.quality.flags)),
            issue_count=sum(point.quality.issue_count for point in points),
            notes=[note for point in points for note in point.quality.notes][:20],
        )

    @staticmethod
    def _node_count(roots: Sequence[HierarchyNode]) -> int:
        return sum(1 + CatalogService._node_count(node.children) for node in roots)

    @staticmethod
    def _aggregate_hierarchy(roots: Sequence[HierarchyNode], meters: Sequence[Meter], readings_by_meter: dict[str, float]) -> list[HierarchyNode]:
        nodes_by_id: dict[str, list[HierarchyNode]] = defaultdict(list)

        def index(node: HierarchyNode) -> None:
            nodes_by_id[node.id].append(node)
            for child in node.children:
                index(child)

        for root in roots:
            index(root)
        assigned: set[str] = set()
        enriched: list[HierarchyNode] = []

        def enrich(node: HierarchyNode) -> HierarchyNode:
            children = [enrich(child) for child in node.children]
            child_meter_ids = {child.id for child in children if child.node_type == "meter"}
            direct = [
                meter
                for meter in meters
                if (meter.network_node_id == node.id or meter.id == node.id)
                and meter.id not in child_meter_ids
            ]
            assigned.update(meter.id for meter in direct)
            direct_total = sum(readings_by_meter[meter.id] for meter in direct)
            child_count = sum(child.meter_count for child in children)
            child_total = sum(child.consumption_total or 0 for child in children)
            return node.model_copy(update={"children": children, "meter_count": len(direct) + child_count, "consumption_total": direct_total + child_total if direct or children else None})

        enriched.extend(enrich(root) for root in roots)
        unassigned = [meter for meter in meters if meter.id not in assigned]
        if unassigned:
            enriched.append(HierarchyNode(id="unassigned", name="Unassigned", node_type="synthetic", meter_count=len(unassigned), quality=QualitySummary(flags=[QualityFlag.ORPHAN], issue_count=len(unassigned), notes=["meter has no observed hierarchy node"]), children=[HierarchyNode(id=meter.id, name=meter.name, node_type="meter", parent_id="unassigned", meter_count=1) for meter in unassigned]))
        return enriched
