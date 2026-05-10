from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
TICKERS_DIR = DATA_DIR / "_tickers"
LOG_DIR = REPO_ROOT / "logs"


class Market(StrEnum):
    kospi = "kospi"
    nasdaq = "nasdaq"


@dataclass(frozen=True)
class CrawlConfig:
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
        return self.data_dir / self.market.value

    @property
    def market_tickers_file(self) -> Path:
        suffix = "_no_etf" if self.exclude_etf else ""
        return self.tickers_dir / f"{self.market.value}_top{self.top_n}{suffix}.csv"
