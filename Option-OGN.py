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
  - Swing-trading pages: reversal candles (pandas-ta-classic), swing structure (swingtrend),
    confirmed pivots and ATR-normalized formations (scipy)

Report pages: technical -> candlesticks -> swing structure -> pivots -> formations
-> max pain & PCR -> trendlines -> volatility -> volatility guide -> option IV
(next 3 monthly expiries, plus the next 5 expiries when weekly contracts are listed)
-> comparison, then separate Japan, US Schiller and India Schiller appendices once
per PDF. Edit REPORT_SECTIONS to drop any of them.

Usage:
    python Option-OGN.py                          # analyse all FnO symbols (interactive)
    python Option-OGN.py WTI                       # full analysis for one series
    python Option-OGN.py --pdf WTI 250d            # one series, last 250 trading days
    python Option-OGN.py --pdf WTI 350d-25d        # ... 350 back to 25 back (latest 25 excluded)
    python Option-OGN.py --pdf WTI Jan2026         # ... January 2026 (also Jan2026-Mar2026)
    python Option-OGN.py WTI US02Y__US10Y          # ... plus a statistical comparison
    python Option-OGN.py WTI US02Y__US10Y 250d     # ... over the last 250 aligned observations
    python Option-OGN.py --pdf WTI JP10Y 120d      # last 120 aligned months
    python Option-OGN.py --pdf WTI JP10Y --compare-aggregation last
    python Option-OGN.py --pdf WTI JP10Y --compare-frequency quarterly
    python Option-OGN.py --estimator Raw WTI       # pick the volatility estimator
    python Option-OGN.py --trend-bars 250 GLD      # widen the trendline lookback
    python Option-OGN.py --trend-distance 20 GLD   # demand 20 bars between pivots
    python Option-OGN.py --trend-prominence 5 GLD  # absolute prominence, in price units
    python Option-OGN.py --trend-prominence-pct 5 GLD  # auto-scale off 5% of the range
    python Option-OGN.py --pdf                     # all FnO symbols -> charts/FnO_Analysis_<stamp>.pdf
    python Option-OGN.py --pdf WTI                 # single symbol -> charts/WTI_Analysis_<stamp>.pdf
    python Option-OGN.py --pdf output.pdf          # custom output file -> output_<stamp>.pdf
    python Option-OGN.py List "<file>.parquet" 20  # latest 20 rows of any Parquet file
    python Option-OGN.py --pdf List "<file>.parquet" 100d  # every row on the latest 100 trading days, + PDF

PDF names carry a _YYYYMMDD_HHMMSS stamp (<stamp>), so a rerun never overwrites a report;
each PDF's full path is printed once it is saved.

@author: HRTR
"""

import io
import os
import sys
import math
import shutil
import datetime
import warnings
import contextlib
import textwrap
from functools import reduce
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.dates import date2num, AutoDateLocator, ConciseDateFormatter
from matplotlib.ticker import FixedLocator, FuncFormatter
import mplfinance as mpf
import pandas as pd
import numpy as np
import seaborn as sns
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller, coint, grangercausalitytests
from scipy.stats import norm, linregress
from scipy.signal import argrelextrema, find_peaks
import japan_macro
import nifty_macro
import schiller_macro
import option_overlay

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

# Optional: candlestick patterns, native implementations (pip install pandas-ta-classic)
try:
    import pandas_ta_classic
    HAS_PANDAS_TA = True
except ImportError:
    pandas_ta_classic = None
    HAS_PANDAS_TA = False

# Optional: Dow-style swing structure (pip install swingtrend; GPLv3)
try:
    from swingtrend import Swing
    HAS_SWINGTREND = True
except ImportError:
    Swing = None
    HAS_SWINGTREND = False

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
    load_derivatives,
    load_index,
    NSEFnOList,
    WATCHLIST,
    _load_parquet,
    _naive_dates,
    latest_parquet_rows,
    LATEST_ROWS,
    ReportWindow,
    parse_report_window,
    as_report_window,
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

# Default PDF folder, a fixed location independent of the scripts' folder and the working directory.
CHARTS_DIR = Path(r"C:\OGN-OneDrive\OneDrive\Github projects\OGN") / "charts"

# ── Report composition ────────────────────────────────────────────────────
# Comment out any line to drop that section from the generated report.
REPORT_SECTIONS = [
    'technical',    # multi-panel indicator chart for the first symbol
    'candlesticks',     # recent reversal candles (pandas-ta-classic) and their follow-through
    'swing_structure',  # swingtrend trend, breaks of structure and change-of-character level
    'pivots',           # SciPy-confirmed pivot highs / lows: nearest support and resistance
    'formations',       # ATR-normalized head & shoulders, double tops / bottoms and triangles
    'max_pain',     # max pain and put-call ratio of the range's latest options, when stored
    'trendlines',   # candlestick page with support / resistance regression lines
    'volatility',   # volatility cone / rolling / histogram page
    'volatility_guide',  # one page explaining each volatility graph with this report's numbers
    'option_overlay',
    'comparison',   # statistical comparison, only when a second symbol is given
    # 'japan_macro',
    # 'schiller_macro',
    #'india_schiller',
]

# ── Trendline page defaults (override on the CLI) ─────────────────────────
TREND_BARS = 180              # Trailing bars fed to the pivot search
TREND_DISTANCE = 12           # Minimum bars between two pivots of the same kind
TREND_PROMINENCE_PCT = 0.02   # Pivot must clear 2% of the window's high-low range
TREND_RESISTANCE_COLOUR = '#ef5350'
TREND_SUPPORT_COLOUR = '#26a69a'

# ── Swing-trading pages (after the technical page) ────────────────────────
SWING_WINDOW_MONTHS = 6       # Calendar months shown, unless a single-symbol window overrides it
CANDLE_PATTERNS = {           # pandas-ta-classic pattern name -> label
    'engulfing': 'Engulfing', 'hammer': 'Hammer', 'morningstar': 'Morning star',
    'eveningstar': 'Evening star', 'shootingstar': 'Shooting star', 'piercing': 'Piercing line',
}
CANDLE_SIGNAL_ROWS = 10       # Latest signal days numbered on the chart and listed
SWING_RETRACE_PCT = 5.0       # Pullback (%) before swingtrend moves its change-of-character level
SWING_EVENT_ROWS = 6          # Latest breaks of structure and reversals listed
PIVOT_ORDER = 5               # A pivot is the extreme of this many sessions on each side
PIVOT_ROWS = 5                # Latest confirmed pivot highs and lows listed
FORMATION_ATR_PERIOD = 14     # Formation tolerances below are multiples of this ATR
FORMATION_ATR_FALLBACK = 0.015  # Fraction of the close used when the ATR is unavailable
FORMATION_SHOULDER_ATR = 1.0  # Head and shoulders: shoulders within this many ATRs of each other
FORMATION_HEAD_ATR = 1.0      # ... and the head at least this many ATRs beyond both
FORMATION_TWIN_ATR = 0.75     # Double top / bottom: the twins within this many ATRs
FORMATION_DEPTH_ATR = 1.5     # ... with a pullback of at least this many ATRs between them
FORMATION_FLAT_ATR = 0.03     # A triangle side moving less than this many ATRs per session is flat
FORMATION_FIT_ATR = 1.0       # ... and every triangle pivot lies within this many ATRs of its side

# ── Technical page ────────────────────────────────────────────────────────
# Whole calendar years shown by the indicator panels; Renko keeps its last 100 bricks.
TECHNICAL_WINDOW_YEARS = 1

# Technical audit: each row reads Buy, Sell or Hold. Two lines closer than this
# fraction of ATR(20) are too close to call, so they read Hold.
AUDIT_HOLD_ATR = 0.1
AUDIT_RSI_SELL, AUDIT_RSI_BUY = 40, 60   # RSI between the two reads Hold
AUDIT_VOLUME_SURGE = 1.2                 # Volume must beat its 20-bar average by this factor
AUDIT_COLOURS = {'Buy': '#c6efce', 'Sell': '#ffc7ce', 'Hold': '#ffeb9c'}

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


def timestamped_path(path, moment=None):
    """Absolute `path` with _YYYYMMDD_HHMMSS before its suffix, so a rerun never overwrites a report.

    A file already holding that name (two runs in one second) gets a _2, _3 ... counter.
    """
    path = Path(os.path.abspath(path))
    stamp = (moment or datetime.datetime.now()).strftime('%Y%m%d_%H%M%S')
    candidate = path.with_name(f'{path.stem}_{stamp}{path.suffix}')
    counter = 2
    while candidate.exists():
        candidate = path.with_name(f'{path.stem}_{stamp}_{counter}{path.suffix}')
        counter += 1
    return candidate


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


def max_pain_curve(calls, puts):
    """Option writers' payout at each strike if the expiry settled there.

    `calls` and `puts` hold Strike Price and Open Int rows. Settling at S, call pain
    sums OI x (S - K) over calls struck below S and put pain sums OI x (K - S) over
    puts struck above S. Returns Call pain, Put pain and Total indexed by strike.
    """
    def open_interest(rows):
        strikes = pd.to_numeric(rows['Strike Price'], errors='coerce')
        return pd.to_numeric(rows['Open Int'], errors='coerce').fillna(0.0).groupby(strikes).sum()

    call_oi, put_oi = open_interest(calls), open_interest(puts)
    strikes = np.union1d(call_oi.index.to_numpy(float), put_oi.index.to_numpy(float))
    call_pain = (np.maximum(strikes[:, None] - call_oi.index.to_numpy(float), 0) * call_oi.to_numpy()).sum(axis=1)
    put_pain = (np.maximum(put_oi.index.to_numpy(float) - strikes[:, None], 0) * put_oi.to_numpy()).sum(axis=1)
    return pd.DataFrame({'Call pain': call_pain, 'Put pain': put_pain, 'Total': call_pain + put_pain},
                        index=pd.Index(strikes, name='Strike'))


def max_pain_strike(call_sums, put_sums):
    """The strike at which option writers' total payout (max_pain_curve) is smallest."""
    curve = max_pain_curve(call_sums, put_sums)
    return np.nan if curve.empty else curve['Total'].idxmin()


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


# ── Max pain and put-call ratio page ──────────────────────────────────────
MAX_PAIN_STRIKES = 41                    # Strikes drawn around max pain; the calculation uses all
MAX_PAIN_LOOKBACK_DAYS = 70              # Days searched back for the last expiry that has settled
MAX_PAIN_CALL = ('#c6d9f1', '#4f81bd')   # Bar fill and edge
MAX_PAIN_PUT = ('#f2c4c4', '#c0504d')
MAX_PAIN_CLOSE_COLOUR = '#7b2cbf'        # Expiry-day close line
MAX_PAIN_LABEL_BOX = dict(boxstyle='square,pad=0.15', facecolor='white', edgecolor='none', alpha=0.85)  # Lines pass behind labels
MAX_PAIN_SINGLE = (0.055, 0.2, 0.56, 0.64)                                   # Latest chain alone
MAX_PAIN_HALVES = ((0.055, 0.6, 0.56, 0.245), (0.055, 0.19, 0.56, 0.245))   # Last expiry above latest
PCR_GAUGE_TICKS = (0.25, 0.5, 0.75, 1, 1.5, 2, 4)
PCR_GAUGE_COLOURS = ('#1a7f37', '#a7d7a9', '#f4f4f4', '#f1a8a3', '#c62828')  # Calls green .. puts red
PCR_CALL_COLOUR, PCR_PUT_COLOUR = '#1a7f37', '#c62828'
PCR_GAUGE_AREA = (0.645, 0.09, 0.34, 0.79)  # Left, bottom, width, height right of the max pain chart
PCR_GAUGE_PAD = 0.03                        # Clear margin on each side of a gauge, as a fraction of its cell
PCR_GAUGE_MAX = 8                           # All expiries plus the nearest 7: two columns of four rows
PCR_GAUGE_ASPECT = 2.64 / 2.44              # Width / height of one gauge drawing
PCR_GAUGE_FULL_SIZE = 8.8                   # Drawing height, in inches, at which gauge fonts are full size


def _strike_label(strike):
    """1,234 or 102.5 - strikes without trailing zeros."""
    return format(strike, ',.2f').rstrip('0').rstrip('.')


def _ratio_text(value):
    """A put-call ratio for display; inf means puts without any calls."""
    if value is None or np.isnan(value):
        return 'n/a'
    return 'no calls' if np.isinf(value) else f'{value:.2f}'


def option_positioning(symbol, as_of, start=None):
    """Max pain and put-call ratios of the latest option chain up to `as_of`, plus the last expiry.

    The latest chain is the last option date on or before `as_of` (within a month), for the
    nearest expiry after that date, which has not settled yet. Ratios use open interest
    unless named otherwise: `pcr` for that expiry, `pcr_all` across every listed expiry,
    `pcr_volume` from traded contracts; `all_expiries` and `expiries` (nearest first) repeat
    them together and per expiry. `expired` holds the latest expiry from `start` (the report
    range's first day) up to that date: its chain on the trading day before expiry and the
    underlying's close on expiry day, or None when no expiry falls in the range.
    """
    as_of = pd.Timestamp(as_of).normalize()
    earliest = as_of - pd.Timedelta(days=MAX_PAIN_LOOKBACK_DAYS)
    if start is not None:
        earliest = max(earliest, pd.Timestamp(start).normalize())
    frame = load_derivatives(symbol, start=f'{earliest - pd.Timedelta(days=10):%Y-%m-%d}', end=f'{as_of:%Y-%m-%d}')
    side = (frame['Option type'].astype(str).str.strip().str.upper()
            if 'Option type' in frame.columns else pd.Series('', index=frame.index))
    options = frame[side.isin(['CE', 'PE'])].assign(Side=side)
    recent = options[options['Date'] >= as_of - pd.Timedelta(days=31)]
    if recent.empty:
        raise ValueError(f"no {symbol} options in the month to {as_of:%d %b %Y}")
    day = recent['Date'].max()
    on_day = options[options['Date'] == day]
    listed = on_day[on_day['Expiry'] > day]
    if listed.empty:
        listed = on_day[on_day['Expiry'] == day]
    if listed.empty:
        raise ValueError(f"no unexpired {symbol} options on {day:%d %b %Y}")
    expiry = listed['Expiry'].min()
    chain = listed[listed['Expiry'] == expiry]

    def total(rows, column):
        return float(pd.to_numeric(rows[column], errors='coerce').sum()) if column in rows.columns else np.nan

    def ratio(put, call):
        return put / call if call > 0 else (np.inf if put > 0 else np.nan)

    def summary(rows):
        calls, puts = rows[rows['Side'] == 'CE'], rows[rows['Side'] == 'PE']
        call_oi, put_oi = total(calls, 'Open Int'), total(puts, 'Open Int')
        return {'call_oi': call_oi, 'put_oi': put_oi, 'pcr': ratio(put_oi, call_oi),
                'pcr_volume': ratio(total(puts, 'Contracts'), total(calls, 'Contracts'))}

    def price(rows):
        return (float(pd.to_numeric(rows['Underlying Price'], errors='coerce').median())
                if 'Underlying Price' in rows.columns and len(rows) else np.nan)

    def snapshot(rows):
        curve = max_pain_curve(rows[rows['Side'] == 'CE'], rows[rows['Side'] == 'PE'])
        return {'curve': curve, 'max_pain': curve['Total'].idxmin(), 'spot': price(rows)}

    nearest = summary(chain)
    if not nearest['call_oi'] + nearest['put_oi'] > 0:
        raise ValueError(f"no open interest on the {symbol} {expiry:%d %b %Y} expiry")
    expired = None
    settled = options.loc[(options['Expiry'] >= earliest) & (options['Expiry'] <= day), 'Expiry']
    if not settled.empty:
        settled = settled.max()
        before = options[(options['Expiry'] == settled) & (options['Date'] < settled)]
        prior = before[before['Date'] == before['Date'].max()]
        held = summary(prior)
        if held['call_oi'] + held['put_oi'] > 0:
            expired = {'date': prior['Date'].iloc[0], 'expiry': settled, **snapshot(prior),
                       'close': price(frame[frame['Date'] == settled])}
    consolidated = summary(listed)
    return {'as_of': as_of, 'date': day, 'expiry': expiry, **snapshot(chain), **nearest,
            'pcr_all': consolidated['pcr'], 'all_expiries': consolidated,
            'expiries': [{'expiry': when, **summary(rows)} for when, rows in listed.groupby('Expiry')],
            'expired': expired}


