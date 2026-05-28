"""티커 해석, 증분 시작일 계산, throttle, 재시도, 저장을 묶는 수집 오케스트레이터."""

import logging
import time
from datetime import date, timedelta
from typing import Any

import pandas as pd
from tqdm import tqdm

from .config import CrawlConfig
from .fetcher import fetch_history
from .storage import last_recorded_date, upsert
from .throttle import Throttler
from .tickers import resolve_tickers

log = logging.getLogger(__name__)


def _is_rate_limit_error(err: Exception) -> bool:
    """예외 메시지로 rate-limit(HTTP 429) 류 오류인지 판별한다.

    Args:
        err: 발생한 예외.

    Returns:
        '429', 'too many requests', 'rate limit' 가 포함되어 있으면 ``True``.
    """
    msg = str(err).lower()
    return "429" in msg or "too many requests" in msg or "rate limit" in msg


def _fetch_with_retry(
    cfg: CrawlConfig,
    throttler: Throttler,
    ticker: str,
    start: date | None,
) -> pd.DataFrame:
    """지수 백오프로 재시도하며 단일 종목의 OHLCV 를 받아온다.

    rate-limit 오류는 더 긴 백오프(``5 * 2^attempt``, 최대 120초)로,
    그 외 오류는 짧은 백오프(``2^attempt``, 최대 10초)로 대기한다.

    Args:
        cfg: 수집 설정 (재시도 횟수 등).
        throttler: 매 시도 직전에 ``wait()`` 를 호출할 throttle 인스턴스.
        ticker: 수집 대상 종목 코드.
        start: 수집 시작일. ``None`` 이면 전체 이력.

    Returns:
        ``fetch_history`` 가 반환하는 데이터프레임.

    Raises:
        RuntimeError: 모든 재시도가 실패했을 때, 마지막 예외를 메시지에 담아 발생.
    """
    last_err: Exception | None = None
    for attempt in range(1, cfg.max_retries + 1):
        throttler.wait()
        try:
            return fetch_history(cfg.market, ticker, start=start)
        except Exception as e:  # noqa: BLE001
            last_err = e
            if _is_rate_limit_error(e):
                backoff = min(2**attempt * 5, 120)
            else:
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
    """TOP-N 종목 전체에 대해 증분 OHLCV 수집을 수행한다.

    종목별로 디스크의 마지막 거래일 다음날부터 yfinance 호출 → 재시도 → 저장의
    파이프라인을 반복한다. 한 종목의 실패가 전체를 중단시키지 않으며 결과 요약을
    딕셔너리로 반환한다.

    Args:
        cfg: 수집 설정. ``market_data_dir`` 가 자동으로 생성된다.
        refresh_tickers: ``True`` 이면 TOP-N 티커 목록을 원격에서 다시 받는다.

    Returns:
        다음 키를 가진 요약 딕셔너리:

        - ``market``: 시장 문자열.
        - ``tickers``: 처리한 종목 수.
        - ``succeeded``: 성공한 종목 수.
        - ``failed``: 실패한 종목 수.
        - ``new_rows``: 새로 추가된 거래일 행 수의 합.
        - ``failures``: ``(ticker, error_message)`` 튜플의 리스트.
    """
    cfg.market_data_dir.mkdir(parents=True, exist_ok=True)
    universe = resolve_tickers(cfg, refresh=refresh_tickers)
    log.info(
        "Collecting %s top %d (resolved %d tickers) → %s",
        cfg.market.value.upper(),
        cfg.top_n,
        len(universe),
        cfg.market_data_dir,
    )

    throttler = Throttler(
        min_interval=cfg.request_delay,
        max_per_minute=cfg.max_per_minute,
        jitter=cfg.jitter,
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

        try:
            last = last_recorded_date(cfg.market_data_dir, ticker)
            start = (last + timedelta(days=1)) if last else None
            df = _fetch_with_retry(cfg, throttler, ticker, start)
            added = upsert(cfg.market_data_dir, ticker, df)
        except Exception as e:  # noqa: BLE001
            log.warning("Collection failed for %s: %s", ticker, e)
            failed.append((ticker, str(e)))
            continue

        new_rows += added
        succeeded += 1

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
