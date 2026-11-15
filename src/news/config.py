"""Configuration for the news intelligence module.

Only public, read-only settings live here. No API keys or secrets
should ever be added to this file or committed to the repository -
the OpenAI API key is read from the OPENAI_API_KEY environment
variable at runtime (see ai_analyst.py).
"""

import os

# --- RSS news sources -------------------------------------------------
# Each entry is (source_name, feed_url). Free, public RSS feeds only -
# no paid news API is required for news collection or classification.
RSS_SOURCES = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
    ("Decrypt", "https://decrypt.co/feed"),
    ("CryptoSlate", "https://cryptoslate.com/feed/"),
]

RSS_REQUEST_TIMEOUT_SECONDS = 10

# --- Storage -----------------------------------------------------------
NEWS_DB_PATH = os.path.join("data", "news.db")

# --- Supported assets ----------------------------------------------------
SUPPORTED_NEWS_ASSETS = ["BTC", "ETH", "SOL", "XRP"]

ASSET_KEYWORDS = {
    "BTC": ["bitcoin", "btc", "satoshi"],
    "ETH": ["ethereum", "ether", "eth", "vitalik"],
    "SOL": ["solana", "sol"],
    "XRP": ["xrp", "ripple"],
}

# --- Event categories ----------------------------------------------------
EVENT_CATEGORIES = [
    "etf_institutional",
    "regulation_policy",
    "exchange_market",
    "technology_ecosystem",
    "security_incident",
    "macro_economic",
]

EVENT_CATEGORY_KEYWORDS = {
    "etf_institutional": [
        "etf", "institutional", "blackrock", "fidelity", "grayscale",
        "fund inflow", "fund outflow", "asset manager", "hedge fund",
    ],
    "regulation_policy": [
        "sec ", "regulation", "regulatory", "lawsuit", "congress",
        "senate", "policy", "government", "ban ", "compliance", "cftc",
    ],
    "exchange_market": [
        "exchange", "binance", "coinbase", "kraken", "listing",
        "delisting", "trading volume", "liquidity", "order book",
    ],
    "technology_ecosystem": [
        "upgrade", "hard fork", "mainnet", "testnet", "layer 2",
        "protocol", "developer", "github", "smart contract", "node",
    ],
    "security_incident": [
        "hack", "exploit", "breach", "vulnerability", "stolen",
        "scam", "rug pull", "phishing", "malware",
    ],
    "macro_economic": [
        "federal reserve", "interest rate", "inflation", "cpi",
        "fomc", "recession", "treasury", "gdp", "jobs report",
    ],
}

UNCATEGORIZED_EVENT_CATEGORY = "uncategorized"

# --- OpenAI AI News Analyst ---------------------------------------------
OPENAI_API_KEY_ENV_VAR = "OPENAI_API_KEY"
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

# A small, cost-efficient model: the whole project budget is ~$5, so a
# larger/more expensive model is not appropriate here.
OPENAI_MODEL = "gpt-4o-mini"

OPENAI_REQUEST_TIMEOUT_SECONDS = 30

# Keep prompts short and cheap: truncate the article summary before
# sending it to the model.
MAX_SUMMARY_CHARS_FOR_PROMPT = 600

# Cost-control: AI analysis is user-triggered and batch-limited. These
# bound how many *uncached* articles a single click can analyze.
DEFAULT_ANALYSIS_BATCH_LIMIT = 5
MAX_ANALYSIS_BATCH_LIMIT = 20

SENTIMENT_VALUES = ["bullish", "bearish", "neutral", "mixed"]
IMPACT_LEVEL_VALUES = ["low", "medium", "high"]
IMPACT_HORIZON_VALUES = ["short-term", "medium-term", "long-term", "uncertain"]
