import logging
import random  # nosec B311  # used only for non-security jitter
import time
from collections import deque
from threading import Lock

log = logging.getLogger(__name__)


class Throttler:
    """Enforce a minimum interval between calls and a max-calls-per-minute cap.

    A small random jitter is added on top of any wait so concurrent callers
    do not align perfectly. Thread-safe via an internal lock.
    """

    def __init__(
        self,
        min_interval: float = 0.3,
        max_per_minute: int = 30,
        jitter: float = 0.1,
    ) -> None:
        if min_interval < 0:
            raise ValueError("min_interval must be >= 0")
        if max_per_minute < 0:
            raise ValueError("max_per_minute must be >= 0 (0 disables the window cap)")
        if jitter < 0:
            raise ValueError("jitter must be >= 0")
        self.min_interval = min_interval
        self.max_per_minute = max_per_minute
        self.jitter = jitter
        self._last_call: float = 0.0
        self._calls: deque[float] = deque()
        self._lock = Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait_for = 0.0

            if self._last_call:
                gap = now - self._last_call
                if gap < self.min_interval:
                    wait_for = self.min_interval - gap

            if self.max_per_minute > 0:
                window_start = now - 60.0
                while self._calls and self._calls[0] < window_start:
                    self._calls.popleft()
                if len(self._calls) >= self.max_per_minute:
                    wait_for = max(wait_for, self._calls[0] + 60.0 - now)

            if wait_for > 0 and self.jitter > 0:
                wait_for += random.uniform(0, self.jitter * wait_for)  # nosec B311

            if wait_for > 0:
                log.debug("Throttler sleeping %.3fs", wait_for)
                time.sleep(wait_for)

            t = time.monotonic()
            self._last_call = t
            self._calls.append(t)
