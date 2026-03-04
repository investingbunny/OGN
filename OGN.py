# -*- coding: utf-8 -*-
"""
Data Loader Module for OGN Market Data (v2.0 Parquet Store)

Provides clean functions to load processed market data from the parquet store
created by 'OGN v2.0-download.py'. Replaces the old nsepy-based downloader.

Usage:
    from OGN import load_equity, load_futures, load_options, load_index

    df = load_equity("RELIANCE")
    futures = load_futures("RELIANCE")
    options = load_options("RELIANCE")
    nifty = load_index("NIFTY")

@author: HRTR
"""

import datetime
from pathlib import Path

import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Data store paths (must match OGN v2.0-download.py)
# ---------------------------------------------------------------------------
DATA_ROOT = Path("MarketData_Parquet")

EQUITY_PROCESSED         = DATA_ROOT / "Equity" / "Processed"
DERIVATIVES_PROCESSED    = DATA_ROOT / "Derivatives" / "Processed"
INDICES_PROCESSED        = DATA_ROOT / "Indices" / "Processed"
SHORTSELLING_PROCESSED   = DATA_ROOT / "ShortSelling" / "Processed"
VOLATILITY_PROCESSED     = DATA_ROOT / "Volatility" / "Processed"
MARKETACTIVITY_PROCESSED = DATA_ROOT / "MarketActivity" / "Processed"
PRICEBAND_PROCESSED      = DATA_ROOT / "PriceBand" / "Processed"
PERATIO_PROCESSED        = DATA_ROOT / "PERatio" / "Processed"
CORPBONDS_PROCESSED      = DATA_ROOT / "CorporateBonds" / "Processed"
DELIVERY_PROCESSED       = DATA_ROOT / "DeliveryPositions" / "Processed"
WDM_PROCESSED            = DATA_ROOT / "WDM" / "Processed"


# ---------------------------------------------------------------------------
# Scrip / symbol lists (reference — update periodically)
# ---------------------------------------------------------------------------

# Futures & Options symbols
NSEFnOList = [
    "BANKNIFTY", "NIFTY", "ACC", "ADANIENT", "ADANIPORTS", "AMBUJACEM",
    "APOLLOHOSP", "APOLLOTYRE", "ASHOKLEY", "ASIANPAINT", "AUROPHARMA",
    "AXISBANK", "BAJAJ-AUTO", "BAJAJFINSV", "BAJFINANCE", "BALKRISIND",
    "BANDHANBNK", "BANKBARODA", "BATAINDIA", "BEL", "BERGEPAINT",
    "BHARATFORG", "BHARTIARTL", "BHEL", "BIOCON", "BOSCHLTD", "BPCL",
    "BRITANNIA", "CANBK", "CHOLAFIN", "CIPLA", "COALINDIA", "COLPAL",
    "CONCOR", "CUMMINSIND", "DABUR", "DIVISLAB", "DLF", "DRREDDY",
    "EICHERMOT", "ESCORTS", "EXIDEIND", "FEDERALBNK", "GAIL", "GLENMARK",
    "GMRINFRA", "GODREJCP", "GODREJPROP", "GRASIM", "HAVELLS", "HCLTECH",
    "HDFC", "HDFCBANK", "HDFCLIFE", "HEROMOTOCO", "HINDALCO", "HINDPETRO",
    "HINDUNILVR", "ICICIBANK", "ICICIPRULI", "IDEA", "IDFCFIRSTB", "IGL",
    "INDIGO", "INDUSINDBK", "INFY", "IOC", "ITC", "JINDALSTEL", "JSWSTEEL",
    "JUBLFOOD", "JUSTDIAL", "KOTAKBANK", "L&TFH", "LICHSGFIN", "LT",
    "LUPIN", "M&M", "M&MFIN", "MANAPPURAM", "MARICO", "MARUTI",
    "MCDOWELL-N", "MFSL", "MGL", "MINDTREE", "MOTHERSUMI", "MRF",
    "MUTHOOTFIN", "NATIONALUM", "NAUKRI", "NCC", "NESTLEIND", "NMDC",
    "NTPC", "ONGC", "PAGEIND", "PEL", "PETRONET", "PFC", "PIDILITIND",
    "PNB", "POWERGRID", "PVR", "RAMCOCEM", "RBLBANK", "RECLTD",
    "RELIANCE", "SAIL", "SBILIFE", "SBIN", "SHREECEM", "SIEMENS", "SRF",
    "SRTRANSFIN", "SUNPHARMA", "SUNTV", "TATAMOTORS", "TATAPOWER",
    "TATASTEEL", "TCS", "TECHM", "TITAN", "TORNTPHARM", "TORNTPOWER",
    "TVSMOTOR", "UBL", "ULTRACEMCO", "UPL", "VEDL", "VOLTAS", "WIPRO",
    "ZEEL",
]

