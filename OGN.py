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
    rows, total, order = latest_parquet_rows(DERIVATIVES_PROCESSED / "ABB.parquet", 20)

@author: HRTR
"""

import datetime
import re
import warnings
from pathlib import Path
from typing import NamedTuple, Optional

import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Data store paths (must match OGN v2.0-download.py). The store lives in a fixed
# folder, independent of the scripts' folder and the working directory.
# ---------------------------------------------------------------------------
DATA_ROOT = Path(r"C:\OGN-OneDrive\OneDrive\Github projects\OGN") / "MarketData_Parquet"

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
MACRO_PROCESSED          = DATA_ROOT / "Macro" / "Processed"

# NSE's F&O bhavcopy switched to the UDiFF layout in January 2024. Its
# instrument codes are mapped onto the legacy names so both eras filter alike.
UDIFF_INSTRUMENTS = {'IDF': 'FUTIDX', 'STF': 'FUTSTK', 'IDO': 'OPTIDX', 'STO': 'OPTSTK'}

# Index derivatives have no cash-market row; their spot is the stored index
# close. Only indices kept by the Indices download can be mapped (MINIFTY was
# a mini contract on NIFTY 50; NFTYMCAP50 was renamed NIFTYMID50 in 2016).
INDEX_UNDERLYINGS = {
    'NIFTY': 'NIFTY', 'MINIFTY': 'NIFTY', 'BANKNIFTY': 'BANKNIFTY', 'NIFTYNXT50': 'NIFTYNEXT50',
    'NFTYMCAP50': 'NIFTYMIDCAP50', 'NIFTYMID50': 'NIFTYMIDCAP50',
}


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
        DataFrame with the symbol's data, Date column parsed as datetime,
        taken from NSE's BizDt where a row has one (see corrected_dates)
        and sorted by it when that changed any row.

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
        dates = corrected_dates(df)
        if not dates.equals(df['Date']):
            # Corrected rows no longer follow the file's stored date order.
            df['Date'] = dates
            df = df.sort_values('Date', kind='stable', ignore_index=isinstance(df.index, pd.RangeIndex))
    return df


# UDiFF rows carry NSE's own ISO dates next to the parsed ones. The F&O parser has stored
# some Date and Expiry values with day and month swapped (2024-08-01 as 2024-01-08), so
# these NSE columns win wherever they hold a valid date. Files without them, such as
# equity, index and macro files, keep their stored dates.
NSE_REFERENCE_DATES = {'Date': 'BizDt', 'Expiry': 'FininstrmActlXpryDt'}


def _nse_reference(columns, column):
    """Name of `column`'s NSE reference column among `columns` (any case), or None."""
    wanted = {name.lower(): source.lower() for name, source in NSE_REFERENCE_DATES.items()}
    reference = wanted.get(str(column).lower())
    return next((name for name in columns if reference and str(name).lower() == reference), None)


def corrected_dates(frame: pd.DataFrame, column: str = 'Date', errors: str = 'raise') -> pd.Series:
    """`column` as datetimes, replaced by its NSE reference date wherever that is valid.

    Date takes BizDt and Expiry takes FininstrmActlXpryDt (NSE_REFERENCE_DATES); the
    reference is parsed strictly as ISO 8601, never day-first. Rows without a valid
    reference, and frames without the reference column, keep `column`'s own dates.
    """
    dates = pd.to_datetime(frame[column], errors=errors)
    reference = _nse_reference(frame.columns, column)
    if reference is None:
        return dates
    return pd.to_datetime(frame[reference], format='ISO8601', errors='coerce').fillna(dates)


def list_symbols(directory: Path) -> list:
    """Return sorted list of available symbols in a processed directory."""
    if not directory.exists():
        return []
    return sorted(p.stem for p in directory.glob("*.parquet"))


# ---------------------------------------------------------------------------
# Report windows: 250d, 350d-25d, Jan2026, Jan2026-Mar2026
# ---------------------------------------------------------------------------

_WINDOW_COUNTS = re.compile(r'(\d+)d(?:-(\d+)d)?', re.IGNORECASE)
_WINDOW_MONTHS = re.compile(r'([a-z]+)(\d{4})(?:-([a-z]+)(\d{4}))?', re.IGNORECASE)
_MONTH_NAMES = ('january', 'february', 'march', 'april', 'may', 'june', 'july',
                'august', 'september', 'october', 'november', 'december')


