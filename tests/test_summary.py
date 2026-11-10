import pandas as pd
import pytest

from src.analysis.summary import generate_summary


def _make_df(close, ema_20, ema_50, rsi_14, macd, macd_signal):
    return pd.DataFrame(
        {
            "close": [close],
            "ema_20": [ema_20],
            "ema_50": [ema_50],
            "rsi_14": [rsi_14],
            "macd": [macd],
            "macd_signal": [macd_signal],
        }
    )


def test_generate_summary_uptrend_overbought_bullish():
    df = _make_df(close=110, ema_20=108, ema_50=100, rsi_14=75, macd=2.0, macd_signal=1.0)
    summary = generate_summary(df, "BTCUSDT")
    assert "BTCUSDT" in summary
    assert "uptrend" in summary
    assert "overbought" in summary
    assert "bullish" in summary


def test_generate_summary_downtrend_oversold_bearish():
    df = _make_df(close=90, ema_20=95, ema_50=100, rsi_14=20, macd=-2.0, macd_signal=-1.0)
    summary = generate_summary(df, "ETHUSDT")
    assert "downtrend" in summary
    assert "oversold" in summary
    assert "bearish" in summary


def test_generate_summary_raises_on_missing_columns():
    df = pd.DataFrame({"close": [100]})
    with pytest.raises(ValueError):
        generate_summary(df, "BTCUSDT")


def test_generate_summary_raises_on_empty_dataframe():
    df = pd.DataFrame(
        columns=["close", "ema_20", "ema_50", "rsi_14", "macd", "macd_signal"]
    )
    with pytest.raises(ValueError):
        generate_summary(df, "BTCUSDT")
