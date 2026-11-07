"""Checks for volatility guide, max pain and PCR pages, report windows and timestamped files."""

import datetime
import importlib.util
import io
import itertools
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

GUIDE_TITLES = ['Volatility Cone', 'Distribution by window', 'Rolling YangZhang (30-day window)',
                'Distribution of estimator values', 'Summary', 'Putting it together']


class VolatilityGuideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import matplotlib
        matplotlib.use('Agg')
        spec = importlib.util.spec_from_file_location(
            'ogn_report_pages_test', Path(__file__).with_name('Option-OGN.py'))
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    @staticmethod
    def prices(periods=600):
        generator = np.random.default_rng(11)
        returns = generator.normal(0, 0.01, periods)
        returns[300:320] *= 4  # one volatility burst
        close = 20000 * np.exp(np.cumsum(returns))
        opening = np.concatenate([[close[0]], close[:-1]])
        spread = np.abs(generator.normal(0, 0.004, periods)) * close
        return pd.DataFrame({'Open': opening, 'High': np.maximum(opening, close) + spread,
                             'Low': np.minimum(opening, close) - spread, 'Close': close,
                             'Volume': 1000.0}, index=pd.bdate_range(end='2026-10-21', periods=periods))

    def profile(self, estimator='YangZhang', options=None):
        profile = self.module.compute_volatility_profile(self.prices(), estimator=estimator)
        profile['option_overlay'] = options
        return profile

    def render(self, profile):
        document = Mock()
        count = self.module.plot_volatility_guide(profile, 'TEST', pdf_pages=document)
        figure = document.savefig.call_args.args[0]
        texts = [text.get_text() for text in figure.texts]
        return count, figure, texts, ' '.join(texts).replace('\n', ' ')

    def assert_no_overlaps(self, figure):
        figure.canvas.draw()
        renderer = figure.canvas.get_renderer()
        boxes = [text.get_window_extent(renderer) for text in figure.texts if text.get_text()]
        for box in boxes:
            self.assertGreaterEqual(box.x0, 0)
            self.assertLessEqual(box.x1, figure.bbox.x1)
            self.assertGreaterEqual(box.y0, 0)
        for first, second in itertools.combinations(boxes, 2):
            self.assertFalse(first.overlaps(second))

    def test_guide_explains_each_graph_with_the_report_numbers(self):
        profile = self.profile()
        count, figure, texts, body = self.render(profile)
        self.assertEqual(count, len(GUIDE_TITLES))
        for title in GUIDE_TITLES:
            self.assertIn(title, texts)
        cone, rolling = profile['cone'], profile['rolling']
        latest = rolling.iloc[-1]
        rank = self.module._ordinal(self.module._percentile_rank(rolling, latest))
        self.assertIn(f'{latest * 100:.0f}% at the {rank} percentile of {len(rolling):,} readings', body)
        focus = cone['windows'].index(30)
        self.assertIn(f"30-day: min {cone['min'][focus] * 100:.0f}%, median {cone['median'][focus] * 100:.0f}%, "
                      f"max {cone['max'][focus] * 100:.0f}%", body)
        self.assertIn(f"Peak {rolling.max() * 100:.0f}% in {rolling.idxmax():%b %Y}", body)
        self.assert_no_overlaps(figure)
        self.assertFalse(self.module.plt.get_fignums())

    def test_guide_follows_the_panel_registry_and_option_overlay(self):
        with patch.object(self.module, 'VOLATILITY_PANELS', ['cone', 'summary']):
            count, _, texts, _ = self.render(self.profile())
        self.assertEqual(count, 3)
        self.assertNotIn('Distribution by window', texts)

        as_of = pd.Timestamp('2026-10-21')
        points = pd.DataFrame({
            'Date': as_of, 'Option type': ['CE', 'CE', 'PE', 'PE'], 'IV': [0.14, 0.16, 0.17, 0.19],
            'Expiry': pd.to_datetime(['2026-10-27', '2026-10-27', '2026-10-27', '2026-11-03']),
            'Expiry type': ['Monthly', 'Monthly', 'Monthly', 'Weekly'], 'RV mean': 0.17,
            'Tenor sessions': [4, 4, 4, 9]})
        count, figure, texts, body = self.render(self.profile(options={'points': points, 'as_of': as_of}))
        self.assertEqual(count, 7)
        self.assertIn('Option IV on the cone', texts)
        self.assertIn('27 Oct expiry, 4 sessions: median CE 15%, PE 17% vs 17% realized mean.', body)
        self.assert_no_overlaps(figure)

    def test_moment_estimator_guide_stays_off_option_pricing(self):
        count, _, texts, body = self.render(self.profile(estimator='Skew'))
        self.assertNotIn('Putting it together', texts)
        self.assertNotIn('rich', body)
        self.assertNotIn('option', body.lower())
        self.assertEqual(count, len(GUIDE_TITLES) - 1)

    def test_volatility_page_points_to_the_guide(self):
        for sections, expected in [(['volatility', 'volatility_guide'], True), (['volatility'], False)]:
            document = Mock()
            with patch.object(self.module, 'REPORT_SECTIONS', sections):
                self.module.plot_volatility(self.profile(), 'TEST', pdf_pages=document)
            texts = [text.get_text() for text in document.savefig.call_args.args[0].texts]
            self.assertEqual(any('Next page: how to read each graph.' in text for text in texts), expected)


class TimestampedReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import matplotlib
        matplotlib.use('Agg')
        spec = importlib.util.spec_from_file_location(
            'ogn_timestamp_test', Path(__file__).with_name('Option-OGN.py'))
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_cli_accepts_single_symbol_observation_windows(self):
        window = self.module.ReportWindow
        last_250 = window('250d', last=250)
        cases = [
            (['--pdf', 'WTI', '250d'], 'WTI_250d_Analysis.pdf', last_250),
            (['WTI', '250D', '--pdf'], 'WTI_250d_Analysis.pdf', last_250),
            (['--pdf', '--periods', '250', 'WTI'], 'WTI_250d_Analysis.pdf', last_250),
            (['WTI', '250d'], None, last_250),
            (['WTI', '--periods', '250'], None, last_250),
            (['--pdf', 'WTI', '350d-25d'], 'WTI_350d-25d_Analysis.pdf', window('350d-25d', last=350, skip=25)),
            (['--pdf', 'WTI', 'jan2026'], 'WTI_Jan2026_Analysis.pdf',
             window('Jan2026', start=pd.Timestamp('2026-01-01'), end=pd.Timestamp('2026-01-31'))),
            (['--pdf', 'WTI', 'January2026-Mar2026'], 'WTI_Jan2026-Mar2026_Analysis.pdf',
             window('Jan2026-Mar2026', start=pd.Timestamp('2026-01-01'), end=pd.Timestamp('2026-03-31'))),
        ]
        for arguments, filename, expected_window in cases:
            with self.subTest(arguments=arguments), \
                    patch.object(self.module.sys, 'argv', ['Option-OGN.py', *arguments]), \
                    patch.object(self.module, 'FnOAnalysis') as analyse:
                self.module.main()
                analyse.assert_called_once()
                options = analyse.call_args.kwargs
                self.assertEqual(options['single_scrip'], 'WTI')
                self.assertIsNone(options['compare_with'])
                self.assertEqual(options['days'], expected_window)
                expected = str(self.module.CHARTS_DIR / filename) if filename else None
                self.assertEqual(options['pdf_path'], expected)

    def test_cli_preserves_default_and_pairwise_windows(self):
        cases = [
            ([], None, None, None, 'FnO_Analysis.pdf'),
            (['WTI'], 'WTI', None, None, 'WTI_Analysis.pdf'),
            (['WTI', 'US10Y'], 'WTI', 'US10Y', None, 'WTI_vs_US10Y_Analysis.pdf'),
            (['WTI', 'US10Y', '250d'], 'WTI', 'US10Y', self.module.ReportWindow('250d', last=250),
             'WTI_vs_US10Y_250d_Analysis.pdf'),
        ]
        for arguments, symbol, comparison, days, filename in cases:
            with self.subTest(arguments=arguments), \
                    patch.object(self.module.sys, 'argv', ['Option-OGN.py', '--pdf', *arguments]), \
                    patch.object(self.module, 'FnOAnalysis') as analyse:
                self.module.main()
                analyse.assert_called_once()
                options = analyse.call_args.kwargs
                self.assertEqual(options['single_scrip'], symbol)
                self.assertEqual(options['compare_with'], comparison)
                self.assertEqual(options['days'], days)
                self.assertEqual(options['pdf_path'], str(self.module.CHARTS_DIR / filename))

    def test_cli_single_symbol_window_keeps_custom_output_and_estimator(self):
        arguments = ['Option-OGN.py', '--pdf', 'custom.pdf', '--estimator', 'raw', 'WTI', '250d']
        with patch.object(self.module.sys, 'argv', arguments), \
                patch.object(self.module, 'FnOAnalysis') as analyse:
            self.module.main()
        analyse.assert_called_once()
        options = analyse.call_args.kwargs
        self.assertEqual(options['pdf_path'], 'custom.pdf')
        self.assertEqual(options['days'], self.module.ReportWindow('250d', last=250))
        self.assertEqual(options['estimator'], 'Raw')

    def test_cli_rejects_invalid_windows_and_single_symbol_comparison_options(self):
        cases = [
            (['WTI', '250'], 'Write the window as 250d'),
            (['WTI', '-250'], 'Write the window as 250d'),
            (['WTI', '0d'], 'observations must be positive'),
            (['WTI', '25d-350d'], 'the first count must exceed the second'),
            (['WTI', '25d-25d'], 'the first count must exceed the second'),
            (['WTI', 'Mar2026-Jan2026'], 'the months must run forward'),
            (['WTI', '--periods', '0'], '--periods must be positive'),
            (['WTI', '250d', '--periods', '250'], 'not both'),
            (['250d', 'WTI'], 'Give one window, after the symbols: 250d'),
            (['WTI', 'Jan2026', '250d'], 'Give one window, after the symbols: Jan2026'),
            (['250d'], 'requires a symbol'),
            (['WTI', '--compare-frequency', 'monthly'], 'require a second symbol'),
            (['WTI', '250d', '--compare-aggregation', 'last'], 'require a second symbol'),
        ]
        for arguments, message in cases:
            with self.subTest(arguments=arguments), \
                    patch.object(self.module.sys, 'argv', ['Option-OGN.py', *arguments]), \
                    patch.object(self.module, 'FnOAnalysis') as analyse, \
                    patch.object(self.module.sys, 'stdout', new_callable=io.StringIO) as output:
                self.module.main()
                analyse.assert_not_called()
                self.assertIn('[error]', output.getvalue())
                self.assertIn(message, output.getvalue())

    def test_report_windows_parse_and_select_trading_days_or_months(self):
        dates = pd.bdate_range('2025-12-01', '2026-03-31')
        frame = pd.DataFrame({'Close': np.arange(len(dates), dtype=float)}, index=dates)
        parse = self.module.parse_report_window
        self.assertEqual(parse('250d').select(frame).index.tolist(), dates.tolist())
        self.assertEqual(parse('10d').select(frame).index.tolist(), dates[-10:].tolist())
        excluded = parse('30d-5d').select(frame)
        self.assertEqual(excluded.index.tolist(), dates[-30:-5].tolist())
        self.assertEqual(parse('30d-5d').size, 25)
        january = parse('Jan2026').select(frame)
        self.assertEqual((january.index[0], january.index[-1]), (pd.Timestamp('2026-01-01'), pd.Timestamp('2026-01-30')))
        quarter = parse('jan2026-february2026').select(frame['Close'])
        self.assertEqual((quarter.index[0], quarter.index[-1]), (pd.Timestamp('2026-01-01'), pd.Timestamp('2026-02-27')))
        self.assertTrue(parse('Jun2027').select(frame).empty)
        self.assertTrue(parse('400d-300d').select(frame).empty)
        for text in ('NIFTY', 'US02Y__US10Y', 'ABC2026', 'GLD_SLV', '250'):
            self.assertIsNone(parse(text), text)
        self.assertEqual(self.module.as_report_window(72), self.module.ReportWindow('72d', last=72))
        self.assertEqual(self.module.as_report_window('350d-25d').skip, 25)
        with self.assertRaisesRegex(ValueError, 'Unknown window'):
            self.module.as_report_window('soon')

    def test_stamp_goes_before_the_suffix_and_never_overwrites(self):
        moment = datetime.datetime(2026, 10, 22, 18, 51, 49)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / 'NIFTY_Analysis.pdf'
            first = self.module.timestamped_path(base, moment)
            self.assertEqual(first.name, 'NIFTY_Analysis_20261022_185149.pdf')
            first.write_bytes(b'%PDF')
            self.assertEqual(self.module.timestamped_path(base, moment).name,
                             'NIFTY_Analysis_20261022_185149_2.pdf')

    def test_report_pdf_is_saved_under_a_timestamped_name(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(self.module, 'REPORT_SECTIONS', []), \
                patch.object(self.module, 'load_analysis_frame', side_effect=FileNotFoundError('offline')), \
                patch.object(self.module, 'PdfPages') as document:
            saved = self.module.FnOAnalysis(single_scrip='NIFTY',
                                            pdf_path=str(Path(directory) / 'NIFTY_Analysis.pdf'))
        self.assertRegex(Path(saved).name, r'^NIFTY_Analysis_\d{8}_\d{6}\.pdf$')
        self.assertEqual(Path(saved).parent, Path(directory))
        document.assert_called_once_with(saved)

    def test_standalone_comparison_pdf_is_timestamped(self):
        dates = pd.bdate_range('2024-01-01', periods=120)
        generator = np.random.default_rng(5)
        first = pd.Series(100 + generator.normal(size=120).cumsum(), index=dates)
        second = pd.Series(50 + generator.normal(size=120).cumsum(), index=dates)
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(self.module, 'resolve_comp_series',
                             side_effect=[(first, 'A', 'Test A'), (second, 'B', 'Test B')]), \
                patch.object(self.module, 'plot_comparison'), \
                patch.object(self.module, 'PdfPages') as document:
            self.module.compare_series('A', 'B', pdf_path=str(Path(directory) / 'COMP_A_vs_B.pdf'))
        self.assertRegex(Path(document.call_args.args[0]).name, r'^COMP_A_vs_B_\d{8}_\d{6}\.pdf$')

    def test_relative_pdf_names_are_saved_and_printed_as_full_paths(self):
        moment = datetime.datetime(2026, 10, 22, 18, 51, 49)
        self.assertEqual(self.module.timestamped_path('report.pdf', moment),
                         Path(os.path.abspath('report_20261022_185149.pdf')))
        with tempfile.TemporaryDirectory() as directory:
            try:
                relative = os.path.relpath(Path(directory) / 'NIFTY_Analysis.pdf')
            except ValueError:
                self.skipTest('The temporary folder is on another drive.')
            with patch.object(self.module, 'REPORT_SECTIONS', []), \
                    patch.object(self.module, 'load_analysis_frame', side_effect=FileNotFoundError('offline')), \
                    patch.object(self.module, 'PdfPages') as document, \
                    patch.object(self.module.sys, 'stdout', new_callable=io.StringIO) as output:
                saved = self.module.FnOAnalysis(single_scrip='NIFTY', pdf_path=relative)
        self.assertEqual(Path(saved).parent, Path(directory))
        document.assert_called_once_with(saved)
        self.assertIn(f'Saving charts to: {saved}', output.getvalue())
        self.assertIn(f'PDF saved: {saved}', output.getvalue())


class ParquetListTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import matplotlib
        matplotlib.use('Agg')
        spec = importlib.util.spec_from_file_location(
            'ogn_parquet_list_test', Path(__file__).with_name('Option-OGN.py'))
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        today = datetime.date.today()
        self.source = self.root / 'ABB.parquet'
        pd.DataFrame({'Date': [today - datetime.timedelta(days=3), today + datetime.timedelta(days=30), today],
                      'Symbol': ['OLDEST', 'FUTURE', 'TODAY'], 'Close': [10.5, 12.0, 11.25]}).to_parquet(
            self.source, index=False)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *arguments):
        with patch.object(self.module.sys, 'argv', ['Option-OGN.py', *arguments]), \
                patch.object(self.module, 'CHARTS_DIR', self.root / 'charts'), \
                patch.object(self.module, 'FnOAnalysis') as analyse, \
                patch.object(self.module.sys, 'stdout', new_callable=io.StringIO) as output:
            self.module.main()
        analyse.assert_not_called()
        return output.getvalue()

    def test_list_prints_latest_rows_by_date_with_the_full_file_path(self):
        try:
            relative = os.path.relpath(self.source)
        except ValueError:
            self.skipTest('The temporary folder is on another drive.')
        output = self.run_cli('List', relative, '2')
        self.assertIn(f'File: {os.path.abspath(relative)}', output)
        self.assertIn('Rows: 3 | Columns: 3 | Showing the latest 2 by Date', output)
        self.assertIn('[warning] 1 of these rows is dated after today', output)
        rows = [line.split()[2] for line in output.splitlines() if line.strip()[:1].isdigit()]
        self.assertEqual(rows, ['TODAY', 'FUTURE'])
        self.assertNotIn('OLDEST', output)
        self.assertNotIn('PDF saved', output)
        self.assertFalse((self.root / 'charts').exists())

    def test_list_pdf_is_timestamped_and_its_full_path_printed(self):
        for arguments in (['--pdf', 'List', str(self.source), '2'], ['List', str(self.source), '2', '--pdf']):
            with self.subTest(arguments=arguments):
                output = self.run_cli(*arguments)
                saved = Path(re.search(r'PDF saved: (.+\.pdf)', output).group(1))
                self.assertEqual(saved.parent, self.root / 'charts')
                self.assertRegex(saved.name, r'^ABB_latest2_rows_\d{8}_\d{6}(_\d+)?\.pdf$')
                self.assertTrue(saved.read_bytes().startswith(b'%PDF'))
        custom = self.root / 'listings' / 'abb.pdf'
        output = self.run_cli('--pdf', 'List', str(self.source), str(custom))
        self.assertIn('Showing the latest 3 by Date', output)
        saved = Path(re.search(r'PDF saved: (.+\.pdf)', output).group(1))
        self.assertEqual(saved.parent, custom.parent)
        self.assertRegex(saved.name, r'^abb_\d{8}_\d{6}\.pdf$')
        self.assertTrue(saved.is_file())

    def test_list_reports_usage_and_errors_without_writing(self):
        missing = self.root / 'missing.parquet'
        cases = [
            (['List'], 'Usage: python Option-OGN.py [--pdf] List'),
            (['List', str(self.source), str(self.source)], 'Usage:'),
            (['List', str(self.source), '2', '3'], 'Usage:'),
            (['List', str(self.source), '--rows', '2'], 'Usage:'),
            (['--pdf', 'List', str(self.source), '0'], 'rows must be positive'),
            (['List', str(self.source), 'abb.pdf'], 'Add --pdf to save the listing as abb.pdf'),
            (['--pdf', 'List', str(missing)], f'No such file: {missing}'),
            (['List', str(self.root)], 'is a folder'),
        ]
        for arguments, message in cases:
            with self.subTest(arguments=arguments):
                self.assertIn(message, self.run_cli(*arguments))
        self.assertFalse((self.root / 'charts').exists())

    def test_list_uses_nse_reference_dates_for_derivatives_files(self):
        source = self.root / 'FO.parquet'
        pd.DataFrame({'Date': [datetime.date(2026, 10, 9), datetime.date(2026, 12, 10)],
                      'BizDt': ['2026-10-09', '2026-10-12'], 'Symbol': ['OLDER', 'LATEST']}).to_parquet(
            source, index=False)
        output = self.run_cli('List', str(source), '1')
        self.assertIn('Showing the latest 1 by Date (2026-10-12 to 2026-10-12)', output)
        self.assertIn('Corrected from NSE reference dates: Date from BizDt in 1 of these rows.', output)
        self.assertNotIn('[warning]', output)
        self.assertIn('LATEST', output)
        self.assertNotIn('OLDER', output)

    def test_pdf_pages_repeat_column_block_headers(self):
        pages = self.module._listing_pages(['H1', 'a', 'b', 'c', 'd', '', 'H2', 'e'], 4)
        self.assertEqual(pages, [['H1', 'a', 'b', 'c'], ['H1', 'd', ''], ['H2', 'e']])

    def test_long_wide_listing_fits_every_pdf_page(self):
        frame = pd.DataFrame({f'Column {number:02d}': np.arange(150) * number + 0.5 for number in range(30)})
        dates = pd.date_range('2025-01-01', periods=150).date
        frame.insert(0, 'Date', dates)
        frame.insert(1, 'BizDt', [day.isoformat() for day in dates])
        frame.loc[148, 'Date'] = datetime.date(2025, 1, 2)  # stored day-first; BizDt corrects it
        frame.loc[149, ['Date', 'BizDt']] = [datetime.date.today() + datetime.timedelta(days=30), None]
        source = self.root / 'wide.parquet'
        frame.to_parquet(source, index=False)
        latest, total, order = self.module.latest_parquet_rows(source, 150)
        summary = self.module._listing_summary(source, latest, total, order)
        self.assertEqual(len(summary), 5)  # every optional header line, the tallest layout
        with patch.object(self.module, 'PdfPages') as document:
            saved = self.module.plot_listing(summary, latest, source, str(self.root / 'wide.pdf'))
        figures = [call.args[0] for call in document.return_value.savefig.call_args_list]
        self.assertGreater(len(figures), 3)
        self.assertRegex(Path(saved).name, r'^wide_\d{8}_\d{6}\.pdf$')
        document.return_value.close.assert_called_once()
        for figure in figures:
            figure.canvas.draw()
            renderer = figure.canvas.get_renderer()
            boxes = [text.get_window_extent(renderer) for text in figure.texts if text.get_text()]
            for box in boxes:
                self.assertGreaterEqual(box.x0, 0)
                self.assertLessEqual(box.x1, figure.bbox.x1)
                self.assertGreaterEqual(box.y0, 0)
                self.assertLessEqual(box.y1, figure.bbox.y1)
            for first, second in itertools.combinations(boxes, 2):
                self.assertFalse(first.overlaps(second))
        self.assertFalse(self.module.plt.get_fignums())


