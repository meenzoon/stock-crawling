"""stock_analyzer.indicators 의 기술적 지표 함수 단위 테스트."""

import pandas as pd
import pytest

from stock_analyzer.indicators import atr, bollinger, ema, roc, rsi, volume_spike


def s(values):
    """숫자 리스트를 float Series 로 변환한다."""
    return pd.Series([float(v) for v in values])


# ---------- ema ----------


def test_ema_length_and_warmup():
    out = ema(s(range(10)), period=3)
    assert len(out) == 10
    assert out.iloc[:2].isna().all()
    assert out.iloc[2:].notna().all()


def test_ema_period_one_equals_input():
    close = s([1, 2, 3, 4, 5])
    pd.testing.assert_series_equal(ema(close, 1), close, check_names=False)


def test_ema_constant_series_stays_constant():
    out = ema(s([7] * 20), period=5)
    assert out.dropna().eq(7.0).all()


# ---------- rsi ----------


def test_rsi_uptrend_post_warmup_is_100():
    period = 7
    out = rsi(s(range(1, 40)), period=period)
    assert out.iloc[period:].eq(100.0).all()


def test_rsi_downtrend_post_warmup_is_0():
    period = 7
    out = rsi(s(range(40, 1, -1)), period=period)
    assert out.iloc[period:].eq(0.0).all()


def test_rsi_stays_within_bounds():
    close = s([100, 101, 100, 102, 101, 103, 99, 104, 98, 105] * 4)
    out = rsi(close, period=7).dropna()
    assert (out >= 0).all()
    assert (out <= 100).all()


def test_rsi_length_preserved():
    close = s(range(1, 30))
    assert len(rsi(close, period=7)) == len(close)


# ---------- bollinger ----------


def test_bollinger_returns_three_aligned_series():
    close = s(range(30))
    mid, upper, lower = bollinger(close, period=10, n_std=2.0)
    assert len(mid) == len(upper) == len(lower) == 30


def test_bollinger_band_ordering():
    close = s([10, 12, 11, 13, 9, 14, 8, 15, 7, 16, 6, 17, 5])
    mid, upper, lower = bollinger(close, period=5, n_std=2.0)
    valid = mid.notna()
    assert (upper[valid] >= mid[valid]).all()
    assert (mid[valid] >= lower[valid]).all()


def test_bollinger_mid_is_rolling_mean():
    close = s(range(20))
    mid, _upper, _lower = bollinger(close, period=5)
    expected = close.rolling(5, min_periods=5).mean()
    pd.testing.assert_series_equal(mid, expected)


def test_bollinger_constant_series_has_zero_width():
    close = s([5] * 20)
    mid, upper, lower = bollinger(close, period=5, n_std=2.0)
    valid = mid.notna()
    assert (upper[valid] == mid[valid]).all()
    assert (lower[valid] == mid[valid]).all()


def test_bollinger_width_matches_std():
    close = s([10, 12, 11, 13, 9, 14, 8, 15, 7, 16, 6, 17, 5, 18])
    _mid, upper, lower = bollinger(close, period=5, n_std=2.0)
    std = close.rolling(5, min_periods=5).std(ddof=0)
    pd.testing.assert_series_equal(upper - lower, 4.0 * std, check_names=False)


# ---------- atr ----------


def test_atr_length_and_warmup():
    n = 20
    high = s([10 + i for i in range(n)])
    low = s([8 + i for i in range(n)])
    close = s([9 + i for i in range(n)])
    out = atr(high, low, close, period=7)
    assert len(out) == n
    assert out.iloc[:6].isna().all()
    assert out.iloc[6:].notna().all()


def test_atr_is_non_negative():
    high = s([10, 12, 11, 13, 9, 14, 8, 15, 7, 16, 6, 17, 5, 18, 4, 19])
    low = s([8, 9, 8, 10, 6, 11, 5, 12, 4, 13, 3, 14, 2, 15, 1, 16])
    close = s([9, 11, 9, 12, 7, 13, 6, 14, 5, 15, 4, 16, 3, 17, 2, 18])
    out = atr(high, low, close, period=5).dropna()
    assert (out >= 0).all()


def test_atr_constant_bars_is_zero():
    flat = s([10] * 20)
    out = atr(flat, flat, flat, period=7)
    assert out.iloc[7:].eq(0.0).all()


# ---------- roc ----------


def test_roc_constant_series_is_zero():
    out = roc(s([5] * 10), period=3)
    assert out.iloc[3:].eq(0.0).all()


def test_roc_doubling_is_100_percent():
    out = roc(s([1, 1, 1, 2, 2, 2, 4, 4, 4]), period=3)
    assert out.iloc[3] == pytest.approx(100.0)
    assert out.iloc[6] == pytest.approx(100.0)


def test_roc_warmup_is_nan():
    out = roc(s(range(1, 10)), period=3)
    assert out.iloc[:3].isna().all()


# ---------- volume_spike ----------


def test_volume_spike_constant_volume_is_one():
    out = volume_spike(s([1000] * 30), ma_period=20)
    assert out.iloc[19:].eq(1.0).all()


def test_volume_spike_detects_spike_ratio():
    out = volume_spike(s([1000] * 20 + [5000]), ma_period=20)
    # 마지막 봉: 20일 MA = (19*1000 + 5000)/20 = 1200, 비율 = 5000/1200
    assert out.iloc[-1] == pytest.approx(5000 / 1200)


def test_volume_spike_zero_ma_is_nan():
    out = volume_spike(s([0] * 30), ma_period=20)
    assert out.iloc[19:].isna().all()


def test_volume_spike_warmup_is_nan():
    out = volume_spike(s([1000] * 30), ma_period=20)
    assert out.iloc[:19].isna().all()
