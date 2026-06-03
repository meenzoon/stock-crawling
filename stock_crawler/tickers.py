"""KOSPI / NASDAQ 시가총액 TOP-N 티커 목록을 해석하고 디스크에 캐시한다.

KOSPI 는 Naver Finance 시가총액 페이지(HTML)를 스크래핑하고, NASDAQ 은
nasdaq.com 의 공개 screener API(JSON)를 사용한다. ``exclude_etf`` 옵션이
켜진 경우 각 시장별 ETF 코드 목록을 별도로 받아 차집합으로 필터링한다.
"""

import logging
import re
import time

import pandas as pd
import requests
from bs4 import BeautifulSoup

from .config import CrawlConfig, Market
from .storage import read_csv_or_none

log = logging.getLogger(__name__)


# ---------- KOSPI: Naver Finance 시가총액 랭킹 (무료, 인증 불필요) ----------

NAVER_MARKET_SUM_URL = "https://finance.naver.com/sise/sise_market_sum.naver?sosok=0&page={page}"
NAVER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}
NAVER_PAGE_SIZE = 50  # 시가총액 페이지 한 페이지당 행 수
NAVER_ETF_LIST_URL = "https://finance.naver.com/api/sise/etfItemList.nhn"


def fetch_kospi_etf_codes() -> set[str]:
    """Naver ETF 목록 JSON 엔드포인트에서 KOSPI/KOSDAQ 상장 ETF 코드를 모두 받아온다.

    Returns:
        6자리 ETF 종목 코드의 집합.

    Raises:
        RuntimeError: 응답이 비어 있거나 예상한 키 구조가 아닌 경우.
    """
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
    """Naver Finance 시가총액 페이지를 스크래핑해 KOSPI TOP-N 종목을 반환한다.

    Args:
        n: 가져올 상위 종목 수.
        exclude_etf: ``True`` 이면 ETF 코드를 차집합으로 제외한다. 이때 ETF 만큼
            결과가 줄어드는 것을 보전하기 위해 페이지 상한을 두 배로 확장한다.

    Returns:
        컬럼이 ``ticker, name, market_cap, as_of`` 인 데이터프레임.

    Raises:
        RuntimeError: 페이지 응답에 데이터 테이블이 없거나 한 행도 추출하지 못한 경우.
    """
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
                # Naver 는 시가총액을 억원 단위(1e8 KRW)로 표시함
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


# ---------- NASDAQ: nasdaq.com 공개 screener API ----------

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
    """문자열로 표현된 시가총액 컬럼(``"$1,234,000"`` 등)을 부동소수로 변환한다.

    Args:
        series: 변환 대상 시리즈. 이미 숫자형이면 그대로 ``float`` 캐스팅한다.

    Returns:
        ``float`` 타입의 시리즈. 빈 문자열/'NA'/'N/A'/'nan' 은 ``0`` 으로 처리된다.
    """
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
    """nasdaq.com ETF screener 에서 NASDAQ 상장 ETF 심볼을 모두 받아온다.

    Returns:
        대문자로 정규화된 ETF 심볼의 집합.

    Raises:
        RuntimeError: 응답에 행이 하나도 없는 경우.
    """
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
    """nasdaq.com 공개 screener 로 NASDAQ 상장 TOP-N 종목(시가총액 기준)을 받아온다.

    Args:
        n: 가져올 상위 종목 수.
        exclude_etf: ``True`` 이면 ETF 심볼을 차집합으로 제외한다. 안전 마진을
            위해 over-fetch 배수를 3배에서 4배로 늘리고 ETF 목록을 사전에 받는다.

    Returns:
        컬럼이 ``ticker, name, market_cap, as_of`` 인 데이터프레임.

    Raises:
        RuntimeError: 응답이 비어 있거나 예상한 컬럼이 없을 때.
    """
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


# ---------- 디스크 캐시를 갖는 공개 진입점 ----------


def resolve_tickers(cfg: CrawlConfig, refresh: bool = False) -> pd.DataFrame:
    """TOP-N 티커 목록을 캐시 파일에서 읽거나 새로 받아온다.

    캐시 파일 경로는 ``cfg.market_tickers_file`` 로 결정되며, ``exclude_etf``
    플래그에 따라 자동으로 분리된 파일명을 사용한다. ``refresh=True`` 일 때만
    강제로 다시 받아 캐시를 갱신한다. 읽을 수 없거나(빈 파일·잘린 CSV 등)
    ``ticker`` 컬럼이 없는 손상된 캐시는 무시하고 원격에서 다시 받아 덮어쓴다.

    Args:
        cfg: 시장/TOP-N/ETF 제외 등 수집 설정을 담은 ``CrawlConfig``.
        refresh: ``True`` 이면 기존 캐시를 무시하고 원격에서 새로 받는다.

    Returns:
        TOP-N 행을 가진 데이터프레임 (``ticker, name, market_cap, as_of``).
    """
    cfg.tickers_dir.mkdir(parents=True, exist_ok=True)
    out = cfg.market_tickers_file
    if not refresh and out.exists():
        cached = read_csv_or_none(out, dtype={"ticker": str})
        if cached is not None and "ticker" not in cached.columns:
            log.warning(
                "Ignoring ticker cache %s: missing 'ticker' column (found %s)",
                out,
                list(cached.columns),
            )
            cached = None
        if cached is not None and len(cached) >= cfg.top_n:
            return cached.head(cfg.top_n)

    if cfg.market is Market.kospi:
        df = fetch_kospi_top(cfg.top_n, exclude_etf=cfg.exclude_etf)
    else:
        df = fetch_nasdaq_top(cfg.top_n, exclude_etf=cfg.exclude_etf)
    df.to_csv(out, index=False)
    return df
