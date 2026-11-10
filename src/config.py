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

EMA_SHORT_PERIOD = 20
EMA_LONG_PERIOD = 50
RSI_PERIOD = 14
MACD_FAST_PERIOD = 12
MACD_SLOW_PERIOD = 26
MACD_SIGNAL_PERIOD = 9
