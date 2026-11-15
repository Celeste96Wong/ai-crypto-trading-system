"""Streamlit dashboard for the Personal AI Crypto Trading System.

Two sections:
- Market Data (Phase 1/1.1): public OHLCV market data from Binance plus
  EMA20/EMA50/RSI14/MACD indicators and a simple technical summary.
- News Intelligence (Phase 2): free RSS crypto news, local
  classification, and optional, user-triggered OpenAI analysis.

This dashboard is read-only: it does not place orders, does not use
any Binance API keys/secrets, and does not run automated trading. AI
news analysis is entirely optional and only ever runs when the user
clicks a button - never on a timer or in the background.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.analysis.summary import generate_summary
from src.config import DEFAULT_LIMIT, SUPPORTED_INTERVALS, SUPPORTED_SYMBOLS
from src.data.binance_client import BinanceClientError, fetch_ohlcv
from src.indicators.technical import add_all_indicators
from src.news.ai_analyst import (
    OpenAIAnalysisError,
    analyze_articles,
    is_configured as is_ai_configured,
)
from src.news.collector import collect_and_store_news
from src.news.config import DEFAULT_ANALYSIS_BATCH_LIMIT, MAX_ANALYSIS_BATCH_LIMIT
from src.news.storage import NewsStorage

st.set_page_config(page_title="AI Crypto Trading System (MVP)", layout="wide")

_SENTIMENT_EMOJI = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪", "mixed": "🟡"}


@st.cache_data(ttl=60)
def load_data(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    df = fetch_ohlcv(symbol, interval, limit)
    return add_all_indicators(df)


@st.cache_resource
def get_news_storage() -> NewsStorage:
    return NewsStorage()


def render_price_chart(df: pd.DataFrame, symbol: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name=symbol,
        )
    )
    fig.add_trace(
        go.Scatter(x=df.index, y=df["ema_20"], name="EMA 20", line=dict(width=1.5))
    )
    fig.add_trace(
        go.Scatter(x=df.index, y=df["ema_50"], name="EMA 50", line=dict(width=1.5))
    )
    fig.update_layout(
        title=f"{symbol} price with EMA20 / EMA50",
        xaxis_title="Time (UTC)",
        yaxis_title="Price (USDT)",
        height=500,
        xaxis_rangeslider_visible=False,
    )
    return fig


def render_rsi_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["rsi_14"], name="RSI 14"))
    fig.add_hline(y=70, line_dash="dash", line_color="red")
    fig.add_hline(y=30, line_dash="dash", line_color="green")
    fig.update_layout(title="RSI 14", height=250, yaxis_range=[0, 100])
    return fig


def render_macd_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df.index, y=df["macd_histogram"], name="Histogram"))
    fig.add_trace(go.Scatter(x=df.index, y=df["macd"], name="MACD"))
    fig.add_trace(go.Scatter(x=df.index, y=df["macd_signal"], name="Signal"))
    fig.update_layout(title="MACD", height=250)
    return fig


def render_market_data_tab() -> None:
    with st.sidebar:
        st.header("Market Data Settings")
        symbol = st.selectbox("Trading pair", SUPPORTED_SYMBOLS, index=0)
        interval = st.selectbox(
            "Candlestick interval", SUPPORTED_INTERVALS, index=SUPPORTED_INTERVALS.index("1h")
        )
        limit = st.slider(
            "Number of candles", min_value=100, max_value=1000, value=DEFAULT_LIMIT, step=50
        )
        refresh = st.button("Refresh data")

    if refresh:
        st.cache_data.clear()

    try:
        df = load_data(symbol, interval, limit)
    except BinanceClientError as exc:
        st.error(f"Could not load market data: {exc}")
        st.stop()

    st.info(
        "All charts, indicators and the summary below are calculated using "
        "only fully closed candles. The most recent, still-forming candle "
        "is excluded to avoid misleading signals."
    )

    col_chart, col_summary = st.columns([3, 1])

    with col_chart:
        st.plotly_chart(render_price_chart(df, symbol), use_container_width=True)
        st.plotly_chart(render_rsi_chart(df), use_container_width=True)
        st.plotly_chart(render_macd_chart(df), use_container_width=True)

    with col_summary:
        st.caption(
            "Indicators and summary use only fully closed candles. "
            f"Latest completed candle (UTC): {df.index[-1]}"
        )
        st.subheader("Technical Summary")
        st.text(generate_summary(df, symbol))

        st.subheader("Latest values")
        latest = df.iloc[-1]
        st.metric("Close", f"{latest['close']:.4f}")
        st.metric("EMA 20", f"{latest['ema_20']:.4f}")
        st.metric("EMA 50", f"{latest['ema_50']:.4f}")
        st.metric("RSI 14", f"{latest['rsi_14']:.2f}")
        st.metric("MACD", f"{latest['macd']:.4f}")
        st.metric("MACD Signal", f"{latest['macd_signal']:.4f}")

    with st.expander("Raw data"):
        st.dataframe(df.tail(50))


def render_news_article_card(article, storage: NewsStorage) -> None:
    analysis = storage.get_analysis(article.article_id)

    with st.container(border=True):
        st.markdown(f"#### [{article.title}]({article.url})")
        st.caption(
            f"{article.source} · {article.published_at.strftime('%Y-%m-%d %H:%M UTC')}"
        )

        tag_parts = []
        if article.assets:
            tag_parts.append("Assets: " + ", ".join(article.assets))
        else:
            tag_parts.append("Assets: none identified")
        if article.event_categories:
            tag_parts.append("Categories: " + ", ".join(article.event_categories))
        st.caption(" | ".join(tag_parts))

        if article.summary:
            st.write(article.summary)

        if analysis is not None:
            emoji = _SENTIMENT_EMOJI.get(analysis.sentiment, "")
            st.markdown(
                f"**AI analysis** {emoji} sentiment: `{analysis.sentiment}` | "
                f"impact: `{analysis.impact_level}` | "
                f"confidence: `{analysis.confidence}/100` | "
                f"horizon: `{analysis.impact_horizon}`"
            )
            st.caption(analysis.short_summary)
            with st.expander("Full AI reasoning"):
                st.write(f"**Potential market impact:** {analysis.potential_market_impact}")
                st.write(f"**Reasoning:** {analysis.reasoning}")
                st.write(
                    "**Affected assets:** "
                    + (", ".join(analysis.affected_assets) or "None identified")
                )
                st.caption(f"Model: {analysis.model or 'unknown'}")
        else:
            st.caption("Not yet analyzed by AI.")


def render_news_tab() -> None:
    st.header("News Intelligence")
    st.caption(
        "Free RSS news sources only - no paid news API. AI analysis is "
        "optional, user-triggered, and never runs automatically. Nothing "
        "in this section places trades or guarantees any price movement."
    )

    storage = get_news_storage()

    col_refresh, col_analyze = st.columns([1, 2])

    with col_refresh:
        if st.button("🔄 Refresh news"):
            with st.spinner("Fetching latest headlines from RSS feeds..."):
                fetched, new_count, errors = collect_and_store_news(storage)
            st.success(f"Fetched {fetched} article(s), {new_count} new.")
            for error in errors:
                st.warning(error)

    with col_analyze:
        batch_limit = st.number_input(
            "Articles to analyze per click",
            min_value=1,
            max_value=MAX_ANALYSIS_BATCH_LIMIT,
            value=DEFAULT_ANALYSIS_BATCH_LIMIT,
            help=(
                "Caps how many not-yet-analyzed articles a single click "
                "sends to the OpenAI API, to keep costs predictable."
            ),
        )
        if st.button("🤖 Analyze with AI"):
            pending = storage.get_unanalyzed_articles(limit=int(batch_limit))
            if not pending:
                st.info("No unanalyzed articles right now.")
            else:
                with st.spinner(f"Analyzing {len(pending)} article(s) with AI..."):
                    try:
                        results, errors = analyze_articles(
                            pending, storage, limit=int(batch_limit)
                        )
                    except OpenAIAnalysisError as exc:
                        results, errors = [], [str(exc)]
                if results:
                    st.success(f"Analyzed {len(results)} article(s).")
                for error in errors:
                    st.warning(error)

    if not is_ai_configured():
        st.info(
            "AI analysis is unavailable: set the OPENAI_API_KEY environment "
            "variable to enable it. News collection and classification "
            "below work fine without it."
        )

    articles = storage.get_recent_articles(limit=30)
    if not articles:
        st.info(
            "No articles collected yet. Click 'Refresh news' above to fetch "
            "the latest headlines."
        )
        return

    for article in articles:
        render_news_article_card(article, storage)


def main() -> None:
    st.title("Personal AI Crypto Trading System")
    st.caption(
        "Public market data and free news sources only. No real trading, "
        "no API keys stored in code, no leverage. For informational "
        "purposes only - not financial advice."
    )

    tab_market, tab_news = st.tabs(["📈 Market Data", "📰 News Intelligence"])

    with tab_market:
        render_market_data_tab()

    with tab_news:
        render_news_tab()


if __name__ == "__main__":
    main()
