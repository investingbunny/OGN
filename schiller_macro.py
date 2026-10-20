"""US-only Schiller valuation definitions and verified public-source parsers."""

import io
import re
from urllib.parse import urljoin, urlparse

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup


SHILLER_PAGE = 'https://shillerdata.com/'
SCHILLER_SERIES = {
    'SCHCAPE': {
        'name': 'US Shiller CAPE (PE10)', 'provider': 'Shiller',
        'series': 'ie_data / CAPE', 'source': 'Robert Shiller (US)',
        'frequency': 'Monthly', 'unit': 'Ratio', 'url': SHILLER_PAGE,
        'full_refresh': True,
        'description': 'US stock price divided by ten years of average US '
                       'inflation-adjusted earnings. Conventional CAPE, not total-return '
                       'CAPE. Historical equity composite before the modern S&P 500.',
    },
    'SCHREAL': {
        'name': 'US Inflation-Adjusted S&P Composite', 'provider': 'Shiller',
        'series': 'ie_data / Real Price', 'source': 'Robert Shiller (US)',
        'frequency': 'Monthly', 'unit': 'Real index points (latest US CPI base)',
        'url': SHILLER_PAGE, 'full_refresh': True,
        'description': 'Published real US price index using monthly prices and US CPI; '
                       'not a total-return index. Full history refresh avoids mixing '
                       'inflation bases. Latest source observations may be preliminary.',
    },
    'SCHEARN': {
        'name': 'US Shiller Trailing Earnings', 'provider': 'Shiller',
        'series': 'ie_data / E', 'source': 'Robert Shiller (US)',
        'frequency': 'Monthly', 'unit': 'Nominal USD per index share',
        'url': SHILLER_PAGE, 'full_refresh': True,
        'description': 'Nominal trailing annual earnings in the Shiller workbook. '
                       'Monthly figures interpolate four-quarter earnings (annual '
                       'data before 1926); not single-quarter S&P earnings.',
    },
    'SCHEPS': {
        'name': 'S&P 500 Quarterly Reported EPS', 'provider': None,
        'series': 'S&P DJI / quarterly as-reported EPS', 'source': 'S&P Dow Jones Indices',
        'frequency': 'Quarterly', 'unit': 'USD per index share',
        'url': 'https://www.spglobal.com/spdji/en/documents/additional-material/sp-500-eps-est.xlsx',
        'description': 'Single-quarter as-reported earnings per share for the S&P 500, '
                       'not operating earnings, trailing annual earnings or forecasts. '
                       'Shiller monthly earnings are displayed separately.',
        'unavailable': 'The official earnings workbook returned HTTP 403; no verified quarterly adapter configured.',
    },
    'SCHPE': {
        'name': 'S&P 500 Trailing P/E', 'provider': 'Multpl',
        'series': 'Multpl / s-p-500-pe-ratio', 'source': 'Multpl (US)',
        'frequency': 'Monthly', 'unit': 'Ratio',
        'url': 'https://www.multpl.com/s-p-500-pe-ratio/table/by-month',
        'heading': 'S&P 500 PE Ratio by Month',
        'description': 'US price divided by trailing twelve-month earnings, not CAPE. '
                       'Monthly historical observations exclude the extra live quote. '
                       'Recent source observations may be estimates.',
    },
    'SCHEY': {
        'name': 'S&P 500 Earnings Yield', 'provider': 'Multpl',
        'series': 'Multpl / s-p-500-earnings-yield', 'source': 'Multpl (US)',
        'frequency': 'Monthly', 'unit': 'Percent',
        'url': 'https://www.multpl.com/s-p-500-earnings-yield/table/by-month',
        'heading': 'S&P 500 Earnings Yield by Month',
        'description': 'US trailing annual earnings divided by price, in percent. '
                       'Approximately 100 divided by trailing P/E; not inverse CAPE. '
                       'Recent source observations may be estimates.',
    },
    'SCHPS': {
        'name': 'S&P 500 Price/Sales', 'provider': 'Multpl',
        'series': 'Multpl / s-p-500-price-to-sales', 'source': 'Multpl / S&P (US)',
        'frequency': 'Quarterly', 'unit': 'Ratio',
        'url': 'https://www.multpl.com/s-p-500-price-to-sales/table/by-quarter',
        'heading': 'S&P 500 Price to Sales Ratio by Quarter',
        'description': 'US index price relative to trailing twelve-month sales per share. '
                       'Quarter-end observations only; live quotes are excluded. '
                       'Recent source estimates can later be revised.',
    },
    'SCHPB': {
        'name': 'S&P 500 Price/Book', 'provider': 'Multpl',
        'series': 'Multpl / s-p-500-price-to-book', 'source': 'Multpl / S&P (US)',
        'frequency': 'Quarterly', 'unit': 'Ratio',
        'url': 'https://www.multpl.com/s-p-500-price-to-book/table/by-quarter',
        'heading': 'S&P 500 Price to Book Value by Quarter',
        'description': 'US index price divided by book value per index share. Uses '
                       'quarter-end table observations, not the extra live quote. '
                       'Recent source observations may be estimates.',
    },
    'SCHBV': {
        'name': 'S&P 500 Book Value Per Share', 'provider': 'Multpl',
        'series': 'Multpl / s-p-500-book-value', 'source': 'Multpl / S&P (US)',
        'frequency': 'Quarterly', 'unit': 'USD per index share',
        'url': 'https://www.multpl.com/s-p-500-book-value/table/by-quarter',
        'heading': 'S&P 500 Book Value Per Share by Quarter',
        'description': 'US accounting book value per index share, in nominal dollars. '
                       'The book-value level is distinct from the price/book multiple '
                       'and is not an estimate of liquidation value.',
    },
}

