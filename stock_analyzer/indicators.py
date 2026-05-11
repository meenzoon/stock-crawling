"""단기 매매 신호 계산에 사용되는 기술적 지표 모음.

모든 함수는 입력 시리즈와 동일한 길이의 시리즈를 반환하며, 누적 윈도우가 채워지지
않은 앞부분은 ``NaN`` 으로 채운다(``min_periods=period``).
"""

import pandas as pd


def ema(close: pd.Series, period: int) -> pd.Series:
    """지수 가중 이동평균(EMA).

    Args:
        close: 종가 시리즈.
        period: EMA span(주기). 첫 ``period`` 개 값은 ``NaN``.

    Returns:
        입력과 동일한 인덱스의 EMA 시리즈.
    """
    return close.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(close: pd.Series, period: int = 7) -> pd.Series:
    """Wilder 공식의 RSI(상대강도지수).

    상승/하락분의 EMA 비율을 사용하며, 손실 EMA 가 0 인 구간(=무손실 구간)은 100 으로
    클램프한다.

    Args:
        close: 종가 시리즈.
        period: RSI 평균 윈도우 길이 (기본값 7, 단기 매매에 적합).

    Returns:
        0~100 범위의 RSI 시리즈.
    """
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, pd.NA)
    out = 100.0 - (100.0 / (1.0 + rs))
    return out.fillna(100.0).where(avg_loss != 0, 100.0)


def bollinger(
    close: pd.Series,
    period: int = 10,
    n_std: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """볼린저 밴드(중앙선/상단/하단).

    Args:
        close: 종가 시리즈.
        period: 이동평균 윈도우.
        n_std: 표준편차 배수 (밴드 폭을 결정).

    Returns:
        ``(중앙선, 상단, 하단)`` 시리즈 튜플.
    """
    mid = close.rolling(period, min_periods=period).mean()
    std = close.rolling(period, min_periods=period).std(ddof=0)
    upper = mid + n_std * std
    lower = mid - n_std * std
    return mid, upper, lower


def atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 7,
) -> pd.Series:
    """Average True Range — 변동성 측정 지표.

    True Range 는 ``max(high-low, |high-prev_close|, |low-prev_close|)`` 로
    정의되며, 그 EMA 가 ATR 이다.

    Args:
        high: 고가 시리즈.
        low: 저가 시리즈.
        close: 종가 시리즈.
        period: ATR 평균 윈도우 (기본값 7).

    Returns:
        ATR 시리즈.
    """
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def roc(close: pd.Series, period: int = 5) -> pd.Series:
    """Rate of Change — N일 전 대비 종가 변화율(%).

    Args:
        close: 종가 시리즈.
        period: 비교할 과거 거래일 간격.

    Returns:
        ``(close / close.shift(period) - 1) * 100`` 시리즈.
    """
    return (close / close.shift(period) - 1.0) * 100.0


def volume_spike(volume: pd.Series, ma_period: int = 20) -> pd.Series:
    """현재 거래량 / ``ma_period`` 일 이동평균 거래량의 비율.

    Args:
        volume: 거래량 시리즈.
        ma_period: 이동평균 윈도우 (기본값 20).

    Returns:
        비율 시리즈. 이동평균이 0 인 구간은 ``NaN``.
    """
    ma = volume.rolling(ma_period, min_periods=ma_period).mean()
    return volume / ma.replace(0.0, pd.NA)
