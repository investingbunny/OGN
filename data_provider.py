"""Modern Data Provider module for stock analysis.

This module handles data fetching using yfinance and ensures data quality
with modern Pandas 3.0+ features and PyArrow backend.
"""

import asyncio
from typing import List
import pandas as pd
import yfinance as yf
import numpy as np


class DataProvider:
    """Class to fetch and manage market data."""

    def __init__(self, use_pyarrow: bool = True):
        """Initializes the DataProvider.

        Args:
            use_pyarrow: Whether to use PyArrow backend for Pandas.
        """
        self.use_pyarrow = use_pyarrow

    def fetch_ticker_data(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        interval: str = "1d"
    ) -> pd.DataFrame:
        """Fetches historical data for a single ticker.

        Args:
            ticker: Stock ticker symbol.
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            interval: Data interval (e.g., '1d', '1h', '5m').

        Returns:
            pd.DataFrame: Historical OHLCV data.
        """
        df = yf.download(
            ticker,
            start=start_date,
            end=end_date,
            interval=interval,
            progress=False
        )

        if df.empty:
            return pd.DataFrame()

        # Modern Pandas 3.0+ backend conversion
        if self.use_pyarrow:
            df = df.convert_dtypes(dtype_backend="pyarrow")

        # Handle Edge Cases: Missing market data
        df = self._handle_missing_data(df)

        return df

    def _handle_missing_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Handles NaN values and missing data points.

        Args:
            df: Input DataFrame.

        Returns:
            pd.DataFrame: Cleaned DataFrame.
        """
        # Forward fill then backward fill for remaining NaNs
        df = df.ffill().bfill()
        return df

    async def fetch_multiple_tickers_async(
        self,
        tickers: List[str],
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """Fetches data for multiple tickers asynchronously.

        Note: yfinance's download method already uses multi-threading,
        but this provides an async interface for integration into
        modern async pipelines.

        Args:
            tickers: List of ticker symbols.
            start_date: Start date.
            end_date: End date.

        Returns:
            pd.DataFrame: Combined DataFrame.
        """
        # Wrapping synchronous yf.download in a thread for async compatibility
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(
            None,
            lambda: yf.download(
                tickers,
                start=start_date,
                end=end_date,
                group_by="ticker",
                progress=False
            )
        )

        if self.use_pyarrow:
            df = df.convert_dtypes(dtype_backend="pyarrow")

        return df
