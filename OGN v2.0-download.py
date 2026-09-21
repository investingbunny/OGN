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
import argparse
import sys
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
import japan_macro
import nifty_macro
import schiller_macro
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
MACRO_PROCESSED = DATA_ROOT / "Macro" / "Processed"

# Shared schema for every file in Macro/Processed.
MACRO_COLUMNS = [
    'Date', 'Symbol', 'Value', 'Series', 'Name', 'Unit', 'Source',
    'Frequency', 'Description',
]
MACRO_STRING_COLUMNS = (
    'Symbol', 'Series', 'Name', 'Unit', 'Source', 'Frequency', 'Description',
)
MACRO_MAX_HISTORY_YEARS = 50   # First-run lookback when no stored history exists
MACRO_REFRESH_OVERLAP_DAYS = 10
FRED_REVISION_OVERLAP_DAYS = 400
# World Bank restates annual series for several years after first publication.
WORLDBANK_REVISION_OVERLAP_DAYS = 1825

# Comment out any line below to skip that FRED series.
# Format: (stored symbol, FRED series ID, display name, unit)
FRED_SERIES = [
    ("US02Y", "DGS2", "US Treasury 2-Year Constant Maturity Yield", "Percent"),
    ("US10Y", "DGS10", "US Treasury 10-Year Constant Maturity Yield", "Percent"),
    ("US03M", "DTB3", "US 3-Month Treasury Bill Secondary Market Rate", "Percent"),
    ("GVZ", "GVZCLS", "CBOE Gold ETF Volatility Index", "Index"),
    ("USCORPOAS", "BAMLC0A0CM", "ICE BofA US Corporate Index Option-Adjusted Spread", "Percent"),
    ("USDJPY", "DEXJPUS", "Japanese Yen to US Dollar Spot Exchange Rate", "JPY per USD"),
    ("USDINR", "DEXINUS", "Indian Rupee to US Dollar Spot Exchange Rate", "INR per USD"),
    ("FEDTARU", "DFEDTARU", "Federal Funds Target Range - Upper Limit", "Percent"),
    ("T10Y2Y", "T10Y2Y", "10-Year Minus 2-Year Treasury Constant Maturity Spread", "Percent"),
    ("T10YIE", "T10YIE", "10-Year Breakeven Inflation Rate", "Percent"),
    ("FEDASSETS", "WALCL", "Federal Reserve Total Assets", "Millions of USD"),
    ("USHYOAS", "BAMLH0A0HYM2", "ICE BofA US High Yield Index Option-Adjusted Spread", "Percent"),
    ("WTI", "DCOILWTICO", "Crude Oil Prices: West Texas Intermediate", "USD per Barrel"),
    ("EURUSD", "DEXUSEU", "US Dollar to Euro Spot Exchange Rate", "USD per EUR"),
    ("STLFSI", "STLFSI4", "St. Louis Fed Financial Stress Index", "Index"),
    ("USGDP", "GDPC1", "Real Gross Domestic Product (Quarterly)", "Billions of Chained 2017 USD"),
    ("PAYEMS", "PAYEMS", "Total Nonfarm Payrolls (Monthly)", "Thousands of Persons"),
    ("UNRATE", "UNRATE", "Unemployment Rate (Monthly)", "Percent"),
    ("USCPI", "CPIAUCSL", "Consumer Price Index for All Urban Consumers: All Items (Monthly)", "Index 1982-1984=100"),
    ("USPCE", "PCEPI", "Personal Consumption Expenditures Price Index (Monthly)", "Index 2017=100"),
    ("FEDFUNDS", "FEDFUNDS", "Effective Federal Funds Rate (Monthly)", "Percent"),
    ("US10YM", "GS10", "10-Year Treasury Constant Maturity Rate (Monthly Average)", "Percent"),
    ("HOUST", "HOUST", "Housing Starts: New Privately Owned Housing Units Started (Monthly)", "Thousands of Units"),
    ("INDPRO", "INDPRO", "Industrial Production Index (Monthly)", "Index 2017=100"),
    ("USRETAIL", "RSXFS", "Advance Retail Sales: Retail and Food Services (Monthly)", "Millions of USD"),
    # India. Only series that still return data are listed; NSE/RBI/MoSPI
    # publish no machine-readable feed this pipeline can consume directly.
    ("INTRADEBAL", "XTNTVA01INM667S", "India Merchandise Trade Balance (Monthly)", "USD"),
    ("INCPI", "INDCPIALLMINMEI", "India Consumer Price Index: All Items (Monthly)", "Index 2015=100"),
    ("INPOLRATE", "INTDSRINM193N", "India Central Bank Policy/Discount Rate (Monthly)", "Percent"),
]

FRED_SERIES_METADATA = {
    "GDPC1": (
        "Quarterly",
        "The ultimate headline measure of overall economic output adjusted for inflation. "
        "It aggregates total consumer spending, business investment, government spending, "
        "and net exports.",
    ),
    "PAYEMS": (
        "Monthly",
        "A cornerstone employment metric tracking the total number of paid U.S. workers "
        "excluding farm workers and private household employees. It serves as a real-time "
        "health check for business hiring momentum.",
    ),
    "UNRATE": (
        "Monthly",
        "Measures the percentage of the labor force that is jobless and actively seeking "
        "employment. It is a primary lagging indicator watched closely by central banks "
        "for labor market slack.",
    ),
    "CPIAUCSL": (
        "Monthly",
        "The most widely cited gauge of headline consumer inflation, measuring average "
        "price changes across a standard basket of consumer goods and services.",
    ),
    "PCEPI": (
        "Monthly",
        "The Federal Reserve's preferred measure of inflation. It accounts for consumer "
        "substitution across products better than the CPI, making it critical for monetary "
        "policy tracking.",
    ),
    "FEDFUNDS": (
        "Monthly",
        "The foundational benchmark interest rate set by the Federal Reserve, which heavily "
        "dictates broader borrowing costs across the entire financial system.",
    ),
    "GS10": (
        "Monthly",
        "The benchmark for long-term debt, driving mortgage rates, corporate bonds, and "
        "long-term financial forecasting. Its relationship with short-term rates forms "
        "the yield curve.",
    ),
    "HOUST": (
        "Monthly",
        "A powerful leading indicator tracking residential construction activity. Housing "
        "data typically reacts swiftly to shifting interest rates and consumer confidence.",
    ),
    "INDPRO": (
        "Monthly",
        "Measures real output across the manufacturing, mining, electric, and gas utilities "
        "sectors. It provides a direct lens into the physical production side of the economy, "
        "independent of services.",
    ),
    "RSXFS": (
        "Monthly",
        "Captures shifts in consumer spending across retail and food services.",
    ),
    "XTNTVA01INM667S": (
        "Monthly",
        "Measures the gap between India's merchandise exports and imports, tracking "
        "vulnerability to global commodity shocks and capital flows.",
    ),
    "INDCPIALLMINMEI": (
        "Monthly",
        "The headline retail inflation metric tracking price changes across a standard "
        "consumer basket; the core anchor for Reserve Bank of India monetary policy. "
        "The OECD stopped updating this series after March 2025.",
    ),
    "INTDSRINM193N": (
        "Monthly",
        "The benchmark rate at which the central bank lends short-term funds to commercial "
        "banks, steering liquidity, credit conditions and systemic borrowing costs. "
        "The IMF stopped updating this series after July 2022.",
    ),
}

# Comment out any line below to skip that World Bank series.
# Format: (stored symbol, indicator code, ISO3 country, display name, unit)
WORLDBANK_SERIES = [
    ("INGDPGR", "NY.GDP.MKTP.KD.ZG", "IND", "India Real GDP Growth Rate (Annual)", "Percent"),
    ("INUNRATE", "SL.UEM.TOTL.ZS", "IND", "India Unemployment Rate (Annual)", "Percent"),
]

