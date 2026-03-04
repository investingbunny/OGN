# -*- coding: utf-8 -*-
"""
Technical Analysis & Charting for OGN Market Data (v2.0)

Reads from the parquet data store (via OGN.py data loader) and generates
multi-panel technical analysis charts including:
  - MACD, RSI, ADX, OBV, ATR, Bollinger Bands
  - Fibonacci retracements & extensions
  - Max Pain analysis (options)
  - Futures fair-value vs settle-price overlay
  - Renko charts
  - Support / resistance trendlines (optional, requires trendln)

Usage:
    python Option-OGN.py                    # analyse all FnO symbols (interactive)
    python Option-OGN.py RELIANCE             # analyse a single symbol (interactive)
    python Option-OGN.py --pdf                # all FnO symbols → charts/FnO_Analysis.pdf
    python Option-OGN.py --pdf RELIANCE       # single symbol → charts/RELIANCE_Analysis.pdf
    python Option-OGN.py --pdf output.pdf     # custom output file

@author: HRTR
"""

import sys
import math
import datetime
from functools import reduce

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.dates import date2num
import mplfinance as mpf
import pandas as pd
import numpy as np
import seaborn as sns
import statsmodels.api as sm

# Optional: trendln for support/resistance trendlines
try:
    import trendln
    HAS_TRENDLN = True
except ImportError:
    HAS_TRENDLN = False

# Optional: stocktrends for Renko (pip install stocktrends)
try:
    from stocktrends import Renko
    HAS_RENKO = True
except ImportError:
    HAS_RENKO = False

# Optional: talib for statistical functions
try:
    import talib
    HAS_TALIB = True
except ImportError:
    HAS_TALIB = False

