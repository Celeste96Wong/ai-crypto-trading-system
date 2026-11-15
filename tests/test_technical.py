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


def test_calculate_rsi_all_losses_is_0():
    close = pd.Series(np.arange(30, 1, -1, dtype=float))
    rsi = calculate_rsi(close, period=14)
    assert rsi.iloc[-1] == pytest.approx(0.0)


def test_calculate_rsi_no_movement_is_neutral_50():
    # Flat price: no gains and no losses at all, so avg_gain and
    # avg_loss are both 0. The plain RSI formula is 0/0 here; this
    # must resolve to the neutral value 50, not 100.
    close = pd.Series([100.0] * 20)
    rsi = calculate_rsi(close, period=14)
    assert rsi.iloc[-1] == pytest.approx(50.0)


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


# --- Deterministic, hand-calculated numerical checks ---
#
# These use small, non-default periods on short price series so the
# expected values below can be verified by hand with the standard
# recursive EMA definition: y[0] = x[0]; y[t] = alpha*x[t] + (1-alpha)*y[t-1],
# where alpha = 2 / (period + 1).


def test_calculate_ema_matches_hand_calculated_values():
    # close = [10, 11, 12, 11, 13], period=3 -> alpha = 2/4 = 0.5
    # y0 = 10
    # y1 = 0.5*10 + 0.5*11 = 10.5
    # y2 = 0.5*10.5 + 0.5*12 = 11.25
    # y3 = 0.5*11.25 + 0.5*11 = 11.125
    # y4 = 0.5*11.125 + 0.5*13 = 12.0625
    close = pd.Series([10.0, 11.0, 12.0, 11.0, 13.0])
    expected = [10.0, 10.5, 11.25, 11.125, 12.0625]

    ema = calculate_ema(close, period=3)

    assert ema.tolist() == pytest.approx(expected, abs=1e-9)


def test_calculate_rsi_matches_hand_calculated_values():
    # close = [10, 12, 11, 14], period=2 -> alpha = 1/2 = 0.5
    # delta = [nan, 2, -1, 3]; gain = [nan, 2, 0, 3]; loss = [nan, 0, 1, 0]
    # The EWM recursion skips the leading NaN and seeds at the first
    # valid observation (index 1):
    #   avg_gain: 2 -> 0.5*0 + 0.5*2 = 1.0 -> 0.5*3 + 0.5*1.0 = 2.0
    #   avg_loss: 0 -> 0.5*1 + 0.5*0 = 0.5 -> 0.5*0 + 0.5*0.5 = 0.25
    # min_periods=2 masks index 0 and 1 (fewer than 2 valid observations
    # seen yet); values become valid from index 2:
    #   rsi[2] = 100 - 100/(1 + 1.0/0.5) = 100 - 100/3    = 66.666...
    #   rsi[3] = 100 - 100/(1 + 2.0/0.25) = 100 - 100/9   = 88.888...
    close = pd.Series([10.0, 12.0, 11.0, 14.0])

    rsi = calculate_rsi(close, period=2)

    assert rsi.iloc[0:2].isna().all()
    assert rsi.iloc[2] == pytest.approx(66.66666666666667, abs=1e-6)
    assert rsi.iloc[3] == pytest.approx(88.88888888888889, abs=1e-6)


def test_calculate_macd_matches_hand_calculated_values():
    # close = [10, 11, 12, 13, 12, 14], fast=2, slow=4, signal=2
    # alpha_fast = 2/3, alpha_slow = 2/5, alpha_signal = 2/3
    #
    # EMA_fast: 10, 10.6667, 11.5556, 12.5185, 12.1728, 13.3909
    # EMA_slow: 10, 10.4,    11.04,   11.824,  11.8944, 12.73664
    # macd = EMA_fast - EMA_slow:
    #   0, 0.26667, 0.51556, 0.69452, 0.27844, 0.65431
    # signal = EMA(macd, alpha=2/3), seeded at macd[0] = 0:
    #   0, 0.17778, 0.40296, 0.59733, 0.38474, 0.56445
    # histogram = macd - signal
    close = pd.Series([10.0, 11.0, 12.0, 13.0, 12.0, 14.0])

    macd_df = calculate_macd(close, fast_period=2, slow_period=4, signal_period=2)

    expected_macd = [0.0, 0.266666667, 0.515555556, 0.694518519, 0.278439506, 0.654306502]
    expected_signal = [0.0, 0.177777778, 0.402962963, 0.597333333, 0.384737449, 0.564450151]
    expected_histogram = [m - s for m, s in zip(expected_macd, expected_signal)]

    assert macd_df["macd"].tolist() == pytest.approx(expected_macd, abs=1e-6)
    assert macd_df["signal"].tolist() == pytest.approx(expected_signal, abs=1e-6)
    assert macd_df["histogram"].tolist() == pytest.approx(expected_histogram, abs=1e-6)
