from unittest.mock import Mock, patch

import pandas as pd
import pytest
import requests

from src.data.binance_client import BinanceClientError, fetch_ohlcv

SAMPLE_KLINE_ROW = [
    1700000000000,  # open_time
    "100.0",  # open
    "105.0",  # high
    "95.0",  # low
    "102.0",  # close
    "10.5",  # volume
    1700003599999,  # close_time
    "1000.0",
    100,
    "500.0",
    "500.0",
    "0",
]


def _mock_response(json_data, status_ok=True):
    mock_resp = Mock()
    mock_resp.json.return_value = json_data
    if status_ok:
        mock_resp.raise_for_status.return_value = None
    else:
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("bad status")
    return mock_resp


def test_fetch_ohlcv_rejects_unsupported_symbol():
    with pytest.raises(BinanceClientError):
        fetch_ohlcv("DOGEUSDT", "1h", limit=10)


@patch("src.data.binance_client.requests.get")
def test_fetch_ohlcv_parses_valid_response(mock_get):
    mock_get.return_value = _mock_response([SAMPLE_KLINE_ROW] * 5)

    df = fetch_ohlcv("BTCUSDT", "1h", limit=5)

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 5
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df["close"].iloc[0] == pytest.approx(102.0)
    assert isinstance(df.index, pd.DatetimeIndex)


@patch("src.data.binance_client.requests.get")
def test_fetch_ohlcv_raises_on_network_error(mock_get):
    mock_get.side_effect = requests.exceptions.ConnectionError("network down")

    with pytest.raises(BinanceClientError):
        fetch_ohlcv("BTCUSDT", "1h", limit=5)


@patch("src.data.binance_client.requests.get")
def test_fetch_ohlcv_raises_on_http_error(mock_get):
    mock_get.return_value = _mock_response([], status_ok=False)

    with pytest.raises(BinanceClientError):
        fetch_ohlcv("BTCUSDT", "1h", limit=5)


@patch("src.data.binance_client.requests.get")
def test_fetch_ohlcv_raises_on_empty_response(mock_get):
    mock_get.return_value = _mock_response([])

    with pytest.raises(BinanceClientError):
        fetch_ohlcv("BTCUSDT", "1h", limit=5)
