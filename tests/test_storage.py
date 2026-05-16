"""stock_crawler.storage 의 CSV 경로/마지막일자/병합 단위 테스트."""

from datetime import date
from pathlib import Path

import pandas as pd

from stock_crawler.storage import csv_path, last_recorded_date, upsert


def _idx_df(dates, closes):
    """``date`` 이름의 DatetimeIndex 를 가진 OHLCV 데이터프레임을 만든다."""
    return pd.DataFrame(
        {"close": closes},
        index=pd.DatetimeIndex(pd.to_datetime(dates), name="date"),
    )


# ---------- csv_path ----------


def test_csv_path_basic():
    assert csv_path(Path("/d/kospi"), "005930") == Path("/d/kospi/005930.csv")


def test_csv_path_sanitizes_separators():
    assert csv_path(Path("/d/nasdaq"), "BRK/B") == Path("/d/nasdaq/BRK_B.csv")
    assert csv_path(Path("/d/nasdaq"), "A\\B") == Path("/d/nasdaq/A_B.csv")


# ---------- last_recorded_date ----------


def test_last_recorded_date_missing_file(tmp_path):
    assert last_recorded_date(tmp_path, "AAA") is None


def test_last_recorded_date_returns_max(tmp_path):
    df = pd.DataFrame({"date": ["2024-01-02", "2024-01-05", "2024-01-03"], "close": [1, 2, 3]})
    df.to_csv(csv_path(tmp_path, "AAA"), index=False)
    assert last_recorded_date(tmp_path, "AAA") == date(2024, 1, 5)


def test_last_recorded_date_empty_file(tmp_path):
    pd.DataFrame({"date": []}).to_csv(csv_path(tmp_path, "AAA"), index=False)
    assert last_recorded_date(tmp_path, "AAA") is None


def test_last_recorded_date_unreadable_returns_none(tmp_path):
    # date 컬럼이 없는 파일 → read_csv 가 예외 → None 으로 처리
    pd.DataFrame({"close": [1, 2]}).to_csv(csv_path(tmp_path, "AAA"), index=False)
    assert last_recorded_date(tmp_path, "AAA") is None


# ---------- upsert ----------


def test_upsert_empty_input_returns_zero(tmp_path):
    assert upsert(tmp_path, "AAA", pd.DataFrame()) == 0
    assert upsert(tmp_path, "AAA", None) == 0


def test_upsert_creates_new_file(tmp_path):
    df = _idx_df(["2024-01-02", "2024-01-03"], [10.0, 11.0])
    added = upsert(tmp_path, "AAA", df)
    assert added == 2
    saved = pd.read_csv(csv_path(tmp_path, "AAA"))
    assert list(saved["date"]) == ["2024-01-02", "2024-01-03"]
    assert list(saved["close"]) == [10.0, 11.0]


def test_upsert_creates_missing_directory(tmp_path):
    market_dir = tmp_path / "kospi"
    added = upsert(market_dir, "AAA", _idx_df(["2024-01-02"], [10.0]))
    assert added == 1
    assert (market_dir / "AAA.csv").exists()


def test_upsert_counts_only_new_dates(tmp_path):
    upsert(tmp_path, "AAA", _idx_df(["2024-01-02", "2024-01-03"], [10.0, 11.0]))
    added = upsert(tmp_path, "AAA", _idx_df(["2024-01-03", "2024-01-04"], [11.5, 12.0]))
    assert added == 1  # 2024-01-04 만 신규


def test_upsert_dedupes_keeping_latest(tmp_path):
    upsert(tmp_path, "AAA", _idx_df(["2024-01-03"], [11.0]))
    upsert(tmp_path, "AAA", _idx_df(["2024-01-03"], [99.0]))
    saved = pd.read_csv(csv_path(tmp_path, "AAA"))
    assert len(saved) == 1
    assert saved["close"].iloc[0] == 99.0


def test_upsert_sorts_by_date(tmp_path):
    upsert(tmp_path, "AAA", _idx_df(["2024-01-05", "2024-01-01", "2024-01-03"], [1, 2, 3]))
    saved = pd.read_csv(csv_path(tmp_path, "AAA"))
    assert list(saved["date"]) == ["2024-01-01", "2024-01-03", "2024-01-05"]


def test_upsert_accepts_date_column(tmp_path):
    df = pd.DataFrame({"date": pd.to_datetime(["2024-01-02"]), "close": [10.0]})
    assert upsert(tmp_path, "AAA", df) == 1


def test_upsert_accepts_unnamed_datetime_index(tmp_path):
    df = pd.DataFrame({"close": [10.0]}, index=pd.DatetimeIndex(pd.to_datetime(["2024-01-02"])))
    added = upsert(tmp_path, "AAA", df)
    assert added == 1
    saved = pd.read_csv(csv_path(tmp_path, "AAA"))
    assert list(saved["date"]) == ["2024-01-02"]
