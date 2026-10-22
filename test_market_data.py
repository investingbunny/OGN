"""Regression checks for NSE layout handling, merge robustness, data-store repairs and paths."""

import contextlib
import datetime
import importlib.util
import io
import json
import os
import re
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import DEFAULT, patch

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

import OGN

HERE = Path(__file__).resolve().parent
DAY = datetime.date


def load_script(name, module_name):
    spec = importlib.util.spec_from_file_location(module_name, HERE / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def string_modes():
    """pandas 2 object strings, plus pandas 3's `str` dtype where it can be switched on."""
    modes = [contextlib.nullcontext]
    try:
        pd.get_option('future.infer_string')
        modes.append(lambda: pd.option_context('future.infer_string', True))
    except Exception:
        pass
    return modes


def contracts(dates, expiry, close=101.5):
    return pd.DataFrame({'Date': dates, 'Symbol': 'NIFTY', 'Instrument': 'OPTIDX',
                         'Expiry': expiry, 'Strike Price': 22000.0, 'Option type': 'CE',
                         'Close': close})


def legacy_day(date):
    """One NIFTY future and option as the legacy F&O layout stores them."""
    return pd.DataFrame({'Date': date, 'Symbol': 'NIFTY', 'Instrument': ['FUTIDX', 'OPTIDX'],
                         'Expiry': DAY(2024, 3, 28), 'Strike Price': [0.0, 22000.0],
                         'Option type': ['XX', 'CE'], 'Close': [22100.0, 150.0]})


def udiff_day(date):
    """The same two contracts as the UDiFF layout stores them."""
    return pd.DataFrame({'Date': date, 'Symbol': 'NIFTY', 'Instrument': ['IDF', 'IDO'],
                         'Expiry': DAY(2024, 3, 28), 'Strike Price': [np.nan, 22000.0],
                         'Option type': [np.nan, 'CE'], 'Close': [22100.0, 150.0],
                         'UndrlygPric': 22050.0})


def market_activity_day(date):
    """Market Activity lines share Date and Symbol, as NSE's report does."""
    return pd.DataFrame({'Date': date, 'Symbol': 'MARKET',
                         'Line': ['Equity', 'Derivatives', 'Currency', 'Debt', 'Total'],
                         'Value': [1.0, 2.0, 3.0, 4.0, 10.0]})


def cm_day(date, close):
    """One stock trading in two series, with an integer column."""
    return pd.DataFrame({'Date': [date, date], 'Symbol': 'PFC', 'Series': ['EQ', 'N1'],
                         'Close': [close, close + 600.0], 'Volume': [100, 200]})


def legacy_fo(date):
    """Legacy F&O day with the empty trailing CSV column and integer open interest."""
    return legacy_day(date).assign(**{'Open Int': [1000, 2000], 'Unnamed: 15': np.nan})


def udiff_fo(date, first_id=1001):
    """UDiFF F&O day: adds columns (one integer) and lacks the legacy trailing column."""
    return udiff_day(date).assign(**{'Open Int': [3000, 4000], 'FinInstrmId': [first_id, first_id + 1]})


def dated_market_activity(date):
    """Market Activity day as earlier versions saved it: a column named after the date."""
    return pd.DataFrame({'Unnamed: 0': ['The Nifty witnessed an intraday movement', 'nan', 'nan'],
                         date.strftime('%d-%b-%Y'): ['nan', 'TOP 25 Securities Today :',
                                                     'Top Five Nifty 50 Gainers:'],
                         'Symbol': 'MARKET', 'Date': date})


def old_short_sales(date):
    """Short sales as earlier versions saved them: symbol in an unmapped column, UNKNOWN Symbol."""
    return pd.DataFrame({'Security Name': ['YES BANK LIMITED', 'KOTAK MAHINDRA BANK LTD'],
                         'Security Symbol': ['YESBANK', 'KOTAKBANK'], 'Date': date,
                         'Qty Short Sold': [153300, 56000], 'Symbol': 'UNKNOWN'})


WDM_ADDED = ['ST', 'Security', 'Issue', 'Issue Description', 'Coupon', 'Issue Date', 'Maturity Date',
             'Next IP Date', 'Coupon Freq', 'Rating', 'Listed']
WDM_MATURED = ['ST', 'Security', 'Issue', 'Issue Description', 'Coupon', 'Issue Date', 'Maturity Date',
               'Rating', 'Listed']


def old_wdm_day(date):
    """A WDM day as earlier versions saved it.

    Symbols carry dates, and each issue list was read with its title line as the
    header, so the real header is the first data row, the title names the 4th
    column, and the numeric Coupon column lost its header text.
    """
    def issue_list(title, header, row, symbol):
        cells = {f'Unnamed: {i}': [name, value, 'nan'] for i, (name, value) in enumerate(zip(header, row))}
        cells[title] = cells.pop('Unnamed: 3')
        cells['Unnamed: 4'] = [np.nan, float(row[4]), np.nan]
        return pd.DataFrame({**cells, 'Date': date, 'Symbol': symbol})

    trades = pd.DataFrame({'Date': [date], 'Sectype': ['GS'], 'Security': ['CG2031'],
                           'Traded Value (Rs.Cr.)': [128.24], 'Symbol': [f'Debt_trd{date:%d%m}_sett']})
    added = issue_list(f'Issues added on {date:%d %B %Y}', WDM_ADDED,
                       ['CP', 'ABML', '110923', 'ABML CP 11/09/23', '0', '13-Jun-2023', '11-Sep-2023',
                        'nan', 'nan', 'CRISIL A1+', 'Yes'], f'Debt_add{date:%Y%m%d}')
    matured = issue_list(f'Issues matured on {date:%d %B %Y}', WDM_MATURED,
                         ['PT', 'PFC23', '8.19%', 'POWER FIN 8.19% 2023', '8.19', '14-Jun-2013',
                          '14-Jun-2023', 'ICRA AAA', 'Yes'], f'Debt_mat{date:%Y%m%d}')
    frame = pd.concat([trades, added, matured], ignore_index=True)
    for col in frame.columns:
        if frame[col].dtype == object and col != 'Date':
            frame[col] = frame[col].astype(str)
    return frame


def wdm_zip(date):
    """A WDM Daily ZIP as NSE ships it, with 2011-style short title lines."""
    files = {
        f'trd{date:%d%m}_sett.csv': f'Trade date,Sectype,Security,Traded Value (Rs.Cr.)\n'
                                    f'{date:%d-%b-%Y},GS,CG2036,25.00\n',
        f'add{date:%Y%m%d}.csv': f',,,Issues added on {date:%d %B %Y}\n' + ','.join(WDM_ADDED) + '\n'
                                 'CP,ICFL,310827,ICFL CP 31/08/27,0,16-Oct-2026,31-Aug-2027,,,CARE A1+,Yes\n'
                                 'DB,IBHF29,9.80%,INDBULLS HSG FIN 9.80 % 2029,9.8,16-Oct-2026,16-Oct-2029,'
                                 '16-Oct-2027,Yearly,BRCK AA+,Yes\n',
        f'mat{date:%Y%m%d}.csv': f',,,Issues matured on {date:%d %B %Y},,,,,\n' + ','.join(WDM_MATURED) + '\n'
                                 'PT,PGC26,8.85%,PGC 8.85% 2026,8.85,19-Oct-2012,19-Oct-2026,CARE AAA,Yes\n',
        'Legend.doc': 'not a data file',
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return buffer.getvalue()


class MergeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_script('OGN v2.0-download.py', 'ogn_market_data_download')

    def downloader(self):
        return object.__new__(self.module.NSEMarketDataDownloader)

    def folders(self, tmp):
        raw, processed = Path(tmp) / 'Raw', Path(tmp) / 'Processed'
        raw.mkdir()
        processed.mkdir()
        return raw, processed

    def test_retry_file_with_text_dates_merges(self):
        for mode in string_modes():
            with self.subTest(mode=mode), mode(), tempfile.TemporaryDirectory() as tmp, \
                    contextlib.redirect_stdout(None):
                raw, processed = self.folders(tmp)
                stored = contracts([DAY(2024, 1, 1), DAY(2024, 1, 2)], DAY(2024, 1, 25))
                stored['Expiry'] = stored['Expiry'].astype(str)
                stored.to_parquet(processed / 'NIFTY.parquet', index=False)
                (raw / '.retry').mkdir()
                retry = contracts([DAY(2024, 1, 2), DAY(2024, 1, 3)], DAY(2024, 1, 25), close=99.0)
                retry.astype({'Date': str, 'Expiry': str}).to_parquet(
                    raw / '.retry' / 'NIFTY.parquet', index=False)
                self.downloader().merge_raw_to_processed(raw, 'fo', processed, 'Derivatives')
                result = pd.read_parquet(processed / 'NIFTY.parquet')
                self.assertFalse((raw / '.retry').exists())
                self.assertEqual(result['Date'].tolist(), [DAY(2024, 1, 1), DAY(2024, 1, 2), DAY(2024, 1, 3)])
                self.assertEqual(result['Close'].tolist(), [101.5, 99.0, 99.0])
                self.assertTrue(all(type(value) is DAY for value in result['Expiry']))

    def test_main_merge_keeps_expiry_dates_and_deduplicates_across_types(self):
        for mode in string_modes():
            with self.subTest(mode=mode), mode(), tempfile.TemporaryDirectory() as tmp, \
                    contextlib.redirect_stdout(None):
                raw, processed = self.folders(tmp)
                stored = contracts([DAY(2024, 1, 2), DAY(2024, 1, 3)], DAY(2024, 1, 25))
                stored['Expiry'] = stored['Expiry'].astype(str)
                stored.to_parquet(processed / 'NIFTY.parquet', index=False)
                older = contracts([DAY(2024, 1, 1)], DAY(2024, 1, 25))
                older.astype({'Expiry': str}).to_parquet(raw / 'fo_20240101.parquet', index=False)
                contracts([DAY(2024, 1, 3)], DAY(2024, 1, 25), close=105.0).to_parquet(
                    raw / 'fo_20240103.parquet', index=False)
                self.downloader().merge_raw_to_processed(raw, 'fo', processed, 'Derivatives')
                result = pd.read_parquet(processed / 'NIFTY.parquet')
                self.assertEqual(result['Date'].tolist(), [DAY(2024, 1, 1), DAY(2024, 1, 2), DAY(2024, 1, 3)])
                self.assertEqual(result['Close'].tolist(), [101.5, 101.5, 105.0])
                self.assertEqual(str(pq.read_schema(processed / 'NIFTY.parquet').field('Expiry').type), 'date32[day]')

    def test_late_day_keeps_every_cash_market_series(self):
        def day(date, close):
            return pd.DataFrame({'Date': [date, date], 'Symbol': 'PFC', 'Series': ['EQ', 'N1'],
                                 'Close': [close, 1000.0 + close]})
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(None):
            raw, processed = self.folders(tmp)
            day(DAY(2024, 1, 2), 400.0).to_parquet(raw / 'cm_20240102.parquet', index=False)
            day(DAY(2024, 1, 4), 410.0).to_parquet(raw / 'cm_20240104.parquet', index=False)
            self.downloader().merge_raw_to_processed(raw, 'cm', processed, 'Equity')
            day(DAY(2024, 1, 3), 405.0).to_parquet(raw / 'cm_20240103.parquet', index=False)
            self.downloader().merge_raw_to_processed(raw, 'cm', processed, 'Equity')
            result = pd.read_parquet(processed / 'PFC.parquet')
            equity = result[result['Series'].eq('EQ')].sort_values('Date')
            self.assertEqual(len(result), 6)
            self.assertEqual(equity['Close'].tolist(), [400.0, 405.0, 410.0])

    def test_keyless_reports_keep_rows_sharing_date_and_symbol(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(None):
            raw, processed = self.folders(tmp)
            for date in (DAY(2024, 1, 2), DAY(2024, 1, 4)):
                market_activity_day(date).to_parquet(raw / f'ma_{date:%Y%m%d}.parquet', index=False)
            self.downloader().merge_raw_to_processed(raw, 'ma', processed, 'Market Activity')
            market_activity_day(DAY(2024, 1, 3)).to_parquet(raw / 'ma_20240103.parquet', index=False)
            (raw / '.retry').mkdir()
            market_activity_day(DAY(2024, 1, 2)).to_parquet(raw / '.retry' / 'MARKET.parquet', index=False)
            self.downloader().merge_raw_to_processed(raw, 'ma', processed, 'Market Activity')
            result = pd.read_parquet(processed / 'MARKET.parquet')
        self.assertEqual(result.groupby('Date').size().tolist(), [5, 5, 5])
        self.assertEqual(self.module.NSEMarketDataDownloader._dedup_keys(result, 'ma'), result.columns.tolist())

    def test_fo_day_stored_in_both_layouts_keeps_the_udiff_copy(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(None):
            raw, processed = self.folders(tmp)
            stored = {DAY(2023, 12, 29): legacy_day, DAY(2024, 3, 14): legacy_day,
                      DAY(2024, 3, 15): legacy_day, DAY(2024, 7, 10): udiff_day}
            for date, layout in stored.items():
                layout(date).to_parquet(raw / f'fo_{date:%Y%m%d}.parquet', index=False)
            self.downloader().merge_raw_to_processed(raw, 'fo', processed, 'Derivatives')
            udiff_day(DAY(2024, 3, 15)).to_parquet(raw / 'fo_20240315 (1).parquet', index=False)
            self.downloader().merge_raw_to_processed(raw, 'fo', processed, 'Derivatives')
            result = pd.read_parquet(processed / 'NIFTY.parquet')
        instruments = result.groupby('Date')['Instrument'].apply(sorted).to_dict()
        self.assertEqual(instruments, {
            DAY(2023, 12, 29): ['FUTIDX', 'OPTIDX'], DAY(2024, 3, 14): ['FUTIDX', 'OPTIDX'],
            DAY(2024, 3, 15): ['IDF', 'IDO'], DAY(2024, 7, 10): ['IDF', 'IDO']})

    def test_both_layouts_of_a_day_in_one_merge_keep_the_udiff_copy(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(None):
            raw, processed = self.folders(tmp)
            legacy_day(DAY(2024, 3, 15)).to_parquet(raw / 'fo_20240315.parquet', index=False)
            udiff_day(DAY(2024, 3, 15)).to_parquet(raw / 'fo_20240315 (1).parquet', index=False)
            self.downloader().merge_raw_to_processed(raw, 'fo', processed, 'Derivatives')
            result = pd.read_parquet(processed / 'NIFTY.parquet')
        self.assertEqual(sorted(result['Instrument']), ['IDF', 'IDO'])

    def test_layout_rule_leaves_other_rows_alone(self):
        rules = self.module.NSEMarketDataDownloader
        for mode in string_modes():
            with self.subTest(mode=mode), mode():
                frame = pd.concat([legacy_day(DAY(2024, 3, 15)), udiff_day(DAY(2024, 3, 15)),
                                   legacy_day(DAY(2024, 3, 14)), udiff_day(DAY(2024, 7, 10)),
                                   pd.DataFrame({'Date': [DAY(2024, 3, 15)], 'Symbol': 'NIFTY',
                                                 'Instrument': ['OTHER']})])
                result = rules._drop_superseded_legacy_rows(frame)
                self.assertEqual(sorted(result.loc[result['Date'].eq(DAY(2024, 3, 15)), 'Instrument']),
                                 ['IDF', 'IDO', 'OTHER'])
                self.assertEqual(len(result), len(frame) - 2)
        cash = pd.DataFrame({'Date': [DAY(2024, 3, 15)] * 2, 'Symbol': 'PFC', 'Series': ['EQ', 'N1']})
        self.assertIs(rules._drop_superseded_legacy_rows(cash), cash)

    def test_days_already_downloaded_are_not_fetched_again(self):
        fetched = []

        def fetch(day):
            fetched.append(day)
            return day, None

        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(None):
            raw = Path(tmp)
            legacy_day(DAY(2024, 3, 15)).to_parquet(raw / 'fo_20240315.parquet', index=False)
            (raw / 'fo_20240314.nodata').touch()
            self.downloader()._concurrent_download(
                [DAY(2024, 3, 13), DAY(2024, 3, 14), DAY(2024, 3, 15), DAY(2024, 3, 16)],
                fetch, raw, 'fo', 'Derivatives')
        self.assertEqual(fetched, [DAY(2024, 3, 13)])

    def test_restore_date_columns_normalises_or_refuses(self):
        restore = self.module.NSEMarketDataDownloader._restore_date_columns
        frame = pd.DataFrame({'Date': pd.Series([DAY(2024, 1, 2), '2024-01-03', 'nan', None], dtype=object),
                              'Expiry': pd.to_datetime(['2024-01-25'] * 4)})
        result = restore(frame)
        self.assertEqual(result['Date'].tolist()[:2], [DAY(2024, 1, 2), DAY(2024, 1, 3)])
        self.assertTrue(result['Date'].iloc[2:].isna().all())
        self.assertTrue(all(type(value) is DAY for value in result['Expiry']))
        with self.assertRaisesRegex(ValueError, 'unparseable Date'):
            restore(pd.DataFrame({'Date': ['2024-01-02', 'not a date']}))

    def test_raw_files_store_expiry_as_date(self):
        frame = contracts([DAY(2024, 1, 2)], DAY(2024, 1, 25))
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(None):
            raw = Path(tmp)
            self.downloader()._concurrent_download(
                [DAY(2024, 1, 2)], lambda day: (day, frame.copy()), raw, 'fo', 'Derivatives')
            schema = pq.read_schema(raw / 'fo_20240102.parquet')
        self.assertEqual(str(schema.field('Expiry').type), 'date32[day]')
        self.assertEqual(str(schema.field('Date').type), 'date32[day]')

    def test_udiff_starts_with_2024(self):
        self.assertEqual(self.module.UDIFF_START_DATE, DAY(2024, 1, 1))


def plain_text(table):
    """The table with large_string columns read as string (pandas 3 writes large_string)."""
    return table.cast(pa.schema([pa.field(f.name, pa.string()) if pa.types.is_large_string(f.type) else f
                                 for f in table.schema], metadata=table.schema.metadata))


class FastAppendTests(unittest.TestCase):
    """Appending newer days with pyarrow must write exactly what the pandas merge writes."""

    @classmethod
    def setUpClass(cls):
        cls.module = load_script('OGN v2.0-download.py', 'ogn_market_data_fast_append')
        cls.rules = cls.module.NSEMarketDataDownloader

    def folders(self, tmp):
        raw, processed = Path(tmp) / 'Raw', Path(tmp) / 'Processed'
        raw.mkdir()
        processed.mkdir()
        return raw, processed

    def run_merges(self, prefix, batches, fast):
        """Merges each batch of raw days in turn and returns the processed tables."""
        outcomes = []
        append = self.rules._append_newer_rows

        def spy(file_path, new_data):
            outcomes.append(append(file_path, new_data) if fast else False)
            return outcomes[-1]

        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), \
                patch.object(self.rules, '_append_newer_rows', side_effect=spy):
            raw, processed = self.folders(tmp)
            for batch in batches:
                for name, frame in batch.items():
                    frame.to_parquet(raw / name, index=False)
                object.__new__(self.rules).merge_raw_to_processed(raw, prefix, processed, prefix)
            tables = {p.name: pq.read_table(p) for p in processed.glob('*.parquet')}
            frames = {p.name: pd.read_parquet(p) for p in processed.glob('*.parquet')}
            leftovers = [p.name for p in processed.iterdir() if not p.name.endswith('.parquet')]
        self.assertEqual(leftovers, [])
        return tables, frames, outcomes

    def assert_same_output(self, prefix, batches):
        for mode in string_modes():
            with self.subTest(mode=mode), mode():
                fast_tables, fast_frames, outcomes = self.run_merges(prefix, batches, fast=True)
                slow_tables, slow_frames, _ = self.run_merges(prefix, batches, fast=False)
                self.assertTrue(any(outcomes), 'the fast append was never used')
                self.assertEqual(sorted(fast_tables), sorted(slow_tables))
                for name in fast_tables:
                    fast, slow = plain_text(fast_tables[name]), plain_text(slow_tables[name])
                    self.assertEqual(fast.schema.remove_metadata(), slow.schema.remove_metadata(), name)
                    self.assertTrue(fast.equals(slow), name)
                    self.assertEqual(json.loads(fast.schema.metadata[b'pandas'])['columns'],
                                     json.loads(slow.schema.metadata[b'pandas'])['columns'], name)
                    pd.testing.assert_frame_equal(fast_frames[name], slow_frames[name])

    def test_derivatives_across_layout_change(self):
        # UDiFF days add columns (one of them integer) and lack the legacy trailing column;
        # the next day's integers then join the float column the first append created.
        self.assert_same_output('fo', [
            {'fo_20240102.parquet': legacy_fo(DAY(2024, 1, 2)), 'fo_20240103.parquet': legacy_fo(DAY(2024, 1, 3))},
            {'fo_20240710.parquet': udiff_fo(DAY(2024, 7, 10))},
            {'fo_20240711.parquet': udiff_fo(DAY(2024, 7, 11), 2001),
             'fo_20240712.parquet': udiff_fo(DAY(2024, 7, 12), 3001)}])

    def test_equity_and_keyless_reports(self):
        self.assert_same_output('cm', [{'cm_20240102.parquet': cm_day(DAY(2024, 1, 2), 400.0)},
                                       {'cm_20240103.parquet': cm_day(DAY(2024, 1, 3), 410.0),
                                        'cm_20240104.parquet': cm_day(DAY(2024, 1, 4), 420.0)}])
        self.assert_same_output('ma', [{'ma_20240102.parquet': market_activity_day(DAY(2024, 1, 2))},
                                       {'ma_20240103.parquet': market_activity_day(DAY(2024, 1, 3)).assign(Note='late')}])

    def test_overlaps_and_type_changes_are_left_to_the_full_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'PFC.parquet'
            cm_day(DAY(2024, 1, 3), 400.0).to_parquet(path, index=False)
            before = path.read_bytes()
            for later in (cm_day(DAY(2024, 1, 3), 401.0), cm_day(DAY(2024, 1, 2), 401.0),
                          cm_day(DAY(2024, 1, 4), 401.0).assign(Volume=[1.5, 2.5]),
                          cm_day(DAY(2024, 1, 4), 401.0).drop(columns='Volume')):
                self.assertFalse(self.rules._append_newer_rows(path, later))
            self.assertEqual(path.read_bytes(), before)

    def test_interrupted_write_keeps_the_stored_file(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            raw, processed = self.folders(tmp)
            downloader = object.__new__(self.rules)
            cm_day(DAY(2024, 1, 2), 400.0).to_parquet(raw / 'cm_20240102.parquet', index=False)
            downloader.merge_raw_to_processed(raw, 'cm', processed, 'Equity')
            before = (processed / 'PFC.parquet').read_bytes()
            cm_day(DAY(2024, 1, 3), 410.0).to_parquet(raw / 'cm_20240103.parquet', index=False)
            write_table = pq.write_table

            def disk_full(table, where, *args, **kwargs):
                if Path(where).parent == processed:
                    Path(where).write_bytes(b'PAR1 partial')
                    raise OSError('disk full')
                return write_table(table, where, *args, **kwargs)

            with patch.object(self.module.pq, 'write_table', side_effect=disk_full):
                downloader.merge_raw_to_processed(raw, 'cm', processed, 'Equity')
            self.assertEqual((processed / 'PFC.parquet').read_bytes(), before)
            self.assertEqual([p.name for p in processed.iterdir()], ['PFC.parquet'])
            self.assertTrue((raw / '.retry' / 'PFC.parquet').exists())
            downloader.merge_raw_to_processed(raw, 'cm', processed, 'Equity')
            result = pd.read_parquet(processed / 'PFC.parquet')
        self.assertEqual(result.groupby('Date').size().to_dict(), {DAY(2024, 1, 2): 2, DAY(2024, 1, 3): 2})

    def test_replace_waits_for_a_briefly_locked_file(self):
        attempts = []
        replace = os.replace

        def locked(source, target):
            attempts.append(target)
            if len(attempts) < 3:
                raise PermissionError('in use by OneDrive')
            return replace(source, target)

        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(self.module.os, 'replace', side_effect=locked), \
                patch.object(self.module.time, 'sleep'):
            path = Path(tmp) / 'PFC.parquet'
            self.rules._write_parquet_atomic(cm_day(DAY(2024, 1, 2), 400.0), path)
            self.assertEqual(len(pd.read_parquet(path)), 2)
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ['PFC.parquet'])
        self.assertEqual(len(attempts), 3)


class ReportLayoutTests(unittest.TestCase):
    """Dates in column and symbol names, unmapped symbols and copies of a day."""

    @classmethod
    def setUpClass(cls):
        cls.module = load_script('OGN v2.0-download.py', 'ogn_market_data_layouts')
        cls.rules = cls.module.NSEMarketDataDownloader

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raw, self.processed = Path(self.tmp.name) / 'Raw', Path(self.tmp.name) / 'Processed'
        self.raw.mkdir()
        self.processed.mkdir()
        self.downloader = object.__new__(self.rules)

    def tearDown(self):
        self.tmp.cleanup()

    def merge(self, prefix):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.downloader.merge_raw_to_processed(self.raw, prefix, self.processed, prefix)
        return output.getvalue()

    def save_download(self, prefix, day, frame):
        """Saves a cleaned day the way the downloader does."""
        with contextlib.redirect_stdout(io.StringIO()):
            self.downloader._concurrent_download([day], lambda d: (d, frame), self.raw, prefix, prefix)

    def test_market_activity_date_is_not_a_column_name(self):
        for date in (DAY(2024, 1, 2), DAY(2024, 1, 3)):
            dated_market_activity(date).to_parquet(self.raw / f'ma_{date:%Y%m%d}.parquet', index=False)
        self.merge('ma')
        cleaned = self.downloader._clean_market_activity_data(
            pd.DataFrame({'Unnamed: 0': ['The Nifty witnessed', np.nan], '04-Jan-2024': [np.nan, 'TOP 25']}),
            DAY(2024, 1, 4))
        self.assertEqual(cleaned.columns.tolist(), ['Unnamed: 0', 'Details', 'Symbol', 'Date'])
        self.save_download('ma', DAY(2024, 1, 4), cleaned)
        self.merge('ma')
        result = pd.read_parquet(self.processed / 'MARKET.parquet')
        self.assertEqual(result.columns.tolist(), ['Unnamed: 0', 'Details', 'Symbol', 'Date'])
        self.assertEqual(result.groupby('Date').size().tolist(), [3, 3, 2])
        self.assertEqual(result.loc[result['Date'].eq(DAY(2024, 1, 3)), 'Details'].tolist(),
                         ['nan', 'TOP 25 Securities Today :', 'Top Five Nifty 50 Gainers:'])

    def test_short_sales_keep_their_security_symbol(self):
        cleaned = self.downloader._clean_short_selling_data(
            pd.DataFrame({'Security Name': ['YES BANK LIMITED'], 'Security Symbol': ['YESBANK'],
                          'Trade Date': ['07-Jun-2016'], 'Quantity': [153300]}), DAY(2016, 6, 14))
        self.assertEqual(cleaned[['Symbol', 'Date', 'Qty Short Sold']].values.tolist(),
                         [['YESBANK', DAY(2016, 6, 7), 153300]])
        self.assertNotIn('Security Symbol', cleaned.columns)
        old_short_sales(DAY(2016, 6, 7)).to_parquet(self.raw / 'ss_20160614.parquet', index=False)
        self.merge('ss')
        self.assertEqual(sorted(p.name for p in self.processed.glob('*.parquet')),
                         ['KOTAKBANK.parquet', 'YESBANK.parquet'])
        self.assertEqual(pd.read_parquet(self.processed / 'YESBANK.parquet')['Qty Short Sold'].tolist(), [153300])

    def test_wdm_is_three_series_with_real_column_names(self):
        parsed = self.downloader._parse_wdm_zip(wdm_zip(DAY(2026, 10, 19)), DAY(2026, 10, 19))
        self.assertEqual(sorted(parsed['Symbol'].unique()), ['Debt_add', 'Debt_mat', 'Debt_trd_sett'])
        self.assertEqual(parsed.loc[parsed['Symbol'].eq('Debt_add'), 'Security'].tolist(), ['ICFL', 'IBHF29'])
        old_wdm_day(DAY(2023, 6, 14)).to_parquet(self.raw / 'wdm_20230614.parquet', index=False)
        self.merge('wdm')
        self.save_download('wdm', DAY(2026, 10, 19), parsed)
        self.merge('wdm')
        self.assertEqual(sorted(p.name for p in self.processed.glob('*.parquet')),
                         ['Debt_add.parquet', 'Debt_mat.parquet', 'Debt_trd_sett.parquet'])
        for symbol, header, securities in (('Debt_add', WDM_ADDED, ['ABML', 'ICFL', 'IBHF29']),
                                           ('Debt_mat', WDM_MATURED, ['PFC23', 'PGC26'])):
            stored = pd.read_parquet(self.processed / f'{symbol}.parquet')
            self.assertEqual(sorted(stored.columns), sorted(header + ['Date', 'Symbol']), symbol)
            self.assertEqual(stored['Security'].tolist(), securities)
        trades = pd.read_parquet(self.processed / 'Debt_trd_sett.parquet')
        self.assertEqual(trades['Security'].tolist(), ['CG2031', 'CG2036'])
        self.assertFalse([c for c in trades.columns if c.startswith(('Unnamed', 'Issues'))])

    def test_unexpected_issue_list_is_left_as_it_is(self):
        frame = old_wdm_day(DAY(2023, 6, 14))
        frame.loc[frame['Symbol'].str.startswith('Debt_add'), 'Unnamed: 0'] = 'XX'
        result = self.rules._normalise_wdm(frame)
        self.assertIn('Issues added on 14 June 2023', result.columns)
        self.assertEqual(result['Symbol'].value_counts().to_dict(),
                         {'Debt_add': 3, 'Debt_mat': 1, 'Debt_trd_sett': 1})

    def test_copies_of_a_day_are_stored_once(self):
        for prefix, day_frame in (('cm', lambda d: cm_day(d, 400.0)), ('ma', market_activity_day)):
            with self.subTest(prefix=prefix):
                for path in list(self.raw.iterdir()) + list(self.processed.iterdir()):
                    path.unlink()
                day_frame(DAY(2024, 1, 2)).to_parquet(self.raw / f'{prefix}_20240102.parquet', index=False)
                self.merge(prefix)
                for name in (f'{prefix}_20240103.parquet', f'{prefix}_20240103 (1).parquet',
                             f'{prefix}_20240103-DESKTOP-PC.parquet'):
                    day_frame(DAY(2024, 1, 3)).to_parquet(self.raw / name, index=False)
                output = self.merge(prefix)
                result = pd.read_parquet(next(self.processed.glob('*.parquet')))
                self.assertIn('2 raw files are extra copies of a day', output)
                rows = len(day_frame(DAY(2024, 1, 2)))
                self.assertEqual(result.groupby('Date').size().tolist(), [rows, rows])


class IndicesCleanerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        module = load_script('OGN v2.0-download.py', 'ogn_market_data_indices')
        cls.downloader = object.__new__(module.NSEMarketDataDownloader)

    def test_cnx_era_index_names_are_kept(self):
        frame = pd.DataFrame({
            'Index Name': ['S&P CNX Nifty', 'CNX Bank', 'CNX Nifty Junior', 'NIFTY Midcap 50',
                           'CNX 500', 'S&P CNX NIFTY Sec', 'CNX IT'],
            'Index Date': '01-06-2012', 'Closing Index Value': [4841.6, 9000, 9440, 2400, 3800, 1, 2],
            'P/E': 16.36,
        })
        result = self.downloader._clean_indices_data(frame, DAY(2012, 6, 1))
        self.assertEqual(result['Symbol'].tolist(),
                         ['NIFTY', 'BANKNIFTY', 'NIFTYNEXT50', 'NIFTYMIDCAP50', 'NIFTY500'])
        self.assertEqual(set(result['Date']), {DAY(2012, 6, 1)})

    def test_pr_file_rows_keep_standard_columns(self):
        frame = pd.DataFrame({
            'MKT': ['Y', 'Y', 'N'], 'SECURITY': ['S&P CNX Nifty', 'BANK Nifty', 'ABB LTD.'],
            'OPEN_PRICE': [5086.25, 9331.85, 855.7], 'HIGH_PRICE': [5086.95, 9334.3, 858.8],
            'LOW_PRICE': [4961.05, 9093.15, 845.65], 'CLOSE_PRICE': [4970.2, 9119.05, 854.3],
            'NET_TRDVAL': [1.3e11, 0.0, 1.1e8],
        })
        result = self.downloader._clean_indices_data(frame, DAY(2010, 6, 1))
        self.assertEqual(result.columns.tolist(), ['Date', 'Symbol', 'Open', 'High', 'Low', 'Close'])
        self.assertEqual(result['Symbol'].tolist(), ['NIFTY', 'BANKNIFTY'])
        self.assertEqual(result['Close'].tolist(), [4970.2, 9119.05])


class DerivativesLoaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.paths = {name: root / name for name in ('Derivatives', 'Equity', 'Indices')}
        for path in self.paths.values():
            path.mkdir()
        self.patches = [patch.object(OGN, 'DERIVATIVES_PROCESSED', self.paths['Derivatives']),
                        patch.object(OGN, 'EQUITY_PROCESSED', self.paths['Equity']),
                        patch.object(OGN, 'INDICES_PROCESSED', self.paths['Indices'])]
        for active in self.patches:
            active.start()

    def tearDown(self):
        for active in self.patches:
            active.stop()
        self.tmp.cleanup()

    def write_stock(self):
        legacy = pd.DataFrame({
            'Date': DAY(2023, 12, 29), 'Symbol': 'ABC', 'Instrument': ['FUTSTK', 'OPTSTK'],
            'Expiry': DAY(2024, 1, 25), 'Strike Price': [np.nan, 700.0], 'Option type': ['XX', 'CE'],
            'Close': [705.0, 12.0], 'Contracts': [10.0, 20.0], 'Value': [10.5, 2.0]})
        udiff = pd.DataFrame({
            'Date': DAY(2024, 7, 5), 'Symbol': 'ABC', 'Instrument': ['STF', 'STO'],
            'Expiry': DAY(2024, 7, 25), 'Strike Price': [np.nan, 720.0], 'Option type': ['nan', 'PE'],
            'Close': [725.0, 9.0], 'Contracts': [10.0, 20.0], 'Value': [1.05e6, 2.0e5],
            'UndrlygPric': 721.85, 'NewBrdLotQty': 1100.0})
        pd.concat([legacy, udiff]).to_parquet(self.paths['Derivatives'] / 'ABC.parquet', index=False)
        pd.DataFrame({'Date': [DAY(2023, 12, 29), DAY(2023, 12, 29), DAY(2024, 7, 5)], 'Symbol': 'ABC',
                      'Series': ['EQ', 'N1', 'EQ'], 'Close': [700.0, 1010.0, 721.9]}).to_parquet(
            self.paths['Equity'] / 'ABC.parquet', index=False)

    def test_legacy_and_udiff_rows_are_normalised(self):
        self.write_stock()
        for mode in string_modes():
            with self.subTest(mode=mode), mode():
                frame = OGN.load_derivatives('ABC').set_index(['Date', 'Instrument'])
                legacy, udiff = pd.Timestamp('2023-12-29'), pd.Timestamp('2024-07-05')
                self.assertEqual(frame.loc[(legacy, 'FUTSTK'), 'Underlying Price'], 700.0)
                self.assertEqual(frame.loc[(udiff, 'FUTSTK'), 'Underlying Price'], 721.85)
                self.assertTrue(np.isnan(frame.loc[(legacy, 'OPTSTK'), 'Lot Size']))
                self.assertEqual(frame.loc[(udiff, 'OPTSTK'), 'Lot Size'], 1100.0)
                self.assertEqual(frame.loc[(legacy, 'FUTSTK'), 'Value'], 1_050_000.0)
                self.assertEqual(frame.loc[(udiff, 'FUTSTK'), 'Value'], 1.05e6)
                self.assertEqual(sorted(frame.index.get_level_values('Instrument').unique()),
                                 ['FUTSTK', 'OPTSTK'])

    def test_futures_and_options_loaders_span_both_layouts(self):
        self.write_stock()
        self.assertEqual(len(OGN.load_futures('ABC')), 2)
        self.assertEqual(len(OGN.load_futures('ABC', instrument='FUTSTK')), 2)
        self.assertEqual(len(OGN.load_options('ABC')), 2)
        monthly = OGN.load_monthly_options('ABC', start='2024-01-01')
        self.assertEqual(monthly['Option type'].tolist(), ['PE'])

    def test_index_derivatives_use_stored_index_close(self):
        pd.DataFrame({'Date': [DAY(2012, 6, 1)], 'Symbol': 'NIFTY', 'Close': [4841.6]}).to_parquet(
            self.paths['Indices'] / 'NIFTY.parquet', index=False)
        pd.DataFrame({'Date': [DAY(2012, 6, 1)], 'Symbol': 'MINIFTY', 'Instrument': 'FUTIDX',
                      'Expiry': DAY(2012, 6, 28), 'Close': [4850.0], 'Value': [1.0]}).to_parquet(
            self.paths['Derivatives'] / 'MINIFTY.parquet', index=False)
        self.assertEqual(OGN.load_derivatives('MINIFTY')['Underlying Price'].tolist(), [4841.6])

    def test_missing_cash_data_leaves_spot_blank(self):
        pd.DataFrame({'Date': [DAY(2022, 6, 1)], 'Symbol': 'FINNIFTY', 'Instrument': 'OPTIDX',
                      'Expiry': DAY(2022, 6, 28), 'Close': [10.0], 'Value': [1.0]}).to_parquet(
            self.paths['Derivatives'] / 'FINNIFTY.parquet', index=False)
        self.assertTrue(OGN.load_derivatives('FINNIFTY')['Underlying Price'].isna().all())


class RepairTests(unittest.TestCase):
    FOLDERS = {'EQUITY': 'Equity', 'PRICEBAND': 'PriceBand', 'DELIVERY': 'DeliveryPositions',
               'MARKETACTIVITY': 'MarketActivity', 'SHORTSELLING': 'ShortSelling', 'WDM': 'WDM',
               'INDICES': 'Indices'}

    @classmethod
    def setUpClass(cls):
        cls.module = load_script('OGN v2.0-download.py', 'ogn_market_data_repairs')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.record = self.root / '.migrations.json'
        self.patches = [patch.object(self.module, 'MIGRATIONS_FILE', self.record)]
        for constant, folder in self.FOLDERS.items():
            for kind in ('Raw', 'Processed'):
                path = self.root / folder / kind
                path.mkdir(parents=True)
                self.patches.append(patch.object(self.module, f'{constant}_{kind.upper()}', path))
        for active in self.patches:
            active.start()
        self.downloader = object.__new__(self.module.NSEMarketDataDownloader)

    def tearDown(self):
        for active in self.patches:
            active.stop()
        self.tmp.cleanup()

    def migrate(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.downloader._migrate_data_store()
        return output.getvalue()

    def merge(self, raw, prefix, processed):
        with contextlib.redirect_stdout(io.StringIO()):
            self.downloader.merge_raw_to_processed(raw, prefix, processed, prefix)

    def old_equity_store(self):
        """Raw days keep both series; the old merge left one row per date and symbol."""
        raw, processed = self.module.EQUITY_RAW, self.module.EQUITY_PROCESSED
        days = [DAY(2024, 1, 2), DAY(2024, 1, 3)]
        for day in days:
            pd.DataFrame({'Date': day, 'Symbol': 'PFC', 'Series': ['EQ', 'N1'],
                          'Close': [400.0, 1010.0]}).to_parquet(raw / f'cm_{day:%Y%m%d}.parquet', index=False)
        (raw / '.merged_cm.txt').write_text('\n'.join(f'cm_{day:%Y%m%d}.parquet' for day in days))
        pd.DataFrame({'Date': days, 'Symbol': 'PFC', 'Series': 'N1', 'Close': 1010.0}).to_parquet(
            processed / 'PFC.parquet', index=False)
        return raw, processed, days

    def test_fresh_install_has_nothing_to_repair(self):
        self.assertEqual(self.migrate(), '')
        self.assertEqual(json.loads(self.record.read_text()),
                         ['rebuild-collapsed-rows', 'rebuild-normalised-reports',
                          'redownload-incomplete-indices'])
        self.assertEqual([path for path in self.root.rglob('*') if path.is_file()], [self.record])

    def test_collapsed_rows_are_rebuilt_from_raw(self):
        raw, processed, days = self.old_equity_store()
        ma_raw, ma_processed = self.module.MARKETACTIVITY_RAW, self.module.MARKETACTIVITY_PROCESSED
        market_activity_day(days[0]).to_parquet(ma_raw / 'ma_20240102.parquet', index=False)
        (ma_raw / '.merged_ma.txt').write_text('ma_20240102.parquet')
        market_activity_day(days[0]).tail(1).to_parquet(ma_processed / 'MARKET.parquet', index=False)
        (ma_raw / '.retry').mkdir()
        market_activity_day(days[0]).tail(1).to_parquet(ma_raw / '.retry' / 'MARKET.parquet', index=False)
        self.assertIn('rebuilding 1 processed files', self.migrate())
        self.merge(raw, 'cm', processed)
        self.merge(ma_raw, 'ma', ma_processed)
        equity = pd.read_parquet(processed / 'PFC.parquet')
        self.assertEqual(sorted(zip(equity['Date'], equity['Series'])),
                         [(day, series) for day in days for series in ('EQ', 'N1')])
        self.assertEqual(len(pd.read_parquet(ma_processed / 'MARKET.parquet')), 5)

    def test_store_with_missing_raw_files_is_left_as_is(self):
        raw, processed, _ = self.old_equity_store()
        (raw / 'cm_20240103.parquet').unlink()
        before = (processed / 'PFC.parquet').read_bytes()
        self.assertIn('1 merged raw files are missing or unreadable', self.migrate())
        self.assertEqual((processed / 'PFC.parquet').read_bytes(), before)
        self.assertTrue((raw / '.merged_cm.txt').exists())

    def test_interrupted_rebuild_resumes(self):
        raw, processed, days = self.old_equity_store()
        (processed / 'PFC.parquet').unlink()
        self.migrate()
        self.assertFalse((raw / '.merged_cm.txt').exists())
        self.merge(raw, 'cm', processed)
        self.assertEqual(len(pd.read_parquet(processed / 'PFC.parquet')), 2 * len(days))

    def test_repairs_run_only_once(self):
        self.migrate()
        raw, processed, _ = self.old_equity_store()
        before = (processed / 'PFC.parquet').read_bytes()
        self.assertEqual(self.migrate(), '')
        self.assertEqual((processed / 'PFC.parquet').read_bytes(), before)

    def test_failed_repair_resumes_on_next_run(self):
        raw, processed, _ = self.old_equity_store()
        unlink = Path.unlink

        def locked(path, *args, **kwargs):
            if path.name == 'PFC.parquet':
                raise PermissionError('file is in use')
            return unlink(path, *args, **kwargs)

        with patch.object(Path, 'unlink', locked):
            self.assertIn('resumes on the next run', self.migrate())
        self.assertEqual(json.loads(self.record.read_text()),
                         ['rebuild-normalised-reports', 'redownload-incomplete-indices'])
        self.assertTrue((raw / '.merged_cm.txt').exists())
        self.migrate()
        self.assertFalse((processed / 'PFC.parquet').exists())
        self.assertFalse((raw / '.merged_cm.txt').exists())
        self.assertEqual(len(json.loads(self.record.read_text())), 3)

    def test_index_days_without_nifty_are_downloaded_again(self):
        raw, processed = self.module.INDICES_RAW, self.module.INDICES_PROCESSED
        pd.DataFrame().to_parquet(raw / 'idx_20100601.parquet')
        pd.DataFrame({'Date': [DAY(2014, 6, 2)], 'Symbol': ['NIFTY500'], 'Close': [5000.0]}).to_parquet(
            raw / 'idx_20140602.parquet', index=False)
        pd.DataFrame({'Date': [DAY(2016, 6, 1)] * 2, 'Symbol': ['NIFTY', 'NIFTY500'],
                      'Close': [8179.95, 6900.0]}).to_parquet(raw / 'idx_20160601.parquet', index=False)
        names = ['idx_20100601.parquet', 'idx_20140602.parquet', 'idx_20160601.parquet']
        (raw / '.merged_idx.txt').write_text('\n'.join(names))
        pd.DataFrame({'Date': [DAY(2014, 6, 2)], 'Symbol': ['NIFTY500'], 'Close': [5000.0]}).to_parquet(
            processed / 'NIFTY500.parquet', index=False)
        before = (processed / 'NIFTY500.parquet').read_bytes()
        self.assertIn('re-downloading 2 days', self.migrate())
        self.assertEqual(sorted(path.name for path in raw.glob('*.parquet')), ['idx_20160601.parquet'])
        self.assertEqual((raw / '.merged_idx.txt').read_text().split(), ['idx_20160601.parquet'])
        self.assertEqual((processed / 'NIFTY500.parquet').read_bytes(), before)

    def test_dated_layouts_are_rebuilt_from_raw(self):
        self.record.write_text(json.dumps(['rebuild-collapsed-rows', 'redownload-incomplete-indices']))
        stores = {
            'ma': (self.module.MARKETACTIVITY_RAW, self.module.MARKETACTIVITY_PROCESSED,
                   dated_market_activity(DAY(2024, 1, 2)), 'MARKET.parquet'),
            'ss': (self.module.SHORTSELLING_RAW, self.module.SHORTSELLING_PROCESSED,
                   old_short_sales(DAY(2016, 6, 7)), 'UNKNOWN.parquet'),
            'wdm': (self.module.WDM_RAW, self.module.WDM_PROCESSED,
                    old_wdm_day(DAY(2023, 6, 14)), 'Debt_add20230614.parquet'),
        }
        for prefix, (raw, processed, frame, stored_name) in stores.items():
            frame.to_parquet(raw / f'{prefix}_20240102.parquet', index=False)
            (raw / f'.merged_{prefix}.txt').write_text(f'{prefix}_20240102.parquet')
            frame.to_parquet(processed / stored_name, index=False)
        self.assertEqual(self.migrate().count('One-time repair: rebuilding 1 processed files'), 3)
        for prefix, (raw, processed, _, _) in stores.items():
            self.merge(raw, prefix, processed)
        self.assertEqual(pd.read_parquet(self.module.MARKETACTIVITY_PROCESSED / 'MARKET.parquet').columns.tolist(),
                         ['Unnamed: 0', 'Details', 'Symbol', 'Date'])
        self.assertEqual(sorted(p.name for p in self.module.SHORTSELLING_PROCESSED.glob('*.parquet')),
                         ['KOTAKBANK.parquet', 'YESBANK.parquet'])
        self.assertEqual(sorted(p.name for p in self.module.WDM_PROCESSED.glob('*.parquet')),
                         ['Debt_add.parquet', 'Debt_mat.parquet', 'Debt_trd_sett.parquet'])


class CleanupTests(unittest.TestCase):
    def test_cleanup_applies_the_merge_rules(self):
        cleanup = load_script('parquet_cleanup.py', 'ogn_market_data_cleanup_rules')
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            root = Path(tmp)
            activity = root / 'MarketActivity' / 'Processed'
            derivatives = root / 'Derivatives' / 'Processed'
            activity.mkdir(parents=True)
            derivatives.mkdir(parents=True)
            lines = market_activity_day(DAY(2024, 1, 2))
            pd.concat([lines, lines.tail(1)]).to_parquet(activity / 'MARKET.parquet', index=False)
            pd.concat([legacy_day(DAY(2024, 3, 15)), udiff_day(DAY(2024, 3, 15))]).to_parquet(
                derivatives / 'NIFTY.parquet', index=False)
            with patch.object(cleanup, 'DATA_ROOT', root):
                cleanup.cleanup_duplicates()
            self.assertEqual(len(pd.read_parquet(activity / 'MARKET.parquet')), 5)
            self.assertEqual(sorted(pd.read_parquet(derivatives / 'NIFTY.parquet')['Instrument']), ['IDF', 'IDO'])


class PathTests(unittest.TestCase):
    def test_data_roots_point_to_the_fixed_data_folder(self):
        expected = Path(r'C:\OGN-OneDrive\OneDrive\Github projects\OGN') / 'MarketData_Parquet'
        self.assertEqual(OGN.DATA_ROOT, expected)
        self.assertEqual(load_script('OGN v2.0-download.py', 'ogn_market_data_paths').DATA_ROOT, expected)
        self.assertEqual(load_script('parquet_cleanup.py', 'ogn_market_data_cleanup').DATA_ROOT, expected)

    def test_downloader_stops_when_the_data_folder_is_missing(self):
        module = load_script('OGN v2.0-download.py', 'ogn_market_data_missing_root')
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / 'MarketData_Parquet'
            for mode in ([], ['--japan-only'], ['--schiller-only'], ['--india-schiller-only']):
                with self.subTest(mode=mode):
                    output = io.StringIO()
                    with patch.object(module, 'DATA_ROOT', missing), \
                            patch.object(module.sys, 'argv', ['OGN v2.0-download.py', *mode]), \
                            patch.multiple(module.NSEMarketDataDownloader, _init_session=DEFAULT,
                                           run_incremental_update=DEFAULT, update_japan_series=DEFAULT,
                                           update_schiller_series=DEFAULT,
                                           update_india_schiller_series=DEFAULT) as calls, \
                            patch.object(Path, 'mkdir') as mkdir, \
                            contextlib.redirect_stdout(output), \
                            self.assertRaises(SystemExit) as stopped:
                        module.main()
                    self.assertEqual(stopped.exception.code, 1)
                    self.assertIn(f'Error: Data folder not found: {missing}', output.getvalue())
                    self.assertEqual([name for name, call in calls.items() if call.called], [])
                    mkdir.assert_not_called()
            self.assertFalse(missing.exists())

    def test_downloader_reports_the_data_folder_it_uses(self):
        module = load_script('OGN v2.0-download.py', 'ogn_market_data_existing_root')
        with tempfile.TemporaryDirectory() as tmp:
            output = io.StringIO()
            with patch.object(module, 'DATA_ROOT', Path(tmp)), \
                    patch.object(module.sys, 'argv', ['OGN v2.0-download.py']), \
                    patch.multiple(module.NSEMarketDataDownloader, _init_session=DEFAULT,
                                   run_incremental_update=DEFAULT) as calls, \
                    patch.object(Path, 'mkdir') as mkdir, \
                    contextlib.redirect_stdout(output):
                module.main()
            self.assertIn(f'Data folder: {Path(tmp)}', output.getvalue())
            calls['run_incremental_update'].assert_called_once()
            self.assertTrue(mkdir.called)

    def test_scripts_have_no_working_directory_relative_paths(self):
        literal = re.compile(r"""r?(['"])\.[/\\][^'"\n]*\1""")
        offenders = []
        for path in sorted([*HERE.glob('*.py'), *(HERE / 'downloaded code').glob('*.py')]):
            for number, line in enumerate(path.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
                if literal.search(line) and not line.lstrip().startswith('#'):
                    offenders.append(f'{path.name}:{number}')
        self.assertEqual(offenders, [])


if __name__ == '__main__':
    unittest.main()
