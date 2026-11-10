from unittest.mock import Mock, patch

import pandas as pd
import pytest
import requests

from src.config import (
    BINANCE_KLINES_URL,
    BINANCE_SERVER_TIME_URL,
    MAX_RETRIES,
    SUPPORTED_INTERVALS,
)
from src.data.binance_client import BinanceClientError, BinanceRateLimitError, fetch_ohlcv


def _make_kline_row(open_time_ms, close_time_ms, close_price="102.0"):
    return [
        open_time_ms,  # open_time
        "100.0",  # open
        "105.0",  # high
        "95.0",  # low
        close_price,  # close
        "10.5",  # volume
        close_time_ms,  # close_time
        "1000.0",
        100,
        "500.0",
        "500.0",
        "0",
    ]


# A single closed candle used by the pre-existing "happy path" tests.
SAMPLE_KLINE_ROW = _make_kline_row(1700000000000, 1700003599999)


def _mock_response(json_data, status_ok=True, status_code=None, headers=None):
    """Build a fake `requests` response.

    `status_code` drives the retry logic in `_request_with_retry`
    (429/418/5xx vs. everything else), so it must always be set to
    something comparable to an int - defaults to 200 for the "ok" case
    and 400 (a non-retryable client error) for the "not ok" case.
    """
    mock_resp = Mock()
    mock_resp.json.return_value = json_data
    mock_resp.headers = headers or {}
    mock_resp.status_code = status_code if status_code is not None else (200 if status_ok else 400)
    if status_ok:
        mock_resp.raise_for_status.return_value = None
    else:
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("bad status")
    return mock_resp


def _server_time_at(ms: int) -> pd.Timestamp:
    """Build the UTC timestamp `_get_server_time_utc` would return at `ms`."""
    return pd.Timestamp(ms, unit="ms", tz="UTC")


def test_fetch_ohlcv_rejects_unsupported_symbol():
    with pytest.raises(BinanceClientError):
        fetch_ohlcv("DOGEUSDT", "1h", limit=10)


@patch("src.data.binance_client._get_server_time_utc")
@patch("src.data.binance_client.requests.get")
def test_fetch_ohlcv_parses_valid_response(mock_get, mock_server_time):
    mock_get.return_value = _mock_response([SAMPLE_KLINE_ROW] * 5)
    # Server time is well after every candle's close_time, so all are closed.
    mock_server_time.return_value = _server_time_at(1700003599999 + 1_000)

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


# --- Completed-candle filtering (Critical Issue #1 from the code review) ---


@patch("src.data.binance_client._get_server_time_utc")
@patch("src.data.binance_client.requests.get")
def test_fetch_ohlcv_includes_a_candle_that_has_already_closed(mock_get, mock_server_time):
    close_time_ms = 1700003599999
    closed_row = _make_kline_row(1700000000000, close_time_ms)
    mock_get.return_value = _mock_response([closed_row])
    # Server time is after this candle's close_time -> it has closed.
    mock_server_time.return_value = _server_time_at(close_time_ms + 1_000)

    df = fetch_ohlcv("BTCUSDT", "1h", limit=1)

    assert len(df) == 1


@patch("src.data.binance_client._get_server_time_utc")
@patch("src.data.binance_client.requests.get")
def test_fetch_ohlcv_excludes_a_candle_that_is_still_forming(mock_get, mock_server_time):
    closed_close_time_ms = 1700003599999
    forming_close_time_ms = 1700007199999
    closed_row = _make_kline_row(1700000000000, closed_close_time_ms)
    forming_row = _make_kline_row(1700003600000, forming_close_time_ms)
    mock_get.return_value = _mock_response([closed_row, forming_row])
    # Server time is after the first candle's close but before the
    # second (latest) candle's close -> the latest candle is still forming.
    mock_server_time.return_value = _server_time_at(closed_close_time_ms + 1_000)

    df = fetch_ohlcv("BTCUSDT", "1h", limit=2)

    assert len(df) == 1
    assert df.index[0] == pd.Timestamp(1700000000000, unit="ms", tz="UTC")


@patch("src.data.binance_client._get_server_time_utc")
@patch("src.data.binance_client.requests.get")
def test_fetch_ohlcv_raises_when_only_available_candle_is_still_forming(
    mock_get, mock_server_time
):
    forming_close_time_ms = 1700007199999
    forming_row = _make_kline_row(1700003600000, forming_close_time_ms)
    mock_get.return_value = _mock_response([forming_row])
    # Server time is before this candle's close_time -> still forming.
    mock_server_time.return_value = _server_time_at(forming_close_time_ms - 1_000)

    with pytest.raises(BinanceClientError):
        fetch_ohlcv("BTCUSDT", "1h", limit=1)


