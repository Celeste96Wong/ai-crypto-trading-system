"""Fetches public market data from Binance's public REST API.

No API key or secret is used or required anywhere in this module -
only Binance's public, read-only market data endpoints are called.

Only fully closed candles are returned: the most recent candle from
Binance's klines endpoint is often still "in progress" (it has not
reached its close_time yet), and using its still-changing price would
make indicators and summaries flicker and could produce misleading
signals. See `_get_server_time_utc` and the filtering in `fetch_ohlcv`.

Requests also go through `_request_with_retry`, which applies a small,
bounded retry for Binance's ordinary rate limit (HTTP 429, honoring the
Retry-After header) and transient server errors (5xx), so a brief
hiccup does not immediately surface as an error to the user. HTTP 418
(Binance has banned this IP) is never retried automatically - see
`_request_with_retry` for why.

Error messages raised here are deliberately plain, user-facing text:
they never include raw exception text, response bodies, or other
request/response internals, even though no credentials are used or at
risk in this project. The original exception is still chained with
`raise ... from exc` so it remains visible in tracebacks/logs.
"""

from __future__ import annotations

import time

import pandas as pd
import requests

from src.config import (
    BINANCE_KLINES_URL,
    BINANCE_SERVER_TIME_URL,
    DEFAULT_RETRY_AFTER_SECONDS,
    IP_BAN_STATUS_CODES,
    MAX_RETRIES,
    MAX_RETRY_AFTER_SECONDS,
    RATE_LIMIT_RETRYABLE_STATUS_CODES,
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


def _parse_retry_after_seconds(response) -> float | None:
    """Read Binance's Retry-After header, verbatim and uncapped.

    Returns None if the header is missing or not a valid non-negative
    number. Callers decide separately whether the value is within an
    acceptable wait - this function never silently shortens it, since
    doing so would mean retrying sooner than Binance permits.
    """
    retry_after = response.headers.get("Retry-After")
    if retry_after is None:
        return None

    try:
        seconds = float(retry_after)
    except (TypeError, ValueError):
        return None

    return max(seconds, 0.0)


def _format_retry_after(retry_after_seconds: float | None) -> str:
    """Build a short, user-facing phrase describing a required wait."""
    if retry_after_seconds is None:
        return "Please try again later."
    return f"Please try again in about {retry_after_seconds:g} second(s)."


def _request_with_retry(url: str, params: dict | None = None, context: str = "request"):
    """GET a Binance public endpoint with a small, bounded retry.

    Retries up to MAX_RETRIES extra times (never indefinitely) on:
    - HTTP 429 (ordinary rate limiting), waiting for the Retry-After
      duration Binance sends when available. If that wait is longer
      than MAX_RETRY_AFTER_SECONDS, this fails immediately instead of
      retrying sooner than Binance permits.
    - Transient 5xx server errors, with a short fixed wait.
    - Network-level failures (timeouts, connection errors).

    HTTP 418 ("IP auto-banned") is a special case and is NEVER retried:
    per Binance's API documentation, only 429 is meant to be retried;
    418 means this IP is temporarily banned, so this raises immediately
    instead of sending another request.

    No API credentials are used anywhere. Error messages are plain,
    user-facing text and never include raw exception text, response
    bodies, or other request/response internals; the original
    exception is still chained via `raise ... from exc` for anyone
    inspecting tracebacks/logs.

    Args:
        url: The full Binance endpoint URL to GET.
        params: Optional query parameters.
        context: Short human-readable label used in error messages
            (e.g. "klines for BTCUSDT 1h"), to say what failed without
            leaking request internals.

    Returns:
        The parsed JSON body of the successful response.

    Raises:
        BinanceRateLimitError: If Binance has banned this IP (HTTP
            418), or is still rate-limiting the request (HTTP 429)
            after all retries, or reports a required wait longer than
            this app will ever wait automatically.
        BinanceClientError: For any other failure once retries are
            exhausted, including network errors, server errors, and
            responses that cannot be parsed as JSON.
    """
    for attempt in range(MAX_RETRIES + 1):
        is_last_attempt = attempt == MAX_RETRIES

        try:
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.exceptions.RequestException as exc:
            if is_last_attempt:
                raise BinanceClientError(
                    f"Could not reach Binance ({context}) after {MAX_RETRIES} retries."
                ) from exc
            time.sleep(DEFAULT_RETRY_AFTER_SECONDS)
            continue

        if response.status_code in IP_BAN_STATUS_CODES:
            # Never retried: Binance has already banned this IP, so
            # sending another request would not help.
            retry_after_seconds = _parse_retry_after_seconds(response)
            raise BinanceRateLimitError(
                f"Binance has temporarily banned this IP address ({context}; "
                f"HTTP 418). {_format_retry_after(retry_after_seconds)}"
            )

        if response.status_code in RATE_LIMIT_RETRYABLE_STATUS_CODES:
            retry_after_seconds = _parse_retry_after_seconds(response)
            wait_seconds = (
                retry_after_seconds
                if retry_after_seconds is not None
                else DEFAULT_RETRY_AFTER_SECONDS
            )

            if wait_seconds > MAX_RETRY_AFTER_SECONDS:
                # Do not cap this and retry sooner than Binance permits;
                # fail now and tell the caller the real required wait.
                raise BinanceRateLimitError(
                    f"Binance is rate-limiting requests ({context}; HTTP 429) "
                    f"and requires a longer wait than this app retries "
                    f"automatically. {_format_retry_after(retry_after_seconds)}"
                )

            if is_last_attempt:
                raise BinanceRateLimitError(
                    f"Binance is still rate-limiting requests ({context}) "
                    f"after {MAX_RETRIES} retries (HTTP 429). "
                    f"{_format_retry_after(retry_after_seconds)}"
                )

            time.sleep(wait_seconds)
            continue

        if response.status_code in RETRYABLE_SERVER_ERROR_STATUS_CODES:
            if is_last_attempt:
                raise BinanceClientError(
                    f"Binance is temporarily unavailable ({context}) after "
                    f"{MAX_RETRIES} retries."
                )
            time.sleep(DEFAULT_RETRY_AFTER_SECONDS)
            continue

        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            raise BinanceClientError(f"Binance rejected the request ({context}).") from exc

        try:
            return response.json()
        except ValueError as exc:
            raise BinanceClientError(
                f"Binance returned an unreadable response ({context})."
            ) from exc

    # Defensive: the loop above always returns or raises before this point.
    raise BinanceClientError(f"Could not reach Binance ({context}) after {MAX_RETRIES} retries.")


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
            f"Binance returned candlestick data in an unexpected format for {symbol}."
        ) from exc

    completed = df[df["close_time"] <= server_time_utc]

    if completed.empty:
        raise BinanceClientError(
            f"No completed candle available yet for {symbol} {interval}; "
            "the only data returned by Binance is still forming."
        )

    return completed.set_index("open_time")[NUMERIC_COLUMNS]
