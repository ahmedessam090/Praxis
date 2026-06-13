"""Hand-rolled indicators (ATR / SMA / OBV) — no external TA dependency."""

from __future__ import annotations

import numpy as np
import pandas as pd


def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    true_range = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(length, min_periods=1).mean()


def sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(length, min_periods=1).mean()


def obv(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["close"].diff().fillna(0.0))
    return (direction * df["volume"]).cumsum()


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False, min_periods=1).mean()


def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / length, adjust=False, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1.0 / length, adjust=False, min_periods=length).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return (100.0 - 100.0 / (1.0 + rs)).fillna(100.0)


def atr_pct(df: pd.DataFrame, length: int = 14) -> pd.Series:
    return 100.0 * atr(df, length) / df["close"]


def dollar_volume(df: pd.DataFrame) -> pd.Series:
    return df["close"] * df["volume"]


def avg_dollar_volume(df: pd.DataFrame, length: int = 20) -> pd.Series:
    return dollar_volume(df).rolling(length, min_periods=1).mean()


def relative_volume(df: pd.DataFrame, length: int = 20) -> pd.Series:
    avg = df["volume"].rolling(length, min_periods=1).mean()
    return df["volume"] / avg.replace(0.0, np.nan)


def rolling_high(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(length, min_periods=1).max()


def rolling_low(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(length, min_periods=1).min()


def realized_vol(series: pd.Series, length: int = 20) -> pd.Series:
    logret = np.log(series / series.shift(1))
    return logret.rolling(length, min_periods=2).std() * np.sqrt(252.0) * 100.0
