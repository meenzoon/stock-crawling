"""종목별 OHLCV CSV 파일의 경로 계산, 마지막 일자 조회, 신규 데이터 병합 유틸."""

import logging
from datetime import date
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)


def csv_path(market_dir: Path, ticker: str) -> Path:
    """종목 CSV 파일 경로를 계산한다.

    파일명에 사용할 수 없는 슬래시는 언더스코어로 치환한다.

    Args:
        market_dir: 해당 시장의 OHLCV 디렉터리 (예: ``data/kospi``).
        ticker: 종목 코드 (KOSPI 6자리, NASDAQ 알파벳 심볼).

    Returns:
        ``{market_dir}/{ticker}.csv`` 형태의 절대/상대 경로.
    """
    safe = ticker.replace("/", "_").replace("\\", "_")
    return market_dir / f"{safe}.csv"


def last_recorded_date(market_dir: Path, ticker: str) -> date | None:
    """저장된 종목 CSV 의 마지막 거래일을 반환한다.

    파일이 없거나 읽을 수 없으면 ``None`` 을 반환한다.
    호출자는 다음 수집 시작일을 결정할 때 이 값을 사용한다.

    Args:
        market_dir: 해당 시장의 OHLCV 디렉터리.
        ticker: 종목 코드.

    Returns:
        파일이 존재하고 데이터가 있으면 마지막 ``date``, 그 외에는 ``None``.
    """
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
    """신규 OHLCV 데이터를 종목 CSV 에 병합(upsert)한다.

    같은 거래일이 중복되면 ``new_df`` 쪽 값으로 덮어쓰며, 결과는 날짜 오름차순으로
    정렬되어 다시 저장된다. 디렉터리는 필요 시 자동 생성한다.

    Args:
        market_dir: 해당 시장의 OHLCV 디렉터리.
        ticker: 종목 코드.
        new_df: 거래일을 인덱스(``DatetimeIndex``, name='date')로 가진 데이터프레임.
            인덱스가 'date' 컬럼으로 들어와도 무방하다.

    Returns:
        디스크에 새로 추가된 거래일 행 수. 빈 입력이면 ``0``.
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
