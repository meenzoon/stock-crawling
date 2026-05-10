import pandas as pd


def ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(close: pd.Series, period: int = 7) -> pd.Series:
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
    """Rate of change in percent over `period` days."""
    return (close / close.shift(period) - 1.0) * 100.0


def volume_spike(volume: pd.Series, ma_period: int = 20) -> pd.Series:
    """Ratio of current volume to its `ma_period`-day moving average."""
    ma = volume.rolling(ma_period, min_periods=ma_period).mean()
    return volume / ma.replace(0.0, pd.NA)
