"""Offline checks for Japan macro sources, calculations and report integration."""

import contextlib
import datetime
import io
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

import japan_macro as japan


def load_downloader():
    path = Path(__file__).with_name('OGN v2.0-download.py')
    spec = importlib.util.spec_from_file_location('ogn_download_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class JapanSourceTests(unittest.TestCase):
    def test_registry_covers_report_once(self):
        symbols = [symbol for _, group in japan.JAPAN_REPORT_GROUPS for symbol in group]
        self.assertEqual(set(symbols), set(japan.JAPAN_SERIES))
        self.assertEqual(len(symbols), len(set(symbols)))
        for definition in japan.JAPAN_SERIES.values():
            for column in ['name', 'series', 'source', 'frequency', 'unit', 'description', 'url']:
                self.assertTrue(definition[column])
            if definition['provider'] is None:
                self.assertTrue(definition['unavailable'])

    def test_bis_policy_units_and_negative_rates(self):
        content = (b'FREQ,REF_AREA,UNIT_MEASURE,UNIT_MULT,TIME_PERIOD,OBS_VALUE\n'
                   b'D,JP,368,0,2024-01-01,-0.1\nD,JP,368,0,2024-01-02,.\n')
        result = japan.parse_bis_csv(content, japan.JAPAN_SERIES['JPPOLRATE'])
        self.assertEqual(result['Value'].iloc[0], -0.1)
        self.assertTrue(pd.isna(result['Value'].iloc[1]))
        with self.assertRaisesRegex(ValueError, 'multiplier'):
            japan.parse_bis_csv(content.replace(b',368,0,', b',368,6,'),
                                japan.JAPAN_SERIES['JPPOLRATE'])
        with self.assertRaisesRegex(ValueError, 'dimension'):
            japan.parse_bis_csv(content.replace(b',JP,', b',US,'),
                                japan.JAPAN_SERIES['JPPOLRATE'])

    def test_bis_rejects_html_and_multiple_series(self):
        with self.assertRaises(ValueError):
            japan.parse_bis_csv(b'<html>Service unavailable</html>',
                                japan.JAPAN_SERIES['JPPOLRATE'])
        content = (b'FREQ,REF_AREA,UNIT_MEASURE,UNIT_MULT,TIME_PERIOD,OBS_VALUE\n'
                   b'D,JP,368,0,2024-01-01,-0.1\nD,JP,368,0,2024-01-01,0.5\n')
        with self.assertRaisesRegex(ValueError, 'multiple'):
            japan.parse_bis_csv(content, japan.JAPAN_SERIES['JPPOLRATE'])

    def test_cftc_sign_and_pagination(self):
        rows = [
            {'report_date_as_yyyy_mm_dd': '2026-09-08T00:00:00',
             'cftc_contract_market_code': '097741',
             'noncomm_positions_long_all': '100', 'noncomm_positions_short_all': '250'},
            {'report_date_as_yyyy_mm_dd': '2026-09-15T00:00:00',
             'cftc_contract_market_code': '097741',
             'noncomm_positions_long_all': '300', 'noncomm_positions_short_all': '125'},
        ]
        replies = [Mock(**{'json.return_value': [row]}) for row in rows]
        replies.append(Mock(**{'json.return_value': []}))
        with patch.object(japan, 'CFTC_PAGE_SIZE', 1), \
                patch.object(japan.requests, 'get', side_effect=replies) as request:
            result = japan.download_cftc_jpy(datetime.date(2026, 9, 1))
        self.assertEqual(result['Value'].tolist(), [150, -175])
        self.assertEqual([call.kwargs['params']['$offset'] for call in request.call_args_list],
                         [0, 1, 2])
        self.assertIn("097741", request.call_args.kwargs['params']['$where'])

    def test_cftc_rejects_error_payload(self):
        with patch.object(japan.requests, 'get', return_value=Mock(
                **{'json.return_value': {'error': 'rate limit'}})):
            with self.assertRaisesRegex(ValueError, 'schema'):
                japan.download_cftc_jpy(datetime.date(2026, 1, 1))

    def test_bis_quarter_end_and_currency(self):
        definition = japan.JAPAN_SERIES['JPXBYEN']
        row = dict(definition['dimensions'], UNIT_MEASURE='USD', UNIT_MULT='6',
                   TIME_PERIOD='2025-Q4', OBS_VALUE='1126057.607')
        content = pd.DataFrame([row]).to_csv(index=False).encode()
        result = japan.parse_bis_csv(content, definition)
        self.assertEqual(result['Date'].iloc[0], pd.Timestamp('2025-12-31'))
        self.assertEqual(result['Value'].iloc[0], 1126057.607)
        with self.assertRaisesRegex(ValueError, 'unit'):
            japan.parse_bis_csv(content.replace(b'USD', b'JPY'), definition)

    def test_bis_foreign_claims_excludes_domestic_positions(self):
        definition = japan.JAPAN_SERIES['JPFOREIGN']
        row = dict(definition['dimensions'], UNIT_MEASURE='USD', UNIT_MULT='6',
                   TIME_PERIOD='2026-Q1', OBS_VALUE='6051101.7')
        content = pd.DataFrame([row]).to_csv(index=False).encode()
        result = japan.parse_bis_csv(content, definition)
        self.assertEqual(result['Value'].tolist(), [6051101.7])
        with self.assertRaisesRegex(ValueError, 'CBS_BANK_TYPE'):
            japan.parse_bis_csv(content.replace(b'4R', b'4B'), definition)

    def test_esri_selects_composite_not_diffusion_or_reference(self):
        frame = pd.DataFrame([
            [None, None, None, None, None, None],
            [None, None, None, 'Composite Indexes', 'Diffusion Indexes',
             '(for reference) no outlier replacement Composite Indexes'],
            [None, None, None, None, None, None],
            ['Time Code', 'Calendar year', 'Month', 'Leading Index', 'Leading Index', 'Leading Index'],
            [None, None, None, None, None, None],
            [None, None, None, '2020=100', None, '2020=100'],
            [2026000707, 2026, 7, 117.9, 66.7, 115.5],
        ])
        with io.BytesIO() as buffer:
            frame.to_excel(buffer, index=False, header=False, engine='openpyxl')
            result = japan.parse_esri_leading(buffer.getvalue())
        self.assertEqual(result['Value'].tolist(), [117.9])
        self.assertEqual(result['Date'].iloc[0], pd.Timestamp('2026-07-01'))
        frame.iloc[5, 3] = '2025=100'
        with io.BytesIO() as buffer:
            frame.to_excel(buffer, index=False, header=False, engine='openpyxl')
            with self.assertRaisesRegex(ValueError, 'base changed'):
                japan.parse_esri_leading(buffer.getvalue())

    def test_mof_year_fill_months_and_yen_scaling(self):
        content = (b'(100 million Yen),,,,\n'
                   b',,,,Current account (a+b+c)\n'
                   b',,2025,Dec,"1,000"\n'
                   b',,2026,Jan,-250\n'
                   b',,,Feb (P),500\n')
        result = japan.parse_mof_current_account(content)
        self.assertEqual(result['Value'].tolist(), [100.0, -25.0, 50.0])
        self.assertEqual(result['Date'].dt.strftime('%Y-%m-%d').tolist(),
                         ['2025-12-01', '2026-01-01', '2026-02-01'])
        with self.assertRaisesRegex(ValueError, 'units'):
            japan.parse_mof_current_account(content.replace(b'100 million Yen', b'USD'))

    def test_carry_matches_dates_without_filling_or_realized_proxy(self):
        us_rate = pd.DataFrame({'Date': ['2026-01-01', '2026-01-02', '2026-01-03'],
                                'Value': [4.5, 4.5, 4.5]})
        japan_rate = pd.DataFrame({'Date': ['2026-01-01', '2026-01-03'],
                                   'Value': [0.5, 0.5]})
        implied = pd.DataFrame({'Date': ['2026-01-01', '2026-01-02', '2026-01-03'],
                                'Value': [10.0, 10.0, 0.0]})
        result = japan.calculate_carry_to_risk(us_rate, japan_rate, implied)
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result['Value'].iloc[0], 0.4)
        self.assertTrue(japan.calculate_carry_to_risk(us_rate, japan_rate, None).empty)

    def test_dashboard_validates_region_unit_and_complete_response(self):
        definition = japan.JAPAN_SERIES['JPCORECPI']
        value = {'@indicator': definition['indicator'], '@regionCode': '00000',
                 '@stat': '00200573', '@unit': '001', '@cycle': '1', '@isSeasonal': '1',
                 '@time': '20260800', '$': '1.7'}
        payload = {'GET_STATS': {'RESULT': {'status': '0'}, 'STATISTICAL_DATA': {
            'RESULT_INF': {'TOTAL_NUMBER': '1'}, 'DATA_INF': {'DATA_OBJ': [{'VALUE': value}]}}}}
        result = japan.parse_dashboard_json(payload, definition)
        self.assertEqual(result['Date'].iloc[0], pd.Timestamp('2026-08-01'))
        self.assertEqual(result['Value'].tolist(), [1.7])
        with self.assertRaisesRegex(ValueError, '@regionCode'):
            japan.parse_dashboard_json(payload, japan.JAPAN_SERIES['JPTOKYOCORE'])
        value['@unit'] = 'yen'
        with self.assertRaisesRegex(ValueError, '@unit'):
            japan.parse_dashboard_json(payload, definition)
        value['@unit'] = '001'
        payload['GET_STATS']['STATISTICAL_DATA']['RESULT_INF']['TOTAL_NUMBER'] = '2'
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            japan.parse_dashboard_json(payload, definition)

    def test_dashboard_error_and_documented_query(self):
        with self.assertRaisesRegex(ValueError, 'Dashboard error'):
            japan.parse_dashboard_json({'GET_STATS': {'RESULT': {'status': '100'}}},
                                        japan.JAPAN_SERIES['JPWAGES'])
        payload = {'GET_STATS': {'RESULT': {'status': '0'}, 'STATISTICAL_DATA': {
            'RESULT_INF': {'TOTAL_NUMBER': '0'}}}}
        with patch.object(japan.requests, 'get', return_value=Mock(
                **{'json.return_value': payload})) as request:
            result = japan.download_dashboard_series(
                japan.JAPAN_SERIES['JPWAGES'], datetime.date(2026, 1, 1))
        self.assertTrue(result.empty)
        self.assertEqual(request.call_args.kwargs['params']['IsSeasonalAdjustment'], '1')
        self.assertEqual(request.call_args.kwargs['params']['TimeFrom'], '20260100')


class JapanRefreshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_downloader()

    def test_japan_constructor_does_not_contact_nse(self):
        downloader_class = self.module.NSEMarketDataDownloader
        with patch.object(downloader_class, '_init_session') as initialize, \
                patch.object(downloader_class, '_create_dirs'):
            downloader_class(initialize_nse=False)
            initialize.assert_not_called()
            downloader_class()
            initialize.assert_called_once()

    def test_refresh_metadata_overlap_and_idempotence(self):
        module = self.module
        downloader = object.__new__(module.NSEMarketDataDownloader)
        registry = {'JP10Y': japan.JAPAN_SERIES['JP10Y']}
        frame = pd.DataFrame({'Date': ['2025-01-01', '2026-08-01'], 'Value': [1.245, 2.94]})
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(module, 'MACRO_PROCESSED', Path(directory)), \
                patch.object(japan, 'JAPAN_SERIES', registry), \
                patch.object(downloader, 'download_japan_series', return_value=frame) as download:
            downloader.update_japan_series()
            downloader.update_japan_series()
            result = pd.read_parquet(Path(directory) / 'JP10Y.parquet')
            self.assertEqual(len(result), 2)
            self.assertEqual(list(result.columns), module.MACRO_COLUMNS)
            self.assertTrue(result['Frequency'].eq('Monthly').all())
            self.assertTrue(result['Description'].str.contains('not real-time').all())
            self.assertEqual(download.call_args.args[1], datetime.date(2025, 6, 27))
            self.assertFalse(list(Path(directory).glob('*.tmp')))

    def test_failed_refresh_keeps_file_and_continues(self):
        module = self.module
        downloader = object.__new__(module.NSEMarketDataDownloader)
        registry = {symbol: japan.JAPAN_SERIES[symbol] for symbol in ['JP10Y', 'JPPOLRATE']}
        frame = pd.DataFrame({'Date': ['2026-01-01'], 'Value': [0.5]})
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(module, 'MACRO_PROCESSED', Path(directory)), \
                patch.object(japan, 'JAPAN_SERIES', registry):
            downloader._macro_write('JP10Y', frame.assign(Symbol='JP10Y'), None)
            original = (Path(directory) / 'JP10Y.parquet').read_bytes()
            with patch.object(downloader, 'download_japan_series', side_effect=[
                    module.DownloadFailedError('Temporary outage'), frame]):
                downloader.update_japan_series()
            self.assertEqual((Path(directory) / 'JP10Y.parquet').read_bytes(), original)
            self.assertTrue((Path(directory) / 'JPPOLRATE.parquet').exists())

    def test_malformed_public_response_retries_and_recovers(self):
        downloader = object.__new__(self.module.NSEMarketDataDownloader)
        frame = pd.DataFrame({'Date': ['2026-01-01'], 'Value': [0.5]})
        with patch.object(japan, 'download_bis_series', side_effect=[ValueError('HTML'), frame]) as fetch, \
                patch.object(self.module.time, 'sleep') as sleep:
            result = downloader.download_japan_series('JPPOLRATE', datetime.date(2026, 1, 1))
        self.assertEqual(len(result), 1)
        self.assertEqual(fetch.call_count, 2)
        sleep.assert_called_once_with(1.0)

    def test_unavailable_feeds_never_create_fake_data(self):
        module = self.module
        downloader = object.__new__(module.NSEMarketDataDownloader)
        registry = {symbol: japan.JAPAN_SERIES[symbol] for symbol in ['JPPMI', 'JPCARRY']}
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(module, 'MACRO_PROCESSED', Path(directory)), \
                patch.object(japan, 'JAPAN_SERIES', registry), \
                patch.object(module.requests, 'get') as request:
            downloader.update_japan_series()
            self.assertFalse(list(Path(directory).iterdir()))
            request.assert_not_called()


class JapanReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import matplotlib
        matplotlib.use('Agg')
        path = Path(__file__).with_name('Option-OGN.py')
        spec = importlib.util.spec_from_file_location('ogn_report_test', path)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_report_keeps_pages_with_data_and_drops_empty_ones(self):
        module = self.module
        definition = japan.JAPAN_SERIES['JP10Y']
        today = pd.Timestamp.today().normalize()
        frame = pd.DataFrame({'Date': [today - pd.Timedelta(days=45), today - pd.Timedelta(days=15)],
                               'Value': [1.5, 1.7], 'Unit': definition['unit'],
                               'Series': definition['series']})
        document = Mock()
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(module, 'MACRO_PROCESSED', Path(directory)), \
            patch.object(japan.requests, 'get', side_effect=AssertionError('Charts must not download')), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            frame.to_parquet(Path(directory) / 'JP10Y.parquet', index=False)
            result = module.plot_japan_macro(pdf_pages=document)
        self.assertEqual(result['JP10Y'], 'plotted')
        self.assertEqual(result['JPPMI'], 'unavailable')
        self.assertEqual(result['JPCARRY'], 'unavailable')
        self.assertEqual(set(result), set(japan.JAPAN_SERIES))
        # Only the page holding JP10Y has data; its other series still show why they are missing.
        self.assertEqual(document.savefig.call_count, 1)
        text = '\n'.join(label.get_text() for call in document.savefig.call_args_list
                         for label in call.args[0].texts)
        kept, *dropped = japan.JAPAN_REPORT_GROUPS
        for symbol in kept[1]:
            self.assertIn(symbol + ' | ', text)
        for _, symbols in dropped:
            self.assertTrue(all(symbol + ' | ' not in text for symbol in symbols))
            self.assertIn(', '.join(symbols), output.getvalue())
        self.assertIn('Past 1 year', text)
        self.assertIn('Japan 1/1', text)
        self.assertIn('Observed ', text)
        self.assertIn('not publication timestamps', text)
        self.assertFalse(module.plt.get_fignums())

    def test_report_with_no_data_in_range_has_no_pages(self):
        module = self.module
        definition = japan.JAPAN_SERIES['JP10Y']
        stale = pd.DataFrame({'Date': pd.to_datetime(['2020-01-01', '2020-02-01']), 'Value': [1.0, 1.1],
                              'Unit': definition['unit'], 'Series': definition['series']})
        document = Mock()
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(module, 'MACRO_PROCESSED', Path(directory)), \
                contextlib.redirect_stdout(io.StringIO()):
            stale.to_parquet(Path(directory) / 'JP10Y.parquet', index=False)
            result = module.plot_japan_macro(pdf_pages=document)
            document.savefig.assert_not_called()
            self.assertEqual(set(result.values()), {'unavailable'})
            module.plot_japan_macro(pdf_pages=document, years=10)
        self.assertEqual(document.savefig.call_count, 1)

    def test_daily_panels_skip_non_trading_days_and_monthly_keep_calendar(self):
        from matplotlib.dates import date2num
        module = self.module
        today = pd.Timestamp.today().normalize()
        daily_dates = pd.bdate_range(end=today - pd.Timedelta(days=3), periods=60)
        monthly_dates = pd.date_range(end=today - pd.Timedelta(days=40), periods=10, freq='MS')
        frames = {}
        for symbol, dates in (('JPUSDJPY', daily_dates), ('JP10Y', monthly_dates)):
            definition = japan.JAPAN_SERIES[symbol]
            frames[symbol] = pd.DataFrame({'Date': dates, 'Value': np.linspace(1.0, 2.0, len(dates)),
                                           'Unit': definition['unit'], 'Series': definition['series']})
        document = Mock()
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(module, 'MACRO_PROCESSED', Path(directory)), \
                patch.object(japan.requests, 'get', side_effect=AssertionError('Charts must not download')):
            for symbol, frame in frames.items():
                frame.to_parquet(Path(directory) / f'{symbol}.parquet', index=False)
            module.plot_japan_macro(pdf_pages=document)
        lines = {len(line.get_xdata()): line.get_xdata()
                 for call in document.savefig.call_args_list
                 for axes in call.args[0].axes for line in axes.get_lines()
                 if len(line.get_xdata()) in (len(daily_dates), len(monthly_dates))}
        np.testing.assert_array_equal(lines[len(daily_dates)], np.arange(len(daily_dates), dtype=float))
        np.testing.assert_allclose(lines[len(monthly_dates)], date2num(monthly_dates.to_numpy()))

    def test_appendix_once_per_pdf_and_section_toggle(self):
        module = self.module
        with patch.object(module, 'REPORT_SECTIONS', ['japan_macro']), \
                patch.object(module, 'load_analysis_frame', side_effect=FileNotFoundError('offline test')), \
                patch.object(module, 'PdfPages') as document, \
                patch.object(module, 'plot_japan_macro') as render, \
                tempfile.TemporaryDirectory() as directory:
            module.FnOAnalysis(scrip_list=['GLD', 'SLV'], pdf_path=str(Path(directory) / 'report.pdf'))
            render.assert_called_once_with(pdf_pages=document.return_value, years=module.REPORT_YEARS)
            document.return_value.close.assert_called_once()
            render.reset_mock()
            with patch.object(module, 'REPORT_SECTIONS', []):
                module.FnOAnalysis(single_scrip='GLD', pdf_path=str(Path(directory) / 'disabled.pdf'))
            render.assert_not_called()


if __name__ == '__main__':
    unittest.main()