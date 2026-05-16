"""stock_crawler.config 의 Market enum 과 CrawlConfig 단위 테스트."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from stock_crawler.config import CrawlConfig, Market


def test_market_enum_values():
    assert Market.kospi.value == "kospi"
    assert Market.nasdaq.value == "nasdaq"
    assert Market("kospi") is Market.kospi


def test_crawl_config_defaults():
    cfg = CrawlConfig(market=Market.kospi)
    assert cfg.top_n == 200
    assert cfg.request_delay == 0.3
    assert cfg.max_retries == 3
    assert cfg.max_per_minute == 30
    assert cfg.jitter == 0.1
    assert cfg.exclude_etf is False


def test_market_data_dir():
    cfg = CrawlConfig(market=Market.kospi, data_dir=Path("/data"))
    assert cfg.market_data_dir == Path("/data/kospi")


def test_market_tickers_file_default():
    cfg = CrawlConfig(market=Market.nasdaq, tickers_dir=Path("/t"), top_n=200)
    assert cfg.market_tickers_file == Path("/t/nasdaq_top200.csv")


def test_market_tickers_file_exclude_etf_suffix():
    cfg = CrawlConfig(market=Market.kospi, tickers_dir=Path("/t"), top_n=50, exclude_etf=True)
    assert cfg.market_tickers_file == Path("/t/kospi_top50_no_etf.csv")


def test_crawl_config_is_frozen():
    cfg = CrawlConfig(market=Market.kospi)
    with pytest.raises(FrozenInstanceError):
        cfg.top_n = 5
