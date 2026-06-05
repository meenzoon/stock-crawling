"""단기(1일~1주일) 매매 신호를 생성하는 전략 함수 모음.

각 전략은 ``StrategyResult`` 를 반환하며 ``signal`` (buy/sell/hold), ``score``
(-1~+1 의 신호 강도), ``reasons`` (사람이 읽을 설명), ``indicators`` (보조 수치)를
담는다. ``composite`` 전략은 나머지 4개 전략의 평균 점수를 사용한다.
"""

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from .indicators import atr, bollinger, ema, roc, rsi, volume_spike

Signal = Literal["buy", "sell", "hold"]

MIN_BARS = 25  # 단기 지표 셋을 평가하기 위한 최소 행 수


@dataclass(frozen=True)
class StrategyResult:
    """전략 실행 결과를 묶는 불변 데이터클래스.

    Attributes:
        signal: ``"buy" | "sell" | "hold"``.
        score: -1.0 ~ +1.0 사이 신호 강도. 절대값이 클수록 강한 신호.
        reasons: 사람이 읽을 수 있는 신호 사유 리스트.
        indicators: 결과에 기여한 보조 지표 값들.
    """

    signal: Signal
    score: float
    reasons: list[str] = field(default_factory=list)
    indicators: dict[str, float] = field(default_factory=dict)


def _signal_from_score(score: float, *, threshold: float = 0.2) -> Signal:
    """점수를 임계값과 비교해 buy/sell/hold 시그널로 변환한다.

    Args:
        score: 전략 점수 (-1 ~ +1 권장).
        threshold: 매수/매도로 인정할 절대값 임계.

    Returns:
        ``"buy"`` / ``"sell"`` / ``"hold"`` 중 하나.
    """
    if score >= threshold:
        return "buy"
    if score <= -threshold:
        return "sell"
    return "hold"


def _last_float(series: pd.Series) -> float | None:
    """시리즈의 마지막 값을 ``float`` 으로 반환한다. 비어있거나 ``NaN`` 이면 ``None``."""
    if series.empty:
        return None
    val = series.iloc[-1]
    if pd.isna(val):
        return None
    return float(val)


def _insufficient(reason: str = "insufficient data") -> StrategyResult:
    """데이터 부족 시 반환할 hold 결과를 생성한다.

    Args:
        reason: ``reasons`` 에 들어갈 설명 문자열.

    Returns:
        ``hold`` / ``score=0`` / 주어진 사유 한 줄로 구성된 결과.
    """
    return StrategyResult(signal="hold", score=0.0, reasons=[reason])


def rsi_mean_reversion(
    df: pd.DataFrame,
    *,
    period: int = 7,
    oversold: float = 30.0,
    overbought: float = 70.0,
) -> StrategyResult:
    """RSI 기반 평균회귀 전략. 과매도→매수, 과매수→매도.

    Args:
        df: ``close`` 컬럼을 포함하는 OHLCV 데이터프레임.
        period: RSI 평균 윈도우.
        oversold: 매수 트리거가 되는 RSI 하한.
        overbought: 매도 트리거가 되는 RSI 상한.

    Returns:
        RSI 마지막 값에 따른 신호. 데이터가 부족하면 ``_insufficient()``.
    """
    if len(df) < period + 1:
        return _insufficient()
    rsi_series = rsi(df["close"], period=period)
    val = _last_float(rsi_series)
    if val is None:
        return _insufficient()

    if val <= oversold:
        score = min(1.0, (oversold - val) / oversold)
        return StrategyResult(
            signal="buy",
            score=score,
            reasons=[f"RSI({period})={val:.1f} <= {oversold}"],
            indicators={"rsi": val},
        )
    if val >= overbought:
        score = -min(1.0, (val - overbought) / (100.0 - overbought))
        return StrategyResult(
            signal="sell",
            score=score,
            reasons=[f"RSI({period})={val:.1f} >= {overbought}"],
            indicators={"rsi": val},
        )
    midpoint = (oversold + overbought) / 2.0
    score = (midpoint - val) / (midpoint - oversold)
    score = max(-1.0, min(1.0, score))
    return StrategyResult(
        signal="hold",
        score=score * 0.3,
        reasons=[f"RSI({period})={val:.1f} neutral"],
        indicators={"rsi": val},
    )


