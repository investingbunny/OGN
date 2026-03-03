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
    """Compute the strike at which total option-writer pain is minimised."""
    strikes = sorted(set(call_sums['Strike Price']).union(set(put_sums['Strike Price'])))
    pain = {}
    for s in strikes:
        call_pain = call_sums.loc[call_sums['Strike Price'] < s,
                                  'Open Int'].sum() * 0  # ITM calls
        # For each strike, sum intrinsic * OI for all ITM options
        itm_calls = call_sums[call_sums['Strike Price'] < s].copy()
        itm_calls['pain'] = (s - itm_calls['Strike Price']) * itm_calls['Open Int']
        itm_puts = put_sums[put_sums['Strike Price'] > s].copy()
        itm_puts['pain'] = (itm_puts['Strike Price'] - s) * itm_puts['Open Int']
        pain[s] = itm_calls['pain'].sum() + itm_puts['pain'].sum()
    if not pain:
        return np.nan
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
    """Wilder-style RSI."""
    df = DF.copy()
    delta = df['Close'].diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    avg_gain = [np.nan] * n
    avg_loss = [np.nan] * n
    avg_gain.append(gain.iloc[1:n + 1].mean())
    avg_loss.append(loss.iloc[1:n + 1].mean())
    for i in range(n + 1, len(df)):
        avg_gain.append((avg_gain[-1] * (n - 1) + gain.iloc[i]) / n)
        avg_loss.append((avg_loss[-1] * (n - 1) + loss.iloc[i]) / n)
    df['avg_gain'] = np.array(avg_gain)
    df['avg_loss'] = np.array(avg_loss)
    df['RS'] = df['avg_gain'] / df['avg_loss']
    df['RSI'] = 100 - (100 / (1 + df['RS']))
    return df['RSI']


def ADX(DF, n=20):
    """Average Directional Index (ADX), DI+, DI-."""
    df2 = DF.copy()
    df2['TR'] = ATR(df2, n)['TR']
    df2['DMplus'] = np.where(
        (df2['High'] - df2['High'].shift(1)) > (df2['Low'].shift(1) - df2['Low']),
        df2['High'] - df2['High'].shift(1), 0)
    df2['DMplus'] = np.where(df2['DMplus'] < 0, 0, df2['DMplus'])
    df2['DMminus'] = np.where(
        (df2['Low'].shift(1) - df2['Low']) > (df2['High'] - df2['High'].shift(1)),
        df2['Low'].shift(1) - df2['Low'], 0)
    df2['DMminus'] = np.where(df2['DMminus'] < 0, 0, df2['DMminus'])

    TRn, DMpN, DMmN = [], [], []
    TR = df2['TR'].tolist()
    DMp = df2['DMplus'].tolist()
    DMm = df2['DMminus'].tolist()
    for i in range(len(df2)):
        if i < n:
            TRn.append(np.nan); DMpN.append(np.nan); DMmN.append(np.nan)
        elif i == n:
            TRn.append(df2['TR'].rolling(n).sum().iloc[n])
            DMpN.append(df2['DMplus'].rolling(n).sum().iloc[n])
            DMmN.append(df2['DMminus'].rolling(n).sum().iloc[n])
        else:
            TRn.append(TRn[-1] - TRn[-1] / n + TR[i])
            DMpN.append(DMpN[-1] - DMpN[-1] / n + DMp[i])
            DMmN.append(DMmN[-1] - DMmN[-1] / n + DMm[i])
    df2['TRn'] = np.array(TRn)
    df2['DMplusN'] = np.array(DMpN)
    df2['DMminusN'] = np.array(DMmN)
    df2['DIplusN'] = 100 * (df2['DMplusN'] / df2['TRn'])
    df2['DIminusN'] = 100 * (df2['DMminusN'] / df2['TRn'])
    df2['DIdiff'] = abs(df2['DIplusN'] - df2['DIminusN'])
    df2['DIsum'] = df2['DIplusN'] + df2['DIminusN']
    df2['DX'] = 100 * (df2['DIdiff'] / df2['DIsum'])

    adx_vals = []
    DX = df2['DX'].tolist()
    for j in range(len(df2)):
        if j < 2 * n - 1:
            adx_vals.append(np.nan)
        elif j == 2 * n - 1:
            adx_vals.append(df2['DX'].iloc[j - n + 1:j + 1].mean())
        else:
            adx_vals.append(((n - 1) * adx_vals[-1] + DX[j]) / n)
    df2['ADX'] = np.array(adx_vals)
    return df2