WORLDBANK_SERIES_METADATA = {
    "NY.GDP.MKTP.KD.ZG": (
        "Annual",
        "The primary headline measure of India's overall economic output adjusted for "
        "inflation, aggregating performance across agriculture, industry and services. "
        "MoSPI publishes this quarterly but offers no machine-readable feed, so the "
        "World Bank annual series is used.",
    ),
    "SL.UEM.TOTL.ZS": (
        "Annual",
        "Share of the labour force that is jobless and actively seeking work, on the ILO "
        "modelled estimate. Stands in for the MoSPI Periodic Labour Force Survey, which "
        "has no machine-readable feed.",
    ),
}

# Comment out any line below to skip that Yahoo Finance series.
# Format: (stored symbol, Yahoo ticker, display name, unit)
YAHOO_SERIES = [
    ("GLD", "GLD", "SPDR Gold Shares ETF", "USD"),
    ("SLV", "SLV", "iShares Silver Trust ETF", "USD"),
]

# Ratios derived from series already stored in Macro/Processed.
# Format: (stored symbol, numerator symbol, denominator symbol, display name)
MACRO_RATIOS = [
    ("GLD_SLV", "GLD", "SLV", "SPDR Gold Shares / iShares Silver Trust Price Ratio"),
]

# Budget day (Feb 1) is always attempted even if it falls on a weekend.
# Actual market holidays (Republic Day, Holi, etc.) vary each year and are
# handled dynamically: a genuine 404 creates a .nodata marker so the day
# is never retried.  Weekend dates (Feb 1 on Sat/Sun) get a .nodata_weekend
# marker without making any HTTP request.  Transient failures (403, timeouts,
# etc.) do NOT create markers so they are retried on the next run.
BUDGET_DAY = (2, 1)  # (month, day) — always try this date