def ema_crossover(
    df: pd.DataFrame,
    *,
    fast_period: int = 5,
    slow_period: int = 20,
) -> StrategyResult:
    """단기 EMA / 장기 EMA 의 교차/스프레드를 사용하는 추세 전략.

    Args:
        df: ``close`` 컬럼을 포함하는 OHLCV 데이터프레임.
        fast_period: 단기 EMA 주기.
        slow_period: 장기 EMA 주기 (단기보다 커야 의미 있음).

    Returns:
        직전 봉에서 교차가 일어났다면 강한 신호(±0.8 이상), 그 외에는 스프레드 비율을
        20배 스케일링한 점수를 갖는 결과.
    """
    if len(df) < slow_period + 2:
        return _insufficient()
    fast = ema(df["close"], period=fast_period)
    slow = ema(df["close"], period=slow_period)
    f_now, s_now = _last_float(fast), _last_float(slow)
    if f_now is None or s_now is None:
        return _insufficient()
    f_prev = float(fast.iloc[-2]) if not pd.isna(fast.iloc[-2]) else None
    s_prev = float(slow.iloc[-2]) if not pd.isna(slow.iloc[-2]) else None

    spread = (f_now - s_now) / s_now
    score = max(-1.0, min(1.0, spread * 20.0))

    reasons: list[str] = []
    if f_prev is not None and s_prev is not None:
        if f_prev <= s_prev and f_now > s_now:
            score = max(score, 0.8)
            reasons.append(f"EMA({fast_period}) crossed above EMA({slow_period})")
        elif f_prev >= s_prev and f_now < s_now:
            score = min(score, -0.8)
            reasons.append(f"EMA({fast_period}) crossed below EMA({slow_period})")

    if not reasons:
        direction = "above" if f_now > s_now else "below"
        reasons.append(f"EMA({fast_period}) {direction} EMA({slow_period}) (spread={spread:.2%})")

    return StrategyResult(
        signal=_signal_from_score(score),
        score=score,
        reasons=reasons,
        indicators={"ema_fast": f_now, "ema_slow": s_now},
    )


def bollinger_breakout(
    df: pd.DataFrame,
    *,
    period: int = 10,
    n_std: float = 2.0,
) -> StrategyResult:
    """볼린저 밴드 상/하단 돌파 전략 (하단 이탈→매수, 상단 돌파→매도).

    Args:
        df: ``close`` 컬럼을 포함하는 OHLCV 데이터프레임.
        period: 밴드 이동평균 윈도우.
        n_std: 밴드 폭을 결정하는 표준편차 배수.

    Returns:
        밴드 폭이 0 이거나 데이터가 부족하면 ``_insufficient()``, 그 외엔 종가의 밴드
        위치에 따른 결과.
    """
    if len(df) < period + 1:
        return _insufficient()
    mid, upper, lower = bollinger(df["close"], period=period, n_std=n_std)
    close_now = _last_float(df["close"])
    upper_now = _last_float(upper)
    lower_now = _last_float(lower)
    mid_now = _last_float(mid)
    if any(v is None for v in (close_now, upper_now, lower_now, mid_now)):
        return _insufficient()

    band_width = upper_now - lower_now
    if band_width <= 0:
        return _insufficient("flat bollinger band")

    if close_now <= lower_now:
        score = min(1.0, (lower_now - close_now) / band_width + 0.5)
        return StrategyResult(
            signal="buy",
            score=score,
            reasons=[f"Close={close_now:.2f} below lower band={lower_now:.2f}"],
            indicators={"bb_upper": upper_now, "bb_lower": lower_now, "bb_mid": mid_now},
        )
    if close_now >= upper_now:
        score = -min(1.0, (close_now - upper_now) / band_width + 0.5)
        return StrategyResult(
            signal="sell",
            score=score,
            reasons=[f"Close={close_now:.2f} above upper band={upper_now:.2f}"],
            indicators={"bb_upper": upper_now, "bb_lower": lower_now, "bb_mid": mid_now},
        )
    pct_b = (close_now - lower_now) / band_width
    score = (0.5 - pct_b) * 0.6
    return StrategyResult(
        signal=_signal_from_score(score),
        score=score,
        reasons=[f"%B={pct_b:.2f} inside band"],
        indicators={"bb_upper": upper_now, "bb_lower": lower_now, "bb_mid": mid_now},
    )


