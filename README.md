# OGN — NSE Market Data Pipeline & Technical Analysis

End-to-end pipeline for downloading, storing, and analysing NSE (National Stock Exchange of India) market data. Data is stored as compressed Parquet files (zstd) for fast, space-efficient access.

---

## Main Files

| File | Purpose |
|---|---|
| **OGN v2.0-download.py** | Downloads daily market data from NSE across 11 categories (Equity, Derivatives, Indices, Short Selling, Volatility, Market Activity, Price Band, PE Ratio, Corporate Bonds, Delivery Positions, WDM Daily), plus a 12th **Macro** category sourced from FRED and Yahoo Finance. Handles incremental updates, raw→processed merge, deduplication, and error recovery. |
| **OGN.py** | Data loader module — provides Python functions to read processed Parquet data. Use `from OGN import load_equity, load_futures, load_options, load_index, load_macro` etc. in your own scripts or notebooks. |
| **Option-OGN.py** | Technical analysis & charting — generates multi-panel charts (MACD, RSI, ADX, Bollinger Bands, Fibonacci, Max Pain, Futures Fair Value, Renko) from the Parquet store. Also provides **COMP**, a pairwise statistical comparison between any two series. Supports interactive display and PDF export. |

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

### 5. Compare two series statistically (COMP)

```bash
# Interactive
python Option-OGN.py COMP GLD SLV

# Export to PDF → charts/COMP_GLD_vs_SLV.pdf
python Option-OGN.py --pdf COMP GLD SLV

# Ratios use a double underscore as the division operator
python Option-OGN.py --pdf COMP US02Y__US10Y WTI
```

