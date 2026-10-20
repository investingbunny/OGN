"""Japan macro definitions and public-source parsers shared by downloads and reports."""

import io
import re
from urllib.parse import urljoin, urlparse

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup


JAPAN_SERIES = {
    'JPUSDJPY': {
        'name': 'USD/JPY Exchange Rate',
        'provider': 'Yahoo', 'series': 'USDJPY=X',
        'source': 'Yahoo Finance', 'frequency': 'Daily', 'unit': 'JPY per USD',
        'url': 'https://finance.yahoo.com/quote/USDJPY=X/',
        'description': 'Yen per US dollar. A falling rate means yen appreciation and can '
                       'accompany carry unwinds; it is not proof of an unwind. Daily '
                       'quotes, not a real-time streaming feed.',
    },
    'JP10Y': {
        'name': 'Japan 10-Year Government Bond Yield',
        'provider': 'FRED', 'series': 'IRLTLT01JPM156N',
        'source': 'FRED / OECD', 'frequency': 'Monthly', 'unit': 'Percent',
        'url': 'https://fred.stlouisfed.org/series/IRLTLT01JPM156N',
        'description': 'Japanese 10-year government bond yield. Higher yields narrow '
                       'the US-Japan yield differential. Monthly observations, not '
                       'real-time JGB quotes.',
    },
    'JPPOLRATE': {
        'name': 'BOJ Policy Interest Rate',
        'provider': 'BIS', 'series': 'WS_CBPOL/D.JP',
        'source': 'BIS / Bank of Japan', 'frequency': 'Daily', 'unit': 'Percent',
        'dimensions': {'FREQ': 'D', 'REF_AREA': 'JP'},
        'unit_code': '368', 'unit_mult': 0,
        'url': 'https://data.bis.org/topics/CBPOL',
        'description': 'BOJ policy-rate history published daily by BIS; decisions occur '
                       'at policy meetings. Measures yen funding policy, not the '
                       'discount rate. Historical operating regimes and gaps differ.',
    },
    'JPJPYIV': {
        'name': 'USD/JPY One-Month Implied Volatility',
        'provider': None, 'series': 'USD/JPY 1M ATM implied volatility',
        'source': 'Licensed FX options data', 'frequency': 'Daily',
        'unit': 'Percent annualized',
        'url': 'https://www.cmegroup.com/markets/cvol.html',
        'description': 'Annualized one-month at-the-money USD/JPY implied volatility. '
                       'The forward-looking risk denominator for JPCARRY; realized '
                       'volatility is a different measure and is not substituted.',
        'unavailable': 'No verified public historical feed configured for 1M ATM implied volatility.',
    },
    'JPCARRY': {
        'name': 'Yen Carry-to-Risk Ratio',
        'provider': 'Derived', 'series': '(FEDTARU-JPPOLRATE)/JPJPYIV',
        'source': 'Derived', 'frequency': 'Daily', 'unit': 'Ratio',
        'url': 'https://en.macromicro.me/collections/8425/jpy/151155/carrytorisk-ratio-vs-yen-positioning-cot-index',
        'description': 'US Fed target upper limit minus BOJ policy rate, divided by '
                       '1M ATM implied yen volatility, all in annualized percent. '
                       'Same-date inputs only; not a reproduction of MacroMicro methodology.',
        'unavailable': 'Requires FEDTARU, JPPOLRATE and JPJPYIV; no realized-volatility proxy.',
    },
    'JPCOTSHORT': {
        'name': 'CFTC JPY Net Speculative Shorts',
        'provider': 'CFTC', 'series': '6dca-aqww / 097741',
        'source': 'CFTC Legacy Futures Only', 'frequency': 'Weekly', 'unit': 'Contracts',
        'url': 'https://publicreporting.cftc.gov/resource/6dca-aqww.json',
        'description': 'CME yen noncommercial shorts minus longs. Positive means net '
                       'short yen; negative means net long. Tuesday positions, normally '
                       'published Friday. Not total carry exposure or a normalized COT index.',
    },
    'JPCOTINDEX': {
        'name': 'MacroMicro JPY Positioning COT Index',
        'provider': None, 'series': 'MacroMicro / Yen positioning COT index',
        'source': 'MacroMicro / CFTC', 'frequency': 'Weekly', 'unit': 'Index',
        'url': 'https://en.macromicro.me/collections/8425/jpy/151155/carrytorisk-ratio-vs-yen-positioning-cot-index',
        'description': 'The normalized positioning index in the linked MacroMicro '
                       'chart. Raw CFTC contract counts are a separate series; the '
                       'index window, trader category and methodology are not reproduced.',
        'unavailable': 'No verified public feed or calculation methodology configured for this specific index.',
    },
    'JPTANKAN': {
        'name': 'Tankan Large Manufacturers Index',
        'provider': None, 'series': 'Large manufacturers / business conditions / actual DI',
        'source': 'Bank of Japan', 'frequency': 'Quarterly', 'unit': 'DI points',
        'url': 'https://www.boj.or.jp/en/statistics/tk/long/index.htm',
        'description': 'Large manufacturers reporting favorable business conditions '
                       'minus those reporting unfavorable conditions. Actual Tankan DI, '
                       'not its outlook or a broader business-confidence proxy.',
        'unavailable': 'No verified public time-series download configured; BOJ access was unavailable.',
    },
    'JPLEADING': {
        'name': 'Japan Composite Leading Index',
        'provider': 'ESRI', 'series': 'ESRI Composite Index / Leading',
        'source': 'Japan Cabinet Office / ESRI', 'frequency': 'Monthly',
        'unit': 'Index 2020=100', 'full_refresh': True,
        'url': 'https://www.esri.cao.go.jp/en/stat/di/di-e.html',
        'description': 'Cabinet Office composite leading index, combining indicators '
                       'that tend to precede economic turning points. Not the OECD '
                       'amplitude-adjusted composite leading indicator.',
    },
    'JPPMI': {
        'name': 'Japan Composite PMI',
        'provider': None, 'series': 'Japan Composite Output PMI',
        'source': 'S&P Global / au Jibun Bank', 'frequency': 'Monthly', 'unit': 'Index',
        'url': 'https://www.pmi.spglobal.com/Public/Release/PressReleases',
        'description': 'Composite purchasing managers output index covering Japanese '
                       'manufacturing and services. Above 50 signals expansion versus '
                       'the previous month; below 50 signals contraction.',
        'unavailable': 'Historical PMI data requires provider access; no verified public feed configured.',
    },
    'JPTOKYOCORE': {
        'name': 'Tokyo Core CPI',
        'provider': 'Dashboard', 'series': '0703010601010030010 / 13100',
        'indicator': '0703010601010030010', 'region': '13100', 'statistic': '00200573',
        'source': 'Statistics Bureau / Statistics Dashboard',
        'frequency': 'Monthly', 'unit': 'Percent YoY', 'full_refresh': True,
        'url': 'https://www.stat.go.jp/english/data/cpi/1581-z.html',
        'description': 'Tokyo ku-area consumer inflation excluding fresh food, including '
                       'energy. Published YoY changes, 2025-base series; usually precedes '
                       'national CPI. Dashboard updates may lag the preliminary release.',
    },
    'JPCORECPI': {
        'name': 'National Core CPI',
        'provider': 'Dashboard', 'series': '0703010601010030010 / 00000',
        'indicator': '0703010601010030010', 'region': '00000', 'statistic': '00200573',
        'source': 'Statistics Bureau / Statistics Dashboard',
        'frequency': 'Monthly', 'unit': 'Percent YoY', 'full_refresh': True,
        'url': 'https://www.stat.go.jp/english/data/cpi/1581-z.html',
        'description': 'National consumer inflation excluding fresh food, including '
                       'energy: published YoY, 2025-base series. A key BOJ gauge; '
                       'the 2% price-stability target is defined using all-items CPI.',
    },
    'JPWAGES': {
        'name': 'Total Cash Earnings Growth',
        'provider': 'Dashboard', 'series': '0302020000000030000 / 00000',
        'indicator': '0302020000000030000', 'region': '00000', 'statistic': '00450071',
        'source': 'MHLW / Statistics Dashboard',
        'frequency': 'Monthly', 'unit': 'Percent YoY',
        'url': 'https://dashboard.e-stat.go.jp/en/static/api',
        'description': 'Nominal total cash earnings growth per regular employee, '
                       'including bonuses and overtime. Wage persistence informs '
                       'BOJ normalization. Not real wages; latest releases may be preliminary.',
    },
    'JPCURRENT': {
        'name': 'Japan Current Account Balance',
        'provider': 'MOF', 'series': '6s-1-4 / Current account (a+b+c)',
        'source': 'Japan Ministry of Finance / Bank of Japan',
        'frequency': 'Monthly', 'unit': 'Billions of JPY', 'full_refresh': True,
        'url': 'https://www.mof.go.jp/english/policy/international_policy/reference/balance_of_payments/index.htm',
        'download_url': 'https://www.mof.go.jp/policy/international_policy/reference/'
                        'balance_of_payments/bp_trend/bpnet/sbp/s-1/6s-1-4.csv',
        'description': 'Net trade in goods and services plus primary and secondary '
                       'income, not seasonally adjusted. Source units of 100 million '
                       'yen are converted to billions. Surplus is not proof of repatriation.',
    },
    'JPXBYEN': {
        'name': 'Cross-Border Yen Loans and Deposits',
        'provider': 'BIS', 'series': 'WS_LBS_D_PUB/Q.S.C.G.JPY.A.5J.A.5A.A.5J.N',
        'source': 'BIS Locational Banking Statistics',
        'frequency': 'Quarterly', 'unit': 'Millions of USD', 'overlap_days': 1825,
        'dimensions': {
            'FREQ': 'Q', 'L_MEASURE': 'S', 'L_POSITION': 'C', 'L_INSTR': 'G',
            'L_DENOM': 'JPY', 'L_CURR_TYPE': 'A', 'L_PARENT_CTY': '5J',
            'L_REP_BANK_TYPE': 'A', 'L_REP_CTY': '5A', 'L_CP_SECTOR': 'A',
            'L_CP_COUNTRY': '5J', 'L_POS_TYPE': 'N',
        },
        'unit_code': 'USD', 'unit_mult': 6,
        'url': 'https://data.bis.org/topics/LBS',
        'description': 'Outstanding cross-border yen loans and deposits: all reporting '
                       'banks, all counterparties. USD equivalents, not yen amounts. '
                       'Includes non-carry business; not a direct carry-trade size estimate.',
    },
    'JPFOREIGN': {
        'name': 'Japanese Banks Foreign Claims',
        'provider': 'BIS', 'series': 'WS_CBS_PUB/Q.S.JP.4R.F.C.A.A.TO1.A.5J',
        'source': 'BIS Consolidated Banking Statistics',
        'frequency': 'Quarterly', 'unit': 'Millions of USD', 'overlap_days': 1825,
        'dimensions': {
            'FREQ': 'Q', 'L_MEASURE': 'S', 'L_REP_CTY': 'JP', 'CBS_BANK_TYPE': '4R',
            'CBS_BASIS': 'F', 'L_POSITION': 'C', 'L_INSTR': 'A', 'REM_MATURITY': 'A',
            'CURR_TYPE_BOOK': 'TO1', 'L_CP_SECTOR': 'A', 'L_CP_COUNTRY': '5J',
        },
        'unit_code': 'USD', 'unit_mult': 6,
        'url': 'https://data.bis.org/topics/CBS',
        'description': 'Consolidated foreign claims of Japanese banks, by bank '
                       'nationality, on an immediate-counterparty basis. Includes '
                       'loans and other claims; not exclusively yen-funded lending.',
    },
}

