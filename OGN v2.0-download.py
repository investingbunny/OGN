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

# Holiday List (Simplified - ideally fetch from NSE)
HOLIDAYS = [
    '2026-01-26', '2026-03-06', '2026-03-30', '2026-04-10', '2026-04-14',
    '2026-05-01', '2026-10-02', '2026-10-21', '2026-11-05', '2026-12-25'
]
HOLIDAYS = pd.to_datetime(HOLIDAYS).date

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
        for path in [EQUITY_RAW, EQUITY_PROCESSED, DERIVATIVES_RAW, DERIVATIVES_PROCESSED, INDICES_RAW, INDICES_PROCESSED]:
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

                elif r.status_code in (403, 401):
                    # Forbidden/Unauthorized — likely session expired or IP blocked
                    print(f"  HTTP {r.status_code} for {url.split('?')[0]}... "
                          f"re-initializing session (attempt {attempt+1}/{max_retries}).")
                    self._init_session()
                    time.sleep(delay + 2)  # Extra pause for auth issues

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
                target_csv = f"Pr{date.strftime('%d%m%y')}.csv"
                if target_csv not in z.namelist():
                    # Sometimes casing differs
                    target_csv = [n for n in z.namelist() if n.lower() == target_csv.lower()][0]

                with z.open(target_csv) as f:
                    # Index PR files often have issues with trailers or leading spaces
                    df = pd.read_csv(f, skipinitialspace=True)
                    # The first ~57 lines are usually the indices
                    df = df.head(100) # Safety margin
                    return self._clean_indices_data(df, date)
        except Exception as e:
            print(f"Error parsing Indices PR for {date}: {e}")
            return None

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
        """Standardizes Indices data from PR report."""
        # Index PR reports are a bit messy.
        # Typically: Index Name, Open, High, Low, Close, Prev Close, Change, % Change, Volume, Turnover, PE, PB, DY
        # We need to find the right columns.
        df.columns = [c.strip() for c in df.columns]

        mapping = {
            'Index Name': 'Symbol', 'Index Name ': 'Symbol',
            'INDEX_NAME': 'Symbol', 'Index': 'Symbol',
            'Index Date': 'Date', 'Date': 'Date',
            'Open Index Value': 'Open', 'High Index Value': 'High',
            'Low Index Value': 'Low', 'Closing Index Value': 'Close',
            'Points Change': 'Change', 'Change(%)': 'Percent Change',
            'Volume': 'Volume', 'Turnover (Rs. Cr.)': 'Turnover'
        }
        df = df.rename(columns=mapping)
        
        # If 'Date' column is missing (often is in PR files), add it
        if 'Date' not in df.columns:
            df['Date'] = date
        else:
            df['Date'] = pd.to_datetime(df['Date']).dt.date

        # Standardize Symbol names
        if 'Symbol' in df.columns:
            df['Symbol'] = df['Symbol'].str.strip()
            df['Symbol'] = df['Symbol'].replace({'Nifty 50': 'NIFTY', 'Nifty Bank': 'BANKNIFTY'})

        # Filter for known indices to avoid trash
        known_indices = ['NIFTY', 'BANKNIFTY', 'Nifty Next 50', 'Nifty 500', 'Nifty Midcap 50']
        df = df[df['Symbol'].isin(known_indices)].copy()
        
        return df

    def update_processed_data(self, df: pd.DataFrame, target_dir: Path, group_col: str = 'Symbol'):
        """Appends new data to per-symbol Parquet files."""
        if df is None or df.empty:
            return

        for name, group in df.groupby(group_col):
            file_path = target_dir / f"{name}.parquet"
            if file_path.exists():
                existing_df = pd.read_parquet(file_path, engine='pyarrow')
                # Merge and drop duplicates
                combined_df = pd.concat([existing_df, group]).drop_duplicates(subset=['Date'], keep='last')
                combined_df = combined_df.sort_values('Date')
                combined_df.to_parquet(file_path, engine='pyarrow', compression='zstd', index=False)
            else:
                group = group.sort_values('Date')
                group.to_parquet(file_path, engine='pyarrow', compression='zstd', index=False)

    def batch_update_processed_data(self, all_dfs: List[pd.DataFrame], target_dir: Path, group_col: str = 'Symbol'):
        """Batch-merges multiple days of data into per-symbol Parquet files in one pass.
        
        Instead of reading/writing each symbol file once per day, this concatenates
        ALL new data first, then reads each symbol file only once, merges, and writes once.
        This reduces I/O from (days × symbols) to just (symbols).
        """
        if not all_dfs:
            return

        combined_new = pd.concat(all_dfs, ignore_index=True)
        if combined_new.empty:
            return

        groups = list(combined_new.groupby(group_col))
        total_symbols = len(groups)
        done_symbols = 0
        last_progress_time = time.time()
        label = target_dir.parent.name  # e.g. Equity, Derivatives, Indices

        for name, group in groups:
            file_path = target_dir / f"{name}.parquet"
            if file_path.exists():
                existing_df = pd.read_parquet(file_path, engine='pyarrow')
                merged = pd.concat([existing_df, group]).drop_duplicates(subset=['Date'], keep='last')
            else:
                merged = group
            merged = merged.sort_values('Date')
            merged.to_parquet(file_path, engine='pyarrow', compression='zstd', index=False)
            done_symbols += 1
            now = time.time()
            if now - last_progress_time >= 10 or done_symbols == total_symbols:
                pct = done_symbols * 100 // total_symbols
                print(f"  [{label}] Merged {done_symbols}/{total_symbols} ({pct}%) symbols...")
                last_progress_time = now

    def get_last_date(self, processed_dir: Path) -> datetime.date:
        """Finds the latest date across all processed files."""
        files = list(processed_dir.glob("*.parquet"))
        if not files:
            return DEFAULT_START_DATE
        
        # Check a few major files for efficiency
        major_files = [processed_dir / "NIFTY.parquet", processed_dir / "SBIN.parquet", processed_dir / "RELIANCE.parquet"]
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

    def _concurrent_download(self, days, download_fn, raw_dir, raw_prefix, label):
        """Downloads data for multiple days concurrently and returns list of DataFrames.

        Uses ThreadPoolExecutor for parallel HTTP requests, saves raw files as they
        arrive, and returns all successful DataFrames for batch processing.
        Failed days are retried once with reduced concurrency.
        """
        all_dfs = []
        if not days:
            return all_dfs

        total = len(days)
        done_count = 0
        success_count = 0
        failed_days = []
        last_progress_time = time.time()
        print(f"  Downloading {total} days of {label} data ({self.MAX_WORKERS} workers)...")

        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            futures = {}
            for day in days:
                future = executor.submit(download_fn, day)
                futures[future] = day
                time.sleep(self.DOWNLOAD_DELAY)  # Stagger submissions to avoid burst

            for future in as_completed(futures):
                day = futures[future]
                done_count += 1
                try:
                    _, df = future.result()
                    if df is not None:
                        # Save raw file
                        try:
                            df.to_parquet(
                                raw_dir / f"{raw_prefix}_{day.strftime('%Y%m%d')}.parquet",
                                engine='pyarrow', compression='zstd', index=False
                            )
                        except (OSError, IOError) as e:
                            print(f"  [{label}] Failed to save raw file for {day}: {e}")
                        all_dfs.append(df)
                        success_count += 1
                    else:
                        failed_days.append(day)
                    now = time.time()
                    if now - last_progress_time >= 10 or done_count == total:
                        pct = done_count * 100 // total
                        elapsed = now - last_progress_time
                        print(f"  [{label}] {done_count}/{total} ({pct}%) days processed, {success_count} successful, {len(failed_days)} failed")
                        last_progress_time = now
                except Exception as e:
                    print(f"  [{label}] Error for {day}: {type(e).__name__}: {e}")
                    failed_days.append(day)

        # --- Retry failed days with reduced concurrency ---
        if failed_days:
            retry_count = len(failed_days)
            print(f"  [{label}] Retrying {retry_count} failed days (1 worker, slower pace)...")
            self._init_session()  # Fresh session before retries
            time.sleep(2)

            for day in failed_days:
                try:
                    _, df = download_fn(day)
                    if df is not None:
                        try:
                            df.to_parquet(
                                raw_dir / f"{raw_prefix}_{day.strftime('%Y%m%d')}.parquet",
                                engine='pyarrow', compression='zstd', index=False
                            )
                        except (OSError, IOError) as e:
                            print(f"  [{label}] Failed to save raw file for {day} on retry: {e}")
                        all_dfs.append(df)
                    time.sleep(1)  # Slower pace for retries
                except Exception as e:
                    print(f"  [{label}] Retry also failed for {day}: {type(e).__name__}: {e}")

        success = len(all_dfs)
        final_failed = total - success
        msg = f"  [{label}] Download complete: {success}/{total} days successful."
        if final_failed > 0:
            msg += f" ({final_failed} days failed even after retry)"
        print(msg)
        return all_dfs

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

        # 1. Equity
        last_cm_date = self.get_last_date(EQUITY_PROCESSED)
        print(f"Last Equity Date: {last_cm_date}")
        cm_days = self.get_trading_days(last_cm_date + datetime.timedelta(days=1), datetime.date.today())

        cm_dfs = self._concurrent_download(cm_days, self._download_day_cm, EQUITY_RAW, "cm", "Equity")
        print(f"  Merging {len(cm_dfs)} days into per-symbol Equity files...")
        self.batch_update_processed_data(cm_dfs, EQUITY_PROCESSED)
        print(f"  Equity update done.")

        # 2. Derivatives
        last_fo_date = self.get_last_date(DERIVATIVES_PROCESSED)
        print(f"Last Derivatives Date: {last_fo_date}")
        fo_days = self.get_trading_days(last_fo_date + datetime.timedelta(days=1), datetime.date.today())

        fo_dfs = self._concurrent_download(fo_days, self._download_day_fo, DERIVATIVES_RAW, "fo", "Derivatives")
        print(f"  Merging {len(fo_dfs)} days into per-symbol Derivatives files...")
        self.batch_update_processed_data(fo_dfs, DERIVATIVES_PROCESSED)
        print(f"  Derivatives update done.")

        # 3. Indices
        last_idx_date = self.get_last_date(INDICES_PROCESSED)
        print(f"Last Indices Date: {last_idx_date}")
        idx_days = self.get_trading_days(last_idx_date + datetime.timedelta(days=1), datetime.date.today())

        idx_dfs = self._concurrent_download(idx_days, self._download_day_idx, INDICES_RAW, "idx", "Indices")
        print(f"  Merging {len(idx_dfs)} days into per-symbol Indices files...")
        self.batch_update_processed_data(idx_dfs, INDICES_PROCESSED)
        print(f"  Indices update done.")

        elapsed = time.time() - t0
        print(f"Update Complete. Total time: {elapsed:.1f}s")

def main():
    downloader = NSEMarketDataDownloader()
    downloader.run_incremental_update()

if __name__ == '__main__':
    main()
