"""Offline regressions for market valuation sources and separate Indian CAPE."""

import unittest
import datetime
import importlib.util
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

import nifty_macro
import schiller_macro


class SchillerSourceTests(unittest.TestCase):
    def test_multpl_monthly_values_and_estimates(self):
        html = '<h1>S&P 500 PE Ratio by Month</h1><table id="datatable">' \
               '<tr><th>Date</th><th>Value</th></tr>' \
               '<tr><td>Sep 18, 2026</td><td>99</td></tr>' \
               '<tr><td>Sep 1, 2026</td><td><abbr title="Estimate">*</abbr>26.04</td></tr>' \
               '<tr><td>Jan 1, 1871</td><td>11.10</td></tr></table>'
        result = schiller_macro.parse_multpl_table(html, schiller_macro.SCHILLER_SERIES['SCHPE'])
        self.assertEqual(result['Value'].tolist(), [11.1, 26.04])
        self.assertEqual(result['Estimated'].tolist(), [False, True])

    def test_multpl_percent_units_and_quarter_dates(self):
        html = '<h1>S&P 500 Earnings Yield by Month</h1><table id="datatable">' \
               '<tr><th>Date</th><th>Value</th></tr>' \
               '<tr><td>Jan 1, 2025</td><td>4.25%</td></tr></table>'
        result = schiller_macro.parse_multpl_table(html, schiller_macro.SCHILLER_SERIES['SCHEY'])
        self.assertEqual(result['Value'].tolist(), [4.25])
        with self.assertRaisesRegex(ValueError, 'unit'):
            schiller_macro.parse_multpl_table(html.replace('%', ''), schiller_macro.SCHILLER_SERIES['SCHEY'])
        html = '<h1>S&P 500 Price to Book Value by Quarter</h1><table id="datatable">' \
               '<tr><th>Date</th><th>Value</th></tr>' \
               '<tr><td>Sep 18, 2026</td><td>6.06</td></tr>' \
               '<tr><td>Dec 31, 2025</td><td>5.39</td></tr></table>'
        result = schiller_macro.parse_multpl_table(html, schiller_macro.SCHILLER_SERIES['SCHPB'])
        self.assertEqual(result['Value'].tolist(), [5.39])

    def test_multpl_block_page_is_an_error(self):
        with self.assertRaises(ValueError):
            schiller_macro.parse_multpl_table('<html>Access denied</html>',
                                               schiller_macro.SCHILLER_SERIES['SCHPE'])

    def test_shiller_dates_and_conventional_not_total_return_cape(self):
        raw = pd.DataFrame([
            [None, None, None, None, 'Real', 'Return', None],
            ['Date', 'P', 'E', 'CAPE', 'Price', 'Price', 'TR CAPE'],
            [1871.01, 4.44, 0.4, np.nan, 100.0, 500.0, np.nan],
            [1881.1, 5.0, 0.5, 10.0, 120.0, 600.0, 99.0],
            [1881.11, 6.0, 0.6, 11.0, 140.0, 700.0, 98.0],
            [None, 'Notes', None, None, None, None, None],
        ])
        result = schiller_macro.parse_shiller_frame(raw)
        self.assertEqual(result['SCHCAPE']['Value'].tolist(), [10, 11])
        self.assertEqual(result['SCHCAPE']['Date'].iloc[0], pd.Timestamp('1881-10-01'))
        self.assertEqual(result['SCHREAL']['Value'].tolist(), [100, 120, 140])
        self.assertEqual(result['SCHEARN']['Date'].min(), pd.Timestamp('1871-01-01'))
        raw.iloc[3, 0] = 1881.13
        with self.assertRaisesRegex(ValueError, 'date'):
            schiller_macro.parse_shiller_frame(raw)


