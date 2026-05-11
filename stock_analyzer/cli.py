"""분석기 CLI 진입점. ``analyze`` (단일 종목), ``scan`` (시장 전체) 명령을 노출한다."""

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
    help="저장된 OHLCV CSV 위에서 단기(1일~1주일) 매매 신호를 생성하는 분석기.",
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


def _strategy_choices() -> str:
    """help 텍스트에 보여줄 전략 선택지 문자열 ('rsi|ema|...' 형태)."""
    return "|".join(STRATEGIES)


@app.command()
def analyze(
    ticker: str = typer.Argument(
        ..., help="종목 코드 (KOSPI 는 6자리 숫자, NASDAQ 은 알파벳 심볼). 예: 005930, AAPL."
    ),
    market: Market = typer.Option(Market.kospi, help="대상 시장."),
    strategy: str = typer.Option("composite", help=f"실행할 전략 ({_strategy_choices()})."),
    lookback_days: int = typer.Option(
        DEFAULT_LOOKBACK_DAYS,
        min=10,
        help="지표 계산에 사용할 최근 거래일 수 (최소 10).",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="DEBUG 로그를 활성화한다."),
) -> None:
    """단일 종목을 분석해 신호/점수/사유/지표를 출력한다."""
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
    market: Market = typer.Option(Market.kospi, help="대상 시장."),
    top: int = typer.Option(200, min=1, max=2000, help="분석할 시가총액 상위 종목 수."),
    strategy: str = typer.Option("composite", help=f"실행할 전략 ({_strategy_choices()})."),
    lookback_days: int = typer.Option(
        DEFAULT_LOOKBACK_DAYS, min=10, help="지표 계산에 사용할 최근 거래일 수."
    ),
    save: bool = typer.Option(True, help="data/{market}/_signals/ 아래에 신호 CSV 를 저장할지."),
    show_top: int = typer.Option(
        20, min=0, help="|score| 내림차순 상위 N개 행을 표준 출력으로 보여준다."
    ),
    exclude_etf: bool = typer.Option(
        False, "--exclude-etf", help="TOP-N 산정에서 ETF 종목을 제외한다."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="DEBUG 로그를 활성화한다."),
) -> None:
    """시장 TOP-N 전체에 전략을 실행해 점수 순 신호 표를 출력/저장한다."""
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
