"""Generates a simple, human-readable technical summary from indicators.

This is a rule-based summary only - it does not place trades, does not
give financial advice, and is for informational purposes only.
"""

from __future__ import annotations

import pandas as pd

RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30


def generate_summary(df: pd.DataFrame, symbol: str) -> str:
    """Build a short plain-language summary of the latest indicator values.

    Args:
        df: DataFrame with columns close, ema_20, ema_50, rsi_14,
            macd, macd_signal produced by add_all_indicators.
        symbol: Trading pair name, e.g. "BTCUSDT", used in the text.

    Returns:
        A multi-line string summarizing trend, momentum and MACD signal.
    """
    required_columns = {"close", "ema_20", "ema_50", "rsi_14", "macd", "macd_signal"}
    missing = required_columns - set(df.columns)
    if missing:
        raise ValueError(f"DataFrame is missing required columns: {missing}")
    if df.empty:
        raise ValueError("DataFrame is empty; cannot generate a summary")

    latest = df.iloc[-1]
    lines = [f"Technical summary for {symbol}", f"Latest close: {latest['close']:.4f}"]

    # Trend: based on EMA20 vs EMA50 ("golden cross" style comparison).
    if pd.isna(latest["ema_20"]) or pd.isna(latest["ema_50"]):
        lines.append("Trend: not enough data yet to compare EMA20/EMA50.")
    elif latest["ema_20"] > latest["ema_50"]:
        lines.append(
            "Trend: EMA20 is above EMA50, suggesting a short-term uptrend."
        )
    elif latest["ema_20"] < latest["ema_50"]:
        lines.append(
            "Trend: EMA20 is below EMA50, suggesting a short-term downtrend."
        )
    else:
        lines.append("Trend: EMA20 and EMA50 are essentially equal (sideways).")

    # Momentum: based on RSI14.
    rsi = latest["rsi_14"]
    if pd.isna(rsi):
        lines.append("Momentum: not enough data yet to compute RSI14.")
    elif rsi >= RSI_OVERBOUGHT:
        lines.append(f"Momentum: RSI14 is {rsi:.1f}, in overbought territory (>= {RSI_OVERBOUGHT}).")
    elif rsi <= RSI_OVERSOLD:
        lines.append(f"Momentum: RSI14 is {rsi:.1f}, in oversold territory (<= {RSI_OVERSOLD}).")
    else:
        lines.append(f"Momentum: RSI14 is {rsi:.1f}, in a neutral range.")

    # MACD: compare MACD line to signal line.
    if pd.isna(latest["macd"]) or pd.isna(latest["macd_signal"]):
        lines.append("MACD: not enough data yet to compare MACD/signal lines.")
    elif latest["macd"] > latest["macd_signal"]:
        lines.append("MACD: MACD line is above the signal line (bullish bias).")
    elif latest["macd"] < latest["macd_signal"]:
        lines.append("MACD: MACD line is below the signal line (bearish bias).")
    else:
        lines.append("MACD: MACD line and signal line are essentially equal.")

    lines.append(
        "Note: This is an automated technical summary for information only, "
        "not financial advice. No trades are placed by this system."
    )

    return "\n".join(lines)
