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
import requests
import urllib.parse
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, List, Dict, Any

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
        self._init_session()
        self._create_dirs()

    def _init_session(self):
        """Initializes the session with NSE cookies."""
        try:
            self.session.get(BASE_URL, timeout=15)
            self.session.get(ALL_REPORTS_URL, timeout=15)
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
        """Downloads a file with proper error handling and retry logic."""
        if referer:
            self.session.headers.update({"Referer": referer})
        
        for attempt in range(3):
            try:
                r = self.session.get(url, timeout=20)
                if r.status_code == 200:
                    # Check if it's actually an HTML error page disguised as 200
                    if r.headers.get('Content-Type', '').startswith('text/html') and b'<!DOCTYPE html>' in r.content[:100]:
                        return None
                    return r.content
                elif r.status_code == 404:
                    return None
                time.sleep(1)
            except Exception as e:
                print(f"Attempt {attempt+1} failed for {url}: {e}")
                time.sleep(2)
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
        
        df['Date'] = pd.to_datetime(df['Date']).dt.date
        df['Expiry'] = pd.to_datetime(df['Expiry']).dt.date
        
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

    def run_incremental_update(self):
        """Main loop to download and update data incrementally."""
        print("Starting Incremental Update...")

        # 1. Equity
        last_cm_date = self.get_last_date(EQUITY_PROCESSED)
        print(f"Last Equity Date: {last_cm_date}")
        cm_days = self.get_trading_days(last_cm_date + datetime.timedelta(days=1), datetime.date.today())

        for day in cm_days:
            print(f"Downloading CM Bhavcopy for {day}...")
            df = self.download_cm_bhavcopy(day)
            if df is not None:
                # Save Raw
                df.to_parquet(EQUITY_RAW / f"cm_{day.strftime('%Y%m%d')}.parquet", engine='pyarrow', compression='zstd', index=False)
                # Update Processed
                self.update_processed_data(df, EQUITY_PROCESSED)
                print(f"Updated Equity for {day}")
            time.sleep(1) # Be gentle with NSE

        # 2. Derivatives
        last_fo_date = self.get_last_date(DERIVATIVES_PROCESSED)
        print(f"Last Derivatives Date: {last_fo_date}")
        fo_days = self.get_trading_days(last_fo_date + datetime.timedelta(days=1), datetime.date.today())

        for day in fo_days:
            print(f"Downloading FO Bhavcopy for {day}...")
            df = self.download_fo_bhavcopy(day)
            if df is not None:
                # Save Raw
                df.to_parquet(DERIVATIVES_RAW / f"fo_{day.strftime('%Y%m%d')}.parquet", engine='pyarrow', compression='zstd', index=False)
                # Update Processed
                self.update_processed_data(df, DERIVATIVES_PROCESSED)
                print(f"Updated Derivatives for {day}")
            time.sleep(1)

        # 3. Indices
        last_idx_date = self.get_last_date(INDICES_PROCESSED)
        print(f"Last Indices Date: {last_idx_date}")
        idx_days = self.get_trading_days(last_idx_date + datetime.timedelta(days=1), datetime.date.today())
        
        for day in idx_days:
            print(f"Downloading Indices for {day}...")
            df = self.download_indices_report(day)
            if df is not None:
                # Save Raw
                df.to_parquet(INDICES_RAW / f"idx_{day.strftime('%Y%m%d')}.parquet", engine='pyarrow', compression='zstd', index=False)
                # Update Processed
                self.update_processed_data(df, INDICES_PROCESSED)
                print(f"Updated Indices for {day}")
            time.sleep(1)

        print("Update Complete.")

def main():
    downloader = NSEMarketDataDownloader()
    downloader.run_incremental_update()

if __name__ == '__main__':
    main()