JAPAN_REPORT_GROUPS = (
    ('Funding and Carry Trade',
    ('JPUSDJPY', 'JP10Y', 'JPPOLRATE', 'JPJPYIV', 'JPCARRY')),
    ('Growth, Inflation and Wages',
     ('JPTANKAN', 'JPLEADING', 'JPPMI', 'JPTOKYOCORE', 'JPCORECPI', 'JPWAGES')),
    ('Positioning and Capital Flows',
    ('JPCOTSHORT', 'JPCOTINDEX', 'JPCURRENT', 'JPXBYEN', 'JPFOREIGN')),
)

CFTC_PAGE_SIZE = 5000
BIS_API = 'https://stats.bis.org/api/v1/data'


def parse_bis_csv(content, definition):
    """Validate one exact SDMX series, including its currency and scaling."""
    frame = pd.read_csv(io.BytesIO(content), dtype=str)
    required = {'TIME_PERIOD', 'OBS_VALUE', 'UNIT_MEASURE', 'UNIT_MULT'}
    required.update(definition['dimensions'])
    if not required.issubset(frame.columns):
        raise ValueError('BIS response is missing required SDMX columns')
    if frame.empty:
        return pd.DataFrame(columns=['Date', 'Value'])
    for column, expected in definition['dimensions'].items():
        if not frame[column].eq(expected).all():
            raise ValueError(f'Unexpected BIS dimension: {column}')
    if not frame['UNIT_MEASURE'].eq(definition['unit_code']).all():
        raise ValueError('Unexpected BIS measurement unit')
    if not pd.to_numeric(frame['UNIT_MULT']).eq(definition['unit_mult']).all():
        raise ValueError('Unexpected BIS unit multiplier')
    if frame['TIME_PERIOD'].duplicated().any():
        raise ValueError('BIS response contains multiple observations per period')
    if definition['frequency'] == 'Quarterly':
        dates = pd.PeriodIndex(frame['TIME_PERIOD'], freq='Q').to_timestamp(how='end').normalize()
    else:
        dates = pd.to_datetime(frame['TIME_PERIOD'], errors='raise')
    return pd.DataFrame({
        'Date': np.asarray(dates),
        'Value': pd.to_numeric(frame['OBS_VALUE'], errors='coerce').to_numpy(),
    })