SCHILLER_REPORT_GROUPS = (
    ('CAPE and Long-Run Valuation', ('SCHCAPE', 'SCHREAL', 'SCHPE', 'SCHEY')),
    ('Earnings, Sales and Book Value', ('SCHEARN', 'SCHEPS', 'SCHPS', 'SCHPB', 'SCHBV')),
)


def parse_multpl_table(content, definition):
    """Parse the requested historical table without relabelling live quotes."""
    page = BeautifulSoup(content, 'html.parser')
    heading = page.find('h1')
    table = page.find('table', id='datatable')
    if heading is None or heading.get_text(' ', strip=True) != definition['heading'] or table is None:
        raise ValueError('Unexpected Multpl page or missing historical table')
    if [cell.get_text(' ', strip=True) for cell in table.find_all('th')] != ['Date', 'Value']:
        raise ValueError('Unexpected Multpl table columns')
    rows = []
    for row in table.find_all('tr'):
        cells = row.find_all('td')
        if not cells:
            continue
        if len(cells) != 2:
            raise ValueError('Malformed Multpl table row')
        date = pd.to_datetime(cells[0].get_text(' ', strip=True), format='%b %d, %Y')
        if definition['frequency'] == 'Monthly' and date.day != 1:
            continue
        if definition['frequency'] == 'Quarterly' and not date.is_quarter_end:
            continue
        estimated = any('estimate' in str(marker.get('title', '')).lower()
                        for marker in cells[1].find_all('abbr'))
        for marker in cells[1].find_all('abbr'):
            marker.decompose()
        text = cells[1].get_text(' ', strip=True).replace(',', '').strip()
        if text in ('', '-', '--', 'N/A', 'NA'):
            continue
        percent = text.endswith('%')
        if percent != (definition['unit'] == 'Percent'):
            raise ValueError('Unexpected Multpl measurement unit')
        number = text[:-1].strip() if percent else text
        if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)', number):
            raise ValueError('Non-numeric Multpl observation')
        rows.append((date, float(number), estimated))
    result = pd.DataFrame(rows, columns=['Date', 'Value', 'Estimated'])
    if result.empty or result['Date'].duplicated().any() or not np.isfinite(result['Value']).all():
        raise ValueError('Multpl returned invalid history or duplicate historical dates')
    return result.sort_values('Date').reset_index(drop=True)


