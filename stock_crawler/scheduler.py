import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .collector import collect
from .config import CrawlConfig

log = logging.getLogger(__name__)


def _run(cfg: CrawlConfig) -> None:
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
