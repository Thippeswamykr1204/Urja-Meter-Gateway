from collections import OrderedDict, deque
from time import monotonic


class InMemoryRateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60, max_keys: int = 10_000) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._events: OrderedDict[str, deque[float]] = OrderedDict()

    def allow(self, key: str) -> bool:
        now = monotonic()
        events = self._events.pop(key, deque())
        self._events[key] = events
        while len(self._events) > self.max_keys:
            self._events.popitem(last=False)
        while events and events[0] <= now - self.window_seconds:
            events.popleft()
        if len(events) >= self.limit:
            return False
        events.append(now)
        return True