# Data loader — reads from MarketData_Parquet/ processed parquet files
from OGN import (
    load_equity,
    load_full_futures,
    load_monthly_options,
    load_index,
    NSEFnOList,
    WATCHLIST,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# File-path references kept for backward compatibility docstrings
DailyOHLCFilePath = "ohlc"          # now {Symbol}.parquet in Equity/Processed
FullFuturesFilePath = "full-futures" # now {Symbol}.parquet in Derivatives/Processed
MonthlyOptionsFilePath = "monthly-options"

RiskFreeRate = 0.065  # ~6.5% annualised (adjust as needed)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def business_days(start, end):
    """Return number of business days between two date(-like) values."""
    s = pd.to_datetime(start)
    e = pd.to_datetime(end)
    if isinstance(s, pd.Series):
        return s.combine(e, lambda a, b: np.busday_count(
            np.datetime64(a, 'D'), np.datetime64(b, 'D')))
    if isinstance(s, pd.Timestamp):
        s = s.to_numpy().astype('datetime64[D]')
    if isinstance(e, pd.Timestamp):
        e = e.to_numpy().astype('datetime64[D]')
    # vectorised for Series/arrays
    return np.busday_count(
        np.asarray(s, dtype='datetime64[D]'),
        np.asarray(e, dtype='datetime64[D]'),
    )


# ---------------------------------------------------------------------------
# Max Pain analysis
# ---------------------------------------------------------------------------

def call_otm(df, focus_date):
    """Out-of-the-money call open interest at each strike for a given date."""
    mask = (df['Date'] == focus_date) & (df['Option type'] == 'CE')
    return df.loc[mask, ['Strike Price', 'Open Int']].copy()


def put_otm(df, focus_date):
    """Out-of-the-money put open interest at each strike for a given date."""
    mask = (df['Date'] == focus_date) & (df['Option type'] == 'PE')
    return df.loc[mask, ['Strike Price', 'Open Int']].copy()


def max_pain_strike(call_sums, put_sums):
    """Compute the strike at which total option-writer pain is minimised.

    For each candidate strike, calculates the total intrinsic value * OI
    that option writers would have to pay out (ITM calls + ITM puts).
    The strike with the lowest total payout is the "max pain" strike.
    """
    strikes = sorted(set(call_sums['Strike Price']).union(set(put_sums['Strike Price'])))
    pain = {}
    for s in strikes:
        # ITM calls: strikes below the candidate settlement price
        itm_calls = call_sums[call_sums['Strike Price'] < s].copy()
        itm_calls['pain'] = (s - itm_calls['Strike Price']) * itm_calls['Open Int']
        # ITM puts: strikes above the candidate settlement price
        itm_puts = put_sums[put_sums['Strike Price'] > s].copy()
        itm_puts['pain'] = (itm_puts['Strike Price'] - s) * itm_puts['Open Int']
        # Total writer payout at this settlement price
        pain[s] = itm_calls['pain'].sum() + itm_puts['pain'].sum()
    if not pain:
        return np.nan
    # Strike that minimises total writer pain
    return min(pain, key=pain.get)


def GetMaxPain(scrip, start_date):
    """Compute Max Pain & PCR for each trading date from start_date onwards.

    Returns DataFrame with columns: Date, MaxPain, PCR
    """
    try:
        opts = load_monthly_options(scrip, start=str(start_date)[:10])
    except FileNotFoundError:
        return pd.DataFrame(columns=['Date', 'MaxPain', 'PCR'])

    if opts.empty:
        return pd.DataFrame(columns=['Date', 'MaxPain', 'PCR'])

    dates = sorted(opts['Date'].unique())
    rows = []
    for d in dates:
        cs = call_otm(opts, d)
        ps = put_otm(opts, d)
        pcr = ps['Open Int'].sum() / cs['Open Int'].sum() if cs['Open Int'].sum() else np.nan
        mp = max_pain_strike(cs, ps)
        rows.append({'Date': d, 'MaxPain': mp, 'PCR': pcr})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Technical indicators (pure computation — work on any OHLCV DataFrame)
# ---------------------------------------------------------------------------

def MACD(DF, a=12, b=26, c=9):
    """MACD, Signal line, and histogram."""
    df = DF.copy()
    df["MA_Fast"] = df["Close"].ewm(span=a, min_periods=a).mean()
    df["MA_Slow"] = df["Close"].ewm(span=b, min_periods=b).mean()
    df["MACD"] = df["MA_Fast"] - df["MA_Slow"]
    df["Signal"] = df["MACD"].ewm(span=c, min_periods=c).mean()
    return df


def RSI(DF, n=14):
    """Wilder-style RSI (Relative Strength Index).

    Uses Wilder's smoothing method: the first average is a simple mean
    over n periods, then each subsequent average is exponentially smoothed
    with factor (n-1)/n.

    Args:
        DF: DataFrame with a 'Close' column.
        n:  Lookback period (default 14).

    Returns:
        Series of RSI values (0–100 scale).
    """
    df = DF.copy()
    delta = df['Close'].diff()
    gain = delta.clip(lower=0)      # Positive price changes only
    loss = (-delta).clip(lower=0)   # Negative changes made positive

    # Seed with NaN for the first n rows (insufficient data)
    avg_gain = [np.nan] * n
    avg_loss = [np.nan] * n
    # First average: simple mean of the first n periods
    avg_gain.append(gain.iloc[1:n + 1].mean())
    avg_loss.append(loss.iloc[1:n + 1].mean())
    # Wilder smoothing: avg = (prev_avg * (n-1) + current) / n
    for i in range(n + 1, len(df)):
        avg_gain.append((avg_gain[-1] * (n - 1) + gain.iloc[i]) / n)
        avg_loss.append((avg_loss[-1] * (n - 1) + loss.iloc[i]) / n)
    df['avg_gain'] = np.array(avg_gain)
    df['avg_loss'] = np.array(avg_loss)
    df['RS'] = df['avg_gain'] / df['avg_loss']  # Relative Strength
    df['RSI'] = 100 - (100 / (1 + df['RS']))    # Normalise to 0–100
    return df['RSI']


def ADX(DF, n=20):
    """Average Directional Index (ADX), DI+, DI-.

    Uses Wilder's smoothing method for TR, DM+, and DM- to compute
    directional indicators (DI+, DI-), then smooths DX into ADX.

    Args:
        DF: DataFrame with 'High', 'Low', 'Close' columns.
        n:  Lookback period (default 20).

    Returns:
        DataFrame with added columns: ADX, DIplusN, DIminusN, DX, etc.
    """
    df2 = DF.copy()
    df2['TR'] = ATR(df2, n)['TR']  # True Range from ATR helper

    # Directional Movement: DM+ = upward move, DM- = downward move
    df2['DMplus'] = np.where(
        (df2['High'] - df2['High'].shift(1)) > (df2['Low'].shift(1) - df2['Low']),
        df2['High'] - df2['High'].shift(1), 0)
    df2['DMplus'] = np.where(df2['DMplus'] < 0, 0, df2['DMplus'])
    df2['DMminus'] = np.where(
        (df2['Low'].shift(1) - df2['Low']) > (df2['High'] - df2['High'].shift(1)),
        df2['Low'].shift(1) - df2['Low'], 0)
    df2['DMminus'] = np.where(df2['DMminus'] < 0, 0, df2['DMminus'])

    # Wilder smoothing for TR, DM+, DM- over n periods
    TRn, DMpN, DMmN = [], [], []
    TR = df2['TR'].tolist()
    DMp = df2['DMplus'].tolist()
    DMm = df2['DMminus'].tolist()
    for i in range(len(df2)):
        if i < n:
            # Not enough data yet
            TRn.append(np.nan)
            DMpN.append(np.nan)
            DMmN.append(np.nan)
        elif i == n:
            # First smoothed value: simple sum of n periods
            TRn.append(df2['TR'].rolling(n).sum().iloc[n])
            DMpN.append(df2['DMplus'].rolling(n).sum().iloc[n])
            DMmN.append(df2['DMminus'].rolling(n).sum().iloc[n])
        else:
            # Wilder smoothing: prev - (prev/n) + current
            TRn.append(TRn[-1] - TRn[-1] / n + TR[i])
            DMpN.append(DMpN[-1] - DMpN[-1] / n + DMp[i])
            DMmN.append(DMmN[-1] - DMmN[-1] / n + DMm[i])
    df2['TRn'] = np.array(TRn)
    df2['DMplusN'] = np.array(DMpN)
    df2['DMminusN'] = np.array(DMmN)

    # Directional Indicators (percentage of smoothed DM to smoothed TR)
    df2['DIplusN'] = 100 * (df2['DMplusN'] / df2['TRn'])
    df2['DIminusN'] = 100 * (df2['DMminusN'] / df2['TRn'])
    df2['DIdiff'] = abs(df2['DIplusN'] - df2['DIminusN'])
    df2['DIsum'] = df2['DIplusN'] + df2['DIminusN']
    df2['DX'] = 100 * (df2['DIdiff'] / df2['DIsum'])  # Directional Index

    # ADX: smoothed DX (needs 2*n - 1 bars before first value)
    adx_vals = []
    DX = df2['DX'].tolist()
    for j in range(len(df2)):
        if j < 2 * n - 1:
            adx_vals.append(np.nan)  # Insufficient data
        elif j == 2 * n - 1:
            # First ADX: simple mean of DX over last n bars
            adx_vals.append(df2['DX'].iloc[j - n + 1:j + 1].mean())
        else:
            # Wilder smoothing: ((n-1) * prev_ADX + current_DX) / n
            adx_vals.append(((n - 1) * adx_vals[-1] + DX[j]) / n)
    df2['ADX'] = np.array(adx_vals)
    return df2


def OBV(DF):
    """On Balance Volume.

    Cumulative volume indicator: adds volume on up-days, subtracts on
    down-days.  Used to confirm price trends via volume flow.
    """
    df = DF.copy()
    df['daily_ret'] = df['Close'].pct_change()
    # Direction: +1 on up/flat days, -1 on down days
    df['direction'] = np.where(df['daily_ret'] >= 0, 1, -1)
    df.iloc[0, df.columns.get_loc('direction')] = 0  # No direction on first bar
    df['vol_adj'] = df['Volume'] * df['direction']
    df['obv'] = df['vol_adj'].cumsum()  # Running cumulative OBV
    return df


def ATR(DF, n=20):
    """True Range and Average True Range.

    TR = max(High-Low, |High-PrevClose|, |Low-PrevClose|)
    ATR = simple rolling mean of TR over n periods.

    Args:
        DF: DataFrame with 'High', 'Low', 'Close' columns.
        n:  Rolling window size (default 20).
    """
    df = DF.copy()
    df['H-L'] = abs(df['High'] - df['Low'])              # Intraday range
    df['H-PC'] = abs(df['High'] - df['Close'].shift(1))  # Gap up component
    df['L-PC'] = abs(df['Low'] - df['Close'].shift(1))   # Gap down component
    df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1, skipna=False)
    df['ATR'] = df['TR'].rolling(n).mean()
    df.drop(['H-L', 'H-PC', 'L-PC'], axis=1, inplace=True)  # Clean up temp cols
    return df