class NiftyCapeTests(unittest.TestCase):
    def monthly_inputs(self, months=121):
        periods = pd.period_range('2000-01', periods=months, freq='M')
        monthly = pd.DataFrame({'Close': 1000.0, 'PE': 20.0}, index=periods)
        monthly.attrs['symbol'] = 'NIFTY'
        cpi = pd.DataFrame({'Date': periods.to_timestamp(), 'Value': 100.0,
                            'Symbol': 'INCPI', 'Series': 'INDCPIALLMINMEI',
                            'Unit': 'Index 2015=100', 'Frequency': 'Monthly'})
        return monthly, cpi

    def test_cape_requires_full_ten_year_window(self):
        monthly, cpi = self.monthly_inputs()
        result = nifty_macro.calculate_nifty_cape(monthly, cpi)
        self.assertEqual(len(result), 2)
        np.testing.assert_allclose(result['Value'], [20, 20])
        self.assertEqual(result['Date'].iloc[0], pd.Timestamp('2009-12-31'))
        self.assertTrue(nifty_macro.calculate_nifty_cape(monthly.iloc[:119], cpi).empty)

    def test_indian_inflation_adjustment_is_not_ordinary_pe(self):
        monthly, cpi = self.monthly_inputs(120)
        cpi['Value'] = np.linspace(100, 200, 120)
        result = nifty_macro.calculate_nifty_cape(monthly, cpi)
        expected = (1000 / 200) / (50 / cpi['Value']).mean()
        self.assertAlmostEqual(result['Value'].iloc[0], expected)
        self.assertNotAlmostEqual(result['Value'].iloc[0], 20)

    def test_us_cpi_and_foreign_index_are_rejected(self):
        monthly, cpi = self.monthly_inputs(120)
        for column, value in [('Symbol', 'USCPI'), ('Series', 'CPIAUCSL'),
                              ('Unit', 'Percent YoY'), ('Frequency', 'Annual')]:
            with self.subTest(column=column), self.assertRaisesRegex(ValueError, 'Indian CPI'):
                nifty_macro.calculate_nifty_cape(monthly, cpi.assign(**{column: value}))
        monthly.attrs['symbol'] = 'SP500'
        with self.assertRaisesRegex(ValueError, 'Indian NIFTY'):
            nifty_macro.calculate_nifty_cape(monthly, cpi)
        daily = pd.DataFrame({'Date': pd.bdate_range('2025-01-01', periods=23),
                               'Symbol': 'SP500', 'Close': 1000.0, 'PE': 20.0})
        with self.assertRaisesRegex(ValueError, 'Indian NIFTY'):
            nifty_macro.nifty_monthly_valuation(daily)

    def test_missing_month_or_cpi_never_filled(self):
        monthly, cpi = self.monthly_inputs(120)
        self.assertTrue(nifty_macro.calculate_nifty_cape(monthly.drop(monthly.index[20]), cpi).empty)
        self.assertTrue(nifty_macro.calculate_nifty_cape(monthly, cpi.drop(index=20)).empty)
        self.assertTrue(nifty_macro.calculate_nifty_cape(monthly, None).empty)
        cpi.loc[20, 'Value'] = 0
        self.assertTrue(nifty_macro.calculate_nifty_cape(monthly, cpi).empty)

    def test_monthly_selection_checks_coverage_and_latest_pe(self):
        dates = pd.bdate_range('2025-01-01', '2025-02-05')
        frame = pd.DataFrame({'Date': dates, 'Symbol': 'NIFTY', 'Close': 1000.0, 'PE': 20.0})
        result = nifty_macro.nifty_monthly_valuation(frame)
        self.assertEqual(result.index.tolist(), [pd.Period('2025-01', freq='M')])
        self.assertEqual(result.attrs['symbol'], 'NIFTY')
        frame.loc[frame['Date'].eq(pd.Timestamp('2025-01-31')), 'PE'] = np.nan
        monthly = nifty_macro.nifty_monthly_valuation(frame)
        self.assertTrue(nifty_macro.calculate_nifty_metrics(monthly)['NIFTYPE'].empty)

    def test_india_matrix_published_and_derived_metrics(self):
        monthly, _ = self.monthly_inputs(2)
        monthly['PB'] = [3.0, 4.0]
        monthly['DY'] = [0.0, 1.2]
        metrics = nifty_macro.calculate_nifty_metrics(monthly)
        self.assertEqual(metrics['NIFTYEY']['Value'].tolist(), [5, 5])
        self.assertEqual(metrics['NIFTYEPS']['Value'].tolist(), [50, 50])
        self.assertEqual(metrics['NIFTYPB']['Value'].tolist(), [3, 4])
        self.assertEqual(metrics['NIFTYDY']['Value'].tolist(), [0, 1.2])
        symbols = [symbol for _, group in nifty_macro.NIFTY_REPORT_GROUPS for symbol in group]
        self.assertEqual(set(symbols), set(nifty_macro.NIFTY_SERIES))
        self.assertEqual(len(symbols), len(set(symbols)))
        self.assertTrue(set(symbols).isdisjoint(schiller_macro.SCHILLER_SERIES))
        self.assertIsNone(nifty_macro.NIFTY_SERIES['INIIMCAPE']['provider'])
        self.assertEqual(nifty_macro.NIFTY_SERIES['NIFTYCAPE']['provider'], 'Derived')


class ValuationUpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            'ogn_valuation_download_test', Path(__file__).with_name('OGN v2.0-download.py'))
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_us_history_and_revision_merge_preserve_1871(self):
        module = self.module
        downloader = object.__new__(module.NSEMarketDataDownloader)
        definition = schiller_macro.SCHILLER_SERIES['SCHPE']
        first = pd.DataFrame({'Date': pd.to_datetime(['1871-01-01', '2025-01-01']),
                              'Value': [11.1, 20.0], 'Estimated': [False, True]})
        revised = pd.DataFrame({'Date': pd.to_datetime(['2025-01-01', '2026-01-01']),
                                'Value': [21.0, 22.0], 'Estimated': False})
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(module, 'MACRO_PROCESSED', Path(directory)), \
                patch.object(schiller_macro, 'SCHILLER_SERIES', {'SCHPE': definition}), \
                patch.object(downloader, 'download_schiller_series', side_effect=[first, revised]) as fetch:
            downloader.update_schiller_series()
            downloader.update_schiller_series()
            stored = pd.read_parquet(Path(directory) / 'SCHPE.parquet')
            self.assertEqual(stored['Value'].tolist(), [11.1, 21.0, 22.0])
            self.assertEqual(stored['Date'].min(), datetime.date(1871, 1, 1))
            self.assertEqual(fetch.call_args_list[0].args[1], datetime.date(1871, 1, 1))
            self.assertEqual(stored.columns.tolist(), module.MACRO_COLUMNS)
            self.assertFalse(list(Path(directory).glob('*.tmp')))

    def test_full_real_price_refresh_rebases_old_history_and_rejects_truncation(self):
        module = self.module
        downloader = object.__new__(module.NSEMarketDataDownloader)
        definition = schiller_macro.SCHILLER_SERIES['SCHREAL']
        frame = pd.DataFrame({'Date': ['1871-01-01', '2026-01-01'], 'Value': [10.0, 100.0]})
        with tempfile.TemporaryDirectory() as directory, patch.object(module, 'MACRO_PROCESSED', Path(directory)):
            original = downloader._write_valuation_series('SCHREAL', definition, frame, None)
            fresh = frame.assign(Value=[11.0, 110.0])
            result = downloader._write_valuation_series('SCHREAL', definition, fresh, original)
            self.assertEqual(result['Value'].tolist(), [11, 110])
            saved = (Path(directory) / 'SCHREAL.parquet').read_bytes()
            with self.assertRaisesRegex(module.DownloadFailedError, 'Truncated'):
                downloader._write_valuation_series('SCHREAL', definition, fresh.iloc[1:], result)
            self.assertEqual((Path(directory) / 'SCHREAL.parquet').read_bytes(), saved)

    def test_us_download_retries_parser_and_honours_rate_limit(self):
        downloader = object.__new__(self.module.NSEMarketDataDownloader)
        frame = pd.DataFrame({'Date': pd.to_datetime(['2025-01-01']), 'Value': [20.0]})
        with patch.object(schiller_macro, 'download_multpl_series', side_effect=[ValueError('HTML'), frame]) as fetch, \
                patch.object(self.module.time, 'sleep') as sleep:
            result = downloader.download_schiller_series('SCHPE', datetime.date(1871, 1, 1))
        self.assertEqual(len(result), 1)
        self.assertEqual(fetch.call_count, 2)
        sleep.assert_called_once_with(1.0)
        response = self.module.requests.Response()
        response.status_code = 429
        response.headers['Retry-After'] = '7'
        error = self.module.requests.HTTPError('rate limited', response=response)
        with patch.object(schiller_macro, 'download_multpl_series', side_effect=[error, frame]), \
                patch.object(self.module.time, 'sleep') as sleep:
            downloader.download_schiller_series('SCHPE', datetime.date(1871, 1, 1))
        sleep.assert_called_once_with(7.0)

    def test_workbook_is_reused_within_one_group_update(self):
        module = self.module
        downloader = object.__new__(module.NSEMarketDataDownloader)
        frame = pd.DataFrame({'Date': pd.to_datetime(['1881-01-01']), 'Value': [10.0]})
        payload = {symbol: frame for symbol in ['SCHCAPE', 'SCHREAL', 'SCHEARN']}
        registry = {symbol: schiller_macro.SCHILLER_SERIES[symbol] for symbol in payload}
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(module, 'MACRO_PROCESSED', Path(directory)), \
                patch.object(schiller_macro, 'SCHILLER_SERIES', registry), \
                patch.object(schiller_macro, 'download_shiller_workbook', return_value=payload) as fetch:
            downloader.update_schiller_series()
        fetch.assert_called_once()

    def test_failed_series_retains_history_and_other_us_series_continue(self):
        module = self.module
        downloader = object.__new__(module.NSEMarketDataDownloader)
        frame = pd.DataFrame({'Date': ['2025-01-01'], 'Value': [20.0]})
        registry = {symbol: schiller_macro.SCHILLER_SERIES[symbol] for symbol in ['SCHPE', 'SCHEY']}
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(module, 'MACRO_PROCESSED', Path(directory)), \
                patch.object(schiller_macro, 'SCHILLER_SERIES', registry):
            downloader._write_valuation_series('SCHPE', registry['SCHPE'], frame, None)
            original = (Path(directory) / 'SCHPE.parquet').read_bytes()
            with patch.object(downloader, 'download_schiller_series', side_effect=[
                    module.DownloadFailedError('outage'), frame]):
                downloader.update_schiller_series()
            self.assertEqual((Path(directory) / 'SCHPE.parquet').read_bytes(), original)
            self.assertTrue((Path(directory) / 'SCHEY.parquet').exists())

    def test_india_updater_rejects_foreign_cpi_before_relabelling(self):
        module = self.module
        downloader = object.__new__(module.NSEMarketDataDownloader)
        foreign = pd.DataFrame({'Date': ['2025-01-01'], 'Value': [200.0], 'Symbol': 'USCPI',
                                'Series': 'CPIAUCSL', 'Unit': 'Index 1982-1984=100',
                                'Frequency': 'Monthly'})
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(module, 'MACRO_PROCESSED', Path(directory)), \
                patch.object(module, 'INDICES_PROCESSED', Path(directory)), \
                patch.object(downloader, 'download_fred_series', return_value=foreign):
            downloader.update_india_schiller_series()
            self.assertFalse((Path(directory) / 'INCPI.parquet').exists())
            self.assertFalse((Path(directory) / 'NIFTYCAPE.parquet').exists())

    def test_indian_update_never_fetches_us_data(self):
        module = self.module
        downloader = object.__new__(module.NSEMarketDataDownloader)
        dates = pd.bdate_range('2000-01-01', '2010-12-31')
        indian_index = pd.DataFrame({'Date': dates, 'Symbol': 'NIFTY', 'Close': 1000.0,
                                     'PE': 20.0, 'PB': 3.0, 'DY': 1.5})
        months = pd.date_range('2000-01-01', '2010-12-01', freq='MS')
        cpi = pd.DataFrame({'Date': months, 'Value': 100.0, 'Symbol': 'INCPI',
                            'Series': nifty_macro.INDIA_CPI_SERIES, 'Unit': nifty_macro.INDIA_CPI_UNIT,
                            'Frequency': 'Monthly'})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            indian_index.to_parquet(root / 'NIFTY.parquet', index=False)
            with patch.object(module, 'MACRO_PROCESSED', root), \
                    patch.object(module, 'INDICES_PROCESSED', root), \
                    patch.object(downloader, 'download_fred_series', return_value=cpi) as fetch, \
                    patch.object(downloader, 'download_schiller_series') as us_fetch:
                downloader.update_india_schiller_series()
                fetch.assert_called_once()
                self.assertEqual(fetch.call_args.args[:2], ('INCPI', nifty_macro.INDIA_CPI_SERIES))
                us_fetch.assert_not_called()
                stored = pd.read_parquet(root / 'NIFTYCAPE.parquet')
                np.testing.assert_allclose(stored['Value'], 20.0)
                self.assertEqual(len(stored), 13)
                self.assertFalse((root / 'INIIMCAPE.parquet').exists())
                self.assertFalse((root / 'INRBICPI.parquet').exists())


class ValuationReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import matplotlib
        matplotlib.use('Agg')
        spec = importlib.util.spec_from_file_location(
            'ogn_valuation_report_test', Path(__file__).with_name('Option-OGN.py'))
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_indian_and_us_pages_keep_tickers_separate(self):
        module = self.module
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(module, 'MACRO_PROCESSED', Path(directory)), \
                patch.object(schiller_macro.requests, 'get', side_effect=AssertionError('Charts must be offline')):
            us_document = Mock()
            india_document = Mock()
            us = module.plot_schiller_macro(pdf_pages=us_document)
            india = module.plot_india_schiller(pdf_pages=india_document)
        self.assertEqual(set(us), set(schiller_macro.SCHILLER_SERIES))
        self.assertEqual(set(india), set(nifty_macro.NIFTY_SERIES))
        self.assertTrue(set(us).isdisjoint(india))
        self.assertEqual(us_document.savefig.call_count, 2)
        self.assertEqual(india_document.savefig.call_count, 2)
        us_text = '\n'.join(text.get_text() for call in us_document.savefig.call_args_list
                            for text in call.args[0].texts)
        india_text = '\n'.join(text.get_text() for call in india_document.savefig.call_args_list
                               for text in call.args[0].texts)
        self.assertIn('India Schiller', india_text)
        self.assertIn('NIFTYCAPE |', india_text)
        self.assertNotIn('SCHCAPE |', india_text)
        self.assertNotIn('NIFTYCAPE |', us_text)
        self.assertIn('US Schiller', us_text)
        self.assertFalse(module.plt.get_fignums())

    def test_new_appendices_are_once_per_report_and_can_be_disabled(self):
        module = self.module
        with patch.object(module, 'REPORT_SECTIONS', ['schiller_macro', 'india_schiller']), \
                patch.object(module, 'load_analysis_frame', side_effect=FileNotFoundError('test')), \
                patch.object(module, 'PdfPages') as document, \
                patch.object(module, 'plot_schiller_macro') as us, \
                patch.object(module, 'plot_india_schiller') as india, \
                tempfile.TemporaryDirectory() as directory:
            module.FnOAnalysis(scrip_list=['WTI', 'GLD'], pdf_path=str(Path(directory) / 'report.pdf'))
            us.assert_called_once_with(pdf_pages=document.return_value)
            india.assert_called_once_with(pdf_pages=document.return_value)
            us.reset_mock()
            india.reset_mock()
            with patch.object(module, 'REPORT_SECTIONS', []):
                module.FnOAnalysis(single_scrip='WTI', pdf_path=str(Path(directory) / 'disabled.pdf'))
            us.assert_not_called()
            india.assert_not_called()


if __name__ == '__main__':
    unittest.main()