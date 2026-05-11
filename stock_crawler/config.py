"""크롤러 전역 설정과 경로 상수.

이 모듈은 수집 대상 시장(``Market``)과 수집 동작에 필요한 설정값
(``CrawlConfig``)을 정의한다. 데이터/티커/로그 디렉터리 경로도 함께 둔다.
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
TICKERS_DIR = DATA_DIR / "_tickers"
LOG_DIR = REPO_ROOT / "logs"


class Market(StrEnum):
    """수집 대상 시장."""

    kospi = "kospi"
    nasdaq = "nasdaq"


@dataclass(frozen=True)
class CrawlConfig:
    """수집 한 회 실행에 필요한 모든 설정값을 묶는 불변 데이터클래스.

    Attributes:
        market: 대상 시장 (``Market.kospi`` 또는 ``Market.nasdaq``).
        top_n: 시가총액 상위 몇 종목까지 수집할지.
        data_dir: 종목별 OHLCV CSV 가 저장될 루트 디렉터리.
        tickers_dir: TOP-N 티커 캐시 CSV 가 저장될 디렉터리.
        log_dir: 로그 파일 저장 디렉터리.
        request_delay: yfinance 호출 사이 최소 대기 시간(초).
        max_retries: 종목당 fetch 재시도 횟수 상한.
        max_per_minute: 60초 슬라이딩 윈도우 내 yfinance 호출 상한 (0 이면 비활성).
        jitter: throttle 대기 시간에 더해지는 랜덤 지터의 비율.
        exclude_etf: ``True`` 일 때 TOP-N 산정에서 ETF 종목을 제외한다.
    """

    market: Market
    top_n: int = 200
    data_dir: Path = DATA_DIR
    tickers_dir: Path = TICKERS_DIR
    log_dir: Path = LOG_DIR
    request_delay: float = 0.3
    max_retries: int = 3
    max_per_minute: int = 30
    jitter: float = 0.1
    exclude_etf: bool = False

    @property
    def market_data_dir(self) -> Path:
        """해당 시장의 종목별 CSV 가 저장되는 디렉터리."""
        return self.data_dir / self.market.value

    @property
    def market_tickers_file(self) -> Path:
        """TOP-N 티커 캐시 CSV 경로. ``exclude_etf`` 가 켜진 경우 ``_no_etf`` 접미사가 붙는다."""
        suffix = "_no_etf" if self.exclude_etf else ""
        return self.tickers_dir / f"{self.market.value}_top{self.top_n}{suffix}.csv"