class ReportWindow(NamedTuple):
    """The period a report or listing covers.

    Count windows are trading days, i.e. observations at the analysed cadence: the
    latest `last`, minus the newest `skip`. Month windows cover the calendar dates
    `start` to `end` inclusive.
    """
    label: str
    last: Optional[int] = None
    skip: int = 0
    start: Optional[pd.Timestamp] = None
    end: Optional[pd.Timestamp] = None

    @property
    def size(self):
        """Observations a count window asks for; None for month windows."""
        return None if self.last is None else self.last - self.skip

    def through_end(self, dates):
        """Boolean mask of ascending `dates` up to the window's end."""
        dates = pd.DatetimeIndex(dates)
        if self.end is not None:
            return np.asarray(dates < self.end + pd.Timedelta(days=1))
        keep = np.ones(len(dates), dtype=bool)
        keep[max(len(dates) - self.skip, 0):] = False
        return keep

    def from_start(self, frame):
        """Rows from the window's start, for a frame already cut at its end."""
        if self.start is not None:
            return frame[np.asarray(pd.DatetimeIndex(frame.index) >= self.start)]
        return frame.iloc[-self.size:]

    def select(self, frame):
        """Rows of a date-indexed, ascending frame or Series inside the window."""
        return self.from_start(frame[self.through_end(frame.index)])


def _month_start(name, year):
    """First day of month `name` (Jan or January, any case) in `year`, or None."""
    name = name.lower()
    for number, month in enumerate(_MONTH_NAMES, 1):
        if name in (month, month[:3]):
            return pd.Timestamp(int(year), number, 1)
    return None


def parse_report_window(text):
    """Parse 250d, 350d-25d, Jan2026 or Jan2026-Mar2026; None when `text` is not a window."""
    match = _WINDOW_COUNTS.fullmatch(text)
    if match:
        last, skip = int(match.group(1)), int(match.group(2) or 0)
        if last <= 0:
            raise ValueError(f"observations must be positive, got {text}.")
        if last <= skip:
            raise ValueError(f"{text}: the first count must exceed the second, e.g. 350d-25d.")
        return ReportWindow(f'{last}d' + (f'-{skip}d' if skip else ''), last=last, skip=skip)
    match = _WINDOW_MONTHS.fullmatch(text)
    if match:
        first = _month_start(match.group(1), match.group(2))
        final = _month_start(match.group(3), match.group(4)) if match.group(3) else first
        if first is not None and final is not None:
            if final < first:
                raise ValueError(f"{text}: the months must run forward, e.g. Jan2026-Mar2026.")
            label = '-'.join(dict.fromkeys(
                f'{_MONTH_NAMES[month.month - 1][:3].title()}{month.year}' for month in (first, final)))
            return ReportWindow(label, start=first, end=final + pd.offsets.MonthEnd(0))
    return None


def as_report_window(value):
    """A ReportWindow from None, a ReportWindow, window text, or a count of trailing observations."""
    if value is None or isinstance(value, ReportWindow):
        return value
    if isinstance(value, str):
        window = parse_report_window(value.strip())
        if window is None:
            raise ValueError(f"Unknown window '{value}': use 250d, 350d-25d, Jan2026 or Jan2026-Mar2026.")
        return window
    if value <= 0:
        raise ValueError(f"observations must be positive, got {value}.")
    return ReportWindow(f'{int(value)}d', last=int(value))


LATEST_ROWS = 10  # Default count for latest_parquet_rows and `Option-OGN.py List`