def slope(ser, n=5):
    """Slope of regression line for n consecutive points (degrees).

    Normalises both x (time) and y (price) to [0,1] range, then fits
    OLS regression over rolling windows.  Returns slope angle in degrees.

    Args:
        ser: Price series.
        n:   Rolling window size (default 5).
    """
    # Normalise price to [0, 1] for comparable slope magnitudes
    ser = (ser - ser.min()) / (ser.max() - ser.min())
    x = np.array(range(len(ser)))
    x = (x - x.min()) / (x.max() - x.min())  # Normalise time axis
    slopes = [0.0] * (n - 1)  # Pad initial values
    for i in range(n, len(ser) + 1):
        y_scaled = ser.iloc[i - n:i]
        x_scaled = x[i - n:i]
        x_scaled = sm.add_constant(x_scaled)  # Add intercept term
        model = sm.OLS(y_scaled, x_scaled)
        results = model.fit()
        slopes.append(results.params.iloc[-1])  # Coefficient = slope
    # Convert slope ratio to angle in degrees
    return np.rad2deg(np.arctan(np.array(slopes)))


def BollBnd(DF, n=20):
    """Bollinger Bands (MA ± 2σ) and band width."""
    df = DF.copy()
    df["MA"] = df['Close'].rolling(n).mean()
    df["BB_up"] = df["MA"] + 2 * df['Close'].rolling(n).std(ddof=0)
    df["BB_dn"] = df["MA"] - 2 * df['Close'].rolling(n).std(ddof=0)
    df["BB_width"] = df["BB_up"] - df["BB_dn"]
    return df