def OBV(DF):
    """On Balance Volume."""
    df = DF.copy()
    df['daily_ret'] = df['Close'].pct_change()
    df['direction'] = np.where(df['daily_ret'] >= 0, 1, -1)
    df.iloc[0, df.columns.get_loc('direction')] = 0
    df['vol_adj'] = df['Volume'] * df['direction']
    df['obv'] = df['vol_adj'].cumsum()
    return df


def ATR(DF, n=20):
    """True Range and Average True Range."""
    df = DF.copy()
    df['H-L'] = abs(df['High'] - df['Low'])
    df['H-PC'] = abs(df['High'] - df['Close'].shift(1))
    df['L-PC'] = abs(df['Low'] - df['Close'].shift(1))
    df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1, skipna=False)
    df['ATR'] = df['TR'].rolling(n).mean()
    df.drop(['H-L', 'H-PC', 'L-PC'], axis=1, inplace=True)
    return df


def slope(ser, n=5):
    """Slope of regression line for n consecutive points (degrees)."""
    ser = (ser - ser.min()) / (ser.max() - ser.min())
    x = np.array(range(len(ser)))
    x = (x - x.min()) / (x.max() - x.min())
    slopes = [0.0] * (n - 1)
    for i in range(n, len(ser) + 1):
        y_scaled = ser.iloc[i - n:i]
        x_scaled = x[i - n:i]
        x_scaled = sm.add_constant(x_scaled)
        model = sm.OLS(y_scaled, x_scaled)
        results = model.fit()
        slopes.append(results.params[-1])
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
    """Convert OHLCV data into Renko bricks (requires stocktrends)."""
    if not HAS_RENKO:
        print("  [skip] stocktrends not installed — Renko unavailable")
        return pd.DataFrame()
    df = DF.copy()
    # Select columns: date, open, high, low, close, volume
    if ticker in ("NIFTY", "BANKNIFTY"):
        df = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].copy()
    else:
        # Equity data already has the right columns
        df = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].copy()
    df.rename(columns={"Date": "date", "High": "high", "Low": "low",
                        "Open": "open", "Close": "close", "Volume": "volume"},
              inplace=True)
    df2 = Renko(df)
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

    # ── Build OHLC list for candlestick ───────────────────────────────
    ohlc = []
    for dt, row in data.iterrows():
        ohlc.append([date2num(dt), row['Open'], row['High'], row['Low'], row['Close']])

    # ── Figure 2: main analysis panels ────────────────────────────────
    fig2 = plt.figure(figsize=(48, 27))

    ax_macd = fig2.add_axes((0, 0.84, 0.49, 0.24))
    ax_rsi = fig2.add_axes((0, 0.56, 0.49, 0.24), sharex=ax_macd)
    ax_fibret = fig2.add_axes((0, 0.28, 0.49, 0.24), sharex=ax_macd)
    ax_bba = fig2.add_axes((0, 0, 0.49, 0.24), sharex=ax_macd)

    ax_ema = fig2.add_axes((0.51, 0.76, 0.49, 0.32), sharex=ax_macd)
    ax_maxpain = fig2.add_axes((0.51, 0.52, 0.49, 0.2), sharex=ax_macd)
    ax_futures = fig2.add_axes((0.51, 0, 0.49, 0.5), sharex=ax_macd)

    ax_macd.xaxis_date()

    # ── EMA panel ─────────────────────────────────────────────────────
    ax_ema.plot(data.index, data["Close"], label=f"{ticker} Price")
    for col in ["10DMA-E", "20DMA-E", "50DMA-E", "80DMA-E", "140DMA-E"]:
        if col in data.columns:
            ax_ema.plot(data.index, data[col], label=col)
    ax_ema.legend()

    # ── Futures fair-value overlay ────────────────────────────────────
    if Futdf is not None and 'NearExpiry' in Futdf.columns:
        try:
            StdDev = data['Log_Ret'].std()
            DailyRet = data['Log_Ret'].mean()
            days = np.busday_count(
                np.datetime64(data.index[0], 'D'),
                np.datetime64(datetime.date.today(), 'D'))

            for prefix, expiry_col in [('Near', 'NearExpiry'), ('Mid', 'MidExpiry'), ('Far', 'FarExpiry')]:
                col_name = f"{prefix}FuturesFormula"
                Futdf[col_name] = Futdf["Close"] * (
                    1 + RiskFreeRate * business_days(
                        pd.to_datetime(Futdf['Date']),
                        pd.to_datetime(Futdf[expiry_col])) / 365
                ) - Dividend

            Average = DailyRet * days
            SD = StdDev * math.sqrt(days)
            StartingPrice = data.iloc[0].Close

            SD1upLevel = StartingPrice * math.exp(Average + SD)
            SD1downLevel = StartingPrice * math.exp(Average - SD)

            Futdf.index = pd.to_datetime(Futdf["Date"])
            Futdf.drop("Date", axis=1, inplace=True)

            ax_futures.plot(Futdf.index, Futdf["Close"], color="black", label="Price")
            colour_map = {
                'Near': ('gray', 'silver'), 'Mid': ('blue', 'skyblue'),
                'Far': ('darkorchid', 'plum'),
            }
            for prefix, (c1, c2) in colour_map.items():
                sp_col = f"{prefix}SettlePrice"
                ff_col = f"{prefix}FuturesFormula"
                if sp_col in Futdf.columns:
                    ax_futures.plot(Futdf.index, Futdf[sp_col], color=c1, label=f"{prefix}SP")
                if ff_col in Futdf.columns:
                    ax_futures.plot(Futdf.index, Futdf[ff_col], color=c2, label=f"{prefix}FF")

            ax_futures.set_ylabel('Price')
            ax_futures.plot(data.index, [StartingPrice] * len(data.index),
                            label=f'SD1: {SD:.4f}, Average: {Average:.4f}')
            ax_futures.axhspan(StartingPrice, SD1downLevel, alpha=0.5,
                               color='mistyrose', label=f'{SD1downLevel:.1f} -SD1')
            ax_futures.axhspan(SD1upLevel, StartingPrice, alpha=0.5,
                               color='greenyellow', label=f'{SD1upLevel:.1f} +SD1')
            ax_futures.legend()
        except Exception as e:
            ax_futures.text(0.5, 0.5, f"Futures overlay error:\n{e}",
                            transform=ax_futures.transAxes, ha='center')

    # ── MACD panel ────────────────────────────────────────────────────
    ax_macd.plot(data.index, data["MACD"], label="MACD")
    ax_macd.bar(data.index, (data["MACD"] - data["Signal"]) * 3, label="hist")
    ax_macd.plot(data.index, data["Signal"], label="Signal")
    ax_macd.legend()

    # ── RSI & ADX panel ───────────────────────────────────────────────
    ax_rsi.set_ylabel("(%)")
    ax_rsi.axhline(80, color='grey', linestyle='--', label="overbought")
    ax_rsi.axhline(20, color='grey', linestyle='--', label="oversold")
    ax_rsi.axhline(50, color='grey', linestyle=':')
    ax_rsi.plot(data.index, data["RSI"], label="RSI", color='lightpink')
    if 'ADX' in data.columns:
        ax_rsi.plot(data.index, data["ADX"], label="ADX", color='blue')
    if 'DIplusN' in data.columns:
        ax_rsi.plot(data.index, data["DIplusN"], label="DI+", color='green')
    if 'DIminusN' in data.columns:
        ax_rsi.plot(data.index, data["DIminusN"], label="DI-", color='red')
    ax_rsi.legend()

    # ── Bollinger Bands + OBV panel ───────────────────────────────────
    ax_bba.plot(data.index, data["BB_up"], label="BB_up")
    ax_bba.plot(data.index, data["BB_dn"], label="BB_dn")
    ax_bba.plot(data.index, data["MA"], label="MA")
    ax_bba.legend()

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

    # Candlestick overlay on Fibonacci panel using mplfinance-compatible OHLC
    # (Using simple line plot since mplfinance add_plot requires different setup)
    ax_fibret.plot(data.index, data['Close'], color='black', linewidth=0.8)

    # ── Max Pain panel ────────────────────────────────────────────────
    if Mpdf is not None and not Mpdf.empty and 'MaxPain' in data.columns:
        ax_maxpain.plot(data.index, data["Close"], label="Price")
        ax_maxpain.plot(data.index, data["MaxPain"], color="red", marker="o", label="MaxPain")
        ax_pcr = ax_maxpain.twinx()
        if 'PCR' in data.columns:
            ax_pcr.plot(data.index, data["PCR"], color="black", marker="*", label="PCR")
        ax_maxpain.set_ylabel('Price')
        ax_pcr.set_ylabel('PCR')
        ax_pcr.grid(visible=False)
        ax_maxpain.legend()
    else:
        # Show Fibonacci extensions instead
        ext_levels = [
            (1.272, 'limegreen'), (1.382, 'lime'),
            (1.5, 'deepskyblue'), (1.618, 'powderblue'),
        ]
        prev_ext = price_max
        for ratio, colour in ext_levels:
            level = price_max - ratio * diff
            ax_maxpain.axhspan(level, prev_ext, alpha=0.5, color=colour,
                               label=f'{level:.1f} ({ratio})')
            prev_ext = level
        ax_maxpain.legend()
        ax_maxpain.plot(data.index, data['Close'], color='black', linewidth=0.8)

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

        # MACD
        Indicatordf = MACD(Indicatordf, 12, 26, 9)

        # Bollinger Bands
        Indicatordf = BollBnd(Indicatordf, 20)

        # ATR
        Indicatordf = ATR(Indicatordf, 20)

        # ADX
        ADXdf = ADX(Indicatordf, 20)
        Indicatordf['ADX'] = ADXdf['ADX']
        Indicatordf['DIplusN'] = ADXdf['DIplusN']
        Indicatordf['DIminusN'] = ADXdf['DIminusN']

        # Rolling ADX
        Indicatordf['ADXRoll5'] = Indicatordf['ADX'].rolling(5).mean()
        Indicatordf['ADXRoll10'] = Indicatordf['ADX'].rolling(15).mean()

        # Rolling volume
        Indicatordf['VolRoll5'] = Indicatordf['Volume'].rolling(5).mean()
        Indicatordf['VolRoll10'] = Indicatordf['Volume'].rolling(10).mean()

        # Beta (via talib if available)
        if HAS_TALIB:
            Indicatordf["Beta"] = talib.BETA(
                Indicatordf["High"], Indicatordf["Low"], timeperiod=14)

        # RSI
        Indicatordf["RSI"] = RSI(Indicatordf, 14)

        # OBV
        OBVdf = OBV(Indicatordf)
        Indicatordf["OBV"] = OBVdf["obv"]
        Indicatordf["Daily_Ret"] = OBVdf['daily_ret']
        Indicatordf["Log_Ret"] = np.log(1 + OBVdf['daily_ret'])

        # Slope
        Indicatordf["Slope"] = slope(Indicatordf["Close"], 5)

        # Simple DMAs
        for w in [10, 20, 50, 100, 200]:
            Indicatordf[f"{w}DMA"] = Indicatordf["Close"].rolling(window=w).mean()

        # Exponential DMAs
        for w in [10, 20, 50, 80, 140]:
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
