"""Indian-only NIFTY valuation definitions and estimated CAPE calculation."""

import datetime

import numpy as np
import pandas as pd


INDIA_CPI_SYMBOL = 'INCPI'
INDIA_CPI_SERIES = 'INDCPIALLMINMEI'
INDIA_CPI_UNIT = 'Index 2015=100'
CAPE_WINDOW_MONTHS = 120

NIFTY_SERIES = {
    'INIIMCAPE': {
        'name': 'India CAPE - IIM Ahmedabad (Requested)', 'provider': None,
        'series': 'IIM Ahmedabad / India CAPE (unverified)',
        'source': 'IIM Ahmedabad (requested)', 'frequency': 'Unverified', 'unit': 'Ratio',
        'url': 'https://www.iima.ac.in/',
        'description': 'Requested published India CAPE history. The exact dataset, '
                       'index universe, frequency and methodology have not been verified. '
                       'Never populated from the local NIFTY estimate or US Shiller data.',
        'unavailable': 'An exact IIM CAPE dataset or paper link is needed; coverage from 2004 is not yet verified.',
    },
    'NIFTYPE': {
        'name': 'NIFTY 50 Trailing P/E', 'provider': 'Stored NSE',
        'series': 'NIFTY / monthly last reported PE', 'source': 'NSE Indices (India)',
        'frequency': 'Monthly', 'unit': 'Ratio',
        'url': 'https://www.niftyindices.com/reports/historical-data',
        'description': 'Published NIFTY 50 trailing P/E at the last available trading '
                       'date of each closed month. Ordinary P/E, not CAPE. '
                       'Earnings methodology changes affect historical comparability.',
        'unavailable': 'Requires stored Indian NIFTY index history with Close and PE columns.',
    },
    'NIFTYCAPE': {
        'name': 'NIFTY 50 CAPE Estimate', 'provider': 'Derived',
        'series': 'NIFTY PE-implied EPS / 120-month India CPI-adjusted mean',
        'source': 'Derived / NSE India / OECD India CPI via FRED',
        'frequency': 'Monthly', 'unit': 'Ratio',
        'url': 'https://www.niftyindices.com/reports/historical-data',
        'description': 'Estimate from Indian NIFTY prices, P/E-implied trailing earnings '
                       'and Indian CPI over 120 complete months. No US inputs. '
                       'Not official NSE CAPE; composition and earnings-methodology breaks matter.',
        'unavailable': 'Requires 120 consecutive months of NIFTY Close/PE and INCPI. No filling or US-data fallback.',
    },
    'NIFTYPB': {
        'name': 'NIFTY 50 Price/Book', 'provider': 'Stored NSE',
        'series': 'NIFTY / monthly last reported PB', 'source': 'NSE Indices (India)',
        'frequency': 'Monthly', 'unit': 'Ratio',
        'url': 'https://www.niftyindices.com/reports/historical-data',
        'description': 'NIFTY 50 price relative to book value, at the last available '
                       'trading date of each closed month. Indian index-level valuation; '
                       'not a company screener average or a US price/book ratio.',
        'unavailable': 'Requires stored NIFTY PB observations from NSE Indices.',
    },
    'NIFTYEPS': {
        'name': 'NIFTY 50 Implied Trailing Earnings', 'provider': 'Derived',
        'series': 'NIFTY Close / NSE PE', 'source': 'Derived / NSE Indices (India)',
        'frequency': 'Monthly', 'unit': 'INR per index unit',
        'url': 'https://www.niftyindices.com/reports/historical-data',
        'description': 'Trailing earnings implied by the same-date NIFTY index close '
                       'divided by published P/E. A derived index quantity, not audited '
                       'single-quarter earnings. Earnings-methodology changes affect continuity.',
        'unavailable': 'Requires matched Indian NIFTY Close and positive PE observations.',
    },
    'NIFTYDY': {
        'name': 'NIFTY 50 Dividend Yield', 'provider': 'Stored NSE',
        'series': 'NIFTY / monthly last reported DY', 'source': 'NSE Indices (India)',
        'frequency': 'Monthly', 'unit': 'Percent',
        'url': 'https://www.niftyindices.com/reports/historical-data',
        'description': 'Published NIFTY 50 dividend yield, in percent, at the last '
                       'available trading date of each closed month. Dividend income '
                       'relative to index price; not earnings yield or total return.',
        'unavailable': 'Requires stored NIFTY DY observations from NSE Indices.',
    },
    'NIFTYEY': {
        'name': 'NIFTY 50 Earnings Yield', 'provider': 'Derived',
        'series': '100 / NSE NIFTY PE', 'source': 'Derived / NSE Indices (India)',
        'frequency': 'Monthly', 'unit': 'Percent',
        'url': 'https://www.niftyindices.com/reports/historical-data',
        'description': 'Inverse of published NIFTY trailing P/E, expressed as percent: '
                       '100 divided by P/E. For P/E of 20, yield is 5%. '
                       'Not dividend yield and not the inverse of CAPE.',
        'unavailable': 'Requires positive Indian NIFTY PE observations.',
    },
    'INRBICPI': {
        'name': 'India CPI Combined - RBI DBIE', 'provider': None,
        'series': 'RBI DBIE / CPI Combined General / 2012 base',
        'source': 'RBI DBIE / MoSPI (India)', 'frequency': 'Monthly', 'unit': 'Index 2012=100',
        'url': 'https://data.rbi.org.in/#/dbie/dataquery_enhanced',
        'description': 'Indian consumer price index for combined rural and urban '
                       'households, general index. CPI levels, not YoY inflation rates. '
                       'Separate from WPI and the OECD Indian CPI used by the estimate.',
        'unavailable': 'No verified RBI DBIE export adapter configured for this exact CPI series and base.',
    },
    'INRBIWPI': {
        'name': 'India WPI - RBI DBIE', 'provider': None,
        'series': 'RBI DBIE / WPI All Commodities / 2011-12 base',
        'source': 'RBI DBIE / Office of Economic Adviser (India)',
        'frequency': 'Monthly', 'unit': 'Index 2011-12=100',
        'url': 'https://data.rbi.org.in/#/dbie/dataquery_enhanced',
        'description': 'Indian wholesale price index for all commodities. Measures '
                       'wholesale prices rather than household consumer prices. '
                       'Not spliced with CPI or used as a silent CAPE deflator substitute.',
        'unavailable': 'No verified RBI DBIE export adapter configured for this exact WPI series and base.',
    },
    'NIFTYPS': {
        'name': 'NIFTY 50 Price/Sales', 'provider': None,
        'series': 'NIFTY 50 / aggregate price-to-sales (unverified)',
        'source': 'BSE / Trendlyne / Screener (requested)',
        'frequency': 'Unverified', 'unit': 'Ratio',
        'url': 'https://www.bseindia.com/',
        'description': 'Requested aggregate Indian NIFTY price/sales history. '
                       'Company-level screener ratios and BSE/Sensex index ratios '
                       'are not interchangeable with NIFTY 50 and are not substituted.',
        'unavailable': 'No verified free NIFTY 50 aggregate price/sales time series found at the listed portals.',
    },
    'INCPI': {
        'name': 'India CPI - OECD Historical', 'provider': 'Stored India CPI',
        'series': INDIA_CPI_SERIES, 'source': 'OECD India CPI via FRED',
        'frequency': 'Monthly', 'unit': INDIA_CPI_UNIT,
        'url': 'https://fred.stlouisfed.org/series/INDCPIALLMINMEI',
        'description': 'Indian all-items CPI from OECD via FRED, 2015=100. '
                       'The configured deflator for the NIFTY CAPE estimate, not RBI '
                       'DBIE or US CPI. This discontinued history ends in March 2025.',
        'unavailable': 'Requires the existing Indian INCPI history; it is not replaced by US inflation.',
    },
}