# Indices tracked in the parquet store
TRACKED_INDICES = ["NIFTY", "BANKNIFTY", "NIFTYNEXT50", "NIFTY500", "NIFTYMIDCAP50"]

# Quick watchlist (customise as needed)
WATCHLIST = [
    "RELIANCE", "HDFCBANK", "TATASTEEL", "TCS", "TATAMOTORS", "TATAPOWER",
    "INDIGO", "IDEA", "AUROPHARMA", "CIPLA", "FEDERALBNK", "AXISBANK",
    "BHARTIARTL", "BHEL", "SAIL", "JINDALSTEL", "PNB", "HINDALCO",
    "ADANIENT", "MANAPPURAM", "ITC", "ICICIBANK", "BAJFINANCE", "LUPIN",
    "CONCOR", "EICHERMOT", "RBLBANK",
]


# ---------------------------------------------------------------------------
# Core loading helpers
# ---------------------------------------------------------------------------

def _load_parquet(directory: Path, symbol: str) -> pd.DataFrame:
    """Load a single symbol's parquet file from a processed directory.

    Args:
        directory: Path to the processed data directory (e.g. Equity/Processed).
        symbol:    NSE symbol name (used as the parquet filename stem).

    Returns:
        DataFrame with the symbol's data, Date column parsed as datetime.

    Raises:
        FileNotFoundError: If the parquet file does not exist.
    """
    fpath = directory / f"{symbol}.parquet"
    if not fpath.exists():
        raise FileNotFoundError(f"No data file found: {fpath}")
    df = pd.read_parquet(fpath, engine='pyarrow')
    # Ensure Date column is proper datetime for filtering/sorting
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'])
    return df


def list_symbols(directory: Path) -> list:
    """Return sorted list of available symbols in a processed directory."""
    if not directory.exists():
        return []
    return sorted(p.stem for p in directory.glob("*.parquet"))


# ---------------------------------------------------------------------------
# Equity
# ---------------------------------------------------------------------------

def load_equity(symbol: str, start: str = None, end: str = None) -> pd.DataFrame:
    """Load daily OHLC equity data for a symbol.

    Columns: Date, Symbol, Series, Open, High, Low, Close, Last,
             Prev Close, Volume, Turnover

    Args:
        symbol: NSE symbol (e.g. 'RELIANCE')
        start:  Optional start date 'YYYY-MM-DD'
        end:    Optional end date 'YYYY-MM-DD'
    """
    df = _load_parquet(EQUITY_PROCESSED, symbol)
    return _filter_dates(df, start, end)


def list_equity_symbols() -> list:
    """Return all available equity symbols."""
    return list_symbols(EQUITY_PROCESSED)


# ---------------------------------------------------------------------------
# Derivatives (Futures + Options)
# ---------------------------------------------------------------------------

def load_derivatives(symbol: str, start: str = None, end: str = None) -> pd.DataFrame:
    """Load all derivatives data (futures + options) for a symbol.

    Columns: Date, Symbol, Instrument, Open, High, Low, Close, Settle Price,
             Open Int, Change in OI, Contracts, Value, Expiry, Strike Price,
             Option type
    """
    df = _load_parquet(DERIVATIVES_PROCESSED, symbol)
    # Parse Expiry as datetime for date-based filtering downstream
    if 'Expiry' in df.columns:
        df['Expiry'] = pd.to_datetime(df['Expiry'])
    return _filter_dates(df, start, end)


