"""stock_crawler.throttle.Throttler 의 인자 검증과 대기 동작 단위 테스트.

``time`` 과 ``random`` 을 가짜 객체로 교체해 sleep 호출 여부와 대기 시간을
결정적으로 검증한다.
"""

import pytest

from stock_crawler.pipeline import throttle


class FakeClock:
    """``monotonic()`` 이 항상 ``t`` 를 돌려주는 가짜 시계."""

    def __init__(self, t=1000.0):
        self.t = t

    def monotonic(self):
        return self.t


class SleepRecorder:
    """``sleep`` 호출 인자를 모아두는 가짜 sleep."""

    def __init__(self):
        self.calls = []

    def __call__(self, secs):
        self.calls.append(secs)


@pytest.fixture
def patched(monkeypatch):
    """throttle 모듈의 time/random 을 가짜로 교체하고 (clock, sleeps) 를 돌려준다."""
    clock = FakeClock(1000.0)
    sleeps = SleepRecorder()
    monkeypatch.setattr(throttle.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(throttle.time, "sleep", sleeps)
    monkeypatch.setattr(throttle.random, "uniform", lambda _a, _b: 0.0)
    return clock, sleeps


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_interval": -1.0},
        {"max_per_minute": -1},
        {"jitter": -0.1},
    ],
)
def test_negative_args_raise(kwargs):
    with pytest.raises(ValueError, match=">="):
        throttle.Throttler(**kwargs)


def test_zero_args_allowed():
    throttle.Throttler(min_interval=0.0, max_per_minute=0, jitter=0.0)


def test_first_wait_does_not_sleep(patched):
    _clock, sleeps = patched
    t = throttle.Throttler(min_interval=0.3, max_per_minute=30, jitter=0.0)
    t.wait()
    assert sleeps.calls == []


def test_wait_enforces_min_interval(patched):
    clock, sleeps = patched
    t = throttle.Throttler(min_interval=0.3, max_per_minute=0, jitter=0.0)
    t.wait()
    clock.t = 1000.1  # 직전 호출에서 0.1초 경과
    t.wait()
    assert sleeps.calls == [pytest.approx(0.2)]


def test_wait_skips_sleep_when_interval_satisfied(patched):
    clock, sleeps = patched
    t = throttle.Throttler(min_interval=0.3, max_per_minute=0, jitter=0.0)
    t.wait()
    clock.t = 1000.5  # 0.5초 경과, min_interval 충족
    t.wait()
    assert sleeps.calls == []


def test_wait_enforces_per_minute_cap(patched):
    _clock, sleeps = patched
    t = throttle.Throttler(min_interval=0.0, max_per_minute=2, jitter=0.0)
    t.wait()
    t.wait()
    assert sleeps.calls == []
    t.wait()  # 3번째 호출 → 60초 윈도우 한도 초과
    assert sleeps.calls == [pytest.approx(60.0)]


def test_wait_adds_jitter(monkeypatch):
    clock = FakeClock(1000.0)
    sleeps = SleepRecorder()
    captured = []

    def fake_uniform(low, high):
        captured.append((low, high))
        return high  # 최대 지터

    monkeypatch.setattr(throttle.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(throttle.time, "sleep", sleeps)
    monkeypatch.setattr(throttle.random, "uniform", fake_uniform)

    t = throttle.Throttler(min_interval=0.5, max_per_minute=0, jitter=0.2)
    t.wait()
    clock.t = 1000.1  # gap 0.1 → 기본 대기 0.4초
    t.wait()
    assert captured == [(0, pytest.approx(0.08))]  # jitter 범위 = 0.2 * 0.4
    assert sleeps.calls == [pytest.approx(0.48)]  # 0.4 + 0.08