# ---------------------------------------------------------------------------
# Renko
# ---------------------------------------------------------------------------

def Renko_DF(DF, ticker):
    """Convert OHLCV data into Renko bricks (requires stocktrends).

    Brick size is set to the 120-period ATR of the source data.

    Args:
        DF:     DataFrame with Date, Open, High, Low, Close, Volume.
        ticker: Symbol name (for logging only).

    Returns:
        Renko OHLC DataFrame, or empty DataFrame if stocktrends is missing.
    """
    if not HAS_RENKO:
        print("  [skip] stocktrends not installed — Renko unavailable")
        return pd.DataFrame()
    df = DF.copy()
    # Select and rename columns to lowercase (stocktrends convention)
    df = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].copy()
    df.rename(columns={"Date": "date", "High": "high", "Low": "low",
                        "Open": "open", "Close": "close", "Volume": "volume"},
              inplace=True)
    df2 = Renko(df)
    # Use 120-period ATR as brick size for adaptive brick scaling
    df2.brick_size = round(ATR(DF, 120)["ATR"].iloc[-1], 0)
    renko_df = df2.get_ohlc_data()
    return renko_df


def PlotRenko(DF, num_bars=100):
    """Plot Renko chart."""
    if DF.empty:
        return
    plt.ioff()
    df = DF.tail(num_bars).copy()
    if len(df) < 2:
        return
    price_move = abs(df.iloc[1]['open'] - df.iloc[1]['close'])

    fig = plt.figure()
    fig.clf()
    axes = fig.gca()

    for idx, (_, row) in enumerate(df.iterrows(), 1):
        op, cl = row['open'], row['close']
        # Green for up-bricks, red for down-bricks
        colour = ('darkgreen', 'green') if op < cl else ('darkred', 'red')
        r = matplotlib.patches.Rectangle(
            (idx, op), 1, cl - op,
            edgecolor=colour[0], facecolor=colour[1], alpha=0.5)
        axes.add_patch(r)

    plt.xlim([0, num_bars])
    plt.ylim([min(df['open'].min(), df['close'].min()),
              max(df['open'].max(), df['close'].max())])
    fig.suptitle(
        f"Bars from {df['date'].min():%d-%b-%Y} to {df['date'].max():%d-%b-%Y}"
        f"\nPrice movement = {price_move}",
        fontsize=14)
    plt.xlabel('Bar Number')
    plt.ylabel('Price')
    plt.grid(True)
    return fig


# ---------------------------------------------------------------------------
# Technical audit table (crossover / momentum / fractal analysis)
# ---------------------------------------------------------------------------

