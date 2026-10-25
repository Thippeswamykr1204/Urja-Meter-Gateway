from collections.abc import Sequence
from datetime import date
from typing import Protocol

from app.domain.models import ConsumptionPoint, HierarchyNode, Meter


class PortalAdapter(Protocol):
    async def list_meters(self) -> Sequence[Meter]: ...

    async def get_meter(self, meter_id: str) -> Meter | None: ...

    async def get_consumption(
        self, meter_id: str, start: date | None = None, end: date | None = None
    ) -> Sequence[ConsumptionPoint]: ...

    async def get_hierarchy(self) -> Sequence[HierarchyNode]: ...

    async def health(self) -> dict[str, object]: ...
