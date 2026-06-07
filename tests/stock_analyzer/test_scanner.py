"""stock_analyzer.scanner.scan 의 신호 스캔 동작 단위 테스트."""

import pandas as pd

from stock_analyzer import scanner
from stock_crawler.config import Market


def test_scan_empty_universe_does_not_raise(tmp_path, monkeypatch):
    # universe 가 비면 result_df 에 컬럼이 없어 sort_values("score") 가 KeyError 였음
    monkeypatch.setattr(
        scanner,
        "resolve_tickers",
        lambda cfg, refresh=False: pd.DataFrame(columns=["ticker", "name"]),
    )
    out = scanner.scan(Market.kospi, top_n=5, save=False, data_dir=tmp_path)
    assert out.empty