def analyze_stock(data, ticker):
    """Run a multi-factor technical audit on the indicator DataFrame.

    Evaluates crossover signals, momentum, volatility, and fractal
    Fibonacci structure.  Returns a DataFrame with columns:
        Condition, Status, Verdict

    Args:
        data:   DataFrame with pre-computed indicators (Close, EMA/SMA
                columns, MACD, Signal, RSI, BB_up/BB_dn, Volume, etc.).
                Must already be indexed or have the Date column.
        ticker: Symbol name (for display only).
    """
    # Ensure we work with a copy to avoid side-effects
    df = data.copy()

    # Compute any extra EMAs/SMAs that the audit needs but may not exist yet
    for span, col in [(5, 'EMA5'), (9, 'EMA9'), (13, 'EMA13'),
                      (21, 'EMA21'), (48, 'EMA48')]:
        if col not in df.columns:
            src = df['Close'] if 'Close' in df.columns else df.iloc[:, 0]
            df[col] = src.ewm(span=span, adjust=False).mean()
    for window, col in [(20, 'SMA20'), (50, 'SMA50'), (200, 'SMA200')]:
        if col not in df.columns:
            src = df['Close'] if 'Close' in df.columns else df.iloc[:, 0]
            df[col] = src.rolling(window=window).mean()

    # Map existing indicator column names to the short names used here
    ema_map = {'5DMA-E': 'EMA5', '9DMA-E': 'EMA9', '13DMA-E': 'EMA13',
               '21DMA-E': 'EMA21', '48DMA-E': 'EMA48'}
    sma_map = {'20DMA': 'SMA20', '50DMA': 'SMA50', '200DMA': 'SMA200'}
    for old, new in {**ema_map, **sma_map}.items():
        if old in df.columns and new not in df.columns:
            df[new] = df[old]

    # --- Fractal Fibonacci (last 60 bars ≈ 3 months) ---
    recent = df.tail(60)
    swing_high = recent['High'].max() if 'High' in recent.columns else recent['Close'].max()
    swing_low = recent['Low'].min() if 'Low' in recent.columns else recent['Close'].min()
    fib618 = swing_high - (0.382 * (swing_high - swing_low))

    # --- Current bar values ---
    curr = df.iloc[-1]
    vol_avg = df['Volume'].rolling(20).mean().iloc[-1] if 'Volume' in df.columns else 0

    results = []

    # 1. Crossover categories
    results.append(["Inst: 50/200 SMA",
                    "Yes" if curr.get('SMA50', np.nan) > curr.get('SMA200', np.nan) else "No",
                    "Bullish Market Regime"])
    results.append(["Mom: 9/21 EMA",
                    "Yes" if curr.get('EMA9', np.nan) > curr.get('EMA21', np.nan) else "No",
                    "Short-term acceleration"])
    results.append(["Trend: 13/48 EMA",
                    "Yes" if curr.get('EMA13', np.nan) > curr.get('EMA48', np.nan) else "No",
                    "Confirmed trend run"])
    results.append(["Hybrid: 5E / 20S",
                    "Yes" if curr.get('EMA5', np.nan) > curr.get('SMA20', np.nan) else "No",
                    "Price aggressive vs mean"])

    # 2. Momentum & volatility
    macd_val = curr.get('MACD', np.nan)
    sig_val = curr.get('Signal', np.nan)
    results.append(["MACD > Signal",
                    "Yes" if macd_val > sig_val else "No",
                    "Momentum engine firing"])
    rsi_val = curr.get('RSI', np.nan)
    results.append(["RSI > 60",
                    "Yes" if rsi_val > 60 else "No",
                    "Super-Bullish zone"])
    sma20_val = curr.get('SMA20', curr.get('MA', np.nan))
    results.append(["Close > BB Mid",
                    "Yes" if curr['Close'] > sma20_val else "No",
                    "Bullish volatility channel"])

    # 3. Fractal structure & filters
    results.append([f"Fib > 61.8% ({fib618:.0f})",
                    "Yes" if curr['Close'] > fib618 else "No",
                    "Holding above pivot"])
    if vol_avg > 0:
        results.append(["Volume > 1.2× avg",
                        "Yes" if curr.get('Volume', 0) > (vol_avg * 1.2) else "No",
                        "Big players confirming"])

    return pd.DataFrame(results, columns=["Condition", "Status", "Verdict"])


# ---------------------------------------------------------------------------
# Main chart builder
# ---------------------------------------------------------------------------