# Hold datetime.date objects, so pandas reports them as dtype `object`.
# They must never be swept up by the mixed-type coercion loops: stringifying
# them makes the column uncomparable against dates in the stored file.
DATE_COLUMNS = ('Date', 'Expiry')


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

    def __init__(self, initialize_nse: bool = True):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._session_lock = threading.Lock()
        self._throttle_lock = threading.Lock()
        self._last_request_time = 0.0
        self._request_count = 0
        self._last_session_init = 0.0
        self._consecutive_failures = 0
        if initialize_nse:
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
                     WDM_RAW, WDM_PROCESSED, MACRO_PROCESSED]:
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

    MACRO_MAX_RETRIES = 3  # Attempts per macro source before giving up

    def download_fred_series(self, symbol: str, series_id: str, name: str,
                             unit: str, start_date: datetime.date) -> Optional[pd.DataFrame]:
        """Downloads one FRED series from `start_date` onwards.

        Tolerates FRED's legacy `DATE` header alongside the current
        `observation_date`, and any casing of the value column. HTTP and
        content/parse failures are retried with exponential backoff.
        """
        url = (f"https://fred.stlouisfed.org/graph/fredgraph.csv"
               f"?id={series_id}&cosd={start_date.isoformat()}")

        last_error = None
        for attempt in range(self.MACRO_MAX_RETRIES):
            retry_delay = float(2 ** attempt)
            try:
                response = requests.get(url, timeout=30 + attempt * 15)
                if response.status_code == 404:
                    return None
                if response.status_code == 429:
                    try:
                        retry_delay = max(
                            retry_delay, float(response.headers.get('Retry-After', 0)))
                    except (TypeError, ValueError):
                        pass
                response.raise_for_status()
                content = response.content
                if not content.strip():
                    raise DownloadFailedError(f"Empty FRED response for {series_id}")
                head = content[:200].lstrip().lower()
                if head.startswith(b'<!doctype html') or head.startswith(b'<html'):
                    raise DownloadFailedError(
                        f"FRED returned an HTML page for {series_id}")

                try:
                    df = pd.read_csv(
                        io.BytesIO(content),
                        na_values=['.', 'NA', 'N/A', 'null', 'NaN'],
                    )
                except Exception as e:
                    raise DownloadFailedError(
                        f"Could not parse FRED CSV for {series_id}: {e}") from e

                if df.empty:
                    return None
                if len(df.columns) < 2:
                    raise DownloadFailedError(
                        f"Incomplete FRED CSV for {series_id}: {list(df.columns)}")

                date_col = self._pick_column(
                    df.columns,
                    ('observation_date', 'date', 'time_period', 'datetime', 'timestamp'),
                )
                if date_col is None:
                    date_col = df.columns[0]

                value_col = self._pick_column(
                    df.columns, (series_id.lower(), 'value'))
                if value_col is None:
                    remaining = [c for c in df.columns if c != date_col]
                    if not remaining:
                        raise DownloadFailedError(
                            f"No value column in FRED CSV for {series_id}: "
                            f"{list(df.columns)}")
                    value_col = remaining[0]

                frequency, description = FRED_SERIES_METADATA.get(
                    series_id, ('', ''))
                out = df[[date_col, value_col]].rename(
                    columns={date_col: 'Date', value_col: 'Value'})
                out['Symbol'] = symbol
                out['Series'] = series_id
                out['Name'] = name
                out['Unit'] = unit
                out['Source'] = 'FRED'
                out['Frequency'] = frequency
                out['Description'] = description

                out = self._macro_normalize(out)
                out = out[out['Date'] >= start_date]
                return out if not out.empty else None
            except (requests.exceptions.RequestException, DownloadFailedError) as e:
                last_error = e
                if attempt < self.MACRO_MAX_RETRIES - 1:
                    print(f"  [{symbol}] FRED attempt {attempt + 1}/"
                          f"{self.MACRO_MAX_RETRIES} failed: {e}. "
                          f"Retrying in {retry_delay:.0f}s.", flush=True)
                    time.sleep(retry_delay)

        raise DownloadFailedError(
            f"FRED download failed for {series_id} after "
            f"{self.MACRO_MAX_RETRIES} attempts: {last_error}")

    WORLDBANK_BASE_URL = "https://api.worldbank.org/v2"

    def download_worldbank_series(self, symbol: str, indicator: str, country: str,
                                  name: str, unit: str,
                                  start_date: datetime.date) -> Optional[pd.DataFrame]:
        """Downloads one World Bank indicator for `country` from `start_date`.

        The v2 API answers with [paging_metadata, observations]; annual points
        carry a bare year in `date`, which normalises to 1 January of that year.
        """
        end_year = datetime.date.today().year
        url = (f"{self.WORLDBANK_BASE_URL}/country/{country}/indicator/{indicator}"
               f"?format=json&per_page=1000&date={start_date.year}:{end_year}")

        last_error = None
        for attempt in range(self.MACRO_MAX_RETRIES):
            retry_delay = float(2 ** attempt)
            try:
                response = requests.get(url, timeout=30 + attempt * 15)
                if response.status_code == 404:
                    return None
                if response.status_code == 429:
                    try:
                        retry_delay = max(
                            retry_delay, float(response.headers.get('Retry-After', 0)))
                    except (TypeError, ValueError):
                        pass
                response.raise_for_status()

                try:
                    payload = response.json()
                except ValueError as e:
                    raise DownloadFailedError(
                        f"World Bank returned non-JSON for {indicator}: {e}") from e

                # The API reports its own errors inside an HTTP 200 body.
                if not isinstance(payload, list) or not payload:
                    raise DownloadFailedError(
                        f"World Bank error for {indicator}: {str(payload)[:160]}")
                if len(payload) < 2 or payload[1] is None:
                    return None

                rows = [(o.get('date'), o.get('value')) for o in payload[1]
                        if isinstance(o, dict) and o.get('value') is not None]
                if not rows:
                    return None

                frequency, description = WORLDBANK_SERIES_METADATA.get(
                    indicator, ('', ''))
                out = pd.DataFrame(rows, columns=['Date', 'Value'])
                out['Symbol'] = symbol
                out['Series'] = indicator
                out['Name'] = name
                out['Unit'] = unit
                out['Source'] = 'World Bank'
                out['Frequency'] = frequency
                out['Description'] = description

                out = self._macro_normalize(out)
                out = out[out['Date'] >= start_date]
                return out if not out.empty else None
            except (requests.exceptions.RequestException, DownloadFailedError) as e:
                last_error = e
                if attempt < self.MACRO_MAX_RETRIES - 1:
                    print(f"  [{symbol}] World Bank attempt {attempt + 1}/"
                          f"{self.MACRO_MAX_RETRIES} failed: {e}. "
                          f"Retrying in {retry_delay:.0f}s.", flush=True)
                    time.sleep(retry_delay)

        raise DownloadFailedError(
            f"World Bank download failed for {indicator} after "
            f"{self.MACRO_MAX_RETRIES} attempts: {last_error}")

    def download_yahoo_series(self, symbol: str, ticker: str, name: str, unit: str,
                              start_date: Optional[datetime.date]) -> Optional[pd.DataFrame]:
        """Downloads daily closes for one Yahoo Finance ticker.

        `start_date=None` fetches the full available history.
        """
        try:
            import yfinance as yf
        except ImportError as e:
            raise DownloadFailedError(
                "yfinance is not installed — run 'pip install yfinance'") from e

        raw = None
        last_error = None
        for attempt in range(self.MACRO_MAX_RETRIES):
            try:
                handle = yf.Ticker(ticker)
                if start_date is None:
                    raw = handle.history(period="max", interval="1d", auto_adjust=False)
                else:
                    raw = handle.history(start=start_date.isoformat(), interval="1d",
                                         auto_adjust=False)
                break
            except Exception as e:
                last_error = e
                if attempt < self.MACRO_MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
        if raw is None:
            raise DownloadFailedError(
                f"Yahoo download failed for {ticker}: {last_error}")
        if raw.empty:
            return None

        try:
            frame = raw.copy()
            if isinstance(frame.columns, pd.MultiIndex):
                # yfinance emits (field, ticker) columns when grouping is active
                frame.columns = [c[0] if isinstance(c, tuple) else c for c in frame.columns]

            price_col = self._pick_column(frame.columns, ('close', 'adj close', 'adjclose'))
            if price_col is None:
                raise DownloadFailedError(
                    f"No close column for {ticker}: {list(frame.columns)}")

            prices = frame[price_col]
            if isinstance(prices, pd.DataFrame):
                prices = prices.iloc[:, 0]

            index = pd.to_datetime(frame.index, errors='coerce')
            if getattr(index, 'tz', None) is not None:
                index = index.tz_localize(None)

            out = pd.DataFrame({
                'Date': index,
                'Value': pd.to_numeric(prices.to_numpy(), errors='coerce'),
            })
            out['Symbol'] = symbol
            out['Series'] = ticker
            out['Name'] = name
            out['Unit'] = unit
            out['Source'] = 'Yahoo'
            out['Frequency'] = 'Daily'
            out['Description'] = ''

            out = self._macro_normalize(out)
            if start_date is not None:
                out = out[out['Date'] >= start_date]
            return out if not out.empty else None
        except DownloadFailedError:
            raise
        except Exception as e:
            raise DownloadFailedError(
                f"Parse error for Yahoo ticker {ticker}: {e}") from e

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
        """Standardizes Equity data.

        Handles both UDiFF format (post July 2024, TckrSymb/OpnPric columns)
        and legacy format (SYMBOL/OPEN columns) via a unified column mapping.
        """
        df.columns = [c.strip() for c in df.columns]

        # UDiFF + Legacy column mapping → standardised names
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

        # Select important columns (drop any extras from UDiFF/legacy format)
        cols = ['Date', 'Symbol', 'Series', 'Open', 'High', 'Low', 'Close', 'Last', 'Prev Close', 'Volume', 'Turnover']
        available_cols = [c for c in cols if c in df.columns]
        df = df[available_cols].copy()

        # Parse dates and coerce numeric columns
        df['Date'] = pd.to_datetime(df['Date']).dt.date
        numeric_cols = ['Open', 'High', 'Low', 'Close', 'Last', 'Prev Close', 'Volume', 'Turnover']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df

    def _clean_fo_data(self, df: pd.DataFrame, date: datetime.date) -> pd.DataFrame:
        """Standardizes F&O data.

        Handles both UDiFF format (post July 2024, FinInstrmTp/SttlmPric columns)
        and legacy format (INSTRUMENT/SETTLE_PR columns) via a unified column mapping.
        """
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
        Filters output to only known tracked indices (NIFTY, BANKNIFTY, etc.).
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

        # Blanket fix: coerce ALL remaining object columns to numeric or string.
        # Corporate Bonds CSVs have many columns (e.g. Last Trade Yield (YTM))
        # that arrive as mixed float/str, causing pyarrow serialisation errors.
        for col in df.columns:
            if df[col].dtype == object and col not in ('Date', 'Symbol', 'Security Name'):
                converted = pd.to_numeric(df[col], errors='coerce')
                if converted.notna().sum() >= df[col].notna().sum() * 0.5:
                    df[col] = converted
                else:
                    df[col] = df[col].astype(str)
        return df

    def _clean_delivery_data(self, df: pd.DataFrame, date: datetime.date) -> pd.DataFrame:
        """Standardizes Security-wise Delivery Positions data.

        DAT format has: Record Type, Symbol, Series, Qty Traded,
        Deliverable Qty, % of Deliverable to Traded.
        Record type 20 = data rows (10 = header, 30 = trailer).
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

        # Convert numeric-looking columns; ensure no mixed-type object columns
        # remain (pyarrow cannot serialise them to parquet).
        for col in df.columns:
            if col in ('Date', 'Symbol'):
                continue
            if df[col].dtype == object:
                converted = pd.to_numeric(df[col], errors='coerce')
                # Only apply if >50% of non-null values converted successfully
                if converted.notna().sum() > 0.5 * df[col].notna().sum():
                    df[col] = converted
                else:
                    df[col] = df[col].astype(str)

        return df

    def update_processed_data(self, df: pd.DataFrame, target_dir: Path, group_col: str = 'Symbol'):
        """Appends new data to per-symbol Parquet files.

        Groups the input DataFrame by `group_col`, then for each group:
        - If a parquet file already exists, concatenates and deduplicates.
        - Otherwise, creates a new file.

        Deduplication keys depend on the data type (Equity vs Derivatives).
        """
        if df is None or df.empty:
            return

        for name, group in df.groupby(group_col):
            file_path = target_dir / f"{name}.parquet"
            if file_path.exists():
                # Append to existing file: concat → dedup → sort
                existing_df = pd.read_parquet(file_path, engine='pyarrow')
                # pd.concat automatically handles differing columns
                combined_df = pd.concat([existing_df, group], ignore_index=True)
                combined_df = combined_df.drop_duplicates(
                    subset=self._dedup_keys(combined_df), keep='last')
                combined_df = combined_df.sort_values('Date')
                combined_df.to_parquet(file_path, engine='pyarrow', compression='zstd', index=False)
            else:
                # Create new file for this symbol
                group = group.sort_values('Date')
                group.to_parquet(file_path, engine='pyarrow', compression='zstd', index=False)

    MERGE_WORKERS = 12  # Parallel threads for writing per-symbol parquet files

    @staticmethod
    def _dedup_keys(df: pd.DataFrame) -> List[str]:
        """Identity columns that make a row unique within a processed file.

        Derivatives carry many rows per date (strike x expiry x option type),
        so deduplicating on Date alone would collapse a whole day into one row.
        """
        keys = ['Date']
        for extra_key in ['Symbol', 'Instrument', 'Expiry', 'Strike Price', 'Option type']:
            if extra_key in df.columns:
                keys.append(extra_key)
        return keys

    @staticmethod
    def _restore_date_columns(df: pd.DataFrame) -> pd.DataFrame:
        """Converts ISO-string date columns back to datetime.date.

        Retry files written before the stringification bug was fixed store
        dates as text, which cannot be compared against the datetime.date
        values in the processed file.
        """
        for col in DATE_COLUMNS:
            if col in df.columns and df[col].dtype == object:
                sample = df[col].dropna()
                if not sample.empty and isinstance(sample.iloc[0], str):
                    df[col] = pd.to_datetime(df[col], errors='coerce').dt.date
        return df

    def merge_raw_to_processed(self, raw_dir: Path, raw_prefix: str, target_dir: Path, label: str, group_col: str = 'Symbol'):
        """Merges raw day-parquet files from disk into per-symbol processed files.

        Strategy for speed and memory safety:
        1. Process files in mega-batches (MERGE_MEGA_BATCH files each) to
           bound memory usage.  Each mega-batch does the full read → consolidate
           → write cycle.  Stamp file is updated after each mega-batch so
           progress is preserved if a crash occurs.
        2. Within each mega-batch, read raw files in parallel (READER_THREADS).
        3. Pre-consolidate per-symbol data and cast dtypes once (not per-write).
        4. Smart dedup: if new dates don't overlap existing processed file,
           skip drop_duplicates + sort (just append).
        5. Write per-symbol files in parallel threads (I/O bound, releases GIL).
        6. Per-mega-batch timeout (MERGE_TIMEOUT_S): if exceeded, the batch is
           skipped and an error is printed, but the script continues.
        """
        # --- Phase 0: Retry previously failed symbol writes ---
        retry_dir = raw_dir / ".retry"
        if retry_dir.exists():
            retry_files = sorted(retry_dir.glob("*.parquet"))
            if retry_files:
                print(f"  [{label}] Retrying {len(retry_files)} previously failed symbols...", flush=True)
                retry_ok = 0
                retry_fail = 0
                for rf in retry_files:
                    symbol = rf.stem
                    try:
                        new_data = pd.read_parquet(rf, engine='pyarrow')
                        new_data = self._restore_date_columns(new_data)
                        # Coerce object columns to clean types
                        for col in new_data.columns:
                            if new_data[col].dtype == object and col not in DATE_COLUMNS:
                                conv = pd.to_numeric(new_data[col], errors='coerce')
                                if conv.notna().sum() >= new_data[col].notna().sum() * 0.5:
                                    new_data[col] = conv
                                else:
                                    new_data[col] = new_data[col].astype(str)
                        file_path = target_dir / f"{symbol}.parquet"
                        if file_path.exists():
                            existing = pd.read_parquet(file_path, engine='pyarrow')
                            existing = self._restore_date_columns(existing)
                            combined = pd.concat([existing, new_data], ignore_index=True)
                            combined = combined.drop_duplicates(
                                subset=self._dedup_keys(combined), keep='last')
                            combined = combined.sort_values('Date')
                            del existing
                        else:
                            combined = new_data.sort_values('Date')
                        # Coerce again after concat with existing (may re-introduce mixed types)
                        for col in combined.columns:
                            if combined[col].dtype == object and col not in DATE_COLUMNS:
                                conv = pd.to_numeric(combined[col], errors='coerce')
                                if conv.notna().sum() >= combined[col].notna().sum() * 0.5:
                                    combined[col] = conv
                                else:
                                    combined[col] = combined[col].astype(str)
                        combined.to_parquet(file_path, engine='pyarrow', compression='zstd', index=False)
                        rf.unlink()
                        retry_ok += 1
                    except Exception as e:
                        retry_fail += 1
                        if retry_fail <= 3:
                            print(f"    Retry failed for {symbol}: {e}")
                if retry_ok:
                    print(f"  [{label}] Retried {retry_ok} symbols successfully.", flush=True)
                if retry_fail:
                    print(f"  [{label}] {retry_fail} retries still failing.", flush=True)
                # Clean up empty retry dir
                remaining = list(retry_dir.glob("*.parquet"))
                if not remaining:
                    try:
                        retry_dir.rmdir()
                    except Exception:
                        pass

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

        MERGE_MEGA_BATCH = 500    # Files per mega-batch (memory control)
        MERGE_TIMEOUT_S = 120     # Max seconds per mega-batch before giving up
        READ_CHUNK = 200          # Files per read chunk within a mega-batch
        READER_THREADS = 8        # Parallel readers within each chunk
        total_symbols_written = 0

        for mega_start in range(0, total_files, MERGE_MEGA_BATCH):
            mega_end = min(mega_start + MERGE_MEGA_BATCH, total_files)
            mega_files = files_to_merge[mega_start:mega_end]
            mega_t0 = time.time()

            try:
                # --- Phase 1: Read raw files in chunks with parallel I/O ---
                symbol_new_data: Dict[str, List[pd.DataFrame]] = {}
                dedup_cols = None
                read_errors = 0

                def _read_one(f: Path):
                    try:
                        return pd.read_parquet(f, engine='pyarrow')
                    except Exception as e:
                        return e

                for chunk_start in range(0, len(mega_files), READ_CHUNK):
                    # Timeout check
                    if time.time() - mega_t0 > MERGE_TIMEOUT_S:
                        print(f"  [{label}] Merge timeout ({MERGE_TIMEOUT_S}s) exceeded "
                              f"during read phase at file {mega_start + chunk_start}/{total_files}. "
                              f"Remaining files will be retried next run.", flush=True)
                        raise TimeoutError("merge read timeout")

                    chunk_end = min(chunk_start + READ_CHUNK, len(mega_files))
                    chunk_files = mega_files[chunk_start:chunk_end]

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

                    if dedup_cols is None:
                        dedup_cols = ['Date']
                        for extra_key in ['Symbol', 'Instrument', 'Expiry', 'Strike Price', 'Option type']:
                            if extra_key in combined.columns:
                                dedup_cols.append(extra_key)

                    for name, group in combined.groupby(group_col):
                        symbol_new_data.setdefault(name, []).append(group)

                    del combined

                    progress_file = mega_start + chunk_end
                    if progress_file < total_files:
                        elapsed = time.time() - t0
                        print(f"  [{label}] Read {progress_file}/{total_files} raw files ({elapsed:.1f}s)...", flush=True)

                if not symbol_new_data:
                    # No data in this mega-batch — still mark as merged
                    already_merged |= {f.name for f in mega_files}
                    try:
                        stamp_file.write_text('\n'.join(sorted(already_merged)))
                    except Exception:
                        pass
                    continue

                # Timeout check before consolidation
                if time.time() - mega_t0 > MERGE_TIMEOUT_S:
                    print(f"  [{label}] Merge timeout ({MERGE_TIMEOUT_S}s) before consolidation. "
                          f"Skipping batch {mega_start}-{mega_end}, retry next run.", flush=True)
                    del symbol_new_data
                    continue

                # --- Phase 1.5: Pre-consolidate per-symbol DataFrames ---
                for name in list(symbol_new_data.keys()):
                    dfs = symbol_new_data[name]
                    merged = pd.concat(dfs, ignore_index=True) if len(dfs) > 1 else dfs[0]
                    for col in merged.columns:
                        if merged[col].dtype == object and col != 'Date':
                            # Try numeric first (handles mixed float/str columns)
                            converted = pd.to_numeric(merged[col], errors='coerce')
                            if converted.notna().sum() >= merged[col].notna().sum() * 0.5:
                                merged[col] = converted
                            else:
                                merged[col] = merged[col].astype(str)
                    symbol_new_data[name] = merged
                    del dfs

                num_symbols = len(symbol_new_data)
                read_elapsed = time.time() - t0
                if read_errors > 3:
                    print(f"  [{label}] ({read_errors - 3} more read errors suppressed)")
                print(f"  [{label}] Batch {mega_start}-{mega_end}: {len(mega_files)} files, "
                      f"{num_symbols} symbols, read in {time.time() - mega_t0:.1f}s. Writing...", flush=True)

                # --- Phase 2: Write each processed file ONCE, in parallel ---
                final_dedup_cols = dedup_cols or ['Date']
                write_errors = []

                def _merge_and_write(item):
                    name, new_data = item
                    file_path = target_dir / f"{name}.parquet"
                    merged = None
                    try:
                        if file_path.exists():
                            existing = pd.read_parquet(file_path, engine='pyarrow')
                            new_min_date = new_data['Date'].min()
                            existing_max_date = existing['Date'].max()
                            if new_min_date > existing_max_date:
                                new_sorted = new_data.sort_values('Date')
                                merged = pd.concat([existing, new_sorted], ignore_index=True)
                                del new_sorted
                            else:
                                merged = pd.concat([existing, new_data], ignore_index=True)
                                merged = merged.drop_duplicates(subset=final_dedup_cols, keep='last')
                                merged = merged.sort_values('Date')
                            del existing
                        else:
                            merged = new_data.sort_values('Date')
                        del new_data
                        # Safety net: coerce any remaining mixed-type object columns
                        # so pyarrow can serialise without "Expected bytes / got float"
                        for col in merged.columns:
                            if merged[col].dtype == object and col != 'Date':
                                conv = pd.to_numeric(merged[col], errors='coerce')
                                if conv.notna().sum() >= merged[col].notna().sum() * 0.5:
                                    merged[col] = conv
                                else:
                                    merged[col] = merged[col].astype(str)
                        merged.to_parquet(file_path, engine='pyarrow', compression='zstd', index=False)
                        del merged
                    except Exception as e:
                        write_errors.append(f"{name}: {e}")
                        # Save failed data so it can be retried on next run
                        try:
                            retry_dir = raw_dir / ".retry"
                            retry_dir.mkdir(exist_ok=True)
                            save_df = merged if merged is not None else new_data
                            for c in save_df.columns:
                                if save_df[c].dtype == object and c not in DATE_COLUMNS:
                                    save_df[c] = save_df[c].astype(str)
                            save_df.to_parquet(retry_dir / f"{name}.parquet",
                                               engine='pyarrow', compression='zstd', index=False)
                        except Exception:
                            pass  # best-effort retry save

                with ThreadPoolExecutor(max_workers=self.MERGE_WORKERS) as pool:
                    list(pool.map(_merge_and_write, symbol_new_data.items()))

                total_symbols_written += num_symbols
                del symbol_new_data

                if write_errors:
                    for err in write_errors[:5]:
                        print(f"  [{label}] Write error: {err}")

                # Update stamp after each mega-batch (crash-safe)
                already_merged |= {f.name for f in mega_files}
                try:
                    stamp_file.write_text('\n'.join(sorted(already_merged)))
                except Exception as e:
                    print(f"  [{label}] Warning: could not update merge stamp: {e}")

                batch_elapsed = time.time() - mega_t0
                print(f"  [{label}] Batch {mega_start}-{mega_end} complete in {batch_elapsed:.1f}s "
                      f"({num_symbols} symbols written).", flush=True)

            except TimeoutError:
                # Already printed message above — just skip this batch
                pass
            except MemoryError:
                print(f"  [{label}] Out of memory during merge batch {mega_start}-{mega_end}. "
                      f"Skipping — will retry next run with smaller data.", flush=True)
                try:
                    del symbol_new_data
                except NameError:
                    pass
                import gc; gc.collect()
            except Exception as e:
                print(f"  [{label}] Merge error in batch {mega_start}-{mega_end}: "
                      f"{type(e).__name__}: {e}", flush=True)
                try:
                    del symbol_new_data
                except NameError:
                    pass

        elapsed = time.time() - t0
        print(f"  [{label}] Merge complete: {total_files} files → {total_symbols_written} symbol-writes "
              f"in {elapsed:.1f}s", flush=True)

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
        """Download Short Selling report for one day. Returns (day, df_or_None)."""
        df = self.download_short_selling(day)
        return (day, df)

    def _download_day_vol(self, day: datetime.date) -> tuple:
        """Download Daily Volatility report for one day. Returns (day, df_or_None)."""
        df = self.download_daily_volatility(day)
        return (day, df)

    def _download_day_ma(self, day: datetime.date) -> tuple:
        """Download Market Activity report for one day. Returns (day, df_or_None)."""
        df = self.download_market_activity(day)
        return (day, df)

    def _download_day_pb(self, day: datetime.date) -> tuple:
        """Download Price Band report for one day. Returns (day, df_or_None)."""
        df = self.download_price_band(day)
        return (day, df)

    def _download_day_pe(self, day: datetime.date) -> tuple:
        """Download PE Ratio report for one day. Returns (day, df_or_None)."""
        df = self.download_pe_ratio(day)
        return (day, df)

    def _download_day_cb(self, day: datetime.date) -> tuple:
        """Download Corporate Bonds report for one day. Returns (day, df_or_None)."""
        df = self.download_corp_bonds(day)
        return (day, df)

    def _download_day_del(self, day: datetime.date) -> tuple:
        """Download Delivery Positions report for one day. Returns (day, df_or_None)."""
        df = self.download_delivery_positions(day)
        return (day, df)

    def _download_day_wdm(self, day: datetime.date) -> tuple:
        """Download WDM Daily Report for one day. Returns (day, df_or_None)."""
        df = self.download_wdm_daily(day)
        return (day, df)

    NODATA_RETRY_SAMPLE = 10  # Number of random .nodata days to retry per category

    @staticmethod
    def _pick_column(columns, candidates) -> Optional[str]:
        """Case- and whitespace-insensitive column lookup."""
        lookup = {str(c).strip().lower(): c for c in columns}
        for candidate in candidates:
            if candidate in lookup:
                return lookup[candidate]
        return None

    @staticmethod
    def _macro_normalize(df: Optional[pd.DataFrame]) -> pd.DataFrame:
        """Coerces any macro frame to MACRO_COLUMNS with date/float typing.

        Guards the ratio join, where a datetime64 'Date' in one file and a
        python-date 'Date' in another would silently match nothing. Metadata
        is normalized to single-line Python strings for parquet and charts.
        """
        if df is None or df.empty:
            return pd.DataFrame(columns=MACRO_COLUMNS)

        out = df.copy()
        for col in MACRO_COLUMNS:
            if col not in out.columns:
                out[col] = pd.NA
        out = out[MACRO_COLUMNS]

        dates = pd.to_datetime(out['Date'], errors='coerce', utc=True)
        out['Date'] = dates.dt.tz_convert(None).dt.normalize()
        values = out['Value']
        if (pd.api.types.is_object_dtype(values.dtype)
                or pd.api.types.is_string_dtype(values.dtype)):
            values = values.astype(str).str.replace(',', '', regex=False).str.strip()
        out['Value'] = pd.to_numeric(values, errors='coerce')

        out = out[out['Date'].notna() & out['Value'].notna()].copy()
        if out.empty:
            return pd.DataFrame(columns=MACRO_COLUMNS)

        out['Date'] = out['Date'].dt.date
        for col in MACRO_STRING_COLUMNS:
            text = out[col].astype('string').fillna('')
            out[col] = (text.str.normalize('NFKC')
                             .str.replace(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]',
                                          ' ', regex=True)
                             .str.replace(r'\s+', ' ', regex=True)
                             .str.strip()
                             .astype(object))
        return (out.drop_duplicates(subset=['Date'], keep='last')
                   .sort_values('Date')
                   .reset_index(drop=True))

    def _macro_read(self, symbol: str) -> Optional[pd.DataFrame]:
        """Reads a stored Macro series, or None if absent/unreadable/empty."""
        path = MACRO_PROCESSED / f"{symbol}.parquet"
        if not path.exists():
            return None
        try:
            stored = pd.read_parquet(path, engine='pyarrow')
        except Exception as e:
            print(f"  [{symbol}] Could not read stored file ({e}) — rebuilding.", flush=True)
            return None
        normalized = self._macro_normalize(stored)
        return normalized if not normalized.empty else None

    @staticmethod
    def _macro_incremental_start(
            existing: Optional[pd.DataFrame],
            overlap_days: int = MACRO_REFRESH_OVERLAP_DAYS) -> Optional[datetime.date]:
        """Start date for an incremental refresh, or None when no history exists."""
        if existing is None or existing.empty or 'Date' not in existing.columns:
            return None
        last = pd.Timestamp(existing['Date'].max())
        return (last - pd.Timedelta(days=overlap_days)).date()

    def _macro_write(self, symbol: str, new_df: pd.DataFrame,
                     existing: Optional[pd.DataFrame]) -> pd.DataFrame:
        """Merges new rows into a stored Macro series and writes atomically."""
        combined = self._macro_normalize(new_df)
        if existing is not None and not existing.empty:
            # New rows go last so drop_duplicates(keep='last') prefers them.
            combined = self._macro_normalize(
                pd.concat([self._macro_normalize(existing), combined], ignore_index=True))
        if combined.empty:
            raise DownloadFailedError(f"No usable rows to write for {symbol}")

        for col in MACRO_STRING_COLUMNS:
            populated = combined.loc[combined[col] != '', col]
            if not populated.empty:
                combined.loc[combined[col] == '', col] = populated.iloc[-1]

        target = MACRO_PROCESSED / f"{symbol}.parquet"
        temp_target = target.with_suffix('.parquet.tmp')
        try:
            combined.to_parquet(temp_target, engine='pyarrow', compression='zstd', index=False)
            temp_target.replace(target)
        except Exception:
            temp_target.unlink(missing_ok=True)
            raise
        return combined

    def download_japan_series(self, symbol: str, start_date: datetime.date) -> Optional[pd.DataFrame]:
        """Fetch an exact Japan indicator without silently substituting a proxy."""
        definition = japan_macro.JAPAN_SERIES[symbol]
        provider = definition['provider']
        if provider == 'FRED':
            return self.download_fred_series(
                symbol, definition['series'], definition['name'], definition['unit'], start_date)
        if provider == 'Yahoo':
            return self.download_yahoo_series(
                symbol, definition['series'], definition['name'], definition['unit'], start_date)
        if provider == 'Derived':
            inputs = []
            for dependency, expected_unit in [('FEDTARU', 'Percent'), ('JPPOLRATE', 'Percent'),
                                               ('JPJPYIV', 'Percent annualized')]:
                frame = self._macro_read(dependency)
                if frame is None:
                    return None
                if not frame['Unit'].eq(expected_unit).all():
                    raise DownloadFailedError(f'Unexpected units for {dependency}: expected {expected_unit}')
                inputs.append(frame)
            return japan_macro.calculate_carry_to_risk(*inputs)
        if provider is None:
            return None

        last_error = None
        for attempt in range(self.MACRO_MAX_RETRIES):
            try:
                if provider == 'BIS':
                    return japan_macro.download_bis_series(definition, start_date)
                if provider == 'CFTC':
                    return japan_macro.download_cftc_jpy(start_date)
                if provider == 'ESRI':
                    return japan_macro.download_esri_leading()
                if provider == 'MOF':
                    return japan_macro.download_mof_current_account()
                if provider == 'Dashboard':
                    return japan_macro.download_dashboard_series(definition, start_date)
                raise ValueError(f'Unsupported Japan source: {provider}')
            except (requests.exceptions.RequestException, ValueError, KeyError, zipfile.BadZipFile) as error:
                last_error = error
                if attempt < self.MACRO_MAX_RETRIES - 1:
                    delay = float(2 ** attempt)
                    response = getattr(error, 'response', None)
                    if response is not None and response.status_code == 429:
                        try:
                            delay = max(delay, float(response.headers.get('Retry-After', 0)))
                        except (TypeError, ValueError):
                            pass
                    print(f"  [{symbol}] {provider} attempt {attempt + 1}/"
                          f"{self.MACRO_MAX_RETRIES} failed: {error}. Retrying in {delay:.0f}s.",
                          flush=True)
                    time.sleep(delay)
        raise DownloadFailedError(f'Japan download failed for {symbol}: {last_error}')

    def update_japan_series(self):
        """Refresh the Japan group with common metadata and isolated failures."""
        print('\n--- Japan Macro and Carry Trade ---', flush=True)
        for symbol, definition in japan_macro.JAPAN_SERIES.items():
            if definition['provider'] is None:
                print(f"  [{symbol}] Unavailable: {definition['unavailable']}", flush=True)
                continue
            try:
                existing = self._macro_read(symbol)
                overlap = definition.get(
                    'overlap_days', MACRO_REFRESH_OVERLAP_DAYS
                    if definition['provider'] == 'Yahoo' else FRED_REVISION_OVERLAP_DAYS)
                start = self._macro_incremental_start(existing, overlap)
                if start is None or definition.get('full_refresh') or definition['provider'] == 'Derived':
                    start = (pd.Timestamp(datetime.date.today())
                             - pd.DateOffset(years=MACRO_MAX_HISTORY_YEARS)).date()
                frame = self.download_japan_series(symbol, start)
                if frame is None or frame.empty:
                    reason = definition.get('unavailable', f'No new data since {start}.')
                    print(f'  [{symbol}] {reason}', flush=True)
                    continue
                frame = frame.copy()
                frame['Symbol'] = symbol
                for column in ['Series', 'Name', 'Unit', 'Source', 'Frequency', 'Description']:
                    frame[column] = definition[column.lower()]
                frame = self._macro_normalize(frame)
                frame = frame[(frame['Date'] >= start) & np.isfinite(frame['Value'])]
                if frame.empty:
                    print(f'  [{symbol}] No usable observations since {start}.', flush=True)
                    continue
                combined = self._macro_write(symbol, frame, existing)
                print(f"  [{symbol}] +{len(frame):,} rows -> {len(combined):,} total "
                      f"({combined['Date'].min()} to {combined['Date'].max()}).", flush=True)
            except Exception as error:
                print(f'  [{symbol}] Update failed; stored data retained: '
                      f'{type(error).__name__}: {error}', flush=True)

    def _write_valuation_series(self, symbol, definition, frame, existing):
        """Apply the shared schema and atomic write to a market-specific valuation."""
        if frame is None or frame.empty:
            print(f"  [{symbol}] {definition.get('unavailable', 'No usable source observations.')}", flush=True)
            return existing
        frame = frame.copy()
        frame['Symbol'] = symbol
        for column in ['Series', 'Name', 'Unit', 'Source', 'Frequency', 'Description']:
            frame[column] = definition[column.lower()]
        if 'Estimated' in frame:
            frame.loc[frame['Estimated'].eq(True), 'Description'] += ' Source marks this observation as estimated.'
        frame = self._macro_normalize(frame)
        frame = frame[np.isfinite(frame['Value']) & (frame['Date'] <= datetime.date.today())]
        if frame.empty:
            raise DownloadFailedError(f'No finite historical observations for {symbol}')
        if definition.get('full_refresh') and existing is not None and not existing.empty:
            if (frame['Date'].min() > existing['Date'].min()
                    or frame['Date'].max() < existing['Date'].max()):
                raise DownloadFailedError(f'Truncated full-history response for {symbol}; stored history retained')
            existing = None
        combined = self._macro_write(symbol, frame, existing)
        print(f"  [{symbol}] +{len(frame):,} rows -> {len(combined):,} total "
              f"({combined['Date'].min()} to {combined['Date'].max()}).", flush=True)
        return combined

    def download_schiller_series(self, symbol, start_date, workbook_cache=None):
        """Fetch US-only valuations, retrying HTTP and parser failures together."""
        definition = schiller_macro.SCHILLER_SERIES[symbol]
        if definition['provider'] is None:
            return None
        cache = workbook_cache if workbook_cache is not None else {}
        last_error = None
        for attempt in range(self.MACRO_MAX_RETRIES):
            try:
                if definition['provider'] == 'Shiller':
                    if 'shiller' not in cache:
                        cache['shiller'] = schiller_macro.download_shiller_workbook()
                    frame = cache['shiller'][symbol].copy()
                elif definition['provider'] == 'Multpl':
                    frame = schiller_macro.download_multpl_series(definition)
                else:
                    raise ValueError('Unsupported US valuation provider')
                dates = pd.to_datetime(frame['Date'], errors='raise').dt.date
                return frame[dates >= start_date].copy()
            except Exception as error:
                last_error = error
                if attempt < self.MACRO_MAX_RETRIES - 1:
                    delay = float(2 ** attempt)
                    response = getattr(error, 'response', None)
                    if response is not None and response.status_code == 429:
                        try:
                            delay = max(delay, float(response.headers.get('Retry-After', 0)))
                        except (TypeError, ValueError):
                            pass
                    print(f'  [{symbol}] Attempt {attempt + 1}/{self.MACRO_MAX_RETRIES} '
                          f'failed: {error}. Retrying in {delay:.0f}s.', flush=True)
                    time.sleep(delay)
        raise DownloadFailedError(f'US Schiller download failed for {symbol}: {last_error}')

    def update_schiller_series(self):
        """Refresh the US group without clipping nineteenth-century source history."""
        print('\n--- US Schiller Valuation ---', flush=True)
        workbook_cache = {}
        workbook_failed = False
        for symbol, definition in schiller_macro.SCHILLER_SERIES.items():
            if definition['provider'] is None:
                print(f"  [{symbol}] Unavailable: {definition['unavailable']}", flush=True)
                continue
            if definition['provider'] == 'Shiller' and workbook_failed:
                print(f'  [{symbol}] Workbook unavailable; stored history retained.', flush=True)
                continue
            try:
                existing = self._macro_read(symbol)
                start = self._macro_incremental_start(existing, FRED_REVISION_OVERLAP_DAYS)
                if start is None or definition.get('full_refresh'):
                    start = datetime.date(1871, 1, 1)
                frame = self.download_schiller_series(symbol, start, workbook_cache)
                self._write_valuation_series(symbol, definition, frame, existing)
            except Exception as error:
                if definition['provider'] == 'Shiller' and 'shiller' not in workbook_cache:
                    workbook_failed = True
                print(f'  [{symbol}] Update failed; stored data retained: '
                      f'{type(error).__name__}: {error}', flush=True)

    def update_india_schiller_series(self):
        """Update Indian-only valuation outputs; never use US inputs or substitutes."""
        print('\n--- India Schiller / NIFTY Valuation ---', flush=True)
        for symbol, definition in nifty_macro.NIFTY_SERIES.items():
            if definition['provider'] is None:
                print(f"  [{symbol}] Unavailable: {definition['unavailable']}", flush=True)
        cpi_symbol = nifty_macro.INDIA_CPI_SYMBOL
        cpi = self._macro_read(cpi_symbol)
        try:
            definition = nifty_macro.NIFTY_SERIES[cpi_symbol]
            start = self._macro_incremental_start(cpi, FRED_REVISION_OVERLAP_DAYS)
            if start is None:
                start = datetime.date(1960, 1, 1)
            fresh = self.download_fred_series(
                cpi_symbol, nifty_macro.INDIA_CPI_SERIES, definition['name'],
                nifty_macro.INDIA_CPI_UNIT, start)
            if fresh is not None and not fresh.empty:
                nifty_macro.validate_india_cpi(fresh)
            cpi = self._write_valuation_series(cpi_symbol, definition, fresh, cpi)
        except Exception as error:
            print(f'  [{cpi_symbol}] Refresh failed; using stored Indian CPI only: {error}', flush=True)
        index_path = INDICES_PROCESSED / 'NIFTY.parquet'
        if not index_path.exists():
            print('  [NIFTY] No stored NSE NIFTY index history. Valuation outputs unavailable.', flush=True)
            return
        try:
            index_frame = pd.read_parquet(index_path, engine='pyarrow')
            monthly = nifty_macro.nifty_monthly_valuation(index_frame)
            metrics = nifty_macro.calculate_nifty_metrics(monthly)
        except Exception as error:
            print(f'  [NIFTY] Invalid Indian index history; existing valuations retained: {error}', flush=True)
            return
        try:
            metrics['NIFTYCAPE'] = nifty_macro.calculate_nifty_cape(monthly, cpi)
        except Exception as error:
            print(f'  [NIFTYCAPE] Calculation rejected; stored data retained: {error}', flush=True)
        for symbol, definition in nifty_macro.NIFTY_SERIES.items():
            if definition['provider'] not in ('Stored NSE', 'Derived'):
                continue
            try:
                self._write_valuation_series(
                    symbol, definition, metrics.get(symbol), self._macro_read(symbol))
            except Exception as error:
                print(f'  [{symbol}] Update failed; stored data retained: {error}', flush=True)

    def update_fred_series(self):
        """Incrementally refreshes all enabled series in FRED_SERIES."""
        if not FRED_SERIES:
            return

        print("\n--- FRED Macro Series ---", flush=True)
        for symbol, series_id, name, unit in FRED_SERIES:
            try:
                existing = self._macro_read(symbol)
                overlap_days = (
                    FRED_REVISION_OVERLAP_DAYS
                    if series_id in FRED_SERIES_METADATA
                    else MACRO_REFRESH_OVERLAP_DAYS
                )
                start = self._macro_incremental_start(existing, overlap_days)
                if start is None:
                    start = (pd.Timestamp(datetime.date.today())
                             - pd.DateOffset(years=MACRO_MAX_HISTORY_YEARS)).date()

                df = self.download_fred_series(symbol, series_id, name, unit, start)
                if df is None or df.empty:
                    print(f"  [{symbol}] No new data since {start}.", flush=True)
                    continue

                combined = self._macro_write(symbol, df, existing)
                print(f"  [{symbol}] +{len(df):,} rows from {start} -> {len(combined):,} total "
                      f"({combined['Date'].min()} to {combined['Date'].max()}).", flush=True)
            except Exception as e:
                print(f"  [{symbol}] Update failed: {type(e).__name__}: {e}", flush=True)

    def update_worldbank_series(self):
        """Incrementally refreshes all enabled series in WORLDBANK_SERIES."""
        if not WORLDBANK_SERIES:
            return

        print("\n--- World Bank Macro Series ---", flush=True)
        for symbol, indicator, country, name, unit in WORLDBANK_SERIES:
            try:
                existing = self._macro_read(symbol)
                start = self._macro_incremental_start(
                    existing, WORLDBANK_REVISION_OVERLAP_DAYS)
                if start is None:
                    start = (pd.Timestamp(datetime.date.today())
                             - pd.DateOffset(years=MACRO_MAX_HISTORY_YEARS)).date()

                df = self.download_worldbank_series(
                    symbol, indicator, country, name, unit, start)
                if df is None or df.empty:
                    print(f"  [{symbol}] No new data since {start}.", flush=True)
                    continue

                combined = self._macro_write(symbol, df, existing)
                print(f"  [{symbol}] +{len(df):,} rows from {start} -> {len(combined):,} total "
                      f"({combined['Date'].min()} to {combined['Date'].max()}).", flush=True)
            except Exception as e:
                print(f"  [{symbol}] Update failed: {type(e).__name__}: {e}", flush=True)

    def update_yahoo_series(self):
        """Incrementally refreshes all enabled series in YAHOO_SERIES."""
        if not YAHOO_SERIES:
            return
        print("\n--- Yahoo Finance Series ---", flush=True)
        for symbol, ticker, name, unit in YAHOO_SERIES:
            try:
                existing = self._macro_read(symbol)
                start = self._macro_incremental_start(existing)

                df = self.download_yahoo_series(symbol, ticker, name, unit, start)
                if df is None or df.empty:
                    print(f"  [{symbol}] No new data for {ticker}.", flush=True)
                    continue

                combined = self._macro_write(symbol, df, existing)
                scope = f"from {start}" if start else "full history"
                print(f"  [{symbol}] +{len(df):,} rows ({scope}) -> {len(combined):,} total "
                      f"({combined['Date'].min()} to {combined['Date'].max()}).", flush=True)
            except Exception as e:
                print(f"  [{symbol}] Update failed: {type(e).__name__}: {e}", flush=True)

    def update_macro_ratios(self):
        """Incrementally recomputes ratios derived from stored Macro series."""
        if not MACRO_RATIOS:
            return

        print("\n--- Derived Macro Ratios ---", flush=True)
        for symbol, num_symbol, den_symbol, name in MACRO_RATIOS:
            try:
                numerator = self._macro_read(num_symbol)
                denominator = self._macro_read(den_symbol)
                if numerator is None or numerator.empty or denominator is None or denominator.empty:
                    print(f"  [{symbol}] Skipped - {num_symbol} or {den_symbol} "
                          f"not available.", flush=True)
                    continue

                existing = self._macro_read(symbol)
                start = self._macro_incremental_start(existing)

                merged = pd.merge(
                    numerator[['Date', 'Value']].rename(columns={'Value': 'Numerator'}),
                    denominator[['Date', 'Value']].rename(columns={'Value': 'Denominator'}),
                    on='Date', how='inner')
                if start is not None:
                    merged = merged[merged['Date'] >= start]
                merged = merged[merged['Denominator'].notna() & (merged['Denominator'] != 0)]
                if merged.empty:
                    print(f"  [{symbol}] No new dates to compute.", flush=True)
                    continue

                df = pd.DataFrame({
                    'Date': merged['Date'].to_numpy(),
                    'Symbol': symbol,
                    'Value': (merged['Numerator'] / merged['Denominator']).to_numpy(),
                    'Series': f"{num_symbol}/{den_symbol}",
                    'Name': name,
                    'Unit': 'Ratio',
                    'Source': 'Derived',
                    'Frequency': numerator['Frequency'].iloc[-1],
                    'Description': f"Ratio of {num_symbol} to {den_symbol}, "
                                   f"computed on their common dates.",
                })[MACRO_COLUMNS]

                combined = self._macro_write(symbol, df, existing)
                print(f"  [{symbol}] +{len(df):,} rows -> {len(combined):,} total "
                      f"({combined['Date'].min()} to {combined['Date'].max()}).", flush=True)
            except Exception as e:
                print(f"  [{symbol}] Update failed: {type(e).__name__}: {e}", flush=True)

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
                    for _c in df.columns:
                        if df[_c].dtype == object and _c != 'Date':
                            _conv = pd.to_numeric(df[_c], errors='coerce')
                            if _conv.notna().sum() >= df[_c].notna().sum() * 0.5:
                                df[_c] = _conv
                            else:
                                df[_c] = df[_c].astype(str)
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

        # Skip days that already have raw files, .nodata, or .nodata_weekend markers.
        # This avoids redundant HTTP requests on subsequent runs.
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

        # Reverse: process newest days first (more likely to succeed, updates faster)
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

        # Process in batches to allow concurrent downloads while tracking 403 streaks.
        # Batch size = MAX_WORKERS * 5 to balance parallelism with 403 detection.
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
                                # Safety net: coerce any remaining mixed-type
                                # object columns so pyarrow can serialise them.
                                for _c in df.columns:
                                    if df[_c].dtype == object and _c != 'Date':
                                        _conv = pd.to_numeric(df[_c], errors='coerce')
                                        if _conv.notna().sum() >= df[_c].notna().sum() * 0.5:
                                            df[_c] = _conv
                                        else:
                                            df[_c] = df[_c].astype(str)
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

            # Check consecutive 403 streak in date order (newest first = batch_days order).
            # If we hit MAX_CONSECUTIVE_403 in a row, older data is likely unavailable
            # on NSE, so stop going further back for this category.
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

        For each category the pipeline is:
          1. Retry a random sample of .nodata days (recover false negatives)
          2. Download missing days concurrently (newest-first)
          3. Merge raw day-parquet files into per-symbol processed files
        """
        print("Starting Incremental Update...")
        t0 = time.time()

        # All categories download from DEFAULT_START_DATE to today (newest first).
        # Already-downloaded days are skipped automatically (raw file exists on disk).
        # If 5 consecutive 403 errors are hit working backwards, that category stops.
        today = datetime.date.today()
        all_days = self.get_trading_days(DEFAULT_START_DATE, today)

        self.update_fred_series()
        self.update_worldbank_series()
        self.update_yahoo_series()
        self.update_macro_ratios()
        self.update_japan_series()
        self.update_schiller_series()

        # ── Category list ──────────────────────────────────────────────
        # Comment out any line below to skip that category entirely.
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

        self.update_india_schiller_series()
        elapsed = time.time() - t0
        print(f"\nUpdate Complete. Total time: {elapsed:.1f}s")

def main():
    # Legacy Windows code pages cannot encode this script's Unicode output.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description='Refresh NSE and macro market data.')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--japan-only', action='store_true',
                       help='Refresh only Japan macro series, without contacting NSE.')
    group.add_argument('--schiller-only', action='store_true',
                       help='Refresh only US Schiller valuation sources.')
    group.add_argument('--india-schiller-only', action='store_true',
                       help='Refresh Indian CPI and valuations from stored NSE NIFTY history.')
    args = parser.parse_args()
    macro_only = args.japan_only or args.schiller_only or args.india_schiller_only
    downloader = NSEMarketDataDownloader(initialize_nse=not macro_only)
    if args.japan_only:
        downloader.update_japan_series()
    elif args.schiller_only:
        downloader.update_schiller_series()
    elif args.india_schiller_only:
        downloader.update_india_schiller_series()
    else:
        downloader.run_incremental_update()

if __name__ == '__main__':
    main()
