"""Fetches public market data from Binance's public REST API.

No API key or secret is used or required anywhere in this module -
only Binance's public, read-only market data endpoints are called.

Only fully closed candles are returned: the most recent candle from
Binance's klines endpoint is often still "in progress" (it has not
reached its close_time yet), and using its still-changing price would
make indicators and summaries flicker and could produce misleading
signals. See `_get_server_time_utc` and the filtering in `fetch_ohlcv`.

Requests also go through `_request_with_retry`, which applies a small,
bounded retry for Binance rate limiting (HTTP 429/418, honoring the
Retry-After header) and transient server errors (5xx), so a brief
hiccup does not immediately surface as an error to the user.
"""

from __future__ import annotations

import time

import pandas as pd
import requests

from src.config import (
    BINANCE_KLINES_URL,
    BINANCE_SERVER_TIME_URL,
    DEFAULT_RETRY_AFTER_SECONDS,
    MAX_RETRIES,
    MAX_RETRY_AFTER_SECONDS,
    RATE_LIMIT_STATUS_CODES,
    REQUEST_TIMEOUT_SECONDS,
    RETRYABLE_SERVER_ERROR_STATUS_CODES,
    SUPPORTED_INTERVALS,
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


class BinanceRateLimitError(BinanceClientError):
    """Raised when Binance is still rate-limiting requests after all retries."""


def _parse_retry_after_seconds(response) -> float:
    """Read Binance's Retry-After header, bounded to a sane range.

    Falls back to DEFAULT_RETRY_AFTER_SECONDS if the header is missing
    or not a valid number, and never waits longer than
    MAX_RETRY_AFTER_SECONDS regardless of what the header says.
    """
    retry_after = response.headers.get("Retry-After")
    if retry_after is None:
        return DEFAULT_RETRY_AFTER_SECONDS

    try:
        seconds = float(retry_after)
    except (TypeError, ValueError):
        return DEFAULT_RETRY_AFTER_SECONDS

    return min(max(seconds, 0.0), MAX_RETRY_AFTER_SECONDS)


def _request_with_retry(url: str, params: dict | None = None, context: str = "request"):
    """GET a Binance public endpoint with a small, bounded retry.

    Retries up to MAX_RETRIES extra times (never indefinitely) on:
    - HTTP 429 / 418 (rate limiting), waiting for the Retry-After
      duration Binance sends when available.
    - Transient 5xx server errors, with a short fixed wait.
    - Network-level failures (timeouts, connection errors).

    No API credentials are used anywhere, and nothing from the
    response (headers or body) is included in the exceptions raised.

    Args:
        url: The full Binance endpoint URL to GET.
        params: Optional query parameters.
        context: Short human-readable label used in error messages
            (e.g. "klines for BTCUSDT 1h"), to say what failed without
            leaking request internals.

    Returns:
        The parsed JSON body of the successful response.

    Raises:
        BinanceRateLimitError: If Binance keeps rate-limiting the
            request after all retries are exhausted.
        BinanceClientError: For any other failure once retries are
            exhausted, including network errors, server errors, and
            responses that cannot be parsed as JSON.
    """
    last_network_error_message = f"Failed to reach Binance API ({context})"

    for attempt in range(MAX_RETRIES + 1):
        is_last_attempt = attempt == MAX_RETRIES

        try:
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.exceptions.RequestException as exc:
            last_network_error_message = f"Failed to reach Binance API ({context}): {exc}"
            if is_last_attempt:
                raise BinanceClientError(last_network_error_message) from exc
            time.sleep(DEFAULT_RETRY_AFTER_SECONDS)
            continue

        if response.status_code in RATE_LIMIT_STATUS_CODES:
            if is_last_attempt:
                raise BinanceRateLimitError(
                    f"Binance rate-limited the request ({context}) after "
                    f"{MAX_RETRIES} retries (HTTP {response.status_code})."
                )
            time.sleep(_parse_retry_after_seconds(response))
            continue

        if response.status_code in RETRYABLE_SERVER_ERROR_STATUS_CODES:
            if is_last_attempt:
                raise BinanceClientError(
                    f"Binance API returned a server error ({context}) after "
                    f"{MAX_RETRIES} retries (HTTP {response.status_code})."
                )
            time.sleep(DEFAULT_RETRY_AFTER_SECONDS)
            continue

        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            raise BinanceClientError(f"Binance API request failed ({context}): {exc}") from exc

        try:
            return response.json()
        except ValueError as exc:
            raise BinanceClientError(
                f"Binance API returned an invalid response ({context}): {exc}"
            ) from exc

    # Defensive: the loop above always returns or raises before this point.
    raise BinanceClientError(last_network_error_message)


def _get_server_time_utc() -> pd.Timestamp:
    """Return the current time as a timezone-aware UTC timestamp.

    Prefers Binance's own public /time endpoint so that "has this candle
    closed yet" is judged against the exchange's clock rather than this
    machine's local clock or timezone settings. If the time endpoint
    cannot be reached (even after retries), falls back to this machine's
    clock, read as UTC (never as a locale-dependent local timezone).
    """
    try:
        payload = _request_with_retry(BINANCE_SERVER_TIME_URL, context="server time")
        server_time_ms = payload["serverTime"]
        return pd.Timestamp(server_time_ms, unit="ms", tz="UTC")
    except (BinanceClientError, KeyError, TypeError, ValueError):
        return pd.Timestamp.now(tz="UTC")


def fetch_ohlcv(symbol: str, interval: str, limit: int = 300) -> pd.DataFrame:
    """Fetch completed OHLCV candlestick data for a symbol from Binance.

    Args:
        symbol: Trading pair, e.g. "BTCUSDT". Must be one of
            SUPPORTED_SYMBOLS.
        interval: Candlestick interval, e.g. "1h". Must be one of
            SUPPORTED_INTERVALS; checked before any API request is sent.
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
        BinanceClientError: If the symbol or interval is unsupported,
            the request fails (including after bounded retries), the
            response cannot be parsed, or no completed candle is
            available yet. BinanceRateLimitError (a subclass) is raised
            specifically when Binance is still rate-limiting requests
            after all retries.
    """
    if symbol not in SUPPORTED_SYMBOLS:
        raise BinanceClientError(
            f"Unsupported symbol '{symbol}'. Supported symbols: {SUPPORTED_SYMBOLS}"
        )
    if interval not in SUPPORTED_INTERVALS:
        raise BinanceClientError(
            f"Unsupported interval '{interval}'. Supported intervals: {SUPPORTED_INTERVALS}"
        )

    # Fetch the server clock before requesting klines. A candle could
    # otherwise close in the gap between the klines request and a
    # later time request, making a still-forming candle look closed.
    # Fetching the clock first means the comparison timestamp is always
    # at or before the candles' actual request time, so a forming
    # candle is never mistaken for a completed one.
    server_time_utc = _get_server_time_utc()

    params = {"symbol": symbol, "interval": interval, "limit": limit}
    raw_data = _request_with_retry(
        BINANCE_KLINES_URL, params=params, context=f"klines for {symbol} {interval}"
    )

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