See [COMP — Pairwise Statistical Comparison](#comp--pairwise-statistical-comparison) below.

### 6. Use as a library

```python
from OGN import load_equity, load_futures, load_options, load_index
from OGN import load_equity_panel, load_macro, data_summary

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

# Macro series (FRED / Yahoo / derived ratios)
us10y = load_macro("US10Y")
gold_silver = load_macro("GLD_SLV")
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
| 12 | Macro (FRED / Yahoo / derived) | — | `MarketData_Parquet/Macro/Processed/` |

---

## Macro Data Sources

Categories 1–11 are day-file downloads from NSE. The **Macro** category is different: each
series is a single full-history file refreshed in place, and every file shares one schema:

`Date, Symbol, Value, Series, Name, Unit, Source`

All three registries live at the top of `OGN v2.0-download.py`. **Comment out any line to
skip that series.**

### FRED (`FRED_SERIES`)

| Symbol | FRED ID | Description | Unit |
|---|---|---|---|
| `US02Y` | DGS2 | US Treasury 2-Year Constant Maturity Yield | Percent |
| `US10Y` | DGS10 | US Treasury 10-Year Constant Maturity Yield | Percent |
| `US03M` | DTB3 | US 3-Month Treasury Bill Secondary Market Rate | Percent |
| `GVZ` | GVZCLS | CBOE Gold ETF Volatility Index | Index |
| `USCORPOAS` | BAMLC0A0CM | ICE BofA US Corporate Index Option-Adjusted Spread | Percent |
| `USHYOAS` | BAMLH0A0HYM2 | ICE BofA US High Yield Index Option-Adjusted Spread | Percent |
| `USDJPY` | DEXJPUS | Japanese Yen to US Dollar Spot Exchange Rate | JPY per USD |
| `USDINR` | DEXINUS | Indian Rupee to US Dollar Spot Exchange Rate | INR per USD |
| `EURUSD` | DEXUSEU | US Dollar to Euro Spot Exchange Rate | USD per EUR |
| `FEDTARU` | DFEDTARU | Federal Funds Target Range – Upper Limit | Percent |
| `T10Y2Y` | T10Y2Y | 10-Year Minus 2-Year Treasury Spread | Percent |
| `T10YIE` | T10YIE | 10-Year Breakeven Inflation Rate | Percent |
| `FEDASSETS` | WALCL | Federal Reserve Total Assets | Millions of USD |
| `WTI` | DCOILWTICO | Crude Oil Prices: West Texas Intermediate | USD per Barrel |
| `STLFSI` | STLFSI4 | St. Louis Fed Financial Stress Index | Index |

> **Note on the ICE BofA series.** FRED serves only a rolling **3-year** window for
> `BAMLC0A0CM` and `BAMLH0A0HYM2` ("Starting in April 2026, this series will only include
> 3 years of observations") because of ICE Data Indices licensing. This is a source-side
> limit, not a bug. Since the store is incremental, your local history keeps growing
> beyond that window with every run.

### Yahoo Finance (`YAHOO_SERIES`)

| Symbol | Ticker | Description | Unit |
|---|---|---|---|
| `GLD` | GLD | SPDR Gold Shares ETF | USD |
| `SLV` | SLV | iShares Silver Trust ETF | USD |

Requires `yfinance`. The first run pulls the full available history (`period="max"`).

### Derived ratios (`MACRO_RATIOS`)

| Symbol | Formula | Description |
|---|---|---|
| `GLD_SLV` | GLD / SLV | Gold/Silver ETF price ratio |

Computed from the stored legs over their overlapping dates, then written as a normal
Macro file. To add one, append a `(symbol, numerator, denominator, name)` tuple.

### Incremental behaviour

Every Macro series updates incrementally:

1. Read the stored Parquet and find its last date.
2. Re-fetch from `last_date − 10 days` (`MACRO_REFRESH_OVERLAP_DAYS`) so upstream
   revisions are picked up.
3. Merge, deduplicate on `Date` keeping the newest row, sort, and write atomically via a
   temp file.

A first run backfills up to 50 years (`MACRO_MAX_HISTORY_YEARS`); later runs typically add
only a handful of rows per series.

All sources pass through one normalisation gate that unifies the schema, coerces `Date` to
a plain calendar date and `Value` to float, and tolerates format drift — FRED's legacy
`DATE` header vs the current `observation_date`, Yahoo's `Close` vs `Adj Close`, thousands
separators, and tz-aware timestamps.

---

## COMP — Pairwise Statistical Comparison

Compares **any two** downloaded series — across FRED, Yahoo, Equity, Indices, Derivatives,
Volatility, PE Ratio and the rest — and reports the relationship measures used in
statistical-arbitrage and lead-lag research.

```bash
python Option-OGN.py COMP <symbol1> <symbol2> [days]
python Option-OGN.py --pdf COMP <symbol1> <symbol2> [days]
```

### Arguments

Each argument is either a **stored symbol** or a **ratio** written as `NUM__DEN`, using a
**double underscore** as the division operator:

```bash
python Option-OGN.py COMP GLD SLV                # two macro series
python Option-OGN.py COMP NIFTY US10Y            # index vs macro
python Option-OGN.py COMP RELIANCE NIFTY         # equity vs index
python Option-OGN.py COMP US02Y__US10Y WTI       # ratio vs macro
python Option-OGN.py COMP GLD__SLV US10Y         # ratio computed on the fly
```

The double underscore keeps ratios unambiguous against stored names that contain a single
underscore — `GLD_SLV` loads the stored Parquet file, while `GLD__SLV` computes the ratio
fresh from `GLD` and `SLV`. It is also filename-safe, so it survives in the generated PDF
name (`charts/COMP_US02Y__US10Y_vs_WTI.pdf`).

A ratio is built in memory over the two legs' overlapping dates and is never written to
disk. Exactly one `__` is allowed per argument.

### Optional third argument: `days`

```bash
python Option-OGN.py COMP GLD SLV 250            # last 250 days only
python Option-OGN.py --pdf COMP GLD SLV 250      # → charts/COMP_GLD_vs_SLV_250d.pdf
python Option-OGN.py COMP GLD SLV                # omitted → full common horizon
```

- **Omitted** — the analysis runs over the entire overlap, i.e. the horizon of whichever
  series is shorter. Ratios inherit the same rule.
- **Supplied** — only the most recent N observations are used. Trimming happens *after*
  alignment, so the sample is exactly N rows rather than whatever the two calendars happen
  to share in the last N calendar days.
- Must be at least 60 (`COMP_MIN_OBS`); below that the estimators are not meaningful and
  the run stops with a clear message.
- If N exceeds the available overlap, everything available is used and the console says so.
- The window is echoed on the console, in the chart title, and in the generated PDF name.

### Alignment rules

- Timestamps are stripped to tz-naive midnight, so sources with different timestamp types
  and localisations line up on the calendar day.
- Sources with several rows per day are reduced to one daily print. Derivatives collapse
  to the **front-month future**; anything still duplicated is averaged.
- The two series are inner-joined, so the comparison automatically runs over the
  **shorter** of the two horizons. Ratios inherit the same rule. Pass the optional `days`
  argument to narrow it further.
- Minimum 60 overlapping observations, otherwise the run stops with a clear message.

### Measures reported

| Measure | What it measures | Quant use case |
|---|---|---|
| **Cointegration** | Whether a linear combination forms a stable mean-reverting spread | Pairs trading / statistical arbitrage |
| **Granger Causality** | Whether past values of A help forecast B (tested both directions) | Lead-lag strategies, leading macro indicators |
| **Cross-Correlation** | Correlation across lags −10…+10 days | Pinpointing the trigger-to-response delay |
| **Dynamic Time Warping** | Shape similarity allowing for speed/phase differences | Matching historic regimes with different cycle speeds |
| **Mutual Information** | Shared information, linear *and* non-linear | Feature selection for ML alpha models |

### Methodology notes

- **Cointegration runs on levels** (Engle–Granger); the other four run on **log returns**,
  since Granger tests on non-stationary levels are spurious. Series that can be zero or
  negative (spreads such as `T10Y2Y`) fall back to first differences. The transform used
  is printed and shown on the chart.
- **Cross-correlation sign convention:** a *positive* lag means `symbol1` leads `symbol2`.
- **DTW** uses `dtaidistance` with a Sakoe-Chiba band on z-normalised series, resampled to
  at most 1000 points so multi-decade histories stay fast. The distance is
  length-normalised, so it is comparable across pairs. The library's compiled C extension
  is used when available and the pure-Python path otherwise.
- **Mutual Information** uses `scikit-learn`'s k-nearest-neighbour (Kraskov) estimator,
  reported in bits. It is essentially unbiased, so independent series score ~0 — unlike a
  histogram estimate, which can report ~0.12 bits for unrelated series. It also detects
  purely non-linear relationships that Pearson correlation misses entirely.
- **Cointegration** and **Granger causality** come from `statsmodels`.

### Libraries used

| Measure | Library |
|---|---|
| Cointegration | `statsmodels.tsa.stattools.coint` |
| Granger causality | `statsmodels.tsa.stattools.grangercausalitytests` |
| Cross-correlation | `pandas` |
| Dynamic Time Warping | `dtaidistance` |
| Mutual Information | `scikit-learn` |

### Output

One figure (on screen, or PDF with `--pdf`) containing:

1. Both series as levels on twin axes
2. Both rebased to 100 at the common start date
3. The cointegration spread with mean and ±2σ bands
4. The cross-correlation function, with the strongest lag highlighted
5. A colour-coded summary table — measure name, value, a plain-English reading of *this*
   result, and a one-line note on what the measure tells you

The same table is printed to the console.

---

## Requirements

- Python 3.10+
- See [requirements.txt](requirements.txt) for full list
- `yfinance` is required for the Yahoo macro series (`GLD`, `SLV`)
- `statsmodels`, `scikit-learn` and `dtaidistance` are required for COMP
- Optional: TA-Lib (C library + Python wrapper), trendln, stocktrends