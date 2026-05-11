"""TOP-N 종목 전체에 전략을 적용해 신호 표를 생성하고 디스크에 저장한다."""

import logging
from datetime import date
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from stock_crawler.config import DATA_DIR, CrawlConfig, Market
from stock_crawler.tickers import resolve_tickers

from .data import load_ohlcv
from .strategies import StrategyResult, run_strategy

log = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS = 60


def _signals_dir(market: Market, data_dir: Path = DATA_DIR) -> Path:
    """일자별 신호 CSV 가 저장될 디렉터리 (``data/{market}/_signals``)."""
    return data_dir / market.value / "_signals"


def _result_to_row(
    ticker: str,
    name: str,
    as_of: date,
    res: StrategyResult,
) -> dict[str, object]:
    """``StrategyResult`` 한 건을 신호 CSV 의 한 행 딕셔너리로 변환한다.

    Args:
        ticker: 종목 코드.
        name: 종목명.
        as_of: 신호 산정 기준일.
        res: 전략 실행 결과.

    Returns:
        ``as_of_date / ticker / name / signal / score / reasons`` 와 indicators 가
        평탄화되어 들어간 행 딕셔너리.
    """
    row: dict[str, object] = {
        "as_of_date": as_of.isoformat(),
        "ticker": ticker,
        "name": name,
        "signal": res.signal,
        "score": round(res.score, 4),
        "reasons": " | ".join(res.reasons),
    }
    for k, v in res.indicators.items():
        row[k] = round(v, 4) if isinstance(v, float) else v
    return row


def scan(
    market: Market,
    *,
    top_n: int = 200,
    strategy: str = "composite",
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    save: bool = True,
    data_dir: Path = DATA_DIR,
    exclude_etf: bool = False,
) -> pd.DataFrame:
    """TOP-N 종목 전체에 전략을 적용해 신호 데이터프레임을 생성한다.

    종목 단위 실패는 잡아서 ``hold`` 결과로 대체하고 전체 흐름을 계속한다.
    결과는 ``|score|`` 내림차순으로 정렬된다.

    Args:
        market: 대상 시장.
        top_n: 분석할 시가총액 상위 종목 수.
        strategy: ``stock_analyzer.strategies.STRATEGIES`` 키 중 하나.
        lookback_days: 각 종목당 인디케이터 계산용으로 잘라 읽을 최근 거래일 수.
        save: ``True`` 이면 ``data/{market}/_signals/{YYYY-MM-DD}.csv`` 로 저장한다.
        data_dir: OHLCV 와 신호 디렉터리의 공통 루트.
        exclude_etf: ``True`` 이면 TOP-N 산정에서 ETF 를 제외한다.

    Returns:
        정렬된 신호 데이터프레임 (``as_of_date, ticker, name, signal, score,
        reasons`` + 전략별 지표 컬럼).
    """
    cfg = CrawlConfig(market=market, top_n=top_n, data_dir=data_dir, exclude_etf=exclude_etf)
    universe = resolve_tickers(cfg, refresh=False)
    log.info(
        "Scanning %s top %d with strategy=%s",
        market.value.upper(),
        len(universe),
        strategy,
    )

    rows: list[dict[str, object]] = []
    today = date.today()
    iterator = tqdm(
        universe.itertuples(index=False),
        total=len(universe),
        desc=f"{market.value}/{strategy}",
    )
    for u in iterator:
        ticker = str(u.ticker).strip()
        name = str(getattr(u, "name", ""))
        df = load_ohlcv(market, ticker, lookback_days=lookback_days, data_dir=data_dir)
        if df.empty:
            res = StrategyResult(signal="hold", score=0.0, reasons=["no data"])
        else:
            try:
                res = run_strategy(strategy, df)
            except Exception as e:  # noqa: BLE001
                log.warning("Strategy %s failed for %s: %s", strategy, ticker, e)
                res = StrategyResult(signal="hold", score=0.0, reasons=[f"error: {e}"])
        rows.append(_result_to_row(ticker, name, today, res))

    result_df = pd.DataFrame(rows)
    result_df = result_df.sort_values("score", key=lambda s: s.abs(), ascending=False).reset_index(
        drop=True
    )

    if save:
        out_dir = _signals_dir(market, data_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{today.isoformat()}.csv"
        result_df.to_csv(out, index=False)
        log.info("Saved %d signals to %s", len(result_df), out)

    return result_df
