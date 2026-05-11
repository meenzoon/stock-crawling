"""yfinance 를 통해 일봉 OHLCV 를 받아오는 얇은 래퍼.

KOSPI 종목은 Yahoo Finance 규약상 ``.KS`` 접미사가 필요하므로 시장에 따라
심볼을 가공한 뒤 ``yfinance.Ticker.history`` 를 호출한다.
"""

import logging
from datetime import date

import pandas as pd
import yfinance as yf

from .config import Market

log = logging.getLogger(__name__)

OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]

# Yahoo Finance 에서 KOSPI 종목은 ".KS" 접미사가 필요함
_KOSPI_SUFFIX = ".KS"


def _yf_symbol(market: Market, ticker: str) -> str:
    """시장에 맞춰 yfinance 가 인식할 수 있는 심볼로 변환한다.

    Args:
        market: 종목이 속한 시장.
        ticker: 원본 종목 코드 (KOSPI 6자리 등).

    Returns:
        KOSPI 라면 ``"{ticker}.KS"``, NASDAQ 이면 원본 그대로.
    """
    if market is Market.kospi:
        return ticker + _KOSPI_SUFFIX
    return ticker


def fetch_yfinance(symbol: str, start: date | None = None) -> pd.DataFrame:
    """단일 yfinance 심볼의 일봉 OHLCV 를 가져온다.

    Args:
        symbol: yfinance 가 인식하는 심볼 (KOSPI 의 경우 ``.KS`` 접미사 포함).
        start: 가져올 시작일. ``None`` 이면 ``period='max'`` 로 전체 이력을 받는다.

    Returns:
        ``date`` 인덱스(naive), 컬럼은 소문자 ``open/high/low/close/volume``.
        데이터가 없으면 동일 컬럼의 빈 데이터프레임을 반환한다.
    """
    t = yf.Ticker(symbol)
    if start is None:
        df = t.history(period="max", auto_adjust=False, actions=False)
    else:
        df = t.history(start=start.strftime("%Y-%m-%d"), auto_adjust=False, actions=False)
    if df is None or df.empty:
        return pd.DataFrame(columns=OHLCV_COLUMNS)

    idx = pd.to_datetime(df.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    df.index = idx
    df.index.name = "date"
    df = df.rename(columns=str.lower)
    return df[[c for c in OHLCV_COLUMNS if c in df.columns]]


def fetch_history(market: Market, ticker: str, start: date | None) -> pd.DataFrame:
    """KOSPI/NASDAQ 종목의 일봉 OHLCV 를 시장 규약에 맞춰 받아온다.

    Args:
        market: 종목이 속한 시장.
        ticker: 원본 종목 코드.
        start: 수집 시작일. ``None`` 이면 전체 이력을 받는다.

    Returns:
        ``fetch_yfinance`` 와 동일한 형태의 데이터프레임.
    """
    return fetch_yfinance(_yf_symbol(market, ticker), start=start)