NIFTY_REPORT_GROUPS = (
    ('CAPE and NIFTY Valuation', ('INIIMCAPE', 'NIFTYCAPE', 'NIFTYPE', 'NIFTYPB', 'NIFTYPS')),
    ('Indian Earnings and Inflation', ('NIFTYEPS', 'NIFTYDY', 'NIFTYEY', 'INRBICPI', 'INRBIWPI', 'INCPI')),
)


def nifty_monthly_valuation(index_frame):
    """Select matched NIFTY month-end price/P/E rows with sufficient daily coverage."""
    if index_frame is None or index_frame.empty:
        return pd.DataFrame(columns=['Close', 'PE'], index=pd.PeriodIndex([], freq='M'))
    if not {'Date', 'Symbol', 'Close', 'PE'}.issubset(index_frame.columns):
        raise ValueError('NIFTY input requires Date, Symbol, Close and PE columns')
    if not index_frame['Symbol'].eq('NIFTY').all():
        raise ValueError('Only Indian NIFTY index observations may be used for NIFTY CAPE')
    value_columns = ['Close', 'PE'] + [column for column in ['PB', 'DY'] if column in index_frame]
    frame = index_frame[['Date', *value_columns]].copy()
    frame['Date'] = pd.to_datetime(frame['Date'], errors='coerce')
    if frame['Date'].dt.tz is not None:
        frame['Date'] = frame['Date'].dt.tz_localize(None)
    frame['Date'] = frame['Date'].dt.normalize()
    frame = frame.dropna(subset=['Date']).sort_values('Date').drop_duplicates('Date', keep='last')
    for column in value_columns:
        frame[column] = pd.to_numeric(frame[column], errors='coerce')
    frame['Month'] = frame['Date'].dt.to_period('M')
    counts = frame[frame['Date'].dt.dayofweek < 5].groupby('Month').size()
    monthly = frame.groupby('Month').tail(1).set_index('Month')[value_columns]
    starts = monthly.index.to_timestamp().to_numpy().astype('datetime64[D]')
    ends = (monthly.index + 1).to_timestamp().to_numpy().astype('datetime64[D]')
    coverage = counts.reindex(monthly.index, fill_value=0) >= np.busday_count(starts, ends) * 0.8
    closed = monthly.index < pd.Timestamp(datetime.date.today()).to_period('M')
    for column in ['Close', 'PE', 'PB']:
        if column in monthly:
            monthly[column] = monthly[column].where(np.isfinite(monthly[column]) & (monthly[column] > 0))
    if 'DY' in monthly:
        monthly['DY'] = monthly['DY'].where(np.isfinite(monthly['DY']) & (monthly['DY'] >= 0))
    result = monthly[coverage & closed].copy()
    result.attrs['symbol'] = 'NIFTY'
    return result