def _max_pain_window(curve, max_pain, spot):
    """MAX_PAIN_STRIKES strikes around max pain, shifted to include the spot when both fit."""
    strikes = curve.index.to_numpy(float)
    if len(strikes) <= MAX_PAIN_STRIKES:
        return curve
    centre = int(np.searchsorted(strikes, max_pain))
    if np.isfinite(spot):
        spot_at = int(np.clip(np.searchsorted(strikes, spot), 0, len(strikes) - 1))
        if abs(spot_at - centre) < MAX_PAIN_STRIKES - 2:
            centre = (centre + spot_at) // 2
    first = int(np.clip(centre - MAX_PAIN_STRIKES // 2, 0, len(strikes) - MAX_PAIN_STRIKES))
    return curve.iloc[first:first + MAX_PAIN_STRIKES]


def _gauge_layout(count):
    """(columns, rows) for `count` gauges: one column up to three, then two columns."""
    columns = 1 if count <= 3 else 2
    return columns, math.ceil(count / columns)


def _pcr_gauges(positioning):
    """(title, figures) per gauge - all expiries, then each expiry nearest first - and expiries left out."""
    expiries = positioning['expiries']
    if len(expiries) == 1:
        return [(f"Expiry {expiries[0]['expiry']:%d %b %Y} (only expiry)", expiries[0])], 0
    shown = expiries[:PCR_GAUGE_MAX - 1]
    gauges = [('All expiries', positioning['all_expiries'])]
    gauges += [(f"Expiry {item['expiry']:%d %b %Y}"
                + (' (max pain)' if item['expiry'] == positioning['expiry'] else ''), item) for item in shown]
    return gauges, len(expiries) - len(shown)


def _draw_pcr_gauge(ax, title, figures, scale=1.0):
    """Semicircular gauge: the needle sits at puts' share of open interest.

    Calls dominate on the green left, puts on the red right; PCR 1 points straight up.
    Fonts follow `scale`, so smaller gauges in a grid keep the same proportions.
    """
    def size(points):
        return max(points * scale, 7)

    cmap = matplotlib.colors.LinearSegmentedColormap.from_list('pcr', PCR_GAUGE_COLOURS)
    for step in range(90):
        ax.add_patch(matplotlib.patches.Wedge((0, 0), 1.0, 178 - 2 * step, 180 - 2 * step, width=0.3,
                                              facecolor=cmap((step + 0.5) / 90), edgecolor='none'))
    for value in PCR_GAUGE_TICKS:
        angle = np.radians(180 * (1 - value / (1 + value)))
        direction = np.array([np.cos(angle), np.sin(angle)])
        ax.plot(*zip(direction * 1.0, direction * 1.07), color='#454c50', linewidth=max(2 * scale, 1))
        ax.text(*(direction * 1.17), f'{value:g}', ha='center', va='center', fontsize=size(17), color='#373d41')
    pcr = figures['pcr']
    if not np.isnan(pcr):  # No needle without any open interest
        angle = np.radians(180 * (1 - (1.0 if np.isinf(pcr) else pcr / (1 + pcr))))
        tip = np.array([np.cos(angle), np.sin(angle)]) * 0.86
        side = np.array([-np.sin(angle), np.cos(angle)]) * 0.04
        ax.add_patch(matplotlib.patches.Polygon([tip, side, -side], closed=True, color='#2b2f33', zorder=4))
    ax.add_patch(matplotlib.patches.Circle((0, 0), 0.08, color='#2b2f33', zorder=5))
    ax.text(-0.85, -0.1, 'CALLS', ha='center', va='top', fontsize=size(20), fontweight='bold', color=PCR_CALL_COLOUR)
    ax.text(0.85, -0.1, 'PUTS', ha='center', va='top', fontsize=size(20), fontweight='bold', color=PCR_PUT_COLOUR)
    colour = PCR_CALL_COLOUR if pcr < 1 else PCR_PUT_COLOUR if pcr > 1 else '#454c50'
    ax.text(0, -0.2, f'PCR {_ratio_text(pcr)}', ha='center', va='top', fontsize=size(44), fontweight='bold',
            color=colour)
    ax.text(0, -0.52, f"Put OI {figures['put_oi']:,.0f}   /   Call OI {figures['call_oi']:,.0f}",
            ha='center', va='top', fontsize=size(17), color='#373d41')
    ax.text(0, -0.66, f"Volume PCR {_ratio_text(figures['pcr_volume'])}", ha='center', va='top',
            fontsize=size(17), color='#555b60')
    ax.text(0, 1.36, title, ha='center', va='bottom', fontsize=size(22), fontweight='bold', color='#24282b')
    ax.set_xlim(-1.32, 1.32)
    ax.set_ylim(-0.82, 1.62)
    ax.set_aspect('equal')
    ax.set_anchor('C')
    ax.set_axis_off()


def _draw_max_pain_chart(ax, snapshot, title, compact=False, xlabel=True):
    """Stacked call and put pain by strike: max pain arrowed, the spot and any expiry close as lines."""
    shown = _max_pain_window(snapshot['curve'], snapshot['max_pain'], snapshot['spot'])
    strikes = shown.index.to_numpy(float)
    x = np.arange(len(shown))
    call, put = shown['Call pain'].to_numpy() / 1e7, shown['Put pain'].to_numpy() / 1e7  # Rs crore
    top = float((call + put).max()) or 1.0
    size = 0.82 if compact else 1.0
    ax.bar(x, call, width=0.72, color=MAX_PAIN_CALL[0], edgecolor=MAX_PAIN_CALL[1], linewidth=1.2, label='Call pain')
    ax.bar(x, put, width=0.72, bottom=call, color=MAX_PAIN_PUT[0], edgecolor=MAX_PAIN_PUT[1], linewidth=1.2,
           label='Put pain')
    ax.set_ylim(0, top * 1.2)
    ax.set_xlim(-0.7, len(x) - 0.3)
    at = int(np.flatnonzero(strikes == snapshot['max_pain'])[0])
    align = 'left' if at < len(x) / 4 else 'right' if at > 3 * len(x) / 4 else 'center'
    ax.annotate(f"Max pain {_strike_label(snapshot['max_pain'])}", xy=(at, call[at] + put[at]),
                xytext=(at, call[at] + put[at] + top * 0.3), ha=align, va='bottom', fontsize=21 * size,
                fontweight='bold', color='#2b3fd6', bbox=MAX_PAIN_LABEL_BOX,
                arrowprops=dict(arrowstyle='-|>', color='#2b3fd6', lw=2.5))
    marks = [(snapshot['spot'], f"Spot {snapshot['spot']:,.2f} ({snapshot['date']:%d %b})", '#d62728', ':')]
    close = snapshot.get('close', np.nan)
    if np.isfinite(close):
        gap = (close - snapshot['max_pain']) / snapshot['max_pain']
        marks.append((close, f"Expiry close {close:,.2f} ({snapshot['expiry']:%d %b}), {gap:+.1%} vs max pain",
                       MAX_PAIN_CLOSE_COLOUR, '--'))
    for level, (price, label, colour, style) in enumerate(marks):
        if np.isfinite(price) and strikes[0] <= price <= strikes[-1]:
            where = float(np.interp(price, strikes, x))
            ax.axvline(where, color=colour, linestyle=style, linewidth=3)
            right = where <= (len(x) - 1) / 2  # The roomier side of the line
            ax.text(where + (0.25 if right else -0.25), top * (1.17 - 0.09 * level), label, color=colour,
                    fontsize=19 * size, va='top', ha='left' if right else 'right', bbox=MAX_PAIN_LABEL_BOX)
    ax.set_xticks(x)
    ax.set_xticklabels([_strike_label(strike) for strike in strikes], rotation=90,
                       fontsize=(14 if len(x) <= 30 else 11) * (0.9 if compact else 1.0))
    ax.tick_params(axis='y', labelsize=14 * size)
    if xlabel:
        ax.set_xlabel('Strike (settlement price at expiry)', fontsize=18 * size, fontweight='bold')
    ax.set_ylabel('Pain value (Rs crore)', fontsize=18 * size, fontweight='bold')
    ax.grid(axis='y', color='#d5dadd', alpha=0.7)
    ax.set_axisbelow(True)
    ax.spines[['top', 'right']].set_visible(False)
    ax.set_title(title, fontsize=24 * size, fontweight='bold', pad=48 * size)
    ax.legend(loc='lower center', bbox_to_anchor=(0.5, 1.0), ncol=2, fontsize=17 * size, frameon=False)


def plot_max_pain(positioning, ticker, pdf_pages=None):
    """One page of max pain beside PCR gauges for the latest option chain.

    With a settled expiry in the report range, the left side splits in two: that expiry's
    chain on the day before it settled, with its close, above the latest chain.
    """
    figure = plt.figure(figsize=(30, 17), facecolor='white')
    figure.suptitle(f"{ticker}   Max Pain & Put-Call Ratio   |   options of {positioning['date']:%d %b %Y}",
                    fontsize=32, fontweight='bold', y=0.975)
    latest = (f"Max Pain: {ticker} {positioning['date']:%d-%m-%Y}, latest options, "
              f"expiry {positioning['expiry']:%d %b %Y}")
    expired = positioning.get('expired')
    if expired:
        upper, lower = MAX_PAIN_HALVES
        _draw_max_pain_chart(figure.add_axes(upper), expired,
                             f"Max Pain: {ticker} {expired['date']:%d-%m-%Y}, the day before the "
                             f"{expired['expiry']:%d %b %Y} expiry", compact=True, xlabel=False)
        _draw_max_pain_chart(figure.add_axes(lower), positioning, latest, compact=True)
    else:
        _draw_max_pain_chart(figure.add_axes(MAX_PAIN_SINGLE), positioning, latest)

    gauges, hidden = _pcr_gauges(positioning)
    left, bottom, width, height = PCR_GAUGE_AREA
    columns, rows = _gauge_layout(len(gauges))
    cell_width, cell_height = width / columns, height / rows
    inner_width, inner_height = cell_width * (1 - 2 * PCR_GAUGE_PAD), cell_height * (1 - 2 * PCR_GAUGE_PAD)
    figure_width, figure_height = figure.get_size_inches()
    drawing = min(inner_height * figure_height, inner_width * figure_width / PCR_GAUGE_ASPECT)
    scale = min(1.0, drawing / PCR_GAUGE_FULL_SIZE)
    for number, (title, figures) in enumerate(gauges):
        row, column = divmod(number, columns)
        if row == rows - 1 and len(gauges) % columns:
            column = (columns - 1) / 2  # Centre a lone gauge on the last row
        _draw_pcr_gauge(figure.add_axes((left + (column + PCR_GAUGE_PAD) * cell_width,
                                         bottom + (rows - 1 - row + PCR_GAUGE_PAD) * cell_height,
                                         inner_width, inner_height)), title, figures, scale)
    figure.text(left + width / 2, bottom + height + 0.01,
                f"Put-Call Ratio (open interest)   |   {positioning['date']:%d %b %Y}", ha='center',
                va='bottom', fontsize=24, fontweight='bold', color='#24282b')
    notes = [
        'Max pain: the expiry settlement price at which in-the-money options are worth least, so option writers '
        'pay out least. Pain = open interest x intrinsic value; each bar stacks call and put pain.',
        'PCR: put open interest / call open interest'
        + (' of the only expiry. ' if len(gauges) == 1 else ' for all expiries, then each expiry, nearest first. ')
        + 'Above 1 (red) more puts, below 1 (green) more calls. A positioning snapshot, not a forecast.',
    ]
    if hidden:
        notes.append(f"PCR gauges show the nearest {len(gauges) - 1} of {len(positioning['expiries'])} expiries; "
                     'All expiries includes every one.')
    if positioning['date'] != positioning['as_of']:
        notes.append(f"Latest options on or before {positioning['as_of']:%d %b %Y}, the end of the report's range.")
    figure.text(0.055, 0.075, '\n'.join(notes), fontsize=14, color='#454c50', va='top', linespacing=1.5)
    if pdf_pages is not None:
        try:
            pdf_pages.savefig(figure)
        finally:
            plt.close(figure)
    else:
        plt.show()


def max_pain_analysis(ticker, as_of, start=None, pdf_pages=None):
    """Compute and render the max pain and put-call ratio page for a report range ending `as_of`."""
    try:
        positioning = option_positioning(ticker, as_of, start=start)
    except FileNotFoundError:
        print(f"  [max pain] No stored derivatives for {ticker}.")
        return None
    expired = positioning['expired']
    if expired:
        close = (f"expiry close {expired['close']:,.2f}" if np.isfinite(expired['close'])
                 else 'no expiry-day close stored')
        print(f"  [max pain] {expired['date']:%Y-%m-%d}, the day before the {expired['expiry']:%Y-%m-%d} expiry: "
              f"max pain {_strike_label(expired['max_pain'])}, {close}")
    print(f"  [max pain] {positioning['date']:%Y-%m-%d}, expiry {positioning['expiry']:%Y-%m-%d}: "
          f"max pain {_strike_label(positioning['max_pain'])}, spot {positioning['spot']:,.2f}, "
          f"PCR {_ratio_text(positioning['pcr'])} (all expiries {_ratio_text(positioning['pcr_all'])})")
    plot_max_pain(positioning, ticker, pdf_pages=pdf_pages)
    return positioning


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

def _number(value):
    """Float for a scalar cell, NaN when it is missing or not numeric."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def _audit_side(gap, tolerance):
    """Buy above +tolerance, Sell below -tolerance, Hold inside the band or when unknown."""
    if not np.isfinite(gap):
        return 'Hold'
    if gap > tolerance:
        return 'Buy'
    if gap < -tolerance:
        return 'Sell'
    return 'Hold'


def analyze_stock(data, ticker):
    """Run a multi-factor technical audit on the indicator DataFrame.

    Evaluates crossover signals, momentum, volatility, and fractal
    Fibonacci structure.  Each row's Status is Buy, Sell or Hold:

      - Line pairs (SMA/EMA crossovers, MACD vs Signal, Close vs BB mid):
        Buy when the first line is above the second by more than
        AUDIT_HOLD_ATR x ATR(20), Sell when below by more, else Hold.
      - RSI: Buy above 60, Sell below 40, Hold in between.
      - Fibonacci (last 60 bars): Buy above the 61.8% level, Sell below
        the 38.2% level, Hold in between.
      - Volume: only a bar above 1.2x its 20-bar average counts, as Buy on
        an up close and Sell on a down close; otherwise Hold.

    Missing inputs read Hold.  Returns a DataFrame with columns:
        Condition, Status, Verdict

    Args:
        data:   DataFrame with pre-computed indicators (Close, EMA/SMA
                columns, MACD, Signal, RSI, BB_up/BB_dn, Volume, etc.).
                Must already be indexed or have the Date column.
        ticker: Symbol name (for display only).
    """
    # Ensure we work with a copy to avoid side-effects
    df = data.copy()

    # Use the indicator columns already computed on full history (the lines drawn
    # on the page), under the short names used here
    ema_map = {'5DMA-E': 'EMA5', '9DMA-E': 'EMA9', '13DMA-E': 'EMA13',
               '21DMA-E': 'EMA21', '48DMA-E': 'EMA48'}
    sma_map = {'20DMA': 'SMA20', '50DMA': 'SMA50', '200DMA': 'SMA200'}
    for old, new in {**ema_map, **sma_map}.items():
        if old in df.columns and new not in df.columns:
            df[new] = df[old]

    # Compute any EMAs/SMAs that are still missing
    for span, col in [(5, 'EMA5'), (9, 'EMA9'), (13, 'EMA13'),
                      (21, 'EMA21'), (48, 'EMA48')]:
        if col not in df.columns:
            src = df['Close'] if 'Close' in df.columns else df.iloc[:, 0]
            df[col] = src.ewm(span=span, adjust=False).mean()
    for window, col in [(20, 'SMA20'), (50, 'SMA50'), (200, 'SMA200')]:
        if col not in df.columns:
            src = df['Close'] if 'Close' in df.columns else df.iloc[:, 0]
            df[col] = src.rolling(window=window).mean()

    # --- Fractal Fibonacci (last 60 bars ≈ 3 months) ---
    recent = df.tail(60)
    swing_high = recent['High'].max() if 'High' in recent.columns else recent['Close'].max()
    swing_low = recent['Low'].min() if 'Low' in recent.columns else recent['Close'].min()
    fib618 = swing_high - (0.382 * (swing_high - swing_low))
    fib382 = swing_high - (0.618 * (swing_high - swing_low))

    # --- Hold band: a fraction of the typical daily range ---
    atr = _number(df['ATR'].iloc[-1]) if 'ATR' in df.columns else np.nan
    if not atr > 0 and {'High', 'Low', 'Close'}.issubset(df.columns):
        atr = _number(ATR(df, 20)['ATR'].iloc[-1])
    tolerance = AUDIT_HOLD_ATR * atr if atr > 0 else 0.0

    # --- Current bar values ---
    curr = df.iloc[-1]
    close = _number(curr.get('Close'))
    volume = (pd.to_numeric(df['Volume'], errors='coerce') if 'Volume' in df.columns
              else pd.Series(0.0, index=df.index))
    vol_avg = volume.rolling(20).mean().iloc[-1]

    results = []

    # 1. Crossovers, MACD and the Bollinger midline: line A versus line B
    pairs = [
        ("Inst: 50/200 SMA", 'SMA50', 'SMA200',
         ("Bullish market regime", "Bearish market regime", "Regime at a crossover")),
        ("Mom: 9/21 EMA", 'EMA9', 'EMA21',
         ("Short-term acceleration", "Short-term deceleration", "Momentum flat")),
        ("Trend: 13/48 EMA", 'EMA13', 'EMA48',
         ("Confirmed uptrend", "Confirmed downtrend", "Trend at a crossover")),
        ("Hybrid: 5E / 20S", 'EMA5', 'SMA20',
         ("Price aggressive vs mean", "Price weak vs mean", "Price at its mean")),
        ("MACD vs Signal", 'MACD', 'Signal',
         ("Momentum engine firing", "Momentum engine stalling", "MACD at a crossover")),
    ]
    for condition, first, second, readings in pairs:
        gap = _number(curr.get(first)) - _number(curr.get(second))
        status = _audit_side(gap, tolerance)
        reading = dict(zip(('Buy', 'Sell', 'Hold'), readings))[status]
        results.append([condition, status, reading if np.isfinite(gap) else "Not enough history"])

    # 2. Momentum zone
    rsi_val = _number(curr.get('RSI'))
    if not np.isfinite(rsi_val):
        results.append(["RSI 14", "Hold", "Not enough history"])
    elif rsi_val > AUDIT_RSI_BUY:
        results.append([f"RSI 14 ({rsi_val:.0f})", "Buy", f"Bullish zone (> {AUDIT_RSI_BUY})"])
    elif rsi_val < AUDIT_RSI_SELL:
        results.append([f"RSI 14 ({rsi_val:.0f})", "Sell", f"Bearish zone (< {AUDIT_RSI_SELL})"])
    else:
        results.append([f"RSI 14 ({rsi_val:.0f})", "Hold",
                        f"Neutral zone ({AUDIT_RSI_SELL}-{AUDIT_RSI_BUY})"])

    midline = _number(curr.get('SMA20', curr.get('MA', np.nan)))
    status = _audit_side(close - midline, tolerance)
    results.append(["Close vs BB Mid", status,
                    {'Buy': "Bullish volatility channel", 'Sell': "Bearish volatility channel",
                     'Hold': "At the channel midline"}[status]])

    # 3. Fractal structure & filters
    if not np.isfinite(close) or not np.isfinite(fib618):
        results.append(["Fib 61.8%", "Hold", "Not enough history"])
    elif close > fib618:
        results.append([f"Fib 61.8% ({fib618:.0f})", "Buy", "Holding above pivot"])
    elif close < fib382:
        results.append([f"Fib 61.8% ({fib618:.0f})", "Sell", f"Below 38.2% ({fib382:.0f})"])
    else:
        results.append([f"Fib 61.8% ({fib618:.0f})", "Hold", "Between 38.2% and 61.8%"])

    if vol_avg > 0:
        previous = _number(df['Close'].iloc[-2]) if len(df) > 1 else np.nan
        change = close - previous
        surge = volume.iloc[-1] > vol_avg * AUDIT_VOLUME_SURGE
        if surge and change > 0:
            results.append(["Volume vs 1.2× avg", "Buy", "Volume confirms up day"])
        elif surge and change < 0:
            results.append(["Volume vs 1.2× avg", "Sell", "Volume confirms down day"])
        else:
            results.append(["Volume vs 1.2× avg", "Hold",
                            "Surge on a flat close" if surge else "No volume surge"])

    return pd.DataFrame(results, columns=["Condition", "Status", "Verdict"])


# ---------------------------------------------------------------------------
# Main chart builder
# ---------------------------------------------------------------------------

def technical_window_bars(dates, years=TECHNICAL_WINDOW_YEARS, months=0):
    """Count the bars dated within `years` calendar years and `months` months of the latest bar."""
    dates = pd.to_datetime(pd.Series(dates)).dropna()
    if dates.empty:
        return 0
    start = dates.max() - pd.DateOffset(years=years, months=months)
    return int((dates >= start).sum())


def _plot_available(ax, x, values, **kwargs):
    """Plot only the bars that have a value, so a missing day does not break the line."""
    values = np.asarray(values, dtype=float)
    present = np.isfinite(values)
    return ax.plot(x[present], values[present], **kwargs)


def _label_trading_days(ax, dates, max_ticks=13):
    """Date-label an x-axis whose bars sit at consecutive positions 0..N-1.

    Days without data (weekends, holidays) have no position, so they leave no
    gap. Ticks mark the first bar of each month, or evenly spaced bars when
    the window covers only a few months.
    """
    dates = pd.DatetimeIndex(dates)
    count = len(dates)
    if count == 0:
        return
    months = dates.to_period('M')
    ticks = np.flatnonzero(months[1:] != months[:-1]) + 1
    if len(ticks) < 4:
        ticks = np.unique(np.linspace(0, count - 1, min(count, 6)).round().astype(int))
    else:
        ticks = ticks[::math.ceil(len(ticks) / max_ticks)]

    def label(value, _pos):
        position = int(round(value))
        return dates[position].strftime('%d-%b-%y') if 0 <= position < count else ''

    ax.xaxis.set_major_locator(FixedLocator(ticks))
    ax.xaxis.set_major_formatter(FuncFormatter(label))
    ax.set_xlim(-1, count)


def plot_chart(DF, n, ticker, Dividend=0, pdf_pages=None):
    """Generate the multi-panel technical analysis chart.

    Args:
        DF:        DataFrame with indicators already computed
        n:         Number of trailing price bars shown by the indicator panels
                   (Renko keeps its own last 100 bricks)
        ticker:    Symbol name
        Dividend:  Expected dividend (for futures fair-value calc)
        pdf_pages: Optional PdfPages object — if set, saves to PDF instead of plt.show()
    """
    data = DF.copy()
    data = data[data['Close'].notna()]  # rows without a price are skipped

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

    # ── Try loading futures for overlay ───────────────────────────────
    # Max Pain is not merged in: no panel shows it, and its option-only
    # dates would add rows without a price.
    Futdf = None

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

    # Bars sit at consecutive positions, so days without data take no space
    x = np.arange(len(data))

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

    for col in ["5DMA-E", "9DMA-E", "13DMA-E", "21DMA-E", "48DMA-E"]:
        if col in data.columns:
            _plot_available(ax_ema, x, data[col], label=col)
    _plot_available(ax_ema, x, data['Close'], color='black', linestyle=':', linewidth=2.5, label=f"{ticker} Price", zorder=10)
    ax_ema.legend(fontsize=20)
    ax_ema.grid(True)
    ax_ema.tick_params(labelsize=20)
    ax_ema.set_title('EMA Crossover', fontsize=30, fontweight='bold', pad=8)

    # ── SMA panel ─────────────────────────────────────────────────────
    for col in ["20DMA", "50DMA", "200DMA"]:
        if col in data.columns:
            _plot_available(ax_sma, x, data[col], label=col)
    _plot_available(ax_sma, x, data['Close'], color='black', linestyle=':', linewidth=2.5, label=f"{ticker} Price", zorder=10)
    ax_sma.legend(fontsize=20)
    ax_sma.grid(True)
    ax_sma.tick_params(labelsize=20)
    ax_sma.set_title('SMA Crossover', fontsize=30, fontweight='bold', pad=8)

    # ── MACD panel ────────────────────────────────────────────────────
    _plot_available(ax_macd, x, data["MACD"], label="MACD")
    ax_macd.bar(x, (data["MACD"] - data["Signal"]) * 3, label="hist")
    _plot_available(ax_macd, x, data["Signal"], label="Signal")
    ax_macd.legend(fontsize=20)
    ax_macd.grid(True)
    ax_macd.tick_params(labelsize=20)
    ax_macd.set_title('MACD (12, 26, 9)', fontsize=30, fontweight='bold', pad=8)

    # ── RSI & ADX panel ───────────────────────────────────────────────
    ax_rsi.set_ylabel("(%)")
    ax_rsi.axhline(70, color='grey', linestyle='--', label="overbought")
    ax_rsi.axhline(30, color='grey', linestyle='--', label="oversold")
    ax_rsi.axhline(50, color='grey', linestyle=':')
    _plot_available(ax_rsi, x, data["RSI"], label="RSI", color='lightpink')
    if 'ADX' in data.columns:
        _plot_available(ax_rsi, x, data["ADX"], label="ADX", color='blue')
    if 'DIplusN' in data.columns:
        _plot_available(ax_rsi, x, data["DIplusN"], label="DI+", color='green')
    if 'DIminusN' in data.columns:
        _plot_available(ax_rsi, x, data["DIminusN"], label="DI-", color='red')
    ax_rsi.legend(fontsize=20)
    ax_rsi.grid(True)
    ax_rsi.tick_params(labelsize=20)
    ax_rsi.set_title('RSI & ADX', fontsize=30, fontweight='bold', pad=8)

    # ── Bollinger Bands + OBV panel ───────────────────────────────────
    _plot_available(ax_bba, x, data["BB_up"], label="BB_up")
    _plot_available(ax_bba, x, data["BB_dn"], label="BB_dn")
    _plot_available(ax_bba, x, data["MA"], label="MA")
    _plot_available(ax_bba, x, data['Close'], color='black', linestyle=':', linewidth=2.5, label='Close Price', zorder=10)
    ax_bba.legend(fontsize=20)
    ax_bba.grid(True)
    ax_bba.tick_params(labelsize=20)
    ax_bba.set_title('Bollinger Bands & OBV', fontsize=30, fontweight='bold', pad=8)

    if 'OBV' in data.columns:
        ax_obv = ax_bba.twinx()
        _plot_available(ax_obv, x, data["OBV"] / 100000, marker="*", label="OBV")
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
    _plot_available(ax_fibret, x, data['Close'], color='black', linestyle=':', linewidth=2.5, label='Close Price', zorder=10)

    # Shared by every indicator panel above (Renko has its own axis)
    _label_trading_days(ax_macd, data.index)

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
        # Status cell: green Buy, red Sell, amber Hold
        cell_colours = [['#f2f2f2', AUDIT_COLOURS[status], '#f2f2f2']
                        for status in report['Status']]

        tbl = ax_table.table(
            cellText=report.values,
            colLabels=report.columns,
            cellColours=cell_colours,
            colColours=['#4472c4'] * 3,
            colWidths=[0.34, 0.16, 0.50],
            cellLoc='center',
            loc='upper center',
        )
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(23)
        tbl.scale(1.0, 6.0)  # Stretch rows for readability
        # Style header row; Buy/Sell/Hold in bold
        for (r, c), cell in tbl.get_celld().items():
            if r == 0:
                cell.set_text_props(color='white', fontweight='bold')
            elif c == 1:
                cell.set_text_props(fontweight='bold')
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
# Swing-trading pages: candlesticks, swing structure, confirmed pivots, formations
# ---------------------------------------------------------------------------

SWING_BULL_COLOUR, SWING_BEAR_COLOUR = TREND_SUPPORT_COLOUR, TREND_RESISTANCE_COLOUR
SWING_NEUTRAL_COLOUR = '#c88a04'
SWING_CHART_AXES = (0.05, 0.43, 0.90, 0.46)   # Price chart: left, bottom, width, height
SWING_SUMMARY_LEFT, SWING_SUMMARY_TOP = 0.59, 0.36
SWING_SUMMARY_WRAP = 76                        # Characters per line of the reading notes
SWING_CELL = '#f7f7f7'
SWING_CELL_COLOURS = {'Bullish': AUDIT_COLOURS['Buy'], 'Bearish': AUDIT_COLOURS['Sell'],
                      'Mixed': AUDIT_COLOURS['Hold'], 'Consolidation': AUDIT_COLOURS['Hold'],
                      'Confirmed': AUDIT_COLOURS['Buy'], 'Failed': AUDIT_COLOURS['Sell'],
                      'Pending': AUDIT_COLOURS['Hold']}


def _ohlc_bars(price_data):
    """Date-sorted numeric Open/High/Low/Close bars; a bar missing any price is dropped."""
    missing = {'Open', 'High', 'Low', 'Close'} - set(price_data.columns)
    if missing:
        raise ValueError(f"missing OHLC columns: {', '.join(sorted(missing))}")
    frame = price_data[['Open', 'High', 'Low', 'Close']].apply(pd.to_numeric, errors='coerce')
    frame.index = pd.DatetimeIndex(pd.to_datetime(frame.index, errors='coerce'))
    frame = frame[frame.index.notna()].replace([np.inf, -np.inf], np.nan).dropna().sort_index()
    frame = frame[~frame.index.duplicated(keep='last')]
    if frame.empty:
        raise ValueError('no complete OHLC bars')
    return frame


def _level_gap(level, close):
    """A level's distance from the close, '+2.1%', or 'n/a'."""
    if level is None or not np.isfinite(level) or not close > 0:
        return 'n/a'
    return f'{(level / close - 1) * 100:+.1f}%'


def _swing_page(ticker, title, shown, subtitle):
    """A new page: title with the shown range, a subtitle line and the price-chart axes."""
    figure = plt.figure(figsize=(30, 17), facecolor='white')
    figure.suptitle(f"{ticker}   {title}   |   {shown.index[0]:%d %b %Y} \u2192 {shown.index[-1]:%d %b %Y}"
                    f"   |   {len(shown):,} sessions", fontsize=30, fontweight='bold', y=0.975)
    figure.text(0.05, 0.928, subtitle, fontsize=15, color='#454c50')
    return figure, figure.add_axes(SWING_CHART_AXES)


def _style_price_axis(ax, shown):
    """Date ticks on consecutive bar positions, a price grid and an open frame."""
    _label_trading_days(ax, shown.index)
    ax.yaxis.set_major_formatter(FuncFormatter(
        lambda value, _: f'{value:,.2f}' if abs(value) < 100 else f'{value:,.0f}'))
    ax.tick_params(labelsize=14)
    ax.grid(axis='y', color='#d5dadd', alpha=0.6)
    ax.set_axisbelow(True)
    ax.spines[['top', 'right']].set_visible(False)
    ax.set_ylabel('Price', fontsize=16)


def _draw_price_bars(ax, shown):
    """Candles at consecutive positions, so non-trading days leave no gap; flat bars get a close line."""
    x = np.arange(len(shown))
    if _has_intraday_range(shown):
        opens, highs, lows, closes = (shown[column].to_numpy(dtype=float)
                                      for column in ('Open', 'High', 'Low', 'Close'))
        colours = np.where(closes >= opens, SWING_BULL_COLOUR, SWING_BEAR_COLOUR)
        ax.vlines(x, lows, highs, colors=colours, linewidth=1.2, zorder=2)
        ax.bar(x, np.abs(closes - opens), bottom=np.minimum(opens, closes), width=0.62,
               color=colours, edgecolor=colours, linewidth=0.8, zorder=3)
    else:
        ax.plot(x, shown['Close'].to_numpy(dtype=float), color='#24282b', linewidth=2, zorder=3)
    _style_price_axis(ax, shown)
    return x


def _price_pad(shown, fraction=0.025):
    """Marker offset from a bar: a fraction of the shown high-low range."""
    return float(shown['High'].max() - shown['Low'].min()) * fraction or 1.0


def _price_text(value):
    """Whole prices from 1,000 up, two decimals below, so table cells stay short."""
    return f'{value:,.0f}' if abs(value) >= 1000 else f'{value:,.2f}'


def _swing_table(figure, rect, title, columns, rows, widths, colours=None, fontsize=13):
    """Bordered table with a blue header row in its own axes; no rows reads None."""
    axes = figure.add_axes(rect)
    axes.axis('off')
    if not rows:
        rows, colours = [['None'] + [''] * (len(columns) - 1)], None
    table = axes.table(cellText=rows, colLabels=columns, colWidths=widths, cellColours=colours,
                       cellLoc='left', colLoc='left', loc='upper left')
    table.auto_set_font_size(False)
    table.set_fontsize(fontsize)
    table.scale(1.0, 1.9)
    for (row, _), cell in table.get_celld().items():
        cell.set_edgecolor('#cccccc')
        if row == 0:
            cell.set_facecolor('#4472c4')
            cell.set_text_props(color='white', fontweight='bold')
    axes.set_title(title, fontsize=18, fontweight='bold', loc='left', pad=10)
    return axes


def _swing_summary(figure, items):
    """'How to read this page': (label, text) notes stacked beside the tables."""
    left, y = SWING_SUMMARY_LEFT, SWING_SUMMARY_TOP
    figure.text(left, y, 'How to read this page', fontsize=19, fontweight='bold', color='#1f3864', va='top')
    y -= 0.034
    for label, text in items:
        figure.text(left, y, label, fontsize=14, fontweight='bold', color='#555555', va='top')
        body = figure.text(left + 0.068, y, textwrap.fill(text, SWING_SUMMARY_WRAP), fontsize=14,
                           va='top', linespacing=1.3)
        y -= body.get_window_extent().height / figure.bbox.height + 0.013


def _save_swing_page(figure, pdf_pages):
    if pdf_pages is not None:
        try:
            pdf_pages.savefig(figure)
        finally:
            plt.close(figure)
    else:
        plt.show()


def _follow_through(shown, position, direction):
    """Confirmed or Failed, dated, on the first later close beyond the signal candle; else Pending."""
    if direction == 'Mixed':
        return 'Mixed: no direction'
    later = shown.iloc[position + 1:]
    above = later.index[later['Close'] > shown['High'].iloc[position]]
    below = later.index[later['Close'] < shown['Low'].iloc[position]]
    if above.empty and below.empty:
        return 'Pending'
    broke_up = not above.empty and (below.empty or above[0] < below[0])
    worked = broke_up == (direction == 'Bullish')
    return f"{'Confirmed' if worked else 'Failed'} {(above[0] if broke_up else below[0]):%d %b}"


def compute_candlestick_signals(price_data, bars, patterns=CANDLE_PATTERNS):
    """pandas-ta-classic reversal candles on all history to the range end, kept for the last `bars`.

    Positive pattern values are bullish and negative bearish. Follow-through is the first later
    close in the range beyond the signal candle: above its high confirms a bullish candle (and
    fails a bearish one), below its low does the reverse.
    """
    if not HAS_PANDAS_TA:
        raise ValueError('pandas-ta-classic is not installed (pip install pandas-ta-classic)')
    history = _ohlc_bars(price_data)
    if not _has_intraday_range(history):
        raise ValueError('candle patterns need real open/high/low/close bars, not flat single-value bars')
    found = pandas_ta_classic.cdl_pattern(history['Open'], history['High'], history['Low'],
                                          history['Close'], name=list(patterns))
    shown = history.tail(bars)
    found = (pd.DataFrame(index=history.index) if found is None else found).reindex(shown.index).fillna(0.0)
    signals = []
    for position, (date, row) in enumerate(found.iterrows()):
        values = {label: row.get(f'CDL_{name.upper()}', 0.0) for name, label in patterns.items()}
        bullish = [label for label, value in values.items() if value > 0]
        bearish = [label for label, value in values.items() if value < 0]
        if not bullish and not bearish:
            continue
        direction = 'Mixed' if bullish and bearish else 'Bullish' if bullish else 'Bearish'
        signals.append({'Date': date, 'Position': position, 'Close': shown['Close'].iloc[position],
                        'High': shown['High'].iloc[position], 'Low': shown['Low'].iloc[position],
                        'Direction': direction, 'Bullish': bullish, 'Bearish': bearish,
                        'Follow-through': _follow_through(shown, position, direction)})
    columns = ['Date', 'Position', 'Close', 'High', 'Low', 'Direction', 'Bullish', 'Bearish', 'Follow-through']
    return {'shown': shown, 'signals': pd.DataFrame(signals, columns=columns)}


def _candle_names(signal):
    """'Hammer, Engulfing', or each name tagged bull / bear on a mixed day."""
    if signal['Direction'] == 'Mixed':
        return ', '.join([f'{name} (bull)' for name in signal['Bullish']]
                         + [f'{name} (bear)' for name in signal['Bearish']])
    return ', '.join(signal['Bullish'] or signal['Bearish'])


def plot_candlesticks(profile, ticker, pdf_pages=None):
    """Candles with reversal-pattern markers, the latest signal days and how to read them."""
    shown, signals = profile['shown'], profile['signals']
    figure, chart = _swing_page(
        ticker, 'Candlestick Reversal Setups', shown,
        'pandas-ta-classic native patterns: ' + ', '.join(label.lower() for label in CANDLE_PATTERNS.values())
        + '   |   found on all history up to the range end')
    _draw_price_bars(chart, shown)
    pad = _price_pad(shown, 0.03)
    for kind, marker, colour, below in (('Bullish', '^', SWING_BULL_COLOUR, True),
                                        ('Bearish', 'v', SWING_BEAR_COLOUR, False)):
        rows = signals[signals['Direction'].isin([kind, 'Mixed'])]
        if len(rows):
            chart.scatter(rows['Position'], rows['Low'] - pad if below else rows['High'] + pad, marker=marker,
                          s=190, color=colour, edgecolors='#24282b', linewidths=0.7, zorder=5,
                          label=f'{kind} pattern')
    latest = signals.iloc[::-1].head(CANDLE_SIGNAL_ROWS).reset_index(drop=True)
    for number, signal in latest.iterrows():
        below = signal['Direction'] != 'Bearish'
        chart.text(signal['Position'], signal['Low'] - 2.1 * pad if below else signal['High'] + 2.1 * pad,
                   str(number + 1), ha='center', va='top' if below else 'bottom', fontsize=13,
                   fontweight='bold', color='#24282b', zorder=6)
    chart.set_ylim(shown['Low'].min() - 3.8 * pad, shown['High'].max() + 3.8 * pad)
    if len(signals):
        chart.legend(fontsize=13, loc='best', framealpha=0.85)

    rows, colours = [], []
    for number, signal in latest.iterrows():
        outcome = signal['Follow-through'].split()[0]
        rows.append([str(number + 1), f"{signal['Date']:%d %b %Y}", f"{signal['Close']:,.2f}",
                     signal['Direction'], _candle_names(signal), signal['Follow-through']])
        colours.append([SWING_CELL] * 3 + [SWING_CELL_COLOURS[signal['Direction']], SWING_CELL,
                                           SWING_CELL_COLOURS.get(outcome, SWING_CELL)])
    _swing_table(figure, (0.05, 0.04, 0.50, 0.32), f'Latest {CANDLE_SIGNAL_ROWS} signal days (#1 latest)',
                 ['#', 'Date', 'Close', 'Signal', 'Patterns', 'Follow-through'], rows,
                 [0.05, 0.15, 0.13, 0.12, 0.34, 0.21], colours)

    counts = signals['Direction'].value_counts()
    outcomes = signals['Follow-through'].str.split().str[0].value_counts()
    if latest.empty:
        now = f'No reversal pattern in these {len(shown)} sessions.'
    else:
        last = latest.iloc[0]
        now = (f"{counts.get('Bullish', 0)} bullish and {counts.get('Bearish', 0)} bearish signal days"
               + (f" ({counts['Mixed']} mixed)" if counts.get('Mixed', 0) else '')
               + f"; follow-through {outcomes.get('Confirmed', 0)} confirmed, {outcomes.get('Failed', 0)} "
               f"failed, {outcomes.get('Pending', 0)} pending. Latest (#1): {_candle_names(last)} "
               f"({last['Direction'].lower()}) on {last['Date']:%d %b} at {last['Close']:,.2f}; "
               f"follow-through: {last['Follow-through']}.")
    _swing_summary(figure, [
        ('What you see', 'Daily candles. A green \u25b2 below a candle marks a bullish reversal pattern '
                         '(hammer, morning star, piercing line, bullish engulfing); a red \u25bc above marks '
                         'a bearish one (shooting star, evening star, bearish engulfing). Numbers match '
                         'the table.'),
        ('How to read', 'A pattern is a prompt, not a trade: it matters most at support or resistance or '
                        'after an extended move. It needs follow-through: a later close above the signal '
                        "candle's high confirms a bullish pattern, below its low a bearish one; the "
                        'opposite close means it failed.'),
        ('Now', now)])
    _save_swing_page(figure, pdf_pages)


def candlestick_analysis(price_data, ticker, bars, pdf_pages=None):
    """Compute and render the candlestick reversal page."""
    profile = compute_candlestick_signals(price_data, bars)
    counts = profile['signals']['Direction'].value_counts()
    print(f"  [candlesticks] {len(profile['shown'])} sessions: {len(profile['signals'])} signal days "
          f"({counts.get('Bullish', 0)} bullish, {counts.get('Bearish', 0)} bearish, "
          f"{counts.get('Mixed', 0)} mixed)")
    plot_candlesticks(profile, ticker, pdf_pages=pdf_pages)
    return profile


def compute_swing_structure(price_data, bars, retrace_pct=SWING_RETRACE_PCT):
    """swingtrend's trend, breaks of structure and change-of-character level, bar by bar.

    Bars reach Swing.identify() one at a time, over all history up to the range end so the state
    is warm when the shown window starts; Swing.run() would read the columns by position, which
    stored frames do not guarantee. In an up-trend the breakout level is the swing-point high (SPH)
    and the reversal level the change of character (CoCh) below; a down-trend mirrors them.
    """
    if not HAS_SWINGTREND:
        raise ValueError('swingtrend is not installed (pip install swingtrend)')
    history = _ohlc_bars(price_data)
    if not (history[['High', 'Low', 'Close']] > 0).all().all():
        raise ValueError('swing retracements are percentages, so every price must be positive')
    events = []

    def record(kind):
        def callback(swing, date, close, **level):
            events.append({'Date': pd.Timestamp(date), 'Event': kind, 'Trend': swing.trend,
                           'Close': float(close), 'Level': float(next(iter(level.values())))})
        return callback

    swing = Swing(retrace_threshold_pct=retrace_pct, on_breakout=record('BOS'),
                  on_reversal=record('Reversal'))
    states = []
    for date, high, low, close in zip(history.index, history['High'], history['Low'], history['Close']):
        swing.identify(date, float(high), float(low), float(close))
        trigger = swing.sph if swing.trend == 'UP' else swing.spl if swing.trend == 'DOWN' else None
        states.append((swing.trend or '', np.nan if swing.coc is None else swing.coc,
                       np.nan if trigger is None else trigger))
    state = pd.DataFrame(states, index=history.index, columns=['Trend', 'CoCh', 'Breakout'])
    runs = state['Trend'].ne(state['Trend'].shift()).to_numpy()
    up = swing.trend == 'UP'
    current = {
        'trend': swing.trend, 'since': state.index[runs][-1], 'legs': swing.leg_count,
        'coc': swing.coc, 'coc_date': swing.coc_dt,
        'breakout': swing.sph if up else swing.spl, 'breakout_date': swing.sph_dt if up else swing.spl_dt,
        'bars_since': swing.bars_since, 'sideways': swing.is_sideways,
        'sideways_bars': swing.sideways_threshold, 'close': float(history['Close'].iloc[-1]),
    }
    return {'shown': history.tail(bars), 'state': state.tail(bars), 'current': current,
            'events': pd.DataFrame(events, columns=['Date', 'Event', 'Trend', 'Close', 'Level']),
            'retrace_pct': retrace_pct}


def _swing_level(value, when, close):
    """'24,210.00 on 21 Oct 2026 (-3.4%)', or 'none yet'."""
    if value is None:
        return 'none yet: the leg is still extending'
    return f'{value:,.2f} on {when:%d %b %Y} ({_level_gap(value, close)})'


def plot_swing_structure(profile, ticker, pdf_pages=None):
    """Candles shaded by trend with the CoCh and breakout levels, events, current state and notes."""
    shown, state, current = profile['shown'], profile['state'], profile['current']
    figure, chart = _swing_page(
        ticker, 'Swing Structure', shown,
        f"swingtrend Dow-style swings   |   CoCh moves only after a pullback of at least "
        f"{profile['retrace_pct']:g}%   |   state built on all history up to the range end")
    x = _draw_price_bars(chart, shown)
    trend = state['Trend'].to_numpy()
    for kind, colour, reversal, breakout in (('UP', SWING_BULL_COLOUR, SWING_BEAR_COLOUR, SWING_BULL_COLOUR),
                                             ('DOWN', SWING_BEAR_COLOUR, SWING_BULL_COLOUR, SWING_BEAR_COLOUR)):
        inside = trend == kind
        edges = np.flatnonzero(np.diff(np.concatenate([[0], inside.astype(int), [0]])))
        for start, stop in zip(edges[::2], edges[1::2]):
            chart.axvspan(start - 0.5, stop - 0.5, color=colour, alpha=0.08, linewidth=0, zorder=0)
        chart.plot(x, np.where(inside, state['CoCh'], np.nan), drawstyle='steps-mid', color=reversal,
                   linestyle='--', linewidth=2.4, zorder=4)
        chart.plot(x, np.where(inside, state['Breakout'], np.nan), drawstyle='steps-mid', color=breakout,
                   linestyle=':', linewidth=2.6, zorder=4)
    events = profile['events']
    events = events[(events['Date'] >= shown.index[0]) & (events['Date'] <= shown.index[-1])]
    for position, (_, event) in zip(shown.index.get_indexer(events['Date']), events.iterrows()):
        colour = SWING_BULL_COLOUR if event['Trend'] == 'UP' else SWING_BEAR_COLOUR
        reversal = event['Event'] == 'Reversal'
        chart.scatter([position], [event['Close']], marker='*' if reversal else '^' if event['Trend'] == 'UP' else 'v',
                      s=560 if reversal else 170, color=colour, edgecolors='#24282b', linewidths=0.8, zorder=6)
    chart.legend(handles=[
        matplotlib.patches.Patch(color=SWING_BULL_COLOUR, alpha=0.25, label='Up-trend'),
        matplotlib.patches.Patch(color=SWING_BEAR_COLOUR, alpha=0.25, label='Down-trend'),
        plt.Line2D([], [], color='#555b60', linestyle='--', linewidth=2.4, label='CoCh: a close beyond it reverses'),
        plt.Line2D([], [], color='#555b60', linestyle=':', linewidth=2.6, label='Swing point: a close beyond it is a BOS'),
        plt.Line2D([], [], color='#555b60', marker='^', linestyle='none', markersize=12, label='Break of structure (BOS)'),
        plt.Line2D([], [], color='#555b60', marker='*', linestyle='none', markersize=18, label='Reversal'),
    ], fontsize=13, loc='best', framealpha=0.85)
    # Fit candles and today's levels; older far-off levels are clipped at the frame.
    levels = [level for level in (current['coc'], current['breakout']) if level is not None]
    low, high = min([shown['Low'].min(), *levels]), max([shown['High'].max(), *levels])
    chart.set_ylim(low - (high - low) * 0.06, high + (high - low) * 0.06)

    direction, close = current['trend'], current['close']
    legs = f"{current['legs']} break{'' if current['legs'] == 1 else 's'} of structure"
    pace = ('>', 'sideways') if current['sideways'] else ('\u2264', 'trending')
    rows = [
        ['Trend', f"{direction} since {current['since']:%d %b %Y}" if direction
         else "Not set: no close beyond the first bar's range"],
        ['Legs in this trend', legs],
        ['Breakout level (' + ('SPL' if direction == 'DOWN' else 'SPH') + ')',
         _swing_level(current['breakout'], current['breakout_date'], close)],
        ['Reversal level (CoCh)', _swing_level(current['coc'], current['coc_date'], close)],
        ['Sessions since swing', f"{current['bars_since']} ({pace[0]} {current['sideways_bars']}: {pace[1]})"],
        ['Close', f'{close:,.2f}'],
    ]
    _swing_table(figure, (0.05, 0.04, 0.28, 0.32), 'Current structure', ['Measure', 'Value'], rows, [0.33, 0.67])
    recent = profile['events'].iloc[::-1].head(SWING_EVENT_ROWS)
    _swing_table(
        figure, (0.35, 0.04, 0.21, 0.32), 'Latest structure events', ['Date', 'Event', 'Close', 'Level'],
        [[f"{event['Date']:%d %b %Y}",
          f"Reversal \u2192 {event['Trend']}" if event['Event'] == 'Reversal'
          else f"BOS {'up' if event['Trend'] == 'UP' else 'down'}",
          f"{event['Close']:,.2f}", f"{event['Level']:,.2f}"] for _, event in recent.iterrows()],
        [0.3, 0.3, 0.2, 0.2],
        [[SWING_CELL, SWING_CELL_COLOURS['Bullish' if event['Trend'] == 'UP' else 'Bearish'], SWING_CELL, SWING_CELL]
         for _, event in recent.iterrows()])

    if direction:
        breakout = (f"breakout {current['breakout']:,.2f} ({_level_gap(current['breakout'], close)})"
                    if current['breakout'] is not None else 'no swing point to break yet (the leg is extending)')
        now = (f"{direction} since {current['since']:%d %b %Y} with {legs}. "
               f"Close {close:,.2f}: {breakout}; reversal (CoCh) {current['coc']:,.2f} "
               f"({_level_gap(current['coc'], close)}). {current['bars_since']} sessions since the last swing "
               f"point, so {'sideways' if current['sideways'] else 'still trending'}.")
    else:
        now = "No trend yet: no close beyond the first bar's range."
    _swing_summary(figure, [
        ('What you see', 'Candles shaded by the swingtrend state: green up-trend, red down-trend. Dashed: the '
                         'change-of-character (CoCh) level; a close beyond it reverses the trend. Dotted: the '
                         'latest swing point; a close beyond it is a break of structure (BOS), a new leg. '
                         'Triangles mark breaks of structure, stars reversals.'),
        ('How to read', 'An up-trend keeps making higher swing highs while pullbacks hold above CoCh; a '
                        f"down-trend mirrors it. Pullbacks under {profile['retrace_pct']:g}% are noise and "
                        f"leave CoCh unchanged. Sideways means no new swing point for {current['sideways_bars']} "
                        'sessions; the trend label holds until a break.'),
        ('Now', now)])
    _save_swing_page(figure, pdf_pages)


def swing_structure_analysis(price_data, ticker, bars, pdf_pages=None):
    """Compute and render the swing-structure page."""
    profile = compute_swing_structure(price_data, bars)
    current = profile['current']
    print(f"  [swing structure] {current['trend'] or 'no trend'} since {current['since']:%Y-%m-%d}, "
          f"{current['legs']} legs, CoCh {'none' if current['coc'] is None else format(current['coc'], ',.2f')}, "
          f"breakout {'none' if current['breakout'] is None else format(current['breakout'], ',.2f')}")
    plot_swing_structure(profile, ticker, pdf_pages=pdf_pages)
    return profile


def confirmed_pivots(frame, order=PIVOT_ORDER):
    """Positions of pivot highs and lows that `order` bars on each side have confirmed.

    argrelextrema with >= / <= marks the highest High / lowest Low of its 2 x order + 1 bars.
    Bars within `order` of either end are unconfirmed, equal extremes on one plateau count once
    (the first), and a window without any range (flat bars) has no turning point.
    """
    def confirmed(values, comparator):
        kept = []
        for position in argrelextrema(values, comparator, order=order)[0]:
            if position < order or position >= len(values) - order:
                continue
            if np.ptp(values[position - order:position + order + 1]) == 0:
                continue
            if kept and position - kept[-1] <= order:
                continue
            kept.append(int(position))
        return np.asarray(kept, dtype=int)

    return (confirmed(frame['High'].to_numpy(dtype=float), np.greater_equal),
            confirmed(frame['Low'].to_numpy(dtype=float), np.less_equal))


def _window_pivots(history, positions, column, offset):
    """[(position in the shown window, price, date)] for the pivots inside it."""
    return [(int(position) - offset, float(history[column].iloc[position]), history.index[position])
            for position in positions if position >= offset]


def _pivot_structure(highs, lows):
    """Dow reading of the last two confirmed pivot highs and lows."""
    if len(highs) < 2 or len(lows) < 2:
        return 'too few confirmed pivots for a structure reading'

    def compare(last, previous, word):
        return f'higher {word}' if last > previous else f'lower {word}' if last < previous else f'equal {word}s'

    high, low = compare(highs[-1][1], highs[-2][1], 'high'), compare(lows[-1][1], lows[-2][1], 'low')
    reading = {('higher high', 'higher low'): 'up-trend structure',
               ('lower high', 'lower low'): 'down-trend structure',
               ('lower high', 'higher low'): 'contracting range',
               ('higher high', 'lower low'): 'expanding range'}.get((high, low), 'transitional structure')
    return f'{high} and {low}: {reading}'


def compute_pivot_levels(price_data, bars, order=PIVOT_ORDER):
    """Confirmed pivots on all history to the range end, listed and levelled for the last `bars`."""
    history = _ohlc_bars(price_data)
    if len(history) < 2 * order + 1:
        raise ValueError(f'only {len(history)} bars; a pivot needs {order} bars on each side')
    high_idx, low_idx = confirmed_pivots(history, order)
    shown = history.tail(bars)
    offset = len(history) - len(shown)
    highs = _window_pivots(history, high_idx, 'High', offset)
    lows = _window_pivots(history, low_idx, 'Low', offset)
    close = float(shown['Close'].iloc[-1])
    return {'shown': shown, 'order': order, 'highs': highs, 'lows': lows, 'close': close,
            'resistance': min((price for _, price, _ in highs if price > close), default=None),
            'support': max((price for _, price, _ in lows if price < close), default=None),
            'structure': _pivot_structure(highs, lows), 'unconfirmed': min(order, len(shown))}


def _mark_pivots(chart, profile, pad, size=190, alpha=1.0, labels=True):
    """Red down-triangles above pivot highs and green up-triangles below pivot lows."""
    for pivots, marker, colour, sign, name in ((profile['highs'], 'v', SWING_BEAR_COLOUR, 1, 'Pivot high'),
                                               (profile['lows'], '^', SWING_BULL_COLOUR, -1, 'Pivot low')):
        if pivots:
            positions, prices, _ = zip(*pivots)
            chart.scatter(positions, np.asarray(prices) + sign * pad, marker=marker, s=size, color=colour,
                          alpha=alpha, edgecolors='#24282b', linewidths=0.6, zorder=5,
                          label=name if labels else '_nolegend_')


def plot_pivots(profile, ticker, pdf_pages=None):
    """Close with confirmed pivot markers above the pivot tables, levels and notes."""
    shown, order, close = profile['shown'], profile['order'], profile['close']
    figure, chart = _swing_page(
        ticker, 'Confirmed Pivot Highs & Lows', shown,
        f'SciPy argrelextrema, order {order}: the highest high / lowest low of {order} sessions on each side'
        '   |   equal highs on a plateau count once   |   no look-ahead')
    x = np.arange(len(shown))
    chart.vlines(x, shown['Low'], shown['High'], colors='#b8bec3', linewidth=2.4, zorder=2)
    chart.plot(x, shown['Close'], color='#24282b', linewidth=2, zorder=3, label='Close (grey: high-low range)')
    _style_price_axis(chart, shown)
    pad = _price_pad(shown)
    _mark_pivots(chart, profile, pad)
    for pivots, colour in ((profile['highs'], SWING_BEAR_COLOUR), (profile['lows'], SWING_BULL_COLOUR)):
        for position, price, _ in pivots[-PIVOT_ROWS:]:
            chart.hlines(price, position, len(shown) - 1, colors=colour, linestyles=':', linewidth=1.5,
                         alpha=0.75, zorder=1)
    edge = len(shown) - profile['unconfirmed'] - 0.5
    for level, colour, va, name in ((profile['resistance'], SWING_BEAR_COLOUR, 'bottom', 'Nearest resistance'),
                                    (profile['support'], SWING_BULL_COLOUR, 'top', 'Nearest support')):
        if level is not None:
            chart.axhline(level, color=colour, linestyle='--', linewidth=2.2, zorder=1)
            chart.text(edge - 1, level, f'{name} {level:,.2f} ({_level_gap(level, close)})', ha='right', va=va,
                       fontsize=13, fontweight='bold', color=colour, bbox=MAX_PAIN_LABEL_BOX, zorder=7)
    chart.axvspan(edge, len(shown) - 0.5, color='#9aa0a6', alpha=0.18, linewidth=0, zorder=0)
    chart.text(len(shown) - 0.5, 0.02, f"Unconfirmed\nlast {profile['unconfirmed']}", ha='right', va='bottom',
               transform=chart.get_xaxis_transform(), fontsize=11, color='#555b60', zorder=7)
    chart.set_ylim(shown['Low'].min() - 3 * pad, shown['High'].max() + 3 * pad)
    chart.legend(fontsize=13, loc='best', framealpha=0.85)

    for left, pivots, name in ((0.05, profile['highs'], 'High'), (0.315, profile['lows'], 'Low')):
        recent = pivots[::-1][:PIVOT_ROWS]
        _swing_table(figure, (left, 0.04, 0.245, 0.32),
                     f"Latest pivot {name.lower()}s ({'resistance' if name == 'High' else 'support'})",
                     ['Date', name, 'vs close'],
                     [[f'{date:%d %b %Y}', f'{price:,.2f}', _level_gap(price, close)] for _, price, date in recent],
                     [0.4, 0.33, 0.27])

    levels = []
    for level, name in ((profile['resistance'], 'resistance'), (profile['support'], 'support')):
        levels.append(f'nearest {name} {level:,.2f} ({_level_gap(level, close)})' if level is not None
                      else f'no confirmed pivot {name} in this window')
    _swing_summary(figure, [
        ('What you see', f"Close (black) with each session's high-low range (grey). A red \u25bc marks a confirmed "
                         f"pivot high, the highest high of {order} sessions on each side; a green \u25b2 a pivot low. "
                         f'Dotted lines carry the latest {PIVOT_ROWS} pivot levels forward; dashed ones are the '
                         f'nearest resistance and support. The grey band is the last {order} sessions, not yet '
                         'confirmable.'),
        ('How to read', f'A pivot is confirmed {order} sessions after it prints and never repaints, so these '
                        'levels carry no look-ahead but lag turns. Rising pivot highs and lows are up-trend '
                        'structure, falling ones down-trend; a close through the nearest level breaks it.'),
        ('Now', f"Close {close:,.2f}: {levels[0]}, {levels[1]}. Latest pivots: {profile['structure']}.")])
    _save_swing_page(figure, pdf_pages)


def pivot_analysis(price_data, ticker, bars, pdf_pages=None):
    """Compute and render the confirmed-pivot page."""
    profile = compute_pivot_levels(price_data, bars)
    print(f"  [pivots] {len(profile['highs'])} highs / {len(profile['lows'])} lows confirmed in "
          f"{len(profile['shown'])} sessions; {profile['structure']}")
    plot_pivots(profile, ticker, pdf_pages=pdf_pages)
    return profile


def _formation_status(close, level, bearish):
    """Confirmed once the close is through a neckline, else what is still needed."""
    side = 'below' if bearish else 'above'
    if (close < level) if bearish else (close > level):
        return f'Confirmed: close {side} the neckline'
    return f'Watching: needs a close {side} {_price_text(level)}'


def compute_formations(price_data, bars, order=PIVOT_ORDER):
    """ATR-normalized head and shoulders, double tops / bottoms and triangles on confirmed pivots.

    Scans the confirmed pivots (confirmed_pivots) inside the shown window with the ATR at the range
    end. Head and shoulders: the last three pivot highs, shoulders within FORMATION_SHOULDER_ATR of
    each other and the head FORMATION_HEAD_ATR above both; the neckline is the lowest low from
    shoulder to shoulder. Double top: the last two pivot highs within FORMATION_TWIN_ATR with a
    pullback of FORMATION_DEPTH_ATR between, the neckline at its low. Inverse head and shoulders and
    double bottoms mirror these on the lows. Triangles regress the last three pivot highs and lows;
    a side moving less than FORMATION_FLAT_ATR per session is flat (drawn at the pivots' mean), and
    every pivot must lie within FORMATION_FIT_ATR of its side, so three highs shaped like a head and
    shoulders are not also read as a flat top. Status compares the latest close with each trigger.
    """
    history = _ohlc_bars(price_data)
    if len(history) < 2 * order + 1:
        raise ValueError(f'only {len(history)} bars; a pivot needs {order} bars on each side')
    shown = history.tail(bars)
    offset, last = len(history) - len(shown), len(history) - 1
    high_idx, low_idx = (positions[positions >= offset] for positions in confirmed_pivots(history, order))
    highs, lows = history['High'].to_numpy(dtype=float), history['Low'].to_numpy(dtype=float)
    close = float(history['Close'].iloc[-1])
    atr, basis = _number(ATR(history, FORMATION_ATR_PERIOD)['ATR'].iloc[-1]), f'ATR({FORMATION_ATR_PERIOD})'
    if not atr > 0:
        atr, basis = abs(close) * FORMATION_ATR_FALLBACK, f'{FORMATION_ATR_FALLBACK:.1%} of the close'
    if not atr > 0:
        raise ValueError('no price range to scale the formation tolerances')

    def point(position, price, label):
        return {'Position': int(position) - offset, 'Price': float(price),
                'Date': history.index[position], 'Label': label}

    def neckline_pattern(pattern, bias, points, level):
        return {'Pattern': pattern, 'Bias': bias, 'Points': points, 'Neckline': level, 'Lines': [],
                'Trigger': f'Neckline {_price_text(level)}',
                'Status': _formation_status(close, level, bias == 'Bearish'),
                'Detail': ' | '.join(f"{p['Label']} {p['Date']:%d %b} {_price_text(p['Price'])}" for p in points)}

    formations = []
    if len(high_idx) >= 3:
        s1, head, s2 = high_idx[-3:]
        if (abs(highs[s1] - highs[s2]) <= FORMATION_SHOULDER_ATR * atr
                and highs[head] - max(highs[s1], highs[s2]) >= FORMATION_HEAD_ATR * atr):
            formations.append(neckline_pattern(
                'Head and Shoulders', 'Bearish',
                [point(s1, highs[s1], 'LS'), point(head, highs[head], 'H'), point(s2, highs[s2], 'RS')],
                float(lows[s1:s2 + 1].min())))
    if len(low_idx) >= 3:
        s1, head, s2 = low_idx[-3:]
        if (abs(lows[s1] - lows[s2]) <= FORMATION_SHOULDER_ATR * atr
                and min(lows[s1], lows[s2]) - lows[head] >= FORMATION_HEAD_ATR * atr):
            formations.append(neckline_pattern(
                'Inverse Head and Shoulders', 'Bullish',
                [point(s1, lows[s1], 'LS'), point(head, lows[head], 'H'), point(s2, lows[s2], 'RS')],
                float(highs[s1:s2 + 1].max())))
    if len(high_idx) >= 2:
        h1, h2 = high_idx[-2:]
        valley = float(lows[h1:h2 + 1].min())
        if (abs(highs[h1] - highs[h2]) <= FORMATION_TWIN_ATR * atr
                and min(highs[h1], highs[h2]) - valley >= FORMATION_DEPTH_ATR * atr):
            formations.append(neckline_pattern(
                'Double Top', 'Bearish', [point(h1, highs[h1], 'P1'), point(h2, highs[h2], 'P2')], valley))
    if len(low_idx) >= 2:
        l1, l2 = low_idx[-2:]
        peak = float(highs[l1:l2 + 1].max())
        if (abs(lows[l1] - lows[l2]) <= FORMATION_TWIN_ATR * atr
                and peak - max(lows[l1], lows[l2]) >= FORMATION_DEPTH_ATR * atr):
            formations.append(neckline_pattern(
                'Double Bottom', 'Bullish', [point(l1, lows[l1], 'T1'), point(l2, lows[l2], 'T2')], peak))
    if len(high_idx) >= 3 and len(low_idx) >= 3:
        upper_x, lower_x = high_idx[-3:], low_idx[-3:]
        upper, lower = linregress(upper_x, highs[upper_x]), linregress(lower_x, lows[lower_x])
        upper_slope, lower_slope = upper.slope / atr, lower.slope / atr
        flat = FORMATION_FLAT_ATR
        pattern, bias = (('Ascending Triangle', 'Bullish') if abs(upper_slope) <= flat and lower_slope > flat
                         else ('Descending Triangle', 'Bearish') if upper_slope < -flat and abs(lower_slope) <= flat
                         else ('Symmetrical Triangle', 'Consolidation') if upper_slope < -flat and lower_slope > flat
                         else (None, None))
        if pattern:
            span = np.array([min(upper_x[0], lower_x[0]), last], dtype=float)

            def side(fit, x, values, flat_side):
                """The side at its pivots and over [start, last]: flat at their mean, else the regression."""
                if flat_side:
                    return np.full(len(x), values.mean()), np.full(2, values.mean())
                return fit.intercept + fit.slope * x, fit.intercept + fit.slope * span

            upper_fit, top = side(upper, upper_x, highs[upper_x], pattern == 'Ascending Triangle')
            lower_fit, bottom = side(lower, lower_x, lows[lower_x], pattern == 'Descending Triangle')
            if max(np.abs(highs[upper_x] - upper_fit).max(),
                   np.abs(lows[lower_x] - lower_fit).max()) > FORMATION_FIT_ATR * atr:
                pattern = None
        if pattern:
            if top[1] <= bottom[1]:
                status = 'Apex passed: the sides have crossed'
            elif close > top[1]:
                status = f'Broken out: close above {_price_text(top[1])}'
            elif close < bottom[1]:
                status = f'Broken down: close below {_price_text(bottom[1])}'
            else:
                status = f'Inside: watch {_price_text(bottom[1])} / {_price_text(top[1])}'
            formations.append({
                'Pattern': pattern, 'Bias': bias, 'Status': status, 'Neckline': None,
                'Points': [point(p, highs[p], '') for p in upper_x] + [point(p, lows[p], '') for p in lower_x],
                'Lines': [((span[0] - offset, line[0]), (span[1] - offset, line[1])) for line in (top, bottom)],
                'Trigger': f'{_price_text(bottom[1])} / {_price_text(top[1])}',
                'Detail': f'Sides {upper_slope:+.3f} / {lower_slope:+.3f} ATR per session'})
    return {'shown': shown, 'order': order, 'atr': atr, 'basis': basis, 'close': close, 'formations': formations,
            'highs': _window_pivots(history, high_idx, 'High', offset),
            'lows': _window_pivots(history, low_idx, 'Low', offset)}


def _formation_colour(formation):
    """Status cell colour: confirmed or broken in a direction, otherwise still forming."""
    status = formation['Status']
    if status.startswith('Confirmed'):
        return SWING_CELL_COLOURS[formation['Bias']]
    if status.startswith('Broken'):
        return SWING_CELL_COLOURS['Bullish' if 'above' in status else 'Bearish']
    return AUDIT_COLOURS['Hold'] if status.startswith(('Watching', 'Inside')) else '#e7e7e7'


def plot_formations(profile, ticker, pdf_pages=None):
    """Candles with each detected formation drawn on its pivots, the formation table and notes."""
    shown, close = profile['shown'], profile['close']
    figure, chart = _swing_page(
        ticker, 'Geometric Formations', shown,
        f"ATR-normalized scan of confirmed pivots (order {profile['order']})   |   {profile['basis']} = "
        f"{profile['atr']:,.2f}   |   status compares the latest close with each trigger")
    _draw_price_bars(chart, shown)
    pad = _price_pad(shown)
    _mark_pivots(chart, profile, pad, size=80, alpha=0.4, labels=False)
    colours = {'Bullish': SWING_BULL_COLOUR, 'Bearish': SWING_BEAR_COLOUR, 'Consolidation': SWING_NEUTRAL_COLOUR}
    for formation in profile['formations']:
        colour, label = colours[formation['Bias']], f"{formation['Pattern']} ({formation['Trigger']})"
        if formation['Neckline'] is None:
            for number, ((x0, y0), (x1, y1)) in enumerate(formation['Lines']):
                chart.plot([x0, x1], [y0, y1], color=colour, linewidth=2.6, linestyle='--', zorder=5,
                           label=label if number == 0 else '_nolegend_')
            continue
        points = formation['Points']
        on_highs = formation['Pattern'] in ('Head and Shoulders', 'Double Top')
        chart.plot([p['Position'] for p in points], [p['Price'] for p in points], color=colour, linewidth=2.6,
                   marker='o', markersize=11, zorder=6, label=label)
        for p in points:
            chart.annotate(p['Label'], (p['Position'], p['Price']), xytext=(0, 14 if on_highs else -14),
                           textcoords='offset points', ha='center', va='bottom' if on_highs else 'top',
                           fontsize=14, fontweight='bold', color=colour, zorder=7)
        chart.hlines(formation['Neckline'], points[0]['Position'], len(shown) - 1, colors=colour,
                     linestyles='--', linewidth=2.2, zorder=5)
    chart.set_ylim(shown['Low'].min() - 4 * pad, shown['High'].max() + 4 * pad)
    if profile['formations']:
        chart.legend(fontsize=13, loc='best', framealpha=0.85)
    else:
        chart.text(0.5, 0.96, 'No active multi-swing pattern', transform=chart.transAxes, ha='center', va='top',
                   fontsize=18, color='#555b60', bbox=MAX_PAIN_LABEL_BOX, zorder=7)

    formations = profile['formations']
    _swing_table(
        figure, (0.05, 0.04, 0.50, 0.32), 'Detected formations', ['Pattern', 'Bias', 'Swing points', 'Trigger', 'Status'],
        [[f['Pattern'], f['Bias'], f['Detail'], f['Trigger'], f['Status']] for f in formations]
        or [['None', 'Neutral', 'No active multi-swing pattern', '', '']],
        [0.18, 0.09, 0.38, 0.13, 0.22],
        [[SWING_CELL, SWING_CELL_COLOURS[f['Bias']], SWING_CELL, SWING_CELL, _formation_colour(f)]
         for f in formations] or None, fontsize=12)

    if formations:
        now = (f"{len(formations)} formation{'s' if len(formations) > 1 else ''}: "
               + '; '.join(f"{f['Pattern']} ({f['Bias'].lower()}), {f['Status'][0].lower()}{f['Status'][1:]}"
                           for f in formations) + f'. Close {close:,.2f}.')
        if {f['Bias'] for f in formations} >= {'Bullish', 'Bearish'}:
            now += ' Bullish and bearish formations overlap: let the first trigger to break decide.'
    else:
        now = f'No active multi-swing pattern: the latest pivots meet none of the ATR rules. Close {close:,.2f}.'
    _swing_summary(figure, [
        ('What you see', 'Candles with the confirmed pivots (faint markers) the scanner uses. Each detected '
                         'formation is drawn on its pivots: head and shoulders (LS, H, RS) and double tops / '
                         'bottoms with a dashed neckline, triangles with dashed sides through the last three '
                         'pivot highs and lows.'),
        ('How to read', f"Tolerances scale with volatility, {profile['basis']} {profile['atr']:,.2f}: shoulders "
                        f'within {FORMATION_SHOULDER_ATR:g} ATR and the head {FORMATION_HEAD_ATR:g} ATR beyond '
                        f'them; twins within {FORMATION_TWIN_ATR:g} ATR with a {FORMATION_DEPTH_ATR:g} ATR '
                        f'pullback between; triangle sides moving under {FORMATION_FLAT_ATR:g} ATR a session '
                        f'are flat, with every pivot within {FORMATION_FIT_ATR:g} ATR of its side. A formation '
                        'is a hypothesis until a close breaks its trigger.'),
        ('Now', now)])
    _save_swing_page(figure, pdf_pages)


def formation_analysis(price_data, ticker, bars, pdf_pages=None):
    """Compute and render the geometric-formation page."""
    profile = compute_formations(price_data, bars)
    found = ', '.join(f"{f['Pattern']} ({f['Status'].split(':')[0].lower()})" for f in profile['formations'])
    print(f"  [formations] {profile['basis']} {profile['atr']:,.2f}; {found or 'no active multi-swing pattern'}")
    plot_formations(profile, ticker, pdf_pages=pdf_pages)
    return profile


# ---------------------------------------------------------------------------
# Main analysis orchestrator
# ---------------------------------------------------------------------------

def FnOAnalysis(scrip_list=None, single_scrip=None, pdf_path=None,
                compare_with=None, days=None, estimator=DEFAULT_ESTIMATOR,
                trend_bars=TREND_BARS, trend_distance=TREND_DISTANCE,
                trend_prominence=None,
                trend_prominence_pct=TREND_PROMINENCE_PCT,
                comparison_frequency='auto', comparison_aggregation='auto',
                option_dates=option_overlay.OPTION_HISTORY_DATES,
                option_min_contracts=option_overlay.OPTION_MIN_CONTRACTS,
                option_outliers=option_overlay.OPTION_OUTLIER_COUNT,
                option_rate=RiskFreeRate, option_iv_unit='percent'):
    """Run technical analysis for each symbol in the list.

    Sections are driven by REPORT_SECTIONS, so any of them can be commented out.

    Args:
        scrip_list:           List of symbols to analyse (default: NSEFnOList)
        single_scrip:         If set, analyse only this one symbol
        pdf_path:             If set, save all charts to this PDF file, with a
                              _YYYYMMDD_HHMMSS stamp added before .pdf
        compare_with:         If set, append a statistical comparison of the
                              analysed symbol against this second series
        days:                 Report window (legacy name): a ReportWindow, text such as
                              250d, 350d-25d, Jan2026 or Jan2026-Mar2026, or a count of
                              trailing observations. Limits the single-symbol pages, or
                              only the comparison when compare_with is set
        estimator:            Volatility estimator name (see ESTIMATORS)
        trend_bars:           Trailing bars used by the trendline page
        trend_distance:       Minimum bars between two trendline pivots
        trend_prominence:     Absolute pivot prominence; None auto-scales
        trend_prominence_pct: Fraction of the window range used when
                              auto-scaling the prominence
        comparison_frequency: auto chooses the slower native cadence
        comparison_aggregation: auto, mean, last or sum for downsampled series
        option_dates:         Recent underlying trading dates for option IV overlays
        option_min_contracts: Minimum traded contracts for eligible option observations
        option_outliers:      Additional qualifying MAD outliers per side/expiry/date
        option_rate:          Annual decimal rate for Black-76 IV estimates
        option_iv_unit:       Unit of source-reported IV: percent or decimal

    Returns:
        The saved PDF path (timestamped), or None for interactive charts.
    """
    window = as_report_window(days)
    analysis_window = window if not compare_with else None

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
        pdf_path = str(timestamped_path(pdf_path))
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

        price_data = OHLCdf.set_index('Date')
        if analysis_window is not None:
            price_data = analysis_window.select(price_data)
            if price_data.empty:
                print(f"  [skip] No {Scrip} observations in window {analysis_window.label}")
                continue
            scope = f"{len(price_data):,} observations"
            if analysis_window.size and len(price_data) < analysis_window.size:
                scope += f" - fewer than the {analysis_window.size:,} requested"
            print(f"  Window {analysis_window.label}: {scope} "
                  f"({price_data.index[0]:%Y-%m-%d} to {price_data.index[-1]:%Y-%m-%d})")
            # Nothing after the window's last bar reaches the indicators, audit or Renko.
            Indicatordf = Indicatordf[Indicatordf['Date'] <= price_data.index[-1]].reset_index(drop=True)

        # ── Plot ──────────────────────────────────────────────────────
        if 'technical' in REPORT_SECTIONS:
            display_bars = (technical_window_bars(Indicatordf['Date'])
                            if analysis_window is None else len(price_data))
            plot_chart(Indicatordf, display_bars, Scrip, 0, pdf_pages=pdf_pages)

        # ── Swing-trading pages, on all history up to the range end ───
        swing_pages = [(name, page) for name, page in (
            ('candlesticks', candlestick_analysis), ('swing_structure', swing_structure_analysis),
            ('pivots', pivot_analysis), ('formations', formation_analysis)) if name in REPORT_SECTIONS]
        if swing_pages:
            swing_history = OHLCdf.set_index('Date')
            swing_history = swing_history[swing_history.index <= price_data.index[-1]]
            swing_bars = (len(price_data) if analysis_window is not None else technical_window_bars(
                swing_history.index, years=0, months=SWING_WINDOW_MONTHS))
            for name, page in swing_pages:
                try:
                    page(swing_history, Scrip, swing_bars, pdf_pages=pdf_pages)
                except (ValueError, KeyError) as e:
                    print(f"  [{name.replace('_', ' ')} skipped] {e}")

        # ── Max pain and put-call ratio of the range's latest options ─
        if 'max_pain' in REPORT_SECTIONS:
            try:
                max_pain_analysis(Scrip, price_data.index[-1], start=price_data.index[0], pdf_pages=pdf_pages)
            except (ValueError, KeyError) as e:
                print(f"  [max pain skipped] {e}")

        # ── Support / resistance trendlines ───────────────────────────
        if 'trendlines' in REPORT_SECTIONS:
            try:
                trendline_analysis(price_data, Scrip,
                                   bars=trend_bars, distance=trend_distance,
                                   prominence=trend_prominence,
                                   prominence_pct=trend_prominence_pct,
                                   pdf_pages=pdf_pages)
            except (ValueError, KeyError) as e:
                print(f"  [trendlines skipped] {e}")

        # ── Volatility profile ────────────────────────────────────────
        if 'volatility' in REPORT_SECTIONS:
            try:
                volatility_analysis(price_data, Scrip,
                                    estimator=estimator, pdf_pages=pdf_pages,
                                    option_dates=option_dates, option_min_contracts=option_min_contracts,
                                    option_outliers=option_outliers, option_rate=option_rate,
                                    option_iv_unit=option_iv_unit)
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
    return pdf_path


# ---------------------------------------------------------------------------
# COMP — pairwise statistical comparison across any two data series
# ---------------------------------------------------------------------------

COMP_MAX_LAG = 10        # Lags scanned by Granger causality and cross-correlation
COMP_MIN_OBS = 60        # Below this the estimators are not worth reporting
DTW_MAX_POINTS = 1000    # Series are resampled to this length before DTW
DTW_BAND_FRACTION = 0.1  # Sakoe-Chiba band as a fraction of series length
RATIO_OPERATOR = '__'    # NUM__DEN, e.g. US02Y__US10Y

# Plain-English definitions shown beside each measure on the comparison slide.
COMP_DEFINITIONS = {
    'Cointegration': "Two series that wander but are tied together: a weighted spread "
                     "between them keeps returning to its mean.",
    'Granger': "Whether past values of one series improve forecasts of the other "
               "beyond that series' own past.",
    'Cross-Correlation': "Correlation (-1 to +1) of the two series' changes, with one "
                         "shifted k periods to see which moves first.",
    'Dynamic Time Warping': "Distance between the two standardized paths after stretching "
                            "time to align them; 0 means identical shape.",
    'Mutual Information': "How much knowing one series' change reduces uncertainty about "
                          "the other's, in bits; 0 means independent.",
}

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
                            frequency='auto', aggregation='auto', window=None):
    """Align at the slower cadence, without upsampling or filling missing periods.

    A ReportWindow's end applies before the latest contiguous run is chosen, so a
    window that ends earlier is not lost to a later gap; its start is left to the caller.
    """
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
    if window is not None:
        ends = (aligned.index.to_timestamp(how='end').normalize()
                if isinstance(aligned.index, pd.PeriodIndex) else aligned.index)
        aligned = aligned[window.through_end(ends)]
    if aligned.empty:
        scope = f' in window {window.label}' if window is not None else ''
        raise ValueError(f'No overlapping closed {target} periods between {label_a} and {label_b}{scope}.')
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
            if directory == DERIVATIVES_PROCESSED:
                # The loader maps UDiFF instrument codes, so futures stay detectable.
                return load_derivatives(symbol), source
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

    `days` (legacy name) is the report window: a ReportWindow, text such as 250d,
    350d-25d or Jan2026, or a count of the latest aligned observations, never
    calendar days. Short samples retain descriptive charts but not significance tests.
    """
    window = as_report_window(days)
    if window is not None and window.size is not None and window.size < 3:
        raise ValueError('The comparison window needs at least 3 aligned observations.')
    if label_a == label_b:
        raise ValueError('Choose two different series for a comparison.')
    if max_lag < 1:
        raise ValueError('max_lag must be positive.')
    aligned, alignment = align_comparison_series(
        series_a, series_b, label_a, label_b, frequency=frequency, aggregation=aggregation,
        window=window)
    total_overlap = len(aligned)

    if window is not None:
        aligned = window.from_start(aligned)

    if len(aligned) < 3:
        scope = f' in window {window.label}' if window is not None else ''
        raise ValueError(
            f"Only {len(aligned)} overlapping observations between {label_a} and "
            f"{label_b}{scope} - need at least 3 for descriptive charts.")

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
        'window': window,
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
    rows.append(["Cointegration", COMP_DEFINITIONS['Cointegration'], value, reading,
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
        rows.append([name, COMP_DEFINITIONS['Granger'], value, reading,
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
    rows.append(["Cross-Correlation", COMP_DEFINITIONS['Cross-Correlation'], value, reading,
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
    rows.append(["Dynamic Time Warping", COMP_DEFINITIONS['Dynamic Time Warping'], value, reading,
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
    rows.append(["Mutual Information", COMP_DEFINITIONS['Mutual Information'], value, reading,
                 "Total shared information, linear and non-linear; used for feature selection."])

    return pd.DataFrame(
        rows, columns=["Measure", "Definition", "Value", "Reading", "What it tells you"])


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
    window = results.get('window')
    if window is None:
        return ""
    return f"   |   {window.label}: {len(results['aligned']):,} {results.get('lag_unit', 'observations')}"


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
        cell_colours.append(['#f2f2f2', '#f2f2f2', tint, tint, '#f2f2f2'])

    display_table = table.copy()
    for column, width in zip(display_table.columns, [22, 58, 22, 40, 56]):
        display_table[column] = display_table[column].map(
            lambda value: '\n'.join(textwrap.fill(line, width) for line in str(value).splitlines()))
    tbl = ax_table.table(
        cellText=display_table.values,
        colLabels=table.columns,
        cellColours=cell_colours,
        colColours=['#4472c4'] * len(table.columns),
        cellLoc='left',
        colWidths=[0.13, 0.28, 0.12, 0.20, 0.27],
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
    window = results['window']
    if window is None:
        scope = f"{len(aligned):,} aligned observations in the latest contiguous overlap"
    else:
        scope = f"window {window.label}: {len(aligned):,} of {overlap:,} aligned observations"
        if window.size and len(aligned) < window.size:
            scope += f" - fewer than the {window.size:,} requested"
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
        print(table.drop(columns='Definition').to_string(index=False))
    print()

    owns_pdf = False
    if pdf_pages is None and pdf_path:
        from pathlib import Path
        pdf_path = str(timestamped_path(pdf_path))
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

def build_volatility_option_overlay(price_data, ticker, estimator,
                                     date_count=option_overlay.OPTION_HISTORY_DATES,
                                     min_contracts=option_overlay.OPTION_MIN_CONTRACTS,
                                     outlier_count=option_overlay.OPTION_OUTLIER_COUNT,
                                     rate=RiskFreeRate, reported_iv_unit='percent'):
    """Load all expiries for one underlying and build an as-of IV overlay."""
    if date_count < 1 or min_contracts < 1 or not 0 <= outlier_count <= 2:
        raise ValueError('Option dates and minimum contracts must be positive; outliers must be 0, 1 or 2')
    if estimator in MOMENT_ESTIMATORS:
        print(f'  [options] IV overlays do not apply to the {estimator} moment estimator.')
        return None
    if estimator in RANGE_ESTIMATORS and not _has_intraday_range(price_data):
        print(f'  [options] {estimator} needs actual underlying high/low ranges for an IV comparison.')
        return None
    history = price_data.copy()
    history.index = pd.DatetimeIndex(pd.to_datetime(history.index, errors='coerce'))
    if history.index.tz is not None:
        history.index = history.index.tz_localize(None)
    history.index = history.index.normalize()
    history = history[history.index.notna() & (history.index <= pd.Timestamp(datetime.date.today()))].sort_index()
    if history.empty or history.index.duplicated().any():
        print('  [options] A unique daily underlying price history is required.')
        return None
    frequency, _ = _comp_native_frequency(history['Close'])
    if frequency != 'daily':
        print('  [options] Option IV overlays require daily underlying prices, not monthly/quarterly macro observations.')
        return None
    dates = history.index[-date_count:]
    try:
        derivatives = load_derivatives(ticker, start=f'{dates[0]:%Y-%m-%d}', end=f'{dates[-1]:%Y-%m-%d}')
    except FileNotFoundError:
        print(f'  [options] No stored derivatives for {ticker}; historical-volatility charts remain unchanged.')
        return None
    if derivatives.empty:
        print(f'  [options] No option observations for {ticker} in the selected date window.')
        return None
    chain, diagnostics = option_overlay.prepare_option_iv(
        derivatives, ticker, dates, rate=rate, reported_iv_unit=reported_iv_unit,
        min_contracts=min_contracts)
    points = option_overlay.select_option_points(chain, outlier_count=outlier_count,
                                                 min_contracts=min_contracts)
    if points.empty:
        print(f"  [options] No valid IV points: {diagnostics['eligible_contracts']} eligible contracts, "
              f"{diagnostics['missing_forward']} without a same-expiry future or parity forward, "
              f"{diagnostics['invalid_premium']} invalid premiums, "
              f"{diagnostics['solver_failures']} solver failures.")
        if diagnostics['solver_unavailable']:
            print('  [options] Install vollib to estimate missing IV; reported IV can be used directly.')
        return None
    # Next monthly expiries, plus the next expiries of any kind when weeklies are listed
    expiries = option_overlay.select_report_expiries(points)
    points = points[points['Expiry'].isin(expiries)].reset_index(drop=True)
    if points.empty:
        print('  [options] No upcoming expiries with valid IV points.')
        return None
    points = option_overlay.attach_realized_benchmarks(
        points, history, lambda available, tenor: get_volatility_estimator(available, estimator, tenor))
    kinds = points.drop_duplicates('Expiry')['Expiry type'].value_counts()
    print(f"  [options] {len(points)} selected points across {len(expiries)} upcoming expiries "
          f"({kinds.get('Monthly', 0)} monthly, {kinds.get('Weekly', 0)} weekly) and "
          f"{points['Date'].nunique()} dates; {diagnostics['reported_iv']} reported IV, "
          f"{diagnostics['estimated_iv']} Black-76 estimates ({diagnostics['parity_iv']} via put-call "
          f"parity). Rate {rate:.2%}, ACT/365.")
    return {'points': points, 'diagnostics': diagnostics, 'as_of': dates[-1],
            'estimator': estimator, 'top_count': option_overlay.OPTION_TOP_COUNT,
            'outlier_count': outlier_count, 'min_contracts': min_contracts, 'rate': rate,
            'reported_iv_unit': reported_iv_unit, 'expiries': expiries}


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

    cone = {'windows': [], 'max': [], 'top_q': [], 'median': [], 'mean': [],
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
        cone['mean'].append(series.mean())
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


def _percentile_rank(series, value):
    """Share of readings at or below `value`, in percent."""
    series = pd.Series(series).dropna()
    return float((series <= value).mean() * 100) if len(series) else np.nan


def _ordinal(number):
    """39 -> '39th', 41 -> '41st', 12 -> '12th'."""
    number = int(round(number))
    suffix = 'th' if 10 <= number % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(number % 10, 'th')
    return f'{number}{suffix}'


def _volatility_reading(percentile):
    """Plain-English band for the latest reading's percentile rank."""
    if percentile >= 80:
        return 'Elevated - rich vs its own history'
    if percentile <= 20:
        return 'Depressed - cheap vs its own history'
    return 'Middle of its historical range'


def _cone_option_points(options, outliers_only=True):
    """Latest-date monthly IV; show only Smile MAD outliers by default.

    Use outliers_only=False to keep all monthly tenors for realized benchmarks.
    """
    if options is None:
        return pd.DataFrame()
    points = options['points']
    latest = points[points['Date'].eq(options['as_of'])]
    if 'Expiry type' in latest.columns:
        latest = latest[latest['Expiry type'].eq('Monthly')]
    if outliers_only:
        plotted = latest[latest['Is outlier']]
        # To restore the other nearby/top-volume strikes on the cone (and its
        # guide), uncomment the next line. Expiry-page selections are unchanged.
        # plotted = latest
        return plotted
    return latest


def plot_volatility(profile, ticker, pdf_pages=None):
    """Render the volatility page: cone, box, rolling series and distribution."""
    cone = profile['cone']
    estimator = profile['estimator']
    rolling = profile['rolling']
    label = _volatility_formatter(profile)
    lower, upper = profile['quantiles']
    options = profile.get('option_overlay')

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
        ax_cone.plot(cone['windows'], cone['mean'], color='#555555', linestyle='--',
                 linewidth=1.8, label='Historical mean')
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
        if options is not None:
            latest = _cone_option_points(options)
            if not latest.empty:
                option_overlay.plot_option_markers(ax_cone, latest, 'Tenor sessions', fontsize=9)
                ax_cone.set_xlabel('Lookback / expiry tenor (weekday sessions)', fontsize=13)
                ax_cone.set_title(f"Volatility Cone + Option IV | {options['as_of']:%d %b %Y}",
                                  fontsize=18, fontweight='bold', pad=8)

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
        percentile = _percentile_rank(rolling, latest)
        reading = _volatility_reading(percentile)
        rows = [
            ['Estimator', estimator],
            [f'Latest ({profile["rolling_window"]}d)', label(latest)],
            ['Percentile rank', f"{_ordinal(percentile)} - {reading}"],
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

    notes = []
    if options is not None:
        notes.append("Option IV: CE green, PE red; outlier labels show strike, expiry and quote-date "
                     "option Close (N/A if missing). "
                     f"Black-76 estimates use {options['rate']:.2%} ACT/365; realized volatility uses 252/year. "
                     'The cone defaults to monthly Smile MAD outliers.')
    if 'volatility_guide' in REPORT_SECTIONS:
        notes.append('Next page: how to read each graph.')
    if options is not None:
        notes.append('Per-expiry option IV pages follow.')
    if notes:
        figure.text(0.05, 0.017, ' '.join(notes), fontsize=11, color='#555555')
    if pdf_pages:
        pdf_pages.savefig(figure)
        plt.close(figure)
    else:
        plt.show()


def _volatility_guide_blocks(profile, ticker):
    """(title, [(label, text), ...]) for each graph drawn on the volatility page."""
    has = lambda name: name in VOLATILITY_PANELS
    cone, rolling = profile['cone'], profile['rolling']
    label = _volatility_formatter(profile)
    estimator, moment = profile['estimator'], profile['is_moment']
    noun = estimator if moment else 'volatility'
    lower, upper = (round(q * 100) for q in profile['quantiles'])
    windows, window = cone['windows'], profile['rolling_window']
    blocks = []

    if has('cone'):
        focus = window if window in windows else windows[-1]
        i = windows.index(focus)
        today = cone['realized'][i]
        if today > cone['top_q'][i]:
            place = f'above the {upper}th percentile, so high for that window'
        elif today < cone['bottom_q'][i]:
            place = f'below the {lower}th percentile, so low for that window'
        else:
            place = f'between the {lower}th and {upper}th percentiles, so normal'
        example = (f"{focus}-day: min {label(cone['min'][i])}, median {label(cone['median'][i])}, "
                   f"max {label(cone['max'][i])}; today {label(today)} sits {place}.")
        if not moment and len(windows) > 1:
            short, long = cone['realized'][0], cone['realized'][-1]
            example += (f" {windows[0]}-day {label(short)} vs {windows[-1]}-day {label(long)}: recent "
                        f"moves are {'larger' if short > long else 'smaller'} than the longer-run pace.")
        blocks.append(('Volatility Cone', [
            ('Shows', f'The range of {estimator} {noun} for each look-back window ({windows[0]} to '
                      f'{windows[-1]} days): max, {upper}th percentile, median, mean, {lower}th '
                      'percentile and min over the whole history. Red stars are today.'),
            ('Read', 'Short windows swing far more than long ones, so the cone narrows to the right. '
                     'A star near the top of the cone is high for that window, near the bottom low.'),
            ('Here', example)]))

    if has('box'):
        ranks = ', '.join(f'{w}d {_ordinal(_percentile_rank(series, series.iloc[-1]))}'
                          for w, series in zip(windows, cone['series']))
        blocks.append(('Distribution by window', [
            ('Shows', "Each window's full history as a box plot: the box spans the 25th to 75th "
                      "percentile, the notch marks the median, whiskers reach 1.5 box-heights and '+' "
                      'marks extreme readings. Red stars are today.'),
            ('Read', f"Many '+' marks above a box mean {noun} arrives in bursts. A star outside its "
                     'box is unusual for that window.'),
            ('Here', f"Today's percentile rank by window: {ranks}.")]))

    if has('rolling') and not rolling.empty:
        latest = rolling.iloc[-1]
        prior = rolling.iloc[-1 - window] if len(rolling) > window else rolling.iloc[0]
        peak_at = rolling.idxmax()
        when = f' in {peak_at:%b %Y}' if isinstance(peak_at, (pd.Timestamp, datetime.date)) else ''
        direction = 'up' if latest > prior else 'down' if latest < prior else 'unchanged'
        blocks.append((f'Rolling {estimator} ({window}-day window)', [
            ('Shows', f'{window}-day {noun} through time (red), with the {upper}th percentile, median '
                      f'and {lower}th percentile of its last {window} readings (blue, black, green).'),
            ('Read', f'Red above blue: {noun} is rising faster than its recent range; red below green: '
                     'it is calming. Tall spikes mark stress events.'),
            ('Here', f'Peak {label(rolling.max())}{when}; today {label(latest)}, {direction} from '
                     f'{label(prior)} {window} sessions ago.')]))

    if has('histogram') and not rolling.empty:
        low, high = rolling.quantile([0.10, 0.90])
        spread = rolling.std()
        tail = float((rolling > rolling.mean() + 2 * spread).mean() * 100) if spread > 0 else 0.0
        blocks.append(('Distribution of estimator values', [
            ('Shows', f'How often each {window}-day level has occurred (bars), a normal curve fitted '
                      "to them (dashed green) and today's level (red line)."),
            ('Read', 'Bars stretching right of the curve mean spikes come more often than a normal '
                     'model predicts, so plan for them.'),
            ('Here', f'80% of readings lie between {label(low)} and {label(high)}; {tail:.1f}% sit more '
                     'than 2 SD above the mean, against 2.3% for a normal curve. Today '
                     f'{label(rolling.iloc[-1])}, median {label(rolling.median())}.')]))

    if has('summary') and not rolling.empty:
        percentile = _percentile_rank(rolling, rolling.iloc[-1])
        reading = _volatility_reading(percentile).lower()
        if moment:
            reading = reading.split(' - ')[0]  # rich/cheap describes option pricing, not moments
        blocks.append(('Summary', [
            ('Shows', "Today's value, its percentile rank in its own history, the median, the "
                      'extremes and the number of readings.'),
            ('Read', 'A rank of 80th or higher is elevated and 20th or lower depressed'
                     + ('; options then tend to look rich or cheap against history.' if not moment
                        else '; anything in between is normal.')),
            ('Here', f'{label(rolling.iloc[-1])} at the {_ordinal(percentile)} percentile of '
                     f'{len(rolling):,} readings: {reading}.')]))

    cone_points = _cone_option_points(profile.get('option_overlay'))
    if has('cone') and not cone_points.empty:
        nearest = cone_points['Expiry'].min()
        near = cone_points[cone_points['Expiry'].eq(nearest)]
        sides = {side: near.loc[near['Option type'].eq(side), 'IV'].dropna().median() for side in ('CE', 'PE')}
        realized = near['RV mean'].dropna().median()
        benchmark = (f'{label(realized)} realized mean' if np.isfinite(realized)
                     else 'no realized benchmark yet')
        blocks.append(('Option IV on the cone', [
            ('Shows', "Today's plotted monthly option IV, calls green and puts red, at remaining "
                      'weekday tenor. Only Smile MAD outliers by default; labels include quote-date option Close.'),
            ('Read', 'IV above the realized lines at the same tenor means options price more movement '
                     'than history has delivered; below them, less.'),
            ('Here', f"{nearest:%d %b} expiry, {int(near['Tenor sessions'].iloc[0])} sessions: median "
                     + ', '.join(f'{side} {label(value)}' for side, value in sides.items()
                                 if np.isfinite(value))
                     + f' vs {benchmark}.')]))

    if not moment and not rolling.empty:
        percentile = _percentile_rank(rolling, rolling.iloc[-1])
        blocks.append(('Putting it together', [
            ('Now', f"{ticker}'s {window}-day volatility is {label(rolling.iloc[-1])}, the "
                    f'{_ordinal(percentile)} percentile: {_volatility_reading(percentile).lower()}.'),
            ('Why', f'Volatility tends to drift back toward its median ({label(rolling.median())}), '
                    'so extreme readings rarely last.'),
            ('Use', 'Before calling option premiums rich or cheap, compare their IV with the cone '
                    'at the same tenor.')]))
    return blocks


def plot_volatility_guide(profile, ticker, pdf_pages=None):
    """Page after the volatility profile: what each graph shows, using this report's numbers."""
    blocks = _volatility_guide_blocks(profile, ticker)
    if not blocks:
        return 0
    figure = plt.figure(figsize=(30, 17))
    figure.suptitle(f"{ticker}   Volatility Profile - how to read it   |   "
                    f"{profile['estimator']} estimator", fontsize=32, fontweight='bold', y=0.975)
    figure.text(0.05, 0.925, "One block per graph on the previous page: what it shows, how to read "
                "it, and this report's numbers as the example.", fontsize=17, color='#444444')
    rows = math.ceil(len(blocks) / 2)
    size, wrap = (20, 82) if rows <= 3 else (17, 96)  # A fourth row needs smaller text
    top = 0.88
    row_height = (top - 0.02) / rows
    for index, (title, items) in enumerate(blocks):
        left = 0.05 + (index % 2) * 0.475
        y = top - (index // 2) * row_height
        figure.text(left, y, title, fontsize=size + 6, fontweight='bold', color='#1f3864', va='top')
        y -= 0.042
        for name, text in items:
            figure.text(left, y, name, fontsize=size, fontweight='bold', color='#555555', va='top')
            body = figure.text(left + 0.055, y, textwrap.fill(text, wrap), fontsize=size,
                               va='top', linespacing=1.3)
            y -= body.get_window_extent().height / figure.bbox.height + 0.01
    if pdf_pages:
        pdf_pages.savefig(figure)
        plt.close(figure)
    else:
        plt.show()
    return len(blocks)


def volatility_analysis(price_data, ticker, estimator=DEFAULT_ESTIMATOR,
                        pdf_pages=None, option_dates=option_overlay.OPTION_HISTORY_DATES,
                        option_min_contracts=option_overlay.OPTION_MIN_CONTRACTS,
                        option_outliers=option_overlay.OPTION_OUTLIER_COUNT,
                        option_rate=RiskFreeRate, option_iv_unit='percent'):
    """Compute and render the volatility page for one symbol."""
    if estimator in RANGE_ESTIMATORS and not _has_intraday_range(price_data):
        print(f"  [volatility] {estimator} needs an intraday high/low range, but "
              f"{ticker} has flat bars - it will read zero.")
        print(f"  [volatility] Use Raw, HodgesTompkins or YangZhang for this series.")

    options = None
    if 'option_overlay' in REPORT_SECTIONS:
        try:
            options = build_volatility_option_overlay(
                price_data, ticker, estimator, date_count=option_dates,
                min_contracts=option_min_contracts, outlier_count=option_outliers,
                rate=option_rate, reported_iv_unit=option_iv_unit)
        except Exception as error:
            print(f'  [options unavailable] {type(error).__name__}: {error}')
    windows = list(VOLATILITY_WINDOWS)
    if options is not None:
        latest = _cone_option_points(options, outliers_only=False)
        windows = sorted(set(windows) | set(latest.loc[latest['RV count'] > 0, 'Tenor sessions'].astype(int)))
    profile = compute_volatility_profile(price_data, estimator=estimator, windows=windows)
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

    profile['option_overlay'] = options
    plot_volatility(profile, ticker, pdf_pages=pdf_pages)
    if 'volatility_guide' in REPORT_SECTIONS:
        plot_volatility_guide(profile, ticker, pdf_pages=pdf_pages)
    if options is not None:
        option_overlay.plot_option_history(options, ticker, pdf_pages=pdf_pages)
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
# List - the latest rows of any Parquet file
# ---------------------------------------------------------------------------

LIST_PDF_CHARACTERS = 180  # Monospace characters per PDF line
LIST_PDF_LINES = 52        # Table lines per PDF page
LIST_MAX_COLWIDTH = 60     # Longer cell values are cut short with ...


def _listing_text(frame, width):
    """Every column of `frame`, wrapped into blocks at most `width` characters wide."""
    return frame.to_string(line_width=width, max_colwidth=LIST_MAX_COLWIDTH)


def _listing_summary(source, latest, total, order, window=None):
    """Header lines shared by the console and PDF listings."""
    lines = [f'File: {source}']
    if latest.empty:
        scope = f' | No rows in window {window.label}' if window is not None else ''
        return lines + [f'Rows: {total:,} | Columns: {len(latest.columns)}{scope}']
    dates = None
    if order is None:
        scope = f'last {len(latest):,} in file order (no Date column)'
    else:
        dates = _naive_dates(latest[order])
        days = dates.nunique()
        scope = (f'latest {len(latest):,} by {order}' if window is None else
                 f"{len(latest):,} rows on {days:,} trading day{'' if days == 1 else 's'} "
                 f"in window {window.label}, by {order}")
        if dates.notna().any():
            scope += f' ({dates.min():%Y-%m-%d} to {dates.max():%Y-%m-%d})'
    lines.append(f'Rows: {total:,} | Columns: {len(latest.columns)} | Showing the {scope}')
    corrected = latest.attrs.get('corrected_dates') or {}
    if corrected:
        details = ', '.join(f'{column} from {reference} in {count:,}'
                            for column, (reference, count) in corrected.items())
        lines.append(f'Corrected from NSE reference dates: {details} of these rows.')
    if dates is not None:
        today = pd.Timestamp.today().normalize()
        ahead = int((dates.dt.normalize() > today).sum())
        if ahead:
            lines.append(f"[warning] {ahead:,} of these rows {'is' if ahead == 1 else 'are'} dated "
                         f"after today ({today:%Y-%m-%d}); check the stored dates.")
    lines.append("The first column is each row's position in the file, counting from 0.")
    return lines


def _listing_pages(lines, per_page):
    """Split listing lines into pages, repeating a column block's header after a page break."""
    pages, page, header = [], [], None
    for index, line in enumerate(lines):
        if not line.strip():
            if page and len(page) < per_page:
                page.append(line)
            continue
        starts_block = index == 0 or not lines[index - 1].strip()
        if starts_block:
            header = line
        # A block header needs room for at least one of its rows below it.
        if len(page) >= per_page - (1 if starts_block else 0):
            pages.append(page)
            page = [] if starts_block else [header]
        page.append(line)
    if page:
        pages.append(page)
    return pages


def plot_listing(summary, latest, source, pdf_path, window=None):
    """Save a List result as a timestamped PDF and return its full path."""
    matplotlib.use('Agg')
    pdf_path = str(timestamped_path(pdf_path))
    Path(pdf_path).parent.mkdir(parents=True, exist_ok=True)
    lines = _listing_text(latest, LIST_PDF_CHARACTERS).splitlines() if len(latest) else ['No rows.']
    pages = _listing_pages(lines, LIST_PDF_LINES)
    title = (f'{source.name} | latest {len(latest):,} rows' if window is None
             else f'{source.name} | window {window.label} | {len(latest):,} rows')
    document = PdfPages(pdf_path)
    try:
        for number, page in enumerate(pages, 1):
            figure = plt.figure(figsize=(16.54, 11.69))  # A3 landscape
            figure.text(0.03, 0.965, title, fontsize=18, fontweight='bold', color='#24282b', va='top')
            for offset, line in enumerate(summary):
                figure.text(0.03, 0.925 - offset * 0.022, line, fontsize=10.5, va='top',
                            color='#a34542' if line.startswith('[warning]') else '#454c50')
            figure.text(0.03, 0.913 - len(summary) * 0.022, '\n'.join(page), family='monospace',
                        fontsize=9.5, va='top', linespacing=1.3, color='#24282b')
            figure.text(0.97, 0.02, f'Page {number}/{len(pages)}', fontsize=9, ha='right',
                        color='#555b60')
            try:
                document.savefig(figure)
            finally:
                plt.close(figure)
    finally:
        document.close()
    return pdf_path


def list_parquet(arguments, use_pdf=False):
    """`List <file> [rows|window] [output.pdf]`: print the latest rows of any Parquet file.

    `rows` counts rows. A window - 100d, 350d-25d, Jan2026 or Jan2026-Mar2026 - takes every
    row on its trading days instead, by Date (BizDt where present). With --pdf the listing is
    also saved, by default as charts/<file name>_latest<rows>_rows_<stamp>.pdf or
    charts/<file name>_<window>_rows_<stamp>.pdf. Returns the PDF path, or None.
    """
    counts = [argument for argument in arguments if argument.lstrip('+-').isdigit()]
    outputs = [argument for argument in arguments if argument.lower().endswith('.pdf')]
    windows = []
    for argument in arguments:
        if argument in counts or argument in outputs:
            continue
        try:
            window = parse_report_window(argument)
        except ValueError as error:
            print(f'  [error] {error}')
            return None
        if window is not None:
            windows.append((argument, window))
    files = [argument for argument in arguments
             if argument not in counts + outputs + [token for token, _ in windows]]
    if (len(files) != 1 or len(counts) + len(windows) > 1 or len(outputs) > 1
            or files[0].startswith('--')):
        print('Usage: python Option-OGN.py [--pdf] List <file.parquet> [rows|window] [output.pdf]')
        print(f'  rows        optional - latest N rows (default {LATEST_ROWS}), by Date when the file has one')
        print('  window      optional - every row on 100d (latest 100 trading days), 350d-25d,')
        print('              Jan2026 or Jan2026-Mar2026, instead of a row count')
        print('  --pdf       also save the listing as a PDF, by default in the charts folder')
        print('  output.pdf  optional - custom PDF name; needs --pdf')
        print('  Quote paths that contain spaces.')
        return None
    window = windows[0][1] if windows else None
    rows = int(counts[0]) if counts else LATEST_ROWS
    if window is None and rows <= 0:
        print(f'  [error] rows must be positive, got {rows}.')
        return None
    if outputs and not use_pdf:
        print(f'  [error] Add --pdf to save the listing as {outputs[0]}.')
        return None

    source = Path(os.path.abspath(files[0]))
    try:
        latest, total, order = latest_parquet_rows(source, rows, window=window)
    except (OSError, ValueError, NotImplementedError) as error:
        print(f'  [error] {error}')
        return None
    summary = _listing_summary(source, latest, total, order, window)
    for line in summary:
        print(f'  {line}')
    if len(latest):
        print()
        print(_listing_text(latest, shutil.get_terminal_size((160, 24)).columns))
    if not use_pdf:
        return None
    name = (f'{source.stem}_latest{rows}_rows.pdf' if window is None
            else f'{source.stem}_{window.label}_rows.pdf')
    pdf_path = plot_listing(summary, latest, source, outputs[0] if outputs else str(CHARTS_DIR / name),
                            window=window)
    print(f'\n  PDF saved: {pdf_path}')
    return pdf_path


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
        python Option-OGN.py --pdf WTI 250d           # one symbol, last 250 trading days
        python Option-OGN.py --pdf WTI 350d-25d       # ... 350 back to 25 back (latest 25 excluded)
        python Option-OGN.py --pdf WTI Jan2026        # ... January 2026 (also Jan2026-Mar2026)
        python Option-OGN.py WTI US02Y__US10Y         # ... plus a comparison
        python Option-OGN.py WTI US02Y__US10Y 250d    # ... over the last 250 aligned observations
        python Option-OGN.py --pdf WTI JP10Y --periods 120  # monthly alignment
        python Option-OGN.py --pdf WTI JP10Y --compare-frequency quarterly
        python Option-OGN.py --estimator Raw WTI      # choose the volatility estimator
        python Option-OGN.py --trend-bars 250 GLD     # widen the trendline lookback
        python Option-OGN.py --trend-distance 20 GLD  # demand 20 bars between pivots
        python Option-OGN.py --trend-prominence 5 GLD # absolute prominence, price units
        python Option-OGN.py --trend-prominence-pct 5 GLD  # auto-scale off 5% of range
        python Option-OGN.py --pdf                    # all FnO -> charts/FnO_Analysis_<stamp>.pdf
        python Option-OGN.py --pdf WTI                # -> charts/WTI_Analysis_<stamp>.pdf
        python Option-OGN.py --pdf WTI US02Y__US10Y   # -> charts/WTI_vs_US02Y__US10Y_Analysis_<stamp>.pdf
        python Option-OGN.py --pdf output.pdf         # custom output file -> output_<stamp>.pdf
        python Option-OGN.py List "<file>.parquet" 20 # latest 20 rows of any Parquet file
        python Option-OGN.py --pdf List "<file>.parquet" 100d  # -> charts/<file>_100d_rows_<stamp>.pdf

    <stamp> is the run time as YYYYMMDD_HHMMSS, so reruns never overwrite a report.
    Each PDF's full path is printed once it is saved.
    """
    args = sys.argv[1:]
    use_pdf = '--pdf' in args
    if use_pdf:
        args.remove('--pdf')

    # Legacy Windows code pages cannot encode this script's Unicode output.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if args and args[0].lower() == 'list':
        list_parquet(args[1:], use_pdf=use_pdf)
        return

    try:
        raw_option_dates = _take_flag_value(args, '--option-dates')
        raw_option_contracts = _take_flag_value(args, '--option-min-contracts')
        raw_option_outliers = _take_flag_value(args, '--option-outliers')
        raw_option_rate = _take_flag_value(args, '--option-rate')
        option_iv_unit = (_take_flag_value(args, '--option-iv-unit') or 'percent').lower()
        option_dates = (option_overlay.OPTION_HISTORY_DATES if raw_option_dates is None
                        else _positive_number(raw_option_dates, '--option-dates', int))
        option_min_contracts = (option_overlay.OPTION_MIN_CONTRACTS if raw_option_contracts is None
                                else _positive_number(raw_option_contracts, '--option-min-contracts', int))
        option_outliers = option_overlay.OPTION_OUTLIER_COUNT if raw_option_outliers is None else int(raw_option_outliers)
        option_rate = RiskFreeRate if raw_option_rate is None else float(raw_option_rate)
        if option_outliers not in (0, 1, 2):
            raise ValueError('--option-outliers must be 0, 1 or 2.')
        if option_iv_unit not in ('percent', 'decimal'):
            raise ValueError('--option-iv-unit must be percent or decimal.')
        if not np.isfinite(option_rate) or not -1 < option_rate < 1:
            raise ValueError('--option-rate must be a finite annual decimal between -1 and 1.')
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

    pdf_path = None
    tokens = []
    for arg in args:
        if arg.lower().endswith('.pdf'):
            pdf_path = arg
        else:
            tokens.append(arg)

    days = None if requested_periods is None else ReportWindow(f'{requested_periods}d', last=requested_periods)
    try:
        trailing = parse_report_window(tokens[-1]) if tokens else None
        if trailing is not None:
            if days is not None:
                raise ValueError('Use --periods or the trailing window, not both.')
            days = trailing
            tokens.pop()
        elif tokens and tokens[-1].lstrip('+-').isdigit():
            raise ValueError(f"Write the window as {tokens[-1].lstrip('+-')}d (trading days), "
                             f"350d-25d or Jan2026.")
        for token in tokens:
            try:
                misplaced = parse_report_window(token) is not None
            except ValueError:
                misplaced = True
            if misplaced:
                raise ValueError(f"Give one window, after the symbols: {token}")
    except ValueError as e:
        print(f"  [error] {e}")
        return

    if len(tokens) > 2:
        print("Usage: python Option-OGN.py [--pdf] [--estimator NAME] "
              "[--trend-bars N] [--trend-distance N] [--trend-prominence X] "
              "[--compare-frequency FREQ] [--compare-aggregation METHOD] "
              "[symbol] [compare_symbol] [window]")
        print("  symbol            full technical analysis for this series")
        print("  compare_symbol    optional - append a statistical comparison")
        print("  window            optional - 250d (last 250 trading days), 350d-25d (latest 25 excluded),")
        print("                    Jan2026 or Jan2026-Mar2026; also --periods N. Counts are observations")
        print("                    at the analysed cadence, e.g. aligned months for a monthly comparison")
        print(f"  List <file> [rows|window]  latest rows (default {LATEST_ROWS}) or every row in a window"
              f" (100d, Jan2026) of any Parquet file; --pdf also saves a PDF")
        print("  --compare-frequency   auto (slower source), daily, weekly, monthly, quarterly, annual")
        print("  --compare-aggregation auto (series-specific), mean, last, sum")
        print('  --option-dates N          recent trading dates for IV overlays (default 5)')
        print('  --option-min-contracts N  minimum daily traded contracts (default 10)')
        print('  --option-outliers N       extra smile-MAD outliers per side/expiry/date (0, 1, 2)')
        print('  --option-rate R           annual decimal rate for Black-76 (default 0.065)')
        print('  --option-iv-unit UNIT     source IV units: percent (default) or decimal')
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

    if days is not None and not symbol:
        print('  [error] A report window requires a symbol.')
        return

    if not compare_with and (comparison_frequency != 'auto' or comparison_aggregation != 'auto'):
        print('  [error] Comparison options require a second symbol.')
        return

    if use_pdf and not pdf_path:
        suffix = f"_{days.label}" if days is not None else ""
        if symbol and compare_with:
            if comparison_frequency != 'auto':
                suffix += f'_{comparison_frequency}'
            if comparison_aggregation != 'auto':
                suffix += f'_{comparison_aggregation}'
            pdf_path = str(CHARTS_DIR / f"{symbol}_vs_{compare_with}{suffix}_Analysis.pdf")
        elif symbol:
            pdf_path = str(CHARTS_DIR / f"{symbol}{suffix}_Analysis.pdf")
        else:
            pdf_path = str(CHARTS_DIR / "FnO_Analysis.pdf")

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
                    comparison_aggregation=comparison_aggregation,
                    option_dates=option_dates, option_min_contracts=option_min_contracts,
                    option_outliers=option_outliers, option_rate=option_rate,
                    option_iv_unit=option_iv_unit)
    except (ValueError, FileNotFoundError) as e:
        print(f"  [error] {e}")


if __name__ == "__main__":
    main()
