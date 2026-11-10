import numpy as np
import pandas as pd
import pytest

from src.indicators.technical import (
    add_all_indicators,
    calculate_ema,
    calculate_macd,
    calculate_rsi,
)


@pytest.fixture
def close_series() -> pd.Series:
    # Deterministic, non-trivial price series.
    rng = np.random.default_rng(seed=42)
    prices = 100 + np.cumsum(rng.normal(0, 1, size=200))
    return pd.Series(prices, name="close")


def test_calculate_ema_length_and_no_lookahead(close_series):
    ema = calculate_ema(close_series, period=20)
    assert len(ema) == len(close_series)
    # EMA at time t must not depend on future prices.
    truncated_ema = calculate_ema(close_series.iloc[:50], period=20)
    pd.testing.assert_series_equal(ema.iloc[:50], truncated_ema, check_names=False)


def test_calculate_ema_rejects_invalid_period(close_series):
    with pytest.raises(ValueError):
        calculate_ema(close_series, period=0)


def test_calculate_rsi_bounds(close_series):
    rsi = calculate_rsi(close_series, period=14)
    valid = rsi.dropna()
    assert (valid >= 0).all()
    assert (valid <= 100).all()


def test_calculate_rsi_all_gains_is_100():
    close = pd.Series(np.arange(1, 30, dtype=float))
    rsi = calculate_rsi(close, period=14)
    assert rsi.iloc[-1] == pytest.approx(100.0)


def test_calculate_macd_columns(close_series):
    macd_df = calculate_macd(close_series)
    assert list(macd_df.columns) == ["macd", "signal", "histogram"]
    assert len(macd_df) == len(close_series)
    pd.testing.assert_series_equal(
        macd_df["histogram"],
        macd_df["macd"] - macd_df["signal"],
        check_names=False,
    )


def test_add_all_indicators_adds_expected_columns(close_series):
    df = pd.DataFrame(
        {
            "open": close_series,
            "high": close_series + 1,
            "low": close_series - 1,
            "close": close_series,
            "volume": 1.0,
        }
    )
    result = add_all_indicators(df)
    expected_new_columns = {
        "ema_20",
        "ema_50",
        "rsi_14",
        "macd",
        "macd_signal",
        "macd_histogram",
    }
    assert expected_new_columns.issubset(result.columns)
    assert len(result) == len(df)
