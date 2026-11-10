"""Fetches public market data from Binance's public REST API.

No API key or secret is used or required anywhere in this module -
only Binance's public, read-only market data endpoints are called.

Only fully closed candles are returned: the most recent candle from
Binance's klines endpoint is often still "in progress" (it has not
reached its close_time yet), and using its still-changing price would
make indicators and summaries flicker and could produce misleading
signals. See `_get_server_time_utc` and the filtering in `fetch_ohlcv`.
"""

from __future__ import annotations

import pandas as pd
import requests

from src.config import (
    BINANCE_KLINES_URL,
    BINANCE_SERVER_TIME_URL,
    REQUEST_TIMEOUT_SECONDS,
    SUPPORTED_SYMBOLS,
)

KLINE_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_asset_volume",
    "num_trades",
    "taker_buy_base_asset_volume",
    "taker_buy_quote_asset_volume",
    "ignore",
]

NUMERIC_COLUMNS = ["open", "high", "low", "close", "volume"]


class BinanceClientError(Exception):
    """Raised when market data cannot be retrieved or parsed."""


def _get_server_time_utc() -> pd.Timestamp:
    """Return the current time as a timezone-aware UTC timestamp.

    Prefers Binance's own public /time endpoint so that "has this candle
    closed yet" is judged against the exchange's clock rather than this
    machine's local clock or timezone settings. If the time endpoint
    cannot be reached, falls back to this machine's clock, read as UTC
    (never as a locale-dependent local timezone).
    """
    try:
        response = requests.get(BINANCE_SERVER_TIME_URL, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        server_time_ms = response.json()["serverTime"]
        return pd.Timestamp(server_time_ms, unit="ms", tz="UTC")
    except (requests.exceptions.RequestException, ValueError, KeyError, TypeError):
        return pd.Timestamp.now(tz="UTC")


def fetch_ohlcv(symbol: str, interval: str, limit: int = 300) -> pd.DataFrame:
    """Fetch completed OHLCV candlestick data for a symbol from Binance.

    Args:
        symbol: Trading pair, e.g. "BTCUSDT". Must be one of
            SUPPORTED_SYMBOLS.
        interval: Candlestick interval, e.g. "1h".
        limit: Number of candles to retrieve (max 1000 per Binance limits).
            The most recent candle is dropped if it has not closed yet,
            so the returned DataFrame can have one fewer row than `limit`.

    Returns:
        A DataFrame indexed by UTC timestamp with columns:
        open, high, low, close, volume. Only candles whose close_time
        has already passed (relative to Binance's server clock) are
        included, so indicators computed from this data never use a
        still-forming candle.

    Raises:
        BinanceClientError: If the symbol is unsupported, the request
            fails, the response cannot be parsed, or no completed
            candle is available yet.
    """
    if symbol not in SUPPORTED_SYMBOLS:
        raise BinanceClientError(
            f"Unsupported symbol '{symbol}'. Supported symbols: {SUPPORTED_SYMBOLS}"
        )

    # Fetch the server clock before requesting klines. A candle could
    # otherwise close in the gap between the klines request and a
    # later time request, making a still-forming candle look closed.
    # Fetching the clock first means the comparison timestamp is always
    # at or before the candles' actual request time, so a forming
    # candle is never mistaken for a completed one.
    server_time_utc = _get_server_time_utc()

    params = {"symbol": symbol, "interval": interval, "limit": limit}

    try:
        response = requests.get(
            BINANCE_KLINES_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        raw_data = response.json()
    except requests.exceptions.RequestException as exc:
        raise BinanceClientError(
            f"Failed to reach Binance API for {symbol}: {exc}"
        ) from exc
    except ValueError as exc:
        raise BinanceClientError(
            f"Binance API returned an invalid response for {symbol}: {exc}"
        ) from exc

    if not isinstance(raw_data, list) or not raw_data:
        raise BinanceClientError(
            f"Binance API returned no candlestick data for {symbol}"
        )

    try:
        df = pd.DataFrame(raw_data, columns=KLINE_COLUMNS)
        df[NUMERIC_COLUMNS] = df[NUMERIC_COLUMNS].astype(float)
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    except (KeyError, ValueError, TypeError) as exc:
        raise BinanceClientError(
            f"Failed to parse Binance API response for {symbol}: {exc}"
        ) from exc

    completed = df[df["close_time"] <= server_time_utc]

    if completed.empty:
        raise BinanceClientError(
            f"No completed candle available yet for {symbol} {interval}; "
            "the only data returned by Binance is still forming."
        )

    return completed.set_index("open_time")[NUMERIC_COLUMNS]
