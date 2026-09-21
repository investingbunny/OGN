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
  - Support / resistance regression trendlines (scipy pivots + numpy polyfit)

Report pages: technical -> trendlines -> volatility -> comparison, then separate
Japan, US Schiller and India Schiller appendices once per PDF.
Edit REPORT_SECTIONS to drop any of them.

Usage:
    python Option-OGN.py                          # analyse all FnO symbols (interactive)
    python Option-OGN.py WTI                       # full analysis for one series
    python Option-OGN.py WTI US02Y__US10Y          # ... plus a statistical comparison
    python Option-OGN.py WTI US02Y__US10Y 250      # ... over the last 250 observations
    python Option-OGN.py --pdf WTI JP10Y 120      # last 120 aligned months
    python Option-OGN.py --pdf WTI JP10Y --compare-aggregation last
    python Option-OGN.py --pdf WTI JP10Y --compare-frequency quarterly
    python Option-OGN.py --estimator Raw WTI       # pick the volatility estimator
    python Option-OGN.py --trend-bars 250 GLD      # widen the trendline lookback
    python Option-OGN.py --trend-distance 20 GLD   # demand 20 bars between pivots
    python Option-OGN.py --trend-prominence 5 GLD  # absolute prominence, in price units
    python Option-OGN.py --trend-prominence-pct 5 GLD  # auto-scale off 5% of the range
    python Option-OGN.py --pdf                     # all FnO symbols -> charts/FnO_Analysis.pdf
    python Option-OGN.py --pdf WTI                 # single symbol -> charts/WTI_Analysis.pdf
    python Option-OGN.py --pdf output.pdf          # custom output file

@author: HRTR
"""

import io
import sys
import math
import datetime
import warnings
import contextlib
import textwrap
from functools import reduce

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.dates import date2num, AutoDateLocator, ConciseDateFormatter
from matplotlib.ticker import FuncFormatter
import mplfinance as mpf
import pandas as pd
import numpy as np
import seaborn as sns
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller, coint, grangercausalitytests
from scipy.stats import norm
from scipy.signal import find_peaks
import japan_macro
import nifty_macro
import schiller_macro

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

# Dynamic Time Warping. The compiled C extension is optional, so probe it once
# here rather than per call and fall back to the pure-Python implementation.
try:
    from dtaidistance import dtw as _dtw
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        try:
            _dtw.distance_fast(np.zeros(3), np.zeros(3))
            HAS_DTW_C = True
        except Exception:
            HAS_DTW_C = False
    HAS_DTW = True
except ImportError:
    _dtw = None
    HAS_DTW = False
    HAS_DTW_C = False

# Mutual information (k-NN / Kraskov estimator)
try:
    from sklearn.feature_selection import mutual_info_regression
    HAS_SKLEARN = True
except ImportError:
    mutual_info_regression = None
    HAS_SKLEARN = False

# Volatility estimators - one module per model, each exposing get_estimator()
try:
    import models
    HAS_MODELS = True
except ImportError:
    models = None
    HAS_MODELS = False

# Data loader — reads from MarketData_Parquet/ processed parquet files
from OGN import (
    load_equity,
    load_full_futures,
    load_monthly_options,
    load_index,
    NSEFnOList,
    WATCHLIST,
    _load_parquet,
    EQUITY_PROCESSED,
    DERIVATIVES_PROCESSED,
    INDICES_PROCESSED,
    SHORTSELLING_PROCESSED,
    VOLATILITY_PROCESSED,
    MARKETACTIVITY_PROCESSED,
    PRICEBAND_PROCESSED,
    PERATIO_PROCESSED,
    CORPBONDS_PROCESSED,
    DELIVERY_PROCESSED,
    WDM_PROCESSED,
    MACRO_PROCESSED,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# File-path references kept for backward compatibility docstrings
DailyOHLCFilePath = "ohlc"          # now {Symbol}.parquet in Equity/Processed
FullFuturesFilePath = "full-futures" # now {Symbol}.parquet in Derivatives/Processed
MonthlyOptionsFilePath = "monthly-options"

RiskFreeRate = 0.065  # ~6.5% annualised (adjust as needed)

# ── Report composition ────────────────────────────────────────────────────
# Comment out any line to drop that section from the generated report.
REPORT_SECTIONS = [
    'technical',    # multi-panel indicator chart for the first symbol
    'trendlines',   # candlestick page with support / resistance regression lines
    'volatility',   # volatility cone / rolling / histogram page
    'comparison',   # statistical comparison, only when a second symbol is given
    'japan_macro',
    'schiller_macro',
    'india_schiller',
]

# ── Trendline page defaults (override on the CLI) ─────────────────────────
TREND_BARS = 180              # Trailing bars fed to the pivot search
TREND_DISTANCE = 12           # Minimum bars between two pivots of the same kind
TREND_PROMINENCE_PCT = 0.02   # Pivot must clear 2% of the window's high-low range
TREND_RESISTANCE_COLOUR = '#ef5350'
TREND_SUPPORT_COLOUR = '#26a69a'

# Comment out any line to drop that panel from the volatility page.
VOLATILITY_PANELS = [
    'cone',
    'box',
    'rolling',
    'histogram',
    'summary',
]

# Estimator modules, each exposing get_estimator(price_data, window, clean).
ESTIMATORS = [
    'GarmanKlass',
    'HodgesTompkins',
    'Kurtosis',
    'Parkinson',
    'Raw',
    'RogersSatchell',
    'Skew',
    'YangZhang',
]
DEFAULT_ESTIMATOR = 'YangZhang'

# Skew and Kurtosis are distribution moments, not volatilities, so they are
# labelled as plain numbers rather than percentages.
MOMENT_ESTIMATORS = {'Skew', 'Kurtosis'}

# These need a real intraday high/low range and read as zero on flat bars.
RANGE_ESTIMATORS = {'GarmanKlass', 'Parkinson', 'RogersSatchell'}

VOLATILITY_WINDOWS = [3, 5, 10, 20, 30, 60, 90]  # Cone x-axis
VOLATILITY_WINDOW = 30                            # Rolling / histogram window
VOLATILITY_QUANTILES = [0.25, 0.75]


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

    Because x is evenly spaced, the rolling least-squares slope reduces to a
    fixed-weight dot product, so this is computed by convolution rather than
    by fitting one regression per row.

    Args:
        ser: Price series.
        n:   Rolling window size (default 5).
    """
    values = np.asarray(ser, dtype=float)
    count = len(values)
    if n < 2 or count < n:
        return np.zeros(count)

    span = values.max() - values.min()
    y = (values - values.min()) / span if span > 0 else np.zeros(count)
    step = 1.0 / (count - 1)  # x is the index normalised to [0, 1]

    offsets = np.arange(n) - (n - 1) / 2.0
    denominator = step * np.sum(offsets ** 2)
    rolling = np.convolve(y, offsets[::-1], mode='valid') / denominator

    slopes = np.concatenate([np.zeros(n - 1), rolling])
    return np.rad2deg(np.arctan(slopes))


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
    # Use ATR as brick size — try 120-period first, fall back to shorter
    # periods for recently-listed symbols with limited history
    brick = np.nan
    for period in [120, 60, 20, 10]:
        if len(DF) >= period:
            brick = ATR(DF, period)["ATR"].iloc[-1]
            if not np.isnan(brick):
                break
    if np.isnan(brick) or brick <= 0:
        # Last resort: use simple range of last available bar
        brick = max((DF['High'] - DF['Low']).median(), 1)
        print(f"  [warn] ATR unavailable for {ticker}, using median range ({brick:.0f}) as brick size")
    df2.brick_size = round(brick, 0)
    renko_df = df2.get_ohlc_data()
    return renko_df


