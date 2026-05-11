"""저장된 종목별 OHLCV CSV 를 분석용 데이터프레임으로 적재한다."""

import logging
from pathlib import Path

import pandas as pd

from stock_crawler.config import DATA_DIR, Market
from stock_crawler.storage import csv_path

log = logging.getLogger(__name__)


def market_data_dir(market: Market, data_dir: Path = DATA_DIR) -> Path:
    """해당 시장의 OHLCV 디렉터리 경로를 돌려준다.

    Args:
        market: 대상 시장.
        data_dir: 데이터 루트 (기본값: 저장소 루트의 ``data/``).

    Returns:
        ``{data_dir}/{market}`` 경로.
    """
    return data_dir / market.value


def load_ohlcv(
    market: Market,
    ticker: str,
    *,
    lookback_days: int | None = None,
    data_dir: Path = DATA_DIR,
) -> pd.DataFrame:
    """단일 종목의 OHLCV CSV 를 ``date`` 인덱스 데이터프레임으로 적재한다.

    파일이 없거나 읽을 수 없으면 빈 ``DataFrame`` 을 반환한다(예외를 던지지 않는다).

    Args:
        market: 대상 시장.
        ticker: 종목 코드.
        lookback_days: 양의 정수가 주어지면 마지막 N개 거래일만 잘라서 반환한다.
            ``None`` 또는 0 이하이면 전체 이력을 반환한다.
        data_dir: 데이터 루트 디렉터리.

    Returns:
        오름차순 정렬된 ``date`` 인덱스 데이터프레임. 데이터가 없으면 빈 프레임.
    """
    p = csv_path(market_data_dir(market, data_dir), ticker)
    if not p.exists():
        log.warning("OHLCV file missing for %s/%s: %s", market.value, ticker, p)
        return pd.DataFrame()

    df = pd.read_csv(p, parse_dates=["date"])
    if df.empty:
        return df

    df = df.sort_values("date").set_index("date")
    if lookback_days is not None and lookback_days > 0:
        df = df.tail(lookback_days)
    return df
