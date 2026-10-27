from datetime import UTC, date, datetime, timedelta

from app.adapter.ports import PortalAdapter
from app.domain.models import ConsumptionPoint, HierarchyNode, Meter, Provenance


class DemoPortalAdapter(PortalAdapter):
    """Fixture-backed adapter used when live portal evidence is not configured."""

    def __init__(self) -> None:
        now = datetime.now(UTC)
        provenance = Provenance(source="demo", fetched_at=now, stale=False)
        self.meters = [
            Meter(
                id="MTR-1001",
                serial_number="URJA-1001",
                name="North feeder / A-01",
                status="active",
                latitude=12.9716,
                longitude=77.5946,
                network_node_id="substation-north",
                last_seen_at=now - timedelta(minutes=8),
                provenance=provenance,
            ),
            Meter(
                id="MTR-1002",
                serial_number="URJA-1002",
                name="North feeder / A-02",
                status="warning",
                latitude=12.9750,
                longitude=77.6010,
                network_node_id="substation-north",
                last_seen_at=now - timedelta(hours=3),
                provenance=provenance,
            ),
            Meter(
                id="MTR-2001",
                serial_number="URJA-2001",
                name="South feeder / B-01",
                status="offline",
                latitude=12.9352,
                longitude=77.6245,
                network_node_id="substation-south",
                last_seen_at=now - timedelta(days=2),
                provenance=provenance,
            ),
        ]
        self.provenance = provenance

    async def list_meters(self) -> list[Meter]:
        return self.meters

    async def get_meter(self, meter_id: str) -> Meter | None:
        return next((meter for meter in self.meters if meter.id == meter_id), None)

    async def get_consumption(
        self, meter_id: str, start: date | None = None, end: date | None = None
    ) -> list[ConsumptionPoint]:
        if not any(meter.id == meter_id for meter in self.meters):
            return []
        now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        points = [
            ConsumptionPoint(
                timestamp=now - timedelta(days=offset),
                value=round(18 + ((offset * 7) % 11) + (2.5 if offset == 4 else 0), 2),
                unit="kWh",
                reading_kind="interval",
            )
            for offset in range(13, -1, -1)
        ]
        return [
            point
            for point in points
            if (start is None or (point.timestamp is not None and point.timestamp.date() >= start))
            and (end is None or (point.timestamp is not None and point.timestamp.date() <= end))
        ]

    async def get_hierarchy(self) -> list[HierarchyNode]:
        return [
            HierarchyNode(
                id="grid",
                name="Distribution grid",
                node_type="root",
                meter_count=3,
                children=[
                    HierarchyNode(
                        id="substation-north",
                        name="North substation",
                        node_type="substation",
                        parent_id="grid",
                        meter_count=2,
                        children=[HierarchyNode(id="MTR-1001", name="North feeder / A-01", node_type="meter", parent_id="substation-north", meter_count=1), HierarchyNode(id="MTR-1002", name="North feeder / A-02", node_type="meter", parent_id="substation-north", meter_count=1)],
                    ),
                    HierarchyNode(
                        id="substation-south",
                        name="South substation",
                        node_type="substation",
                        parent_id="grid",
                        meter_count=1,
                        children=[HierarchyNode(id="MTR-2001", name="South feeder / B-01", node_type="meter", parent_id="substation-south", meter_count=1)],
                    ),
                ],
            )
        ]

    async def health(self) -> dict[str, object]:
        return {"mode": "demo", "configured": True, "authenticated": True, "session_age_seconds": 0}