def download_multpl_series(definition):
    """Fetch the public table; the caller owns retries and incremental merging."""
    response = requests.get(definition['url'], timeout=45)
    response.raise_for_status()
    return parse_multpl_table(response.content, definition)


def parse_shiller_frame(raw):
    """Select conventional CAPE, published real price and nominal trailing earnings."""
    candidates = [position for position in range(min(30, len(raw)))
                  if {'Date', 'P', 'E', 'CAPE'}.issubset(
                      set(raw.iloc[position].dropna().astype(str).str.strip()))]
    if len(candidates) != 1 or candidates[0] == 0:
        raise ValueError('Could not identify the Shiller data header')
    header_row = candidates[0]
    headers = raw.iloc[header_row].fillna('').astype(str).str.strip()
    previous = raw.iloc[header_row - 1].fillna('').astype(str).str.strip()
    columns = {}
    for key in ['Date', 'E', 'CAPE']:
        positions = headers.index[headers == key].tolist()
        if len(positions) != 1:
            raise ValueError(f'Ambiguous Shiller column: {key}')
        columns[key] = positions[0]
    prices = headers.index[(headers == 'Price') & (previous == 'Real')].tolist()
    if len(prices) != 1:
        raise ValueError('Missing published real price; total-return price is not a substitute')
    data = raw.iloc[header_row + 1:]
    date_numbers = pd.to_numeric(data[columns['Date']], errors='coerce')
    valid = date_numbers.notna()
    date_numbers = date_numbers[valid]
    years = np.floor(date_numbers).astype(int)
    months = np.rint((date_numbers - years) * 100).astype(int)
    if not years.between(1800, 2200).all() or not months.between(1, 12).all():
        raise ValueError('Invalid Shiller YYYY.MM date')
    dates = pd.to_datetime({'year': years, 'month': months, 'day': 1})
    if dates.duplicated().any():
        raise ValueError('Duplicate Shiller monthly date')
    outputs = {}
    for symbol, column in [('SCHCAPE', columns['CAPE']), ('SCHREAL', prices[0]), ('SCHEARN', columns['E'])]:
        values = pd.to_numeric(data.loc[valid, column], errors='coerce')
        frame = pd.DataFrame({'Date': dates, 'Value': values})
        frame = frame[np.isfinite(frame['Value'])].sort_values('Date').reset_index(drop=True)
        if frame.empty:
            raise ValueError(f'No usable Shiller observations for {symbol}')
        outputs[symbol] = frame
    return outputs


def download_shiller_workbook():
    """Discover the current official workbook link rather than pinning a dated asset."""
    response = requests.get(SHILLER_PAGE, timeout=45)
    response.raise_for_status()
    page = BeautifulSoup(response.content, 'html.parser')
    links = {urljoin(SHILLER_PAGE, anchor['href']) for anchor in page.find_all('a', href=True)
             if urlparse(anchor['href']).path.lower().endswith('/ie_data.xls')}
    links = {link for link in links if urlparse(link).scheme == 'https'
             and urlparse(link).hostname in {'shillerdata.com', 'www.shillerdata.com', 'img1.wsimg.com'}}
    if len(links) != 1:
        raise ValueError('Could not uniquely identify the official Shiller workbook')
    response = requests.get(links.pop(), timeout=45)
    response.raise_for_status()
    if not response.content.startswith(bytes.fromhex('d0cf11e0a1b11ae1')):
        raise ValueError('Shiller response is not an XLS workbook')
    raw = pd.read_excel(io.BytesIO(response.content), sheet_name='Data', header=None, engine='xlrd')
    return parse_shiller_frame(raw)