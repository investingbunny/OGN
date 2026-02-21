"""Modern Technical Analysis module with vectorized operations.

This module provides high-performance technical indicator calculations using
Pandas 3.0+ and NumPy. All functions are strictly typed and documented.
"""

import pandas as pd
import numpy as np


def MACD(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    column: str = "Close"
) -> pd.DataFrame:
    """Calculates Moving Average Convergence Divergence (MACD).

    Formula:
        Fast_EMA = EMA(Price, fast, adjust=False)
        Slow_EMA = EMA(Price, slow, adjust=False)
        MACD_Line = Fast_EMA - Slow_EMA
        Signal_Line = EMA(MACD_Line, signal, adjust=False)
        Histogram = MACD_Line - Signal_Line

    Args:
        df: Pandas DataFrame containing the price data.
        fast: Period for the fast EMA. Defaults to 12.
        slow: Period for the slow EMA. Defaults to 26.
        signal: Period for the signal line EMA. Defaults to 9.
        column: The column name to use for calculation. Defaults to "Close".

    Returns:
        pd.DataFrame: DataFrame with MACD, MACD_Signal, and MACD_Hist columns.
    """
    res = pd.DataFrame(index=df.index)
    # Using adjust=False to match standard industry EMA (like TA-Lib)
    fast_ema = df[column].ewm(span=fast, adjust=False, min_periods=fast).mean()
    slow_ema = df[column].ewm(span=slow, adjust=False, min_periods=slow).mean()

    res["MACD"] = fast_ema - slow_ema
    res["MACD_Signal"] = res["MACD"].ewm(span=signal, adjust=False, min_periods=signal).mean()
    res["MACD_Hist"] = res["MACD"] - res["MACD_Signal"]

    return res


def _wilders_smoothing_vectorized(series: pd.Series, period: int) -> pd.Series:
    """Vectorized Wilder's Smoothing.

    Matches TA-Lib and legacy implementation by using SMA for the first
    period and EMA for subsequent periods.
    """
    if len(series) <= period:
        return pd.Series(np.nan, index=series.index)

    # Calculate SMA for the initial period
    sma = series.rolling(window=period, min_periods=period).mean()

    # Legacy code starts at index 'period' (the period+1-th element)
    # for RSI where it uses the diff.
    idx = period

    if idx >= len(series):
        return pd.Series(np.nan, index=series.index)

    # Rest of the series from index 'idx'
    remaining_series = series.iloc[idx:]

    # Seed the EWM with the SMA value at 'idx'
    seed_series = remaining_series.copy()
    seed_series.iloc[0] = sma.iloc[idx]

    ewm = seed_series.ewm(alpha=1/period, adjust=False).mean()

    # Reconstruct full series
    res = pd.Series(np.nan, index=series.index)
    res.iloc[idx:] = ewm
    return res


def RSI(
    df: pd.DataFrame,
    period: int = 14,
    column: str = "Close"
) -> pd.Series:
    """Calculates Relative Strength Index (RSI) using Wilder's Smoothing.

    Matches TA-Lib RSI output and legacy implementation.

    Args:
        df: Pandas DataFrame containing the price data.
        period: Period for RSI calculation. Defaults to 14.
        column: The column name to use for calculation. Defaults to "Close".

    Returns:
        pd.Series: RSI values.
    """
    delta = df[column].diff()

    # In legacy code, delta at index 0 is NaN, and np.where(NaN >= 0, ...) is False.
    # So gain/loss at index 0 becomes 0.
    gain = np.where(delta >= 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)

    avg_gain = _wilders_smoothing_vectorized(pd.Series(gain, index=df.index), period)
    avg_loss = _wilders_smoothing_vectorized(pd.Series(loss, index=df.index), period)

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


def ATR(
    df: pd.DataFrame,
    period: int = 14
) -> pd.Series:
    """Calculates Average True Range (ATR).

    Formula:
        TR = max(High - Low, |High - Close_prev|, |Low - Close_prev|)
        ATR = Wilder_Smoothing(TR, period)

    Args:
        df: Pandas DataFrame with High, Low, Close columns.
        period: Period for ATR. Defaults to 14.

    Returns:
        pd.Series: ATR values.
    """
    h_l = df["High"] - df["Low"]
    h_cp = (df["High"] - df["Close"].shift(1)).abs()
    l_cp = (df["Low"] - df["Close"].shift(1)).abs()

    tr = pd.concat([h_l, h_cp, l_cp], axis=1).max(axis=1)
    atr = _wilders_smoothing_vectorized(tr, period)

    return atr


