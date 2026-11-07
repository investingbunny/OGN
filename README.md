# OGN - NSE Market Data & Technical Analysis

NSE/macro downloads, zstd Parquet storage, Python loaders and technical/volatility/comparison reports.

## Quick Start

Python 3.10+; dependencies: [requirements.txt](requirements.txt). TA-Lib, trendln and stocktrends are optional.

```powershell
pip install -r requirements.txt
python "OGN v2.0-download.py"
python OGN.py                              # store summary
python Option-OGN.py --pdf WTI 250d         # latest 250 trading days
python Option-OGN.py List "<file>.parquet" 20 # latest 20 rows of any Parquet file
python diagnose_store.py --deep 10 --timing # read-only health/cost report
```

**Before downloading:** `MarketData_Parquet` must exist under
`C:\OGN-OneDrive\OneDrive\Github projects\OGN`. Missing store: exit code 1, no creation/download.
For a fresh install, create an empty folder first; NSE backfills from 2010. Never create a replacement
for an existing store that has not moved/synced.

Moving storage requires updating `DATA_ROOT` in [OGN.py](OGN.py),
[OGN v2.0-download.py](OGN%20v2.0-download.py), [parquet_cleanup.py](parquet_cleanup.py), and
`CHARTS_DIR` in [Option-OGN.py](Option-OGN.py). Scripts work from any directory; legacy `Datastore`
paths remain project-relative. The downloader prints its chosen path.

[diagnose_store.py](diagnose_store.py) reports sizes/shapes, daily rewrite cost, duplicates,
date-named columns, online-only files and sync conflicts. It never writes to the store or hydrates
online-only files; JSON and `--timing` rewrite copies go to the temp folder.

## Main Files

| File | Purpose |
|---|---|
| [OGN v2.0-download.py](OGN%20v2.0-download.py) | Downloads, incremental merges, deduplication and recovery. |
| [OGN.py](OGN.py) | Parquet loaders and store summary. |
| [Option-OGN.py](Option-OGN.py) | Interactive/PDF reports and Max Pain helpers. |
| [japan_macro.py](japan_macro.py) | Japan macro/carry-trade registry and downloads. |
| [schiller_macro.py](schiller_macro.py) | US-only Shiller/Multpl valuations. |
| [nifty_macro.py](nifty_macro.py) | Indian-only NIFTY valuations/CAPE estimate. |
| [option_overlay.py](option_overlay.py) | CE/PE IV selection, Black-76 and smile diagnostics. |
| [diagnose_store.py](diagnose_store.py) | Read-only store diagnostics. |
| [models.py](models.py) | Estimator dispatch: `get_estimator(price_data, window, clean)`. |

## Analysis CLI

```text
python Option-OGN.py [--pdf] [options] [symbol] [compare_symbol] [window]
```

```powershell
python Option-OGN.py                       # interactive, all FnO
python Option-OGN.py RELIANCE               # any stored source
python Option-OGN.py WTI 250d               # last 250 trading days
python Option-OGN.py --pdf WTI 350d-25d     # 350 back to 25 back: 325 days, latest 25 excluded
python Option-OGN.py --pdf WTI Jan2026      # January 2026; ranges such as Jan2026-Mar2026 too
python Option-OGN.py WTI US02Y__US10Y 250d  # first-symbol analysis + ratio comparison
python Option-OGN.py --pdf WTI JP10Y --periods 120 # 120 aligned months
python Option-OGN.py --pdf output.pdf       # custom output base name
```

- **Window** (last argument): `Nd` = latest N trading days (observations at the analysed cadence);
  `Nd-Md` = N back to M back, excluding the latest M; `MonYYYY` or `MonYYYY-MonYYYY` = calendar
  months (`Jan` or `January`, any case). A bare number is rejected; `--periods N` equals `Nd`, use one.
  A window requires a symbol; shorter available history is used with a console notice.
- **One symbol + window:** technical, trendline and volatility pages use only the window. Nothing after
  its last day is used; indicators warm up on earlier history, option IV pages are as of that day.
  Trendlines keep their own bar cap, Renko its last 100 bricks, macro appendices their five-year view.
- **Two symbols + window:** only the comparison is limited, after alignment; primary pages keep
  defaults. Counts are aligned observations at the comparison cadence (months for monthly data).
- `NUM__DEN` computes a ratio in memory after aligning legs to the slower cadence; zero denominators
  are excluded. Exactly one `__` is allowed. `GLD_SLV` loads stored data; `GLD__SLV` computes it.
  Single-value sources become flat OHLC bars with zero volume; volume indicators are inert.

