"""Fetches public market data from Binance's public REST API.

No API key or secret is used or required anywhere in this module -
only Binance's public, read-only market data endpoints are called.
"""

from __future__ import annotations

import pandas as pd
import requests

from src.config import (
    BINANCE_KLINES_URL,
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


def fetch_ohlcv(symbol: str, interval: str, limit: int = 300) -> pd.DataFrame:
    """Fetch OHLCV candlestick data for a symbol from Binance's public API.

    Args:
        symbol: Trading pair, e.g. "BTCUSDT". Must be one of
            SUPPORTED_SYMBOLS.
        interval: Candlestick interval, e.g. "1h".
        limit: Number of candles to retrieve (max 1000 per Binance limits).

    Returns:
        A DataFrame indexed by UTC timestamp with columns:
        open, high, low, close, volume.

    Raises:
        BinanceClientError: If the symbol is unsupported, the request
            fails, or the response cannot be parsed.
    """
    if symbol not in SUPPORTED_SYMBOLS:
        raise BinanceClientError(
            f"Unsupported symbol '{symbol}'. Supported symbols: {SUPPORTED_SYMBOLS}"
        )

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
        df = df.set_index("open_time")[NUMERIC_COLUMNS]
    except (KeyError, ValueError, TypeError) as exc:
        raise BinanceClientError(
            f"Failed to parse Binance API response for {symbol}: {exc}"
        ) from exc

    return df
