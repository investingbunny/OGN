# -*- coding: utf-8 -*-
"""
Modernized NSE Market Data Downloader
Created on Feb 21, 2026
Author: Jules (Modernized from original OGN v2.0)

This script downloads Equity (CM), Derivatives (FO), and Indices data from the NSE website.
It supports both legacy archive formats and the new UDiFF format (post July 2024).
Data is stored in Parquet format for optimal space and performance.
"""

import os
import io
import time
import zipfile
import datetime
import threading
import requests
import requests.exceptions
import urllib.parse
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Constants & Configuration ---
BASE_URL = "https://www.nseindia.com"
ALL_REPORTS_URL = f"{BASE_URL}/all-reports"
ARCHIVE_URL = "https://nsearchives.nseindia.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

UDIFF_START_DATE = datetime.date(2024, 7, 8)
DEFAULT_START_DATE = datetime.date(2010, 1, 1)

DATA_ROOT = Path("MarketData_Parquet")
EQUITY_RAW = DATA_ROOT / "Equity" / "Raw"
EQUITY_PROCESSED = DATA_ROOT / "Equity" / "Processed"
DERIVATIVES_RAW = DATA_ROOT / "Derivatives" / "Raw"
DERIVATIVES_PROCESSED = DATA_ROOT / "Derivatives" / "Processed"
INDICES_RAW = DATA_ROOT / "Indices" / "Raw"
INDICES_PROCESSED = DATA_ROOT / "Indices" / "Processed"
SHORTSELLING_RAW = DATA_ROOT / "ShortSelling" / "Raw"
SHORTSELLING_PROCESSED = DATA_ROOT / "ShortSelling" / "Processed"
VOLATILITY_RAW = DATA_ROOT / "Volatility" / "Raw"
VOLATILITY_PROCESSED = DATA_ROOT / "Volatility" / "Processed"
MARKETACTIVITY_RAW = DATA_ROOT / "MarketActivity" / "Raw"
MARKETACTIVITY_PROCESSED = DATA_ROOT / "MarketActivity" / "Processed"
PRICEBAND_RAW = DATA_ROOT / "PriceBand" / "Raw"
PRICEBAND_PROCESSED = DATA_ROOT / "PriceBand" / "Processed"
PERATIO_RAW = DATA_ROOT / "PERatio" / "Raw"
PERATIO_PROCESSED = DATA_ROOT / "PERatio" / "Processed"
CORPBONDS_RAW = DATA_ROOT / "CorporateBonds" / "Raw"
CORPBONDS_PROCESSED = DATA_ROOT / "CorporateBonds" / "Processed"
DELIVERY_RAW = DATA_ROOT / "DeliveryPositions" / "Raw"
DELIVERY_PROCESSED = DATA_ROOT / "DeliveryPositions" / "Processed"

# Holiday List (Simplified - ideally fetch from NSE)
HOLIDAYS = [
    '2026-01-26', '2026-03-06', '2026-03-30', '2026-04-10', '2026-04-14',
    '2026-05-01', '2026-10-02', '2026-10-21', '2026-11-05', '2026-12-25'
]
HOLIDAYS = pd.to_datetime(HOLIDAYS).date


class HTTP403Error(Exception):
    """Raised when the server returns 403 Forbidden (data not available)."""
    pass


