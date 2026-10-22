"""Checks the report range, its command-line overrides and which pages are drawn."""

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import matplotlib
matplotlib.use('Agg')
import numpy as np
import pandas as pd

import option_overlay

START = pd.Timestamp('2026-03-02')


def load_report_module():
    spec = importlib.util.spec_from_file_location('ogn_report_scope_test', Path(__file__).with_name('Option-OGN.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prices(periods=400, end='2026-09-04'):
    dates = pd.bdate_range(end=end, periods=periods)
    close = 400 + np.random.default_rng(3).normal(0, 3, len(dates)).cumsum()
    return pd.DataFrame({'Date': dates, 'Open': close - 1, 'High': close + 2, 'Low': close - 2,
                         'Close': close, 'Volume': 1000.0})


class ReportRangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_report_module()

    def test_range_helpers(self):
        module = self.module
        self.assertEqual(module.REPORT_YEARS, 1)
        self.assertEqual(module.report_start(1, today='2026-10-22 15:30'), pd.Timestamp('2025-10-22'))
        self.assertEqual(module.report_start(0.5, today='2026-10-22'), pd.Timestamp('2026-04-22'))
        self.assertEqual([module.report_range_label(years) for years in (1, 3, 0.5, 1.5, 1 / 12)],
                         ['1 year', '3 years', '6 months', '18 months', '1 month'])
        self.assertEqual([module._report_range_suffix(years) for years in (1, 3, 0.5)], ['', '_3y', '_6m'])
        with self.assertRaisesRegex(ValueError, 'at least one month'):
            module.report_start(0.01)

    def run_report(self, *, derivatives=True, **options):
        """FnOAnalysis with every page builder replaced by a mock; returns the mocks."""
        module = self.module
        names = ['plot_chart', 'trendline_analysis', 'volatility_analysis', 'compare_series',
                 'plot_japan_macro', 'plot_schiller_macro', 'plot_india_schiller']
        frame = prices()
        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            if derivatives:
                (Path(directory) / 'TEST.parquet').touch()
            stack.enter_context(patch.object(module, 'DERIVATIVES_PROCESSED', Path(directory)))
            stack.enter_context(patch.object(module, 'report_start', return_value=START))
            stack.enter_context(patch.object(module, 'load_analysis_frame', return_value=(frame.copy(), 'test')))
            stack.enter_context(patch.object(module, 'PdfPages'))
            mocks = {name: stack.enter_context(patch.object(module, name)) for name in names}
            module.FnOAnalysis(single_scrip='TEST', compare_with='OTHER',
                               pdf_path=str(Path(directory) / 'report.pdf'), **options)
        mocks['output'] = output.getvalue()
        mocks['frame'] = frame
        return mocks

    def test_every_page_defaults_to_the_report_range(self):
        mocks = self.run_report()
        frame = mocks['frame']
        in_range = int((frame['Date'] >= START).sum())
        indicators, bars = mocks['plot_chart'].call_args.args[:2]
        self.assertEqual(bars, in_range)
        self.assertEqual(len(indicators), len(frame))   # indicators keep their warm-up history
        trend_prices = mocks['trendline_analysis'].call_args.args[0]
        self.assertEqual(trend_prices.index.min(), START)
        self.assertIsNone(mocks['trendline_analysis'].call_args.kwargs['bars'])
        volatility = mocks['volatility_analysis'].call_args
        self.assertEqual(len(volatility.args[0]), len(frame))
        self.assertEqual(volatility.kwargs['start'], START)
        comparison = mocks['compare_series'].call_args.kwargs
        self.assertEqual((comparison['days'], comparison['start']), (None, START))
        for name in ('plot_japan_macro', 'plot_schiller_macro', 'plot_india_schiller'):
            self.assertEqual(mocks[name].call_args.kwargs['years'], 1)

    def test_command_line_overrides_win(self):
        mocks = self.run_report(days=120, trend_bars=60, years=3)
        trend = mocks['trendline_analysis'].call_args
        self.assertEqual(len(trend.args[0]), len(mocks['frame']))
        self.assertEqual(trend.kwargs['bars'], 60)
        comparison = mocks['compare_series'].call_args.kwargs
        self.assertEqual((comparison['days'], comparison['start']), (120, None))
        self.assertEqual(mocks['plot_japan_macro'].call_args.kwargs['years'], 3)

    def test_volatility_page_needs_a_derivatives_file(self):
        mocks = self.run_report(derivatives=False)
        mocks['volatility_analysis'].assert_not_called()
        self.assertIn('TEST has no derivatives file', mocks['output'])
        mocks['plot_chart'].assert_called_once()

    def test_symbol_without_data_in_range_draws_no_symbol_pages(self):
        module = self.module
        stale = prices(end='2024-06-28')
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(module, 'REPORT_SECTIONS', ['technical', 'trendlines', 'volatility']), \
                patch.object(module, 'DERIVATIVES_PROCESSED', Path(directory)), \
                patch.object(module, 'report_start', return_value=START), \
                patch.object(module, 'load_analysis_frame', return_value=(stale, 'test')), \
                patch.object(module, 'PdfPages') as document, \
                patch.object(module, 'plot_chart') as chart, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            (Path(directory) / 'TEST.parquet').touch()
            module.FnOAnalysis(single_scrip='TEST', pdf_path=str(Path(directory) / 'report.pdf'))
        chart.assert_not_called()
        document.return_value.savefig.assert_not_called()
        self.assertIn('No TEST observations since 2026-03-02', output.getvalue())
        self.assertIn('[trendlines skipped]', output.getvalue())
        self.assertIn('page left out', output.getvalue())

    def test_years_flag_reaches_the_report_and_names_the_pdf(self):
        module = self.module
        for argument, years, name in (('3', 3.0, 'WTI_3y_Analysis.pdf'), ('0.5', 0.5, 'WTI_6m_Analysis.pdf')):
            with patch.object(module.sys, 'argv', ['Option-OGN.py', '--pdf', '--years', argument, 'WTI']), \
                    patch.object(module, 'FnOAnalysis') as analyse, contextlib.redirect_stdout(io.StringIO()):
                module.main()
            options = analyse.call_args.kwargs
            self.assertEqual(options['years'], years)
            self.assertIsNone(options['trend_bars'])
            self.assertEqual(Path(options['pdf_path']).name, name)
        with patch.object(module.sys, 'argv', ['Option-OGN.py', '--pdf', 'WTI']), \
                patch.object(module, 'FnOAnalysis') as analyse, contextlib.redirect_stdout(io.StringIO()):
            module.main()
        self.assertEqual(analyse.call_args.kwargs['years'], 1)
        self.assertEqual(Path(analyse.call_args.kwargs['pdf_path']).name, 'WTI_Analysis.pdf')
        for bad in ('0', '0.01', 'x'):
            with patch.object(module.sys, 'argv', ['Option-OGN.py', '--years', bad, 'WTI']), \
                    patch.object(module, 'FnOAnalysis') as analyse, \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                module.main()
            analyse.assert_not_called()
            self.assertIn('[error]', output.getvalue())


class RangeComputationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_report_module()

    def test_volatility_profile_keeps_only_values_in_range(self):
        price_data = prices().set_index('Date')
        full = self.module.compute_volatility_profile(price_data, 'YangZhang')
        ranged = self.module.compute_volatility_profile(price_data, 'YangZhang', start=START)
        self.assertEqual(ranged['rolling'].index.min(), START)
        pd.testing.assert_series_equal(ranged['rolling'], full['rolling'][full['rolling'].index >= START])
        self.assertTrue(all(series.index.min() >= START for series in ranged['cone']['series']))
        self.assertEqual(ranged['cone']['windows'], full['cone']['windows'])   # 90-day window still filled
        self.assertEqual(ranged['start'], START)
        self.assertIsNone(self.module.compute_volatility_profile(price_data, 'YangZhang',
                                                                 start=pd.Timestamp('2027-01-01')))

    def test_comparison_window_follows_start_unless_days_given(self):
        dates = pd.bdate_range(end='2026-09-04', periods=300)
        generator = np.random.default_rng(23)
        first = pd.Series(100 + generator.normal(size=300).cumsum(), index=dates)
        second = pd.Series(50 + generator.normal(size=300).cumsum(), index=dates)
        ranged = self.module.compute_comparison(first, second, 'A', 'B', start=START)
        self.assertEqual(ranged['aligned'].index.min(), START)
        self.assertEqual(ranged['window_start'], START)
        self.assertIn('since 02-Mar-2026', self.module._comp_window_note(ranged))
        counted = self.module.compute_comparison(first, second, 'A', 'B', days=50, start=START)
        self.assertEqual(len(counted['aligned']), 50)
        self.assertIsNone(counted['window_start'])
        with self.assertRaisesRegex(ValueError, 'since 2027-01-01'):
            self.module.compute_comparison(first, second, 'A', 'B', start=pd.Timestamp('2027-01-01'))

    def test_realized_benchmarks_use_values_in_range(self):
        history = prices().set_index('Date')
        points = pd.DataFrame({'Date': [history.index[-1]], 'Tenor sessions': [10], 'IV': [0.2]})
        estimator = lambda available, tenor: self.module.get_volatility_estimator(available, 'YangZhang', tenor)
        full = option_overlay.attach_realized_benchmarks(points, history, estimator)
        ranged = option_overlay.attach_realized_benchmarks(points, history, estimator, start=START)
        expected = estimator(history, 10)
        expected = expected[np.isfinite(expected) & (expected >= 0) & (expected.index >= START)]
        self.assertEqual(int(ranged['RV count'].iloc[0]), len(expected))
        self.assertLess(int(ranged['RV count'].iloc[0]), int(full['RV count'].iloc[0]))
        self.assertAlmostEqual(ranged['RV mean'].iloc[0], expected.mean())


if __name__ == '__main__':
    unittest.main()
