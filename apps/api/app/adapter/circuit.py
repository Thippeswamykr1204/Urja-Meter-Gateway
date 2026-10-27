from dataclasses import dataclass
from time import monotonic

from app.adapter.errors import PortalCircuitOpenError


@dataclass(slots=True)
class CircuitBreaker:
    failure_threshold: int
    reset_seconds: float
    failures: int = 0
    opened_at: float | None = None

    def before_call(self) -> None:
        if self.opened_at is None:
            return
        if monotonic() - self.opened_at >= self.reset_seconds:
            self.opened_at = None
            self.failures = 0
            return
        raise PortalCircuitOpenError("Portal circuit breaker is open")

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.opened_at = monotonic()

    @property
    def state(self) -> str:
        if self.opened_at is None:
            return "closed"
        if monotonic() - self.opened_at >= self.reset_seconds:
            return "half_open"
        return "open"