class MaxPainPageTests(unittest.TestCase):
    STRIKES = [90, 95, 100, 105, 110]

    @classmethod
    def setUpClass(cls):
        import matplotlib
        matplotlib.use('Agg')
        spec = importlib.util.spec_from_file_location(
            'ogn_max_pain_test', Path(__file__).with_name('Option-OGN.py'))
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    @classmethod
    def chain(cls, day, expiry, call_oi, put_oi, spot=101.0, contracts=(8.0, 6.0)):
        rows = [{'Date': pd.Timestamp(day), 'Expiry': pd.Timestamp(expiry), 'Instrument': 'OPTSTK',
                 'Option type': side, 'Strike Price': float(strike), 'Open Int': float(oi),
                 'Contracts': traded, 'Underlying Price': spot}
                for side, values, traded in (('CE', call_oi, contracts[0]), ('PE', put_oi, contracts[1]))
                for strike, oi in zip(cls.STRIKES, values)]
        return pd.DataFrame(rows)

    def positioning(self, frame, as_of='2026-01-31'):
        def stored(symbol, start=None, end=None):
            return frame[(frame['Date'] >= start) & (frame['Date'] <= end)].reset_index(drop=True)
        loader = Mock(side_effect=stored)
        with patch.object(self.module, 'load_derivatives', loader):
            return self.module.option_positioning('ABB', as_of), loader

    def sample(self):
        return pd.concat([
            self.chain('2026-01-29', '2026-02-24', [1] * 5, [1] * 5),        # an older day
            self.chain('2026-01-30', '2026-01-27', [99] * 5, [99] * 5),      # expired, still listed
            self.chain('2026-01-30', '2026-02-24', [5, 10, 20, 40, 30], [60, 40, 20, 10, 10]),
            self.chain('2026-01-30', '2026-03-30', [10] * 5, [30] * 5),      # a later expiry
            self.chain('2026-02-02', '2026-02-24', [7] * 5, [7] * 5),        # after the range
            pd.DataFrame({'Date': [pd.Timestamp('2026-01-30')], 'Expiry': [pd.Timestamp('2026-02-24')],
                          'Instrument': ['FUTSTK'], 'Option type': ['XX'], 'Open Int': [5000.0]}),
        ], ignore_index=True)

    def test_curve_matches_writer_payout_and_the_previous_max_pain(self):
        calls = pd.DataFrame({'Strike Price': self.STRIKES, 'Open Int': [5, 10, 20, 40, 30]})
        puts = pd.DataFrame({'Strike Price': self.STRIKES, 'Open Int': [30, 35, 25, 10, 5]})
        curve = self.module.max_pain_curve(
            pd.concat([calls, pd.DataFrame({'Strike Price': [np.nan], 'Open Int': [999]})]), puts)
        # Settling at 100: calls struck at 90 and 95 pay 5 x 10 + 10 x 5; puts at 105 and 110 the same.
        self.assertEqual(curve.loc[100.0].tolist(), [100.0, 100.0, 200.0])
        expected = {float(s): float(sum(oi * max(s - k, 0) for k, oi in zip(self.STRIKES, calls['Open Int']))
                                    + sum(oi * max(k - s, 0) for k, oi in zip(self.STRIKES, puts['Open Int'])))
                    for s in self.STRIKES}
        self.assertEqual(curve['Total'].to_dict(), expected)
        self.assertEqual(self.module.max_pain_strike(calls, puts), 100.0)
        self.assertTrue(np.isnan(self.module.max_pain_strike(calls.iloc[:0], puts.iloc[:0])))

    def test_positioning_uses_the_latest_options_and_nearest_unexpired_expiry(self):
        positioning, loader = self.positioning(self.sample())
        self.assertEqual(loader.call_args.kwargs, {'start': '2025-12-31', 'end': '2026-01-31'})
        self.assertEqual((positioning['date'], positioning['expiry'], positioning['as_of']),
                         (pd.Timestamp('2026-01-30'), pd.Timestamp('2026-02-24'), pd.Timestamp('2026-01-31')))
        self.assertEqual((positioning['max_pain'], positioning['spot']), (100.0, 101.0))
        self.assertEqual((positioning['call_oi'], positioning['put_oi']), (105.0, 140.0))
        self.assertAlmostEqual(positioning['pcr'], 140 / 105)
        self.assertAlmostEqual(positioning['pcr_all'], 290 / 155)
        self.assertAlmostEqual(positioning['pcr_volume'], 30 / 40)

    def test_positioning_explains_missing_options_or_open_interest(self):
        sample = self.sample()
        with self.assertRaisesRegex(ValueError, 'no ABB options in the month to 31 Dec 2025'):
            self.positioning(sample, as_of='2025-12-31')
        idle = self.chain('2026-01-30', '2026-02-24', [0] * 5, [0] * 5)
        with self.assertRaisesRegex(ValueError, 'no open interest'):
            self.positioning(idle)
        with patch.object(self.module, 'load_derivatives', side_effect=FileNotFoundError('none')), \
                patch.object(self.module, 'plot_max_pain') as plot, \
                patch.object(self.module.sys, 'stdout', new_callable=io.StringIO) as output:
            self.assertIsNone(self.module.max_pain_analysis('WTI', '2026-01-30'))
        plot.assert_not_called()
        self.assertIn('No stored derivatives for WTI', output.getvalue())

    def test_page_marks_max_pain_spot_and_a_pcr_gauge(self):
        positioning, _ = self.positioning(self.sample())
        document = Mock()
        self.module.plot_max_pain(positioning, 'ABB', pdf_pages=document)
        figure = document.savefig.call_args.args[0]
        chart, gauge = figure.axes
        self.assertEqual(len(chart.patches), 2 * len(self.STRIKES))
        self.assertEqual([text.get_text() for text in chart.get_legend().get_texts()], ['Call pain', 'Put pain'])
        self.assertEqual({'Max pain 100', 'Spot 101.00'}, {text.get_text() for text in chart.texts})
        gauge_texts = {text.get_text() for text in gauge.texts}
        self.assertTrue({'CALLS', 'PUTS', 'PCR 1.33', 'Put OI 140   /   Call OI 105',
                         'All expiries 1.87   |   Volume 0.75'} <= gauge_texts)
        needle = next(patch for patch in gauge.patches if isinstance(patch, self.module.matplotlib.patches.Polygon))
        tip = needle.get_xy()[0]
        self.assertAlmostEqual(np.degrees(np.arctan2(tip[1], tip[0])), 180 * (1 - (140 / 105) / (1 + 140 / 105)))
        figure.canvas.draw()
        renderer = figure.canvas.get_renderer()
        titles = [chart.title, gauge.title, *figure.texts]
        boxes = [text.get_window_extent(renderer) for text in titles if text.get_text()]
        for box in boxes:
            self.assertTrue(figure.bbox.x0 <= box.x0 and box.x1 <= figure.bbox.x1)
            self.assertTrue(figure.bbox.y0 <= box.y0 and box.y1 <= figure.bbox.y1)
        for first, second in itertools.combinations(boxes, 2):
            self.assertFalse(first.overlaps(second))
        self.assertFalse(self.module.plt.get_fignums())

    def test_wide_chains_draw_strikes_around_max_pain_and_spot(self):
        curve = pd.DataFrame({'Total': np.arange(100.0)}, index=pd.Index(np.arange(100.0) * 50, name='Strike'))
        window = self.module._max_pain_window
        shown = window(curve, 2500.0, 3000.0).index
        self.assertEqual(len(shown), self.module.MAX_PAIN_STRIKES)
        self.assertTrue(2500.0 in shown and 3000.0 in shown)
        self.assertEqual(window(curve, 100.0, 4900.0).index[0], 0.0)
        self.assertEqual(len(window(curve.iloc[:10], 100.0, 200.0)), 10)


if __name__ == '__main__':
    unittest.main()
