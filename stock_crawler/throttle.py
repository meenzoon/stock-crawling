"""외부 API 호출 속도를 제한하는 ``Throttler`` 구현.

호출 간 최소 간격과 1분 슬라이딩 윈도우 호출 횟수 상한을 함께 강제한다.
여러 호출자가 같은 시점에 정렬되지 않도록 작은 랜덤 지터를 더한다.
"""

import logging
import random  # nosec B311  # 보안 목적이 아닌 단순 지터 생성용
import time
from collections import deque
from threading import Lock

log = logging.getLogger(__name__)


class Throttler:
    """호출 사이 최소 간격과 분당 최대 호출 수를 강제하는 thread-safe throttle.

    대기 시간이 발생할 때마다 ``jitter`` 비율만큼의 랜덤 지터를 더해 동시
    호출자들이 완벽히 동기화되어 외부 API 를 동시에 두드리는 상황을 피한다.
    내부적으로 ``Lock`` 을 사용해 멀티스레드 환경에서도 안전하다.
    """

    def __init__(
        self,
        min_interval: float = 0.3,
        max_per_minute: int = 30,
        jitter: float = 0.1,
    ) -> None:
        """Throttler 인스턴스를 초기화한다.

        Args:
            min_interval: 직전 호출과 다음 호출 사이의 최소 간격(초). ``0`` 이면 비활성.
            max_per_minute: 60초 슬라이딩 윈도우 내 허용되는 최대 호출 횟수.
                ``0`` 이면 윈도우 캡을 비활성화한다.
            jitter: 계산된 대기 시간에 더해질 지터의 최대 비율 (0~1 권장).
                예: ``0.1`` 이면 대기 시간의 최대 10% 가 추가된다.

        Raises:
            ValueError: 음수 인자가 들어온 경우.
        """
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
        """호출 직전에 호출하여 최소 간격과 분당 제한을 만족할 때까지 블로킹한다."""
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