def download_bis_series(definition, start_date):
    """Fetch a selected BIS series; the caller owns retries and normalization."""
    response = requests.get(
        f"{BIS_API}/{definition['series']}",
        params={'startPeriod': start_date.isoformat(), 'format': 'csv'}, timeout=45)
    response.raise_for_status()
    if response.status_code == 204:
        return pd.DataFrame(columns=['Date', 'Value'])
    return parse_bis_csv(response.content, definition)


def download_cftc_jpy(start_date):
    """Fetch legacy futures-only noncommercial shorts minus longs, in contracts."""
    columns = ['report_date_as_yyyy_mm_dd', 'cftc_contract_market_code',
               'noncomm_positions_long_all', 'noncomm_positions_short_all']
    records = []
    offset = 0
    while True:
        response = requests.get(
            JAPAN_SERIES['JPCOTSHORT']['url'],
            params={
                '$select': ','.join(columns),
                '$where': "cftc_contract_market_code='097741' AND "
                          f"report_date_as_yyyy_mm_dd >= '{start_date.isoformat()}T00:00:00'",
                '$order': 'report_date_as_yyyy_mm_dd ASC',
                '$limit': CFTC_PAGE_SIZE, '$offset': offset,
            }, timeout=45)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or any(
                not isinstance(row, dict) or not set(columns).issubset(row)
                for row in payload):
            raise ValueError('Unexpected CFTC response schema')
        if any(row['cftc_contract_market_code'] != '097741' for row in payload):
            raise ValueError('CFTC response contains a different contract')
        records.extend(payload)
        if len(payload) < CFTC_PAGE_SIZE:
            break
        offset += CFTC_PAGE_SIZE
    if not records:
        return pd.DataFrame(columns=['Date', 'Value'])
    frame = pd.DataFrame(records)
    longs = pd.to_numeric(frame['noncomm_positions_long_all'], errors='raise')
    shorts = pd.to_numeric(frame['noncomm_positions_short_all'], errors='raise')
    if ((longs < 0) | (shorts < 0)).any():
        raise ValueError('CFTC gross positions cannot be negative')
    return pd.DataFrame({'Date': frame['report_date_as_yyyy_mm_dd'],
                         'Value': shorts - longs})