def ADX(
    df: pd.DataFrame,
    period: int = 14
) -> pd.DataFrame:
    """Calculates Average Directional Index (ADX).

    Args:
        df: Pandas DataFrame with High, Low, Close columns.
        period: Period for ADX. Defaults to 14.

    Returns:
        pd.DataFrame: DataFrame with ADX, +DI, and -DI columns.
    """
    delta_h = df["High"].diff()
    delta_l = df["Low"].shift(1) - df["Low"]

    plus_dm = np.where((delta_h > delta_l) & (delta_h > 0), delta_h, 0.0)
    minus_dm = np.where((delta_l > delta_h) & (delta_l > 0), delta_l, 0.0)

    # Calculate TR
    h_l = df["High"] - df["Low"]
    h_cp = (df["High"] - df["Close"].shift(1)).abs()
    l_cp = (df["Low"] - df["Close"].shift(1)).abs()
    tr = pd.concat([h_l, h_cp, l_cp], axis=1).max(axis=1)

    # Wilder's Smoothing
    tr_n = _wilders_smoothing_vectorized(tr, period)
    plus_dm_n = _wilders_smoothing_vectorized(pd.Series(plus_dm, index=df.index), period)
    minus_dm_n = _wilders_smoothing_vectorized(pd.Series(minus_dm, index=df.index), period)

    plus_di = 100 * (plus_dm_n / tr_n)
    minus_di = 100 * (minus_dm_n / tr_n)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = _wilders_smoothing_vectorized(dx, period)

    res = pd.DataFrame(index=df.index)
    res["ADX"] = adx
    res["plus_DI"] = plus_di
    res["minus_DI"] = minus_di

    return res


def BollBnd(
    df: pd.DataFrame,
    period: int = 20,
    std_dev: int = 2,
    column: str = "Close"
) -> pd.DataFrame:
    """Calculates Bollinger Bands.

    Formula:
        Middle Band = SMA(Price, period)
        Upper Band = Middle Band + (std_dev * Rolling_Std(Price, period))
        Lower Band = Middle Band - (std_dev * Rolling_Std(Price, period))

    Args:
        df: Pandas DataFrame with price data.
        period: Period for Bollinger Bands. Defaults to 20.
        std_dev: Number of standard deviations. Defaults to 2.
        column: Column name to use. Defaults to "Close".

    Returns:
        pd.DataFrame: DataFrame with BB_Mid, BB_Upper, and BB_Lower columns.
    """
    res = pd.DataFrame(index=df.index)
    res["BB_Mid"] = df[column].rolling(window=period).mean()
    std = df[column].rolling(window=period).std(ddof=0)

    res["BB_Upper"] = res["BB_Mid"] + (std_dev * std)
    res["BB_Lower"] = res["BB_Mid"] - (std_dev * std)

    return res


def slope(
    series: pd.Series,
    period: int = 5
) -> pd.Series:
    """Calculates the slope of a rolling linear regression.

    Args:
        series: Pandas Series to calculate slope for.
        period: Rolling window period. Defaults to 5.

    Returns:
        pd.Series: Slope values (in degrees).
    """
    # x values are just [0, 1, 2, ..., period-1]
    x = np.arange(period)
    x_sum = x.sum()
    x2_sum = (x**2).sum()
    denominator = period * x2_sum - x_sum**2

    y_sum = series.rolling(window=period).sum()
    xy_sum = series.rolling(window=period).apply(
        lambda y: (x * y).sum(), raw=True
    )

    slope_val = (period * xy_sum - x_sum * y_sum) / denominator
    slope_angle = np.rad2deg(np.arctan(slope_val))

    return slope_angle


def fibonacci_levels(
    high: float,
    low: float
) -> dict[str, float]:
    """Calculates Fibonacci retracement levels for a given range.

    Levels: 0.236, 0.382, 0.5, 0.618, 0.786.

    Args:
        high: The high price of the range.
        low: The low price of the range.

    Returns:
        dict: A dictionary of Fibonacci levels.
    """
    diff = high - low
    levels = {
        "0.0": low,
        "0.236": low + 0.236 * diff,
        "0.382": low + 0.382 * diff,
        "0.5": low + 0.5 * diff,
        "0.618": low + 0.618 * diff,
        "0.786": low + 0.786 * diff,
        "1.0": high
    }
    return levels