class NSEMarketDataDownloader:
    """Class to handle robust downloading and storage of NSE market data."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._session_lock = threading.Lock()
        self._last_session_init = 0.0
        self._consecutive_failures = 0
        self._init_session()
        self._create_dirs()

    def _init_session(self):
        """Initializes the session with NSE cookies (thread-safe)."""
        with self._session_lock:
            # Avoid re-initializing too frequently (min 10s gap)
            now = time.time()
            if now - self._last_session_init < 10:
                return
            try:
                self.session.cookies.clear()
                self.session.get(BASE_URL, timeout=15)
                self.session.get(ALL_REPORTS_URL, timeout=15)
                self._last_session_init = now
                self._consecutive_failures = 0
                print("Session (re)initialized successfully.")
            except Exception as e:
                print(f"Warning: Failed to initialize session: {e}")

    def _create_dirs(self):
        """Ensures all necessary directories exist."""
        for path in [EQUITY_RAW, EQUITY_PROCESSED, DERIVATIVES_RAW, DERIVATIVES_PROCESSED,
                     INDICES_RAW, INDICES_PROCESSED, SHORTSELLING_RAW, SHORTSELLING_PROCESSED,
                     VOLATILITY_RAW, VOLATILITY_PROCESSED, MARKETACTIVITY_RAW, MARKETACTIVITY_PROCESSED,
                     PRICEBAND_RAW, PRICEBAND_PROCESSED, PERATIO_RAW, PERATIO_PROCESSED,
                     CORPBONDS_RAW, CORPBONDS_PROCESSED, DELIVERY_RAW, DELIVERY_PROCESSED]:
            path.mkdir(parents=True, exist_ok=True)

    def get_trading_days(self, start_date: datetime.date, end_date: datetime.date) -> List[datetime.date]:
        """Returns a list of business days excluding holidays."""
        bdays = pd.bdate_range(start=start_date, end=end_date)
        days = [d.date() for d in bdays if d.date() not in HOLIDAYS]
        return days

    def _download_file(self, url: str, referer: Optional[str] = None) -> Optional[bytes]:
        """Downloads a file with comprehensive error handling, retry logic, and backoff.

        Handles:
        - HTTP 403/429: Rate limiting — backs off and re-initializes session
        - HTTP 5xx: Server errors — retries with exponential backoff
        - HTTP 404: Not found — returns None immediately (no retry)
        - ConnectionError: Network issues, resets — retries with backoff
        - Timeout: Slow server — retries with increasing timeout
        - SSLError: Certificate issues — retries once then skips
        - ChunkedEncodingError: Incomplete response — retries
        - HTML error pages disguised as 200 — detected and treated as failure
        """
        headers = {}
        if referer:
            headers["Referer"] = referer

        max_retries = 5
        base_delay = 1.0

        for attempt in range(max_retries):
            delay = base_delay * (2 ** attempt)  # Exponential backoff: 1, 2, 4, 8, 16s
            try:
                r = self.session.get(url, timeout=20 + attempt * 5, headers=headers)

                if r.status_code == 200:
                    # Check if it's actually an HTML error page disguised as 200
                    content_type = r.headers.get('Content-Type', '')
                    if content_type.startswith('text/html') and b'<!DOCTYPE html>' in r.content[:100]:
                        # Likely a login/block page — re-init session and retry
                        if attempt < max_retries - 1:
                            print(f"  HTML error page received for {url.split('?')[0]}... re-initializing session.")
                            self._init_session()
                            time.sleep(delay)
                            continue
                        return None
                    self._consecutive_failures = 0
                    return r.content

                elif r.status_code == 404:
                    # Not found — no point retrying
                    return None

                elif r.status_code == 403:
                    # Forbidden — data not available, no retry
                    raise HTTP403Error(f"HTTP 403 for {url.split('?')[0]}")

                elif r.status_code == 401:
                    # Unauthorized — likely session expired
                    print(f"  HTTP 401 for {url.split('?')[0]}... "
                          f"re-initializing session (attempt {attempt+1}/{max_retries}).")
                    self._init_session()
                    time.sleep(delay + 2)

                elif r.status_code == 429:
                    # Rate limited — back off significantly
                    retry_after = int(r.headers.get('Retry-After', delay * 3))
                    print(f"  Rate limited (429). Waiting {retry_after}s before retry "
                          f"(attempt {attempt+1}/{max_retries}).")
                    time.sleep(retry_after)

                elif r.status_code >= 500:
                    # Server error — transient, retry with backoff
                    print(f"  Server error {r.status_code} for {url.split('?')[0]}... "
                          f"retrying in {delay:.0f}s (attempt {attempt+1}/{max_retries}).")
                    time.sleep(delay)

                else:
                    # Other unexpected status codes
                    print(f"  Unexpected HTTP {r.status_code} for {url.split('?')[0]}... "
                          f"retrying in {delay:.0f}s (attempt {attempt+1}/{max_retries}).")
                    time.sleep(delay)

            except requests.exceptions.ConnectionError as e:
                # Connection reset, refused, DNS failure, etc.
                self._consecutive_failures += 1
                print(f"  Connection error (attempt {attempt+1}/{max_retries}): {type(e).__name__}")
                if self._consecutive_failures >= 5:
                    print("  Multiple consecutive connection failures — re-initializing session.")
                    self._init_session()
                time.sleep(delay + 1)

            except requests.exceptions.Timeout as e:
                # Request timed out
                print(f"  Timeout (attempt {attempt+1}/{max_retries}): {e}")
                time.sleep(delay)

            except requests.exceptions.SSLError as e:
                # SSL/TLS certificate issues
                print(f"  SSL error (attempt {attempt+1}/{max_retries}): {e}")
                if attempt >= 1:
                    # SSL errors are usually not transient — don't keep retrying
                    return None
                time.sleep(delay)

            except requests.exceptions.ChunkedEncodingError as e:
                # Incomplete response / connection dropped mid-transfer
                print(f"  Incomplete response (attempt {attempt+1}/{max_retries}): {e}")
                time.sleep(delay)

            except requests.exceptions.ContentDecodingError as e:
                # Corrupted gzip/deflate response
                print(f"  Decoding error (attempt {attempt+1}/{max_retries}): {e}")
                time.sleep(delay)

            except requests.exceptions.RequestException as e:
                # Catch-all for any other requests library errors
                print(f"  Request error (attempt {attempt+1}/{max_retries}): {type(e).__name__}: {e}")
                time.sleep(delay)

            except Exception as e:
                # Truly unexpected errors (shouldn't happen, but don't crash)
                print(f"  Unexpected error (attempt {attempt+1}/{max_retries}): {type(e).__name__}: {e}")
                time.sleep(delay)

        print(f"  All {max_retries} attempts exhausted for {url.split('?')[0]}")
        return None

    # --- Generic report parsing helpers ---

    def _read_csv_with_encoding(self, content_bytes: bytes, **kwargs) -> Optional[pd.DataFrame]:
        """Reads CSV content trying multiple encodings."""
        for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
            try:
                return pd.read_csv(io.BytesIO(content_bytes), encoding=encoding,
                                   on_bad_lines='skip', skipinitialspace=True, **kwargs)
            except (UnicodeDecodeError, UnicodeError):
                continue
            except Exception:
                return None
        return None

    def _parse_report_content(self, content: bytes, date: datetime.date,
                               clean_fn, label: str) -> Optional[pd.DataFrame]:
        """Parses downloaded report content (handles both ZIP and plain CSV)."""
        try:
            if content[:2] == b'PK':
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    data_files = [n for n in z.namelist()
                                  if n.lower().endswith(('.csv', '.dat', '.txt'))]
                    if not data_files:
                        data_files = z.namelist()
                    if not data_files:
                        return None
                    with z.open(data_files[0]) as f:
                        raw_bytes = f.read()
            else:
                raw_bytes = content

            df = self._read_csv_with_encoding(raw_bytes)
            if df is None or df.empty:
                return None
            return clean_fn(df, date)
        except zipfile.BadZipFile:
            df = self._read_csv_with_encoding(content)
            if df is None or df.empty:
                return None
            return clean_fn(df, date)
        except Exception as e:
            print(f"Error parsing {label} for {date}: {e}")
            return None

    def _parse_delivery_content(self, content: bytes, date: datetime.date) -> Optional[pd.DataFrame]:
        """Parses Delivery Positions content (DAT/CSV/ZIP formats).

        DAT files from NSE are comma or pipe delimited with record type markers
        and may lack column headers.
        """
        try:
            raw_bytes = content
            if content[:2] == b'PK':
                try:
                    with zipfile.ZipFile(io.BytesIO(content)) as z:
                        data_files = [n for n in z.namelist()
                                      if n.lower().endswith(('.csv', '.dat', '.txt'))]
                        if not data_files:
                            data_files = z.namelist()
                        if not data_files:
                            return None
                        with z.open(data_files[0]) as f:
                            raw_bytes = f.read()
                except zipfile.BadZipFile:
                    pass  # Try raw_bytes as-is

            # Decode to text
            text = None
            for enc in ['utf-8', 'latin-1', 'cp1252']:
                try:
                    text = raw_bytes.decode(enc)
                    break
                except (UnicodeDecodeError, UnicodeError):
                    continue
            if text is None:
                return None

            # Detect delimiter
            first_line = text.strip().split('\n')[0] if text.strip() else ''
            sep = '|' if '|' in first_line else ','

            # Read CSV
            df = pd.read_csv(io.StringIO(text), sep=sep, on_bad_lines='skip',
                             skipinitialspace=True)
            if df is None or df.empty:
                return None

            # If first column name is numeric, it's a headerless DAT file
            first_col_name = str(df.columns[0]).strip()
            if first_col_name.isdigit():
                df = pd.read_csv(io.StringIO(text), sep=sep, header=None,
                                 on_bad_lines='skip', skipinitialspace=True)
                std_cols = ['Record Type', 'Symbol', 'Series', 'Qty Traded',
                            'Deliverable Qty', 'Delivery Pct']
                if len(df.columns) <= len(std_cols):
                    df.columns = std_cols[:len(df.columns)]
                else:
                    df.columns = std_cols + [f'Extra_{i}' for i in range(len(df.columns) - len(std_cols))]

            return self._clean_delivery_data(df, date)
        except Exception as e:
            print(f"Error parsing Delivery Positions for {date}: {e}")
            return None

    def download_cm_bhavcopy(self, date: datetime.date) -> Optional[pd.DataFrame]:
        """Downloads Equity (Capital Market) Bhavcopy for a given date."""
        if date >= UDIFF_START_DATE:
            # UDiFF Format
            report_name = "CM-UDiFF Common Bhavcopy Final (zip)"
            archives = [{"name": report_name, "type": "archives", "category": "capital-market", "section": "equities"}]
            archives_str = urllib.parse.quote(str(archives).replace("'", '"'))
            url = f"{BASE_URL}/api/reports?archives={archives_str}&date={date.strftime('%d-%b-%Y')}&type=equities&mode=single"
            content = self._download_file(url, referer=ALL_REPORTS_URL)
        else:
            # Legacy Archive Format
            # https://nsearchives.nseindia.com/content/historical/EQUITIES/2024/FEB/cm20FEB2024bhav.csv.zip
            url = f"{ARCHIVE_URL}/content/historical/EQUITIES/{date.strftime('%Y')}/{date.strftime('%b').upper()}/cm{date.strftime('%d%b%Y').upper()}bhav.csv.zip"
            content = self._download_file(url)

        if not content:
            return None

        try:
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                csv_filename = z.namelist()[0]
                with z.open(csv_filename) as f:
                    df = pd.read_csv(f)
                    return self._clean_cm_data(df, date)
        except Exception as e:
            print(f"Error parsing CM Bhavcopy for {date}: {e}")
            return None

    def download_fo_bhavcopy(self, date: datetime.date) -> Optional[pd.DataFrame]:
        """Downloads Derivatives (F&O) Bhavcopy for a given date."""
        if date >= UDIFF_START_DATE:
            # UDiFF Format
            report_name = "F&O - UDiFF Common Bhavcopy Final (zip)"
            archives = [{"name": report_name, "type": "archives", "category": "derivatives", "section": "derivatives"}]
            archives_str = urllib.parse.quote(str(archives).replace("'", '"'))
            url = f"{BASE_URL}/api/reports?archives={archives_str}&date={date.strftime('%d-%b-%Y')}&type=derivatives&mode=single"
            content = self._download_file(url, referer=ALL_REPORTS_URL)
        else:
            # Legacy Archive Format
            # https://nsearchives.nseindia.com/content/historical/DERIVATIVES/2024/FEB/fo20FEB2024bhav.csv.zip
            url = f"{ARCHIVE_URL}/content/historical/DERIVATIVES/{date.strftime('%Y')}/{date.strftime('%b').upper()}/fo{date.strftime('%d%b%Y').upper()}bhav.csv.zip"
            content = self._download_file(url)

        if not content:
            return None

        try:
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                csv_filename = z.namelist()[0]
                with z.open(csv_filename) as f:
                    df = pd.read_csv(f)
                    return self._clean_fo_data(df, date)
        except Exception as e:
            print(f"Error parsing FO Bhavcopy for {date}: {e}")
            return None

    def download_indices_report(self, date: datetime.date) -> Optional[pd.DataFrame]:
        """Downloads Indices PR report for a given date."""
        # https://nsearchives.nseindia.com/archives/equities/bhavcopy/pr/PR200226.zip
        url = f"{ARCHIVE_URL}/archives/equities/bhavcopy/pr/PR{date.strftime('%d%m%y')}.zip"
        content = self._download_file(url)

        if not content:
            return None

        try:
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                # PR zip contains many CSVs, we want the one like PrDDMMYY.csv
                # The naming pattern varies: Pr280226.csv, PR280226.csv, pd280226.csv, etc.
                all_files = z.namelist()
                target_csv = None

                # Try exact patterns first
                for pattern in [
                    f"Pr{date.strftime('%d%m%y')}.csv",
                    f"PR{date.strftime('%d%m%y')}.csv",
                    f"pr{date.strftime('%d%m%y')}.csv",
                ]:
                    if pattern in all_files:
                        target_csv = pattern
                        break

                # Case-insensitive search
                if target_csv is None:
                    date_str = date.strftime('%d%m%y')
                    matches = [n for n in all_files if n.lower() == f"pr{date_str}.csv"]
                    if matches:
                        target_csv = matches[0]

                # Broader search: any CSV with "pr" or "Pr" prefix and the date digits
                if target_csv is None:
                    date_str = date.strftime('%d%m%y')
                    matches = [n for n in all_files if date_str in n and n.lower().endswith('.csv')
                               and n.lower().startswith('pr')]
                    if matches:
                        target_csv = matches[0]

                # Last resort: any CSV containing index-like data (pick the first/largest CSV)
                if target_csv is None:
                    csv_files = [n for n in all_files if n.lower().endswith('.csv')]
                    if csv_files:
                        # Pick the largest CSV (most likely the index data)
                        target_csv = max(csv_files, key=lambda n: z.getinfo(n).file_size)

                if target_csv is None:
                    print(f"No suitable CSV found in PR zip for {date}. Files: {all_files[:5]}")
                    return None

                with z.open(target_csv) as f:
                    raw_bytes = f.read()

                # Try multiple encodings
                df = None
                for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
                    try:
                        df = pd.read_csv(
                            io.BytesIO(raw_bytes),
                            skipinitialspace=True,
                            on_bad_lines='skip',
                            encoding=encoding
                        )
                        break
                    except (UnicodeDecodeError, UnicodeError):
                        continue
                    except Exception:
                        break

                if df is None or df.empty:
                    return None

                # The first ~57 lines are usually the indices
                df = df.head(100)  # Safety margin
                return self._clean_indices_data(df, date)
        except zipfile.BadZipFile:
            # Not a valid zip (might be HTML error page)
            return None
        except Exception as e:
            print(f"Error parsing Indices PR for {date}: {e}")
            return None

    # --- New Report Downloads ---

    def download_short_selling(self, date: datetime.date) -> Optional[pd.DataFrame]:
        """Downloads Short Selling report for a given date."""
        if date >= UDIFF_START_DATE:
            archives = [{"name": "Short Selling", "type": "archives", "category": "capital-market", "section": "equities"}]
            archives_str = urllib.parse.quote(str(archives).replace("'", '"'))
            url = f"{BASE_URL}/api/reports?archives={archives_str}&date={date.strftime('%d-%b-%Y')}&type=equities&mode=single"
            content = self._download_file(url, referer=ALL_REPORTS_URL)
        else:
            url = f"{ARCHIVE_URL}/content/equities/shortselling_{date.strftime('%d%m%Y')}.csv"
            content = self._download_file(url)
        if not content:
            return None
        return self._parse_report_content(content, date, self._clean_short_selling_data, "Short Selling")

    def download_daily_volatility(self, date: datetime.date) -> Optional[pd.DataFrame]:
        """Downloads Daily Volatility report for a given date."""
        if date >= UDIFF_START_DATE:
            archives = [{"name": "Daily Volatility", "type": "archives", "category": "capital-market", "section": "equities"}]
            archives_str = urllib.parse.quote(str(archives).replace("'", '"'))
            url = f"{BASE_URL}/api/reports?archives={archives_str}&date={date.strftime('%d-%b-%Y')}&type=equities&mode=single"
            content = self._download_file(url, referer=ALL_REPORTS_URL)
        else:
            url = f"{ARCHIVE_URL}/archives/nsccl/volt/CMVOLT_{date.strftime('%d%m%Y')}.CSV"
            content = self._download_file(url)
        if not content:
            return None
        return self._parse_report_content(content, date, self._clean_volatility_data, "Daily Volatility")

    def download_market_activity(self, date: datetime.date) -> Optional[pd.DataFrame]:
        """Downloads Market Activity Report for a given date."""
        archives = [{"name": "Market Activity Report", "type": "archives", "category": "capital-market", "section": "equities"}]
        archives_str = urllib.parse.quote(str(archives).replace("'", '"'))
        url = f"{BASE_URL}/api/reports?archives={archives_str}&date={date.strftime('%d-%b-%Y')}&type=equities&mode=single"
        content = self._download_file(url, referer=ALL_REPORTS_URL)
        if not content:
            return None
        return self._parse_report_content(content, date, self._clean_market_activity_data, "Market Activity")

    def download_price_band(self, date: datetime.date) -> Optional[pd.DataFrame]:
        """Downloads Price Band changes from next trade date report."""
        archives = [{"name": "Price Band changes from next trade date", "type": "archives", "category": "capital-market", "section": "equities"}]
        archives_str = urllib.parse.quote(str(archives).replace("'", '"'))
        url = f"{BASE_URL}/api/reports?archives={archives_str}&date={date.strftime('%d-%b-%Y')}&type=equities&mode=single"
        content = self._download_file(url, referer=ALL_REPORTS_URL)
        if not content:
            return None
        return self._parse_report_content(content, date, self._clean_price_band_data, "Price Band")

    def download_pe_ratio(self, date: datetime.date) -> Optional[pd.DataFrame]:
        """Downloads PE Ratio report for a given date."""
        archives = [{"name": "PE Ratio", "type": "archives", "category": "capital-market", "section": "equities"}]
        archives_str = urllib.parse.quote(str(archives).replace("'", '"'))
        url = f"{BASE_URL}/api/reports?archives={archives_str}&date={date.strftime('%d-%b-%Y')}&type=equities&mode=single"
        content = self._download_file(url, referer=ALL_REPORTS_URL)
        if not content:
            return None
        return self._parse_report_content(content, date, self._clean_pe_ratio_data, "PE Ratio")

    def download_corp_bonds(self, date: datetime.date) -> Optional[pd.DataFrame]:
        """Downloads Corporate Bonds Traded Report for a given date."""
        archives = [{"name": "Corporate Bonds Traded Report", "type": "archives", "category": "debt", "section": "debt"}]
        archives_str = urllib.parse.quote(str(archives).replace("'", '"'))
        url = f"{BASE_URL}/api/reports?archives={archives_str}&date={date.strftime('%d-%b-%Y')}&type=debt&mode=single"
        content = self._download_file(url, referer=ALL_REPORTS_URL)
        if not content:
            return None
        return self._parse_report_content(content, date, self._clean_corp_bonds_data, "Corporate Bonds")

    def download_delivery_positions(self, date: datetime.date) -> Optional[pd.DataFrame]:
        """Downloads Security-wise Delivery Positions for a given date.

        Legacy format is a DAT file (comma or pipe delimited with record type markers).
        """
        if date >= UDIFF_START_DATE:
            archives = [{"name": "Security-wise Delivery Positions", "type": "archives", "category": "capital-market", "section": "equities"}]
            archives_str = urllib.parse.quote(str(archives).replace("'", '"'))
            url = f"{BASE_URL}/api/reports?archives={archives_str}&date={date.strftime('%d-%b-%Y')}&type=equities&mode=single"
            content = self._download_file(url, referer=ALL_REPORTS_URL)
        else:
            url = f"{ARCHIVE_URL}/archives/equities/mto/MTO_{date.strftime('%d%m%Y')}.DAT"
            content = self._download_file(url)
        if not content:
            return None
        return self._parse_delivery_content(content, date)

    def _clean_cm_data(self, df: pd.DataFrame, date: datetime.date) -> pd.DataFrame:
        """Standardizes Equity data."""
        df.columns = [c.strip() for c in df.columns]
        
        # UDiFF Mapping
        mapping = {
            'TradDt': 'Date', 'TckrSymb': 'Symbol', 'SctySrs': 'Series',
            'OpnPric': 'Open', 'HghPric': 'High', 'LwPric': 'Low', 'ClsPric': 'Close',
            'LastPric': 'Last', 'PrvsClsgPric': 'Prev Close', 'TtlTradgVol': 'Volume',
            'TtlTrfVal': 'Turnover', 'TtlNbOfTxsExctd': 'Trades',
            'TIMESTAMP': 'Date', 'SYMBOL': 'Symbol', 'SERIES': 'Series',
            'OPEN': 'Open', 'HIGH': 'High', 'LOW': 'Low', 'CLOSE': 'Close',
            'LAST': 'Last', 'PREVCLOSE': 'Prev Close', 'TOTTRDQTY': 'Volume',
            'TOTTRDVAL': 'Turnover', 'TOTALITM': 'Trades'
        }
        df = df.rename(columns=mapping)
        
        # Select important columns
        cols = ['Date', 'Symbol', 'Series', 'Open', 'High', 'Low', 'Close', 'Last', 'Prev Close', 'Volume', 'Turnover']
        available_cols = [c for c in cols if c in df.columns]
        df = df[available_cols].copy()
        
        df['Date'] = pd.to_datetime(df['Date']).dt.date
        numeric_cols = ['Open', 'High', 'Low', 'Close', 'Last', 'Prev Close', 'Volume', 'Turnover']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df

    def _clean_fo_data(self, df: pd.DataFrame, date: datetime.date) -> pd.DataFrame:
        """Standardizes F&O data."""
        df.columns = [c.strip() for c in df.columns]
        
        mapping = {
            'TradDt': 'Date', 'TckrSymb': 'Symbol', 'FinInstrmTp': 'Instrument',
            'OpnPric': 'Open', 'HghPric': 'High', 'LwPric': 'Low', 'ClsPric': 'Close',
            'SttlmPric': 'Settle Price', 'OpnIntrst': 'Open Int', 'ChngInOpnIntrst': 'Change in OI',
            'TtlTradgVol': 'Contracts', 'TtlTrfVal': 'Value', 'XpryDt': 'Expiry',
            'StrkPric': 'Strike Price', 'OptnTp': 'Option type',
            'TIMESTAMP': 'Date', 'SYMBOL': 'Symbol', 'INSTRUMENT': 'Instrument',
            'OPEN': 'Open', 'HIGH': 'High', 'LOW': 'Low', 'CLOSE': 'Close',
            'SETTLE_PR': 'Settle Price', 'OPEN_INT': 'Open Int', 'CHG_IN_OI': 'Change in OI',
            'CONTRACTS': 'Contracts', 'VAL_INLAKH': 'Value', 'EXPIRY_DT': 'Expiry',
            'STRIKE_PR': 'Strike Price', 'OPTION_TYP': 'Option type'
        }
        df = df.rename(columns=mapping)
        
        df['Date'] = pd.to_datetime(df['Date'], format='mixed', dayfirst=True).dt.date
        df['Expiry'] = pd.to_datetime(df['Expiry'], format='mixed', dayfirst=True).dt.date
        
        numeric_cols = ['Open', 'High', 'Low', 'Close', 'Settle Price', 'Open Int', 'Change in OI', 'Contracts', 'Value', 'Strike Price']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        return df

    def _clean_indices_data(self, df: pd.DataFrame, date: datetime.date) -> pd.DataFrame:
        """Standardizes Indices data from PR report.
        
        Handles varying column formats across different years of NSE PR reports.
        Uses fuzzy matching to find the symbol/name column regardless of header naming.
        """
        df.columns = [c.strip() for c in df.columns]

        mapping = {
            'Index Name': 'Symbol', 'Index Name ': 'Symbol',
            'INDEX_NAME': 'Symbol', 'Index': 'Symbol',
            'INDEX': 'Symbol', 'INDEX NAME': 'Symbol',
            'Index Date': 'Date', 'Date': 'Date', 'DATE': 'Date',
            'INDEX_DATE': 'Date', 'TRADING_DATE': 'Date',
            'Open Index Value': 'Open', 'High Index Value': 'High',
            'Low Index Value': 'Low', 'Closing Index Value': 'Close',
            'OPEN': 'Open', 'HIGH': 'High', 'LOW': 'Low', 'CLOSE': 'Close',
            'Open': 'Open', 'High': 'High', 'Low': 'Low', 'Close': 'Close',
            'Points Change': 'Change', 'Change(%)': 'Percent Change',
            'CHANGE': 'Change', '%CHANGE': 'Percent Change',
            'Volume': 'Volume', 'VOLUME': 'Volume',
            'Turnover (Rs. Cr.)': 'Turnover', 'TURNOVER': 'Turnover',
            'Turnover': 'Turnover',
            'P/E': 'PE', 'P/B': 'PB', 'Div Yield': 'DY',
            'PE': 'PE', 'PB': 'PB', 'DY': 'DY',
        }
        df = df.rename(columns=mapping)

        # If no 'Symbol' column found via mapping, try to detect it
        if 'Symbol' not in df.columns:
            # Look for any column that contains index-like names (first col is often the name)
            for col in df.columns:
                col_lower = col.lower()
                if any(keyword in col_lower for keyword in ['index', 'name', 'symbol']):
                    df = df.rename(columns={col: 'Symbol'})
                    break
            else:
                # Last resort: assume first column is the index name
                first_col = df.columns[0]
                # Check if first column has string values that look like index names
                sample = df[first_col].dropna().astype(str).head(5)
                if sample.str.contains('Nifty|NIFTY|nifty|S&P|CNX|BSE', case=False, regex=True).any():
                    df = df.rename(columns={first_col: 'Symbol'})
                else:
                    # Can't identify symbol column — skip this file
                    return pd.DataFrame()

        # If 'Date' column is missing (often is in PR files), add it
        if 'Date' not in df.columns:
            df['Date'] = date
        else:
            df['Date'] = pd.to_datetime(df['Date'], format='mixed', dayfirst=True, errors='coerce').dt.date

        # Standardize Symbol names
        df['Symbol'] = df['Symbol'].astype(str).str.strip()
        df['Symbol'] = df['Symbol'].replace({
            'Nifty 50': 'NIFTY', 'NIFTY 50': 'NIFTY', 'S&P CNX NIFTY': 'NIFTY',
            'Nifty Bank': 'BANKNIFTY', 'NIFTY BANK': 'BANKNIFTY', 'CNX BANK': 'BANKNIFTY',
            'Nifty Next 50': 'NIFTYNEXT50', 'NIFTY NEXT 50': 'NIFTYNEXT50',
            'Nifty 500': 'NIFTY500', 'NIFTY 500': 'NIFTY500', 'CNX 500': 'NIFTY500',
            'Nifty Midcap 50': 'NIFTYMIDCAP50', 'NIFTY MIDCAP 50': 'NIFTYMIDCAP50',
        })

        # Filter for known indices to avoid trash
        known_indices = ['NIFTY', 'BANKNIFTY', 'NIFTYNEXT50', 'NIFTY500', 'NIFTYMIDCAP50']
        df = df[df['Symbol'].isin(known_indices)].copy()
        
        return df

    # --- Clean functions for new report types ---

    def _clean_short_selling_data(self, df: pd.DataFrame, date: datetime.date) -> pd.DataFrame:
        """Standardizes Short Selling data."""
        df.columns = [c.strip() for c in df.columns]
        mapping = {
            'Name of the Security': 'Symbol', 'SYMBOL': 'Symbol', 'Symbol': 'Symbol',
            'NAME OF THE SECURITY': 'Symbol', 'Security Name': 'Symbol',
            'QTY Short Sold': 'Qty Short Sold', 'QTY OF SHORT SELL': 'Qty Short Sold',
            'Quantity Short Sold': 'Qty Short Sold', 'SHORT_SELL_QTY': 'Qty Short Sold',
            'QTY Short Bought Back': 'Qty Short Buy', 'QTY OF SHORT BUY BACK': 'Qty Short Buy',
            'Quantity of Short Buying': 'Qty Short Buy', 'SHORT_BUY_QTY': 'Qty Short Buy',
            'DATE': 'Date', 'Date': 'Date',
        }
        df = df.rename(columns=mapping)
        if 'Date' not in df.columns:
            df['Date'] = date
        else:
            df['Date'] = pd.to_datetime(df['Date'], format='mixed', dayfirst=True, errors='coerce').dt.date
        if 'Symbol' in df.columns:
            df['Symbol'] = df['Symbol'].astype(str).str.strip()
        for col in ['Qty Short Sold', 'Qty Short Buy']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        return df

    def _clean_volatility_data(self, df: pd.DataFrame, date: datetime.date) -> pd.DataFrame:
        """Standardizes Daily Volatility data."""
        df.columns = [c.strip() for c in df.columns]
        mapping = {
            'Date': 'Date', 'DATE': 'Date', 'TIMESTAMP': 'Date',
            'Symbol': 'Symbol', 'SYMBOL': 'Symbol', 'TckrSymb': 'Symbol',
            'Underlying': 'Symbol', 'UNDERLYING': 'Symbol',
            '%Change': 'Pct Change', 'Pct Change': 'Pct Change',
            'Daily Volatility': 'Daily Volatility', 'DAILY_VLTY': 'Daily Volatility',
            'Annualised Volatility': 'Annl Volatility', 'ANNL_VLTY': 'Annl Volatility',
            'Close Price': 'Close', 'CLOSE': 'Close', 'ClsPric': 'Close',
            'Prev Close': 'Prev Close', 'PREV_CL': 'Prev Close',
        }
        df = df.rename(columns=mapping)
        if 'Date' not in df.columns:
            df['Date'] = date
        else:
            df['Date'] = pd.to_datetime(df['Date'], format='mixed', dayfirst=True, errors='coerce').dt.date
        if 'Symbol' in df.columns:
            df['Symbol'] = df['Symbol'].astype(str).str.strip()
        for col in ['Daily Volatility', 'Annl Volatility', 'Pct Change', 'Close', 'Prev Close']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        return df

    def _clean_market_activity_data(self, df: pd.DataFrame, date: datetime.date) -> pd.DataFrame:
        """Standardizes Market Activity Report data.

        This is market-wide data. If no symbol/category column exists,
        stored under Symbol='MARKET'.
        """
        df.columns = [c.strip() for c in df.columns]
        mapping = {
            'Category': 'Symbol', 'CATEGORY': 'Symbol', 'Segment': 'Symbol',
            'SEGMENT': 'Symbol', 'Market Type': 'Symbol', 'MARKET_TYPE': 'Symbol',
        }
        df = df.rename(columns=mapping)
        if 'Symbol' not in df.columns:
            df['Symbol'] = 'MARKET'
        else:
            df['Symbol'] = df['Symbol'].astype(str).str.strip()
        df['Date'] = date
        return df

    def _clean_price_band_data(self, df: pd.DataFrame, date: datetime.date) -> pd.DataFrame:
        """Standardizes Price Band changes data."""
        df.columns = [c.strip() for c in df.columns]
        mapping = {
            'Symbol': 'Symbol', 'SYMBOL': 'Symbol', 'TckrSymb': 'Symbol',
            'Date': 'Date', 'DATE': 'Date',
            'Series': 'Series', 'SERIES': 'Series', 'SctySrs': 'Series',
            'Old Band': 'Old Band', 'FROM_BAND': 'Old Band',
            'New Band': 'New Band', 'TO_BAND': 'New Band',
            'Applicable From': 'Effective Date', 'EFF_DATE': 'Effective Date',
        }
        df = df.rename(columns=mapping)
        if 'Date' not in df.columns:
            df['Date'] = date
        else:
            df['Date'] = pd.to_datetime(df['Date'], format='mixed', dayfirst=True, errors='coerce').dt.date
        if 'Symbol' in df.columns:
            df['Symbol'] = df['Symbol'].astype(str).str.strip()
        return df

    def _clean_pe_ratio_data(self, df: pd.DataFrame, date: datetime.date) -> pd.DataFrame:
        """Standardizes PE Ratio data."""
        df.columns = [c.strip() for c in df.columns]
        mapping = {
            'Index Name': 'Symbol', 'INDEX_NAME': 'Symbol', 'Symbol': 'Symbol',
            'INDEX NAME': 'Symbol', 'Index': 'Symbol',
            'Date': 'Date', 'DATE': 'Date',
            'P/E': 'PE', 'P/B': 'PB', 'Div Yield': 'DY',
            'PE': 'PE', 'PB': 'PB', 'DY': 'DY',
        }
        df = df.rename(columns=mapping)
        if 'Date' not in df.columns:
            df['Date'] = date
        else:
            df['Date'] = pd.to_datetime(df['Date'], format='mixed', dayfirst=True, errors='coerce').dt.date
        if 'Symbol' in df.columns:
            df['Symbol'] = df['Symbol'].astype(str).str.strip()
        for col in ['PE', 'PB', 'DY']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        return df

    def _clean_corp_bonds_data(self, df: pd.DataFrame, date: datetime.date) -> pd.DataFrame:
        """Standardizes Corporate Bonds Traded Report data."""
        df.columns = [c.strip() for c in df.columns]
        mapping = {
            'ISIN': 'Symbol', 'Isin': 'Symbol', 'ISIN No': 'Symbol', 'ISIN No.': 'Symbol',
            'Security': 'Security Name', 'SECURITY': 'Security Name',
            'Security Description': 'Security Name',
            'Date': 'Date', 'DATE': 'Date', 'Trade Date': 'Date', 'TRADE_DATE': 'Date',
            'TRADED_VALUE': 'Traded Value', 'Traded Value': 'Traded Value',
            'TRADED_QTY': 'Traded Qty', 'Traded Quantity': 'Traded Qty',
            'No. of Trades': 'No of Trades', 'NUM_TRADES': 'No of Trades',
        }
        df = df.rename(columns=mapping)
        if 'Date' not in df.columns:
            df['Date'] = date
        else:
            df['Date'] = pd.to_datetime(df['Date'], format='mixed', dayfirst=True, errors='coerce').dt.date
        if 'Symbol' in df.columns:
            df['Symbol'] = df['Symbol'].astype(str).str.strip()
        for col in ['Traded Value', 'Traded Qty', 'No of Trades']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        return df

    def _clean_delivery_data(self, df: pd.DataFrame, date: datetime.date) -> pd.DataFrame:
        """Standardizes Security-wise Delivery Positions data.

        DAT format has: Record Type, Symbol, Series, Qty Traded,
        Deliverable Qty, % of Deliverable to Traded.
        Record type 20 = data rows.
        """
        df.columns = [c.strip() for c in df.columns]

        # Filter for data rows if Record Type column exists
        for col in df.columns:
            col_lower = col.lower()
            if 'record' in col_lower or col_lower in ('rec type', 'rec_type', 'rectype'):
                df[col] = pd.to_numeric(df[col], errors='coerce')
                df = df[df[col] == 20].copy()
                df = df.drop(columns=[col])
                break

        mapping = {
            'SYMBOL': 'Symbol', 'Symbol': 'Symbol', 'NAME OF SECURITY': 'Symbol',
            'TckrSymb': 'Symbol', 'NAME': 'Symbol',
            'SERIES': 'Series', 'Series': 'Series', 'SctySrs': 'Series',
            'QUANTITY TRADED': 'Qty Traded', 'QTY_TRADED': 'Qty Traded',
            'Qty Traded': 'Qty Traded', 'TtlTradgVol': 'Qty Traded',
            'DELIVERABLE QTY': 'Deliverable Qty', 'DELIVERABLE_QTY': 'Deliverable Qty',
            'Deliverable Qty(Demat)': 'Deliverable Qty', 'DlvrblQty': 'Deliverable Qty',
            'Deliverable Qty': 'Deliverable Qty',
            '% OF DELIVERABLE QTY TO TRADED QTY': 'Delivery Pct',
            'DELV_PER': 'Delivery Pct', 'DELV_PERC': 'Delivery Pct',
            'Delivery Pct': 'Delivery Pct', '% Dly Qt to Traded Qty': 'Delivery Pct',
            'PctgDlvryQty': 'Delivery Pct',
            'DATE': 'Date', 'Date': 'Date', 'TIMESTAMP': 'Date',
        }
        df = df.rename(columns=mapping)

        if 'Date' not in df.columns:
            df['Date'] = date
        else:
            df['Date'] = pd.to_datetime(df['Date'], format='mixed', dayfirst=True, errors='coerce').dt.date
        if 'Symbol' in df.columns:
            df['Symbol'] = df['Symbol'].astype(str).str.strip()
        for col in ['Qty Traded', 'Deliverable Qty', 'Delivery Pct']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        return df

    def update_processed_data(self, df: pd.DataFrame, target_dir: Path, group_col: str = 'Symbol'):
        """Appends new data to per-symbol Parquet files."""
        if df is None or df.empty:
            return

        for name, group in df.groupby(group_col):
            file_path = target_dir / f"{name}.parquet"
            if file_path.exists():
                existing_df = pd.read_parquet(file_path, engine='pyarrow')
                # pd.concat automatically handles differing columns
                combined_df = pd.concat([existing_df, group], ignore_index=True)
                dedup_cols = ['Date']
                for extra_key in ['Symbol', 'Instrument', 'Expiry', 'Strike Price', 'Option type']:
                    if extra_key in combined_df.columns:
                        dedup_cols.append(extra_key)
                combined_df = combined_df.drop_duplicates(subset=dedup_cols, keep='last')
                combined_df = combined_df.sort_values('Date')
                combined_df.to_parquet(file_path, engine='pyarrow', compression='zstd', index=False)
            else:
                group = group.sort_values('Date')
                group.to_parquet(file_path, engine='pyarrow', compression='zstd', index=False)

    BATCH_MERGE_SIZE = 50  # Number of raw files to read and merge at a time

    def merge_raw_to_processed(self, raw_dir: Path, raw_prefix: str, target_dir: Path, label: str, group_col: str = 'Symbol'):
        """Merges raw day-parquet files from disk into per-symbol processed files.
        
        Reads raw files from disk in small batches to avoid OOM.
        After successfully merging a batch, the raw files are left on disk
        as a cache (they'll be skipped on next download run).
        """
        raw_files = sorted(raw_dir.glob(f"{raw_prefix}_*.parquet"))
        if not raw_files:
            print(f"  [{label}] No raw files to merge.", flush=True)
            return

        # Determine which raw files are newer than the last processed date
        last_processed = self.get_last_date(target_dir)
        files_to_merge = []
        for f in raw_files:
            # Extract date from filename like fo_20100503.parquet
            try:
                date_str = f.stem.split('_', 1)[1]  # "20100503"
                file_date = datetime.datetime.strptime(date_str, '%Y%m%d').date()
                if file_date > last_processed:
                    files_to_merge.append(f)
            except (IndexError, ValueError):
                files_to_merge.append(f)  # Include if we can't parse the date

        if not files_to_merge:
            print(f"  [{label}] All raw files already merged.", flush=True)
            return

        total_files = len(files_to_merge)
        batch_size = self.BATCH_MERGE_SIZE
        num_batches = (total_files + batch_size - 1) // batch_size
        last_progress_time = time.time()
        print(f"  [{label}] Merging {total_files} raw files in {num_batches} batches...", flush=True)

        for batch_idx in range(num_batches):
            start = batch_idx * batch_size
            end = min(start + batch_size, total_files)
            batch_files = files_to_merge[start:end]

            # Read batch of raw files from disk
            batch_dfs = []
            for f in batch_files:
                try:
                    df = pd.read_parquet(f, engine='pyarrow')
                    batch_dfs.append(df)
                except Exception as e:
                    print(f"  [{label}] Error reading raw file {f.name}: {e}")

            if not batch_dfs:
                continue

            combined_new = pd.concat(batch_dfs, ignore_index=True)
            del batch_dfs  # Free list of DFs

            if combined_new.empty:
                del combined_new
                continue

            for name, group in combined_new.groupby(group_col):
                file_path = target_dir / f"{name}.parquet"
                if file_path.exists():
                    existing_df = pd.read_parquet(file_path, engine='pyarrow')
                    # pd.concat automatically handles differing columns (new cols get NaN in old rows)
                    merged = pd.concat([existing_df, group], ignore_index=True)
                    # Determine dedup key: use all key columns that exist
                    dedup_cols = ['Date']
                    for extra_key in ['Symbol', 'Instrument', 'Expiry', 'Strike Price', 'Option type']:
                        if extra_key in merged.columns:
                            dedup_cols.append(extra_key)
                    merged = merged.drop_duplicates(subset=dedup_cols, keep='last')
                    del existing_df
                else:
                    merged = group
                merged = merged.sort_values('Date')
                merged.to_parquet(file_path, engine='pyarrow', compression='zstd', index=False)
                del merged

            del combined_new

            now = time.time()
            if now - last_progress_time >= 10 or (batch_idx + 1) == num_batches:
                print(f"  [{label}] Merged batch {batch_idx + 1}/{num_batches} (files {start + 1}-{end} of {total_files})", flush=True)
                last_progress_time = now

    def get_last_date(self, processed_dir: Path) -> datetime.date:
        """Finds the latest date across all processed files."""
        files = list(processed_dir.glob("*.parquet"))
        if not files:
            return DEFAULT_START_DATE
        
        # Check a few major/well-known files for efficiency
        major_files = [processed_dir / "NIFTY.parquet", processed_dir / "SBIN.parquet",
                       processed_dir / "RELIANCE.parquet", processed_dir / "MARKET.parquet"]
        last_dates = []
        for f in major_files:
            if f.exists():
                try:
                    df = pd.read_parquet(f, engine='pyarrow', columns=['Date'])
                    last_dates.append(df['Date'].max())
                except:
                    pass
        
        if last_dates:
            return max(last_dates)

        # Fallback: sample a few available files
        for f in files[:5]:
            try:
                df = pd.read_parquet(f, engine='pyarrow', columns=['Date'])
                last_dates.append(df['Date'].max())
            except:
                pass

        if last_dates:
            return max(last_dates)

        return DEFAULT_START_DATE

    # --- Concurrent download helpers ---
    MAX_WORKERS = 4  # Max parallel downloads (be respectful to NSE servers)
    DOWNLOAD_DELAY = 0.3  # Delay between scheduling downloads (seconds)

    def _download_day_cm(self, day: datetime.date) -> tuple:
        """Download CM bhavcopy for one day. Returns (day, df_or_None)."""
        df = self.download_cm_bhavcopy(day)
        return (day, df)

    def _download_day_fo(self, day: datetime.date) -> tuple:
        """Download FO bhavcopy for one day. Returns (day, df_or_None)."""
        df = self.download_fo_bhavcopy(day)
        return (day, df)

    def _download_day_idx(self, day: datetime.date) -> tuple:
        """Download Indices report for one day. Returns (day, df_or_None)."""
        df = self.download_indices_report(day)
        return (day, df)

    def _download_day_ss(self, day: datetime.date) -> tuple:
        df = self.download_short_selling(day)
        return (day, df)

    def _download_day_vol(self, day: datetime.date) -> tuple:
        df = self.download_daily_volatility(day)
        return (day, df)

    def _download_day_ma(self, day: datetime.date) -> tuple:
        df = self.download_market_activity(day)
        return (day, df)

    def _download_day_pb(self, day: datetime.date) -> tuple:
        df = self.download_price_band(day)
        return (day, df)

    def _download_day_pe(self, day: datetime.date) -> tuple:
        df = self.download_pe_ratio(day)
        return (day, df)

    def _download_day_cb(self, day: datetime.date) -> tuple:
        df = self.download_corp_bonds(day)
        return (day, df)

    def _download_day_del(self, day: datetime.date) -> tuple:
        df = self.download_delivery_positions(day)
        return (day, df)

    def _concurrent_download(self, days, download_fn, raw_dir, raw_prefix, label):
        """Downloads data for multiple days, newest first, skipping already-downloaded days.

        Downloads in reverse chronological order (newest first) in batches.
        If 10 consecutive days return HTTP 403, assumes older data is not available
        and stops going further back.
        """
        if not days:
            print(f"  No new {label} days to download.", flush=True)
            return

        # Skip days that already have raw files on disk
        days_to_download = []
        skipped = 0
        for day in days:
            raw_file = raw_dir / f"{raw_prefix}_{day.strftime('%Y%m%d')}.parquet"
            if raw_file.exists():
                skipped += 1
            else:
                days_to_download.append(day)

        if skipped > 0:
            print(f"  [{label}] Skipping {skipped} days (already downloaded), {len(days_to_download)} remaining.", flush=True)

        if not days_to_download:
            print(f"  [{label}] All days already downloaded.", flush=True)
            return

        # Reverse: process newest days first
        days_to_download = list(reversed(days_to_download))

        total = len(days_to_download)
        done_count = 0
        success_count = 0
        failed_days = []
        consecutive_403 = 0
        MAX_CONSECUTIVE_403 = 10
        stopped_early = False
        last_progress_time = time.time()
        print(f"  Downloading {total} days of {label} data (newest first, {self.MAX_WORKERS} workers)...", flush=True)

        # Process in batches to allow concurrent downloads while tracking 403 streaks
        BATCH_SIZE = self.MAX_WORKERS * 3  # e.g. 12 days per batch
        for batch_start in range(0, total, BATCH_SIZE):
            if stopped_early:
                break

            batch_end = min(batch_start + BATCH_SIZE, total)
            batch_days = days_to_download[batch_start:batch_end]

            with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
                futures = {executor.submit(download_fn, day): day for day in batch_days}

                # Collect results keyed by day
                batch_results = {}  # day -> ('ok', df) | ('403',) | ('fail',)
                for future in as_completed(futures):
                    day = futures[future]
                    done_count += 1
                    try:
                        _, df = future.result()
                        if df is not None:
                            try:
                                df.to_parquet(
                                    raw_dir / f"{raw_prefix}_{day.strftime('%Y%m%d')}.parquet",
                                    engine='pyarrow', compression='zstd', index=False
                                )
                            except (OSError, IOError) as e:
                                print(f"  [{label}] Failed to save raw file for {day}: {e}")
                            batch_results[day] = ('ok', df)
                            success_count += 1
                        else:
                            batch_results[day] = ('fail',)
                            failed_days.append(day)
                    except HTTP403Error:
                        batch_results[day] = ('403',)
                        failed_days.append(day)
                    except Exception as e:
                        print(f"  [{label}] Error for {day}: {type(e).__name__}: {e}")
                        batch_results[day] = ('fail',)
                        failed_days.append(day)

            # Check consecutive 403 streak in date order (newest first = batch_days order)
            for day in batch_days:
                result = batch_results.get(day, ('fail',))
                if result[0] == '403':
                    consecutive_403 += 1
                    if consecutive_403 >= MAX_CONSECUTIVE_403:
                        remaining = total - done_count
                        print(f"  [{label}] {MAX_CONSECUTIVE_403} consecutive 403 errors — "
                              f"older data not available. Skipping {remaining} remaining days.", flush=True)
                        stopped_early = True
                        break
                else:
                    consecutive_403 = 0  # Reset on any non-403 result

            now = time.time()
            if now - last_progress_time >= 10 or done_count == total or stopped_early:
                pct = done_count * 100 // total
                print(f"  [{label}] {done_count}/{total} ({pct}%) days processed, "
                      f"{success_count} successful, {len(failed_days)} failed", flush=True)
                last_progress_time = now

        final_failed = done_count - success_count
        msg = f"  [{label}] Download complete: {success_count}/{done_count} days successful."
        if stopped_early:
            msg += f" (stopped early — old data unavailable)"
        elif final_failed > 0:
            msg += f" ({final_failed} days failed)"
        print(msg, flush=True)

    def run_incremental_update(self):
        """Main loop to download and update data incrementally.
        
        Performance optimizations vs original:
        - Concurrent downloads with ThreadPoolExecutor (4 workers)
        - Batch parquet merges: reads/writes each symbol file only ONCE instead
          of once per trading day, reducing I/O from O(days×symbols) to O(symbols)
        - Reduced inter-request sleep from 1s to 0.3s stagger
        """
        print("Starting Incremental Update...")
        t0 = time.time()

        # 1. Equity — Download then merge from raw files
        last_cm_date = self.get_last_date(EQUITY_PROCESSED)
        print(f"Last Equity Date: {last_cm_date}")
        cm_days = self.get_trading_days(last_cm_date + datetime.timedelta(days=1), datetime.date.today())
        self._concurrent_download(cm_days, self._download_day_cm, EQUITY_RAW, "cm", "Equity")
        self.merge_raw_to_processed(EQUITY_RAW, "cm", EQUITY_PROCESSED, "Equity")
        print(f"  Equity update done.", flush=True)

        # 2. Derivatives — Download then merge from raw files
        last_fo_date = self.get_last_date(DERIVATIVES_PROCESSED)
        print(f"Last Derivatives Date: {last_fo_date}")
        fo_days = self.get_trading_days(last_fo_date + datetime.timedelta(days=1), datetime.date.today())
        self._concurrent_download(fo_days, self._download_day_fo, DERIVATIVES_RAW, "fo", "Derivatives")
        self.merge_raw_to_processed(DERIVATIVES_RAW, "fo", DERIVATIVES_PROCESSED, "Derivatives")
        print(f"  Derivatives update done.", flush=True)

        # 3. Indices — Download then merge from raw files
        last_idx_date = self.get_last_date(INDICES_PROCESSED)
        print(f"Last Indices Date: {last_idx_date}")
        idx_days = self.get_trading_days(last_idx_date + datetime.timedelta(days=1), datetime.date.today())
        self._concurrent_download(idx_days, self._download_day_idx, INDICES_RAW, "idx", "Indices")
        self.merge_raw_to_processed(INDICES_RAW, "idx", INDICES_PROCESSED, "Indices")
        print(f"  Indices update done.", flush=True)

        # 4. Short Selling
        last_ss_date = self.get_last_date(SHORTSELLING_PROCESSED)
        print(f"Last Short Selling Date: {last_ss_date}")
        ss_days = self.get_trading_days(last_ss_date + datetime.timedelta(days=1), datetime.date.today())
        self._concurrent_download(ss_days, self._download_day_ss, SHORTSELLING_RAW, "ss", "Short Selling")
        self.merge_raw_to_processed(SHORTSELLING_RAW, "ss", SHORTSELLING_PROCESSED, "Short Selling")
        print(f"  Short Selling update done.", flush=True)

        # 5. Daily Volatility
        last_vol_date = self.get_last_date(VOLATILITY_PROCESSED)
        print(f"Last Volatility Date: {last_vol_date}")
        vol_days = self.get_trading_days(last_vol_date + datetime.timedelta(days=1), datetime.date.today())
        self._concurrent_download(vol_days, self._download_day_vol, VOLATILITY_RAW, "vol", "Volatility")
        self.merge_raw_to_processed(VOLATILITY_RAW, "vol", VOLATILITY_PROCESSED, "Volatility")
        print(f"  Volatility update done.", flush=True)

        # 6. Market Activity Report
        last_ma_date = self.get_last_date(MARKETACTIVITY_PROCESSED)
        print(f"Last Market Activity Date: {last_ma_date}")
        ma_days = self.get_trading_days(last_ma_date + datetime.timedelta(days=1), datetime.date.today())
        self._concurrent_download(ma_days, self._download_day_ma, MARKETACTIVITY_RAW, "ma", "Market Activity")
        self.merge_raw_to_processed(MARKETACTIVITY_RAW, "ma", MARKETACTIVITY_PROCESSED, "Market Activity")
        print(f"  Market Activity update done.", flush=True)

        # 7. Price Band Changes
        last_pb_date = self.get_last_date(PRICEBAND_PROCESSED)
        print(f"Last Price Band Date: {last_pb_date}")
        pb_days = self.get_trading_days(last_pb_date + datetime.timedelta(days=1), datetime.date.today())
        self._concurrent_download(pb_days, self._download_day_pb, PRICEBAND_RAW, "pb", "Price Band")
        self.merge_raw_to_processed(PRICEBAND_RAW, "pb", PRICEBAND_PROCESSED, "Price Band")
        print(f"  Price Band update done.", flush=True)

        # 8. PE Ratio
        last_pe_date = self.get_last_date(PERATIO_PROCESSED)
        print(f"Last PE Ratio Date: {last_pe_date}")
        pe_days = self.get_trading_days(last_pe_date + datetime.timedelta(days=1), datetime.date.today())
        self._concurrent_download(pe_days, self._download_day_pe, PERATIO_RAW, "pe", "PE Ratio")
        self.merge_raw_to_processed(PERATIO_RAW, "pe", PERATIO_PROCESSED, "PE Ratio")
        print(f"  PE Ratio update done.", flush=True)

        # 9. Corporate Bonds
        last_cb_date = self.get_last_date(CORPBONDS_PROCESSED)
        print(f"Last Corporate Bonds Date: {last_cb_date}")
        cb_days = self.get_trading_days(last_cb_date + datetime.timedelta(days=1), datetime.date.today())
        self._concurrent_download(cb_days, self._download_day_cb, CORPBONDS_RAW, "cb", "Corporate Bonds")
        self.merge_raw_to_processed(CORPBONDS_RAW, "cb", CORPBONDS_PROCESSED, "Corporate Bonds")
        print(f"  Corporate Bonds update done.", flush=True)

        # 10. Security-wise Delivery Positions
        last_del_date = self.get_last_date(DELIVERY_PROCESSED)
        print(f"Last Delivery Positions Date: {last_del_date}")
        del_days = self.get_trading_days(last_del_date + datetime.timedelta(days=1), datetime.date.today())
        self._concurrent_download(del_days, self._download_day_del, DELIVERY_RAW, "del", "Delivery Positions")
        self.merge_raw_to_processed(DELIVERY_RAW, "del", DELIVERY_PROCESSED, "Delivery Positions")
        print(f"  Delivery Positions update done.", flush=True)

        elapsed = time.time() - t0
        print(f"Update Complete. Total time: {elapsed:.1f}s")

def main():
    downloader = NSEMarketDataDownloader()
    downloader.run_incremental_update()

if __name__ == '__main__':
    main()
