"""Streamlit dashboard for the Personal AI Crypto Trading System (Phase 1 MVP).

Shows public OHLCV market data from Binance plus EMA20/EMA50/RSI14/MACD
indicators and a simple technical summary. This dashboard is read-only:
it does not place orders and does not use any API keys or secrets.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.analysis.summary import generate_summary
from src.config import DEFAULT_LIMIT, SUPPORTED_INTERVALS, SUPPORTED_SYMBOLS
from src.data.binance_client import BinanceClientError, fetch_ohlcv
from src.indicators.technical import add_all_indicators

st.set_page_config(page_title="AI Crypto Trading System (MVP)", layout="wide")


@st.cache_data(ttl=60)
def load_data(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    df = fetch_ohlcv(symbol, interval, limit)
    return add_all_indicators(df)


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


def main() -> None:
    st.title("Personal AI Crypto Trading System - Phase 1 MVP")
    st.caption(
        "Public market data only. No real trading, no API keys, no leverage. "
        "For informational purposes only - not financial advice."
    )

    with st.sidebar:
        st.header("Settings")
        symbol = st.selectbox("Trading pair", SUPPORTED_SYMBOLS, index=0)
        interval = st.selectbox(
            "Candlestick interval", SUPPORTED_INTERVALS, index=SUPPORTED_INTERVALS.index("1h")
        )
        limit = st.slider("Number of candles", min_value=100, max_value=1000, value=DEFAULT_LIMIT, step=50)
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


if __name__ == "__main__":
    main()
