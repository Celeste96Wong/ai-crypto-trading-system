"""Technical indicator calculations: EMA, RSI and MACD.

All functions take a pandas Series/DataFrame of OHLCV data and return
pandas Series aligned to the same index, so results can be attached
directly as new DataFrame columns.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import (
    EMA_LONG_PERIOD,
    EMA_SHORT_PERIOD,
    MACD_FAST_PERIOD,
    MACD_SIGNAL_PERIOD,
    MACD_SLOW_PERIOD,
    RSI_PERIOD,
)


def calculate_ema(close: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average over the given period."""
    if period <= 0:
        raise ValueError("period must be a positive integer")
    return close.ewm(span=period, adjust=False).mean()


def calculate_rsi(close: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    """Relative Strength Index (Wilder's smoothing) over the given period."""
    if period <= 0:
        raise ValueError("period must be a positive integer")

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    # avg_gain / avg_loss is 0/0 or x/0 whenever there has been no loss
    # (or no gain) at all, which the plain formula below can't express.
    # Handle those edge cases explicitly instead of dividing by zero:
    #   - no gain and no loss at all -> neutral (50)
    #   - gains but zero loss        -> maximally strong (100)
    #   - losses but zero gain       -> maximally weak (0)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

    no_movement = (avg_gain == 0) & (avg_loss == 0)
    gains_only = (avg_gain > 0) & (avg_loss == 0)
    losses_only = (avg_gain == 0) & (avg_loss > 0)

    rsi = rsi.mask(no_movement, 50.0)
    rsi = rsi.mask(gains_only, 100.0)
    rsi = rsi.mask(losses_only, 0.0)
    return rsi


def calculate_macd(
    close: pd.Series,
    fast_period: int = MACD_FAST_PERIOD,
    slow_period: int = MACD_SLOW_PERIOD,
    signal_period: int = MACD_SIGNAL_PERIOD,
) -> pd.DataFrame:
    """Moving Average Convergence Divergence.

    Returns a DataFrame with columns: macd, signal, histogram.
    """
    ema_fast = calculate_ema(close, fast_period)
    ema_slow = calculate_ema(close, slow_period)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal_period)
    histogram = macd_line - signal_line

    return pd.DataFrame(
        {"macd": macd_line, "signal": signal_line, "histogram": histogram}
    )


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of df with EMA20, EMA50, RSI14 and MACD columns added."""
    result = df.copy()
    result["ema_20"] = calculate_ema(result["close"], EMA_SHORT_PERIOD)
    result["ema_50"] = calculate_ema(result["close"], EMA_LONG_PERIOD)
    result["rsi_14"] = calculate_rsi(result["close"], RSI_PERIOD)

    macd_df = calculate_macd(result["close"])
    result["macd"] = macd_df["macd"]
    result["macd_signal"] = macd_df["signal"]
    result["macd_histogram"] = macd_df["histogram"]

    return result
