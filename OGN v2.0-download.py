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
import json
import time
import random
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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "sec-ch-ua": '"Chromium";v="120", "Google Chrome";v="120", "Not=A?Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
}

# Rotate User-Agent to avoid detection as a bot
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

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
WDM_RAW = DATA_ROOT / "WDM" / "Raw"
WDM_PROCESSED = DATA_ROOT / "WDM" / "Processed"

# Budget day (Feb 1) is always attempted even if it falls on a weekend.
# Actual market holidays (Republic Day, Holi, etc.) vary each year and are
# handled dynamically: a genuine 404 creates a .nodata marker so the day
# is never retried.  Weekend dates (Feb 1 on Sat/Sun) get a .nodata_weekend
# marker without making any HTTP request.  Transient failures (403, timeouts,
# etc.) do NOT create markers so they are retried on the next run.
BUDGET_DAY = (2, 1)  # (month, day) — always try this date


class HTTP403Error(Exception):
    """Raised when the server returns 403 Forbidden (data not available)."""
    pass


class DownloadFailedError(Exception):
    """Raised when download fails due to transient/non-404 errors.

    Unlike HTTP403Error (access denied) or a None return (genuine 404),
    this indicates the download could not be completed but the data may
    still exist.  Days that fail with this error should NOT be marked
    with .nodata so they can be retried on the next run.
    """
    pass


