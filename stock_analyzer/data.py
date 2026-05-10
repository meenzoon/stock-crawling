import logging
from pathlib import Path

import pandas as pd

from stock_crawler.config import DATA_DIR, Market
from stock_crawler.storage import csv_path

log = logging.getLogger(__name__)


def market_data_dir(market: Market, data_dir: Path = DATA_DIR) -> Path:
    return data_dir / market.value


def load_ohlcv(
    market: Market,
    ticker: str,
    *,
    lookback_days: int | None = None,
    data_dir: Path = DATA_DIR,
) -> pd.DataFrame:
    """Load per-ticker OHLCV CSV as a DataFrame indexed by date.

    Returns an empty DataFrame if the file is missing or unreadable.
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
