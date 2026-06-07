"""stock_analyzer.strategies 의 매매 신호 전략 단위 테스트."""

import pandas as pd
import pytest

from stock_analyzer.signals.strategies import (
    MIN_BARS,
    _insufficient,
    _last_float,
    _signal_from_score,
    bollinger_breakout,
    composite,
    ema_crossover,
    rsi_mean_reversion,
    run_strategy,
    volume_breakout,
)

# ---------- _signal_from_score ----------


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.5, "buy"),
        (0.2, "buy"),
        (0.19, "hold"),
        (0.0, "hold"),
        (-0.19, "hold"),
        (-0.2, "sell"),
        (-0.8, "sell"),
    ],
)
def test_signal_from_score(score, expected):
    assert _signal_from_score(score) == expected


def test_signal_from_score_custom_threshold():
    assert _signal_from_score(0.4, threshold=0.5) == "hold"
    assert _signal_from_score(0.5, threshold=0.5) == "buy"


# ---------- _last_float ----------


def test_last_float_empty_series_is_none():
    assert _last_float(pd.Series(dtype=float)) is None


def test_last_float_nan_is_none():
    assert _last_float(pd.Series([1.0, float("nan")])) is None


def test_last_float_returns_value():
    assert _last_float(pd.Series([1.0, 2.5])) == 2.5


# ---------- _insufficient ----------


def test_insufficient_defaults():
    r = _insufficient()
    assert r.signal == "hold"
    assert r.score == 0.0
    assert r.reasons == ["insufficient data"]


def test_insufficient_custom_reason():
    assert _insufficient("no data").reasons == ["no data"]


# ---------- rsi_mean_reversion ----------


def test_rsi_strategy_insufficient(make_ohlcv):
    r = rsi_mean_reversion(make_ohlcv([100] * 5))
    assert r.signal == "hold"
    assert r.reasons == ["insufficient data"]


def test_rsi_strategy_oversold_buys(make_ohlcv):
    r = rsi_mean_reversion(make_ohlcv(list(range(140, 100, -1))))
    assert r.signal == "buy"
    assert r.score > 0
    assert "rsi" in r.indicators


def test_rsi_strategy_overbought_sells(make_ohlcv):
    r = rsi_mean_reversion(make_ohlcv(list(range(100, 140))))
    assert r.signal == "sell"
    assert r.score < 0


def test_rsi_strategy_neutral_holds(make_ohlcv):
    r = rsi_mean_reversion(make_ohlcv([100, 101] * 20))
    assert r.signal == "hold"


def test_rsi_strategy_flat_series_holds(make_ohlcv):
    r = rsi_mean_reversion(make_ohlcv([100] * 30))
    assert r.signal == "hold"
    assert r.indicators["rsi"] == pytest.approx(50.0)


def test_composite_flat_series_does_not_signal_sell(make_ohlcv):
    r = composite(make_ohlcv([100] * 30))
    assert r.signal != "sell"


# ---------- ema_crossover ----------


def test_ema_strategy_insufficient(make_ohlcv):
    assert ema_crossover(make_ohlcv([100] * 21)).reasons == ["insufficient data"]


def test_ema_strategy_uptrend_buys(make_ohlcv):
    r = ema_crossover(make_ohlcv(list(range(100, 140))))
    assert r.score > 0
    assert r.signal == "buy"


def test_ema_strategy_downtrend_sells(make_ohlcv):
    r = ema_crossover(make_ohlcv(list(range(140, 100, -1))))
    assert r.score < 0
    assert r.signal == "sell"


def test_ema_strategy_detects_cross_above(make_ohlcv):
    r = ema_crossover(make_ohlcv([100] * 21 + [200]))
    assert r.score >= 0.8
    assert any("crossed above" in reason for reason in r.reasons)


def test_ema_strategy_detects_cross_below(make_ohlcv):
    r = ema_crossover(make_ohlcv([100] * 21 + [50]))
    assert r.score <= -0.8
    assert any("crossed below" in reason for reason in r.reasons)


# ---------- bollinger_breakout ----------


def test_bollinger_strategy_insufficient(make_ohlcv):
    assert bollinger_breakout(make_ohlcv([100] * 10)).reasons == ["insufficient data"]


def test_bollinger_strategy_flat_band_holds(make_ohlcv):
    r = bollinger_breakout(make_ohlcv([100] * 15))
    assert r.signal == "hold"
    assert r.reasons == ["flat bollinger band"]


def test_bollinger_strategy_lower_breakout_buys(make_ohlcv):
    r = bollinger_breakout(make_ohlcv([100] * 11 + [80]))
    assert r.signal == "buy"
    assert r.score > 0


def test_bollinger_strategy_upper_breakout_sells(make_ohlcv):
    r = bollinger_breakout(make_ohlcv([100] * 11 + [120]))
    assert r.signal == "sell"
    assert r.score < 0


# ---------- volume_breakout ----------


def test_volume_strategy_insufficient(make_ohlcv):
    assert volume_breakout(make_ohlcv([100] * 20)).reasons == ["insufficient data"]


def test_volume_strategy_spike_up_buys(make_ohlcv):
    df = make_ohlcv([100] * 21 + [105], volumes=[1000] * 21 + [5000])
    r = volume_breakout(df)
    assert r.signal == "buy"
    assert r.score > 0


def test_volume_strategy_spike_down_sells(make_ohlcv):
    df = make_ohlcv([100] * 21 + [95], volumes=[1000] * 21 + [5000])
    r = volume_breakout(df)
    assert r.signal == "sell"
    assert r.score < 0


def test_volume_strategy_no_spike_holds(make_ohlcv):
    r = volume_breakout(make_ohlcv([100] * 25, volumes=[1000] * 25))
    assert r.signal == "hold"


# ---------- composite ----------


def test_composite_insufficient(make_ohlcv):
    r = composite(make_ohlcv([100] * (MIN_BARS - 1)))
    assert r.signal == "hold"
    assert r.reasons == ["insufficient data"]


def test_composite_returns_valid_result(make_ohlcv):
    r = composite(make_ohlcv(list(range(100, 140))))
    assert r.signal in ("buy", "sell", "hold")
    assert -1.0 <= r.score <= 1.0
    assert "atr7" in r.indicators
    assert "roc5" in r.indicators
    assert "stop_loss" in r.indicators


def test_composite_score_is_average_of_parts(make_ohlcv):
    df = make_ohlcv(list(range(100, 140)))
    parts = [
        rsi_mean_reversion(df),
        ema_crossover(df),
        bollinger_breakout(df),
        volume_breakout(df),
    ]
    expected = sum(p.score for p in parts) / len(parts)
    assert composite(df).score == pytest.approx(expected)


# ---------- run_strategy ----------


def test_run_strategy_dispatches(make_ohlcv):
    df = make_ohlcv(list(range(100, 140)))
    assert run_strategy("rsi", df).signal in ("buy", "sell", "hold")
    assert run_strategy("composite", df) is not None


def test_run_strategy_unknown_name_raises(make_ohlcv):
    with pytest.raises(ValueError, match="Unknown strategy"):
        run_strategy("nope", make_ohlcv([100] * 30))
