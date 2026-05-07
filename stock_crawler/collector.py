import logging
import time
from datetime import date, timedelta
from typing import Any

import pandas as pd
from tqdm import tqdm

from .config import CrawlConfig
from .fetcher import fetch_history
from .storage import last_recorded_date, upsert
from .tickers import resolve_tickers

log = logging.getLogger(__name__)


def _fetch_with_retry(cfg: CrawlConfig, ticker: str, start: date | None) -> pd.DataFrame:
    last_err: Exception | None = None
    for attempt in range(1, cfg.max_retries + 1):
        try:
            return fetch_history(cfg.market, ticker, start=start)
        except Exception as e:  # noqa: BLE001
            last_err = e
            backoff = min(2**attempt, 10)
            log.debug(
                "Retry %d/%d for %s after error: %s (sleep %ss)",
                attempt,
                cfg.max_retries,
                ticker,
                e,
                backoff,
            )
            time.sleep(backoff)
    raise RuntimeError(f"Failed to fetch {ticker}: {last_err}")


def collect(cfg: CrawlConfig, refresh_tickers: bool = False) -> dict[str, Any]:
    cfg.market_data_dir.mkdir(parents=True, exist_ok=True)
    universe = resolve_tickers(cfg, refresh=refresh_tickers)
    log.info(
        "Collecting %s top %d (resolved %d tickers) → %s",
        cfg.market.value.upper(),
        cfg.top_n,
        len(universe),
        cfg.market_data_dir,
    )

    succeeded = 0
    failed: list[tuple[str, str]] = []
    new_rows = 0

    iterator = tqdm(
        universe.itertuples(index=False),
        total=len(universe),
        desc=cfg.market.value,
    )
    for row in iterator:
        ticker = str(row.ticker).strip()
        last = last_recorded_date(cfg.market_data_dir, ticker)
        start = (last + timedelta(days=1)) if last else None

        try:
            df = _fetch_with_retry(cfg, ticker, start)
        except Exception as e:  # noqa: BLE001
            log.warning("Fetch failed for %s: %s", ticker, e)
            failed.append((ticker, str(e)))
            continue

        added = upsert(cfg.market_data_dir, ticker, df)
        new_rows += added
        succeeded += 1
        time.sleep(cfg.request_delay)

    summary = {
        "market": cfg.market.value,
        "tickers": len(universe),
        "succeeded": succeeded,
        "failed": len(failed),
        "new_rows": new_rows,
        "failures": failed,
    }
    log.info(
        "Done %s: succeeded=%d failed=%d new_rows=%d",
        cfg.market.value,
        succeeded,
        len(failed),
        new_rows,
    )
    return summary
