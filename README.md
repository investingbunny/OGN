# OGN — NSE Market Data Pipeline & Technical Analysis

End-to-end pipeline for downloading, storing, and analysing NSE (National Stock Exchange of India) market data. Data is stored as compressed Parquet files (zstd) for fast, space-efficient access.

---

## Main Files

| File | Purpose |
|---|---|
| **OGN v2.0-download.py** | Downloads daily market data from NSE across 11 categories (Equity, Derivatives, Indices, Short Selling, Volatility, Market Activity, Price Band, PE Ratio, Corporate Bonds, Delivery Positions, WDM Daily), plus a 12th **Macro** category sourced from FRED and Yahoo Finance. Handles incremental updates, raw→processed merge, deduplication, and error recovery. |
| **OGN.py** | Data loader module — provides Python functions to read processed Parquet data. Use `from OGN import load_equity, load_futures, load_options, load_index, load_macro` etc. in your own scripts or notebooks. |
| **Option-OGN.py** | Technical analysis & charting — generates multi-panel charts (MACD, RSI, ADX, Bollinger Bands, Fibonacci, Max Pain, Futures Fair Value, Renko), a volatility-cone page from the standalone estimator models, and an optional statistical comparison against a second symbol. Supports interactive display and PDF export. |
| [schiller_macro.py](schiller_macro.py) | US-only Schiller valuations: Robert Shiller's CAPE/real-price/earnings workbook and Multpl valuation histories. |
| [nifty_macro.py](nifty_macro.py) | Separate India Schiller group: NIFTY valuations, calculated Indian-only CAPE, and explicitly unverified IIM/RBI/index-price-sales sources. |
| [option_overlay.py](option_overlay.py) | Volume-ranked CE/PE implied-volatility overlays, matched-futures Black-76 IV estimates, and robust same-expiry smile diagnostics. |
| **models.py** + `GarmanKlass.py`, `HodgesTompkins.py`, `Kurtosis.py`, `Parkinson.py`, `Raw.py`, `RogersSatchell.py`, `Skew.py`, `YangZhang.py` | Volatility estimators. One module per model, each exposing `get_estimator(price_data, window, clean)`. |

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

One command handles both the technical analysis and the optional pairwise comparison:

```
python Option-OGN.py [--pdf] [--estimator NAME] [symbol] [compare_symbol] [days]
```

```bash
# Interactive charts — all FnO symbols
python Option-OGN.py

# Full technical analysis for one series (any source, not just equities)
python Option-OGN.py RELIANCE
python Option-OGN.py WTI

# Full analysis of the first symbol, plus a statistical comparison against the second
python Option-OGN.py WTI US02Y__US10Y

# ... with the comparison restricted to the last 250 days
python Option-OGN.py WTI US02Y__US10Y 250

# Choose the volatility estimator (default YangZhang)
python Option-OGN.py --estimator Raw WTI

# Export to PDF — all FnO symbols
python Option-OGN.py --pdf

# Export to PDF — single symbol → charts/WTI_Analysis.pdf
python Option-OGN.py --pdf WTI

# Export to PDF — pair → charts/WTI_vs_US02Y__US10Y_Analysis.pdf
python Option-OGN.py --pdf WTI US02Y__US10Y

# Export to PDF — custom output file
python Option-OGN.py --pdf output.pdf
```

The report is assembled in this order:

1. **Technical analysis** of the first symbol
2. **Volatility profile** of the first symbol
3. **Statistical comparison** — only when a second symbol is given

