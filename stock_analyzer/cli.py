import logging
import sys

import typer

from stock_crawler.config import Market

from .data import load_ohlcv
from .scanner import DEFAULT_LOOKBACK_DAYS, scan
from .strategies import STRATEGIES, run_strategy

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Short-term (1d~1w) trading-signal analyzer over stored OHLCV CSVs.",
)


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )


def _strategy_choices() -> str:
    return "|".join(STRATEGIES)


@app.command()
def analyze(
    ticker: str = typer.Argument(
        ..., help="Ticker code (e.g., 005930 for KOSPI, AAPL for NASDAQ)."
    ),
    market: Market = typer.Option(Market.kospi, help="Target market."),
    strategy: str = typer.Option("composite", help=f"Strategy to run ({_strategy_choices()})."),
    lookback_days: int = typer.Option(
        DEFAULT_LOOKBACK_DAYS, min=10, help="How many recent rows to feed indicators."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Analyze a single ticker and print the signal, score, reasons, and indicators."""
    _setup_logging(verbose)
    if strategy not in STRATEGIES:
        typer.echo(f"Unknown strategy {strategy!r}. Choose from {list(STRATEGIES)}.")
        raise typer.Exit(2)

    df = load_ohlcv(market, ticker, lookback_days=lookback_days)
    if df.empty:
        typer.echo(f"No OHLCV data for {market.value}/{ticker}. Run `fetch` first.")
        raise typer.Exit(1)

    res = run_strategy(strategy, df)
    typer.echo(f"[{market.value.upper()}] {ticker}  strategy={strategy}")
    typer.echo(f"  signal : {res.signal}")
    typer.echo(f"  score  : {res.score:+.3f}")
    if res.reasons:
        typer.echo("  reasons:")
        for r in res.reasons:
            typer.echo(f"    - {r}")
    if res.indicators:
        typer.echo("  indicators:")
        for k, v in res.indicators.items():
            typer.echo(f"    {k:>14} = {v:.4f}")


@app.command("scan")
def scan_cmd(
    market: Market = typer.Option(Market.kospi),
    top: int = typer.Option(200, min=1, max=2000),
    strategy: str = typer.Option("composite", help=f"Strategy to run ({_strategy_choices()})."),
    lookback_days: int = typer.Option(DEFAULT_LOOKBACK_DAYS, min=10),
    save: bool = typer.Option(True, help="Save signals CSV under data/{market}/_signals/."),
    show_top: int = typer.Option(20, min=0, help="Print top-N rows by |score|."),
    exclude_etf: bool = typer.Option(
        False, "--exclude-etf", help="Exclude ETFs from the top-N universe."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run the strategy across the market top-N and emit a ranked signal table."""
    _setup_logging(verbose)
    if strategy not in STRATEGIES:
        typer.echo(f"Unknown strategy {strategy!r}. Choose from {list(STRATEGIES)}.")
        raise typer.Exit(2)

    result_df = scan(
        market=market,
        top_n=top,
        strategy=strategy,
        lookback_days=lookback_days,
        save=save,
        exclude_etf=exclude_etf,
    )

    counts = result_df["signal"].value_counts().to_dict()
    typer.echo(
        f"\n[{market.value.upper()}] strategy={strategy} "
        f"buy={counts.get('buy', 0)} sell={counts.get('sell', 0)} hold={counts.get('hold', 0)}"
    )
    if show_top > 0 and not result_df.empty:
        cols = [c for c in ("ticker", "name", "signal", "score", "reasons") if c in result_df]
        typer.echo(result_df.head(show_top)[cols].to_string(index=False))


if __name__ == "__main__":
    app()