def calculate_nifty_metrics(monthly):
    """Keep published Indian valuations separate from implied earnings calculations."""
    if monthly.empty:
        return {}
    if monthly.attrs.get('symbol') != 'NIFTY':
        raise ValueError('Only Indian NIFTY inputs are allowed')
    values = {'NIFTYPE': monthly['PE'], 'NIFTYEPS': monthly['Close'] / monthly['PE'],
              'NIFTYEY': 100.0 / monthly['PE']}
    for symbol, column in [('NIFTYPB', 'PB'), ('NIFTYDY', 'DY')]:
        if column in monthly:
            values[symbol] = monthly[column]
    output = {}
    for symbol, series in values.items():
        series = series[np.isfinite(series)]
        output[symbol] = pd.DataFrame({
            'Date': series.index.to_timestamp(how='end').normalize(), 'Value': series.to_numpy(),
        })
    return output


def validate_india_cpi(india_cpi):
    """Reject foreign or incompatible inflation data before metadata or storage changes."""
    required = {'Date', 'Value', 'Symbol', 'Series', 'Unit', 'Frequency'}
    if not required.issubset(india_cpi.columns):
        raise ValueError('Indian CPI provenance metadata is required')
    for column, expected in [('Symbol', INDIA_CPI_SYMBOL), ('Series', INDIA_CPI_SERIES),
                              ('Unit', INDIA_CPI_UNIT), ('Frequency', 'Monthly')]:
        if not india_cpi[column].eq(expected).all():
            raise ValueError(f'Indian CPI {column} must be {expected}; no foreign CPI fallback')


def calculate_nifty_cape(monthly, india_cpi):
    """Use 120 consecutive Indian CPI-adjusted PE-implied earnings observations."""
    if monthly.empty or india_cpi is None or india_cpi.empty:
        return pd.DataFrame(columns=['Date', 'Value'])
    if monthly.attrs.get('symbol') != 'NIFTY':
        raise ValueError('NIFTY CAPE requires verified Indian NIFTY monthly inputs')
    validate_india_cpi(india_cpi)
    cpi = india_cpi[['Date', 'Value']].copy()
    cpi['Date'] = pd.to_datetime(cpi['Date'], errors='coerce')
    if cpi['Date'].dt.tz is not None:
        cpi['Date'] = cpi['Date'].dt.tz_localize(None)
    cpi['Value'] = pd.to_numeric(cpi['Value'], errors='coerce')
    cpi = cpi.dropna().sort_values('Date')
    cpi['Month'] = cpi['Date'].dt.to_period('M')
    if cpi['Month'].duplicated().any():
        raise ValueError('Indian CPI must have exactly one observation per month')
    cpi = cpi.set_index('Month')['Value'].where(lambda values: np.isfinite(values) & (values > 0))
    history = monthly.join(cpi.rename('CPI'), how='left')
    history = history.reindex(pd.period_range(history.index.min(), history.index.max(), freq='M'))
    earnings = history['Close'] / history['PE']
    real_earnings = earnings / history['CPI']
    trailing_mean = real_earnings.rolling(CAPE_WINDOW_MONTHS, min_periods=CAPE_WINDOW_MONTHS).mean()
    cape = (history['Close'] / history['CPI']) / trailing_mean.where(trailing_mean > 0)
    cape = cape[np.isfinite(cape)]
    return pd.DataFrame({'Date': cape.index.to_timestamp(how='end').normalize(),
                         'Value': cape.to_numpy()})