def calculate_carry_to_risk(us_rate, japan_rate, implied_volatility):
    """Divide the policy spread by positive implied vol on common dates only."""
    combined = None
    for name, frame in [('USRate', us_rate), ('JapanRate', japan_rate),
                        ('ImpliedVol', implied_volatility)]:
        if frame is None or frame.empty:
            return pd.DataFrame(columns=['Date', 'Value'])
        values = frame[['Date', 'Value']].copy()
        values['Date'] = pd.to_datetime(values['Date'], utc=True).dt.tz_convert(None).dt.normalize()
        values['Value'] = pd.to_numeric(values['Value'], errors='coerce')
        values = values.dropna().drop_duplicates('Date', keep='last')
        values = values.rename(columns={'Value': name})
        combined = values if combined is None else combined.merge(
            values, on='Date', how='inner', validate='one_to_one')
    valid = np.isfinite(combined[['USRate', 'JapanRate', 'ImpliedVol']]).all(axis=1)
    combined = combined[valid & (combined['ImpliedVol'] > 0)].copy()
    combined['Value'] = (combined['USRate'] - combined['JapanRate']) / combined['ImpliedVol']
    return combined[['Date', 'Value']].sort_values('Date').reset_index(drop=True)


def parse_esri_leading(content):
    """Select the official CI leading column, not the DI or reference variants."""
    frame = pd.read_excel(io.BytesIO(content), sheet_name=0, header=None, engine='openpyxl')
    if len(frame) < 7:
        raise ValueError('Incomplete ESRI historical workbook')
    headings = frame.iloc[3].astype(str).str.strip()
    columns = [column for column in frame.columns
               if str(frame.iloc[1, column]).strip() == 'Composite Indexes'
               and headings[column] == 'Leading Index']
    year_columns = headings[headings == 'Calendar year'].index.tolist()
    month_columns = headings[headings == 'Month'].index.tolist()
    if len(columns) != 1 or len(year_columns) != 1 or len(month_columns) != 1:
        raise ValueError('Unexpected ESRI composite-leading workbook layout')
    value_column = columns[0]
    if str(frame.iloc[5, value_column]).strip() != '2020=100':
        raise ValueError('ESRI index base changed; update the definition before merging')
    data = frame.iloc[6:]
    years = pd.to_numeric(data[year_columns[0]], errors='coerce')
    months = pd.to_numeric(data[month_columns[0]], errors='coerce')
    valid = years.notna() & months.between(1, 12)
    dates = pd.to_datetime({'year': years[valid], 'month': months[valid], 'day': 1})
    values = pd.to_numeric(data.loc[valid, value_column], errors='coerce')
    return pd.DataFrame({'Date': dates, 'Value': values}).dropna().reset_index(drop=True)


