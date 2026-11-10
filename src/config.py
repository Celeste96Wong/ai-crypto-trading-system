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

# Binance uses these status codes specifically for rate limiting / IP bans.
RATE_LIMIT_STATUS_CODES = (429, 418)

# Transient server-side errors that are worth a short retry.
RETRYABLE_SERVER_ERROR_STATUS_CODES = (500, 502, 503, 504)

# Used when Binance rate-limits a request without sending a Retry-After
# header, and as the wait between retries on a transient server error.
DEFAULT_RETRY_AFTER_SECONDS = 1.0

# Upper bound on how long we will ever wait because of a Retry-After
# header, so a malformed or unexpectedly large value cannot stall the app.
MAX_RETRY_AFTER_SECONDS = 10.0

EMA_SHORT_PERIOD = 20
EMA_LONG_PERIOD = 50
RSI_PERIOD = 14
MACD_FAST_PERIOD = 12
MACD_SLOW_PERIOD = 26
MACD_SIGNAL_PERIOD = 9
