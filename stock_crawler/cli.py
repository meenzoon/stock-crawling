"""수집기 CLI 진입점. ``fetch``, ``tickers``, ``schedule`` 명령을 노출한다."""

import logging
import sys

import typer

from .config import CrawlConfig, Market
from .pipeline.collector import collect
from .pipeline.scheduler import schedule_daily, schedule_interval
from .sources.tickers import resolve_tickers

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="KOSPI / NASDAQ TOP-N 일봉 OHLCV 크롤러 (무료 데이터 소스).",
)


def _setup_logging(verbose: bool) -> None:
    """루트 로거를 stdout 핸들러와 함께 초기화한다.

    Args:
        verbose: ``True`` 이면 ``DEBUG`` 레벨, 그 외에는 ``INFO`` 레벨로 설정.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )


@app.command()
def fetch(
    market: Market = typer.Option(Market.kospi, help="대상 시장 (kospi 또는 nasdaq)."),
    top: int = typer.Option(200, min=1, max=2000, help="시가총액 상위 몇 종목까지 받을지."),
    refresh_tickers: bool = typer.Option(
        False, "--refresh-tickers", help="TOP-N 티커 목록을 캐시 무시하고 다시 받는다."
    ),
    request_delay: float = typer.Option(
        0.3, "--request-delay", min=0.0, help="yfinance 호출 사이 최소 대기 시간(초)."
    ),
    max_per_minute: int = typer.Option(
        30,
        "--max-per-minute",
        min=0,
        help="60초 슬라이딩 윈도우 내 yfinance 호출 상한 (0이면 비활성).",
    ),
    exclude_etf: bool = typer.Option(
        False, "--exclude-etf", help="TOP-N 산정에서 ETF 종목을 제외한다."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="DEBUG 로그를 활성화한다."),
) -> None:
    """TOP-N 종목의 OHLCV 이력을 수집한다(첫 실행 후엔 증분 수집)."""
    _setup_logging(verbose)
    cfg = CrawlConfig(
        market=market,
        top_n=top,
        request_delay=request_delay,
        max_per_minute=max_per_minute,
        exclude_etf=exclude_etf,
    )
    summary = collect(cfg, refresh_tickers=refresh_tickers)
    typer.echo(
        f"\n[{market.value.upper()}] succeeded={summary['succeeded']} "
        f"failed={summary['failed']} new_rows={summary['new_rows']}"
    )
    if summary["failed"]:
        typer.echo("First few failures:")
        for t, err in summary["failures"][:10]:
            typer.echo(f"  - {t}: {err}")


@app.command("tickers")
def list_tickers(
    market: Market = typer.Option(Market.kospi, help="대상 시장."),
    top: int = typer.Option(200, min=1, max=2000, help="가져올 상위 종목 수."),
    refresh: bool = typer.Option(False, "--refresh", help="캐시를 무시하고 다시 받는다."),
    exclude_etf: bool = typer.Option(
        False, "--exclude-etf", help="TOP-N 산정에서 ETF 종목을 제외한다."
    ),
) -> None:
    """TOP-N 티커 목록을 해석해 표준 출력으로 보여준다(디스크에 캐시됨)."""
    _setup_logging(False)
    cfg = CrawlConfig(market=market, top_n=top, exclude_etf=exclude_etf)
    df = resolve_tickers(cfg, refresh=refresh)
    typer.echo(df.to_string(index=False))


@app.command()
def schedule(
    market: Market = typer.Option(Market.kospi, help="대상 시장."),
    top: int = typer.Option(200, min=1, max=2000, help="가져올 상위 종목 수."),
    at: str = typer.Option(
        "18:00",
        help="매일 실행할 로컬 시각(HH:MM). --interval-hours 가 주어지면 무시된다.",
    ),
    interval_hours: float | None = typer.Option(
        None,
        help="값이 있으면 --at 대신 매 N시간 간격으로 실행한다.",
    ),
    timezone: str = typer.Option("Asia/Seoul", help="cron 일별 실행에 사용할 IANA 타임존."),
    run_now: bool = typer.Option(
        False, "--run-now", help="스케줄 등록 전에 즉시 한 번 수집을 실행한다."
    ),
    request_delay: float = typer.Option(
        0.3, "--request-delay", min=0.0, help="yfinance 호출 사이 최소 대기 시간(초)."
    ),
    max_per_minute: int = typer.Option(
        30,
        "--max-per-minute",
        min=0,
        help="60초 슬라이딩 윈도우 내 yfinance 호출 상한 (0이면 비활성).",
    ),
    exclude_etf: bool = typer.Option(
        False, "--exclude-etf", help="TOP-N 산정에서 ETF 종목을 제외한다."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="DEBUG 로그를 활성화한다."),
) -> None:
    """포그라운드 블로킹 프로세스로 수집을 반복 실행한다."""
    _setup_logging(verbose)
    cfg = CrawlConfig(
        market=market,
        top_n=top,
        request_delay=request_delay,
        max_per_minute=max_per_minute,
        exclude_etf=exclude_etf,
    )

    if interval_hours is not None:
        schedule_interval(cfg, hours=interval_hours, run_now=run_now)
        return

    try:
        hh, mm = at.split(":")
        hour, minute = int(hh), int(mm)
    except ValueError as e:
        typer.echo(f"--at must be HH:MM (got {at!r}): {e}")
        raise typer.Exit(2) from None

    schedule_daily(cfg, hour=hour, minute=minute, timezone=timezone, run_now=run_now)


if __name__ == "__main__":
    app()