def _naive_dates(values) -> pd.Series:
    """Parse values as naive UTC datetimes; anything unparseable becomes NaT."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        return pd.to_datetime(values, errors='coerce', utc=True).dt.tz_convert(None)


def latest_parquet_rows(path, rows: int = LATEST_ROWS, window: Optional[ReportWindow] = None):
    """Return the latest `rows` rows of any Parquet file, its row count and its ordering column.

    "Latest" follows a column named Date (any case) when the file has one, using NSE's
    BizDt instead wherever a row carries a valid one (see corrected_dates): a stable sort
    keeps each date's stored row order, and rows without a valid date rank oldest.
    Otherwise the file's last rows are used. A ReportWindow replaces `rows` with every
    row on the window's dates, counting trading days (distinct dates) for 250d or 350d-25d.
    Only the row groups holding the chosen rows are read, so a large file is never loaded
    whole. Returned Date and Expiry columns hold the corrected dates;
    frame.attrs['corrected_dates'] maps each changed column to (reference column, rows changed).

    Returns:
        (DataFrame indexed by each row's 0-based position in the file,
         total rows in the file, ordering column name or None)
    """
    import pyarrow.parquet as pq

    if window is None and rows <= 0:
        raise ValueError(f"rows must be positive, got {rows}.")
    path = Path(path)
    if path.is_dir():
        raise IsADirectoryError(f"{path} is a folder; pass one Parquet file.")
    if not path.exists():
        raise FileNotFoundError(f"No such file: {path}")

    with open(path, 'rb') as handle:
        parquet = pq.ParquetFile(handle)
        total = parquet.metadata.num_rows
        names = parquet.schema_arrow.names
        order = next((name for name in names if name.lower() == 'date'), None)
        reference = _nse_reference(names, order or 'Date')
        positions = np.arange(max(total - rows, 0), total)
        dates = None
        if (order or reference) and total:
            stored = parquet.read(columns=[name for name in (order, reference) if name]).to_pandas(
                date_as_object=False, ignore_metadata=True)  # A stored Date index stays a column
            try:
                dates = (_naive_dates(stored[order]) if order
                         else pd.Series(pd.NaT, index=stored.index, dtype='datetime64[ns]'))
                if reference:
                    dates = pd.to_datetime(stored[reference], format='ISO8601', errors='coerce').fillna(dates)
            except (TypeError, ValueError):
                dates = None
            if dates is None or dates.isna().all():
                order, dates = None, None
            else:
                order = order or reference
                # NaT is the smallest int64, so rows without a date rank oldest.
                positions = np.argsort(dates.to_numpy().view('int64'), kind='stable')
                if window is None:
                    positions = positions[-rows:]
                else:
                    days = pd.DatetimeIndex(np.unique(dates.dropna().to_numpy()))
                    chosen = window.select(pd.Series(0, index=days)).index
                    positions = positions[np.isin(dates.to_numpy()[positions], chosen.to_numpy())]
        if window is not None and dates is None and total:
            raise ValueError(f"{path.name} has no usable Date column; give a row count instead of {window.label}.")

        sizes = np.array([parquet.metadata.row_group(group).num_rows
                          for group in range(parquet.metadata.num_row_groups)], dtype='int64')
        starts = np.concatenate([[0], np.cumsum(sizes)])
        groups = np.searchsorted(starts, positions, side='right') - 1
        needed = np.unique(groups)
        if len(needed):
            table = parquet.read_row_groups(needed.tolist())
            offsets = np.concatenate([[0], np.cumsum(sizes[needed])])[np.searchsorted(needed, groups)]
            table = table.take(positions - starts[groups] + offsets)
        else:
            table = parquet.schema_arrow.empty_table()

    frame = table.to_pandas()
    if not isinstance(frame.index, pd.RangeIndex) or frame.index.name is not None:
        frame = frame.reset_index()  # A stored index becomes an ordinary column
    corrections = {}
    for wanted in NSE_REFERENCE_DATES:
        column = next((name for name in frame.columns if str(name).lower() == wanted.lower()), None)
        source = _nse_reference(frame.columns, column) if column is not None else None
        if source is not None:
            stored = pd.to_datetime(frame[column], errors='coerce')
            frame[column] = corrected_dates(frame, column, errors='coerce')
            changed = int((frame[column].notna() & frame[column].ne(stored)).sum())
            if changed:
                corrections[column] = (source, changed)
    frame.index = pd.Index(positions)
    frame.attrs['corrected_dates'] = corrections
    return frame, total, order


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

def _underlying_close(symbol: str) -> pd.Series:
    """Same-day close of a derivative's underlying, indexed by Date.

    Index derivatives use the stored index close; anything else uses the
    cash-market EQ series close (other series are bonds or block deals).
    Returns an empty Series when no matching cash data is stored.
    """
    try:
        if symbol in INDEX_UNDERLYINGS:
            frame = _load_parquet(INDICES_PROCESSED, INDEX_UNDERLYINGS[symbol])
        else:
            frame = _load_parquet(EQUITY_PROCESSED, symbol)
            if 'Series' not in frame.columns:
                return pd.Series(dtype=float)
            frame = frame[frame['Series'].astype(str).str.strip().eq('EQ')]
    except FileNotFoundError:
        return pd.Series(dtype=float)
    if 'Close' not in frame.columns:
        return pd.Series(dtype=float)
    close = pd.Series(pd.to_numeric(frame['Close'], errors='coerce').to_numpy(),
                      index=frame['Date'])
    return close.dropna().groupby(level=0).last()


def load_derivatives(symbol: str, start: str = None, end: str = None) -> pd.DataFrame:
    """Load all derivatives data (futures + options) for a symbol.

    Columns: Date, Symbol, Instrument, Open, High, Low, Close, Settle Price,
             Open Int, Change in OI, Contracts, Value, Expiry, Strike Price,
             Option type, Underlying Price, Lot Size

    Rows span NSE's legacy and UDiFF layouts, normalised here: Instrument
    uses the legacy codes and Value is in rupees (legacy files report lakh).
    UDiFF rows carry the underlying price and lot size. Legacy rows take the
    same day's cash-market EQ close (or the stored index close for the index
    derivatives in INDEX_UNDERLYINGS), so spot and strike share one
    corporate-action basis; their Lot Size stays blank. UDiFF rows take
    Date and Expiry from NSE's BizDt and FininstrmActlXpryDt (corrected_dates).
    """
    df = _load_parquet(DERIVATIVES_PROCESSED, symbol)
    # Parse Expiry as datetime for date-based filtering downstream (NSE's own date where present)
    if 'Expiry' in df.columns:
        df['Expiry'] = corrected_dates(df, 'Expiry')
    df = _filter_dates(df, start, end)
    if 'Instrument' in df.columns:
        instrument = df['Instrument'].astype(str).str.strip()
        if 'Value' in df.columns:
            value = pd.to_numeric(df['Value'], errors='coerce')
            df['Value'] = value.where(~instrument.str.startswith(('FUT', 'OPT'), na=False), value * 100_000)
        df['Instrument'] = instrument.replace(UDIFF_INSTRUMENTS)
    spot = pd.Series(np.nan, index=df.index)
    if 'UndrlygPric' in df.columns:
        spot = pd.to_numeric(df['UndrlygPric'], errors='coerce')
    if spot.isna().any():
        spot = spot.fillna(df['Date'].map(_underlying_close(symbol)))
    df['Underlying Price'] = spot
    df['Lot Size'] = (pd.to_numeric(df['NewBrdLotQty'], errors='coerce')
                      if 'NewBrdLotQty' in df.columns else np.nan)
    return df


def load_futures(symbol: str, start: str = None, end: str = None,
                 instrument: str = None) -> pd.DataFrame:
    """Load futures data for a symbol (FUTSTK / FUTIDX rows, both NSE layouts).

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
    """Load options data for a symbol (OPTSTK / OPTIDX rows, both NSE layouts).

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
    """Load WDM daily report data.

    Symbols: Debt_trd_sett (trades), Debt_add (issues added), Debt_mat (issues matured).
    """
    df = _load_parquet(WDM_PROCESSED, symbol)
    return _filter_dates(df, start, end)


# ---------------------------------------------------------------------------
# FRED Macro Series
# ---------------------------------------------------------------------------

def load_macro(symbol: str, start: str = None,
               end: str = None) -> pd.DataFrame:
    """Load a FRED series such as US02Y or GVZ.

    Columns: Date, Symbol, Value, Series, Name, Unit, Source
    """
    df = _load_parquet(MACRO_PROCESSED, symbol)
    return _filter_dates(df, start, end)


def list_macro_symbols() -> list:
    """Return all available FRED macro-series aliases."""
    return list_symbols(MACRO_PROCESSED)


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
        'Macro (FRED)':        MACRO_PROCESSED,
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