| Option | Meaning |
|---|---|
| `--estimator NAME` | Default `YangZhang`; alternatives below. |
| `--trend-bars N`, `--trend-distance N` | Positive lookback/pivot spacing; bars >= `2 * distance + 1`. |
| `--trend-prominence X` / `--trend-prominence-pct X` | Absolute price units / percent of window range; positive, mutually exclusive. |
| `--compare-frequency FREQ` | `auto` (slower source), `daily`, `weekly`, `monthly`, `quarterly`, `annual`. |
| `--compare-aggregation METHOD` | `auto` (series-specific), `mean`, `last`, `sum`; downsampled legs only. |

Comparison overrides require two symbols. Example:
`python Option-OGN.py --pdf WTI JP10Y 120d --compare-frequency quarterly --compare-aggregation last`.

Default PDF bases: `charts\FnO_Analysis.pdf`, `charts\WTI_Analysis.pdf`,
`charts\WTI_350d-25d_Analysis.pdf`, `charts\WTI_vs_US10Y_Jan2026_Analysis.pdf`.
Explicit comparison settings enter filenames. **Every PDF**, including custom names, gains
`_YYYYMMDD_HHMMSS` before `.pdf`; same-second collisions gain `_2`, preventing overwrites.
The console prints each saved PDF's full path, including custom relative names.

Page order: technical/audit -> trendlines -> volatility -> guide -> option IV by expiry ->
optional comparison. PDFs append Japan (3 pages), US Schiller (2), India Schiller (2), once each.
Macro panels show five years of cached data, source/definition/frequency/units/latest date and gaps.

In [Option-OGN.py](Option-OGN.py), comment `REPORT_SECTIONS` entries to disable sections:
`technical`, `trendlines`, `volatility`, `volatility_guide`, `option_overlay`, `comparison`,
`japan_macro`, `schiller_macro`, `india_schiller`. `VOLATILITY_PANELS` controls individual panels.
Unavailable sections print a reason without removing other pages.

### List Parquet Rows

```powershell
python Option-OGN.py List "<path>\ABB.parquet"            # latest 10 rows
python Option-OGN.py List "<path>\ABB.parquet" 50         # latest 50 rows
python Option-OGN.py --pdf List "<path>\ABB.parquet" 50   # also charts\ABB_latest50_rows_<stamp>.pdf
python Option-OGN.py --pdf List "<path>\ABB.parquet" 50 abb.pdf # custom PDF base name
```

