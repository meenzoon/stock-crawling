"""테스트 전역에서 쓰는 fixture 모음."""

import pandas as pd
import pytest


@pytest.fixture
def make_ohlcv():
    """종가 리스트로 일봉 OHLCV 데이터프레임을 만드는 팩토리 fixture.

    high/low/volume 을 지정하지 않으면 종가 기준으로 합리적인 기본값을 채운다.
    인덱스는 ``date`` 이름의 일별 ``DatetimeIndex`` 이다.
    """

    def _make(closes, *, highs=None, lows=None, volumes=None, start="2024-01-01"):
        closes = [float(c) for c in closes]
        n = len(closes)
        idx = pd.date_range(start, periods=n, freq="D", name="date")
        highs = [float(h) for h in highs] if highs is not None else [c * 1.01 for c in closes]
        lows = [float(low) for low in lows] if lows is not None else [c * 0.99 for c in closes]
        volumes = list(volumes) if volumes is not None else [1000] * n
        return pd.DataFrame(
            {"open": closes, "high": highs, "low": lows, "close": closes, "volume": volumes},
            index=idx,
        )

    return _make
