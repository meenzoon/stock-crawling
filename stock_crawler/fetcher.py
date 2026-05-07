from __future__ import annotations

import logging
from datetime import date

import pandas as pd
import yfinance as yf

from .config import Market

log = logging.getLogger(__name__)

OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]

# KOSPI tickers on Yahoo Finance require the ".KS" suffix
_KOSPI_SUFFIX = ".KS"


def _yf_symbol(market: Market, ticker: str) -> str:
    if market is Market.kospi:
        return ticker + _KOSPI_SUFFIX
    return ticker


def fetch_yfinance(symbol: str, start: date | None = None) -> pd.DataFrame:
    """Daily OHLCV via yfinance. start=None pulls full history (period='max')."""
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
    """Fetch OHLCV via yfinance for both KOSPI (.KS suffix) and NASDAQ."""
    return fetch_yfinance(_yf_symbol(market, ticker), start=start)