@patch("src.data.binance_client.requests.get")
def test_fetch_ohlcv_falls_back_to_local_utc_clock_if_server_time_unavailable(mock_get):
    closed_row = _make_kline_row(1700000000000, 1700003599999)

    def _side_effect(url, *args, **kwargs):
        if url.endswith("/klines"):
            return _mock_response([closed_row])
        if url.endswith("/time"):
            raise requests.exceptions.ConnectionError("time endpoint unreachable")
        raise AssertionError(f"Unexpected URL requested: {url}")

    mock_get.side_effect = _side_effect

    # The candle's close_time (Nov 2023) is long in the past relative to
    # this machine's real UTC clock, so the fallback still marks it closed.
    df = fetch_ohlcv("BTCUSDT", "1h", limit=1)

    assert len(df) == 1


@patch("src.data.binance_client.requests.get")
def test_fetch_ohlcv_requests_server_time_before_klines(mock_get):
    """The server clock must be read before klines are requested, so a
    candle cannot close in the gap between the two requests and be
    mistaken for one that was already closed when klines were fetched."""
    closed_row = _make_kline_row(1700000000000, 1700003599999)

    def _side_effect(url, *args, **kwargs):
        if url == BINANCE_SERVER_TIME_URL:
            return _mock_response({"serverTime": 1700003599999 + 1_000})
        if url == BINANCE_KLINES_URL:
            return _mock_response([closed_row])
        raise AssertionError(f"Unexpected URL requested: {url}")

    mock_get.side_effect = _side_effect

    df = fetch_ohlcv("BTCUSDT", "1h", limit=1)

    assert len(df) == 1
    requested_urls = [call.args[0] for call in mock_get.call_args_list]
    assert requested_urls == [BINANCE_SERVER_TIME_URL, BINANCE_KLINES_URL]


# --- Interval validation ---


def test_fetch_ohlcv_rejects_unsupported_interval():
    with pytest.raises(BinanceClientError):
        fetch_ohlcv("BTCUSDT", "3m", limit=10)


@patch("src.data.binance_client.requests.get")
def test_fetch_ohlcv_rejects_unsupported_interval_before_any_request(mock_get):
    with pytest.raises(BinanceClientError):
        fetch_ohlcv("BTCUSDT", "3m", limit=10)

    mock_get.assert_not_called()


@pytest.mark.parametrize("interval", SUPPORTED_INTERVALS)
@patch("src.data.binance_client._get_server_time_utc")
@patch("src.data.binance_client.requests.get")
def test_fetch_ohlcv_accepts_every_supported_interval(mock_get, mock_server_time, interval):
    close_time_ms = 1700003599999
    closed_row = _make_kline_row(1700000000000, close_time_ms)
    mock_get.return_value = _mock_response([closed_row])
    mock_server_time.return_value = _server_time_at(close_time_ms + 1_000)

    df = fetch_ohlcv("BTCUSDT", interval, limit=1)

    assert len(df) == 1


# --- Rate limiting (429/418) and transient server errors (Important #3) ---


@patch("src.data.binance_client.time.sleep")
@patch("src.data.binance_client.requests.get")
def test_fetch_ohlcv_retries_on_429_then_succeeds(mock_get, mock_sleep):
    close_time_ms = 1700003599999
    closed_row = _make_kline_row(1700000000000, close_time_ms)
    ok_time_response = _mock_response({"serverTime": close_time_ms + 1_000})
    rate_limited_response = _mock_response([], status_code=429, headers={"Retry-After": "2"})
    ok_klines_response = _mock_response([closed_row])
    mock_get.side_effect = [ok_time_response, rate_limited_response, ok_klines_response]

    df = fetch_ohlcv("BTCUSDT", "1h", limit=1)

    assert len(df) == 1
    assert mock_get.call_count == 3
    mock_sleep.assert_called_once_with(2.0)


