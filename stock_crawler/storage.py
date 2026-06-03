"""종목별 OHLCV CSV 파일의 경로 계산, 마지막 일자 조회, 신규 데이터 병합 유틸."""

import logging
from datetime import date
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)


def read_csv_or_none(path: Path, **kwargs: object) -> pd.DataFrame | None:
    """CSV 를 읽되 읽기/파싱이 실패하면 경고 후 ``None`` 을 반환한다.

    빈 파일(``EmptyDataError``)·잘린/파싱 불가 CSV(``ParserError``) 등 손상된
    파일을 호출자가 일관되게 방어할 수 있도록 예외를 삼킨다. 호출자는 ``None`` 을
    "데이터 없음/재수집 대상" 으로 해석한다.

    Args:
        path: 읽을 CSV 경로 (존재 여부는 호출자가 보장).
        **kwargs: ``pandas.read_csv`` 에 그대로 전달되는 인자.

    Returns:
        성공 시 데이터프레임, 읽기/파싱 실패 시 ``None``.
    """
    try:
        return pd.read_csv(path, **kwargs)
    except Exception as e:  # noqa: BLE001
        log.warning("Could not read %s: %s", path, e)
        return None


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
    df = read_csv_or_none(p, usecols=["date"], parse_dates=["date"])
    if df is None or df.empty:
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

    Raises:
        ValueError: ``new_df`` 에 ``date`` 컬럼이나 ``DatetimeIndex`` 가 없어
            거래일을 식별할 수 없을 때.
    """
    if new_df is None or new_df.empty:
        return 0
    market_dir.mkdir(parents=True, exist_ok=True)
    p = csv_path(market_dir, ticker)

    incoming = new_df.copy()
    if isinstance(incoming.index, pd.DatetimeIndex):
        if incoming.index.name is None:
            incoming.index = incoming.index.rename("date")
        incoming = incoming.reset_index()
    elif incoming.index.name == "date":
        incoming = incoming.reset_index()

    if "date" not in incoming.columns:
        raise ValueError(
            f"Cannot upsert {ticker}: 'date' column not found (columns: {list(incoming.columns)})"
        )
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