def download_esri_leading():
    """Discover the current dated historical workbook from the official release page."""
    page_url = JAPAN_SERIES['JPLEADING']['url']
    response = requests.get(page_url, timeout=45)
    response.raise_for_status()
    page = BeautifulSoup(response.content, 'html.parser')
    links = {urljoin(page_url, anchor['href']) for anchor in page.find_all('a', href=True)
             if re.search(r'(?:^|/)\d{4}ci\.xlsx$', anchor['href'])}
    links = {link for link in links if urlparse(link).hostname == 'www.esri.cao.go.jp'}
    if len(links) != 1:
        raise ValueError('Could not uniquely identify the ESRI historical workbook')
    response = requests.get(links.pop(), timeout=45)
    response.raise_for_status()
    return parse_esri_leading(response.content)


def parse_mof_current_account(content):
    """Read MOF monthly current account and convert 100 million yen to billions."""
    frame = pd.read_csv(io.BytesIO(content), encoding='cp932', header=None, dtype=str)
    if frame.shape[1] < 5:
        raise ValueError('Incomplete MOF current-account CSV')
    text = frame[0].fillna('').str.normalize('NFKC').str.replace(r'\s+', ' ', regex=True)
    if not text.str.contains('100 million Yen', case=False, regex=False).any():
        raise ValueError('Unexpected MOF current-account units')
    headings = frame.index[frame[4].fillna('').str.strip().eq('Current account (a+b+c)')]
    if len(headings) != 1:
        raise ValueError('Missing MOF current-account column')
    data = frame.loc[headings[0] + 1:].copy()
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    month_text = data[3].fillna('').str.strip().str.extract(
        r'^(' + '|'.join(month_names) + r')(?:\s*\(P\))?$', expand=False)
    months = month_text.map({name: position + 1 for position, name in enumerate(month_names)})
    year_text = data[2].fillna('').str.strip()
    years = pd.to_numeric(year_text, errors='coerce')
    if (months.notna() & year_text.ne('') & years.isna()).any():
        raise ValueError('Unexpected MOF calendar-year label')
    years = years.ffill()
    valid = months.notna() & years.notna()
    dates = pd.to_datetime({'year': years[valid], 'month': months[valid], 'day': 1})
    values = pd.to_numeric(data.loc[valid, 4].str.replace(',', '', regex=False), errors='coerce')
    return pd.DataFrame({'Date': dates, 'Value': values / 10.0}).dropna().reset_index(drop=True)


