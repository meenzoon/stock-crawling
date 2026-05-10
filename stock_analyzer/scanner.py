import logging
from datetime import date
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from stock_crawler.config import DATA_DIR, CrawlConfig, Market
from stock_crawler.tickers import resolve_tickers

from .data import load_ohlcv
from .strategies import StrategyResult, run_strategy

log = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS = 60


def _signals_dir(market: Market, data_dir: Path = DATA_DIR) -> Path:
    return data_dir / market.value / "_signals"


def _result_to_row(
    ticker: str,
    name: str,
    as_of: date,
    res: StrategyResult,
) -> dict[str, object]:
    row: dict[str, object] = {
        "as_of_date": as_of.isoformat(),
        "ticker": ticker,
        "name": name,
        "signal": res.signal,
        "score": round(res.score, 4),
        "reasons": " | ".join(res.reasons),
    }
    for k, v in res.indicators.items():
        row[k] = round(v, 4) if isinstance(v, float) else v
    return row


def scan(
    market: Market,
    *,
    top_n: int = 200,
    strategy: str = "composite",
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    save: bool = True,
    data_dir: Path = DATA_DIR,
    exclude_etf: bool = False,
) -> pd.DataFrame:
    cfg = CrawlConfig(market=market, top_n=top_n, data_dir=data_dir, exclude_etf=exclude_etf)
    universe = resolve_tickers(cfg, refresh=False)
    log.info(
        "Scanning %s top %d with strategy=%s",
        market.value.upper(),
        len(universe),
        strategy,
    )

    rows: list[dict[str, object]] = []
    today = date.today()
    iterator = tqdm(
        universe.itertuples(index=False),
        total=len(universe),
        desc=f"{market.value}/{strategy}",
    )
    for u in iterator:
        ticker = str(u.ticker).strip()
        name = str(getattr(u, "name", ""))
        df = load_ohlcv(market, ticker, lookback_days=lookback_days, data_dir=data_dir)
        if df.empty:
            res = StrategyResult(signal="hold", score=0.0, reasons=["no data"])
        else:
            try:
                res = run_strategy(strategy, df)
            except Exception as e:  # noqa: BLE001
                log.warning("Strategy %s failed for %s: %s", strategy, ticker, e)
                res = StrategyResult(signal="hold", score=0.0, reasons=[f"error: {e}"])
        rows.append(_result_to_row(ticker, name, today, res))

    result_df = pd.DataFrame(rows)
    result_df = result_df.sort_values("score", key=lambda s: s.abs(), ascending=False).reset_index(
        drop=True
    )

    if save:
        out_dir = _signals_dir(market, data_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{today.isoformat()}.csv"
        result_df.to_csv(out, index=False)
        log.info("Saved %d signals to %s", len(result_df), out)

    return result_df