class NSEMarketDataDownloader:
    """Class to handle robust downloading and storage of NSE market data."""

    MAX_WORKERS = 4  # Concurrent download threads
    REQUEST_DELAY = 0.15  # Minimum seconds between requests (per-thread)
    BATCH_COOLDOWN = 0.5  # Seconds to pause between download batches
    SESSION_REFRESH_AFTER = 150  # Re-init session after this many requests

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._session_lock = threading.Lock()
        self._throttle_lock = threading.Lock()
        self._last_request_time = 0.0
        self._request_count = 0
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
                # Visit main page first to get initial cookies (like a real browser)
                init_headers = {
                    "sec-fetch-dest": "document",
                    "sec-fetch-mode": "navigate",
                    "sec-fetch-site": "none",
                    "sec-fetch-user": "?1",
                }
                self.session.get(BASE_URL, timeout=15, headers=init_headers)
                time.sleep(1)  # Small delay like a real user
                init_headers["sec-fetch-site"] = "same-origin"
                self.session.get(ALL_REPORTS_URL, timeout=15, headers=init_headers)
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
                     CORPBONDS_RAW, CORPBONDS_PROCESSED, DELIVERY_RAW, DELIVERY_PROCESSED,
                     WDM_RAW, WDM_PROCESSED]:
            path.mkdir(parents=True, exist_ok=True)

    def get_trading_days(self, start_date: datetime.date, end_date: datetime.date) -> List[datetime.date]:
        """Returns all calendar days in the range.

        Weekend days are included so that _concurrent_download can create
        .nodata_weekend markers for them (skipping HTTP requests).
        Actual market holidays are handled via .nodata markers — a genuine
        404 response creates a marker so the day is never retried.
        """
        all_days = pd.date_range(start=start_date, end=end_date, freq='D')
        return [d.date() for d in all_days]

    def _download_file(self, url: str, referer: Optional[str] = None) -> Optional[bytes]:
        """Downloads a file with comprehensive error handling, retry logic, and backoff.

        Handles:
        - HTTP 403/429: Rate limiting — backs off and re-initializes session
        - HTTP 5xx: Server errors — retries with exponential backoff
        - HTTP 404: Not found — returns None immediately (no retry)
        - ConnectionError: Network issues, resets — retries with backoff
        - Timeout: Slow server — retries with increasing timeout
        - SSLError: Certificate issues — retries once then raises DownloadFailedError
        - ChunkedEncodingError: Incomplete response — retries
        - HTML error pages disguised as 200 — detected and treated as failure

        Returns:
            bytes on success, None on HTTP 404 (genuine not-found).

        Raises:
            HTTP403Error: On HTTP 403 (access denied, never retried).
            DownloadFailedError: On all other failures after retries exhausted
                (transient errors, HTML block pages, SSL errors, etc.).
        """
        # Throttle: ensure minimum gap between requests across all threads
        with self._throttle_lock:
            now = time.time()
            elapsed = now - self._last_request_time
            if elapsed < self.REQUEST_DELAY:
                time.sleep(self.REQUEST_DELAY - elapsed)
            self._last_request_time = time.time()
            self._request_count += 1
            # Proactively refresh session before hitting rate limits
            if self._request_count % self.SESSION_REFRESH_AFTER == 0:
                self._init_session()
                time.sleep(1)
        headers = {}
        if referer:
            headers["Referer"] = referer
        # Rotate User-Agent to reduce chance of bot detection
        headers["User-Agent"] = random.choice(_USER_AGENTS)

        # Modern browser sec-fetch headers — critical for Cloudflare/bot detection
        if ARCHIVE_URL in url:
            # Archive downloads look like cross-site navigations from the reports page
            headers["sec-fetch-dest"] = "document"
            headers["sec-fetch-mode"] = "navigate"
            headers["sec-fetch-site"] = "same-site"
            headers["sec-fetch-user"] = "?1"
        elif "/api/" in url:
            # API calls look like async XHR from the same origin
            headers["sec-fetch-dest"] = "empty"
            headers["sec-fetch-mode"] = "cors"
            headers["sec-fetch-site"] = "same-origin"
        else:
            headers["sec-fetch-dest"] = "document"
            headers["sec-fetch-mode"] = "navigate"
            headers["sec-fetch-site"] = "none"
            headers["sec-fetch-user"] = "?1"

        max_retries = 3
        base_delay = 0.5

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
                        raise DownloadFailedError(f"HTML error page for {url.split('?')[0]}")
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
                    raise DownloadFailedError(f"Persistent SSL error for {url.split('?')[0]}")
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

            except HTTP403Error:
                # 403 must not be retried — propagate immediately
                raise

            except Exception as e:
                # Truly unexpected errors (shouldn't happen, but don't crash)
                print(f"  Unexpected error (attempt {attempt+1}/{max_retries}): {type(e).__name__}: {e}")
                time.sleep(delay)

        raise DownloadFailedError(
            f"All {max_retries} attempts exhausted for {url.split('?')[0]}")

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
        """Parses downloaded report content (handles both ZIP and plain CSV).

        Returns None if data is genuinely empty (no rows).
        Raises DownloadFailedError if content could not be decoded/parsed.
        """
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
            if df is None:
                raise DownloadFailedError(f"Could not decode {label} CSV for {date}")
            if df.empty:
                return None
            return clean_fn(df, date)
        except zipfile.BadZipFile:
            df = self._read_csv_with_encoding(content)
            if df is None:
                raise DownloadFailedError(f"Could not decode {label} (bad zip fallback) for {date}")
            if df.empty:
                return None
            return clean_fn(df, date)
        except DownloadFailedError:
            raise
        except Exception as e:
            print(f"Error parsing {label} for {date}: {e}")
            raise DownloadFailedError(f"Parse error for {label} {date}: {e}") from e

    def _parse_delivery_content(self, content: bytes, date: datetime.date) -> Optional[pd.DataFrame]:
        """Parses Delivery Positions content (DAT/CSV/ZIP formats).

        Returns None if data is genuinely empty.
        Raises DownloadFailedError if content could not be decoded/parsed.

        MTO DAT files from NSE have a multi-line preamble:
          Line 1: Title ("Security Wise Delivery Position ...")
          Line 2: "10,MTO,..." metadata
          Line 3: "Trade Date <...>,Settlement Type <...>"
          Line 4: Column header ("Record Type,Sr No,Name of Security,...")
          Line 5+: Data rows ("20,1,SYMBOL,...")
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
                raise DownloadFailedError(f"Could not decode Delivery Positions for {date}")

            lines = text.strip().split('\n')

            # Find the actual header line — look for a line containing
            # "Record Type" or "Name of Security" or "Quantity Traded"
            header_idx = None
            for i, line in enumerate(lines):
                line_lower = line.lower()
                if ('record type' in line_lower and 'name of security' in line_lower) or \
                   ('record type' in line_lower and 'quantity traded' in line_lower):
                    header_idx = i
                    break

            if header_idx is not None:
                # Read data lines only (skip header — it's often missing the Series column)
                data_text = '\n'.join(lines[header_idx + 1:])
                sep = '|' if '|' in lines[header_idx] else ','

                # Count fields in header vs first data line to detect mismatch
                header_fields = len(lines[header_idx].split(sep))
                first_data = lines[header_idx + 1].strip() if header_idx + 1 < len(lines) else ''
                data_fields = len(first_data.split(sep)) if first_data else header_fields

                if data_fields > header_fields:
                    # Header is missing columns (common: Series column missing)
                    # Use known 7-column layout: Record Type, Sr No, Symbol, Series, Qty, Deliv Qty, Pct
                    std_cols = ['Record Type', 'Sr No', 'Symbol', 'Series',
                                'Qty Traded', 'Deliverable Qty', 'Delivery Pct']
                    df = pd.read_csv(io.StringIO(data_text), sep=sep, header=None,
                                     on_bad_lines='skip', skipinitialspace=True)
                    if len(df.columns) <= len(std_cols):
                        df.columns = std_cols[:len(df.columns)]
                    else:
                        df.columns = std_cols + [f'Extra_{i}' for i in range(len(df.columns) - len(std_cols))]
                else:
                    # Header matches data — use it
                    full_text = '\n'.join(lines[header_idx:])
                    df = pd.read_csv(io.StringIO(full_text), sep=sep, on_bad_lines='skip',
                                     skipinitialspace=True)
            else:
                # Fallback: detect delimiter and try reading as-is
                first_line = lines[0] if lines else ''
                sep = '|' if '|' in first_line else ','
                df = pd.read_csv(io.StringIO(text), sep=sep, on_bad_lines='skip',
                                 skipinitialspace=True)

            if df is None:
                raise DownloadFailedError(f"Could not parse Delivery Positions CSV for {date}")
            if df.empty:
                return None

            # If first column name is numeric, it's a headerless DAT file
            first_col_name = str(df.columns[0]).strip()
            if first_col_name.isdigit():
                df = pd.read_csv(io.StringIO(data_text if header_idx is not None else text),
                                 sep=sep, header=None,
                                 on_bad_lines='skip', skipinitialspace=True)
                std_cols = ['Record Type', 'Sr No', 'Symbol', 'Series',
                            'Qty Traded', 'Deliverable Qty', 'Delivery Pct']
                if len(df.columns) <= len(std_cols):
                    df.columns = std_cols[:len(df.columns)]
                else:
                    df.columns = std_cols + [f'Extra_{i}' for i in range(len(df.columns) - len(std_cols))]

            return self._clean_delivery_data(df, date)
        except DownloadFailedError:
            raise
        except Exception as e:
            print(f"Error parsing Delivery Positions for {date}: {e}")
            raise DownloadFailedError(f"Parse error for Delivery Positions {date}: {e}") from e

    def download_cm_bhavcopy(self, date: datetime.date) -> Optional[pd.DataFrame]:
        """Downloads Equity (Capital Market) Bhavcopy for a given date."""
        if date >= UDIFF_START_DATE:
            # UDiFF Format — try archive first, fallback to Reports API
            url = f"{ARCHIVE_URL}/content/cm/BhavCopy_NSE_CM_0_0_0_{date.strftime('%Y%m%d')}_F_0000.csv.zip"
            try:
                content = self._download_file(url, referer=ALL_REPORTS_URL)
            except (HTTP403Error, DownloadFailedError):
                content = None

            if not content:
                report_name = "CM-UDiFF Common Bhavcopy Final (zip)"
                archives = [{"name": report_name, "type": "archives", "category": "capital-market", "section": "equities"}]
                archives_str = urllib.parse.quote(json.dumps(archives, separators=(',', ':')))
                api_url = f"{BASE_URL}/api/reports?archives={archives_str}&date={date.strftime('%d-%b-%Y')}&type=equities&mode=single"
                content = self._download_file(api_url, referer=ALL_REPORTS_URL)
        else:
            # Legacy Archive Format — try archive first, fallback to Reports API on 403
            url = f"{ARCHIVE_URL}/content/historical/EQUITIES/{date.strftime('%Y')}/{date.strftime('%b').upper()}/cm{date.strftime('%d%b%Y').upper()}bhav.csv.zip"
            try:
                content = self._download_file(url, referer=ALL_REPORTS_URL)
            except (HTTP403Error, DownloadFailedError):
                # Fallback: try Reports API for older dates
                report_name = "CM-UDiFF Common Bhavcopy Final (zip)"
                archives = [{"name": report_name, "type": "archives", "category": "capital-market", "section": "equities"}]
                archives_str = urllib.parse.quote(json.dumps(archives, separators=(',', ':')))
                api_url = f"{BASE_URL}/api/reports?archives={archives_str}&date={date.strftime('%d-%b-%Y')}&type=equities&mode=single"
                try:
                    content = self._download_file(api_url, referer=ALL_REPORTS_URL)
                except (HTTP403Error, DownloadFailedError):
                    raise  # Both sources failed

        if not content:
            return None

        try:
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                csv_filename = z.namelist()[0]
                with z.open(csv_filename) as f:
                    df = pd.read_csv(f)
                    return self._clean_cm_data(df, date)
        except DownloadFailedError:
            raise
        except Exception as e:
            print(f"Error parsing CM Bhavcopy for {date}: {e}")
            raise DownloadFailedError(f"Parse error for CM Bhavcopy {date}: {e}") from e

    def download_fo_bhavcopy(self, date: datetime.date) -> Optional[pd.DataFrame]:
        """Downloads Derivatives (F&O) Bhavcopy for a given date."""
        if date >= UDIFF_START_DATE:
            # UDiFF Format — try archive first, fallback to Reports API
            url = f"{ARCHIVE_URL}/content/fo/BhavCopy_NSE_FO_0_0_0_{date.strftime('%Y%m%d')}_F_0000.csv.zip"
            try:
                content = self._download_file(url, referer=ALL_REPORTS_URL)
            except (HTTP403Error, DownloadFailedError):
                content = None

            if not content:
                report_name = "F&O - UDiFF Common Bhavcopy Final (zip)"
                archives = [{"name": report_name, "type": "archives", "category": "derivatives", "section": "derivatives"}]
                archives_str = urllib.parse.quote(json.dumps(archives, separators=(',', ':')))
                api_url = f"{BASE_URL}/api/reports?archives={archives_str}&date={date.strftime('%d-%b-%Y')}&type=derivatives&mode=single"
                content = self._download_file(api_url, referer=ALL_REPORTS_URL)
        else:
            # Legacy Archive Format — try archive first, fallback to Reports API on 403
            url = f"{ARCHIVE_URL}/content/historical/DERIVATIVES/{date.strftime('%Y')}/{date.strftime('%b').upper()}/fo{date.strftime('%d%b%Y').upper()}bhav.csv.zip"
            try:
                content = self._download_file(url, referer=ALL_REPORTS_URL)
            except (HTTP403Error, DownloadFailedError):
                # Fallback: try Reports API for older dates
                report_name = "F&O - UDiFF Common Bhavcopy Final (zip)"
                archives = [{"name": report_name, "type": "archives", "category": "derivatives", "section": "derivatives"}]
                archives_str = urllib.parse.quote(json.dumps(archives, separators=(',', ':')))
                api_url = f"{BASE_URL}/api/reports?archives={archives_str}&date={date.strftime('%d-%b-%Y')}&type=derivatives&mode=single"
                try:
                    content = self._download_file(api_url, referer=ALL_REPORTS_URL)
                except (HTTP403Error, DownloadFailedError):
                    raise  # Both sources failed

        if not content:
            return None

        try:
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                csv_filename = z.namelist()[0]
                with z.open(csv_filename) as f:
                    df = pd.read_csv(f)
                    return self._clean_fo_data(df, date)
        except DownloadFailedError:
            raise
        except Exception as e:
            print(f"Error parsing FO Bhavcopy for {date}: {e}")
            raise DownloadFailedError(f"Parse error for FO Bhavcopy {date}: {e}") from e

    def download_indices_report(self, date: datetime.date) -> Optional[pd.DataFrame]:
        """Downloads Indices data for a given date.

        Primary: ind_close_all CSV (has index OHLC, PE, PB, DY).
        Fallback: PR zip (contains stock-level data, less useful for indices).
        """
        # Try ind_close_all first — has the exact index data we need
        url = f"{ARCHIVE_URL}/content/indices/ind_close_all_{date.strftime('%d%m%Y')}.csv"
        try:
            content = self._download_file(url, referer=ALL_REPORTS_URL)
        except (HTTP403Error, DownloadFailedError):
            content = None

        if content:
            try:
                df = pd.read_csv(
                    io.BytesIO(content),
                    skipinitialspace=True,
                    on_bad_lines='skip',
                )
                if df is not None and not df.empty:
                    return self._clean_indices_data(df, date)
            except Exception as e:
                print(f"Error parsing Indices ind_close_all for {date}: {e}")

        # Fallback: PR zip
        url = f"{ARCHIVE_URL}/archives/equities/bhavcopy/pr/PR{date.strftime('%d%m%y')}.zip"
        try:
            content = self._download_file(url, referer=ALL_REPORTS_URL)
        except (HTTP403Error, DownloadFailedError):
            raise

        if not content:
            return None

        try:
            with zipfile.ZipFile(io.BytesIO(content)) as z:
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

                # Broader search: any CSV with "pr" prefix and the date digits
                if target_csv is None:
                    date_str = date.strftime('%d%m%y')
                    matches = [n for n in all_files if date_str in n and n.lower().endswith('.csv')
                               and n.lower().startswith('pr')]
                    if matches:
                        target_csv = matches[0]

                # Last resort: pick the largest CSV
                if target_csv is None:
                    csv_files = [n for n in all_files if n.lower().endswith('.csv')]
                    if csv_files:
                        target_csv = max(csv_files, key=lambda n: z.getinfo(n).file_size)

                if target_csv is None:
                    return None

                with z.open(target_csv) as f:
                    raw_bytes = f.read()

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

                if df is None:
                    raise DownloadFailedError(f"Could not decode Indices PR CSV for {date}")
                if df.empty:
                    return None

                df = df.head(100)
                return self._clean_indices_data(df, date)
        except zipfile.BadZipFile:
            raise DownloadFailedError(f"Corrupt ZIP for Indices PR {date}")
        except DownloadFailedError:
            raise
        except Exception as e:
            print(f"Error parsing Indices PR for {date}: {e}")
            raise DownloadFailedError(f"Parse error for Indices PR {date}: {e}") from e

    # --- New Report Downloads ---

    def download_short_selling(self, date: datetime.date) -> Optional[pd.DataFrame]:
        """Downloads Short Selling report for a given date."""
        # Try direct archive URL first
        url = f"{ARCHIVE_URL}/archives/equities/shortSelling/shortselling_{date.strftime('%d%m%Y')}.csv"
        try:
            content = self._download_file(url, referer=ALL_REPORTS_URL)
        except (HTTP403Error, DownloadFailedError):
            content = None

        # Fallback: try Reports API
        if not content:
            archives = [{"name": "CM - Short Selling", "type": "archives", "category": "capital-market", "section": "equities"}]
            archives_str = urllib.parse.quote(json.dumps(archives, separators=(',', ':')))
            api_url = f"{BASE_URL}/api/reports?archives={archives_str}&date={date.strftime('%d-%b-%Y')}&type=equities&mode=single"
            content = self._download_file(api_url, referer=ALL_REPORTS_URL)

        if not content:
            return None
        return self._parse_report_content(content, date, self._clean_short_selling_data, "Short Selling")

    def download_daily_volatility(self, date: datetime.date) -> Optional[pd.DataFrame]:
        """Downloads Daily Volatility report for a given date."""
        # Try direct archive URL first
        url = f"{ARCHIVE_URL}/archives/nsccl/volt/CMVOLT_{date.strftime('%d%m%Y')}.CSV"
        try:
            content = self._download_file(url, referer=ALL_REPORTS_URL)
        except (HTTP403Error, DownloadFailedError):
            content = None

        # Fallback: try Reports API
        if not content:
            archives = [{"name": "CM - Daily Volatility", "type": "archives", "category": "capital-market", "section": "equities"}]
            archives_str = urllib.parse.quote(json.dumps(archives, separators=(',', ':')))
            api_url = f"{BASE_URL}/api/reports?archives={archives_str}&date={date.strftime('%d-%b-%Y')}&type=equities&mode=single"
            content = self._download_file(api_url, referer=ALL_REPORTS_URL)

        if not content:
            return None
        return self._parse_report_content(content, date, self._clean_volatility_data, "Daily Volatility")

    def download_market_activity(self, date: datetime.date) -> Optional[pd.DataFrame]:
        """Downloads Market Activity Report for a given date."""
        # Try direct archive URL first (format: MADDMMYY.csv)
        url = f"{ARCHIVE_URL}/archives/equities/mkt/MA{date.strftime('%d%m%y')}.csv"
        try:
            content = self._download_file(url, referer=ALL_REPORTS_URL)
        except (HTTP403Error, DownloadFailedError):
            content = None

        # Fallback: try Reports API
        if not content:
            archives = [{"name": "CM - Market Activity Report", "type": "archives", "category": "capital-market", "section": "equities"}]
            archives_str = urllib.parse.quote(json.dumps(archives, separators=(',', ':')))
            api_url = f"{BASE_URL}/api/reports?archives={archives_str}&date={date.strftime('%d-%b-%Y')}&type=equities&mode=single"
            content = self._download_file(api_url, referer=ALL_REPORTS_URL)

        if not content:
            return None
        return self._parse_report_content(content, date, self._clean_market_activity_data, "Market Activity")

    def download_price_band(self, date: datetime.date) -> Optional[pd.DataFrame]:
        """Downloads Price Band changes from next trade date report."""
        # Try direct archive URL first
        url = f"{ARCHIVE_URL}/content/equities/eq_band_changes_{date.strftime('%d%m%Y')}.csv"
        try:
            content = self._download_file(url, referer=ALL_REPORTS_URL)
        except (HTTP403Error, DownloadFailedError):
            content = None

        # Fallback: try Reports API
        if not content:
            archives = [{"name": "CM - Price Band changes (for Next day)", "type": "archives", "category": "capital-market", "section": "equities"}]
            archives_str = urllib.parse.quote(json.dumps(archives, separators=(',', ':')))
            api_url = f"{BASE_URL}/api/reports?archives={archives_str}&date={date.strftime('%d-%b-%Y')}&type=equities&mode=single"
            content = self._download_file(api_url, referer=ALL_REPORTS_URL)

        if not content:
            return None
        return self._parse_report_content(content, date, self._clean_price_band_data, "Price Band")

    def download_pe_ratio(self, date: datetime.date) -> Optional[pd.DataFrame]:
        """Downloads PE Ratio report for a given date.

        The archive URL (PE_DDMMYY.csv) no longer exists on NSE.
        Uses the Reports API directly, which works for recent dates.
        """
        # Reports API is the only working source for PE data
        archives = [{"name": "PE Ratio", "type": "archives", "category": "capital-market", "section": "equities"}]
        archives_str = urllib.parse.quote(json.dumps(archives, separators=(',', ':')))
        api_url = f"{BASE_URL}/api/reports?archives={archives_str}&date={date.strftime('%d-%b-%Y')}&type=equities&mode=single"
        try:
            content = self._download_file(api_url, referer=ALL_REPORTS_URL)
        except (HTTP403Error, DownloadFailedError):
            content = None

        if not content:
            return None
        return self._parse_report_content(content, date, self._clean_pe_ratio_data, "PE Ratio")

    def download_corp_bonds(self, date: datetime.date) -> Optional[pd.DataFrame]:
        """Downloads Corporate Bonds Traded Report for a given date."""
        # Try direct archive URL first
        url = f"{ARCHIVE_URL}/archives/debt/cbm/cbm_trd{date.strftime('%Y%m%d')}.csv"
        try:
            content = self._download_file(url, referer=ALL_REPORTS_URL)
        except (HTTP403Error, DownloadFailedError):
            content = None

        # Fallback: try Reports API
        if not content:
            archives = [{"name": "CBM - Bhavcopy for the day", "type": "archives", "category": "debt", "section": "debt"}]
            archives_str = urllib.parse.quote(json.dumps(archives, separators=(',', ':')))
            api_url = f"{BASE_URL}/api/reports?archives={archives_str}&date={date.strftime('%d-%b-%Y')}&type=debt&mode=single"
            content = self._download_file(api_url, referer=ALL_REPORTS_URL)

        if not content:
            return None
        return self._parse_report_content(content, date, self._clean_corp_bonds_data, "Corporate Bonds")

    def download_delivery_positions(self, date: datetime.date) -> Optional[pd.DataFrame]:
        """Downloads Security-wise Delivery Positions for a given date.

        Legacy format is a DAT file (comma or pipe delimited with record type markers).
        """
        # Try direct archive URL first (works for all dates)
        url = f"{ARCHIVE_URL}/archives/equities/mto/MTO_{date.strftime('%d%m%Y')}.DAT"
        try:
            content = self._download_file(url, referer=ALL_REPORTS_URL)
        except (HTTP403Error, DownloadFailedError):
            content = None

        # Fallback: try Reports API
        if not content:
            archives = [{"name": "CM - Security-wise Delivery Positions", "type": "archives", "category": "capital-market", "section": "equities"}]
            archives_str = urllib.parse.quote(json.dumps(archives, separators=(',', ':')))
            api_url = f"{BASE_URL}/api/reports?archives={archives_str}&date={date.strftime('%d-%b-%Y')}&type=equities&mode=single"
            content = self._download_file(api_url, referer=ALL_REPORTS_URL)

        if not content:
            return None
        return self._parse_delivery_content(content, date)

    def download_wdm_daily(self, date: datetime.date) -> Optional[pd.DataFrame]:
        """Downloads WDM Daily Report (ZIP containing multiple files) for a given date.

        The ZIP contains multiple CSV/DAT files.  Each sub-file is read,
        cleaned, and tagged with Symbol = 'Debt_{filename_stem}'.  All
        sub-files are concatenated into a single DataFrame so the normal
        merge pipeline can split them back into per-symbol processed files.

        Archive URL format: dlyDDMMYYYY.zip
        """
        ALL_REPORTS_DEBT_URL = f"{BASE_URL}/all-reports-debt"

        # Try direct archive URL first
        url = f"{ARCHIVE_URL}/archives/debt/wdm/dly{date.strftime('%d%m%Y')}.zip"
        try:
            content = self._download_file(url, referer=ALL_REPORTS_DEBT_URL)
        except (HTTP403Error, DownloadFailedError):
            content = None

        # Fallback: try Reports API
        if not content:
            archives = [{"name": "WDM - Daily Reports", "type": "archives",
                         "category": "debt", "section": "debt"}]
            archives_str = urllib.parse.quote(json.dumps(archives, separators=(',', ':')))
            api_url = (f"{BASE_URL}/api/reports?archives={archives_str}"
                       f"&date={date.strftime('%d-%b-%Y')}&type=debt&mode=single")
            content = self._download_file(api_url, referer=ALL_REPORTS_DEBT_URL)

        if not content:
            return None

        return self._parse_wdm_zip(content, date)

    def _parse_wdm_zip(self, content: bytes, date: datetime.date) -> Optional[pd.DataFrame]:
        """Extracts all CSV/DAT files from a WDM Daily ZIP and returns them
        as a single DataFrame with Symbol = 'Debt_{filename_stem}'.

        Raises DownloadFailedError if the ZIP cannot be read.
        Returns None if the ZIP is empty or contains no data.
        """
        try:
            if content[:2] != b'PK':
                # Not a ZIP — try to read as plain CSV
                df = self._read_csv_with_encoding(content)
                if df is None or df.empty:
                    return None
                df = self._clean_wdm_subfile(df, date, 'Debt_daily')
                return df

            all_dfs = []
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                data_files = [n for n in z.namelist()
                              if n.lower().endswith(('.csv', '.dat', '.txt'))
                              and not n.startswith('__')]
                if not data_files:
                    # Try all files
                    data_files = [n for n in z.namelist() if not n.startswith('__')]

                for fname in data_files:
                    try:
                        with z.open(fname) as f:
                            raw_bytes = f.read()
                        if not raw_bytes.strip():
                            continue

                        df = self._read_csv_with_encoding(raw_bytes)
                        if df is None or df.empty:
                            continue

                        # Derive symbol name from filename: Debt_{stem}
                        stem = Path(fname).stem
                        # Sanitize: remove date digits from stem for a clean name
                        symbol_name = f"Debt_{stem}"
                        df = self._clean_wdm_subfile(df, date, symbol_name)
                        all_dfs.append(df)
                    except Exception as e:
                        print(f"  [WDM] Error parsing {fname} for {date}: {e}")
                        continue

            if not all_dfs:
                return None

            # Concatenate all sub-files — they may have different schemas;
            # pandas concat fills missing columns with NaN.
            combined = pd.concat(all_dfs, ignore_index=True)
            return combined if not combined.empty else None

        except zipfile.BadZipFile:
            raise DownloadFailedError(f"Corrupt ZIP for WDM Daily {date}")
        except DownloadFailedError:
            raise
        except Exception as e:
            print(f"Error parsing WDM Daily for {date}: {e}")
            raise DownloadFailedError(f"Parse error for WDM Daily {date}: {e}") from e

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
        
        if 'Symbol' not in df.columns:
            df['Symbol'] = 'UNKNOWN'
        else:
            df['Symbol'] = df['Symbol'].astype(str).str.strip()

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

        if 'Symbol' not in df.columns:
            df['Symbol'] = 'UNKNOWN'
        else:
            df['Symbol'] = df['Symbol'].astype(str).str.strip()
        
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
            'Symbol Name': 'Symbol', 'Name of the Security': 'Symbol',
            'SYMBOL': 'Symbol', 'Symbol': 'Symbol',
            'NAME OF THE SECURITY': 'Symbol', 'Security Name': 'Security Name',
            'QTY Short Sold': 'Qty Short Sold', 'QTY OF SHORT SELL': 'Qty Short Sold',
            'Quantity Short Sold': 'Qty Short Sold', 'SHORT_SELL_QTY': 'Qty Short Sold',
            'Quantity': 'Qty Short Sold',
            'QTY Short Bought Back': 'Qty Short Buy', 'QTY OF SHORT BUY BACK': 'Qty Short Buy',
            'Quantity of Short Buying': 'Qty Short Buy', 'SHORT_BUY_QTY': 'Qty Short Buy',
            'DATE': 'Date', 'Date': 'Date', 'Trade Date': 'Date',
        }
        df = df.rename(columns=mapping)
        if 'Date' not in df.columns:
            df['Date'] = date
        else:
            df['Date'] = pd.to_datetime(df['Date'], format='mixed', dayfirst=True, errors='coerce').dt.date
        if 'Symbol' in df.columns:
            df['Symbol'] = df['Symbol'].astype(str).str.strip()
        else:
            df['Symbol'] = 'UNKNOWN'
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
        else:
            df['Symbol'] = 'UNKNOWN'
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
            'Old Band': 'Old Band', 'FROM_BAND': 'Old Band', 'From': 'Old Band',
            'New Band': 'New Band', 'TO_BAND': 'New Band', 'To': 'New Band',
            'Applicable From': 'Effective Date', 'EFF_DATE': 'Effective Date',
        }
        df = df.rename(columns=mapping)
        if 'Date' not in df.columns:
            df['Date'] = date
        else:
            df['Date'] = pd.to_datetime(df['Date'], format='mixed', dayfirst=True, errors='coerce').dt.date
        if 'Symbol' in df.columns:
            df['Symbol'] = df['Symbol'].astype(str).str.strip()
        else:
            df['Symbol'] = 'UNKNOWN'
        # Cast band columns to string to avoid mixed-type issues
        for col in ['Old Band', 'New Band']:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
        return df

    def _clean_pe_ratio_data(self, df: pd.DataFrame, date: datetime.date) -> pd.DataFrame:
        """Standardizes PE Ratio data."""
        df.columns = [c.strip() for c in df.columns]
        mapping = {
            'Index Name': 'Symbol', 'INDEX_NAME': 'Symbol', 'Symbol': 'Symbol',
            'SYMBOL': 'Symbol', 'INDEX NAME': 'Symbol', 'Index': 'Symbol',
            'Date': 'Date', 'DATE': 'Date',
            'P/E': 'PE', 'P/B': 'PB', 'Div Yield': 'DY',
            'PE': 'PE', 'PB': 'PB', 'DY': 'DY',
            'SYMBOL P/E': 'PE', 'ADJUSTED P/E': 'Adjusted PE',
        }
        df = df.rename(columns=mapping)
        if 'Date' not in df.columns:
            df['Date'] = date
        else:
            df['Date'] = pd.to_datetime(df['Date'], format='mixed', dayfirst=True, errors='coerce').dt.date
        if 'Symbol' in df.columns:
            df['Symbol'] = df['Symbol'].astype(str).str.strip()
        else:
            df['Symbol'] = 'UNKNOWN'
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
        else:
            df['Symbol'] = 'UNKNOWN'
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
            'Name of Security': 'Symbol',
            'TckrSymb': 'Symbol', 'NAME': 'Symbol',
            'SERIES': 'Series', 'Series': 'Series', 'SctySrs': 'Series',
            'QUANTITY TRADED': 'Qty Traded', 'QTY_TRADED': 'Qty Traded',
            'Qty Traded': 'Qty Traded', 'TtlTradgVol': 'Qty Traded',
            'Quantity Traded': 'Qty Traded',
            'DELIVERABLE QTY': 'Deliverable Qty', 'DELIVERABLE_QTY': 'Deliverable Qty',
            'Deliverable Qty(Demat)': 'Deliverable Qty', 'DlvrblQty': 'Deliverable Qty',
            'Deliverable Qty': 'Deliverable Qty',
            'Deliverable Quantity(gross across client level)': 'Deliverable Qty',
            '% OF DELIVERABLE QTY TO TRADED QTY': 'Delivery Pct',
            'DELV_PER': 'Delivery Pct', 'DELV_PERC': 'Delivery Pct',
            'Delivery Pct': 'Delivery Pct', '% Dly Qt to Traded Qty': 'Delivery Pct',
            'PctgDlvryQty': 'Delivery Pct',
            '% of Deliverable Quantity to Traded Quantity': 'Delivery Pct',
            'DATE': 'Date', 'Date': 'Date', 'TIMESTAMP': 'Date',
        }
        df = df.rename(columns=mapping)

        # Drop helper columns
        for drop_col in ['Sr No']:
            if drop_col in df.columns:
                df = df.drop(columns=[drop_col])

        if 'Date' not in df.columns:
            df['Date'] = date
        else:
            df['Date'] = pd.to_datetime(df['Date'], format='mixed', dayfirst=True, errors='coerce').dt.date
        if 'Symbol' in df.columns:
            df['Symbol'] = df['Symbol'].astype(str).str.strip()
        else:
            df['Symbol'] = 'UNKNOWN'
        for col in ['Qty Traded', 'Deliverable Qty', 'Delivery Pct']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        return df

    def _clean_wdm_subfile(self, df: pd.DataFrame, date: datetime.date, symbol_name: str) -> pd.DataFrame:
        """Standardizes a single sub-file from a WDM Daily ZIP.

        Sets Symbol = symbol_name (e.g. 'Debt_mktwatch') so the merge
        pipeline writes each sub-file to its own processed parquet.
        Attempts to parse any Date column found; falls back to the
        download date if none exists.
        """
        df.columns = [c.strip() for c in df.columns]

        # Try to identify and parse a date column
        date_col_found = False
        for col in df.columns:
            col_lower = col.lower()
            if col_lower in ('date', 'trade date', 'trade_date', 'timestamp',
                             'trading date', 'trd_dt', 'trddt', 'traddttm'):
                df = df.rename(columns={col: 'Date'})
                df['Date'] = pd.to_datetime(df['Date'], format='mixed',
                                            dayfirst=True, errors='coerce').dt.date
                date_col_found = True
                break

        if not date_col_found:
            df['Date'] = date

        df['Symbol'] = symbol_name

        # Convert numeric-looking columns
        for col in df.columns:
            if col in ('Date', 'Symbol'):
                continue
            # Try numeric conversion — leave as string if it fails
            try:
                converted = pd.to_numeric(df[col], errors='coerce')
                # Only apply if >50% of non-null values converted successfully
                if converted.notna().sum() > 0.5 * df[col].notna().sum():
                    df[col] = converted
            except Exception:
                pass

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

    MERGE_WORKERS = 12  # Parallel threads for writing per-symbol parquet files

    def merge_raw_to_processed(self, raw_dir: Path, raw_prefix: str, target_dir: Path, label: str, group_col: str = 'Symbol'):
        """Merges raw day-parquet files from disk into per-symbol processed files.

        Strategy for speed:
        1. Read ALL raw files in one pass using parallel I/O threads,
           streaming into a per-symbol dict to avoid re-reading/re-writing
           the same processed file across batches.
        2. Memory control: raw files are read in chunks of READ_CHUNK,
           immediately grouped into per-symbol lists, then freed.
        3. Pre-consolidate per-symbol data and cast dtypes once (not per-write).
        4. Smart dedup: if new dates don't overlap existing processed file,
           skip drop_duplicates + sort (just append).
        5. Write per-symbol files in parallel threads (I/O bound, releases GIL).
        """
        raw_files = sorted(raw_dir.glob(f"{raw_prefix}_*.parquet"))
        if not raw_files:
            print(f"  [{label}] No raw files to merge.", flush=True)
            return

        # Track which raw files have already been merged via a stamp file.
        # The stamp records the set of raw filenames that have been processed.
        stamp_file = raw_dir / f".merged_{raw_prefix}.txt"
        already_merged = set()
        if stamp_file.exists():
            try:
                already_merged = set(stamp_file.read_text().strip().splitlines())
            except Exception:
                pass

        files_to_merge = [f for f in raw_files if f.name not in already_merged]

        if not files_to_merge:
            print(f"  [{label}] All raw files already merged.", flush=True)
            return

        total_files = len(files_to_merge)
        t0 = time.time()
        print(f"  [{label}] Merging {total_files} raw files...", flush=True)

        # --- Phase 1: Read raw files in chunks with parallel I/O ---
        READ_CHUNK = 200      # Files per read chunk (memory control)
        READER_THREADS = 8    # Parallel readers within each chunk
        symbol_new_data: Dict[str, List[pd.DataFrame]] = {}
        dedup_cols = None  # Determined from first chunk
        read_errors = 0

        def _read_one(f: Path):
            try:
                return pd.read_parquet(f, engine='pyarrow')
            except Exception as e:
                return e  # Return exception to count errors

        for chunk_start in range(0, total_files, READ_CHUNK):
            chunk_end = min(chunk_start + READ_CHUNK, total_files)
            chunk_files = files_to_merge[chunk_start:chunk_end]

            # Parallel reads — pyarrow releases GIL during I/O
            with ThreadPoolExecutor(max_workers=READER_THREADS) as reader_pool:
                results = list(reader_pool.map(_read_one, chunk_files))

            chunk_dfs = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    read_errors += 1
                    if read_errors <= 3:
                        print(f"  [{label}] Error reading {chunk_files[i].name}: {result}")
                elif result is not None:
                    chunk_dfs.append(result)
            del results

            if not chunk_dfs:
                continue

            combined = pd.concat(chunk_dfs, ignore_index=True)
            del chunk_dfs

            if combined.empty:
                del combined
                continue

            if group_col not in combined.columns:
                print(f"  [{label}] Warning: '{group_col}' missing — setting to 'UNKNOWN'.")
                combined[group_col] = 'UNKNOWN'

            # Determine dedup key columns once
            if dedup_cols is None:
                dedup_cols = ['Date']
                for extra_key in ['Symbol', 'Instrument', 'Expiry', 'Strike Price', 'Option type']:
                    if extra_key in combined.columns:
                        dedup_cols.append(extra_key)

            # Distribute rows into per-symbol buckets
            for name, group in combined.groupby(group_col):
                symbol_new_data.setdefault(name, []).append(group)

            del combined

            if chunk_end < total_files:
                elapsed = time.time() - t0
                print(f"  [{label}] Read {chunk_end}/{total_files} raw files ({elapsed:.1f}s)...", flush=True)

        if not symbol_new_data:
            print(f"  [{label}] No data to merge.", flush=True)
            return

        # --- Phase 1.5: Pre-consolidate per-symbol DataFrames ---
        # Concat all chunks per symbol into one DF and cast dtypes once here,
        # avoiding redundant work in each parallel writer.
        for name in symbol_new_data:
            dfs = symbol_new_data[name]
            merged = pd.concat(dfs, ignore_index=True) if len(dfs) > 1 else dfs[0]
            for col in merged.columns:
                if merged[col].dtype == object and col != 'Date':
                    merged[col] = merged[col].astype(str)
            symbol_new_data[name] = merged
            del dfs

        num_symbols = len(symbol_new_data)
        read_elapsed = time.time() - t0
        if read_errors > 3:
            print(f"  [{label}] ({read_errors - 3} more read errors suppressed)")
        print(f"  [{label}] Read complete ({total_files} files, {num_symbols} symbols, "
              f"{read_elapsed:.1f}s). Writing processed files...", flush=True)

        # --- Phase 2: Write each processed file ONCE, in parallel ---
        # Smart dedup: if all new dates are strictly after the existing file's
        # max date, skip drop_duplicates + sort (just concat).  This is the
        # common case for incremental updates and saves significant time.
        final_dedup_cols = dedup_cols or ['Date']
        write_errors = []
        write_count = 0
        write_lock = threading.Lock()

        def _merge_and_write(item):
            nonlocal write_count
            name, new_data = item
            file_path = target_dir / f"{name}.parquet"
            try:
                if file_path.exists():
                    existing = pd.read_parquet(file_path, engine='pyarrow')
                    # Smart shortcut: check date overlap
                    new_min_date = new_data['Date'].min()
                    existing_max_date = existing['Date'].max()
                    if new_min_date > existing_max_date:
                        # No overlap — new data is strictly newer.
                        # Sort only the new chunk (existing is already sorted),
                        # then append.  Skip dedup entirely.
                        new_sorted = new_data.sort_values('Date')
                        merged = pd.concat([existing, new_sorted], ignore_index=True)
                        del new_sorted
                    else:
                        # Date ranges overlap — full dedup + sort required
                        merged = pd.concat([existing, new_data], ignore_index=True)
                        merged = merged.drop_duplicates(subset=final_dedup_cols, keep='last')
                        merged = merged.sort_values('Date')
                    del existing
                else:
                    # New symbol — just sort
                    merged = new_data.sort_values('Date')
                del new_data
                merged.to_parquet(file_path, engine='pyarrow', compression='zstd', index=False)
                del merged
            except Exception as e:
                write_errors.append(f"{name}: {e}")

            with write_lock:
                write_count += 1

        with ThreadPoolExecutor(max_workers=self.MERGE_WORKERS) as pool:
            list(pool.map(_merge_and_write, symbol_new_data.items()))

        del symbol_new_data

        # Record merged filenames so they aren't re-processed next run
        all_merged = already_merged | {f.name for f in files_to_merge}
        try:
            stamp_file.write_text('\n'.join(sorted(all_merged)))
        except Exception as e:
            print(f"  [{label}] Warning: could not update merge stamp: {e}")

        elapsed = time.time() - t0
        if write_errors:
            for err in write_errors[:5]:
                print(f"  [{label}] Write error: {err}")
        print(f"  [{label}] Merge complete: {total_files} files → {num_symbols} symbols in {elapsed:.1f}s", flush=True)

    # --- Concurrent download helpers ---
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

    def _download_day_wdm(self, day: datetime.date) -> tuple:
        """Download WDM Daily Report for one day. Returns (day, df_or_None)."""
        df = self.download_wdm_daily(day)
        return (day, df)

    NODATA_RETRY_SAMPLE = 10  # Number of random .nodata days to retry per category

    def _retry_nodata_sample(self, download_fn, raw_dir, raw_prefix, processed_dir, label):
        """Retries a random sample of .nodata days to recover falsely-marked dates.

        Picks up to NODATA_RETRY_SAMPLE random .nodata files, attempts to
        download them again.  On success the .nodata marker is replaced with
        the actual parquet file and the data is merged into processed output.
        On failure the .nodata marker stays (day remains skipped).
        """
        nodata_files = list(raw_dir.glob(f"{raw_prefix}_*.nodata"))
        if not nodata_files:
            return

        sample_size = min(self.NODATA_RETRY_SAMPLE, len(nodata_files))
        sample = random.sample(nodata_files, sample_size)

        # Always include today's .nodata if it exists (requirement: always
        # retry today's date on every run — unless today is a weekend
        # and not Budget day, in which case .nodata_weekend applies)
        today = datetime.date.today()
        today_is_trading = today.weekday() < 5 or (today.month, today.day) == BUDGET_DAY
        if today_is_trading:
            today_nodata = raw_dir / f"{raw_prefix}_{today.strftime('%Y%m%d')}.nodata"
            if today_nodata.exists() and today_nodata not in sample:
                sample.append(today_nodata)

        # Extract dates from filenames
        retry_items = []
        for nf in sample:
            try:
                date_str = nf.stem.split('_', 1)[1]  # e.g. "20240115"
                day = datetime.datetime.strptime(date_str, '%Y%m%d').date()
                retry_items.append((day, nf))
            except (IndexError, ValueError):
                continue

        if not retry_items:
            return

        print(f"  [{label}] Retrying {len(retry_items)} random no-data days...", flush=True)
        recovered = 0

        for day, nodata_path in retry_items:
            try:
                _, df = download_fn(day)
            except (HTTP403Error, DownloadFailedError):
                df = None
            except Exception:
                df = None

            if df is not None:
                # Success — save raw file and remove the .nodata marker
                raw_file = raw_dir / f"{raw_prefix}_{day.strftime('%Y%m%d')}.parquet"
                try:
                    df.to_parquet(raw_file, engine='pyarrow', compression='zstd', index=False)
                    nodata_path.unlink(missing_ok=True)
                    recovered += 1
                    print(f"    Recovered {day}", flush=True)
                except Exception as e:
                    print(f"    Failed to save recovered data for {day}: {e}")

        if recovered > 0:
            print(f"  [{label}] Recovered {recovered}/{len(retry_items)} days. Merging...", flush=True)
            self.merge_raw_to_processed(raw_dir, raw_prefix, processed_dir, label)
        else:
            print(f"  [{label}] No data recovered from {len(retry_items)} retries.", flush=True)

    def _concurrent_download(self, days, download_fn, raw_dir, raw_prefix, label):
        """Downloads data for multiple days, newest first, skipping already-downloaded days.

        Downloads in reverse chronological order (newest first) in batches.
        If 5 consecutive days return HTTP 403, assumes older data is not available
        and stops going further back for this category.
        """
        if not days:
            print(f"  No new {label} days to download.", flush=True)
            return

        # Today's date should always be re-attempted on trading days —
        # delete any stale .nodata marker so it is not skipped below.
        # On weekends (except Budget day Feb 1), normal .nodata_weekend applies.
        today = datetime.date.today()
        today_is_trading = today.weekday() < 5 or (today.month, today.day) == BUDGET_DAY
        if today_is_trading:
            today_nodata = raw_dir / f"{raw_prefix}_{today.strftime('%Y%m%d')}.nodata"
            if today_nodata.exists():
                today_nodata.unlink(missing_ok=True)

        # Skip days that already have raw files, .nodata, or .nodata_weekend markers
        days_to_download = []
        skipped = 0
        nodata_skipped = 0
        weekend_skipped = 0
        weekend_marked = 0
        for day in days:
            ds = day.strftime('%Y%m%d')
            raw_file = raw_dir / f"{raw_prefix}_{ds}.parquet"
            nodata_file = raw_dir / f"{raw_prefix}_{ds}.nodata"
            nodata_wknd = raw_dir / f"{raw_prefix}_{ds}.nodata_weekend"
            if raw_file.exists():
                skipped += 1
            elif nodata_wknd.exists():
                weekend_skipped += 1
            elif nodata_file.exists():
                nodata_skipped += 1
            elif day.weekday() >= 5 and (day.month, day.day) != BUDGET_DAY:
                # Weekend (Sat=5, Sun=6) — no trading, skip without requesting
                # Exception: Feb 1 (Budget day) is always a trading day
                try:
                    nodata_wknd.touch(exist_ok=True)
                except OSError:
                    pass
                weekend_marked += 1
            else:
                days_to_download.append(day)

        skip_parts = []
        if skipped > 0:
            skip_parts.append(f"{skipped} downloaded")
        if nodata_skipped > 0:
            skip_parts.append(f"{nodata_skipped} no-data")
        if weekend_skipped > 0:
            skip_parts.append(f"{weekend_skipped} weekend(cached)")
        if weekend_marked > 0:
            skip_parts.append(f"{weekend_marked} weekend(new)")
        if skip_parts:
            print(f"  [{label}] Skipping {' + '.join(skip_parts)}, {len(days_to_download)} remaining.", flush=True)

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
        MAX_CONSECUTIVE_403 = 5
        stopped_early = False
        last_progress_time = time.time()
        print(f"  Downloading {total} days of {label} data (newest first, {self.MAX_WORKERS} workers)...", flush=True)

        # Process in batches to allow concurrent downloads while tracking 403 streaks
        BATCH_SIZE = self.MAX_WORKERS * 5  # e.g. 20 days per batch
        for batch_start in range(0, total, BATCH_SIZE):
            if stopped_early:
                break

            # Pause between batches to stay under rate limits
            if batch_start > 0:
                time.sleep(self.BATCH_COOLDOWN)

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
                            # Genuine 404 / empty data — save marker to avoid retrying
                            # Exception: never create .nodata for today (trading days
                            # only) — data may appear later in the day; retry next run.
                            if not (day == today and today_is_trading):
                                nodata = raw_dir / f"{raw_prefix}_{day.strftime('%Y%m%d')}.nodata"
                                try:
                                    nodata.touch(exist_ok=True)
                                except OSError:
                                    pass
                            batch_results[day] = ('nodata',)
                            failed_days.append(day)
                    except HTTP403Error:
                        batch_results[day] = ('403',)
                        failed_days.append(day)
                    except DownloadFailedError:
                        # Transient failure (timeout, connection, parse error, etc.)
                        # Do NOT create .nodata — data may exist, retry next run
                        batch_results[day] = ('fail',)
                        failed_days.append(day)
                    except Exception as e:
                        # Unexpected error — also do NOT create .nodata
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
        """Main loop to download and update all data categories.

        Downloads from today backwards to DEFAULT_START_DATE (2010).
        Already-downloaded days are automatically skipped (raw file on disk).
        If 5 consecutive 403 errors are hit going backwards, that category
        stops and the next category begins.
        """
        print("Starting Incremental Update...")
        t0 = time.time()

        # All categories download from DEFAULT_START_DATE to today (newest first).
        # Already-downloaded days are skipped automatically (raw file exists on disk).
        # If 5 consecutive 403 errors are hit working backwards, that category stops.
        today = datetime.date.today()
        all_days = self.get_trading_days(DEFAULT_START_DATE, today)

        categories = [
            ("Equity",             self._download_day_cm,  EQUITY_RAW,        "cm",  EQUITY_PROCESSED),
            ("Derivatives",        self._download_day_fo,  DERIVATIVES_RAW,   "fo",  DERIVATIVES_PROCESSED),
            ("Indices",            self._download_day_idx, INDICES_RAW,       "idx", INDICES_PROCESSED),
            ("Short Selling",      self._download_day_ss,  SHORTSELLING_RAW,  "ss",  SHORTSELLING_PROCESSED),
            ("Volatility",         self._download_day_vol, VOLATILITY_RAW,    "vol", VOLATILITY_PROCESSED),
            ("Market Activity",    self._download_day_ma,  MARKETACTIVITY_RAW,"ma",  MARKETACTIVITY_PROCESSED),
            ("Price Band",         self._download_day_pb,  PRICEBAND_RAW,     "pb",  PRICEBAND_PROCESSED),
            ("PE Ratio",           self._download_day_pe,  PERATIO_RAW,       "pe",  PERATIO_PROCESSED),
            ("Corporate Bonds",    self._download_day_cb,  CORPBONDS_RAW,     "cb",  CORPBONDS_PROCESSED),
            ("Delivery Positions", self._download_day_del, DELIVERY_RAW,      "del", DELIVERY_PROCESSED),
            ("WDM Daily",          self._download_day_wdm, WDM_RAW,           "wdm", WDM_PROCESSED),
        ]

        for label, download_fn, raw_dir, prefix, processed_dir in categories:
            print(f"\n--- {label} ---", flush=True)
            cat_t0 = time.time()

            # Spot-check: retry a random sample of .nodata days to recover any
            # dates that were falsely marked due to transient failures
            self._retry_nodata_sample(download_fn, raw_dir, prefix, processed_dir, label)

            self._concurrent_download(all_days, download_fn, raw_dir, prefix, label)
            self.merge_raw_to_processed(raw_dir, prefix, processed_dir, label)
            cat_elapsed = time.time() - cat_t0

            # Diagnostics: file counts and sizes
            raw_files = list(raw_dir.glob(f"{prefix}_*.parquet"))
            nodata_files = list(raw_dir.glob(f"{prefix}_*.nodata"))
            weekend_files = list(raw_dir.glob(f"{prefix}_*.nodata_weekend"))
            proc_files = list(processed_dir.glob("*.parquet"))
            raw_size = sum(f.stat().st_size for f in raw_files) / (1024 * 1024)
            proc_size = sum(f.stat().st_size for f in proc_files) / (1024 * 1024)
            print(f"  [{label}] {len(raw_files)} raw files ({raw_size:.1f} MB), "
                  f"{len(nodata_files)} no-data + {len(weekend_files)} weekend markers, "
                  f"{len(proc_files)} processed files ({proc_size:.1f} MB), "
                  f"took {cat_elapsed:.1f}s", flush=True)
            print(f"  {label} update done.", flush=True)

        elapsed = time.time() - t0
        print(f"\nUpdate Complete. Total time: {elapsed:.1f}s")

def main():
    downloader = NSEMarketDataDownloader()
    downloader.run_incremental_update()

if __name__ == '__main__':
    main()
