"""APScheduler 기반의 일별/간격 수집 스케줄러.

전부 ``BlockingScheduler`` 를 사용해 포그라운드에서 블로킹 실행한다.
백그라운드 데몬화는 이 저장소 밖의 실행 환경(systemd, launchd 등)이 담당한다.
"""

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .collector import collect
from .config import CrawlConfig

log = logging.getLogger(__name__)


def _run(cfg: CrawlConfig) -> None:
    """예외를 잡아서 로깅만 하고 계속 스케줄을 돌릴 수 있도록 감싼 ``collect`` 호출."""
    try:
        collect(cfg)
    except Exception:
        log.exception("Scheduled run failed for %s", cfg.market.value)


def schedule_daily(
    cfg: CrawlConfig,
    hour: int,
    minute: int,
    timezone: str = "Asia/Seoul",
    run_now: bool = False,
) -> None:
    """매일 지정한 시각에 수집을 실행하는 cron 스케줄러를 시작한다.

    Args:
        cfg: 수집 설정.
        hour: 실행 시각의 시(0~23).
        minute: 실행 시각의 분(0~59).
        timezone: cron 트리거가 사용할 IANA 타임존 (예: ``"Asia/Seoul"``).
        run_now: ``True`` 이면 스케줄을 등록하기 전에 한 번 즉시 실행한다.
    """
    if run_now:
        _run(cfg)
    sched = BlockingScheduler(timezone=timezone)
    sched.add_job(
        _run,
        trigger=CronTrigger(hour=hour, minute=minute),
        args=[cfg],
        id=f"daily-{cfg.market.value}",
        replace_existing=True,
    )
    log.info(
        "Scheduled daily %s collection at %02d:%02d %s",
        cfg.market.value,
        hour,
        minute,
        timezone,
    )
    sched.start()


def schedule_interval(cfg: CrawlConfig, hours: float, run_now: bool = False) -> None:
    """일정 시간 간격으로 수집을 반복 실행하는 interval 스케줄러를 시작한다.

    Args:
        cfg: 수집 설정.
        hours: 실행 간격(시간 단위, 소수점 허용 — 예: ``0.5`` 는 30분).
        run_now: ``True`` 이면 스케줄 등록 전에 한 번 즉시 실행한다.
    """
    if run_now:
        _run(cfg)
    sched = BlockingScheduler()
    sched.add_job(
        _run,
        trigger=IntervalTrigger(hours=hours),
        args=[cfg],
        id=f"interval-{cfg.market.value}",
        replace_existing=True,
    )
    log.info("Scheduled %s collection every %.2f hours", cfg.market.value, hours)
    sched.start()