def load_futures(symbol: str, start: str = None, end: str = None,
                 instrument: str = None) -> pd.DataFrame:
    """Load futures data for a symbol (filters to FUTSTK / FUTIDX rows).

    Args:
        symbol:     NSE symbol
        instrument: Specific instrument type ('FUTSTK', 'FUTIDX') or None
    """
    df = load_derivatives(symbol, start, end)
    if instrument:
        return df[df['Instrument'] == instrument].reset_index(drop=True)
    return df[df['Instrument'].str.startswith('FUT')].reset_index(drop=True)


def load_options(symbol: str, start: str = None, end: str = None,
                 option_type: str = None, expiry: str = None) -> pd.DataFrame:
    """Load options data for a symbol (filters to OPTSTK / OPTIDX rows).

    Args:
        symbol:      NSE symbol
        option_type: 'CE' or 'PE' (or None for both)
        expiry:      Specific expiry date 'YYYY-MM-DD' (or None for all)
    """
    df = load_derivatives(symbol, start, end)
    df = df[df['Instrument'].str.startswith('OPT')]
    if option_type:
        df = df[df['Option type'] == option_type]
    if expiry:
        df = df[df['Expiry'] == pd.Timestamp(expiry)]
    return df.reset_index(drop=True)


def load_monthly_futures(symbol: str, start: str = None,
                         end: str = None) -> pd.DataFrame:
    """Load futures — nearest-month contract only (one row per date).

    Equivalent to old ``{symbol}_monthly-futures.ftr``.
    """
    df = load_futures(symbol, start, end)
    if df.empty:
        return df
    # Sort by Date and Expiry, then take first per date → nearest expiry
    df = df.sort_values(['Date', 'Expiry'])
    return df.groupby('Date').first().reset_index()


def load_monthly_options(symbol: str, start: str = None,
                         end: str = None) -> pd.DataFrame:
    """Load options — nearest-month expiry only.

    Equivalent to old ``{symbol}_monthly-options.ftr``.
    """
    df = load_options(symbol, start, end)
    if df.empty:
        return df
    # Find the nearest (earliest) expiry for each trading date
    nearest = df.groupby('Date')['Expiry'].min().reset_index()
    nearest.columns = ['Date', '_near']
    # Keep only rows matching the nearest expiry per date
    df = df.merge(nearest, on='Date')
    df = df[df['Expiry'] == df['_near']].drop(columns=['_near'])
    return df.reset_index(drop=True)


def load_full_futures(symbol: str, start: str = None,
                      end: str = None) -> pd.DataFrame:
    """Load all futures contracts (near + mid + far month).

    Equivalent to old ``{symbol}_full-futures.ftr``.
    """
    return load_futures(symbol, start, end)


def list_derivatives_symbols() -> list:
    """Return all available derivatives symbols."""
    return list_symbols(DERIVATIVES_PROCESSED)


# ---------------------------------------------------------------------------
# Indices
# ---------------------------------------------------------------------------

def load_index(symbol: str, start: str = None, end: str = None) -> pd.DataFrame:
    """Load index data.

    Columns: Date, Symbol, Open, High, Low, Close, Change, Percent Change,
             Volume, Turnover, PE, PB, DY

    Standard symbols: NIFTY, BANKNIFTY, NIFTYNEXT50, NIFTY500, NIFTYMIDCAP50
    """
    df = _load_parquet(INDICES_PROCESSED, symbol)
    return _filter_dates(df, start, end)


def list_index_symbols() -> list:
    """Return all available index symbols."""
    return list_symbols(INDICES_PROCESSED)


# ---------------------------------------------------------------------------
# Short Selling
# ---------------------------------------------------------------------------

def load_short_selling(symbol: str, start: str = None,
                       end: str = None) -> pd.DataFrame:
    """Columns: Date, Symbol, Qty Short Sold, Qty Short Buy"""
    df = _load_parquet(SHORTSELLING_PROCESSED, symbol)
    return _filter_dates(df, start, end)


# ---------------------------------------------------------------------------
# Volatility
# ---------------------------------------------------------------------------

