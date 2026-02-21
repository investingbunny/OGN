"""Modern Financial KPIs module with vectorized operations.

This module provides financial performance metrics using Pandas and NumPy.
All functions are strictly typed and documented.
"""

import pandas as pd
import numpy as np


def CAGR(
    df: pd.DataFrame,
    trading_days: int = 252,
    column: str = "Close"
) -> float:
    """Calculates Cumulative Annual Growth Rate (CAGR).

    Formula:
        Total_Return = (End_Price / Start_Price)
        N_Years = Total_Days / Trading_Days
        CAGR = Total_Return ^ (1 / N_Years) - 1

    Args:
        df: Pandas DataFrame with price data.
        trading_days: Number of trading days in a year. Defaults to 252.
        column: Column name to use. Defaults to "Close".

    Returns:
        float: CAGR value.
    """
    total_return = df[column].iloc[-1] / df[column].iloc[0]
    n_years = len(df) / trading_days
    cagr = (total_return) ** (1 / n_years) - 1
    return float(cagr)


def Volatility(
    df: pd.DataFrame,
    trading_days: int = 252,
    column: str = "Close"
) -> float:
    """Calculates annualized volatility.

    Formula:
        Daily_Returns = Price.pct_change()
        Volatility = Std_Dev(Daily_Returns) * sqrt(Trading_Days)

    Args:
        df: Pandas DataFrame with price data.
        trading_days: Number of trading days in a year. Defaults to 252.
        column: Column name to use. Defaults to "Close".

    Returns:
        float: Annualized volatility.
    """
    daily_ret = df[column].pct_change()
    vol = daily_ret.std() * np.sqrt(trading_days)
    return float(vol)


def Sharpe(
    df: pd.DataFrame,
    rf: float,
    trading_days: int = 252,
    column: str = "Close"
) -> float:
    """Calculates Sharpe Ratio.

    Formula:
        Sharpe = (CAGR - Risk_Free_Rate) / Volatility

    Args:
        df: Pandas DataFrame with price data.
        rf: Risk-free rate (e.g., 0.05 for 5%).
        trading_days: Number of trading days in a year. Defaults to 252.
        column: Column name to use. Defaults to "Close".

    Returns:
        float: Sharpe Ratio.
    """
    return (CAGR(df, trading_days, column) - rf) / Volatility(df, trading_days, column)


def Sortino(
    df: pd.DataFrame,
    rf: float,
    trading_days: int = 252,
    column: str = "Close"
) -> float:
    """Calculates Sortino Ratio.

    Formula:
        Negative_Daily_Returns = Daily_Returns where Daily_Returns < 0
        Downside_Volatility = Std_Dev(Negative_Daily_Returns) * sqrt(Trading_Days)
        Sortino = (CAGR - Risk_Free_Rate) / Downside_Volatility

    Args:
        df: Pandas DataFrame with price data.
        rf: Risk-free rate.
        trading_days: Number of trading days in a year. Defaults to 252.
        column: Column name to use. Defaults to "Close".

    Returns:
        float: Sortino Ratio.
    """
    daily_ret = df[column].pct_change()
    neg_ret = daily_ret[daily_ret < 0]
    # Handle edge case where there are no negative returns
    if neg_ret.empty:
        return np.inf

    downside_vol = neg_ret.std() * np.sqrt(trading_days)
    return (CAGR(df, trading_days, column) - rf) / downside_vol


def Max_dd(
    df: pd.DataFrame,
    column: str = "Close"
) -> float:
    """Calculates Maximum Drawdown (Max_dd).

    Formula:
        Cumulative_Return = (1 + Daily_Returns).cumprod()
        Peak = Cumulative_Return.cummax()
        Drawdown = (Peak - Cumulative_Return) / Peak
        Max_Drawdown = Drawdown.max()

    Args:
        df: Pandas DataFrame with price data.
        column: Column name to use. Defaults to "Close".

    Returns:
        float: Maximum Drawdown value.
    """
    daily_ret = df[column].pct_change().fillna(0)
    cum_return = (1 + daily_ret).cumprod()
    cum_max = cum_return.cummax()
    drawdown = (cum_max - cum_return) / cum_max
    return float(drawdown.max())


def Calmar(
    df: pd.DataFrame,
    trading_days: int = 252,
    column: str = "Close"
) -> float:
    """Calculates Calmar Ratio.

    Formula:
        Calmar = CAGR / Max_Drawdown

    Args:
        df: Pandas DataFrame with price data.
        trading_days: Number of trading days in a year. Defaults to 252.
        column: Column name to use. Defaults to "Close".

    Returns:
        float: Calmar Ratio.
    """
    max_dd = Max_dd(df, column)
    if max_dd == 0:
        return np.inf
    return CAGR(df, trading_days, column) / max_dd
