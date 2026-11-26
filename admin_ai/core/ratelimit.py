"""Small thread-safe sliding-window limiter (per process; best effort on serverless)."""
import threading
import time
from collections import deque
from typing import Callable, Dict


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: float, clock: Callable[[], float] = time.monotonic,
                 max_keys: int = 2000) -> None:
        self.limit, self.window, self._clock, self._max_keys = limit, window_seconds, clock, max_keys
        self._hits: Dict[str, deque] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            if len(self._hits) > self._max_keys:
                self._hits.clear()
            q = self._hits.setdefault(key, deque())
            while q and q[0] <= now - self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True