def load_volatility(symbol: str, start: str = None,
                    end: str = None) -> pd.DataFrame:
    """Columns: Date, Symbol, Daily Volatility, Annl Volatility,
    Pct Change, Close, Prev Close"""
    df = _load_parquet(VOLATILITY_PROCESSED, symbol)
    return _filter_dates(df, start, end)


# ---------------------------------------------------------------------------
# Market Activity
# ---------------------------------------------------------------------------

def load_market_activity(symbol: str = "MARKET", start: str = None,
                         end: str = None) -> pd.DataFrame:
    """Load market-wide activity data."""
    df = _load_parquet(MARKETACTIVITY_PROCESSED, symbol)
    return _filter_dates(df, start, end)


# ---------------------------------------------------------------------------
# Price Band
# ---------------------------------------------------------------------------

def load_price_band(symbol: str, start: str = None,
                    end: str = None) -> pd.DataFrame:
    """Columns: Date, Symbol, Series, Old Band, New Band, Effective Date"""
    df = _load_parquet(PRICEBAND_PROCESSED, symbol)
    return _filter_dates(df, start, end)


# ---------------------------------------------------------------------------
# PE Ratio
# ---------------------------------------------------------------------------

def load_pe_ratio(symbol: str, start: str = None,
                  end: str = None) -> pd.DataFrame:
    """Columns: Date, Symbol, PE, PB, DY"""
    df = _load_parquet(PERATIO_PROCESSED, symbol)
    return _filter_dates(df, start, end)


# ---------------------------------------------------------------------------
# Corporate Bonds
# ---------------------------------------------------------------------------

def load_corp_bonds(symbol: str, start: str = None,
                    end: str = None) -> pd.DataFrame:
    """Columns: Date, Symbol (ISIN), Security Name, Traded Value,
    Traded Qty, No of Trades, + variable yield columns"""
    df = _load_parquet(CORPBONDS_PROCESSED, symbol)
    return _filter_dates(df, start, end)


# ---------------------------------------------------------------------------
# Delivery Positions
# ---------------------------------------------------------------------------

def load_delivery(symbol: str, start: str = None,
                  end: str = None) -> pd.DataFrame:
    """Columns: Date, Symbol, Series, Qty Traded, Deliverable Qty, Delivery Pct"""
    df = _load_parquet(DELIVERY_PROCESSED, symbol)
    return _filter_dates(df, start, end)


# ---------------------------------------------------------------------------
# WDM Daily Reports
# ---------------------------------------------------------------------------

def load_wdm(symbol: str, start: str = None,
             end: str = None) -> pd.DataFrame:
    """Load WDM daily report data (symbol = Debt_{subfile_stem})."""
    df = _load_parquet(WDM_PROCESSED, symbol)
    return _filter_dates(df, start, end)


# ---------------------------------------------------------------------------
# Multi-symbol convenience loaders
# ---------------------------------------------------------------------------

def load_equity_panel(symbols: list, start: str = None, end: str = None,
                      column: str = 'Close') -> pd.DataFrame:
    """Load a single column for multiple equity symbols → wide DataFrame.

    Returns DataFrame with Date index and symbol-name columns.
    Useful for correlation analysis, portfolio construction, etc.

    Args:
        symbols: List of NSE symbol names.
        start:   Optional start date 'YYYY-MM-DD'.
        end:     Optional end date 'YYYY-MM-DD'.
        column:  Column to extract (default 'Close').
    """
    frames = {}
    for sym in symbols:
        try:
            df = load_equity(sym, start, end)
            # Pivot each symbol's column into a dict entry
            frames[sym] = df.set_index('Date')[column]
        except FileNotFoundError:
            pass  # Skip symbols without data files
    if not frames:
        return pd.DataFrame()
    # Combine into a wide DataFrame (one column per symbol)
    panel = pd.DataFrame(frames)
    panel.index.name = 'Date'
    return panel