def plot_chart(DF, n, ticker, Dividend=0, pdf_pages=None):
    """Generate the multi-panel technical analysis chart.

    Args:
        DF:        DataFrame with indicators already computed
        n:         Number of trailing bars to display
        ticker:    Symbol name
        Dividend:  Expected dividend (for futures fair-value calc)
        pdf_pages: Optional PdfPages object — if set, saves to PDF instead of plt.show()
    """
    data = DF.copy()

    # Renko chart
    if HAS_RENKO:
        renkodata = Renko_DF(data, ticker)
        renko_fig = PlotRenko(renkodata, 100)
        if renko_fig:
            if pdf_pages:
                pdf_pages.savefig(renko_fig)
                plt.close(renko_fig)
            else:
                plt.show()

    data = data.iloc[-n:]

    # ── Try loading options / futures for overlay ──────────────────────
    Mpdf = None
    Futdf = None

    try:
        opts_start = data.iloc[0].Date
        Mpdf = GetMaxPain(ticker, opts_start)
        if not Mpdf.empty:
            data = pd.merge(data, Mpdf, on='Date', how='outer')
    except Exception:
        pass

    try:
        ReadFuturesdf = load_full_futures(ticker)
        if not ReadFuturesdf.empty:
            d = data.iloc[0].Date - pd.Timedelta(days=1)
            FuturesSlice = ReadFuturesdf[ReadFuturesdf.Date > d]
            Futdf = FuturesSlice[['Date', 'Expiry', 'Settle Price', 'Open Int']].copy()
            Futdf = Futdf.sort_values(by=['Date', 'Expiry']).reset_index(drop=True)

            SettlePricedf = Futdf.groupby('Date')['Settle Price'].apply(
                lambda x: pd.Series(list(x))).unstack().reset_index()
            OpenInterestdf = Futdf.groupby('Date')['Open Int'].apply(
                lambda x: pd.Series(list(x))).unstack().reset_index()
            ExpiryDatedf = Futdf.groupby('Date')['Expiry'].apply(
                lambda x: pd.Series(list(x))).unstack().reset_index()

            ExpiryDatedf.rename(columns={0: 'NearExpiry', 1: 'MidExpiry', 2: 'FarExpiry'}, inplace=True)
            OpenInterestdf.rename(columns={0: 'NearOpenInterest', 1: 'MidOpenInterest', 2: 'FarOpenInterest'}, inplace=True)
            SettlePricedf.rename(columns={0: 'NearSettlePrice', 1: 'MidSettlePrice', 2: 'FarSettlePrice'}, inplace=True)

            dfs = [ExpiryDatedf, OpenInterestdf, SettlePricedf]
            Futdf = reduce(lambda left, right: pd.merge(left, right, on='Date'), dfs)
            Futdf = pd.merge(data, Futdf, on='Date', how='outer')
    except Exception:
        Futdf = None

    # ── Set Date as index for plotting ────────────────────────────────
    data.index = pd.to_datetime(data["Date"])
    data.drop("Date", axis=1, inplace=True)

    # ── Build OHLC list for candlestick (date as matplotlib number) ───
    ohlc = []
    for dt, row in data.iterrows():
        ohlc.append([date2num(dt), row['Open'], row['High'], row['Low'], row['Close']])

    # ── Figure 2: main analysis panels (7-panel layout) ────────────
    fig2 = plt.figure(figsize=(54, 30))  # Increased from (48, 27)

    # Margins: left/right 5%, top/bottom 5% leaves 90% for content
    # Left column: 0.05 to 0.47 (width=0.42)
    # Right column: 0.52 to 0.95 (width=0.43)
    # Plot area: 0.06 to 0.95 (height=0.89)
    
    # Left column (4 panels): MACD, RSI/ADX, Fibonacci, Bollinger/OBV
    ax_macd = fig2.add_axes((0.05, 0.75, 0.42, 0.20))
    ax_rsi = fig2.add_axes((0.05, 0.52, 0.42, 0.20), sharex=ax_macd)
    ax_fibret = fig2.add_axes((0.05, 0.29, 0.42, 0.20), sharex=ax_macd)
    ax_bba = fig2.add_axes((0.05, 0.06, 0.42, 0.20), sharex=ax_macd)

    # Right column: EMA (top), SMA (mid), bottom split into left/right halves
    ax_ema = fig2.add_axes((0.53, 0.75, 0.42, 0.20), sharex=ax_macd)
    ax_sma = fig2.add_axes((0.53, 0.52, 0.42, 0.20), sharex=ax_macd)
    # Bottom-right left half: futures / max-pain (placeholder, currently unused)
    ax_bottom_left = fig2.add_axes((0.53, 0.06, 0.20, 0.42))
    ax_bottom_left.axis('off')  # Reserve space; can be used for futures overlay later
    # Bottom-right right half: technical audit table
    ax_table = fig2.add_axes((0.74, 0.06, 0.21, 0.42))
    ax_table.axis('off')

    ax_macd.xaxis_date()  # Format x-axis as dates

    for col in ["5DMA-E", "9DMA-E", "13DMA-E", "21DMA-E", "48DMA-E"]:
        if col in data.columns:
            ax_ema.plot(data.index, data[col], label=col)
    ax_ema.plot(data.index, data['Close'], color='black', linestyle=':', linewidth=2.5, label=f"{ticker} Price", zorder=10)
    ax_ema.legend()
    ax_ema.grid(True)

    # ── SMA panel ─────────────────────────────────────────────────────
    for col in ["20DMA", "50DMA", "200DMA"]:
        if col in data.columns:
            ax_sma.plot(data.index, data[col], label=col)
    ax_sma.plot(data.index, data['Close'], color='black', linestyle=':', linewidth=2.5, label=f"{ticker} Price", zorder=10)
    ax_sma.legend()
    ax_sma.grid(True)

    # ── MACD panel ────────────────────────────────────────────────────
    ax_macd.plot(data.index, data["MACD"], label="MACD")
    ax_macd.bar(data.index, (data["MACD"] - data["Signal"]) * 3, label="hist")
    ax_macd.plot(data.index, data["Signal"], label="Signal")
    ax_macd.legend()
    ax_macd.grid(True)

    # ── RSI & ADX panel ───────────────────────────────────────────────
    ax_rsi.set_ylabel("(%)")
    ax_rsi.axhline(70, color='grey', linestyle='--', label="overbought")
    ax_rsi.axhline(30, color='grey', linestyle='--', label="oversold")
    ax_rsi.axhline(50, color='grey', linestyle=':')
    ax_rsi.plot(data.index, data["RSI"], label="RSI", color='lightpink')
    if 'ADX' in data.columns:
        ax_rsi.plot(data.index, data["ADX"], label="ADX", color='blue')
    if 'DIplusN' in data.columns:
        ax_rsi.plot(data.index, data["DIplusN"], label="DI+", color='green')
    if 'DIminusN' in data.columns:
        ax_rsi.plot(data.index, data["DIminusN"], label="DI-", color='red')
    ax_rsi.legend()
    ax_rsi.grid(True)

    # ── Bollinger Bands + OBV panel ───────────────────────────────────
    ax_bba.plot(data.index, data["BB_up"], label="BB_up")
    ax_bba.plot(data.index, data["BB_dn"], label="BB_dn")
    ax_bba.plot(data.index, data["MA"], label="MA")
    ax_bba.plot(data.index, data['Close'], color='black', linestyle=':', linewidth=2.5, label='Close Price', zorder=10)
    ax_bba.legend()
    ax_bba.grid(True)

    if 'OBV' in data.columns:
        ax_obv = ax_bba.twinx()
        ax_obv.plot(data.index, data["OBV"] / 100000, marker="*", label="OBV")
        ax_obv.set_ylabel('OBV')
        ax_obv.grid(visible=False)

    # ── Fibonacci retracements ────────────────────────────────────────
    price_min = data.Low.min()
    price_max = data.High.max()
    diff = price_max - price_min

    fib_levels = [
        (0.236, 'lightcoral'), (0.382, 'lightsalmon'), (0.5, 'mistyrose'),
        (0.618, 'greenyellow'), (0.786, 'lime'),
    ]
    prev = price_min
    for ratio, colour in fib_levels:
        level = price_min + ratio * diff
        ax_fibret.axhspan(prev, level, alpha=0.4, color=colour,
                          label=f'{level:.1f} ({ratio})')
        prev = level
    ax_fibret.axhspan(prev, price_max, alpha=0.5, color='green',
                      label=f'{price_max:.1f} (1)')
    ax_fibret.legend()
    ax_fibret.grid(True)

    # Candlestick overlay on Fibonacci panel using mplfinance-compatible OHLC
    # (Using simple line plot since mplfinance add_plot requires different setup)
    ax_fibret.plot(data.index, data['Close'], color='black', linestyle=':', linewidth=2.5, label='Close Price', zorder=10)

    # ── Technical Audit Table (bottom-right) ──────────────────────────
    try:
        report = analyze_stock(data, ticker)
        # Build colour list: green for "Yes", red for "No"
        cell_colours = []
        for _, row in report.iterrows():
            status_colour = '#c6efce' if row['Status'] == 'Yes' else '#ffc7ce'
            cell_colours.append(['#f2f2f2', status_colour, '#f2f2f2'])

        tbl = ax_table.table(
            cellText=report.values,
            colLabels=report.columns,
            cellColours=cell_colours,
            colColours=['#4472c4'] * 3,
            cellLoc='center',
            loc='upper center',
        )
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(8)
        tbl.scale(1.0, 1.5)  # Stretch rows for readability
        # Style header row
        for (r, c), cell in tbl.get_celld().items():
            if r == 0:
                cell.set_text_props(color='white', fontweight='bold')
            cell.set_edgecolor('#cccccc')
        ax_table.set_title(f"{ticker} — Technical Audit", fontsize=10,
                           fontweight='bold', pad=8)
    except Exception as e:
        ax_table.text(0.5, 0.5, f"Audit error:\n{e}",
                      transform=ax_table.transAxes, ha='center', va='center',
                      fontsize=9, color='red')

    if pdf_pages:
        pdf_pages.savefig(fig2)
        plt.close(fig2)
    else:
        plt.show()

    # ── Trendlines (optional) ─────────────────────────────────────────
    if HAS_TRENDLN:
        try:
            tl_data = data.copy()
            mins, maxs = trendln.calc_support_resistance(
                (tl_data['Low'], tl_data['High']))
            fig3 = trendln.plot_sup_res_date(
                (tl_data['Low'], tl_data['High']), tl_data.index)
            fig3.set_size_inches((16, 9))
            if pdf_pages:
                pdf_pages.savefig(fig3)
                plt.close(fig3)
            else:
                plt.show()
            plt.clf()
        except Exception as e:
            print(f"  [warn] trendln failed: {e}")


