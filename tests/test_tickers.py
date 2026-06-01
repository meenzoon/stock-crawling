"""stock_crawler.tickers.resolve_tickers 의 캐시 동작 단위 테스트."""

import pandas as pd

from stock_crawler import tickers
from stock_crawler.config import CrawlConfig, Market


def _cfg(tmp_path, top_n=3):
    return CrawlConfig(market=Market.nasdaq, top_n=top_n, tickers_dir=tmp_path)


def _patch_fetch(monkeypatch, df):
    """nasdaq fetch 를 더미로 대체하고, 호출 여부 추적용 플래그를 반환한다."""
    calls = {"n": 0}

    def _fake(n, exclude_etf=False):
        calls["n"] += 1
        return df

    monkeypatch.setattr(tickers, "fetch_nasdaq_top", _fake)
    return calls


def _valid_df(symbols):
    return pd.DataFrame(
        {
            "ticker": symbols,
            "name": [f"{s} Inc" for s in symbols],
            "market_cap": [1.0] * len(symbols),
            "as_of": ["2024-01-01"] * len(symbols),
        }
    )


def test_valid_cache_is_reused_without_fetch(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    cfg.market_tickers_file.write_text(_valid_df(["AAA", "BBB", "CCC"]).to_csv(index=False))
    calls = _patch_fetch(monkeypatch, _valid_df(["X", "Y", "Z"]))

    out = tickers.resolve_tickers(cfg)
    assert list(out["ticker"]) == ["AAA", "BBB", "CCC"]
    assert calls["n"] == 0


def test_corrupt_cache_missing_ticker_column_refetches(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    # ticker 컬럼이 없는 손상된 캐시
    pd.DataFrame({"symbol": ["AAA", "BBB", "CCC"]}).to_csv(cfg.market_tickers_file, index=False)
    calls = _patch_fetch(monkeypatch, _valid_df(["X", "Y", "Z"]))

    out = tickers.resolve_tickers(cfg)
    assert calls["n"] == 1
    assert list(out["ticker"]) == ["X", "Y", "Z"]
    # 손상 캐시가 정상 데이터로 덮어써졌는지 확인
    assert "ticker" in pd.read_csv(cfg.market_tickers_file).columns


def test_empty_cache_file_refetches(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    cfg.market_tickers_file.write_text("")  # 0바이트 → EmptyDataError
    calls = _patch_fetch(monkeypatch, _valid_df(["X", "Y", "Z"]))

    out = tickers.resolve_tickers(cfg)
    assert calls["n"] == 1
    assert list(out["ticker"]) == ["X", "Y", "Z"]


def test_unparseable_cache_refetches(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    # 따옴표가 닫히지 않은 파싱 불가 CSV → ParserError
    cfg.market_tickers_file.write_text('ticker,name\n"AAA,Inc\n')
    calls = _patch_fetch(monkeypatch, _valid_df(["X", "Y", "Z"]))

    out = tickers.resolve_tickers(cfg)
    assert calls["n"] == 1
    assert list(out["ticker"]) == ["X", "Y", "Z"]


def test_short_cache_refetches(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, top_n=3)
    cfg.market_tickers_file.write_text(_valid_df(["AAA"]).to_csv(index=False))
    calls = _patch_fetch(monkeypatch, _valid_df(["X", "Y", "Z"]))

    out = tickers.resolve_tickers(cfg)
    assert calls["n"] == 1
    assert list(out["ticker"]) == ["X", "Y", "Z"]


def test_refresh_forces_fetch(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    cfg.market_tickers_file.write_text(_valid_df(["AAA", "BBB", "CCC"]).to_csv(index=False))
    calls = _patch_fetch(monkeypatch, _valid_df(["X", "Y", "Z"]))

    out = tickers.resolve_tickers(cfg, refresh=True)
    assert calls["n"] == 1
    assert list(out["ticker"]) == ["X", "Y", "Z"]
