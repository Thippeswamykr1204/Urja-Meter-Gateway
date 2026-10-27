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
from app.services.sync import SyncCoordinator
from app.store.sqlite import SQLiteStore


class CatalogService:
    def __init__(self, adapter: PortalAdapter, store: SQLiteStore, settings: Settings | None = None) -> None:
        self.adapter = adapter
        self.store = store
        self.settings = settings or Settings()
        self.sync = SyncCoordinator(adapter, store, self.settings)

    async def refresh(self) -> list[Meter]:
        return await self.sync.refresh()

    async def background_refresh(self) -> None:
        await self.sync.background_refresh()

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
            self.sync.request_background_refresh()
        return meters, PageMeta(page=page, page_size=page_size, total=total, has_next=page * page_size < total), provenance

    async def meter(self, meter_id: str) -> tuple[Meter | None, Provenance]:
        meter = await self.store.get_meter(meter_id)
        source = "index"
        if meter is None:
            meter = await self.adapter.get_meter(meter_id)
            if meter is not None:
                await self.store.upsert_meters([meter])
                source = "live" if (await self.adapter.health()).get("mode") == "live" else "demo"
        return meter, await self.provenance("meters", source=source if meter else "live")

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
        partial = False
        if start is not None and end is not None:
            missing_ranges = await self.store.missing_ranges(meter_id, start, end)
            for missing_start, missing_end in missing_ranges:
                fetched = list(await self.adapter.get_consumption(meter_id, missing_start, missing_end))
                await self.store.upsert_readings(meter_id, fetched)
                await self.store.mark_coverage(
                    meter_id,
                    missing_start,
                    missing_end,
                    "complete" if fetched else "empty",
                )
                source = "live" if (await self.adapter.health()).get("mode") == "live" else "demo"
                await self.store.record_dataset_status(
                    "consumption",
                    source,
                    "available" if fetched else "empty",
                    datetime.now(UTC),
                    len(fetched),
                    records_rejected=sum(point.timestamp is None for point in fetched),
                )
            points = await self.store.list_readings(meter_id, start, end)
            partial = bool(await self.store.missing_ranges(meter_id, start, end))
        elif not points:
            points = list(await self.adapter.get_consumption(meter_id, start, end))
            await self.store.upsert_readings(meter_id, points)
            source = "live" if (await self.adapter.health()).get("mode") == "live" else "demo"
            await self.store.record_dataset_status(
                "consumption",
                source,
                "available" if points else "empty",
                datetime.now(UTC),
                len(points),
                records_rejected=sum(point.timestamp is None for point in points),
            )
        else:
            provenance = await self.provenance("consumption", source="index")
            if provenance.stale:
                self.sync.request_background_refresh()
        aggregated = self._aggregate(points, granularity)
        values = [
            point.value
            for point in aggregated
            if point.value is not None
            and point.reading_kind in {"interval", "cumulative"}
            and QualityFlag.INVALID not in point.quality.flags
        ]
        units = {point.unit for point in aggregated if point.unit and QualityFlag.INVALID not in point.quality.flags}
        mixed_units = len(units) > 1
        if mixed_units:
            values = []
        quality = self._quality_for_points(aggregated)
        reading_kinds = {point.reading_kind for point in aggregated if point.reading_kind != "unknown"}
        summary = ConsumptionSummary(
            total=sum(values) if values else None,
            average=sum(values) / len(values) if values else None,
            minimum=min(values) if values else None,
            maximum=max(values) if values else None,
            point_count=len(aggregated),
            missing_count=sum(point.value is None for point in aggregated),
            unit=next(iter(units)) if len(units) == 1 else None,
            mixed_units=mixed_units,
            invalid_count=sum(QualityFlag.INVALID in point.quality.flags for point in aggregated),
            unknown_unit_count=sum(QualityFlag.UNKNOWN_UNIT in point.quality.flags for point in aggregated),
            counter_reset_count=sum(QualityFlag.COUNTER_RESET in point.quality.flags for point in aggregated),
            reading_kind=next(iter(reading_kinds)) if len(reading_kinds) == 1 else "unknown",
            complete=not partial,
        )
        provenance = await self.provenance("consumption", source=source)
        if partial:
            provenance = provenance.model_copy(update={"partial": True, "data_status": "partial", "stale": True})
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
                self.sync.request_background_refresh()
            return roots, provenance
        roots = list(await self.adapter.get_hierarchy())
        meters = await self.store.all_meters()
        all_readings = await self.store.all_readings()
        grouped: dict[str, list[ConsumptionPoint]] = defaultdict(list)
        for meter_id, point in all_readings:
            grouped[meter_id].append(point)
        reading_totals, reading_units, missing_readings = self.sync._reading_totals(grouped)
        roots = self.sync._aggregate_hierarchy(roots, meters, reading_totals, reading_units, missing_readings)
        await self.store.replace_hierarchy(roots)
        source = "live" if (await self.adapter.health()).get("mode") == "live" else "demo"
        await self.store.record_dataset_status(
            "hierarchy",
            source,
            "available" if roots else "empty",
            datetime.now(UTC),
            self.sync._node_count(roots),
        )
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
                    signals.append(Signal(meter_id=meter.id, kind="stale_reporter", detail="Last seen more than 24 hours ago", severity="warning", rule="last_seen_at older than 24 hours"))
            points = grouped.get(meter.id, [])
            values = [point.value for point in points if point.value is not None]
            if len(values) >= 4:
                baseline = median(values[:-1])
                if baseline and values[-1] > baseline * 2:
                    signals.append(Signal(meter_id=meter.id, kind="rolling_median_spike", timestamp=points[-1].timestamp, detail="Latest value is more than twice the prior median", severity="warning", observed_value=values[-1], baseline=baseline, rule="latest value > 2 × prior median"))
            zero_run = 0
            for point in points:
                if point.value == 0:
                    zero_run += 1
                else:
                    zero_run = 0
                if zero_run >= 3:
                    signals.append(Signal(meter_id=meter.id, kind="zero_run", timestamp=point.timestamp, detail="Three or more consecutive zero readings", severity="info", observed_value=0, rule="three or more consecutive zero readings"))
                    break
            for point in points:
                if point.value is not None and point.value < 0:
                    signals.append(Signal(meter_id=meter.id, kind="negative_value", timestamp=point.timestamp, detail="Negative reading retained from source", severity="warning", observed_value=point.value, rule="reading value < 0"))
        return signals

    async def provenance(self, data_type: str, source: str) -> Provenance:
        status = await self.store.dataset_status(data_type)
        indexed_at = self._parse_optional_datetime(status.get("indexed_at")) if status else await self.store.latest_indexed_at(data_type)
        if status is None and indexed_at is None:
            return Provenance(
                source=source,
                fetched_at=datetime.now(UTC),
                indexed_at=None,
                stale=True,
                age_seconds=None,
                data_status="unavailable",
                partial=False,
            )
        fetched_at = self._parse_optional_datetime(status.get("fetched_at")) if status else indexed_at
        fetched_at = fetched_at or datetime.now(UTC)
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=UTC)
        age = max(0.0, (datetime.now(UTC) - fetched_at).total_seconds())
        ttl = {
            "meters": self.settings.meter_metadata_ttl_seconds,
            "hierarchy": self.settings.hierarchy_ttl_seconds,
            "consumption": self.settings.recent_consumption_ttl_seconds,
        }.get(data_type, 0)
        status_name = str(status.get("status", "available")) if status else "available"
        stale = bool(status and status.get("stale")) or (ttl > 0 and age > ttl)
        return Provenance(
            source=source,
            fetched_at=fetched_at,
            indexed_at=indexed_at,
            stale=stale,
            age_seconds=age,
            data_status=status_name,
            partial=bool(status and status.get("partial")),
        )

    @staticmethod
    def _parse_optional_datetime(value: object) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        parsed = datetime.fromisoformat(value)
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)

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
        prepared = list(points)
        previous: float | None = None
        if any(point.reading_kind == "cumulative" for point in prepared):
            normalized: list[ConsumptionPoint] = []
            for point in prepared:
                if point.reading_kind != "cumulative" or point.value is None:
                    normalized.append(point)
                    continue
                if previous is None:
                    delta = None
                    quality = point.quality
                else:
                    delta = point.value - previous
                    quality = point.quality
                    if delta < 0:
                        quality = QualitySummary(
                            flags=list(dict.fromkeys([*quality.flags, QualityFlag.COUNTER_RESET])),
                            issue_count=quality.issue_count + 1,
                            notes=[*quality.notes, "cumulative counter decreased; delta omitted"],
                        )
                        delta = None
                previous = point.value
                normalized.append(point.model_copy(update={"value": delta, "quality": quality}))
            prepared = normalized
        buckets: dict[object, list[ConsumptionPoint]] = defaultdict(list)
        for point in prepared:
            buckets[key(point)].append(point)
        aggregated: list[ConsumptionPoint] = []
        for bucket, values in sorted(
            buckets.items(), key=lambda item: (item[0] is None, item[0] or datetime.min.replace(tzinfo=UTC))
        ):
            units = {point.unit for point in values if point.value is not None and QualityFlag.INVALID not in point.quality.flags and point.unit}
            kinds = {point.reading_kind for point in values if point.value is not None}
            valid = [
                point.value
                for point in values
                if point.value is not None
                and point.reading_kind in {"interval", "cumulative"}
                and QualityFlag.INVALID not in point.quality.flags
                and point.unit in units
            ]
            flags = list(dict.fromkeys(flag for point in values for flag in point.quality.flags))
            notes = [note for point in values for note in point.quality.notes][:10]
            value: float | None = sum(valid) if valid else None
            unit = next(iter(units)) if len(units) == 1 else None
            if len(units) > 1:
                value = None
                flags.append(QualityFlag.MIXED_UNIT)
                notes.append("bucket contains multiple units; total omitted")
            if len(kinds) > 1:
                value = None
                flags.append(QualityFlag.INCOMPATIBLE_READING)
                notes.append("bucket contains incompatible reading kinds; total omitted")
            if any(point.reading_kind == "unknown" for point in values) and len(values) > 1:
                value = None
                flags.append(QualityFlag.INCOMPATIBLE_READING)
                notes.append("unknown reading kind was not aggregated")
            template = values[0]
            aggregated.append(
                template.model_copy(
                    update={
                        "timestamp": bucket,
                        "value": value,
                        "unit": unit,
                        "quality": QualitySummary(
                            flags=list(dict.fromkeys(flags)),
                            issue_count=sum(point.quality.issue_count for point in values),
                            notes=notes,
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
