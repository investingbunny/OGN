# OGN — NSE Market Data Pipeline & Technical Analysis

End-to-end pipeline for downloading, storing, and analysing NSE (National Stock Exchange of India) market data. Data is stored as compressed Parquet files (zstd) for fast, space-efficient access.

---

## Main Files

| File | Purpose |
|---|---|
| **OGN v2.0-download.py** | Downloads daily market data from NSE across 11 categories (Equity, Derivatives, Indices, Short Selling, Volatility, Market Activity, Price Band, PE Ratio, Corporate Bonds, Delivery Positions, WDM Daily). Handles incremental updates, raw→processed merge, deduplication, and error recovery. |
| **OGN.py** | Data loader module — provides Python functions to read processed Parquet data. Use `from OGN import load_equity, load_futures, load_options, load_index` etc. in your own scripts or notebooks. |
| **Option-OGN.py** | Technical analysis & charting — generates multi-panel charts (MACD, RSI, ADX, Bollinger Bands, Fibonacci, Max Pain, Futures Fair Value, Renko) from the Parquet store. Supports interactive display and PDF export. |

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Download market data

```bash
python "OGN v2.0-download.py"
```

This creates the `MarketData_Parquet/` directory tree with raw and processed Parquet files.

### 3. Check data store status

```bash
python OGN.py
```

Prints a summary table showing available categories, symbol counts, and directory paths.

### 4. Generate analysis charts

```bash
# Interactive charts — all FnO symbols
python Option-OGN.py

# Interactive charts — single symbol
python Option-OGN.py RELIANCE

# Export to PDF — all FnO symbols
python Option-OGN.py --pdf

# Export to PDF — single symbol
python Option-OGN.py --pdf RELIANCE

# Export to PDF — custom output file
python Option-OGN.py --pdf output.pdf
```

### 5. Use as a library

```python
from OGN import load_equity, load_futures, load_options, load_index
from OGN import load_equity_panel, data_summary

# Single symbol
df = load_equity("RELIANCE", start="2024-01-01")

# Futures (all contracts)
fut = load_futures("RELIANCE")

# Options (nearest-month, puts only)
from OGN import load_monthly_options
opts = load_monthly_options("RELIANCE")

# Multi-symbol panel (Close prices → wide DataFrame)
panel = load_equity_panel(["RELIANCE", "TCS", "INFY"], start="2024-01-01")

# Index data
nifty = load_index("NIFTY")
```

---

## Data Categories

| # | Category | Raw Prefix | Processed Directory |
|---|---|---|---|
| 1 | Equity | `cm` | `MarketData_Parquet/Equity/Processed/` |
| 2 | Derivatives | `fo` | `MarketData_Parquet/Derivatives/Processed/` |
| 3 | Indices | `idx` | `MarketData_Parquet/Indices/Processed/` |
| 4 | Short Selling | `ss` | `MarketData_Parquet/ShortSelling/Processed/` |
| 5 | Volatility | `vol` | `MarketData_Parquet/Volatility/Processed/` |
| 6 | Market Activity | `ma` | `MarketData_Parquet/MarketActivity/Processed/` |
| 7 | Price Band | `pb` | `MarketData_Parquet/PriceBand/Processed/` |
| 8 | PE Ratio | `pe` | `MarketData_Parquet/PERatio/Processed/` |
| 9 | Corporate Bonds | `cb` | `MarketData_Parquet/CorporateBonds/Processed/` |
| 10 | Delivery Positions | `del` | `MarketData_Parquet/DeliveryPositions/Processed/` |
| 11 | WDM Daily | `wdm` | `MarketData_Parquet/WDM/Processed/` |

---

## Requirements

- Python 3.10+
- See [requirements.txt](requirements.txt) for full list
- Optional: TA-Lib (C library + Python wrapper), trendln, stocktrends