def volume_breakout(
    df: pd.DataFrame,
    *,
    ma_period: int = 20,
    spike_threshold: float = 2.0,
) -> StrategyResult:
    """거래량 스파이크와 당일 종가 변화율을 결합한 돌파 전략.

    Args:
        df: ``close``, ``volume`` 컬럼을 포함하는 OHLCV 데이터프레임.
        ma_period: 거래량 이동평균 윈도우.
        spike_threshold: 스파이크로 인정할 ``volume / MA`` 비율 하한.

    Returns:
        스파이크 + 양봉이면 매수, 스파이크 + 음봉이면 매도, 그 외엔 hold.
    """
    if len(df) < ma_period + 1:
        return _insufficient()
    ratio_series = volume_spike(df["volume"], ma_period=ma_period)
    roc1_series = roc(df["close"], period=1)
    ratio = _last_float(ratio_series)
    roc1 = _last_float(roc1_series)
    if ratio is None or roc1 is None:
        return _insufficient()

    if ratio >= spike_threshold and roc1 > 0:
        score = min(1.0, (ratio - spike_threshold) / spike_threshold + 0.5)
        return StrategyResult(
            signal="buy",
            score=score,
            reasons=[f"Volume {ratio:.1f}x MA({ma_period}) with +{roc1:.2f}% close"],
            indicators={"volume_ratio": ratio, "roc1": roc1},
        )
    if ratio >= spike_threshold and roc1 < 0:
        score = -min(1.0, (ratio - spike_threshold) / spike_threshold + 0.5)
        return StrategyResult(
            signal="sell",
            score=score,
            reasons=[f"Volume {ratio:.1f}x MA({ma_period}) with {roc1:.2f}% close"],
            indicators={"volume_ratio": ratio, "roc1": roc1},
        )
    return StrategyResult(
        signal="hold",
        score=0.0,
        reasons=[f"Volume {ratio:.2f}x MA({ma_period}) (no spike)"],
        indicators={"volume_ratio": ratio, "roc1": roc1},
    )


def composite(df: pd.DataFrame) -> StrategyResult:
    """4개 단일 전략의 평균 점수를 사용하는 합성 전략.

    데이터 부족으로 ``_insufficient`` 가 된 부분 결과는 평균에서 제외하고, ATR/ROC
    같은 보조 지표(손절가 추정용)를 indicators 에 추가한다.

    Args:
        df: ``high/low/close/volume`` 컬럼을 포함한 OHLCV 데이터프레임.
            평가에 필요한 최소 행 수는 ``MIN_BARS`` 이다.

    Returns:
        평균 점수에서 도출된 신호와 모든 부분 전략의 사유/지표를 합친 결과.
    """
    if len(df) < MIN_BARS:
        return _insufficient()

    parts = [
        rsi_mean_reversion(df),
        ema_crossover(df),
        bollinger_breakout(df),
        volume_breakout(df),
    ]
    valid = [r for r in parts if not (r.signal == "hold" and r.reasons == ["insufficient data"])]
    if not valid:
        return _insufficient()

    avg_score = sum(r.score for r in valid) / len(valid)
    reasons: list[str] = []
    indicators: dict[str, float] = {}
    for r in valid:
        reasons.extend(r.reasons)
        indicators.update(r.indicators)

    atr7 = _last_float(atr(df["high"], df["low"], df["close"], period=7))
    roc5 = _last_float(roc(df["close"], period=5))
    close_now = _last_float(df["close"])
    if atr7 is not None:
        indicators["atr7"] = atr7
        if close_now is not None:
            indicators["stop_loss"] = close_now - 1.5 * atr7
    if roc5 is not None:
        indicators["roc5"] = roc5

    return StrategyResult(
        signal=_signal_from_score(avg_score),
        score=avg_score,
        reasons=reasons,
        indicators=indicators,
    )


STRATEGIES = {
    "rsi": rsi_mean_reversion,
    "ema": ema_crossover,
    "bollinger": bollinger_breakout,
    "volume": volume_breakout,
    "composite": composite,
}


def run_strategy(name: str, df: pd.DataFrame) -> StrategyResult:
    """이름으로 전략을 조회해 실행한다.

    Args:
        name: ``STRATEGIES`` 키 중 하나 (rsi/ema/bollinger/volume/composite).
        df: 전략 함수에 그대로 전달될 OHLCV 데이터프레임.

    Returns:
        해당 전략의 ``StrategyResult``.

    Raises:
        ValueError: 알 수 없는 전략 이름이 주어진 경우.
    """
    if name not in STRATEGIES:
        raise ValueError(f"Unknown strategy: {name!r} (choose from {list(STRATEGIES)})")
    return STRATEGIES[name](df)
