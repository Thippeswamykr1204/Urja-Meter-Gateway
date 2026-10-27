from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class QualityFlag(StrEnum):
    CLEAN = "clean"
    MISSING = "missing"
    INVALID = "invalid"
    DUPLICATE = "duplicate"
    ORPHAN = "orphan"
    CYCLE = "cycle"
    UNVERIFIED = "unverified"
    OUT_OF_ORDER = "out_of_order"
    NEGATIVE_VALUE = "negative_value"
    UNIT_CONVERTED = "unit_converted"
    ASSUMED_TIMEZONE = "assumed_timezone"
    UNKNOWN_UNIT = "unknown_unit"
    SCHEMA_DRIFT = "schema_drift"
    AMBIGUOUS_NUMBER = "ambiguous_number"
    AMBIGUOUS_DATE_FORMAT = "ambiguous_date_format"
    MIXED_UNIT = "mixed_unit"
    CONFLICT = "conflict"
    COUNTER_RESET = "counter_reset"
    PARTIAL = "partial"
    INCOMPATIBLE_READING = "incompatible_reading"


class Provenance(BaseModel):
    source: str = "index"
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    stale: bool = False
    portal_timestamp: datetime | None = None
    age_seconds: float | None = None
    indexed_at: datetime | None = None
    data_status: str = "available"
    partial: bool = False


class QualitySummary(BaseModel):
    flags: list[QualityFlag] = Field(default_factory=list)
    issue_count: int = 0
    notes: list[str] = Field(default_factory=list)


class Meter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    serial_number: str | None = None
    name: str | None = None
    status: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    network_node_id: str | None = None
    last_seen_at: datetime | None = None
    source_timestamp: datetime | None = None
    quality: QualitySummary = Field(default_factory=QualitySummary)
    provenance: Provenance = Field(default_factory=Provenance)


class ConsumptionPoint(BaseModel):
    timestamp: datetime | None = None
    original_timestamp: str | None = None
    value: float | None = None
    unit: str | None = None
    original_value: float | None = None
    original_unit: str | None = None
    reading_kind: str = "unknown"
    quality: QualitySummary = Field(default_factory=QualitySummary)


class ConsumptionSummary(BaseModel):
    total: float | None = None
    average: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    point_count: int = 0
    missing_count: int = 0
    unit: str | None = None
    mixed_units: bool = False
    invalid_count: int = 0
    unknown_unit_count: int = 0
    counter_reset_count: int = 0
    reading_kind: str = "unknown"
    complete: bool = True


class ConsumptionResponse(BaseModel):
    meter_id: str
    granularity: str
    points: list[ConsumptionPoint]
    summary: ConsumptionSummary
    provenance: Provenance
    quality: QualitySummary = Field(default_factory=QualitySummary)


class HierarchyNode(BaseModel):
    id: str
    record_id: str | None = None
    name: str | None = None
    node_type: str = "unknown"
    parent_id: str | None = None
    meter_count: int = 0
    consumption_total: float | None = None
    consumption_unit: str | None = None
    consumption_share: float | None = None
    missing_reading_count: int = 0
    mixed_units: bool = False
    quality: QualitySummary = Field(default_factory=QualitySummary)
    children: list["HierarchyNode"] = Field(default_factory=list)


class DataQualityReport(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    total_records: int
    issue_count: int
    by_flag: dict[str, int]
    recent_issues: list[str]
    examples: dict[str, list[str]] = Field(default_factory=dict)


class SyncRun(BaseModel):
    id: int
    started_at: datetime
    finished_at: datetime | None = None
    status: str
    meters_seen: int = 0
    readings_seen: int = 0
    hierarchy_nodes_seen: int = 0
    error: str | None = None
    duration_seconds: float | None = None
    records_rejected: int = 0
    portal_latency_seconds: float | None = None
    checkpoint: str | None = None
    partial: bool = False


class Signal(BaseModel):
    meter_id: str
    kind: str
    timestamp: datetime | None = None
    detail: str
    severity: str = "info"
    observed_value: float | None = None
    baseline: float | None = None
    rule: str | None = None
    sufficient_history: bool = True


class PageMeta(BaseModel):
    page: int
    page_size: int
    total: int
    has_next: bool


T = TypeVar("T")


class ApiEnvelope(BaseModel, Generic[T]):
    data: T
    provenance: Provenance
    meta: dict[str, Any] = Field(default_factory=dict)
