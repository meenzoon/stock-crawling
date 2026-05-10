from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from .indicators import atr, bollinger, ema, roc, rsi, volume_spike

Signal = Literal["buy", "sell", "hold"]

MIN_BARS = 25  # need at least this many rows to evaluate the short-term set


@dataclass(frozen=True)
class StrategyResult:
    signal: Signal
    score: float
    reasons: list[str] = field(default_factory=list)
    indicators: dict[str, float] = field(default_factory=dict)


def _signal_from_score(score: float, *, threshold: float = 0.2) -> Signal:
    if score >= threshold:
        return "buy"
    if score <= -threshold:
        return "sell"
    return "hold"


def _last_float(series: pd.Series) -> float | None:
    if series.empty:
        return None
    val = series.iloc[-1]
    if pd.isna(val):
        return None
    return float(val)


def _insufficient(reason: str = "insufficient data") -> StrategyResult:
    return StrategyResult(signal="hold", score=0.0, reasons=[reason])


def rsi_mean_reversion(
    df: pd.DataFrame,
    *,
    period: int = 7,
    oversold: float = 30.0,
    overbought: float = 70.0,
) -> StrategyResult:
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
    if name not in STRATEGIES:
        raise ValueError(f"Unknown strategy: {name!r} (choose from {list(STRATEGIES)})")
    return STRATEGIES[name](df)