def PlotRenko(DF, num_bars=100, ax=None):
    """Plot Renko chart.

    Args:
        DF:       Renko OHLC DataFrame from Renko_DF().
        num_bars: Number of trailing bricks to display.
        ax:       Optional matplotlib Axes to draw on.  If None a new
                  standalone figure is created and returned.

    Returns:
        The figure object when *ax* is None, otherwise None (draws
        in-place on the supplied axes).
    """
    if DF.empty:
        return None
    plt.ioff()
    df = DF.tail(num_bars).copy()
    if len(df) < 2:
        return None
    price_move = abs(df.iloc[1]['open'] - df.iloc[1]['close'])

    # If no axes supplied, create a standalone figure
    standalone = ax is None
    if standalone:
        fig = plt.figure()
        fig.clf()
        ax = fig.gca()

    for idx, (_, row) in enumerate(df.iterrows(), 1):
        op, cl = row['open'], row['close']
        # Green for up-bricks, red for down-bricks
        colour = ('darkgreen', 'green') if op < cl else ('darkred', 'red')
        r = matplotlib.patches.Rectangle(
            (idx, op), 1, cl - op,
            edgecolor=colour[0], facecolor=colour[1], alpha=0.5)
        ax.add_patch(r)

    ax.set_xlim([0, num_bars])
    ax.set_ylim([min(df['open'].min(), df['close'].min()),
                 max(df['open'].max(), df['close'].max())])
    ax.set_xlabel('Bar #', fontsize=30)
    ax.set_ylabel('Price', fontsize=30)
    ax.tick_params(labelsize=20)
    ax.grid(True)
    ax.set_title(
        f"Renko  |  {df['date'].min():%d-%b-%Y} \u2192 {df['date'].max():%d-%b-%Y}"
        f"  |  brick = {price_move:.0f}",
        fontsize=30, fontweight='bold', pad=6)

    if standalone:
        return fig
    return None


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

    # Compute Renko bricks (plotted later on the main figure)
    renkodata = pd.DataFrame()
    if HAS_RENKO:
        try:
            renkodata = Renko_DF(data, ticker)
        except Exception as e:
            print(f"  [warn] Renko failed for {ticker}: {e}")

    # Clamp display window to available data
    n = min(n, len(data))
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
    # Bottom-right left half: Renko chart (independent axes, no sharex)
    ax_renko = fig2.add_axes((0.53, 0.06, 0.20, 0.42))
    # Bottom-right right half: technical audit table
    ax_table = fig2.add_axes((0.74, 0.06, 0.21, 0.42))
    ax_table.axis('off')

    ax_macd.xaxis_date()  # Format x-axis as dates

    for col in ["5DMA-E", "9DMA-E", "13DMA-E", "21DMA-E", "48DMA-E"]:
        if col in data.columns:
            ax_ema.plot(data.index, data[col], label=col)
    ax_ema.plot(data.index, data['Close'], color='black', linestyle=':', linewidth=2.5, label=f"{ticker} Price", zorder=10)
    ax_ema.legend(fontsize=20)
    ax_ema.grid(True)
    ax_ema.tick_params(labelsize=20)
    ax_ema.set_title('EMA Crossover', fontsize=30, fontweight='bold', pad=8)

    # ── SMA panel ─────────────────────────────────────────────────────
    for col in ["20DMA", "50DMA", "200DMA"]:
        if col in data.columns:
            ax_sma.plot(data.index, data[col], label=col)
    ax_sma.plot(data.index, data['Close'], color='black', linestyle=':', linewidth=2.5, label=f"{ticker} Price", zorder=10)
    ax_sma.legend(fontsize=20)
    ax_sma.grid(True)
    ax_sma.tick_params(labelsize=20)
    ax_sma.set_title('SMA Crossover', fontsize=30, fontweight='bold', pad=8)

    # ── MACD panel ────────────────────────────────────────────────────
    ax_macd.plot(data.index, data["MACD"], label="MACD")
    ax_macd.bar(data.index, (data["MACD"] - data["Signal"]) * 3, label="hist")
    ax_macd.plot(data.index, data["Signal"], label="Signal")
    ax_macd.legend(fontsize=20)
    ax_macd.grid(True)
    ax_macd.tick_params(labelsize=20)
    ax_macd.set_title('MACD (12, 26, 9)', fontsize=30, fontweight='bold', pad=8)

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
    ax_rsi.legend(fontsize=20)
    ax_rsi.grid(True)
    ax_rsi.tick_params(labelsize=20)
    ax_rsi.set_title('RSI & ADX', fontsize=30, fontweight='bold', pad=8)

    # ── Bollinger Bands + OBV panel ───────────────────────────────────
    ax_bba.plot(data.index, data["BB_up"], label="BB_up")
    ax_bba.plot(data.index, data["BB_dn"], label="BB_dn")
    ax_bba.plot(data.index, data["MA"], label="MA")
    ax_bba.plot(data.index, data['Close'], color='black', linestyle=':', linewidth=2.5, label='Close Price', zorder=10)
    ax_bba.legend(fontsize=20)
    ax_bba.grid(True)
    ax_bba.tick_params(labelsize=20)
    ax_bba.set_title('Bollinger Bands & OBV', fontsize=30, fontweight='bold', pad=8)

    if 'OBV' in data.columns:
        ax_obv = ax_bba.twinx()
        ax_obv.plot(data.index, data["OBV"] / 100000, marker="*", label="OBV")
        ax_obv.set_ylabel('OBV')
        ax_obv.tick_params(labelsize=20)
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
    ax_fibret.legend(fontsize=20)
    ax_fibret.grid(True)
    ax_fibret.tick_params(labelsize=20)
    ax_fibret.set_title('Fibonacci Retracements', fontsize=30, fontweight='bold', pad=8)

    # Candlestick overlay on Fibonacci panel using mplfinance-compatible OHLC
    # (Using simple line plot since mplfinance add_plot requires different setup)
    ax_fibret.plot(data.index, data['Close'], color='black', linestyle=':', linewidth=2.5, label='Close Price', zorder=10)

    # ── Renko chart (bottom-left of right column) ─────────────────────
    if not renkodata.empty:
        PlotRenko(renkodata, 100, ax=ax_renko)
    else:
        ax_renko.axis('off')
        ax_renko.text(0.5, 0.5, 'Renko unavailable',
                      transform=ax_renko.transAxes, ha='center', va='center',
                      fontsize=9, color='grey')

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
        tbl.set_fontsize(23)
        tbl.scale(1.0, 6.0)  # Stretch rows for readability
        # Style header row
        for (r, c), cell in tbl.get_celld().items():
            if r == 0:
                cell.set_text_props(color='white', fontweight='bold')
            cell.set_edgecolor('#cccccc')
        ax_table.set_title(f"{ticker} — Technical Audit", fontsize=30,
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


# ---------------------------------------------------------------------------
# Support / resistance trendlines (scipy pivots + OLS regression)
# ---------------------------------------------------------------------------

def find_pivots(highs, lows, distance=TREND_DISTANCE, prominence=None,
                prominence_pct=TREND_PROMINENCE_PCT):
    """Locate resistance peaks and support valleys with scipy.signal.find_peaks.

    Support valleys are found by running the same peak search over the negated
    lows.  `prominence` is taken as an absolute price move when supplied;
    otherwise it is derived from the window's own high-low range so one setting
    works on a 25,000-point index and on a 0.5 yield ratio alike.

    Returns:
        (resistance_idx, support_idx, prominence_used)
    """
    span = float(np.nanmax(highs) - np.nanmin(lows))
    if prominence is None:
        prominence = span * prominence_pct
    # A dead-flat window has no span to scale off, and find_peaks rejects 0.
    if not np.isfinite(prominence) or prominence <= 0:
        prominence = None

    resistance_idx, _ = find_peaks(highs, distance=distance, prominence=prominence)
    support_idx, _ = find_peaks(-lows, distance=distance, prominence=prominence)
    return resistance_idx, support_idx, prominence


def fit_pivot_line(x, y, pivot_idx, fallback):
    """Least-squares line through the pivots, or a flat line if there are <2.

    x is the sequential bar number, never the date, so the fit is immune to
    calendar gaps and to matplotlib's date scaling.

    Returns:
        (slope, intercept, fitted)
    """
    if len(pivot_idx) >= 2:
        slope_, intercept_ = np.polyfit(x[pivot_idx], y[pivot_idx], 1)
        return float(slope_), float(intercept_), True
    return 0.0, float(fallback), False


def compute_trendlines(price_data, bars=TREND_BARS, distance=TREND_DISTANCE,
                       prominence=None, prominence_pct=TREND_PROMINENCE_PCT):
    """Fit support and resistance regression lines over the last `bars` rows.

    Args:
        price_data:     Date-indexed frame carrying Open/High/Low/Close.
        bars:           Trailing bars to fit over; None or 0 uses all history.
        distance:       Minimum bars between two pivots of the same kind.
        prominence:     Absolute prominence in price units; None auto-scales.
        prominence_pct: Fraction of the window range used when auto-scaling.

    Returns:
        dict holding the window, pivot indices, line coefficients, the
        mplfinance `alines` payload and the derived channel statistics.
    """
    frame = price_data.copy()
    missing = {'Open', 'High', 'Low', 'Close'} - set(frame.columns)
    if missing:
        raise ValueError(f"missing OHLC columns: {', '.join(sorted(missing))}")

    if not isinstance(frame.index, pd.DatetimeIndex):
        frame.index = pd.DatetimeIndex(pd.to_datetime(frame.index, errors='coerce'))
    frame = frame[frame.index.notna()].sort_index()

    for column in ('Open', 'High', 'Low', 'Close'):
        frame[column] = pd.to_numeric(frame[column], errors='coerce')
    frame = frame.dropna(subset=['Open', 'High', 'Low', 'Close'])
    if 'Volume' in frame.columns:
        frame['Volume'] = pd.to_numeric(frame['Volume'], errors='coerce').fillna(0.0)
    else:
        frame['Volume'] = 0.0

    window = frame.tail(bars) if bars else frame
    minimum = 2 * distance + 1
    if len(window) < minimum:
        raise ValueError(
            f"only {len(window)} usable bars - need at least {minimum} to fit "
            f"two pivots {distance} bars apart.")

    highs = window['High'].to_numpy(dtype=float)
    lows = window['Low'].to_numpy(dtype=float)
    x = np.arange(len(window))

    resistance_idx, support_idx, prominence_used = find_pivots(
        highs, lows, distance, prominence, prominence_pct)

    slope_res, intercept_res, fitted_res = fit_pivot_line(
        x, highs, resistance_idx, highs.mean())
    slope_sup, intercept_sup, fitted_sup = fit_pivot_line(
        x, lows, support_idx, lows.mean())

    last = len(window) - 1
    res_start, res_end = intercept_res, slope_res * last + intercept_res
    sup_start, sup_end = intercept_sup, slope_sup * last + intercept_sup

    start_date, end_date = window.index[0], window.index[-1]
    alines = [
        [(start_date, res_start), (end_date, res_end)],
        [(start_date, sup_start), (end_date, sup_end)],
    ]

    width_start, width_end = res_start - sup_start, res_end - sup_end
    if width_start > 0 and width_end > 0:
        ratio = width_end / width_start
        channel = ('widening' if ratio > 1.05
                   else 'narrowing' if ratio < 0.95 else 'parallel')
    else:
        channel = 'crossed'  # the fitted lines intersect inside the window

    return {
        'window': window,
        'bars': len(window),
        'resistance_idx': resistance_idx,
        'support_idx': support_idx,
        'prominence': prominence_used,
        'prominence_pct': None if prominence is not None else prominence_pct,
        'resistance': {'slope': slope_res, 'intercept': intercept_res,
                       'start': res_start, 'end': res_end, 'fitted': fitted_res},
        'support': {'slope': slope_sup, 'intercept': intercept_sup,
                    'start': sup_start, 'end': sup_end, 'fitted': fitted_sup},
        'alines': alines,
        'channel': channel,
        'width_start': width_start,
        'width_end': width_end,
    }


def _trend_line_summary(line):
    """One monospaced stats row describing a fitted trendline."""
    if not line['fitted']:
        return "           flat fallback - too few pivots to fit"
    move = line['end'] - line['start']
    if line['start'] != 0:
        change = f"{move / abs(line['start']) * 100:+.1f}% over window"
    else:
        change = f"{move:+.4g} over window"
    return f"           slope {line['slope']:+.4g}/bar   {change}"


def plot_trendlines(profile, ticker, pdf_pages=None):
    """Render the price page with the two regression trendlines overlaid."""
    window = profile['window']
    resistance_idx = profile['resistance_idx']
    support_idx = profile['support_idx']

    style = mpf.make_mpf_style(base_mpf_style='charles', gridstyle='',
                               rc={'font.size': 15})

    # An all-NaN addplot upsets mplfinance, so only mark pivots that exist.
    addplots = []
    for idx, source, marker, colour in (
            (resistance_idx, 'High', 'v', TREND_RESISTANCE_COLOUR),
            (support_idx, 'Low', '^', TREND_SUPPORT_COLOUR)):
        if len(idx) == 0:
            continue
        marks = pd.Series(np.nan, index=window.index)
        marks.iloc[idx] = window[source].to_numpy(dtype=float)[idx]
        addplots.append(mpf.make_addplot(
            marks, type='scatter', marker=marker, markersize=90, color=colour))

    # Flat-bar sources (macro, ratios) collapse candles to invisible dots.
    flat = not _has_intraday_range(window)

    title = (f"\n{ticker}   Regression Trendlines   |   "
             f"{window.index[0]:%d-%b-%Y} \u2192 {window.index[-1]:%d-%b-%Y}   |   "
             f"{profile['bars']:,} bars"
             + ("   |   flat bars: line view" if flat else ""))

    # Flat-bar sources carry Volume 0, so the volume axis gets a zero-height
    # ylim; keep the panel, drop matplotlib's complaint about it.
    with warnings.catch_warnings():
        warnings.filterwarnings(
            'ignore', message='Attempting to set identical low and high ylims')
        figure, axes = mpf.plot(
            window,
            type='line' if flat else 'candle',
            style=style,
            volume=True,
            alines=dict(alines=profile['alines'],
                        colors=[TREND_RESISTANCE_COLOUR, TREND_SUPPORT_COLOUR],
                        linewidths=2.5,
                        alpha=0.85),
            addplot=addplots if addplots else None,
            figsize=(30, 17),
            title=dict(title=title, fontsize=30, fontweight='bold'),
            ylabel='Price',
            ylabel_lower='Volume',
            returnfig=True,
        )

    if profile['prominence'] is None:
        prominence_row = "Prominence n/a - flat window, every local high accepted"
    elif profile['prominence_pct'] is None:
        prominence_row = f"Prominence {profile['prominence']:.4g}  (absolute)"
    else:
        prominence_row = (f"Prominence {profile['prominence']:.4g}  "
                          f"({profile['prominence_pct'] * 100:.1f}% of range)")

    lines = [
        f"Resistance {len(resistance_idx)} pivots",
        _trend_line_summary(profile['resistance']),
        f"Support    {len(support_idx)} pivots",
        _trend_line_summary(profile['support']),
        f"Channel    {profile['channel']} "
        f"({profile['width_start']:.4g} \u2192 {profile['width_end']:.4g})",
        prominence_row,
    ]
    # A rising trend leaves the top-left corner empty, a falling one the right.
    rising = profile['resistance']['slope'] >= 0
    box_x, box_align = (0.012, 'left') if rising else (0.988, 'right')
    axes[0].text(
        box_x, 0.97, "\n".join(lines), transform=axes[0].transAxes,
        va='top', ha=box_align, ma='left', fontsize=15, family='monospace',
        bbox=dict(boxstyle='round,pad=0.6', facecolor='white', alpha=0.85,
                  edgecolor='#cccccc'))

    if pdf_pages:
        pdf_pages.savefig(figure)
        plt.close(figure)
    else:
        plt.show()


def trendline_analysis(price_data, ticker, bars=TREND_BARS,
                       distance=TREND_DISTANCE, prominence=None,
                       prominence_pct=TREND_PROMINENCE_PCT, pdf_pages=None):
    """Compute and render the trendline page for one symbol."""
    profile = compute_trendlines(price_data, bars=bars, distance=distance,
                                 prominence=prominence,
                                 prominence_pct=prominence_pct)

    used = profile['prominence']
    print(f"  [trendlines] {profile['bars']} bars, "
          f"{len(profile['resistance_idx'])} resistance / "
          f"{len(profile['support_idx'])} support pivots, "
          f"prominence {'none' if used is None else format(used, '.4g')}, "
          f"channel {profile['channel']}")

    plot_trendlines(profile, ticker, pdf_pages=pdf_pages)
    return profile


# ---------------------------------------------------------------------------
# Main analysis orchestrator
# ---------------------------------------------------------------------------

def FnOAnalysis(scrip_list=None, single_scrip=None, pdf_path=None,
                compare_with=None, days=None, estimator=DEFAULT_ESTIMATOR,
                trend_bars=TREND_BARS, trend_distance=TREND_DISTANCE,
                trend_prominence=None,
                trend_prominence_pct=TREND_PROMINENCE_PCT,
                comparison_frequency='auto', comparison_aggregation='auto'):
    """Run technical analysis for each symbol in the list.

    Sections are driven by REPORT_SECTIONS, so any of them can be commented out.

    Args:
        scrip_list:           List of symbols to analyse (default: NSEFnOList)
        single_scrip:         If set, analyse only this one symbol
        pdf_path:             If set, save all charts to this PDF file
        compare_with:         If set, append a statistical comparison of the
                              analysed symbol against this second series
        days:                 Window in aligned observations (legacy parameter name)
        estimator:            Volatility estimator name (see ESTIMATORS)
        trend_bars:           Trailing bars used by the trendline page
        trend_distance:       Minimum bars between two trendline pivots
        trend_prominence:     Absolute pivot prominence; None auto-scales
        trend_prominence_pct: Fraction of the window range used when
                              auto-scaling the prominence
        comparison_frequency: auto chooses the slower native cadence
        comparison_aggregation: auto, mean, last or sum for downsampled series
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

        # ── Load OHLC data from whichever source holds this symbol ─────
        try:
            OHLCdf, source_desc = load_analysis_frame(Scrip)
            print(f"  Source: {source_desc}")
        except (FileNotFoundError, ValueError) as e:
            print(f"  [skip] {e}")
            continue

        if OHLCdf.empty:
            print(f"  [skip] Empty data for {Scrip}")
            continue

        # ── Ensure OHLCV columns are numeric (parquet may store as string) ──
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if col in OHLCdf.columns:
                OHLCdf[col] = pd.to_numeric(OHLCdf[col], errors='coerce')

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
        # Series that can print negative (e.g. WTI in Apr 2020) make 1+r <= 0
        _daily_ret = OBVdf['daily_ret']
        Indicatordf["Log_Ret"] = np.log(_daily_ret.where(_daily_ret > -1) + 1)

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
        if 'technical' in REPORT_SECTIONS:
            display_bars = min(25, len(Indicatordf))
            plot_chart(Indicatordf, display_bars, Scrip, 0, pdf_pages=pdf_pages)

        # ── Support / resistance trendlines ───────────────────────────
        if 'trendlines' in REPORT_SECTIONS:
            try:
                trendline_analysis(OHLCdf.set_index('Date'), Scrip,
                                   bars=trend_bars, distance=trend_distance,
                                   prominence=trend_prominence,
                                   prominence_pct=trend_prominence_pct,
                                   pdf_pages=pdf_pages)
            except (ValueError, KeyError) as e:
                print(f"  [trendlines skipped] {e}")

        # ── Volatility profile ────────────────────────────────────────
        if 'volatility' in REPORT_SECTIONS:
            try:
                volatility_analysis(OHLCdf.set_index('Date'), Scrip,
                                    estimator=estimator, pdf_pages=pdf_pages)
            except (ValueError, KeyError) as e:
                print(f"  [volatility skipped] {e}")

        # ── Appended statistical comparison ───────────────────────────
        if compare_with and 'comparison' in REPORT_SECTIONS:
            try:
                compare_series(Scrip, compare_with, days=days,
                               pdf_pages=pdf_pages, frequency=comparison_frequency,
                               aggregation=comparison_aggregation)
            except (ValueError, FileNotFoundError) as e:
                print(f"  [comparison skipped] {e}")

    if pdf_pages:
        try:
            if 'japan_macro' in REPORT_SECTIONS:
                plot_japan_macro(pdf_pages=pdf_pages)
            if 'schiller_macro' in REPORT_SECTIONS:
                plot_schiller_macro(pdf_pages=pdf_pages)
            if 'india_schiller' in REPORT_SECTIONS:
                plot_india_schiller(pdf_pages=pdf_pages)
        finally:
            pdf_pages.close()
        print(f"\n  PDF saved: {pdf_path}")


# ---------------------------------------------------------------------------
# COMP — pairwise statistical comparison across any two data series
# ---------------------------------------------------------------------------

COMP_MAX_LAG = 10        # Lags scanned by Granger causality and cross-correlation
COMP_MIN_OBS = 60        # Below this the estimators are not worth reporting
DTW_MAX_POINTS = 1000    # Series are resampled to this length before DTW
DTW_BAND_FRACTION = 0.1  # Sakoe-Chiba band as a fraction of series length
RATIO_OPERATOR = '__'    # NUM__DEN, e.g. US02Y__US10Y

# Searched in order, so a bare symbol resolves to the most likely source first.
_COMP_SOURCES = [
    ("Macro", MACRO_PROCESSED),
    ("Equity", EQUITY_PROCESSED),
    ("Index", INDICES_PROCESSED),
    ("Derivatives", DERIVATIVES_PROCESSED),
    ("Volatility", VOLATILITY_PROCESSED),
    ("PE Ratio", PERATIO_PROCESSED),
    ("Short Selling", SHORTSELLING_PROCESSED),
    ("Delivery", DELIVERY_PROCESSED),
    ("Corporate Bonds", CORPBONDS_PROCESSED),
    ("Price Band", PRICEBAND_PROCESSED),
    ("Market Activity", MARKETACTIVITY_PROCESSED),
    ("WDM", WDM_PROCESSED),
]

# First match wins when reducing a source frame to one comparable number.
_COMP_VALUE_COLUMNS = [
    'Close', 'Value', 'Settle Price', 'PE', 'Daily Volatility',
    'Annl Volatility', 'Deliverable Qty', 'Qty Short Sold', 'Traded Value',
]

_COMP_SKIP_COLUMNS = {'Date', 'Strike Price', 'Sr No', 'Open Int',
                      'Change in OI', 'Record Type'}

COMP_FREQUENCIES = ('daily', 'weekly', 'monthly', 'quarterly', 'annual')
COMP_PERIOD_RULES = {'daily': 'D', 'weekly': 'W-FRI', 'monthly': 'M',
                     'quarterly': 'Q-DEC', 'annual': 'Y-DEC'}
COMP_LAG_UNITS = {'daily': 'observations', 'weekly': 'weeks', 'monthly': 'months',
                  'quarterly': 'quarters', 'annual': 'years'}
COMP_MIN_PERIOD_COVERAGE = 0.8
_COMP_FLOW_SYMBOLS = {'INTRADEBAL', 'JPCURRENT', 'USRETAIL'}
_COMP_STOCK_SYMBOLS = {'FEDASSETS', 'PAYEMS', 'JPXBYEN', 'JPFOREIGN', 'JPCOTSHORT', 'SCHBV'}
_COMP_FLOW_COLUMNS = {'Volume', 'Deliverable Qty', 'Qty Short Sold', 'Traded Value'}


def _comp_native_frequency(series):
    """Prefer declared frequency; infer cadence only for legacy data without it."""
    declared = str(series.attrs.get('frequency', '')).strip().lower()
    if declared:
        if declared in ('yearly', 'annually'):
            declared = 'annual'
        if declared not in COMP_FREQUENCIES:
            raise ValueError(f"Unsupported frequency metadata: '{declared}'.")
        return declared, 'metadata'
    if len(series) < 3:
        raise ValueError('At least three dates or Frequency metadata are needed to infer cadence.')
    spacing = series.index.to_series().diff().dt.total_seconds().dropna() / 86400.0
    typical_gap = spacing.median()
    for frequency, lower, upper in [('daily', 0, 3), ('weekly', 4, 10),
                                     ('monthly', 20, 45), ('quarterly', 60, 110),
                                     ('annual', 300, 400)]:
        if lower < typical_gap <= upper:
            return frequency, 'inferred'
    raise ValueError('Irregular or unsupported cadence; provide accurate Frequency metadata.')


def align_comparison_series(series_a, series_b, label_a, label_b,
                            frequency='auto', aggregation='auto'):
    """Align at the slower cadence, without upsampling or filling missing periods."""
    if frequency not in ('auto', *COMP_FREQUENCIES):
        raise ValueError(f'Unknown comparison frequency: {frequency}')
    if aggregation not in ('auto', 'mean', 'last', 'sum'):
        raise ValueError(f'Unknown comparison aggregation: {aggregation}')
    cleaned = []
    native_frequencies = []
    frequency_sources = []
    for original in (series_a, series_b):
        series = pd.Series(pd.to_numeric(original, errors='coerce').to_numpy(),
                           index=pd.to_datetime(original.index, errors='coerce'))
        if series.index.tz is not None:
            series.index = series.index.tz_localize(None)
        series.index = series.index.normalize()
        series = series[series.index.notna() & np.isfinite(series)]
        series = series.groupby(level=0).mean().sort_index()
        series.attrs = dict(original.attrs)
        if series.empty:
            raise ValueError('No finite dated observations available for comparison.')
        native, origin = _comp_native_frequency(series)
        cleaned.append(series)
        native_frequencies.append(native)
        frequency_sources.append(origin)
    slowest = max(native_frequencies, key=COMP_FREQUENCIES.index)
    target = slowest if frequency == 'auto' else frequency
    if COMP_FREQUENCIES.index(target) < COMP_FREQUENCIES.index(slowest):
        raise ValueError(f'Cannot upsample {slowest} data to {target}; choose {slowest} or slower.')

    aggregated = []
    methods = []
    open_periods = []
    incomplete_periods = []
    consolidated_weeks = []
    today = pd.Timestamp(datetime.date.today())
    for series, native in zip(cleaned, native_frequencies):
        method = series.attrs.get('aggregation', 'mean') if aggregation == 'auto' else aggregation
        repeated_weeks = 0
        if native == 'weekly':
            weeks = series.index.to_period(COMP_PERIOD_RULES['weekly'])
            repeated_weeks = int(weeks.duplicated().sum())
            series = series[~weeks.duplicated(keep='last')]
        consolidated_weeks.append(repeated_weeks)
        if target == native:
            method = 'last'
        if target == 'daily':
            grouped = series[series.index <= today]
            open_periods.append(0)
            incomplete_periods.append(0)
        else:
            periods = series.index.to_period(COMP_PERIOD_RULES[target])
            if native == target and periods.duplicated().any():
                raise ValueError(f'Multiple {native} observations in one period; check Frequency metadata.')
            grouped = series.groupby(periods).agg(method)
            closed = grouped.index.to_timestamp(how='end').normalize() < today
            open_periods.append(int((~closed).sum()))
            grouped = grouped[closed]
            sufficient = pd.Series(True, index=grouped.index)
            if native == 'daily':
                weekdays = series.index.dayofweek < 5
                counts = series[weekdays].groupby(periods[weekdays]).size()
                starts = grouped.index.to_timestamp().to_numpy().astype('datetime64[D]')
                ends = (grouped.index + 1).to_timestamp().to_numpy().astype('datetime64[D]')
                expected = np.busday_count(starts, ends)
                sufficient = counts.reindex(grouped.index, fill_value=0) >= expected * COMP_MIN_PERIOD_COVERAGE
            elif native in ('monthly', 'quarterly') and native != target:
                expected = {'monthly': {'quarterly': 3, 'annual': 12},
                            'quarterly': {'annual': 4}}[native][target]
                native_periods = series.index.to_period(COMP_PERIOD_RULES[native])
                if native_periods.duplicated().any():
                    raise ValueError(f'Multiple {native} observations in one period.')
                counts = series.groupby(periods).size()
                sufficient = counts.reindex(grouped.index, fill_value=0) == expected
            elif native == 'weekly' and native != target:
                starts = grouped.index.to_timestamp().to_numpy().astype('datetime64[D]')
                ends = (grouped.index + 1).to_timestamp().to_numpy().astype('datetime64[D]')
                expected = np.busday_count(starts, ends, weekmask='Fri')
                counts = series.groupby(periods).size()
                sufficient = counts.reindex(grouped.index, fill_value=0) >= expected * COMP_MIN_PERIOD_COVERAGE
            incomplete_periods.append(int((~sufficient).sum()))
            grouped = grouped[sufficient]
        aggregated.append(grouped)
        methods.append('native' if target == native else method)

    aligned = pd.concat([aggregated[0].rename(label_a), aggregated[1].rename(label_b)],
                        axis=1, join='inner').dropna().sort_index()
    if aligned.empty:
        raise ValueError(f'No overlapping closed {target} periods between {label_a} and {label_b}.')
    dropped_for_gaps = 0
    if target != 'daily':
        breaks = np.flatnonzero(np.diff(aligned.index.asi8) > 1)
        if len(breaks):
            dropped_for_gaps = int(breaks[-1] + 1)
            aligned = aligned.iloc[dropped_for_gaps:]
        aligned.index = aligned.index.to_timestamp(how='end').normalize()
    details = {
        'frequency': target,
        'native_frequencies': native_frequencies,
        'frequency_sources': frequency_sources,
        'aggregation': methods,
        'lag_unit': COMP_LAG_UNITS[target],
        'dropped_for_gaps': dropped_for_gaps,
        'dropped_open_periods': open_periods,
        'dropped_incomplete_periods': incomplete_periods,
        'consolidated_weekly_observations': consolidated_weeks,
    }
    return aligned, details


def _comp_pick_value_column(df):
    """Choose the numeric column that best represents a source frame."""
    for col in _COMP_VALUE_COLUMNS:
        if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
            return col
    for col in df.columns:
        if col not in _COMP_SKIP_COLUMNS and pd.api.types.is_numeric_dtype(df[col]):
            return col
    return None


def _comp_to_daily_series(df, label):
    """Extract dated numeric observations, preserving their native cadence metadata.

    Sources differ in timestamp type (python date, datetime64, tz-aware) and
    in row granularity, so dates are stripped to tz-naive midnight and rows
    are reduced to a single daily print before any comparison happens.
    """
    if 'Date' not in df.columns:
        raise ValueError(f"'{label}' has no Date column.")

    frame = df.copy()
    dates = pd.to_datetime(frame['Date'], errors='coerce')
    if dates.dt.tz is not None:
        dates = dates.dt.tz_localize(None)
    frame['Date'] = dates.dt.normalize()
    frame = frame[frame['Date'].notna()]
    if frame.empty:
        raise ValueError(f"'{label}' has no parseable dates.")

    # Derivatives carry many contracts per day; the front-month future is the
    # single series that behaves like a price history.
    if 'Instrument' in frame.columns:
        futures = frame[frame['Instrument'].astype(str)
                        .str.contains('FUT', case=False, na=False)]
        if not futures.empty:
            frame = futures
        if 'Expiry' in frame.columns:
            frame = (frame.sort_values(['Date', 'Expiry'])
                          .groupby('Date', as_index=False)
                          .first())

    column = _comp_pick_value_column(frame)
    if column is None:
        raise ValueError(f"'{label}' has no numeric column to compare.")

    values = pd.to_numeric(frame[column], errors='coerce')
    out = pd.DataFrame({'Date': frame['Date'].to_numpy(),
                        'Value': values.to_numpy()}).dropna()
    if out.empty:
        raise ValueError(f"'{label}' has no usable numeric data.")

    series = out.groupby('Date')['Value'].mean().sort_index()
    for source_column, attribute in [('Frequency', 'frequency'), ('Unit', 'unit')]:
        if source_column in frame.columns:
            populated = frame[source_column].dropna().astype(str).str.strip()
            populated = populated[~populated.str.lower().isin(['', 'nan', '<na>', 'none'])]
            if not populated.empty:
                if source_column == 'Frequency' and populated.str.lower().nunique() > 1:
                    raise ValueError(f"'{label}' has conflicting Frequency metadata.")
                series.attrs[attribute] = populated.iloc[-1]
    if label in _COMP_FLOW_SYMBOLS or column in _COMP_FLOW_COLUMNS:
        series.attrs['aggregation'] = 'sum'
    elif label in _COMP_STOCK_SYMBOLS:
        series.attrs['aggregation'] = 'last'
    else:
        series.attrs['aggregation'] = 'mean'
    return series, column


def _comp_load_symbol(symbol):
    """Locate `symbol` in any processed directory. Returns (df, source)."""
    for source, directory in _COMP_SOURCES:
        if (directory / f"{symbol}.parquet").exists():
            return _load_parquet(directory, symbol), source
    return None, None


def resolve_comp_series(token):
    """Resolve a COMP argument to a daily series.

    Accepts a stored symbol from any downloaded source, or a ratio written as
    NUM__DEN (e.g. US02Y__US10Y).  The double underscore keeps stored names
    that contain a single underscore (WDM's Debt_* files, GLD_SLV) unambiguous
    and stays safe to use in filenames.

    Returns:
        (series, label, description)
    """
    token = token.strip()
    if not token:
        raise ValueError("Empty symbol.")

    frame, source = _comp_load_symbol(token)
    if frame is not None:
        series, column = _comp_to_daily_series(frame, token)
        return series, token, f"{source} [{column}]"

    if RATIO_OPERATOR in token:
        parts = token.split(RATIO_OPERATOR)
        if len(parts) != 2:
            raise ValueError(
                f"'{token}' contains more than one '{RATIO_OPERATOR}' - a ratio "
                f"must be NUM{RATIO_OPERATOR}DEN.")

        num_name, den_name = parts[0].strip(), parts[1].strip()
        num_frame, _ = _comp_load_symbol(num_name)
        if num_frame is None:
            raise ValueError(f"'{token}': numerator '{num_name}' not found.")
        den_frame, _ = _comp_load_symbol(den_name)
        if den_frame is None:
            raise ValueError(f"'{token}': denominator '{den_name}' not found.")

        num_series, _ = _comp_to_daily_series(num_frame, num_name)
        den_series, _ = _comp_to_daily_series(den_frame, den_name)
        joined, alignment = align_comparison_series(num_series, den_series, 'num', 'den')
        joined = joined[joined['den'] != 0]
        if joined.empty:
            raise ValueError(
                f"'{token}': {num_name} and {den_name} share no overlapping dates.")
        ratio = (joined['num'] / joined['den']).sort_index()
        ratio = ratio[np.isfinite(ratio)]
        if ratio.empty:
            raise ValueError(f"'{token}' has no finite ratio observations.")
        ratio.attrs = {'frequency': alignment['frequency'], 'unit': 'Ratio',
                       'aggregation': 'mean'}
        return ratio, token, f"ratio {num_name}/{den_name} ({alignment['frequency']}, computed)"

    raise ValueError(
        f"Unknown symbol '{token}' - not found in any processed data directory. "
        f"For a ratio use NUM{RATIO_OPERATOR}DEN "
        f"(e.g. US02Y{RATIO_OPERATOR}US10Y).")


# --- Statistical measures --------------------------------------------------

def _comp_resample(values, max_points):
    """Uniformly resample a 1-D array down to at most `max_points`."""
    array = np.asarray(values, dtype=float)
    if len(array) <= max_points:
        return array
    positions = np.linspace(0, len(array) - 1, max_points)
    return np.interp(positions, np.arange(len(array)), array)


def _comp_zscore(values):
    array = np.asarray(values, dtype=float)
    spread = np.std(array)
    return (array - np.mean(array)) / spread if spread > 0 else array - np.mean(array)


def dtw_distance(a, b, band_fraction=DTW_BAND_FRACTION, max_points=DTW_MAX_POINTS):
    """Sakoe-Chiba banded DTW distance between two z-normalised series.

    Series are resampled to `max_points` first so the cost stays bounded for
    multi-decade histories, and the distance is length-normalised so it is
    comparable across pairs.
    """
    if not HAS_DTW:
        return float('nan')

    x = _comp_zscore(_comp_resample(a, max_points))
    y = _comp_zscore(_comp_resample(b, max_points))
    n, m = len(x), len(y)
    if n < 2 or m < 2:
        return float('nan')

    window = max(int(band_fraction * max(n, m)), abs(n - m) + 1)
    if HAS_DTW_C:
        distance = _dtw.distance_fast(x, y, window=window, use_pruning=True)
    else:
        distance = _dtw.distance(x, y, window=window, use_pruning=True)

    if not np.isfinite(distance):
        return float('nan')
    return distance / max(n, m)


def mutual_information(x, y, seed=0):
    """Mutual information in bits, via scikit-learn's k-NN (Kraskov) estimator.

    Captures non-linear dependence that Pearson correlation misses.  Unlike a
    histogram estimate it is essentially unbiased, so independent series score
    ~0 rather than a spurious positive value.
    """
    if not HAS_SKLEARN:
        return float('nan')

    features = np.asarray(x, dtype=float).reshape(-1, 1)
    target = np.asarray(y, dtype=float)
    if len(target) < 20:
        return float('nan')

    nats = float(mutual_info_regression(features, target, random_state=seed)[0])
    return nats / math.log(2)


def cross_correlation(x, y, max_lag=COMP_MAX_LAG):
    """Correlation of x[t] against y[t+k] for k in [-max_lag, max_lag].

    A positive lag means x leads y.
    """
    sx = pd.Series(np.asarray(x, dtype=float))
    sy = pd.Series(np.asarray(y, dtype=float))
    return [(k, sx.corr(sy.shift(-k))) for k in range(-max_lag, max_lag + 1)]


def granger_min_pvalue(cause, effect, max_lag=COMP_MAX_LAG):
    """Smallest p-value (and its lag) for `cause` Granger-causing `effect`."""
    data = np.column_stack([np.asarray(effect, dtype=float),
                            np.asarray(cause, dtype=float)])
    # Older statsmodels prints a report here; stdout is redirected rather than
    # passing verbose=False, which newer releases deprecated.
    with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
        warnings.simplefilter('ignore')
        results = grangercausalitytests(data, maxlag=max_lag)

    best_p, best_lag = float('nan'), None
    for lag, (tests, _) in results.items():
        p_value = tests['ssr_ftest'][1]
        if math.isnan(best_p) or p_value < best_p:
            best_p, best_lag = p_value, lag
    return best_p, best_lag


def compute_comparison(series_a, series_b, label_a, label_b,
                       max_lag=COMP_MAX_LAG, days=None,
                       frequency='auto', aggregation='auto'):
    """Compare native series on a shared cadence before calculating changes.

    The legacy `days` parameter counts aligned observations, not calendar days.
    Short samples retain descriptive charts but not significance tests.
    """
    if label_a == label_b:
        raise ValueError('Choose two different series for a comparison.')
    if max_lag < 1:
        raise ValueError('max_lag must be positive.')
    aligned, alignment = align_comparison_series(
        series_a, series_b, label_a, label_b, frequency=frequency, aggregation=aggregation)
    total_overlap = len(aligned)

    if days is not None:
        if days < 3:
            raise ValueError('The comparison window needs at least 3 aligned observations.')
        aligned = aligned.tail(days)

    if len(aligned) < 3:
        raise ValueError(
            f"Only {len(aligned)} overlapping observations between {label_a} and "
            f"{label_b} - need at least 3 for descriptive charts.")

    levels_a = aligned[label_a].to_numpy(dtype=float)
    levels_b = aligned[label_b].to_numpy(dtype=float)
    changes = pd.DataFrame(index=aligned.index)
    transforms = {}
    units = {}
    for label, original in [(label_a, series_a), (label_b, series_b)]:
        units[label] = str(original.attrs.get('unit', ''))
        if 'percent' in units[label].lower() or units[label] == '%':
            changes[label] = aligned[label].diff()
            transforms[label] = 'percentage-point changes'
        elif (aligned[label] > 0).all():
            changes[label] = np.log(aligned[label]).diff()
            transforms[label] = 'log changes'
        else:
            changes[label] = aligned[label].diff()
            transforms[label] = 'first differences'
    changes = changes.dropna()
    kinds = set(transforms.values())
    change_kind = next(iter(kinds)) if len(kinds) == 1 else 'mixed changes'

    returns_a = changes[label_a].to_numpy(dtype=float)
    returns_b = changes[label_b].to_numpy(dtype=float)
    cadence_limit = {'daily': 10, 'weekly': 10, 'monthly': 10, 'quarterly': 4, 'annual': 2}
    effective_lag = min(max_lag, cadence_limit[alignment['frequency']],
                        max(0, (len(changes) - 1) // 5))
    enough_history = len(aligned) >= COMP_MIN_OBS
    inference_note = f'Needs {COMP_MIN_OBS} aligned observations; only {len(aligned)} available'

    results = {
        'aligned': aligned,
        'changes': changes,
        'change_kind': change_kind,
        'transforms': transforms,
        'units': units,
        'alignment': alignment,
        'frequency': alignment['frequency'],
        'lag_unit': alignment['lag_unit'],
        'label_a': label_a,
        'label_b': label_b,
        'max_lag': effective_lag,
        'days_requested': days,
        'total_overlap': total_overlap,
        'inference_note': '' if enough_history else inference_note,
    }

    # --- Cointegration (on levels) ---
    try:
        if not enough_history:
            raise ValueError(inference_note)
        diagnostics = {}
        for label, levels in [(label_a, levels_a), (label_b, levels_b)]:
            diagnostics[label] = {
                'level_p': float(adfuller(levels, autolag='AIC')[1]),
                'difference_p': float(adfuller(np.diff(levels), autolag='AIC')[1]),
            }
        results['stationarity'] = diagnostics
        if not all(check['level_p'] >= 0.05 and check['difference_p'] < 0.05
                   for check in diagnostics.values()):
            raise ValueError('ADF checks do not support two I(1) series')
        t_stat, p_value, _ = coint(levels_a, levels_b)
        results['coint'] = {'stat': t_stat, 'p': p_value}
    except Exception as e:
        results['coint'] = {'error': str(e)}

    # Hedge ratio and spread for the chart, from OLS of B on A
    try:
        design = sm.add_constant(levels_a)
        fit = sm.OLS(levels_b, design).fit()
        intercept, beta = float(fit.params[0]), float(fit.params[1])
        results['spread'] = pd.Series(levels_b - (intercept + beta * levels_a),
                                      index=aligned.index)
        results['beta'] = beta
    except Exception:
        results['spread'] = None
        results['beta'] = float('nan')

    # --- Granger causality (both directions, on changes) ---
    for key, cause, effect, names in (
            ('granger_ab', returns_a, returns_b, (label_a, label_b)),
            ('granger_ba', returns_b, returns_a, (label_b, label_a))):
        try:
            if not enough_history:
                raise ValueError(inference_note)
            if not all(adfuller(values, autolag='AIC')[1] < 0.05 for values in (cause, effect)):
                raise ValueError('ADF does not support stationary comparison changes')
            p_value, lag = granger_min_pvalue(cause, effect, effective_lag)
            results[key] = {'p': min(1.0, p_value * effective_lag), 'raw_p': p_value,
                            'lag': lag, 'names': names}
        except Exception as e:
            results[key] = {'error': str(e), 'names': names}

    # --- Cross-correlation (on changes) ---
    try:
        if np.std(returns_a) == 0 or np.std(returns_b) == 0:
            raise ValueError('Constant changes: correlation is undefined')
        pairs = cross_correlation(returns_a, returns_b, effective_lag)
        valid = [(k, c) for k, c in pairs if c is not None and not math.isnan(c)]
        results['ccf'] = pairs
        if valid:
            best_lag, best_corr = max(valid, key=lambda item: abs(item[1]))
            results['ccf_best'] = {'lag': best_lag, 'corr': best_corr}
            results['contemporaneous'] = dict(valid).get(0, float('nan'))
        else:
            results['ccf_best'] = {'error': 'no valid correlations'}
    except Exception as e:
        results['ccf'] = []
        results['ccf_best'] = {'error': str(e)}

    # --- DTW (on levels, z-normalised inside) ---
    try:
        results['dtw'] = dtw_distance(levels_a, levels_b)
    except Exception as e:
        results['dtw'] = float('nan')
        results['dtw_error'] = str(e)

    # --- Mutual information (on changes) ---
    try:
        if not enough_history:
            raise ValueError(inference_note)
        results['mi'] = mutual_information(returns_a, returns_b)
    except Exception as e:
        results['mi'] = float('nan')
        results['mi_error'] = str(e)

    return results


def build_comparison_table(results):
    """Turn raw measure output into the on-screen / PDF summary table."""
    label_a = results['label_a']
    label_b = results['label_b']
    lag_unit = results.get('lag_unit', 'observations')
    rows = []

    coint_result = results.get('coint', {})
    if 'error' in coint_result:
        value, reading = "n/a", coint_result['error']
    else:
        p_value = coint_result['p']
        value = f"p = {p_value:.4f}"
        if p_value < 0.01:
            reading = "Evidence of cointegration at 1%"
        elif p_value < 0.05:
            reading = "Evidence of cointegration at 5%"
        elif p_value < 0.10:
            reading = "Weak evidence at 10% only"
        else:
              reading = "No evidence of cointegration at 10%"
    rows.append(["Cointegration", value, reading,
                  "Engle-Granger on levels after ADF checks; not proof of a profitable spread."])

    for key in ('granger_ab', 'granger_ba'):
        result = results.get(key, {})
        cause, effect = result.get('names', (label_a, label_b))
        name = f"Granger {cause} -> {effect}"
        if 'error' in result:
            value, reading = "n/a", result['error']
        else:
            p_value, lag = result['p'], result['lag']
            value = f"p(adj)={p_value:.4f}\nlag {lag} {lag_unit}"
            if p_value < 0.01:
                reading = f"{cause} predicts {effect} in-sample at 1%"
            elif p_value < 0.05:
                reading = f"{cause} predicts {effect} in-sample at 5%"
            else:
                 reading = f"No predictive evidence from {cause} at 5%"
        rows.append([name, value, reading,
                     "Changes; p adjusted for lag search per direction. Not causal or release-time evidence."])

    best = results.get('ccf_best', {})
    if 'error' in best:
        value, reading = "n/a", f"failed: {best['error'][:40]}"
    else:
        lag, corr = best['lag'], best['corr']
        value = f"r = {corr:+.3f} @ lag {lag:+d}"
        if lag == 0:
            reading = "Strongest association is within the same period"
        elif lag > 0:
            reading = f"{label_a} leads {label_b} by {lag} {lag_unit}"
        else:
              reading = f"{label_b} leads {label_a} by {abs(lag)} {lag_unit}"
    rows.append(["Cross-Correlation", value, reading,
                  "Descriptive lag association, not an actionable delay; macro dates are observation periods."])

    dtw_value = results.get('dtw', float('nan'))
    if math.isnan(dtw_value):
        value, reading = "n/a", "could not be computed"
    else:
        value = f"{dtw_value:.4f}"
        if dtw_value < 0.02:
            reading = "Near-identical shape profile"
        elif dtw_value < 0.05:
            reading = "Similar shape allowing for phase shift"
        else:
            reading = "Shapes diverge materially"
    rows.append(["Dynamic Time Warping", value, reading,
                 "Shape similarity despite speed/phase differences; groups like regimes."])

    mi_value = results.get('mi', float('nan'))
    if math.isnan(mi_value):
        value, reading = "n/a", results.get('mi_error', 'could not be computed')
    else:
        value = f"{mi_value:.4f} bits"
        if mi_value < 0.02:
            reading = "Effectively independent"
        elif mi_value < 0.10:
            reading = "Mild shared information"
        else:
            reading = "Substantial shared info incl. non-linear"
    rows.append(["Mutual Information", value, reading,
                 "Total shared information, linear and non-linear; used for feature selection."])

    return pd.DataFrame(
        rows, columns=["Measure", "Value", "Reading", "What it tells you"])


def load_analysis_frame(token):
    """Return an OHLCV frame for `token`, from any downloaded source.

    Equity/index/derivative sources already carry real OHLC bars.  Single-value
    sources (FRED, Yahoo, computed ratios) are expanded into flat bars so the
    same indicator stack applies; Volume is zero there, which the volume-based
    panels already guard against.

    Returns:
        (DataFrame with Date/Open/High/Low/Close/Volume, description)
    """
    frame, source = _comp_load_symbol(token)

    if frame is not None and {'Open', 'High', 'Low', 'Close'}.issubset(frame.columns):
        ohlc = frame.copy()
        dates = pd.to_datetime(ohlc['Date'], errors='coerce')
        if dates.dt.tz is not None:
            dates = dates.dt.tz_localize(None)
        ohlc['Date'] = dates.dt.normalize()
        ohlc = ohlc[ohlc['Date'].notna()]
        for column in ('Open', 'High', 'Low', 'Close', 'Volume'):
            if column in ohlc.columns:
                ohlc[column] = pd.to_numeric(ohlc[column], errors='coerce')
        if 'Volume' not in ohlc.columns:
            ohlc['Volume'] = 0.0
        ohlc = ohlc.dropna(subset=['Close']).sort_values('Date')
        return ohlc.reset_index(drop=True), f"{source} [OHLC]"

    series, _, description = resolve_comp_series(token)
    flat = pd.DataFrame({
        'Date': series.index,
        'Open': series.to_numpy(dtype=float),
        'High': series.to_numpy(dtype=float),
        'Low': series.to_numpy(dtype=float),
        'Close': series.to_numpy(dtype=float),
        'Volume': 0.0,
    })
    return flat.sort_values('Date').reset_index(drop=True), description


def _comp_window_note(results):
    """Label a requested window in aligned periods rather than calendar days."""
    if not results.get('days_requested'):
        return ""
    return f"   |   last {len(results['aligned']):,} {results.get('lag_unit', 'observations')}"


def _comp_alignment_note(results):
    """Describe the actual sampling and aggregation decisions for both legs."""
    details = results['alignment']
    notes = [f"{results['frequency'].title()} comparison"]
    for label, native, origin, method in zip(
            [results['label_a'], results['label_b']], details['native_frequencies'],
            details['frequency_sources'], details['aggregation']):
        notes.append(f'{label}: {native} ({origin}), {method}')
    if results['frequency'] == 'weekly':
        notes.append('Friday-ending weeks')
    return ' | '.join(notes)


def plot_comparison(results, table, desc_a, desc_b, pdf_pages=None):
    """Render the COMP figure: series, spread, cross-correlation and table."""
    aligned = results['aligned']
    label_a = results['label_a']
    label_b = results['label_b']
    lag_unit = results.get('lag_unit', 'observations')

    figure = plt.figure(figsize=(30, 17))
    ax_raw = figure.add_axes((0.05, 0.70, 0.41, 0.18))
    ax_norm = figure.add_axes((0.56, 0.70, 0.41, 0.18))
    ax_spread = figure.add_axes((0.05, 0.40, 0.41, 0.21))
    ax_ccf = figure.add_axes((0.56, 0.40, 0.41, 0.21))
    ax_table = figure.add_axes((0.04, 0.06, 0.93, 0.24))
    ax_table.axis('off')

    figure.suptitle(f"{label_a}   vs   {label_b}{_comp_window_note(results)}",
                    fontsize=30, fontweight='bold', y=0.978)
    figure.text(0.05, 0.944, _comp_alignment_note(results), fontsize=13, va='top')
    transforms = results['transforms']
    figure.text(0.05, 0.922,
                f"Changes: {label_a} = {transforms[label_a]}; {label_b} = {transforms[label_b]}",
                fontsize=12, color='#555555', va='top')

    # --- Raw levels on twin axes (units rarely match) ---
    ax_raw.plot(aligned.index, aligned[label_a], color='tab:blue', linewidth=1.8,
                label=f"{label_a}  ({desc_a})")
    unit_a = results['units'].get(label_a, '')
    unit_b = results['units'].get(label_b, '')
    ax_raw.set_ylabel(f"{label_a} ({unit_a})" if unit_a else label_a,
                      fontsize=14, color='tab:blue')
    ax_raw.tick_params(axis='y', labelcolor='tab:blue', labelsize=13)
    ax_raw.tick_params(axis='x', labelsize=13)
    ax_raw_twin = ax_raw.twinx()
    ax_raw_twin.plot(aligned.index, aligned[label_b], color='tab:red', linewidth=1.8,
                     label=f"{label_b}  ({desc_b})")
    ax_raw_twin.set_ylabel(f"{label_b} ({unit_b})" if unit_b else label_b,
                           fontsize=14, color='tab:red')
    ax_raw_twin.tick_params(axis='y', labelcolor='tab:red', labelsize=13)
    ax_raw_twin.grid(visible=False)
    ax_raw.grid(True, alpha=0.3)
    ax_raw.set_title(
        f"Levels  |  {aligned.index.min():%d-%b-%Y} to {aligned.index.max():%d-%b-%Y}"
        f"  |  {len(aligned):,} aligned observations",
        fontsize=20, fontweight='bold', pad=8)
    handles = ax_raw.get_lines() + ax_raw_twin.get_lines()
    ax_raw.legend(handles, [h.get_label() for h in handles], fontsize=13, loc='best')

    # --- Rebased overlay so the two shapes are directly comparable ---
    positive_levels = bool((aligned > 0).all().all())
    for column, colour in ((label_a, 'tab:blue'), (label_b, 'tab:red')):
        values = aligned[column]
        rebased = values / values.iloc[0] * 100.0 if positive_levels else _comp_zscore(values)
        ax_norm.plot(aligned.index, rebased, color=colour, linewidth=1.8, label=column)
    ax_norm.axhline(100 if positive_levels else 0, color='grey', linestyle='--', linewidth=1)
    ax_norm.legend(fontsize=14)
    ax_norm.grid(True, alpha=0.3)
    ax_norm.tick_params(labelsize=13)
    ax_norm.set_title('Rebased to 100 at common start' if positive_levels
                      else 'Standardized levels (zero or negative observations)', fontsize=20,
                      fontweight='bold', pad=8)

    # --- Cointegration spread ---
    spread = results.get('spread')
    if spread is not None and not spread.empty:
        mean = spread.mean()
        sigma = spread.std()
        ax_spread.plot(spread.index, spread, color='tab:purple', linewidth=1.5,
                       label='Spread (residual)')
        ax_spread.axhline(mean, color='black', linestyle='-', linewidth=1.2, label='mean')
        ax_spread.axhline(mean + 2 * sigma, color='tab:red', linestyle='--',
                          linewidth=1.2, label='+2 sigma')
        ax_spread.axhline(mean - 2 * sigma, color='tab:green', linestyle='--',
                          linewidth=1.2, label='-2 sigma')
        ax_spread.legend(fontsize=13)
        beta = results.get('beta', float('nan'))
        ax_spread.set_title(
            f"OLS residual   {label_b} on {label_a}   |   beta {beta:.4f}",
            fontsize=20, fontweight='bold', pad=8)
    else:
        ax_spread.text(0.5, 0.5, 'Spread unavailable', transform=ax_spread.transAxes,
                       ha='center', va='center', fontsize=16, color='grey')
    ax_spread.grid(True, alpha=0.3)
    ax_spread.tick_params(labelsize=13)

    # --- Cross-correlation function ---
    pairs = [(k, c) for k, c in results.get('ccf', [])
             if c is not None and not math.isnan(c)]
    if pairs:
        lags = [k for k, _ in pairs]
        corrs = [c for _, c in pairs]
        best = results.get('ccf_best', {})
        colours = ['tab:orange' if k == best.get('lag') else 'tab:blue' for k in lags]
        ax_ccf.bar(lags, corrs, color=colours)
        ax_ccf.axhline(0, color='black', linewidth=1)
        ax_ccf.set_xlabel(f"Lag ({lag_unit})   -  positive = {label_a} leads {label_b}",
                          fontsize=15)
        ax_ccf.set_ylabel('Correlation', fontsize=15)
        ax_ccf.set_title(f"Cross-correlation of {results['change_kind']}",
                         fontsize=20, fontweight='bold', pad=8)
    else:
        ax_ccf.text(0.5, 0.5, 'Cross-correlation unavailable',
                    transform=ax_ccf.transAxes, ha='center', va='center',
                    fontsize=16, color='grey')
    ax_ccf.grid(True, alpha=0.3)
    ax_ccf.tick_params(labelsize=13)

    # --- Summary table ---
    cell_colours = []
    for _, row in table.iterrows():
        reading = row['Reading'].lower()
        if any(word in reading for word in ('strong', 'cointegrated at', 'leads',
                                            'substantial', 'near-identical')):
            tint = '#c6efce'
        elif any(word in reading for word in ('not ', 'no ', 'n/a', 'failed',
                                              'independent', 'diverge')):
            tint = '#ffc7ce'
        else:
            tint = '#ffeb9c'
        cell_colours.append(['#f2f2f2', tint, tint, '#f2f2f2'])

    display_table = table.copy()
    for column, width in zip(display_table.columns, [29, 28, 57, 72]):
        display_table[column] = display_table[column].map(
            lambda value: '\n'.join(textwrap.fill(line, width) for line in str(value).splitlines()))
    tbl = ax_table.table(
        cellText=display_table.values,
        colLabels=table.columns,
        cellColours=cell_colours,
        colColours=['#4472c4'] * len(table.columns),
        cellLoc='left',
        colWidths=[0.20, 0.16, 0.29, 0.35],
        bbox=(0, 0, 1, 1),
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(13)
    for (row_idx, _), cell in tbl.get_celld().items():
        cell.set_edgecolor('#cccccc')
        if row_idx == 0:
            cell.set_text_props(color='white', fontweight='bold')
    ax_table.set_title(
        f"Cointegration / DTW on levels; Granger / correlation / MI on changes"
        f"  |  max lag {results['max_lag']} {lag_unit}",
        fontsize=18, fontweight='bold', pad=14)
    details = results['alignment']
    exclusions = (f"Excluded open periods: {sum(details['dropped_open_periods'])}; "
                  f"low coverage: {sum(details['dropped_incomplete_periods'])}; "
                  f"older periods before gaps: {details['dropped_for_gaps']}; "
                  f"extra weekly observations: {sum(details['consolidated_weekly_observations'])}.")
    figure.text(0.05, 0.037, exclusions + ' ' + results.get('inference_note', ''),
                fontsize=11, color='#555555')
    figure.text(0.05, 0.018,
                'Exploratory observation-period analysis, not a release-time backtest. '
                'Macro releases lag their periods and histories are revised; lags do not establish causation.',
                fontsize=11, color='#555555')

    if pdf_pages:
        pdf_pages.savefig(figure)
        plt.close(figure)
    else:
        plt.show()


def compare_series(token_a, token_b, days=None, pdf_path=None, pdf_pages=None,
                    frequency='auto', aggregation='auto'):
    """Resolve, align, measure, and render a comparison of two series.

    Pass `pdf_pages` to append the comparison onto a report that is already
    open; the caller keeps ownership and closes it.
    """
    if pdf_path and pdf_pages is None:
        matplotlib.use('Agg')

    series_a, label_a, desc_a = resolve_comp_series(token_a)
    series_b, label_b, desc_b = resolve_comp_series(token_b)

    print(f"\n{'='*78}")
    print(f"  Comparison:  {label_a}  vs  {label_b}")
    print(f"{'='*78}")
    print(f"  {label_a:<22} {desc_a:<34} "
          f"{series_a.index.min():%Y-%m-%d} to {series_a.index.max():%Y-%m-%d} "
          f"({len(series_a):,} obs)")
    print(f"  {label_b:<22} {desc_b:<34} "
          f"{series_b.index.min():%Y-%m-%d} to {series_b.index.max():%Y-%m-%d} "
          f"({len(series_b):,} obs)")

    results = compute_comparison(series_a, series_b, label_a, label_b, days=days,
                                 frequency=frequency, aggregation=aggregation)
    aligned = results['aligned']
    overlap = results['total_overlap']
    if days and len(aligned) < days:
        scope = f"{len(aligned):,} observations - fewer than the {days:,} requested"
    elif days:
        scope = f"last {len(aligned):,} of {overlap:,} aligned observations"
    else:
        scope = f"{len(aligned):,} aligned observations in the latest contiguous overlap"
    print(f"\n  {_comp_alignment_note(results)}")
    print(f"  Excluded periods by source: open {results['alignment']['dropped_open_periods']}, "
          f"incomplete {results['alignment']['dropped_incomplete_periods']}; "
          f"older rows before gaps {results['alignment']['dropped_for_gaps']}.")
    if any(results['alignment']['consolidated_weekly_observations']):
        print('  Multiple weekly observations: retained the latest within each Friday-ending week.')
    print(f"\n  Analysis window: {aligned.index.min():%Y-%m-%d} to "
          f"{aligned.index.max():%Y-%m-%d}  ({scope})")
    for label, transform in results['transforms'].items():
        print(f'  {label}: {transform}')
    print(f"  Lag unit: {results['lag_unit']}; maximum lag: {results['max_lag']}.")
    if results['inference_note']:
        print(f"  [limited history] {results['inference_note']}.")
    print('  Exploratory observation-period analysis, not a release-time backtest.\n')

    table = build_comparison_table(results)
    with pd.option_context('display.max_colwidth', 60, 'display.width', 200):
        print(table.to_string(index=False))
    print()

    owns_pdf = False
    if pdf_pages is None and pdf_path:
        from pathlib import Path
        Path(pdf_path).parent.mkdir(parents=True, exist_ok=True)
        pdf_pages = PdfPages(pdf_path)
        owns_pdf = True

    plot_comparison(results, table, desc_a, desc_b, pdf_pages=pdf_pages)

    if owns_pdf:
        pdf_pages.close()
        print(f"  PDF saved: {pdf_path}\n")

    return results, table


# ---------------------------------------------------------------------------
# Volatility estimators (cone, rolling, distribution)
# ---------------------------------------------------------------------------

def get_volatility_estimator(price_data, estimator=DEFAULT_ESTIMATOR,
                             window=VOLATILITY_WINDOW, clean=True):
    """Rolling estimator series from the standalone model modules.

    Dispatches to models.<estimator>.get_estimator().  Skew and Kurtosis accept
    the same three arguments but return distribution moments, not volatility.
    """
    if not HAS_MODELS:
        raise ValueError("Estimator modules unavailable - could not import models.py")
    if estimator not in ESTIMATORS:
        raise ValueError(f"Unknown estimator '{estimator}'. "
                         f"Choose from: {', '.join(ESTIMATORS)}")

    return getattr(models, estimator).get_estimator(
        price_data=price_data, window=window, clean=clean)


def _has_intraday_range(price_data):
    """True when High and Low actually differ, i.e. these are real OHLC bars."""
    if not {'High', 'Low'}.issubset(price_data.columns):
        return False
    spread = (price_data['High'] - price_data['Low']).abs()
    return bool(spread.notna().any() and spread.max() > 0)


def compute_volatility_profile(price_data, estimator=DEFAULT_ESTIMATOR,
                               windows=None, window=VOLATILITY_WINDOW,
                               quantiles=None):
    """Cone statistics plus the rolling series for one symbol.

    Returns None when there is not enough history for any requested window.
    """
    windows = list(windows or VOLATILITY_WINDOWS)
    quantiles = list(quantiles or VOLATILITY_QUANTILES)
    if len(quantiles) != 2 or quantiles[0] >= quantiles[1]:
        raise ValueError("quantiles must be [lower, upper] with lower < upper")

    usable = [w for w in windows if len(price_data) > w + 1]
    if not usable:
        return None

    cone = {'windows': [], 'max': [], 'top_q': [], 'median': [],
            'bottom_q': [], 'min': [], 'realized': [], 'series': []}

    for w in usable:
        series = get_volatility_estimator(price_data, estimator, w)
        series = series.replace([np.inf, -np.inf], np.nan).dropna()
        if series.empty:
            continue
        cone['windows'].append(w)
        cone['max'].append(series.max())
        cone['top_q'].append(series.quantile(quantiles[1]))
        cone['median'].append(series.median())
        cone['bottom_q'].append(series.quantile(quantiles[0]))
        cone['min'].append(series.min())
        cone['realized'].append(series.iloc[-1])
        cone['series'].append(series)

    if not cone['windows']:
        return None

    rolling_window = window if len(price_data) > window + 1 else cone['windows'][-1]
    rolling = get_volatility_estimator(price_data, estimator, rolling_window)
    rolling = rolling.replace([np.inf, -np.inf], np.nan).dropna()

    return {
        'estimator': estimator,
        'is_moment': estimator in MOMENT_ESTIMATORS,
        'cone': cone,
        'quantiles': quantiles,
        'rolling': rolling,
        'rolling_window': rolling_window,
        'flat_bars': not _has_intraday_range(price_data),
    }


def _volatility_formatter(profile):
    """Percent labels for volatilities, plain numbers for Skew/Kurtosis."""
    if profile['is_moment']:
        return lambda x: f"{x:.1f}"
    return lambda x: f"{x * 100:.0f}%"


def plot_volatility(profile, ticker, pdf_pages=None):
    """Render the volatility page: cone, box, rolling series and distribution."""
    cone = profile['cone']
    estimator = profile['estimator']
    rolling = profile['rolling']
    label = _volatility_formatter(profile)
    lower, upper = profile['quantiles']

    figure = plt.figure(figsize=(30, 17))
    figure.suptitle(
        f"{ticker}   Volatility Profile   |   {estimator} estimator"
        + ("   |   flat bars: range-based models read zero" if profile['flat_bars'] else ""),
        fontsize=32, fontweight='bold', y=0.975)

    has = lambda name: name in VOLATILITY_PANELS

    # --- Cone: estimator distribution across rolling windows ---
    if has('cone'):
        ax_cone = figure.add_axes((0.05, 0.56, 0.55, 0.34))
        ax_cone.plot(cone['windows'], cone['max'], marker='o', label='Max')
        ax_cone.plot(cone['windows'], cone['top_q'], marker='o',
                     label=f"{int(upper * 100)}th Prctl")
        ax_cone.plot(cone['windows'], cone['median'], marker='o', label='Median')
        ax_cone.plot(cone['windows'], cone['bottom_q'], marker='o',
                     label=f"{int(lower * 100)}th Prctl")
        ax_cone.plot(cone['windows'], cone['min'], marker='o', label='Min')
        ax_cone.plot(cone['windows'], cone['realized'], 'r-.', marker='*',
                     markersize=16, linewidth=2.5, label='Realized (latest)')
        ax_cone.set_xticks(cone['windows'])
        ax_cone.set_xlim(cone['windows'][0] - 3, cone['windows'][-1] + 3)
        ax_cone.set_xlabel('Rolling window (days)', fontsize=15)
        ax_cone.yaxis.set_major_formatter(FuncFormatter(lambda v, _: label(v)))
        ax_cone.grid(True, axis='y', alpha=0.4)
        ax_cone.tick_params(labelsize=13)
        ax_cone.legend(fontsize=13)
        ax_cone.set_title('Volatility Cone', fontsize=20, fontweight='bold', pad=8)

    # --- Box plot of the same per-window distributions ---
    if has('box'):
        ax_box = figure.add_axes((0.65, 0.56, 0.30, 0.34))
        ax_box.boxplot(cone['series'], notch=True, sym='+',
                       tick_labels=[str(w) for w in cone['windows']])
        ax_box.plot(range(1, len(cone['windows']) + 1), cone['realized'],
                    color='r', marker='*', markersize=16, linestyle='none',
                    markeredgecolor='k')
        ax_box.set_xlabel('Rolling window (days)', fontsize=15)
        ax_box.yaxis.set_major_formatter(FuncFormatter(lambda v, _: label(v)))
        ax_box.grid(True, axis='y', alpha=0.4)
        ax_box.tick_params(labelsize=13)
        ax_box.set_title('Distribution by window', fontsize=20,
                         fontweight='bold', pad=8)

    # --- Rolling estimator with quantile bands ---
    if has('rolling') and not rolling.empty:
        ax_roll = figure.add_axes((0.05, 0.31, 0.90, 0.17))
        w = profile['rolling_window']
        ax_roll.plot(rolling.index, rolling, color='tab:red', linewidth=1.4,
                     label=f"Realized ({w}d)")
        ax_roll.plot(rolling.index, rolling.rolling(w).quantile(upper),
                     color='tab:blue', linewidth=1, label=f"{int(upper * 100)}th Prctl")
        ax_roll.plot(rolling.index, rolling.rolling(w).median(),
                     color='black', linewidth=1, label='Median')
        ax_roll.plot(rolling.index, rolling.rolling(w).quantile(lower),
                     color='tab:green', linewidth=1, label=f"{int(lower * 100)}th Prctl")
        ax_roll.yaxis.set_major_formatter(FuncFormatter(lambda v, _: label(v)))
        ax_roll.grid(True, alpha=0.3)
        ax_roll.tick_params(labelsize=13)
        ax_roll.legend(fontsize=13, ncol=4)
        ax_roll.set_title(f'Rolling {estimator} ({w}-day window)',
                          fontsize=20, fontweight='bold', pad=8)

    # --- Histogram of estimator values, latest marked ---
    if has('histogram') and not rolling.empty:
        ax_hist = figure.add_axes((0.05, 0.06, 0.42, 0.17))
        ax_hist.hist(rolling, bins=60, density=True, facecolor='tab:blue', alpha=0.35)
        mean, std = rolling.mean(), rolling.std()
        if std > 0:
            grid = np.linspace(rolling.min(), rolling.max(), 200)
            ax_hist.plot(grid, norm.pdf(grid, mean, std), 'g--', linewidth=1.5,
                         label='Normal fit')
        ax_hist.axvline(rolling.iloc[-1], color='r', linewidth=2,
                        label=f"Latest {label(rolling.iloc[-1])}")
        ax_hist.xaxis.set_major_formatter(FuncFormatter(lambda v, _: label(v)))
        ax_hist.grid(True, axis='y', alpha=0.3)
        ax_hist.tick_params(labelsize=13)
        ax_hist.legend(fontsize=13)
        ax_hist.set_title('Distribution of estimator values', fontsize=20,
                          fontweight='bold', pad=8)

    # --- Summary table ---
    if has('summary') and not rolling.empty:
        ax_table = figure.add_axes((0.53, 0.06, 0.42, 0.17))
        ax_table.axis('off')
        latest = rolling.iloc[-1]
        percentile = float((rolling <= latest).mean() * 100)
        if percentile >= 80:
            reading = 'Elevated - rich vs its own history'
        elif percentile <= 20:
            reading = 'Depressed - cheap vs its own history'
        else:
            reading = 'Middle of its historical range'
        rows = [
            ['Estimator', estimator],
            [f'Latest ({profile["rolling_window"]}d)', label(latest)],
            ['Percentile rank', f"{percentile:.0f}th - {reading}"],
            ['Median', label(rolling.median())],
            ['Min / Max', f"{label(rolling.min())}  /  {label(rolling.max())}"],
            ['Observations', f"{len(rolling):,}"],
        ]
        tbl = ax_table.table(cellText=rows, cellLoc='left',
                             colWidths=[0.32, 0.68], loc='center')
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(15)
        tbl.scale(1.0, 2.4)
        for (row_idx, col_idx), cell in tbl.get_celld().items():
            cell.set_edgecolor('#cccccc')
            if col_idx == 0:
                cell.set_facecolor('#f2f2f2')
                cell.set_text_props(fontweight='bold')
        ax_table.set_title('Summary', fontsize=20, fontweight='bold', pad=8)

    if pdf_pages:
        pdf_pages.savefig(figure)
        plt.close(figure)
    else:
        plt.show()


def volatility_analysis(price_data, ticker, estimator=DEFAULT_ESTIMATOR,
                        pdf_pages=None):
    """Compute and render the volatility page for one symbol."""
    if estimator in RANGE_ESTIMATORS and not _has_intraday_range(price_data):
        print(f"  [volatility] {estimator} needs an intraday high/low range, but "
              f"{ticker} has flat bars - it will read zero.")
        print(f"  [volatility] Use Raw, HodgesTompkins or YangZhang for this series.")

    profile = compute_volatility_profile(price_data, estimator=estimator)
    if profile is None:
        print(f"  [volatility] Not enough history for {ticker} "
              f"(need more than {min(VOLATILITY_WINDOWS) + 1} rows).")
        return None

    rolling = profile['rolling']
    if not rolling.empty:
        label = _volatility_formatter(profile)
        print(f"  [volatility] {estimator} ({profile['rolling_window']}d): "
              f"latest {label(rolling.iloc[-1])}, "
              f"median {label(rolling.median())}, "
              f"range {label(rolling.min())} to {label(rolling.max())}")

    plot_volatility(profile, ticker, pdf_pages=pdf_pages)
    return profile


def _plot_macro_group_pages(group_label, registry, report_groups, subtitle, footer, pdf_pages=None):
    """Render a macro group using the shared metadata and missing-data layout."""
    today = pd.Timestamp(datetime.date.today())
    cutoff = today - pd.DateOffset(years=5)
    summaries = {}
    colours = ['#236b8e', '#237a62', '#b54446']
    for page_number, (group_name, symbols) in enumerate(report_groups, 1):
        figure = plt.figure(figsize=(30, 17), facecolor='white')
        figure.text(0.055, 0.962, f'{group_label} | {group_name}', fontsize=30,
                    fontweight='bold', color='#24282b', va='top')
        figure.text(0.055, 0.922,
                    f'{subtitle} | Past 5 years | Report date {today:%Y-%m-%d}',
                    fontsize=14, color='#555b60', va='top')
        rows = math.ceil(len(symbols) / 2)
        row_height = 0.82 / rows
        for position, symbol in enumerate(symbols):
            definition = registry[symbol]
            left = 0.055 + (position % 2) * 0.48
            top = 0.875 - (position // 2) * row_height
            figure.text(left, top, f"{symbol} | {definition['name']}", fontsize=19,
                        fontweight='bold', color='#24282b', va='top')
            source_label = (f"{definition['source']} | {definition['series']} | "
                            f"{definition['frequency']}")
            figure.text(left, top - 0.026, textwrap.fill(source_label, 130),
                        fontsize=10.5, color='#555b60', va='top')
            figure.text(left, top - 0.050, textwrap.fill(definition['description'], 116),
                        fontsize=12, color='#373d41', va='top')
            bottom = top - row_height + 0.051
            axes = figure.add_axes((left + 0.025, bottom, 0.385, row_height - 0.15))
            frame = pd.DataFrame(columns=['Date', 'Value'])
            status = definition.get('unavailable', 'No stored observations.')
            last_date = None
            path = MACRO_PROCESSED / f'{symbol}.parquet'
            if path.exists():
                try:
                    stored = _load_parquet(MACRO_PROCESSED, symbol)
                    if not {'Date', 'Value', 'Unit', 'Series'}.issubset(stored.columns):
                        raise ValueError('Missing macro columns')
                    if (not stored['Unit'].eq(definition['unit']).all()
                            or not stored['Series'].eq(definition['series']).all()):
                        raise ValueError('Stored series or units differ from this definition')
                    frame = stored[['Date', 'Value']].copy()
                    frame['Date'] = pd.to_datetime(frame['Date'], errors='coerce', utc=True).dt.tz_convert(None)
                    frame['Value'] = pd.to_numeric(frame['Value'], errors='coerce')
                    frame = frame.dropna()
                    frame = frame[np.isfinite(frame['Value']) & (frame['Date'] <= today)]
                    frame = frame.drop_duplicates('Date', keep='last').sort_values('Date')
                    last_date = frame['Date'].max() if not frame.empty else None
                    frame = frame[frame['Date'] >= cutoff]
                    status = 'No observations in the past 5 years.' if last_date is not None else 'No usable stored values.'
                except Exception as error:
                    frame = pd.DataFrame(columns=['Date', 'Value'])
                    status = f'Stored data unavailable: {error}'
            if frame.empty:
                axes.set_axis_off()
                axes.text(0.5, 0.65, 'Data unavailable', transform=axes.transAxes,
                          ha='center', va='center', fontsize=19, color='#a34542')
                axes.text(0.5, 0.36, textwrap.fill(status, 91), transform=axes.transAxes,
                          ha='center', va='center', fontsize=13, color='#555b60')
                latest_label = f"Unit: {definition['unit']} | No values plotted"
                if last_date is not None:
                    latest_label += f' | Last stored observation {last_date:%Y-%m-%d}'
                summaries[symbol] = 'unavailable'
            else:
                colour = colours[(page_number - 1) % len(colours)]
                if symbol == 'JPPOLRATE':
                    axes.step(frame['Date'], frame['Value'], where='post', color=colour, linewidth=1.6)
                else:
                    axes.plot(frame['Date'], frame['Value'], color=colour, linewidth=1.6)
                latest = frame.iloc[-1]
                axes.scatter([latest['Date']], [latest['Value']], color=colour, s=30, zorder=3)
                axes.grid(axis='y', color='#d5dadd', alpha=0.6)
                axes.spines[['top', 'right']].set_visible(False)
                axes.spines[['left', 'bottom']].set_color('#bcc3c7')
                locator = AutoDateLocator(minticks=3, maxticks=6)
                axes.xaxis.set_major_locator(locator)
                axes.xaxis.set_major_formatter(ConciseDateFormatter(locator))
                axes.yaxis.set_major_formatter(FuncFormatter(
                    lambda value, position: f'{value:,.2f}' if abs(value) < 10 else f'{value:,.0f}'))
                axes.tick_params(labelsize=10)
                if frame['Value'].min() < 0 < frame['Value'].max():
                    axes.axhline(0, color='#777777', linewidth=0.7, linestyle='--')
                age = (today - latest['Date']).days
                latest_label = (f"Latest: {latest['Value']:,.3f} {definition['unit']} | "
                                f"Observed {latest['Date']:%Y-%m-%d} | {age} days old")
                summaries[symbol] = 'plotted'
            figure.text(left + 0.025, bottom - 0.034, latest_label, fontsize=11,
                        color='#454c50', va='top')
        figure.text(0.055, 0.025, footer,
                    fontsize=11, color='#555b60')
        figure.text(0.945, 0.025, f'{group_label} {page_number}/{len(report_groups)}',
                    fontsize=11, color='#555b60', ha='right')
        if pdf_pages is not None:
            try:
                pdf_pages.savefig(figure)
            finally:
                plt.close(figure)
        else:
            plt.show()
    return summaries


def plot_japan_macro(pdf_pages=None):
    """Render cached Japan indicators with definitions, dates and explicit gaps."""
    return _plot_macro_group_pages(
        'Japan', japan_macro.JAPAN_SERIES, japan_macro.JAPAN_REPORT_GROUPS,
        'Macro and carry-trade indicators',
        'Dates are observation periods, not publication timestamps. CFTC contracts are not '
        'the proprietary MacroMicro COT index; that index has no verified public feed.',
        pdf_pages=pdf_pages)


def plot_schiller_macro(pdf_pages=None):
    """Render the US-only Schiller valuation group from cached history."""
    return _plot_macro_group_pages(
        'US Schiller', schiller_macro.SCHILLER_SERIES, schiller_macro.SCHILLER_REPORT_GROUPS,
        'US equity valuation | Robert Shiller, S&P and Multpl',
        'Observation periods, not release dates. Sources may revise estimates. '
        'US prices, earnings and inflation remain separate from Indian valuations.',
        pdf_pages=pdf_pages)


def plot_india_schiller(pdf_pages=None):
    """Render Indian-only valuations, distinguishing published CAPE from estimates."""
    return _plot_macro_group_pages(
        'India Schiller', nifty_macro.NIFTY_SERIES, nifty_macro.NIFTY_REPORT_GROUPS,
        'Indian market valuation | NSE NIFTY, Indian inflation and requested research sources',
        'Indian inputs only. NIFTYCAPE is an estimate, not IIM/NSE published CAPE. '
        'CPI ends March 2025; index and earnings-methodology changes affect comparability.',
        pdf_pages=pdf_pages)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _take_flag_value(args, flag):
    """Pop `--flag value` out of args in place; returns the value or None."""
    if flag not in args:
        return None
    position = args.index(flag)
    if position + 1 >= len(args):
        raise ValueError(f"{flag} needs a value.")
    value = args[position + 1]
    del args[position:position + 2]
    return value


def _positive_number(text, flag, cast):
    """Parse and range-check one numeric CLI value."""
    try:
        value = cast(text)
    except ValueError:
        raise ValueError(f"{flag} expects a number, got '{text}'.")
    if value <= 0:
        raise ValueError(f"{flag} must be positive, got {text}.")
    return value


def main():
    """CLI entry point.

    Usage:
        python Option-OGN.py                          # interactive, all FnO
        python Option-OGN.py WTI                      # full analysis, one symbol
        python Option-OGN.py WTI US02Y__US10Y         # ... plus a comparison
        python Option-OGN.py WTI US02Y__US10Y 250     # ... over the last 250 observations
        python Option-OGN.py --pdf WTI JP10Y --periods 120  # monthly alignment
        python Option-OGN.py --pdf WTI JP10Y --compare-frequency quarterly
        python Option-OGN.py --estimator Raw WTI      # choose the volatility estimator
        python Option-OGN.py --trend-bars 250 GLD     # widen the trendline lookback
        python Option-OGN.py --trend-distance 20 GLD  # demand 20 bars between pivots
        python Option-OGN.py --trend-prominence 5 GLD # absolute prominence, price units
        python Option-OGN.py --trend-prominence-pct 5 GLD  # auto-scale off 5% of range
        python Option-OGN.py --pdf                    # all FnO -> charts/FnO_Analysis.pdf
        python Option-OGN.py --pdf WTI                # -> charts/WTI_Analysis.pdf
        python Option-OGN.py --pdf WTI US02Y__US10Y   # -> charts/WTI_vs_US02Y__US10Y_Analysis.pdf
        python Option-OGN.py --pdf output.pdf         # custom output file
    """
    args = sys.argv[1:]
    use_pdf = '--pdf' in args
    if use_pdf:
        args.remove('--pdf')

    try:
        comparison_frequency = (_take_flag_value(args, '--compare-frequency') or 'auto').lower()
        comparison_aggregation = (_take_flag_value(args, '--compare-aggregation') or 'auto').lower()
        raw_periods = _take_flag_value(args, '--periods')
        requested_periods = None if raw_periods is None else _positive_number(raw_periods, '--periods', int)
        if comparison_frequency not in ('auto', *COMP_FREQUENCIES):
            raise ValueError('--compare-frequency must be auto, daily, weekly, monthly, quarterly or annual.')
        if comparison_aggregation not in ('auto', 'mean', 'last', 'sum'):
            raise ValueError('--compare-aggregation must be auto, mean, last or sum.')
        raw_bars = _take_flag_value(args, '--trend-bars')
        raw_distance = _take_flag_value(args, '--trend-distance')
        raw_prominence = _take_flag_value(args, '--trend-prominence')
        raw_prominence_pct = _take_flag_value(args, '--trend-prominence-pct')
        if raw_prominence is not None and raw_prominence_pct is not None:
            raise ValueError("--trend-prominence and --trend-prominence-pct are "
                             "mutually exclusive; the absolute value would win.")
        trend_bars = (TREND_BARS if raw_bars is None
                      else _positive_number(raw_bars, '--trend-bars', int))
        trend_distance = (TREND_DISTANCE if raw_distance is None
                          else _positive_number(raw_distance, '--trend-distance', int))
        trend_prominence = (None if raw_prominence is None
                            else _positive_number(raw_prominence,
                                                  '--trend-prominence', float))
        trend_prominence_pct = (
            TREND_PROMINENCE_PCT if raw_prominence_pct is None
            else _positive_number(raw_prominence_pct,
                                  '--trend-prominence-pct', float) / 100.0)
    except ValueError as e:
        print(f"  [error] {e}")
        return

    if trend_bars < 2 * trend_distance + 1:
        print(f"  [error] --trend-bars {trend_bars} cannot hold two pivots "
              f"{trend_distance} bars apart; needs at least "
              f"{2 * trend_distance + 1}.")
        return

    estimator = DEFAULT_ESTIMATOR
    if '--estimator' in args:
        position = args.index('--estimator')
        if position + 1 >= len(args):
            print(f"  [error] --estimator needs a name. "
                  f"Choose from: {', '.join(ESTIMATORS)}")
            return
        estimator = args[position + 1]
        del args[position:position + 2]
        match = [e for e in ESTIMATORS if e.lower() == estimator.lower()]
        if not match:
            print(f"  [error] Unknown estimator '{estimator}'. "
                  f"Choose from: {', '.join(ESTIMATORS)}")
            return
        estimator = match[0]

    # Legacy Windows code pages cannot encode this script's Unicode output.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    pdf_path = None
    tokens = []
    for arg in args:
        if arg.lower().endswith('.pdf'):
            pdf_path = arg
        else:
            tokens.append(arg)

    days = requested_periods
    if tokens and tokens[-1].lstrip('+-').isdigit():
        if requested_periods is not None:
            print('  [error] Use --periods or the trailing window, not both.')
            return
        days = int(tokens.pop())
        if days <= 0:
            print(f"  [error] observations must be positive, got {days}.")
            return

    if len(tokens) > 2:
        print("Usage: python Option-OGN.py [--pdf] [--estimator NAME] "
              "[--trend-bars N] [--trend-distance N] [--trend-prominence X] "
              "[--compare-frequency FREQ] [--compare-aggregation METHOD] "
              "[symbol] [compare_symbol] [observations]")
        print("  symbol            full technical analysis for this series")
        print("  compare_symbol    optional - append a statistical comparison")
        print("  observations      optional - last N aligned observations; also --periods N")
        print("  --compare-frequency   auto (slower source), daily, weekly, monthly, quarterly, annual")
        print("  --compare-aggregation auto (series-specific), mean, last, sum")
        print(f"  --estimator       optional - default {DEFAULT_ESTIMATOR}; one of: "
              f"{', '.join(ESTIMATORS)}")
        print(f"  --trend-bars      optional - default {TREND_BARS}; trendline lookback")
        print(f"  --trend-distance  optional - default {TREND_DISTANCE}; min bars between pivots")
        print(f"  --trend-prominence     optional - absolute pivot prominence, price units")
        print(f"  --trend-prominence-pct optional - default "
              f"{TREND_PROMINENCE_PCT * 100:.0f}; percent of the window range")
        print(f"  Symbols may come from any downloaded source, or be a ratio")
        print(f"  written as NUM{RATIO_OPERATOR}DEN (e.g. US02Y{RATIO_OPERATOR}US10Y).")
        return

    symbol = tokens[0].upper() if len(tokens) >= 1 else None
    compare_with = tokens[1].upper() if len(tokens) == 2 else None

    if not compare_with and (days or comparison_frequency != 'auto' or comparison_aggregation != 'auto'):
        print('  [error] Comparison options require a second symbol.')
        return

    if use_pdf and not pdf_path:
        if symbol and compare_with:
            suffix = f"_{days}obs" if days else ""
            if comparison_frequency != 'auto':
                suffix += f'_{comparison_frequency}'
            if comparison_aggregation != 'auto':
                suffix += f'_{comparison_aggregation}'
            pdf_path = f"charts/{symbol}_vs_{compare_with}{suffix}_Analysis.pdf"
        elif symbol:
            pdf_path = f"charts/{symbol}_Analysis.pdf"
        else:
            pdf_path = "charts/FnO_Analysis.pdf"

    try:
        FnOAnalysis(single_scrip=symbol,
                    pdf_path=pdf_path if use_pdf else None,
                    compare_with=compare_with,
                    days=days,
                    estimator=estimator,
                    trend_bars=trend_bars,
                    trend_distance=trend_distance,
                    trend_prominence=trend_prominence,
                    trend_prominence_pct=trend_prominence_pct,
                    comparison_frequency=comparison_frequency,
                    comparison_aggregation=comparison_aggregation)
    except (ValueError, FileNotFoundError) as e:
        print(f"  [error] {e}")


if __name__ == "__main__":
    main()