Works on any Parquet file. With a `Date` column (any case), rows are the newest dates (corrected as in
[Correct Dates](#correct-dates)); same-date rows keep file order and undated rows rank oldest. Without
usable dates, the last rows in file order are shown. All columns are printed, wrapped to the console
width; the first column is the row's 0-based file position. Only row groups holding those rows are read.
A header line counts corrected dates; rows dated after today trigger a warning.
`--pdf` (before or after `List`) also saves the table as a timestamped PDF and prints its full path.
Quote paths containing spaces.

### Correct Dates

Some stored F&O UDiFF rows have day and month swapped in `Date` and `Expiry` whenever the day is 12 or
less (trade date 2024-08-01 stored as 2024-01-08). Their NSE columns hold the true values, so every
loader, report page, comparison and `List` reads dates as follows; stored files are not modified:

| File format | `Date` | `Expiry` |
|---|---|---|
| F&O with NSE columns (e.g. `Derivatives\Processed\ABB.parquet`) | `BizDt` where valid, else stored `Date` | `FininstrmActlXpryDt` where valid, else stored `Expiry` |
| Without them (equity, legacy F&O rows, indices, macro) | Stored `Date` | Stored `Expiry` |

Loaded rows are re-sorted by the corrected `Date`. `corrected_dates(frame, column)` in [OGN.py](OGN.py)
applies the same rule to frames you read yourself.

## Python Loaders

```python
from OGN import (load_equity, load_futures, load_monthly_options, load_equity_panel,
                 load_index, load_macro, data_summary)

df = load_equity("RELIANCE", start="2024-01-01")
futures = load_futures("RELIANCE")         # all contracts
options = load_monthly_options("RELIANCE") # nearest month, puts
panel = load_equity_panel(["RELIANCE", "TCS", "INFY"], start="2024-01-01") # wide Close panel
nifty = load_index("NIFTY")
us10y = load_macro("US10Y")
gold_silver = load_macro("GLD_SLV")
```

Other loaders include `load_options` and `load_derivatives`; see [OGN.py](OGN.py).
`latest_parquet_rows(path, rows)` returns `(rows, total_rows, date_column)` for any Parquet file.

## Technical & Volatility Pages

Technical panels cover averages, MACD, RSI/ADX, Fibonacci, Bollinger/OBV, futures fair value,
Renko and an audit. Default view: one calendar year (`TECHNICAL_WINDOW_YEARS = 1`), unless a
single-symbol N overrides it. Full-history indicators remain warmed up. Consecutive price-bar
positions remove weekend/holiday/missing-price gaps; ticks label the first trading day per month.
Renko independently uses full history and shows 100 bricks.

| Audit row | Buy | Sell | Hold |
|---|---|---|---|
| 50/200 SMA, 9/21 EMA, 13/48 EMA, 5E/20S, MACD/Signal, Close/BB mid | First above second | First below second | Within `AUDIT_HOLD_ATR = 0.1` x ATR(20) |
| RSI 14 | >60 | <40 | 40-60 |
| Fib, last 60 bars | Above 61.8% | Below 38.2% | Between |
| Volume vs 1.2x average | Up-close surge | Down-close surge | No surge |

Buy/Sell/Hold are green/red/amber with a verdict. Missing inputs: Hold / *Not enough history*;
no latest volume: omit volume row. Trendlines use scipy pivots and numpy regression.

### Volatility Analysis

| Estimator | Inputs | Meaning |
|---|---|---|
| [YangZhang](YangZhang.py) | OHLC | Default; overnight gaps/drift |
| [GarmanKlass](GarmanKlass.py) | OHLC | Efficient; assumes no drift |
| [Parkinson](Parkinson.py) | HL | Range-only |
| [RogersSatchell](RogersSatchell.py) | OHLC | Drift-independent |
| [HodgesTompkins](HodgesTompkins.py) | C | Bias-corrected close-to-close |
| [Raw](Raw.py) | C | Close-to-close standard deviation |
| [Skew](Skew.py) | C | Return skew, not volatility |
| [Kurtosis](Kurtosis.py) | C | Return kurtosis, not volatility |

Volatility: 252 observations/year, displayed in percent. Moments: plain numbers.
Flat bars make GarmanKlass/Parkinson/RogersSatchell zero; warnings suggest Raw/HodgesTompkins/YangZhang.

| Panel | Content |
|---|---|
| `cone` | Min/25th/mean/median/75th/max by window; latest realized value and eligible option IV |
| `box` | Per-window distributions |
| `rolling` | History with quantile bands |
| `histogram` | Distribution, normal fit, latest value |
| `summary` | Latest, percentile rank, median, range, sample count |

Above the upper cone band means rich relative to realized history. The guide explains enabled
graphs with this report's numbers; moments omit combined option-pricing interpretation.
Tune `VOLATILITY_WINDOWS = [3, 5, 10, 20, 30, 60, 90]`, `VOLATILITY_WINDOW = 30`,
`VOLATILITY_QUANTILES = [0.25, 0.75]`, `DEFAULT_ESTIMATOR = 'YangZhang'` in the script.

## CE/PE Implied-Volatility Overlays

First symbol only; requires stored derivatives and enabled `volatility` + `option_overlay`.
Select five highest-volume calls/puts per expiry/date, plus qualifying smile outliers.
Green/red dots show annualized CE/PE IV with strike/expiry labels; black outlines mark outliers.
The cone uses latest-underlying-date monthly quotes at remaining weekday tenors, never stale quotes.
Matching realized windows are added when history permits.

Expiry pages: next three monthly expiries (last listed per month), plus next five expiries of
any kind where weeklies exist; deduplicate overlap, use stored holiday-adjusted dates, exclude
expired/expiry-day contracts. Monthly/Weekly titles, CE/PE panels, latest-contract tables and
how-to-read lines accompany up to five dates/page; longer windows paginate.
Counts: `OPTION_MONTHLY_EXPIRIES`, `OPTION_SERIES_EXPIRIES` in [option_overlay.py](option_overlay.py).

| Option | Default | Meaning |
|---|---|---|
| `--option-dates N` | `5` | Latest N underlying observation dates, not calendar days/nonempty snapshots |
| `--option-min-contracts N` | `10` | Minimum traded `Contracts`, not OI/turnover |
| `--option-outliers N` | `2` | Extra outliers per side/expiry/date: 0/1/2; 0 disables scoring |
| `--option-rate R` | `0.065` | Fixed continuously compounded annual decimal rate; 0.055 = 5.5% |
| `--option-iv-unit UNIT` | `percent` | Explicit `percent`/`decimal`, never magnitude-inferred |

Example: `python Option-OGN.py --pdf BANKNIFTY --option-dates 10 --option-min-contracts 50`.
Moments, monthly/quarterly data, duplicate underlying dates and flat-bar range estimators exclude IV.
Missing derivatives/valid IV leave historical charts usable.

<details>
<summary>IV eligibility, pricing and outlier methodology</summary>

- Read all expiries through `load_derivatives`, without downloads/writes. Required columns:
  `Date`, `Expiry`, `Symbol`, `Option type`, `Strike Price`, `Contracts`. Finite positive strikes
  and minimum volume required; duplicate date/expiry/side/strike rows keep last, volume ties use
  ascending strike. Fewer qualifying quotes produce fewer dots.
- Valid `Implied Volatility` (preferred) / `IV` wins, even without a future/solver.
  Percent mode: `20`/`20%` = 20%; decimal mode: `0.20` = 20%, percent suffix rejected.
- Missing IV: vollib Black-76 using same ticker/date/expiry future (legacy and UDiFF `IDF/STF`).
  Both settlement prices, or both close if settlement is missing/nonpositive; never mixed bases.
  Bounds failures, ambiguous futures and solver failures are skipped; invalid settlement bounds
  never trigger a close-price retry.
- No listed same-expiry future: parity `F = K + exp(rT) * (C - P)`, median at three strikes with
  closest traded CE/PE prices. Settlement/close forwards remain separate; >10% spot deviation
  rejected. Label *Black-76 parity estimate*. Never substitute another expiry's future or escape
  ambiguous futures via parity. No reported IV/future/parity pair means unavailable IV.
- Black-76: ACT/365 calendar time, European-style assumptions. Realized: 252 observations/year,
  weekday tenors, not exchange holiday calendars. No inferred synchronous quotes, spreads,
  historical curves or intraday expiry time.
- Realized references use history through each option's date, its remaining tenor >=2 sessions,
  and >=30 valid estimator observations. Mean +/- SD is descriptive, not a confidence interval;
  volume leaders can change daily. Tables show contracts, IV/source, realized mean,
  IV-minus-mean (percentage points), MAD score and selection reason.
- Per date/expiry/side, fit a Huber quadratic to centered/scaled log strike across >=12 distinct
  eligible strikes. Median-center residuals; normally adjusted MAD floor: 0.005 annualized IV
  (0.5 percentage points). Flag absolute score >=3.5, excluding two lowest/highest strikes.
  Add at most N largest-score extras; sparse/degenerate/nonconvergent fits add none.
- Smile-adjusted MAD avoids extreme-quote z-score inflation and raw-IQR/smile confusion.
  Volume screens do not check freshness/spreads. Outliers can be bad quotes/fits; IV-minus-realized
  can be normal risk premium, not mispricing/arbitrage evidence.

Synthetic pricing/layout fixtures and 14-22 October 2026 NSE bhavcopies validated holiday-adjusted
expiries, NIFTY-only weekly index contracts and monthly parity within 0.1% of matching futures.
No market-outlier claim is made.

</details>

## Statistical Comparison

Any two stored categories/ratios; comparisons append after the first symbol's primary pages.

| Inputs | Automatic grid |
|---|---|
| Daily + daily | Exact common dates, no resampling/filling |
| Daily + weekly | Friday-ending weeks; daily mean, latest native weekly value |
| Daily/weekly + monthly | Calendar months |
| Daily/monthly + quarterly | Calendar quarters |
| Monthly/quarterly + annual | Calendar years |

Stored `Frequency` wins; otherwise median spacing infers regular cadence and is reported.
Unsupported irregular cadence/upsampling is rejected. Timezone stripping preserves calendar dates;
month-start/end identify the same month, including weekends. Front-month futures are selected first.

Downsampling defaults (native values unchanged; overrides affect only faster legs):
- **Mean:** prices/yields/rates/indexes/ratios, including annualized GDP/housing starts.
- **Last:** `FEDASSETS`, `PAYEMS`, `JPXBYEN`, `JPFOREIGN`, `JPCOTSHORT`.
- **Sum:** `INTRADEBAL`, `JPCURRENT`, `USRETAIL`, `Volume`, `Deliverable Qty`, `Qty Short Sold`,
  `Traded Value`. Only additive flows should use sum, never annualized rates.

No filling; exclude open periods. Daily-to-slower needs 80% weekdays (`COMP_MIN_PERIOD_COVERAGE`);
weekly-to-slower needs 80% expected Friday weeks; monthly/quarterly-to-slower needs every component.
This is a coverage heuristic, not an exchange calendar. Slower-frequency gaps start new segments;
only the latest consecutive segment is used. Daily lags count common observations.
No window uses common history; a window takes the aligned periods inside it (its end is applied
before the latest segment is chosen), reporting shortfalls/exclusions.
At least 3 observations for descriptive plots, 60 (`COMP_MIN_OBS`) for inferential measures.
The Python API keeps the legacy name `days=`, taking window text (e.g. `'350d-25d'`) or a count.

| Measure | Method / Use |
|---|---|
| Cointegration | statsmodels, aligned levels; potential mean-reverting spread/pairs relationship |
| Granger | statsmodels, transformed changes, both directions; forecast lead/lag association |
| Cross-correlation | pandas, changes; positive lag = symbol1 leads symbol2 |
| DTW | dtaidistance, z-normalized levels; shape/regime similarity |
| Mutual information | scikit-learn k-NN/Kraskov, changes, bits; nonlinear feature dependence, near zero for independent series |

Changes are computed after alignment, independently: logs for positive prices/indexes, differences
for nonpositive levels, percentage-point differences for percent-unit series.
Cointegration requires ADF-consistent I(1): no level rejection at 5%, difference rejection.
Granger requires ADF stationarity rejection for both changes; max 10 lags (4 quarterly/2 annual),
sample-limited, Bonferroni-adjusted within each direction, not across pairs.
DTW uses a Sakoe-Chiba band, <=1,000 points and length-normalized distance; C extension or Python.
Below 60 observations, cointegration/Granger/MI are unavailable; levels/residuals/correlation/DTW remain descriptive.

Output: twin-axis levels; rebased-to-100 series (standardized for nonpositive levels); OLS residual
with mean +/- 2 SD (not automatically cointegrated); strongest-lag cross-correlation; color-coded
measure/definition/value/reading/note table. Console omits definitions but reports cadence,
aggregation, transformations, window and exclusions; explicit settings also enter filenames.

**Limits:** observation dates are not release timestamps (CPI reference month; CFTC Tuesday
positions normally released Friday). Delays, within-period conventions, close times and revisions
are not modeled; backtests need release timestamps/as-of vintages. Reports are diagnostic,
in-sample/exploratory: individual audit rows, IV estimates/outliers and statistical associations
do not establish executable prices, causation, profitability or trade signals.

## Data Categories & Updates

<details>
<summary>Storage directories, NSE layouts and migration safety</summary>

Processed path: `MarketData_Parquet\<directory>\Processed`; raw day prefixes:

| Category | Prefix | Directory |
|---|---|---|
| Equity | `cm` | `Equity` |
| Derivatives | `fo` | `Derivatives` |
| Indices | `idx` | `Indices` |
| Short Selling | `ss` | `ShortSelling` |
| Volatility | `vol` | `Volatility` |
| Market Activity | `ma` | `MarketActivity` |
| Price Band | `pb` | `PriceBand` |
| PE Ratio | `pe` | `PERatio` |
| Corporate Bonds | `cb` | `CorporateBonds` |
| Delivery Positions | `del` | `DeliveryPositions` |
| WDM Daily | `wdm` | `WDM` |
| Macro | - | `Macro` |

- Cash/F&O uses UDiFF from 1 January 2024 (legacy overlap through 5 July). Stored days are not
  re-fetched solely for layout changes. `load_derivatives()` normalizes:
  - `Underlying Price`: `UndrlygPric`, or legacy same-date cash **EQ** close on the same corporate-action basis.
    Legacy index mappings: NIFTY/MINIFTY -> NIFTY; BANKNIFTY; NIFTYNXT50 -> NIFTYNEXT50;
    NFTYMCAP50/NIFTYMID50 -> NIFTYMIDCAP50. Unstored indices retain missing spot.
    Cash close matched UDiFF spot within 0.02% in a July 2024 check.
  - `Lot Size`: `NewBrdLotQty`, unavailable in legacy. `IDF/STF/IDO/STO` -> `FUTIDX/FUTSTK/OPTIDX/OPTSTK`.
    `Value` becomes rupees; legacy lakh x 100,000.
- Per-symbol, strictly newer/type-compatible rows fast-append through pyarrow; overlap/late/type
  changes use pandas merge/deduplication, with identical results and append counts in logs.
  Completed temporary-file replacement protects raw/processed data from interruptions/transient locks.
- Sync copies are logged, never deleted/renamed: per symbol/filename day, UDiFF wins, otherwise
  original. Different report days never deduplicate each other's earlier-dated short sales;
  unused copies stay in `Raw`.
- Market Activity date headers become `Details`; its two-field layout retains summary/section lines,
  not wider tables. WDM uses real issue-list headers and stable `Debt_trd_sett`, `Debt_add`, `Debt_mat`.
  Previously skipped raw rows need re-download. Short Selling maps `Security Symbol` to `Symbol`, not `UNKNOWN`.
- Normal downloads automatically run one-time repairs: recover same-date/symbol rows in Equity/Price Band/Delivery/Market Activity/
  Short Selling/WDM; re-fetch pre-late-2015 indices missing NIFTY (~1,450 days, old names/2010-2011
  PR columns); rebuild date-named/unmapped Market Activity/WDM/Short Selling.
  Rebuild **only with all contributing raw files present/readable**, otherwise warn and preserve.
  First upgrade is slower; `MarketData_Parquet\.migrations.json` records completion; interruptions resume.

</details>

## Macro Data Sources

Normal downloads include all groups. Group-only switches avoid NSE:
`--japan-only`, `--schiller-only`, `--india-schiller-only`.

<details>
<summary>Tickers, source definitions, refresh rules and unavailable indicators</summary>

Schema: `Date, Symbol, Value, Series, Name, Unit, Source, Frequency, Description`.
Comment registry entries to skip: `FRED_SERIES`, World Bank, `YAHOO_SERIES`, `MACRO_RATIOS` in
[OGN v2.0-download.py](OGN%20v2.0-download.py); `JAPAN_SERIES`, `SCHILLER_SERIES`, `NIFTY_SERIES`
in their modules, shared by downloads/reports.

Normally backfill 50 years (`MACRO_MAX_HISTORY_YEARS`); Yahoo uses max history, US valuations longer.
Revision overlaps: daily 10 days, monthly/quarterly FRED 400 days, annual World Bank five years.
Merge on Date/newest row, sort, atomic write; normalize FRED `DATE`/`observation_date`, Yahoo
`Close`/`Adj Close`, thousands separators, timezone/calendar dates and float values.

### Core Series

| Symbol | Source ID | Definition / Unit |
|---|---|---|
| `US02Y` | FRED `DGS2` | US 2-year Treasury constant-maturity yield, % |
| `US10Y` | FRED `DGS10` | US 10-year Treasury constant-maturity yield, % |
| `US03M` | FRED `DTB3` | US 3-month Treasury bill secondary-market rate, % |
| `GVZ` | FRED `GVZCLS` | CBOE Gold ETF Volatility Index |
| `USCORPOAS` | FRED `BAMLC0A0CM` | ICE BofA US Corporate Index OAS, % |
| `USHYOAS` | FRED `BAMLH0A0HYM2` | ICE BofA US High Yield Index OAS, % |
| `USDJPY` | FRED `DEXJPUS` | JPY per USD |
| `USDINR` | FRED `DEXINUS` | INR per USD |
| `EURUSD` | FRED `DEXUSEU` | USD per EUR |
| `FEDTARU` | FRED `DFEDTARU` | Fed target upper limit, % |
| `T10Y2Y` | FRED `T10Y2Y` | 10-year minus 2-year spread, % |
| `T10YIE` | FRED `T10YIE` | 10-year breakeven inflation, % |
| `FEDASSETS` | FRED `WALCL` | Fed assets, USD million |
| `WTI` | FRED `DCOILWTICO` | WTI crude, USD/barrel |
| `STLFSI` | FRED `STLFSI4` | St. Louis Fed Financial Stress Index |
| `GLD` | Yahoo `GLD` | SPDR Gold Shares ETF, USD |
| `SLV` | Yahoo `SLV` | iShares Silver Trust ETF, USD |
| `GLD_SLV` | `GLD / SLV` | Stored ETF price ratio on overlapping dates |

OAS = option-adjusted spread. ICE FRED feeds expose rolling three-year history from April 2026
due to licensing; older local history remains. Add ratios as `(symbol, numerator, denominator, name)`.

### Japan Macro & Carry Trade

Example: `python "OGN v2.0-download.py" --japan-only`; `python Option-OGN.py --pdf JPUSDJPY`.
Three appendix groups: funding/carry; growth/inflation/wages; positioning/capital flows.
`JPUSDJPY` leaves FRED `USDJPY` unchanged.

| Ticker | Source ID | Frequency | Definition / Unit |
|---|---|---|---|
| `JPUSDJPY` | Yahoo `USDJPY=X` | Daily | JPY per USD; decline = yen appreciation, not streaming |
| `JP10Y` | FRED/OECD `IRLTLT01JPM156N` | Monthly | Japanese 10-year government yield, %, not real-time |
| `JPPOLRATE` | BIS `WS_CBPOL/D.JP` | Daily | BOJ policy rate, %; historical regimes/gaps |
| `JPCOTSHORT` | CFTC `6dca-aqww`, `097741` | Weekly | CME yen futures-only noncommercial shorts minus longs, contracts; positive = net short |
| `JPLEADING` | ESRI CI Leading | Monthly | Composite leading index, 2020=100; not OECD CLI/diffusion |
| `JPTOKYOCORE` | Dashboard `0703010601010030010`, `13100` | Monthly | Tokyo ku-area CPI ex-fresh-food YoY %, includes energy |
| `JPCORECPI` | Dashboard `0703010601010030010`, `00000` | Monthly | National CPI ex-fresh-food YoY %; BOJ 2% target formally all-items |
| `JPWAGES` | Dashboard `0302020000000030000`, `00000` | Monthly | Nominal total cash earnings YoY %, bonuses/overtime included; preliminary possible |
| `JPCURRENT` | MOF `6s-1-4` | Monthly | Unadjusted current account, JPY billion, converted from 100 million yen |
| `JPXBYEN` | BIS `WS_LBS_D_PUB/Q.S.C.G.JPY.A.5J.A.5A.A.5J.N` | Quarterly | All-bank cross-border yen loans/deposits, USD million; not carry size |
| `JPFOREIGN` | BIS `WS_CBS_PUB/Q.S.JP.4R.F.C.A.A.TO1.A.5J` | Quarterly | Japanese banks' consolidated foreign claims, immediate-counterparty, USD million; includes non-loans, excludes domestic |

Unavailable exact indicators remain gaps, never substitute/fake histories:

| Ticker | Required indicator / Limitation |
|---|---|
| `JPTANKAN` | BOJ large manufacturers' actual business-conditions DI, quarterly; access unavailable at verification, adapter unconfigured |
| `JPPMI` | S&P Global/au Jibun Bank Japan Composite Output PMI, monthly; no verified public history, provider access needed |
| `JPCOTINDEX` | MacroMicro JPY positioning COT index, weekly; no verified feed/normalization, not `JPCOTSHORT` |
| `JPJPYIV` | USD/JPY one-month ATM IV, daily annualized %; no verified history, realized not substituted |
| `JPCARRY` | Carry-to-risk; needs same-date Fed/BOJ rates and `JPJPYIV` |

`JPCARRY = (FEDTARU - JPPOLRATE) / JPJPYIV`, annualized % throughout, not MacroMicro replication.
No filling; exclude nonpositive/nonfinite IV, recompute full-overlap revisions. Japan-only uses
stored `FEDTARU`; normal download refreshes it first.
Yahoo overlap 10 days, regular sources 400 days, BIS banking five years; ESRI/MOF/CPI full history.
Failures preserve files. CPI uses official 2025-base published YoY, never cross-base calculations;
Dashboard may lag Tokyo preliminary releases. BIS exposures include non-carry business.

References: [CFTC](https://publicreporting.cftc.gov/), [BIS](https://data.bis.org/),
[ESRI](https://www.esri.cao.go.jp/en/stat/di/di-e.html),
[MOF](https://www.mof.go.jp/english/policy/international_policy/reference/balance_of_payments/ebpnet.htm),
[Dashboard API](https://dashboard.e-stat.go.jp/en/static/api).
API use does not imply Government of Japan guarantees. ESRI XLSX requires openpyxl>=3.1.

### US Schiller Valuation

**US Schiller** means Robert **Shiller**, S&P DJI/Multpl; no Indian inputs.
Example: `python "OGN v2.0-download.py" --schiller-only`;
`python Option-OGN.py --pdf WTI SCHCAPE --periods 120`.

| Ticker | Metric / Source | Frequency | History |
|---|---|---|---|
| `SCHCAPE` | Conventional PE10 / Shiller CAPE | Monthly | Jan 1881 onward |
| `SCHREAL` | Published real US composite price | Monthly | Jan 1871 onward |
| `SCHEARN` | Nominal trailing annual earnings / workbook E | Monthly, interpolated | Jan 1871 onward |
| `SCHEPS` | Single-quarter as-reported S&P 500 EPS / S&P DJI | Quarterly | Unavailable: official XLS HTTP 403, parser unconfigured |
| `SCHPE` | Trailing P/E / Multpl | Monthly | Jan 1871 onward |
| `SCHEY` | Earnings yield %, Multpl | Monthly | Jan 1871 onward |
| `SCHPS` | S&P 500 price/sales / Multpl | Quarterly | Dec 2000 onward, estimates included |
| `SCHPB` | S&P 500 price/book / Multpl | Quarterly | Dec 1999 onward, estimates included |
| `SCHBV` | Book value per index share / Multpl | Quarterly | Dec 1999 onward |

[Shiller's](https://shillerdata.com/) `ie_data.xls` composite is not the modern S&P 500 throughout
the 1800s. Conventional CAPE != total-return CAPE; real price != total-return index; annual earnings
!= quarterly EPS. Current prices/CPI can be preliminary/estimated; XLS needs xlrd>=2.0.1.

Multpl historical [P/E](https://www.multpl.com/s-p-500-pe-ratio/table/by-month),
[earnings yield](https://www.multpl.com/s-p-500-earnings-yield/table/by-month),
[P/S](https://www.multpl.com/s-p-500-price-to-sales/table/by-quarter),
[P/B](https://www.multpl.com/s-p-500-price-to-book/table/by-quarter),
[book value](https://www.multpl.com/s-p-500-book-value/table/by-quarter):
exclude live-date quotes, mark estimates in `Description`; no GuruFocus/paid-export bypass.
Keep full history, not the 50-year cap. Multpl overlap: 400 days; Shiller workbook: once/group,
fully revalidated. Rewrite all real-price history together to avoid mixed CPI bases; reject
truncated stored coverage. HTTP/rate-limit/parse retries preserve files and independent sources.

### India Schiller / NIFTY

Indian inputs only: no US inputs, Sensex or company-average substitutes.
`python "OGN v2.0-download.py" --india-schiller-only` refreshes `INCPI` and computes from existing
`MarketData_Parquet\Indices\Processed\NIFTY.parquet`; no NSE session/backfill.
Full downloads run this group after NSE index merge.

| Ticker | Metric / Availability |
|---|---|
| `INIIMCAPE` | Published IIM Ahmedabad India CAPE; dataset/universe/frequency/claimed 2004-present coverage unverified, not filled with estimate |
| `NIFTYCAPE` | Additional Indian NIFTY/CPI-based CAPE estimate, 120 complete months; not official NSE/IIM |
| `NIFTYPE` | Published NIFTY 50 P/E, last closed-month observation |
| `NIFTYPB` | Published NIFTY 50 P/B, monthly |
| `NIFTYEPS` | Same-date `Close / PE`, implied trailing earnings, not audited quarterly EPS |
| `NIFTYDY` | Published NIFTY 50 dividend yield %, monthly |
| `NIFTYEY` | `100 / PE` percent; P/E 20 -> 5%, not 0.05% |
| `INRBICPI` | RBI DBIE CPI Combined; export adapter unverified, not relabeled OECD/US |
| `INRBIWPI` | RBI DBIE all-commodities WPI; adapter unverified, never spliced into CPI |
| `NIFTYPS` | Aggregate historical NIFTY 50 P/S, BSE/Trendlyne/Screener; unverified, no company/Sensex substitute |
| `INCPI` | OECD/FRED Indian all-items CPI, 2015=100, ends March 2025; estimate deflator, not RBI DBIE |

For matching NIFTY price `P_t`, P/E `PE_t`, Indian CPI `C_t`:
`E_t = P_t / PE_t`; `NIFTYCAPE_t = (P_t / C_t) / mean(E_s / C_s for s = t-119, ..., t)`.
Last closed-month observations require 80% weekday coverage, all 120 calendar months,
valid positive inputs/consistent CPI bases; no filling, provenance rejects US CPI.
NSE earnings-methodology/composition changes limit comparability, without silent adjustments.
Recompute revisions/deduplicate; missing inputs write no fabricated/empty histories.
Discontinued CPI caps CAPE at March 2025 even with newer prices.

Portals: [IIM](https://www.iima.ac.in/),
[NSE](https://www.niftyindices.com/reports/historical-data),
[RBI DBIE](https://data.rbi.org.in/#/dbie/dataquery_enhanced), [BSE](https://www.bseindia.com/).
1999/2004-present are expectations, not guaranteed coverage; NSE backfills from 2010.
No unverified IIM/RBI/index-P/S export is claimed.

</details>

## Regression Checks

```powershell
python -m unittest test_option_overlay test_comparison test_japan_macro test_valuation_macro test_market_data test_technical_chart test_report_pages -v
```

statsmodels/scikit-learn/dtaidistance: comparisons; scipy: fits/pivots; vollib>=1.0.11: IV;
adjustText: labels; statsmodels: robust smiles; yfinance: Yahoo downloads.
Full list: [requirements.txt](requirements.txt).