def load_index_panel(symbols: list = None, start: str = None,
                     end: str = None, column: str = 'Close') -> pd.DataFrame:
    """Load a single column for multiple indices → wide DataFrame.

    Args:
        symbols: List of index names (default: TRACKED_INDICES).
        start:   Optional start date 'YYYY-MM-DD'.
        end:     Optional end date 'YYYY-MM-DD'.
        column:  Column to extract (default 'Close').
    """
    if symbols is None:
        symbols = TRACKED_INDICES
    frames = {}
    for sym in symbols:
        try:
            df = load_index(sym, start, end)
            frames[sym] = df.set_index('Date')[column]
        except FileNotFoundError:
            pass  # Skip indices without data files
    if not frames:
        return pd.DataFrame()
    # Combine into a wide DataFrame (one column per index)
    panel = pd.DataFrame(frames)
    panel.index.name = 'Date'
    return panel


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _filter_dates(df: pd.DataFrame, start: str = None,
                  end: str = None) -> pd.DataFrame:
    """Filter DataFrame by date range (inclusive on both ends).

    Args:
        df:    DataFrame with a 'Date' column.
        start: Optional start date string 'YYYY-MM-DD'.
        end:   Optional end date string 'YYYY-MM-DD'.

    Returns:
        Filtered DataFrame with reset index.
    """
    if df.empty or 'Date' not in df.columns:
        return df
    if start:
        df = df[df['Date'] >= pd.Timestamp(start)]
    if end:
        df = df[df['Date'] <= pd.Timestamp(end)]
    return df.reset_index(drop=True)


def get_latest_date(directory: Path = None) -> datetime.date:
    """Get the most recent date available in a data store directory.

    Samples a set of well-known liquid symbols first, then falls back to
    a broader scan of up to 50 symbols.  Returns the maximum date found
    across all sampled files.  Defaults to EQUITY_PROCESSED if no
    directory is specified.
    """
    if directory is None:
        directory = EQUITY_PROCESSED
    syms = list_symbols(directory)
    if not syms:
        return None

    # Prefer well-known liquid symbols — they are most likely to have
    # the latest trading-day data.  Fall back to a broader sample if
    # none of these are present.
    priority_symbols = [
        'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK',
        'SBIN', 'TATAMOTORS', 'ITC', 'LT', 'AXISBANK',
        # Index names (for Indices/Processed)
        'NIFTY', 'BANKNIFTY', 'NIFTY500',
    ]
    candidates = [s for s in priority_symbols if s in syms]

    # If none of the priority symbols exist, sample up to 50 from the full list
    if not candidates:
        import random
        candidates = random.sample(syms, min(50, len(syms)))

    latest = None
    for sym in candidates:
        try:
            df = _load_parquet(directory, sym)
            if 'Date' in df.columns and not df.empty:
                sym_max = pd.to_datetime(df['Date']).max().date()
                if latest is None or sym_max > latest:
                    latest = sym_max
        except Exception:
            continue
    return latest


def data_summary() -> pd.DataFrame:
    """Return a summary of available data across all categories.

    Returns a DataFrame with columns: Category, Symbols (count),
    Directory (path string), Exists (bool).
    """
    categories = {
        'Equity':             EQUITY_PROCESSED,
        'Derivatives':        DERIVATIVES_PROCESSED,
        'Indices':            INDICES_PROCESSED,
        'Short Selling':      SHORTSELLING_PROCESSED,
        'Volatility':         VOLATILITY_PROCESSED,
        'Market Activity':    MARKETACTIVITY_PROCESSED,
        'Price Band':         PRICEBAND_PROCESSED,
        'PE Ratio':           PERATIO_PROCESSED,
        'Corporate Bonds':    CORPBONDS_PROCESSED,
        'Delivery Positions': DELIVERY_PROCESSED,
        'WDM Daily':          WDM_PROCESSED,
    }
    rows = []
    for name, path in categories.items():
        syms = list_symbols(path)
        rows.append({
            'Category': name,
            'Symbols': len(syms),        # Number of parquet files
            'Directory': str(path),
            'Exists': path.exists(),      # Whether the directory exists on disk
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# CLI entry point (quick data check)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("OGN Market Data Store — Summary")
    print("=" * 60)
    summary = data_summary()
    print(summary.to_string(index=False))
    print()
    latest = get_latest_date()
    if latest:
        print(f"Latest equity data: {latest}")
    else:
        print("No equity data found. Run 'OGN v2.0-download.py' first.")