def download_mof_current_account():
    """Download the complete official monthly history, including revised values."""
    response = requests.get(JAPAN_SERIES['JPCURRENT']['download_url'], timeout=45)
    response.raise_for_status()
    return parse_mof_current_account(response.content)


def parse_dashboard_json(payload, definition):
    """Validate the exact monthly, unadjusted series and complete observation count."""
    if not isinstance(payload, dict) or not isinstance(payload.get('GET_STATS'), dict):
        raise ValueError('Unexpected Statistics Dashboard response')
    result = payload['GET_STATS']
    if result.get('RESULT', {}).get('status') != '0':
        raise ValueError(f"Statistics Dashboard error: {result.get('RESULT')}")
    data = result.get('STATISTICAL_DATA', {})
    total = int(data.get('RESULT_INF', {}).get('TOTAL_NUMBER', -1))
    rows = data.get('DATA_INF', {}).get('DATA_OBJ', [])
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list) or total != len(rows):
        raise ValueError('Incomplete Statistics Dashboard observations')
    if not rows:
        return pd.DataFrame(columns=['Date', 'Value'])
    expected = {'@indicator': definition['indicator'], '@regionCode': definition['region'],
                '@stat': definition['statistic'], '@unit': '001', '@cycle': '1', '@isSeasonal': '1'}
    values = []
    for row in rows:
        value = row.get('VALUE') if isinstance(row, dict) else None
        if not isinstance(value, dict) or not {'@time', '$'}.issubset(value):
            raise ValueError('Malformed Statistics Dashboard observation')
        for key, required in expected.items():
            if value.get(key) != required:
                raise ValueError(f'Unexpected Statistics Dashboard dimension: {key}')
        if not re.fullmatch(r'\d{4}(?:0[1-9]|1[0-2])00', value['@time']):
            raise ValueError('Unexpected Statistics Dashboard monthly date')
        values.append((value['@time'], value['$']))
    frame = pd.DataFrame(values, columns=['Date', 'Value'])
    frame['Date'] = pd.to_datetime(frame['Date'], format='%Y%m00')
    frame['Value'] = pd.to_numeric(frame['Value'], errors='coerce')
    if frame['Date'].duplicated().any():
        raise ValueError('Statistics Dashboard returned duplicate monthly values')
    return frame


def download_dashboard_series(definition, start_date):
    """Fetch official monthly observations from the registration-free Dashboard API."""
    response = requests.get(
        'https://dashboard.e-stat.go.jp/api/1.0/Json/getData',
        params={'Lang': 'EN', 'IndicatorCode': definition['indicator'],
                'RegionCode': definition['region'], 'Cycle': '1',
                'IsSeasonalAdjustment': '1', 'TimeFrom': start_date.strftime('%Y%m00')},
        timeout=45)
    response.raise_for_status()
    return parse_dashboard_json(response.json(), definition)