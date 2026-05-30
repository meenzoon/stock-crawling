"""stock_analyzer.data 의 OHLCV 로딩 단위 테스트."""

import pandas as pd

from stock_analyzer.data import load_ohlcv, market_data_dir
from stock_crawler.config import Market


def _write_ohlcv(data_dir, market, ticker, df):
    """``{data_dir}/{market}/{ticker}.csv`` 위치에 OHLCV CSV 를 쓴다."""
    d = data_dir / market.value
    d.mkdir(parents=True, exist_ok=True)
    df.to_csv(d / f"{ticker}.csv", index=False)


def test_market_data_dir(tmp_path):
    assert market_data_dir(Market.kospi, tmp_path) == tmp_path / "kospi"


def test_load_ohlcv_missing_file_returns_empty(tmp_path):
    df = load_ohlcv(Market.kospi, "AAA", data_dir=tmp_path)
    assert df.empty


def test_load_ohlcv_corrupt_csv_returns_empty(tmp_path):
    # date 컬럼이 없는 손상 CSV 는 예외 없이 빈 프레임으로 처리되어야 한다
    raw = pd.DataFrame({"open": [1, 2], "close": [1, 2]})
    _write_ohlcv(tmp_path, Market.kospi, "AAA", raw)
    df = load_ohlcv(Market.kospi, "AAA", data_dir=tmp_path)
    assert df.empty


def test_load_ohlcv_reads_and_sorts_by_date(tmp_path):
    raw = pd.DataFrame({"date": ["2024-01-03", "2024-01-01", "2024-01-02"], "close": [3, 1, 2]})
    _write_ohlcv(tmp_path, Market.kospi, "AAA", raw)
    df = load_ohlcv(Market.kospi, "AAA", data_dir=tmp_path)
    assert list(df["close"]) == [1, 2, 3]
    assert df.index.name == "date"
    assert df.index.is_monotonic_increasing


def test_load_ohlcv_lookback_keeps_last_n(tmp_path):
    raw = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=10, freq="D").astype(str),
            "close": range(10),
        }
    )
    _write_ohlcv(tmp_path, Market.kospi, "AAA", raw)
    df = load_ohlcv(Market.kospi, "AAA", lookback_days=3, data_dir=tmp_path)
    assert len(df) == 3
    assert list(df["close"]) == [7, 8, 9]


def test_load_ohlcv_lookback_none_returns_all(tmp_path):
    raw = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=5, freq="D").astype(str),
            "close": range(5),
        }
    )
    _write_ohlcv(tmp_path, Market.kospi, "AAA", raw)
    df = load_ohlcv(Market.kospi, "AAA", lookback_days=None, data_dir=tmp_path)
    assert len(df) == 5
