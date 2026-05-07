import logging
from datetime import date
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)


def csv_path(market_dir: Path, ticker: str) -> Path:
    safe = ticker.replace("/", "_").replace("\\", "_")
    return market_dir / f"{safe}.csv"


def last_recorded_date(market_dir: Path, ticker: str) -> date | None:
    p = csv_path(market_dir, ticker)
    if not p.exists():
        return None
    try:
        df = pd.read_csv(p, usecols=["date"], parse_dates=["date"])
    except Exception as e:  # noqa: BLE001
        log.warning("Could not read %s, treating as empty: %s", p, e)
        return None
    if df.empty:
        return None
    return df["date"].max().date()


def upsert(market_dir: Path, ticker: str, new_df: pd.DataFrame) -> int:
    """Merge ``new_df`` (DatetimeIndex named 'date') into the per-ticker CSV.

    Returns the number of date rows that were not already on disk.
    """
    if new_df is None or new_df.empty:
        return 0
    market_dir.mkdir(parents=True, exist_ok=True)
    p = csv_path(market_dir, ticker)

    incoming = new_df.copy()
    if incoming.index.name == "date" or isinstance(incoming.index, pd.DatetimeIndex):
        incoming = incoming.reset_index()
    if "date" not in incoming.columns:
        first = incoming.columns[0]
        incoming = incoming.rename(columns={first: "date"})
    incoming["date"] = pd.to_datetime(incoming["date"]).dt.normalize()

    if p.exists():
        existing = pd.read_csv(p, parse_dates=["date"])
        existing["date"] = pd.to_datetime(existing["date"]).dt.normalize()
        before = set(existing["date"].dt.date)
        combined = pd.concat([existing, incoming], ignore_index=True)
    else:
        before = set()
        combined = incoming

    combined = (
        combined.drop_duplicates(subset="date", keep="last")
        .sort_values("date")
        .reset_index(drop=True)
    )
    combined.to_csv(p, index=False, date_format="%Y-%m-%d")
    after = set(combined["date"].dt.date)
    return len(after - before)
