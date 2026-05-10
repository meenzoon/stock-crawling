import logging
import re
import time

import pandas as pd
import requests
from bs4 import BeautifulSoup

from .config import CrawlConfig, Market

log = logging.getLogger(__name__)


# ---------- KOSPI: Naver Finance market-cap ranking (free, no auth) ----------

NAVER_MARKET_SUM_URL = "https://finance.naver.com/sise/sise_market_sum.naver?sosok=0&page={page}"
NAVER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}
NAVER_PAGE_SIZE = 50  # rows per market-sum page
NAVER_ETF_LIST_URL = "https://finance.naver.com/api/sise/etfItemList.nhn"


def fetch_kospi_etf_codes() -> set[str]:
    """All KOSPI/KOSDAQ-listed ETF item codes from the Naver ETF JSON endpoint."""
    resp = requests.get(NAVER_ETF_LIST_URL, headers=NAVER_HEADERS, timeout=15)
    resp.raise_for_status()
    payload = resp.json()
    items = (payload.get("result") or {}).get("etfItemList") or []
    if not items:
        raise RuntimeError("Naver ETF list endpoint returned no items")
    codes = {str(item.get("itemcode", "")).strip() for item in items}
    codes = {c for c in codes if re.fullmatch(r"\d{6}", c)}
    log.info("Fetched %d KOSPI/KOSDAQ ETF codes from Naver", len(codes))
    return codes


def fetch_kospi_top(n: int, exclude_etf: bool = False) -> pd.DataFrame:
    """KOSPI top-N by market cap, scraped from Naver Finance market-sum pages."""
    etf_codes: set[str] = fetch_kospi_etf_codes() if exclude_etf else set()
    rows: list[dict] = []
    base_pages = (n + NAVER_PAGE_SIZE - 1) // NAVER_PAGE_SIZE
    max_pages = base_pages * 2 if exclude_etf else base_pages
    for page in range(1, max_pages + 1):
        url = NAVER_MARKET_SUM_URL.format(page=page)
        resp = requests.get(url, headers=NAVER_HEADERS, timeout=15)
        resp.raise_for_status()
        resp.encoding = "euc-kr"
        soup = BeautifulSoup(resp.text, "html.parser")
        table = soup.select_one("table.type_2")
        if table is None:
            raise RuntimeError(f"Naver market-sum page {page} missing data table")

        for tr in table.select("tbody tr"):
            tds = tr.find_all("td")
            if len(tds) < 8:
                continue
            link = tds[1].find("a")
            if link is None:
                continue
            href = link.get("href", "")
            m = re.search(r"code=(\d{6})", href)
            if not m:
                continue
            code = m.group(1)
            if code in etf_codes:
                continue
            name = link.get_text(strip=True)
            cap_text = tds[6].get_text(strip=True).replace(",", "")
            try:
                # Naver shows market cap in units of 억 (1e8 KRW).
                market_cap = int(cap_text) * 100_000_000
            except ValueError:
                market_cap = 0
            rows.append({"ticker": code, "name": name, "market_cap": market_cap})
            if len(rows) >= n:
                break
        if len(rows) >= n:
            break
        time.sleep(0.2)

    if not rows:
        raise RuntimeError("Naver Finance returned no KOSPI rows")

    df = pd.DataFrame(rows).head(n).reset_index(drop=True)
    df["as_of"] = pd.Timestamp.today().strftime("%Y-%m-%d")
    log.info(
        "KOSPI top %d resolved from Naver Finance (exclude_etf=%s)",
        len(df),
        exclude_etf,
    )
    return df


# ---------- NASDAQ: nasdaq.com public screener API ----------

NASDAQ_SCREENER_URL = "https://api.nasdaq.com/api/screener/stocks"
NASDAQ_ETF_SCREENER_URL = "https://api.nasdaq.com/api/screener/etf"
NASDAQ_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/",
}


def _coerce_money(series: pd.Series) -> pd.Series:
    if series.dtype.kind in ("i", "f"):
        return series.astype(float)
    return (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.strip()
        .replace({"": "0", "NA": "0", "N/A": "0", "nan": "0"})
        .astype(float)
    )


def fetch_nasdaq_etf_symbols() -> set[str]:
    """All NASDAQ-listed ETF symbols from the nasdaq.com ETF screener."""
    params = {"tableonly": "true", "limit": "5000", "download": "true"}
    resp = requests.get(NASDAQ_ETF_SCREENER_URL, params=params, headers=NASDAQ_HEADERS, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    data = payload.get("data") or {}
    raw_rows = (
        data.get("rows")
        or (data.get("table") or {}).get("rows")
        or (data.get("data") or {}).get("rows")
        or []
    )
    if not raw_rows:
        raise RuntimeError("NASDAQ ETF screener returned no rows")
    symbols = {str(row.get("symbol", "")).strip().upper() for row in raw_rows if row.get("symbol")}
    symbols.discard("")
    log.info("Fetched %d NASDAQ ETF symbols", len(symbols))
    return symbols


def fetch_nasdaq_top(n: int, exclude_etf: bool = False) -> pd.DataFrame:
    """NASDAQ-listed top-N by market cap from the nasdaq.com screener."""
    etf_symbols: set[str] = fetch_nasdaq_etf_symbols() if exclude_etf else set()
    limit = max(n * 4, 400) if exclude_etf else max(n * 3, 200)
    params = {
        "tableonly": "true",
        "limit": str(limit),
        "exchange": "NASDAQ",
        "download": "true",
    }
    resp = requests.get(NASDAQ_SCREENER_URL, params=params, headers=NASDAQ_HEADERS, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    data = payload.get("data") or {}
    raw_rows = data.get("rows") or (data.get("table") or {}).get("rows") or []
    if not raw_rows:
        raise RuntimeError("NASDAQ screener returned no rows")

    df = pd.DataFrame(raw_rows).rename(
        columns={"symbol": "ticker", "name": "name", "marketCap": "market_cap"}
    )
    if "ticker" not in df.columns or "market_cap" not in df.columns:
        raise RuntimeError(f"Unexpected NASDAQ payload columns: {list(df.columns)}")

    df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()
    df = df[~df["ticker"].str.contains(r"[\^\.\/]", regex=True, na=False)]
    if etf_symbols:
        df = df[~df["ticker"].isin(etf_symbols)]
    df["market_cap"] = _coerce_money(df["market_cap"])
    df = (
        df[df["market_cap"] > 0]
        .drop_duplicates(subset="ticker")
        .sort_values("market_cap", ascending=False)
        .head(n)
        .reset_index(drop=True)
    )
    df["as_of"] = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    log.info(
        "NASDAQ top %d resolved (out of %d candidates, exclude_etf=%s)",
        len(df),
        len(raw_rows),
        exclude_etf,
    )
    return df[["ticker", "name", "market_cap", "as_of"]]


# ---------- Public entry point with on-disk cache ----------


def resolve_tickers(cfg: CrawlConfig, refresh: bool = False) -> pd.DataFrame:
    cfg.tickers_dir.mkdir(parents=True, exist_ok=True)
    out = cfg.market_tickers_file
    if not refresh and out.exists():
        cached = pd.read_csv(out, dtype={"ticker": str})
        if len(cached) >= cfg.top_n:
            return cached.head(cfg.top_n)

    if cfg.market is Market.kospi:
        df = fetch_kospi_top(cfg.top_n, exclude_etf=cfg.exclude_etf)
    else:
        df = fetch_nasdaq_top(cfg.top_n, exclude_etf=cfg.exclude_etf)
    df.to_csv(out, index=False)
    return df
