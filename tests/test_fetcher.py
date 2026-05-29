"""stock_crawler.fetcher 의 yfinance 래퍼 단위 테스트."""

import pandas as pd
import pytest

from stock_crawler import fetcher
from stock_crawler.fetcher import OHLCV_COLUMNS, fetch_yfinance


class _FakeTicker:
    """``yfinance.Ticker`` 를 대체하는 더미. 미리 지정한 프레임을 반환한다."""

    def __init__(self, df):
        self._df = df

    def history(self, **_kwargs):
        return self._df


def _patch_ticker(monkeypatch, df):
    monkeypatch.setattr(fetcher.yf, "Ticker", lambda _symbol: _FakeTicker(df))


def _yf_frame(columns):
    """yfinance 스타일(대문자 컬럼, DatetimeIndex)의 프레임을 만든다."""
    idx = pd.date_range("2024-01-01", periods=3, freq="D")
    return pd.DataFrame({c: [1.0, 2.0, 3.0] for c in columns}, index=idx)


def test_returns_canonical_columns(monkeypatch):
    _patch_ticker(monkeypatch, _yf_frame(["Open", "High", "Low", "Close", "Volume"]))
    out = fetch_yfinance("AAPL")
    assert list(out.columns) == OHLCV_COLUMNS
    assert out.index.name == "date"


def test_ignores_extra_columns(monkeypatch):
    _patch_ticker(
        monkeypatch,
        _yf_frame(["Open", "High", "Low", "Close", "Volume", "Dividends"]),
    )
    assert list(fetch_yfinance("AAPL").columns) == OHLCV_COLUMNS


def test_missing_column_raises(monkeypatch):
    # volume 누락 (부분 응답 / 스키마 변경 시나리오)
    _patch_ticker(monkeypatch, _yf_frame(["Open", "High", "Low", "Close"]))
    with pytest.raises(ValueError, match="missing.*volume"):
        fetch_yfinance("AAPL")


def test_empty_response_returns_empty_frame(monkeypatch):
    _patch_ticker(monkeypatch, pd.DataFrame())
    out = fetch_yfinance("AAPL")
    assert out.empty
    assert list(out.columns) == OHLCV_COLUMNS


def test_tz_aware_index_is_localized_to_naive(monkeypatch):
    df = _yf_frame(["Open", "High", "Low", "Close", "Volume"])
    df.index = df.index.tz_localize("America/New_York")
    _patch_ticker(monkeypatch, df)
    out = fetch_yfinance("AAPL")
    assert out.index.tz is None
