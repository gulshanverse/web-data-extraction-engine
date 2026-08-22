from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field


@dataclass
class SlidingWindowRateLimiter:
    """Small process-local limiter for the API process; production multi-instance limits remain infrastructure-owned."""

    limit: int
    window_seconds: float
    _hits: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        window = self._hits[key]
        threshold = now - self.window_seconds
        while window and window[0] <= threshold:
            window.popleft()
        if len(window) >= self.limit:
            return False
        window.append(now)
        return True