# ---------------------------------------------------------------------------
# Main analysis orchestrator
# ---------------------------------------------------------------------------

def FnOAnalysis(scrip_list=None, single_scrip=None, pdf_path=None):
    """Run technical analysis for each symbol in the list.

    Args:
        scrip_list:   List of symbols to analyse (default: NSEFnOList)
        single_scrip: If set, analyse only this one symbol
        pdf_path:     If set, save all charts to this PDF file
    """
    if single_scrip:
        symbols = [single_scrip]
    elif scrip_list:
        symbols = scrip_list
    else:
        symbols = NSEFnOList

    # Set non-interactive backend for PDF output
    pdf_pages = None
    if pdf_path:
        matplotlib.use('Agg')
        from pathlib import Path
        Path(pdf_path).parent.mkdir(parents=True, exist_ok=True)
        pdf_pages = PdfPages(pdf_path)
        print(f"  Saving charts to: {pdf_path}")

    for Scrip in symbols:
        print(f"\n{'='*60}")
        print(f"  Analysing: {Scrip}")
        print(f"{'='*60}")

        # ── Load equity OHLC data ─────────────────────────────────────
        try:
            OHLCdf = load_equity(Scrip)
        except FileNotFoundError:
            # Try loading as index
            try:
                OHLCdf = load_index(Scrip)
            except FileNotFoundError:
                print(f"  [skip] No data found for {Scrip}")
                continue

        if OHLCdf.empty:
            print(f"  [skip] Empty data for {Scrip}")
            continue

        # ── Compute indicators ────────────────────────────────────────
        Indicatordf = OHLCdf.copy()
        Indicatordf = Indicatordf.set_index("Date")

        # --- Momentum indicators ---
        Indicatordf = MACD(Indicatordf, 12, 26, 9)       # MACD (12/26/9)
        Indicatordf["RSI"] = RSI(Indicatordf, 14)        # RSI (14-period)

        # --- Volatility indicators ---
        Indicatordf = BollBnd(Indicatordf, 20)            # Bollinger Bands (20-period)
        Indicatordf = ATR(Indicatordf, 20)                # Average True Range (20-period)

        # --- Trend strength ---
        ADXdf = ADX(Indicatordf, 20)                      # ADX (20-period Wilder)
        Indicatordf['ADX'] = ADXdf['ADX']
        Indicatordf['DIplusN'] = ADXdf['DIplusN']         # Bullish directional indicator
        Indicatordf['DIminusN'] = ADXdf['DIminusN']       # Bearish directional indicator

        # Smoothed ADX: 5-day and 15-day rolling means
        Indicatordf['ADXRoll5'] = Indicatordf['ADX'].rolling(5).mean()
        Indicatordf['ADXRoll10'] = Indicatordf['ADX'].rolling(15).mean()

        # --- Volume indicators ---
        Indicatordf['VolRoll5'] = Indicatordf['Volume'].rolling(5).mean()   # 5-day avg volume
        Indicatordf['VolRoll10'] = Indicatordf['Volume'].rolling(10).mean() # 10-day avg volume

        OBVdf = OBV(Indicatordf)                          # On Balance Volume
        Indicatordf["OBV"] = OBVdf["obv"]
        Indicatordf["Daily_Ret"] = OBVdf['daily_ret']
        Indicatordf["Log_Ret"] = np.log(1 + OBVdf['daily_ret'])  # Log returns for stats

        # --- Beta via talib (optional) ---
        if HAS_TALIB:
            Indicatordf["Beta"] = talib.BETA(
                Indicatordf["High"], Indicatordf["Low"], timeperiod=14)

        # --- Regression slope (5-bar rolling) ---
        Indicatordf["Slope"] = slope(Indicatordf["Close"], 5)

        # --- Moving averages ---
        # Simple Moving Averages (SMA)
        for w in [20, 50, 200]:
            Indicatordf[f"{w}DMA"] = Indicatordf["Close"].rolling(window=w).mean()
        # Exponential Moving Averages (EMA)
        for w in [5, 9, 13, 21, 48]:
            Indicatordf[f"{w}DMA-E"] = Indicatordf["Close"].ewm(
                span=w, adjust=False).mean()

        Indicatordf.reset_index(inplace=True)

        # ── Plot ──────────────────────────────────────────────────────
        plot_chart(Indicatordf, 60, Scrip, 0, pdf_pages=pdf_pages)

    if pdf_pages:
        pdf_pages.close()
        print(f"\n  PDF saved: {pdf_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """CLI entry point.

    Usage:
        python Option-OGN.py                    # interactive, all FnO
        python Option-OGN.py RELIANCE             # interactive, single symbol
        python Option-OGN.py --pdf                # PDF, all FnO → charts/FnO_Analysis.pdf
        python Option-OGN.py --pdf RELIANCE       # PDF, single → charts/RELIANCE_Analysis.pdf
        python Option-OGN.py --pdf output.pdf     # PDF, all FnO → output.pdf
    """
    args = sys.argv[1:]
    use_pdf = '--pdf' in args
    if use_pdf:
        args.remove('--pdf')

    symbol = None
    pdf_path = None

    for arg in args:
        if arg.lower().endswith('.pdf'):
            pdf_path = arg
        else:
            symbol = arg.upper()

    if use_pdf and not pdf_path:
        if symbol:
            pdf_path = f"charts/{symbol}_Analysis.pdf"
        else:
            pdf_path = "charts/FnO_Analysis.pdf"

    FnOAnalysis(single_scrip=symbol, pdf_path=pdf_path if use_pdf else None)


if __name__ == "__main__":
    main()