See [Volatility Analysis](#volatility-analysis) and [Statistical Comparison](#statistical-comparison)
below.

### 5. Use as a library

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

`Date, Symbol, Value, Series, Name, Unit, Source, Frequency, Description`

The FRED, World Bank, Yahoo and ratio registries live at the top of
`OGN v2.0-download.py`. **Comment out any line to skip that series.** Japan uses
`JAPAN_SERIES` in [japan_macro.py](japan_macro.py); US Schiller uses `SCHILLER_SERIES`
in [schiller_macro.py](schiller_macro.py); India Schiller uses `NIFTY_SERIES` in
[nifty_macro.py](nifty_macro.py). The downloaders and PDF pages share these definitions.

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

### Japan Macro and Carry Trade

Japan refreshes automatically during the normal download run. To update Japan only,
without contacting NSE, and generate an analysis PDF with the Japan appendix:

```powershell
.\.venv\Scripts\python.exe "OGN v2.0-download.py" --japan-only
.\.venv\Scripts\python.exe Option-OGN.py --pdf JPUSDJPY
```

Each series is stored under `MarketData_Parquet/Macro/Processed/{symbol}.parquet`.
The existing FRED `USDJPY` file is unchanged; `JPUSDJPY` uses Yahoo's `USDJPY=X`.
Every analysis PDF includes three Japan pages once per report: funding/carry trade;
growth/inflation/wages; positioning/capital flows. Each panel includes the stored
ticker, source identifier, definition, frequency, units, and latest observation date.
Charts read local data only and show the past five years. Remove `japan_macro` from
`REPORT_SECTIONS` in [Option-OGN.py](Option-OGN.py) to disable this appendix.

Verified public downloads:

| Ticker | Source Identifier | Frequency | Definition / Unit |
|---|---|---|---|
| `JPUSDJPY` | Yahoo `USDJPY=X` | Daily | Yen per USD; a decline means yen appreciation. Not a streaming quote service. |
| `JP10Y` | FRED/OECD `IRLTLT01JPM156N` | Monthly | Japanese 10-year government bond yield, percent; not real-time. |
| `JPPOLRATE` | BIS `WS_CBPOL/D.JP` | Daily | BOJ policy-rate history, percent; changes follow policy decisions, with historical regime changes and gaps. |
| `JPCOTSHORT` | CFTC `6dca-aqww`, contract `097741` | Weekly | CME yen futures-only noncommercial shorts minus longs, contracts. Positive = net short yen. |
| `JPLEADING` | Cabinet Office/ESRI, CI Leading | Monthly | Official composite leading index, 2020=100; not the OECD CLI or a diffusion index. |
| `JPTOKYOCORE` | Statistics Dashboard `0703010601010030010`, region `13100` | Monthly | Tokyo ku-area CPI excluding fresh food, published percent YoY; energy remains included. |
| `JPCORECPI` | Statistics Dashboard `0703010601010030010`, region `00000` | Monthly | National CPI excluding fresh food, published percent YoY. BOJ's 2% target is formally all-items CPI. |
| `JPWAGES` | Statistics Dashboard `0302020000000030000`, region `00000` | Monthly | Nominal total cash earnings growth, percent YoY; includes bonuses and overtime. Latest releases may be preliminary. |
| `JPCURRENT` | MOF `6s-1-4`, current account | Monthly | Current-account balance, not seasonally adjusted, billions of JPY; converted from 100 million yen. |
| `JPXBYEN` | BIS `WS_LBS_D_PUB/Q.S.C.G.JPY.A.5J.A.5A.A.5J.N` | Quarterly | Cross-border yen loans/deposits of all reporting banks, millions of USD equivalent; not a direct carry-trade size estimate. |
| `JPFOREIGN` | BIS `WS_CBS_PUB/Q.S.JP.4R.F.C.A.A.TO1.A.5J` | Quarterly | Japanese banks' consolidated foreign claims, immediate-counterparty basis, millions of USD; excludes domestic positions, includes non-loan claims. |

The report also reserves these exact indicators and displays an explicit gap until
their required data is configured. It does not generate empty/fake Parquet histories
or replace them with different measures:

| Ticker | Indicator | Current Limitation |
|---|---|---|
| `JPTANKAN` | BOJ Tankan large manufacturers' actual business-conditions DI, quarterly | BOJ access was unavailable during verification; no exact public history adapter configured. |
| `JPPMI` | S&P Global / au Jibun Bank Japan Composite Output PMI, monthly | No verified public historical feed configured; provider access is needed. |
| `JPCOTINDEX` | MacroMicro JPY positioning COT index, weekly | No verified public feed or exact normalization methodology; `JPCOTSHORT` is a different measure. |
| `JPJPYIV` | USD/JPY one-month ATM implied volatility, daily annualized percent | No verified public history configured. Realized volatility is not substituted. |
| `JPCARRY` | Carry-to-risk ratio | Requires `FEDTARU`, `JPPOLRATE`, and `JPJPYIV` on the same date. |

`JPCARRY = (FEDTARU - JPPOLRATE) / JPJPYIV`, using annualized percent for both rates
and volatility. This explicitly uses the Fed target upper limit and BOJ policy rate;
it is not claimed to reproduce MacroMicro's methodology. Missing dates are not
forward-filled, zero/negative/nonfinite volatility is excluded, and revisions to any
input are recomputed over their full stored overlap. The Japan-only command uses an
already-stored `FEDTARU`; the normal update refreshes that US dependency first.

Source dates are observation periods, **not publication timestamps**. CFTC data
normally reports Tuesday positions on Friday, and monthly/quarterly releases arrive
later than their period dates. Histories are revised, not point-in-time backtest data.
Both CPI series use the official 2025-base published YoY history, not a calculated
YoY change across incompatible index bases. Dashboard updates may lag preliminary
Tokyo releases. BIS bank exposures include business unrelated to carry trades.

Japan daily Yahoo data re-fetches 10 days; other regular sources re-fetch 400 days;
BIS banking series re-fetch five years. ESRI, MOF and CPI refresh their available
history to capture longer revisions/rebasing. Existing files survive failed requests;
new values use the shared atomic merge. ESRI workbooks require `openpyxl>=3.1`.

Official references: [CFTC](https://publicreporting.cftc.gov/),
[BIS](https://data.bis.org/), [ESRI](https://www.esri.cao.go.jp/en/stat/di/di-e.html),
[MOF](https://www.mof.go.jp/english/policy/international_policy/reference/balance_of_payments/ebpnet.htm),
[Statistics Dashboard API](https://dashboard.e-stat.go.jp/en/static/api).
This service uses the Statistics Dashboard API, but its contents are not guaranteed
by the Government of Japan.

Offline regression checks: `python -m unittest test_japan_macro -v`.

### US Schiller Valuation

The requested "Schiller" group is labeled **US Schiller** to distinguish it from
**India Schiller**. The underlying US data is attributed to **Robert Shiller**,
S&P Dow Jones Indices and Multpl. No Indian inputs enter this group.

```powershell
.\.venv\Scripts\python.exe "OGN v2.0-download.py" --schiller-only
.\.venv\Scripts\python.exe Option-OGN.py --pdf WTI SCHCAPE --periods 120
```

| Ticker | Metric / Source | Native Frequency | Verified Available History |
|---|---|---|---|
| `SCHCAPE` | Conventional PE10 / Robert Shiller workbook CAPE column | Monthly | Jan 1881 - latest workbook |
| `SCHREAL` | Inflation-adjusted US stock composite / published Real Price | Monthly | Jan 1871 - latest workbook |
| `SCHEARN` | Nominal trailing annual earnings / workbook E column | Monthly, source-interpolated | Jan 1871 - latest available earnings |
| `SCHEPS` | Single-quarter as-reported S&P 500 EPS / S&P DJI | Quarterly | **Unavailable:** official workbook returned HTTP 403; exact parser not configured |
| `SCHPE` | Trailing P/E / Multpl | Monthly | Jan 1871 - latest table |
| `SCHEY` | Trailing earnings yield, percent / Multpl | Monthly | Jan 1871 - latest table |
| `SCHPS` | S&P 500 price/sales / Multpl | Quarterly | Dec 2000 - latest reported/estimated quarter |
| `SCHPB` | S&P 500 price/book / Multpl | Quarterly | Dec 1999 - latest reported/estimated quarter |
| `SCHBV` | S&P 500 book value per index share / Multpl | Quarterly | Dec 1999 - latest reported quarter |

The official [Shiller data page](https://shillerdata.com/) links the current
`ie_data.xls` workbook. Its published historical composite is not the modern S&P 500
throughout the nineteenth century. `SCHEARN` contains source-interpolated trailing
annual earnings; it is **not substituted for quarterly reported EPS**. `SCHREAL` is a
real price index, not a total-return index. The current workbook can contain estimated
CPI or preliminary current-month prices. The conventional CAPE column is not the
alternative total-return CAPE column.

Multpl historical tables supply [P/E](https://www.multpl.com/s-p-500-pe-ratio/table/by-month),
[earnings yield](https://www.multpl.com/s-p-500-earnings-yield/table/by-month),
[P/S](https://www.multpl.com/s-p-500-price-to-sales/table/by-quarter),
[P/B](https://www.multpl.com/s-p-500-price-to-book/table/by-quarter), and
[book value](https://www.multpl.com/s-p-500-book-value/table/by-quarter).
The extra live-date quote is excluded rather than relabeled as a monthly or quarterly
observation. Historical estimates are marked in each stored row's `Description`.
GuruFocus is not needed for the publicly verified Multpl tables; no paid export is bypassed.

First runs retain the full available history from 1871, not the general 50-year macro
lookback. Later Multpl updates merge a 400-day revision overlap using the existing atomic
Parquet writer. The small Shiller workbook is fetched once per group refresh and its
complete histories are revalidated. **All real-price history is rewritten together** so
new US CPI-base values are not appended onto a different old base; a response truncating
stored date coverage is rejected. HTTP, rate-limit and parse failures are retried, and
failed series leave existing files intact without blocking independent sources.
Reading legacy XLS requires `xlrd>=2.0.1` from [requirements.txt](requirements.txt).

### India Schiller / NIFTY

This is a separate **Indian-market-only group**, including every metric in the supplied
India matrix. Its registry, calculations, tickers and chart pages are separate from US
Schiller. Missing Indian history is **never** replaced with US P/E, US CPI, US CAPE,
Sensex valuations or company-screener averages.

```powershell
.\.venv\Scripts\python.exe "OGN v2.0-download.py" --india-schiller-only
```

This command refreshes the verified Indian `INCPI` history and computes NIFTY metrics
from the existing [OGN v2.0-download.py](OGN%20v2.0-download.py) NSE index pipeline's
`MarketData_Parquet/Indices/Processed/NIFTY.parquet`. The normal full download also runs
this group **after** the NSE index merge, so new index data is available to calculations.
The group-only command does not backfill NSE day files or require an NSE session.

| Ticker | Metric / Requested Primary Source | Implementation / Availability |
|---|---|---|
| `INIIMCAPE` | Published India CAPE / IIM Ahmedabad | **Unverified:** exact dataset/paper link, index universe, frequency and claimed 2004-present range need confirmation. Not filled with a local estimate. |
| `NIFTYCAPE` | Additional calculated NIFTY CAPE estimate | Uses Indian NIFTY price/P/E-implied earnings and Indian CPI only; requires 120 consecutive complete months. Not official NSE or IIM CAPE. |
| `NIFTYPE` | NIFTY 50 trailing P/E / NSE Indices | Last available observation of each closed month from stored NSE history. |
| `NIFTYPB` | NIFTY 50 price/book / NSE Indices | Published P/B, sampled monthly; not inferred from US or company data. |
| `NIFTYEPS` | NIFTY 50 earnings / NSE data | Explicitly **implied trailing earnings**: same-date NIFTY Close / P/E. Not audited quarterly EPS. |
| `NIFTYDY` | NIFTY 50 dividend yield / NSE Indices | Published DY in percent, sampled monthly. |
| `NIFTYEY` | NIFTY earnings yield / calculated from NSE | `100 / PE` in percent, equivalent to `1 / PE` as a fraction. P/E 20 means yield 5%, not 0.05%. |
| `INRBICPI` | Indian CPI / RBI DBIE | **Unverified export adapter:** separate requested CPI Combined series; not relabeled OECD or US CPI. |
| `INRBIWPI` | Indian WPI / RBI DBIE | **Unverified export adapter:** separate all-commodities wholesale price series, never spliced into CPI. |
| `NIFTYPS` | Indian index price/sales / BSE, Trendlyne, Screener | **Unverified:** an aggregate NIFTY 50 historical series is required. Company and Sensex P/S values are not substitutes. |
| `INCPI` | Additional Indian CPI deflator / OECD via FRED | Verified Indian all-items index, 2015=100, ending March 2025. Used only for the explicitly labeled NIFTY estimate, not presented as RBI DBIE. |

Requested source portals: [IIM Ahmedabad](https://www.iima.ac.in/),
[NSE Nifty Indices](https://www.niftyindices.com/reports/historical-data),
[RBI DBIE](https://data.rbi.org.in/#/dbie/dataquery_enhanced),
[BSE India](https://www.bseindia.com/). The supplied 1999-present and 2004-present
ranges are source expectations, not guaranteed local coverage. The existing NSE
day-file downloader starts in 2010 by default. No automated IIM/RBI/NIFTY price-sales
history is claimed until the exact export and its definition can be verified.

For the estimate, let `P_t` be NIFTY close, `PE_t` the matching NSE P/E and `C_t` Indian CPI:

```text
E_t = P_t / PE_t
NIFTYCAPE_t = (P_t / C_t) / mean(E_s / C_s for s = t-119, ..., t)
```

Monthly inputs use the last observation of a closed month with at least 80% weekday
coverage. Zero/negative P/E and invalid prices/CPI are excluded. All 120 calendar
months must exist; missing months or CPI are never filled, and US CPI is explicitly
rejected by provenance checks. CPI series rebasing must be consistent throughout the
window. Historical NSE earnings-methodology and index-composition changes limit this
estimate's comparability; there is no silent adjustment for those breaks.

NIFTY histories are recomputed and merged without duplicate dates so input revisions
propagate into derived values. No fabricated observations or empty histories are written
when inputs are missing. With the configured discontinued Indian CPI, the latest possible
estimate is March 2025, even if NIFTY prices are newer. At verification, the local NIFTY
index folder was empty; Indian valuation panels therefore correctly show missing data.

Both new groups append **two separate pages each** once per analysis PDF, using the
same layout as Japan: ticker, source ID, frequency, definition, units, latest observation
date, and explicit gaps. Disable them independently using `schiller_macro` or
`india_schiller` in `REPORT_SECTIONS`. Stored monthly/quarterly histories automatically
participate in the existing mixed-frequency statistical comparison workflow.

Focused tests: `python -m unittest test_valuation_macro -v`.

### Incremental behaviour

Every Macro series updates incrementally:

1. Read the stored Parquet and find its last date.
2. Re-fetch from `last_date − 10 days` for daily market series; monthly/quarterly
  FRED series use 400 days and annual World Bank series use five years to capture
  revisions. Japan-specific windows are described above.
3. Merge, deduplicate on `Date` keeping the newest row, sort, and write atomically via a
   temp file.

A first run backfills up to 50 years (`MACRO_MAX_HISTORY_YEARS`); later runs typically add
only a handful of rows per series.

All sources pass through one normalisation gate that unifies the schema, coerces `Date` to
a plain calendar date and `Value` to float, and tolerates format drift — FRED's legacy
`DATE` header vs the current `observation_date`, Yahoo's `Close` vs `Adj Close`, thousands
separators, and tz-aware timestamps.

---

## Volatility Analysis

Every report includes a volatility page for the **first** symbol, built from the standalone
estimator modules (`GarmanKlass.py`, `YangZhang.py`, ...), each of which exposes
`get_estimator(price_data, window, clean)` and is dispatched through `models.py`.

```bash
python Option-OGN.py --pdf WTI                    # default estimator (YangZhang)
python Option-OGN.py --pdf --estimator Raw WTI    # pick another
```

### Available estimators

| Estimator | Type | Inputs used | Notes |
|---|---|---|---|
| `YangZhang` | Volatility | O, H, L, C | **Default.** Handles overnight gaps and drift |
| `GarmanKlass` | Volatility | O, H, L, C | Efficient, assumes no drift |
| `Parkinson` | Volatility | H, L | High/low range only |
| `RogersSatchell` | Volatility | O, H, L, C | Drift-independent |
| `HodgesTompkins` | Volatility | C | Close-to-close, bias corrected |
| `Raw` | Volatility | C | Plain close-to-close standard deviation |
| `Skew` | Moment | C | Return distribution skew |
| `Kurtosis` | Moment | C | Return distribution kurtosis |

Volatility estimators are annualised (252 trading periods) and shown as percentages.
`Skew` and `Kurtosis` are distribution moments, so they are labelled as plain numbers.

> **Estimators needing an intraday range.** `GarmanKlass`, `Parkinson` and `RogersSatchell`
> read the high/low spread. Single-value sources (FRED, Yahoo, ratios) are expanded to flat
> bars where `High == Low`, so those three return **exactly zero** for such series. The tool
> detects this and prints a warning suggesting `Raw`, `HodgesTompkins` or `YangZhang`, which
> are all close-to-close based and remain meaningful.

### The volatility page

| Panel | Shows |
|---|---|
| `cone` | Max / 75th / median / mean / 25th / min across rolling windows, with latest realized volatility and eligible latest-date option IV overlaid |
| `box` | Box-and-whisker of the same per-window distributions |
| `rolling` | The rolling estimator through time with quantile bands |
| `histogram` | Distribution of estimator values, normal fit, and latest value marked |
| `summary` | Latest value, percentile rank against its own history, median, min/max, sample size |

The cone is the classic read: if the realized line sits above the upper percentile band,
short-dated volatility is rich relative to its own history.

### Tuning

At the top of [Option-OGN.py](Option-OGN.py):

```python
VOLATILITY_WINDOWS = [3, 5, 10, 20, 30, 60, 90]  # cone x-axis
VOLATILITY_WINDOW = 30                            # rolling / histogram window
VOLATILITY_QUANTILES = [0.25, 0.75]
DEFAULT_ESTIMATOR = 'YangZhang'
```

### CE/PE Implied-Volatility Overlays

When the selected underlying ticker has stored derivatives, the volatility page can
overlay its **five highest-volume eligible calls and five puts per expiry and trading
date**. This applies to the first analysed symbol, not the comparison symbol.

- **Green dots:** CE implied volatility. **Red dots:** PE implied volatility.
- **Dot height:** annualized IV, not strike or premium. Each dot is labeled with its
  strike and expiry, for example `(24500, 22 Sep)`, with leader lines where needed.
- **Cone overlay:** observations from the latest underlying date only, located at
  the remaining weekday tenor. Matching realized-estimator windows are added when
  enough history exists. Older option observations are never shown as current.
- **Date-series pages:** separate CE/PE panels for each expiry, following the volatility
  page. Up to five trading dates fit on each page; longer windows are paginated.
- **Latest-contract table:** traded contracts, IV, reported/estimated source, realized
  mean, IV-minus-mean in percentage points, smile MAD score, and selection reason.
- **Black outlines:** qualifying smile outliers, including any already among the
  volume leaders. Up to two additional contracts per side/expiry/date can be included;
  no outlier is invented just to fill that quota.

```powershell
python Option-OGN.py --pdf NIFTY
python Option-OGN.py --pdf BANKNIFTY --option-dates 10 --option-min-contracts 50
python Option-OGN.py --pdf NIFTY --option-outliers 0
python Option-OGN.py --pdf NIFTY --option-rate 0.055 --option-iv-unit percent
```

| Option | Default | Meaning |
|---|---|---|
| `--option-dates N` | `5` | Last N underlying observation dates, not N calendar days or N nonempty option snapshots |
| `--option-min-contracts N` | `10` | Minimum traded contracts per option/date; ranking uses `Contracts`, not open interest or turnover |
| `--option-outliers N` | `2` | Maximum extra MAD outliers per side/expiry/date: `0`, `1`, or `2`; `0` disables outlier scoring |
| `--option-rate R` | `0.065` | Fixed continuously compounded annual decimal rate for Black-76; `0.055` means 5.5% |
| `--option-iv-unit UNIT` | `percent` | Units of source-reported IV: `percent` or `decimal`; these are never inferred from magnitude |

Remove `option_overlay` from `REPORT_SECTIONS` to disable this feature. The `volatility`
section must also be enabled. Existing historical charts remain usable when derivatives
or valid IV are unavailable. Skew/Kurtosis are distribution moments, so IV is not plotted
on those axes. Monthly/quarterly macro data, duplicate underlying dates, and range-based
estimators applied to flat bars are also excluded from option overlays.

### Option Data and IV Estimation

The overlay reads the selected ticker's existing processed derivatives through
`load_derivatives`, including **all expiries**, rather than the nearest-expiry-only
options loader. It performs no downloads or writes to market-data files. Required
columns are `Date`, `Expiry`, `Symbol`, `Option type`, `Strike Price`, and `Contracts`.
Only unexpired CE/PE contracts with finite positive strikes and sufficient traded volume
are eligible; expiry-day contracts are excluded because intraday time remaining is unknown.
Duplicate date/expiry/side/strike observations keep the last row. Ties in volume use
ascending strike for reproducibility. Fewer than five dots are shown if fewer qualify.

Valid reported IV from `Implied Volatility` (preferred) or `IV` takes precedence.
In percent mode, `20` and `20%` both mean 20%; in decimal mode, `0.20` means 20%,
and a percent suffix is rejected as a unit conflict.

For missing IV, `vollib` performs Black-76 inversion using **the same ticker, date,
and expiry's futures price**. Legacy futures codes and UDiFF `IDF`/`STF` are supported.
Both option and future use settlement prices, falling back to both close prices when
settlement inputs are missing/nonpositive. Price bases are not mixed. Prices outside
discounted intrinsic/upper bounds, ambiguous futures matches, and solver failures are
skipped. An invalid settlement quote is not silently replaced after failing price bounds.
Reported IV can still be used without a matching future or IV solver.

Black-76 uses ACT/365 calendar time to expiry and the explicit fixed rate above.
Realized volatility uses 252 observations/year and a matching **weekday** lookback;
the tenor count omits weekends, not exchange-specific holidays. Daily prices do not
guarantee synchronous quotes, and no historical yield curve, bid/ask spread, or intraday
expiry time is inferred. These model estimates assume European-style options and are
diagnostic, not executable prices. In particular, a weekly expiry without a matching
future **and** without reported IV is unavailable; a different expiry is not substituted.

### Historical Mean and Outliers

The historical reference is the selected realized-volatility estimator at each option's
remaining weekday tenor, calculated only from underlying observations **through that
option date**. Its mean and standard deviation use the available valid rolling history,
with at least 30 estimator observations and a tenor of at least two sessions. A missing
reference remains unavailable. The shaded mean +/- 1 SD range is descriptive, not a
confidence interval; the date-series dots can represent different volume leaders daily.

Outliers use a separate **cross-sectional robust smile test**, not a raw IV-minus-realized
threshold. On each date, expiry, and CE/PE side independently:

1. Fit a Huber robust quadratic to IV against centered/scaled log strike across the
   entire eligible chain, not only the top five. Require at least 12 distinct strikes.
2. Subtract the fitted smile IV and center the residuals on their median.
3. Scale by the normally adjusted median absolute deviation, with a floor of `0.005`
   annualized IV (0.5 volatility percentage points).
4. Flag absolute scores of at least `3.5`. The two lowest and two highest strikes are
   not outlier candidates because they lack sufficient two-sided strike support.
5. Add at most the requested number of largest absolute-score outliers beyond the
   volume leaders. Sparse, degenerate, or nonconvergent fits add none.

MAD was selected over mean/standard-deviation z-scores because extreme quotes can
inflate the latter's scale. IQR fences are another robust choice, but neither raw-IQR
nor raw-z-score comparisons account for normal volatility-smile differences. This
implementation uses smile-adjusted MAD only; `--option-outliers 0` turns it off.
The liquidity screen checks traded contracts only, not quote freshness or spreads.
An outlier can be a bad quote or model-fit issue; an IV-minus-realized gap can reflect
a normal risk premium. Neither establishes mispricing, arbitrage, or a trade signal.

Focused checks: `python -m unittest test_option_overlay -v`.
Option pricing and dense chart layouts are validated with explicitly synthetic fixtures;
the local processed derivatives folder is empty, so no live option-chain validation or
market outlier claim has been made.

---

## Report Modularity

The report is assembled from two commentable registries at the top of
[Option-OGN.py](Option-OGN.py). **Comment out any line to drop that piece.**

```python
# Whole sections
REPORT_SECTIONS = [
    'technical',    # multi-panel indicator chart for the first symbol
  'trendlines',   # price with regression support/resistance
    'volatility',   # volatility cone / rolling / histogram page
    'option_overlay',  # IV dots and per-expiry pages when derivatives exist
    'comparison',   # statistical comparison, only when a second symbol is given
  'japan_macro',  # Japan appendix once per PDF
    'schiller_macro',  # US-only valuations
    'india_schiller',  # Indian-only valuations and CAPE estimate
]

# Individual panels on the volatility page
VOLATILITY_PANELS = [
    'cone',
    'box',
    'rolling',
    'histogram',
    'summary',
]
```

For example, to produce only the technical chart, leave only `'technical'` enabled.
Sections that fail (bad estimator, too little history, no overlapping
dates) are skipped with a printed reason rather than aborting the run.

---

## Statistical Comparison

Passing a **second symbol** appends a statistical comparison to the report, after the full
technical analysis of the first. It works across **any two** downloaded series: US,
India and Japan macro sources, FRED, World Bank, Yahoo, Equity, Indices, Derivatives,
Volatility, PE Ratio and the rest. It reports the
relationship measures used in statistical-arbitrage and lead-lag research.

```bash
python Option-OGN.py [--pdf] <symbol> <compare_symbol> [observations]
```

### Symbols

Either argument is a **stored symbol** or a **ratio** written as `NUM__DEN`, using a
**double underscore** as the division operator:

```bash
python Option-OGN.py GLD SLV                # two macro series
python Option-OGN.py NIFTY US10Y            # index vs macro
python Option-OGN.py RELIANCE NIFTY         # equity vs index
python Option-OGN.py WTI US02Y__US10Y       # macro vs ratio
python Option-OGN.py GLD__SLV US10Y         # ratio computed on the fly
python Option-OGN.py --pdf WTI JP10Y 120    # daily WTI vs monthly Japan yield, 120 months
python Option-OGN.py --pdf WTI JPXBYEN      # daily WTI vs quarterly BIS yen lending
```

The double underscore keeps ratios unambiguous against stored names that contain a single
underscore — `GLD_SLV` loads the stored Parquet file, while `GLD__SLV` computes the ratio
fresh from `GLD` and `SLV`. It is also filename-safe, so it survives in the generated PDF
name (`charts/WTI_vs_US02Y__US10Y_Analysis.pdf`).

A ratio is built in memory after its two legs are aligned to their slower native cadence
with the default aggregation rules below. Division happens after aggregation, zero
denominators are excluded, and the ratio carries its resulting frequency into the outer
comparison. It is never written to disk. Exactly one `__` is allowed per argument.

> **Any source can drive the full analysis.** Single-value series (FRED, Yahoo, ratios)
> have no OHLC bars, so they are expanded into flat bars (`Open = High = Low = Close`,
> `Volume = 0`) before the indicator stack runs. Price-derived indicators (MACD, RSI,
> Bollinger, ATR, ADX) remain meaningful; volume-based panels (OBV, the volume audit row)
> are inert for those series.

### Comparison Window

```bash
python Option-OGN.py GLD SLV 250            # last 250 common trading observations
python Option-OGN.py --pdf GLD SLV 250      # charts/GLD_vs_SLV_250obs_Analysis.pdf
python Option-OGN.py --pdf WTI JP10Y 120    # last 120 monthly observations
python Option-OGN.py --pdf WTI JP10Y --periods 120  # equivalent named option
python Option-OGN.py GLD SLV                # omitted → full common horizon
```

- **Omitted**: use the common history. Weekly and slower comparisons use the latest
  consecutive run of usable periods, so a missing month is not treated as a one-month lag.
- **Supplied**: use the latest N observations *after* alignment. N means months for a
  monthly comparison, quarters for quarterly, years for annual, and common observations
  for daily. It never means N calendar days. The Python API retains the legacy name `days`.
- At least 3 aligned observations are needed for descriptive charts. Below 60
  (`COMP_MIN_OBS`), cointegration, Granger tests and mutual information are marked
  unavailable; levels, residuals, correlation and DTW remain descriptive, not inferential.
- If N exceeds the available overlap, everything available is used and the console says so.
- Only applies to the comparison, not to the technical-analysis chart.
- The window is echoed on the console, in the chart title, and in the generated PDF name.
- New filenames use `obs` rather than `d`; explicit frequency/aggregation choices are
  included in filenames so alternate reports do not overwrite the default report.

### Mixed-Frequency Alignment

**Default: compare at the slower source frequency.** For `WTI` versus `JP10Y`, every
Japanese monthly yield is matched with the mean of WTI's available daily prices in that
same calendar month. Month-start and month-end source timestamps identify the same month;
the chart labels the aligned observation at month-end. February data stamped on a Saturday
is not lost just because WTI had no observation that day.

| Inputs | Automatic Comparison Grid | Default Faster-Series Treatment |
|---|---|---|
| Daily + daily | Exact common observation dates | No resampling or filling |
| Daily + weekly | Friday-ending calendar weeks | Mean daily levels; latest weekly observation per week |
| Daily/weekly + monthly | Calendar months | Aggregate higher-frequency observations within each month |
| Daily/monthly + quarterly | Calendar quarters | Aggregate within each quarter |
| Monthly/quarterly + annual | Calendar years | Aggregate within each year |

Stored `Frequency` metadata takes precedence. Older files without it use median date
spacing to infer daily/weekly/monthly/quarterly/annual cadence; reports say whether each
frequency was declared or inferred. Unsupported irregular cadence is rejected rather
than silently guessed. Calendar dates are preserved when stripping timezone information.
Derivatives retain the existing front-month-future selection before temporal aggregation.

Default aggregation is series-specific, applied **only when downsampling**:

- **Mean** for prices, yields, rates, indexes and ratios. This includes annualized-rate
  series such as housing starts or GDP: do not sum annualized rates across periods.
- **Last observation** for `FEDASSETS`, `PAYEMS`, `JPXBYEN`, `JPFOREIGN`, and
  `JPCOTSHORT`, which represent stocks or positions.
- **Sum** for period-total flows `INTRADEBAL`, `JPCURRENT`, `USRETAIL`, and selected
  value columns `Volume`, `Deliverable Qty`, `Qty Short Sold`, and `Traded Value`.
- Native-frequency observations keep their published value. These defaults are explicit
  in the comparison constants in [Option-OGN.py](Option-OGN.py), not inferred from magnitudes.

For a period-end price question, override the mean with `last`; for a broader horizon,
request a coarser frequency:

```powershell
python Option-OGN.py --pdf WTI JP10Y 120 --compare-aggregation last
python Option-OGN.py --pdf WTI JP10Y --compare-frequency quarterly --periods 60
python Option-OGN.py --pdf JPWAGES WTI 120
```

`--compare-frequency`: `auto`, `daily`, `weekly`, `monthly`, `quarterly`, `annual`.
`--compare-aggregation`: `auto`, `mean`, `last`, `sum`. Overrides apply to downsampled
legs, not the native-frequency observations; use `sum` only for additive flows.
Requesting a frequency finer than either source is rejected. Both settings and each
series' transformation are printed and shown on the comparison page.

**Missing and incomplete periods:** no interpolation, forward-fill or backward-fill.
Open current weeks/months/quarters/years are excluded. Daily-to-slower aggregation needs
at least 80% of the period's Monday-Friday dates (`COMP_MIN_PERIOD_COVERAGE`), allowing
normal holiday gaps without accepting a handful of daily prices as a monthly average.
Weekly-to-slower aggregation requires at least 80% of expected Friday-ending weeks.
Monthly-to-quarterly/yearly and quarterly-to-yearly aggregation require every component
period. The weekday rule is a coverage heuristic, not an exchange-specific holiday calendar.
After joining, a missing weekly/monthly/quarterly/annual period starts a new contiguous
segment; only the latest segment is used for lag statistics. Exclusion counts are reported.
Daily lags remain counts of common observations, not elapsed calendar days.

**This is an observation-period comparison, not a release-time backtest.** A monthly
CPI timestamp usually describes its reference month, not the day investors learned the
number. CFTC Tuesday positions and weekly market averages are also different within-week
observation conventions. Publication delays, intraday close-time differences and revisions
are not modeled. A trading/backtest workflow needs release timestamps and as-of vintages;
the current aligned histories must not be presented as information available in real time.

### Measures reported

| Measure | What it measures | Quant use case |
|---|---|---|
| **Cointegration** | Whether a linear combination forms a stable mean-reverting spread | Pairs trading / statistical arbitrage |
| **Granger Causality** | Whether past values of A help forecast B (tested both directions) | Lead-lag strategies, leading macro indicators |
| **Cross-Correlation** | Correlation across lags in the selected sampling periods | Descriptive lead/lag association |
| **Dynamic Time Warping** | Shape similarity allowing for speed/phase differences | Matching historic regimes with different cycle speeds |
| **Mutual Information** | Shared information, linear *and* non-linear | Feature selection for ML alpha models |

### Methodology notes

- **Cointegration and DTW run on aligned levels.** Granger, cross-correlation and mutual
  information use changes calculated *after* alignment. Positive price/index series use
  log changes; series containing zero or negative levels use first differences. Series
  whose `Unit` is percent use percentage-point changes, even when every rate is positive.
  Each leg is transformed independently and its transformation is displayed.
- **Cointegration** is only attempted with at least 60 observations and ADF evidence
  consistent with both levels being I(1): the level test does not reject a unit root at
  5%, while the first-difference test does. These are imperfect diagnostic screens, not
  proof of integration order, cointegration stability or profitability.
- **Granger** needs at least 60 aligned observations and ADF rejection of a unit root in
  both transformed series. The lag search is capped at 10 periods (4 quarterly or 2 annual),
  and further limited by sample size. The displayed p-value is Bonferroni-adjusted for
  the number of lags searched **within each direction**; it does not correct for testing
  many ticker pairs. Results are in-sample, exploratory, and do not establish causation.
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

The report is a single PDF (or a sequence of interactive windows). With two symbols it
contains, in order:

**1. The full technical analysis of the first symbol** \u2014 EMA/SMA crossovers, MACD, RSI &
ADX, Fibonacci retracements, Bollinger Bands & OBV, Renko, and the technical audit table.

**2. The regression trendline page of the first symbol**, followed by its **volatility
profile**: cone, per-window box plots, rolling
estimator with quantile bands, distribution histogram, and a summary table. Eligible
option IV is overlaid on the cone, with per-expiry CE/PE date-series pages immediately
afterwards when `option_overlay` is enabled.

**3. The comparison page**, containing:

1. Both series as levels on twin axes
2. Both rebased to 100, or both standardized when either has zero/negative levels
3. An OLS residual with mean and two-standard-deviation bands (not automatically cointegrated)
4. The cross-correlation function, with the strongest lag highlighted
5. A colour-coded summary table \u2014 measure name, value, a plain-English reading of *this*
   result, and a one-line note on what the measure tells you

The same table is printed to the console, with the selected cadence, aggregation,
transformations, sample window and exclusions. The **three Japan macro pages**, **two US
Schiller pages** and **two India Schiller pages** follow once per PDF. If comparison is
unavailable, the other report pages remain and the
reason is printed. This frequency handling applies to the comparison; the first symbol's
technical and volatility pages still use their existing observation-based windows.

Regression checks: `python -m unittest test_option_overlay test_comparison test_japan_macro test_valuation_macro -v`.

---

## Requirements

- Python 3.10+
- See [requirements.txt](requirements.txt) for full list
- `yfinance` is required for the Yahoo macro series (`GLD`, `SLV`)
- `statsmodels`, `scikit-learn` and `dtaidistance` are required for the statistical
  comparison
- `scipy` is required for the volatility histogram's normal fit
- `vollib>=1.0.11` supplies Black-76 implied-volatility inversion; `adjustText` places
  option labels, and `statsmodels` supplies the robust smile fit
- Optional: TA-Lib (C library + Python wrapper), trendln, stocktrends