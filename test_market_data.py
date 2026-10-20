"""Regression checks for NSE layout handling, merge robustness, data-store repairs and paths."""

import contextlib
import datetime
import importlib.util
import io
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import DEFAULT, patch

import numpy as np
import pandas as pd
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
                         ['rebuild-collapsed-rows', 'redownload-incomplete-indices'])
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
        self.assertEqual(json.loads(self.record.read_text()), ['redownload-incomplete-indices'])
        self.assertTrue((raw / '.merged_cm.txt').exists())
        self.migrate()
        self.assertFalse((processed / 'PFC.parquet').exists())
        self.assertFalse((raw / '.merged_cm.txt').exists())
        self.assertEqual(len(json.loads(self.record.read_text())), 2)

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
