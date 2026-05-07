from __future__ import annotations

import logging
import sys

import typer

from .collector import collect
from .config import CrawlConfig, Market
from .scheduler import schedule_daily, schedule_interval
from .tickers import resolve_tickers

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="KOSPI / NASDAQ TOP-N daily OHLCV crawler (free sources).",
)


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )


@app.command()
def fetch(
    market: Market = typer.Option(Market.kospi, help="Target market."),
    top: int = typer.Option(200, min=1, max=2000, help="Top-N by market cap."),
    refresh_tickers: bool = typer.Option(
        False, "--refresh-tickers", help="Re-resolve the top-N ticker list."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Crawl historical OHLCV for the top-N tickers (incremental after first run)."""
    _setup_logging(verbose)
    cfg = CrawlConfig(market=market, top_n=top)
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
    market: Market = typer.Option(Market.kospi),
    top: int = typer.Option(200, min=1, max=2000),
    refresh: bool = typer.Option(False, "--refresh"),
) -> None:
    """Resolve and print the top-N ticker list (cached on disk)."""
    _setup_logging(False)
    cfg = CrawlConfig(market=market, top_n=top)
    df = resolve_tickers(cfg, refresh=refresh)
    typer.echo(df.to_string(index=False))


@app.command()
def schedule(
    market: Market = typer.Option(Market.kospi),
    top: int = typer.Option(200, min=1, max=2000),
    at: str = typer.Option(
        "18:00", help="HH:MM local time for the daily run (ignored if --interval-hours)."
    ),
    interval_hours: float | None = typer.Option(
        None, help="If set, run every N hours instead of daily at --at."
    ),
    timezone: str = typer.Option(
        "Asia/Seoul", help="IANA timezone for the daily schedule."
    ),
    run_now: bool = typer.Option(
        False, "--run-now", help="Execute one collection immediately, then schedule."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run the crawler on a recurring schedule (foreground/blocking process)."""
    _setup_logging(verbose)
    cfg = CrawlConfig(market=market, top_n=top)

    if interval_hours is not None:
        schedule_interval(cfg, hours=interval_hours, run_now=run_now)
        return

    try:
        hh, mm = at.split(":")
        hour, minute = int(hh), int(mm)
    except ValueError as e:
        typer.echo(f"--at must be HH:MM (got {at!r}): {e}")
        raise typer.Exit(2)

    schedule_daily(cfg, hour=hour, minute=minute, timezone=timezone, run_now=run_now)


if __name__ == "__main__":
    app()