@patch("src.data.binance_client.time.sleep")
@patch("src.data.binance_client.requests.get")
def test_fetch_ohlcv_retries_on_418_then_succeeds(mock_get, mock_sleep):
    close_time_ms = 1700003599999
    closed_row = _make_kline_row(1700000000000, close_time_ms)
    ok_time_response = _mock_response({"serverTime": close_time_ms + 1_000})
    banned_response = _mock_response([], status_code=418, headers={"Retry-After": "0"})
    ok_klines_response = _mock_response([closed_row])
    mock_get.side_effect = [ok_time_response, banned_response, ok_klines_response]

    df = fetch_ohlcv("BTCUSDT", "1h", limit=1)

    assert len(df) == 1
    assert mock_get.call_count == 3


@patch("src.data.binance_client.time.sleep")
@patch("src.data.binance_client.requests.get")
def test_fetch_ohlcv_retries_on_transient_server_error_then_succeeds(mock_get, mock_sleep):
    close_time_ms = 1700003599999
    closed_row = _make_kline_row(1700000000000, close_time_ms)
    ok_time_response = _mock_response({"serverTime": close_time_ms + 1_000})
    server_error_response = _mock_response([], status_code=503)
    ok_klines_response = _mock_response([closed_row])
    mock_get.side_effect = [ok_time_response, server_error_response, ok_klines_response]

    df = fetch_ohlcv("BTCUSDT", "1h", limit=1)

    assert len(df) == 1
    assert mock_get.call_count == 3


@patch("src.data.binance_client.time.sleep")
@patch("src.data.binance_client.requests.get")
def test_fetch_ohlcv_raises_rate_limit_error_after_exhausting_retries(mock_get, mock_sleep):
    ok_time_response = _mock_response({"serverTime": 1700003599999 + 1_000})
    always_rate_limited = _mock_response([], status_code=429, headers={"Retry-After": "0"})
    # One call for the server time, then far more 429s than could ever
    # be consumed, to prove the retry loop stops on its own.
    mock_get.side_effect = [ok_time_response] + [always_rate_limited] * 10

    with pytest.raises(BinanceRateLimitError):
        fetch_ohlcv("BTCUSDT", "1h", limit=1)

    # 1 server-time call + (MAX_RETRIES + 1) klines attempts: retries
    # are bounded, never indefinite.
    assert mock_get.call_count == 1 + (MAX_RETRIES + 1)


@patch("src.data.binance_client.time.sleep")
@patch("src.data.binance_client.requests.get")
def test_fetch_ohlcv_respects_retry_after_header(mock_get, mock_sleep):
    close_time_ms = 1700003599999
    closed_row = _make_kline_row(1700000000000, close_time_ms)
    ok_time_response = _mock_response({"serverTime": close_time_ms + 1_000})
    rate_limited_response = _mock_response([], status_code=429, headers={"Retry-After": "7"})
    ok_klines_response = _mock_response([closed_row])
    mock_get.side_effect = [ok_time_response, rate_limited_response, ok_klines_response]

    fetch_ohlcv("BTCUSDT", "1h", limit=1)

    mock_sleep.assert_called_once_with(7.0)


@patch("src.data.binance_client.time.sleep")
@patch("src.data.binance_client.requests.get")
def test_fetch_ohlcv_caps_an_excessive_retry_after_header(mock_get, mock_sleep):
    close_time_ms = 1700003599999
    closed_row = _make_kline_row(1700000000000, close_time_ms)
    ok_time_response = _mock_response({"serverTime": close_time_ms + 1_000})
    # A Retry-After far beyond what we should ever wait.
    rate_limited_response = _mock_response([], status_code=429, headers={"Retry-After": "600"})
    ok_klines_response = _mock_response([closed_row])
    mock_get.side_effect = [ok_time_response, rate_limited_response, ok_klines_response]

    fetch_ohlcv("BTCUSDT", "1h", limit=1)

    mock_sleep.assert_called_once_with(10.0)


@patch("src.data.binance_client.time.sleep")
@patch("src.data.binance_client.requests.get")
def test_get_server_time_falls_back_after_exhausting_retries(mock_get, mock_sleep):
    """If the time endpoint keeps rate-limiting us, fetch_ohlcv should
    still succeed using this machine's local UTC clock as a fallback,
    rather than failing the whole request."""
    close_time_ms = 1700003599999
    closed_row = _make_kline_row(1700000000000, close_time_ms)
    always_rate_limited = _mock_response([], status_code=429, headers={"Retry-After": "0"})
    ok_klines_response = _mock_response([closed_row])
    mock_get.side_effect = [always_rate_limited] * (MAX_RETRIES + 1) + [ok_klines_response]

    df = fetch_ohlcv("BTCUSDT", "1h", limit=1)

    assert len(df) == 1
