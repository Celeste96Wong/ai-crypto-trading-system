"""Central configuration for the trading system.

Only public, read-only settings live here. No API keys or secrets
should ever be added to this file or committed to the repository.
"""

SUPPORTED_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]

SUPPORTED_INTERVALS = ["15m", "1h", "4h", "1d"]

DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_INTERVAL = "1h"
DEFAULT_LIMIT = 300

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_SERVER_TIME_URL = "https://api.binance.com/api/v3/time"
REQUEST_TIMEOUT_SECONDS = 10

# How many extra attempts to make (on top of the first) when Binance
# rate-limits a request or returns a transient server error. This bounds
# retries so a single request can never hang or loop indefinitely.
MAX_RETRIES = 2

# HTTP 429 ("too many requests") is Binance's ordinary rate limit: a
# bounded retry is appropriate, honoring the Retry-After header.
RATE_LIMIT_RETRYABLE_STATUS_CODES = (429,)

# HTTP 418 means Binance has automatically banned this IP address. Per
# Binance's docs, this must NOT be retried automatically - only 429 is
# retried. 418 always fails immediately (see _request_with_retry).
IP_BAN_STATUS_CODES = (418,)

# Transient server-side errors that are worth a short retry.
RETRYABLE_SERVER_ERROR_STATUS_CODES = (500, 502, 503, 504)

# Used when Binance rate-limits a request (429) without sending a
# Retry-After header, and as the wait between retries on a transient
# server error.
DEFAULT_RETRY_AFTER_SECONDS = 1.0

# The longest we will ever wait automatically because of a Retry-After
# header. If Binance asks for a longer wait than this, we fail
# immediately and report the required wait rather than retrying sooner
# than Binance permits.
MAX_RETRY_AFTER_SECONDS = 10.0

EMA_SHORT_PERIOD = 20
EMA_LONG_PERIOD = 50
RSI_PERIOD = 14
MACD_FAST_PERIOD = 12
MACD_SLOW_PERIOD = 26
MACD_SIGNAL_PERIOD = 9
