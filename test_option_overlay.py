"""Focused tests for option volume selection, IV diagnostics and chart overlays."""

import unittest
import importlib.util
from pathlib import Path
from unittest.mock import patch
from unittest.mock import Mock

import numpy as np
import pandas as pd

import option_overlay as overlay
from vollib.black import black


class OptionSelectionTests(unittest.TestCase):
    def chain(self, count=17):
        strikes = np.linspace(21000, 27000, count)
        coordinate = np.log(strikes / 24000)
        implied = 0.20 - 0.08 * coordinate + 0.30 * coordinate ** 2
        implied += np.sin(np.arange(count)) * 0.001
        return pd.DataFrame({
            'Date': pd.Timestamp('2026-09-01'), 'Expiry': pd.Timestamp('2026-09-22'),
            'Symbol': 'NIFTY', 'Option type': 'CE', 'Strike Price': strikes,
            'Contracts': np.arange(count, 0, -1) * 100, 'IV': implied,
        })

    def test_five_each_side_expiry_and_trading_date(self):
        chain = pd.concat([
            self.chain(8).assign(**{'Date': date, 'Expiry': expiry, 'Option type': side})
            for date in pd.to_datetime(['2026-09-01', '2026-09-02'])
            for expiry in pd.to_datetime(['2026-09-22', '2026-10-27'])
            for side in ['CE', 'PE']
        ], ignore_index=True)
        result = overlay.select_option_points(chain, outlier_count=0)
        self.assertEqual(len(result), 40)
        self.assertTrue(result.groupby(['Date', 'Expiry', 'Option type']).size().eq(5).all())
        self.assertTrue(result['Contracts'].ge(400).all())

    def test_extra_outlier_comes_from_full_chain_not_just_top_five(self):
        chain = self.chain()
        chain.loc[10, 'IV'] += 0.17
        result = overlay.select_option_points(chain)
        extra = result[result['Selection'] == 'MAD outlier']
        self.assertEqual(len(extra), 1)
        self.assertEqual(extra['Strike Price'].iloc[0], chain.loc[10, 'Strike Price'])
        self.assertGreaterEqual(extra['MAD score'].iloc[0], 3.5)
        self.assertEqual(result['Selection'].eq('Top volume').sum(), 5)
        self.assertFalse(result.duplicated(['Date', 'Expiry', 'Option type', 'Strike Price']).any())

    def test_normal_smile_does_not_create_forced_outliers(self):
        result = overlay.select_option_points(self.chain())
        self.assertEqual(len(result), 5)
        self.assertFalse(result['Is outlier'].any())

    def test_sparse_chain_and_extreme_endpoint_are_not_scored_as_outliers(self):
        sparse = overlay.select_option_points(self.chain(8))
        self.assertTrue(sparse['MAD score'].isna().all())
        chain = self.chain()
        chain.loc[len(chain) - 1, 'IV'] += 0.50
        scored = overlay.score_option_smile(chain)
        self.assertFalse(scored['Smile supported'].iloc[-1])

    def test_bad_expired_illiquid_and_duplicate_rows_are_excluded(self):
        chain = self.chain(8)
        chain.loc[0, 'Contracts'] = 0
        chain.loc[1, 'IV'] = np.nan
        chain.loc[2, 'Expiry'] = chain.loc[2, 'Date']
        chain.loc[3, 'Option type'] = 'XX'
        chain.loc[4, 'Strike Price'] = -1
        duplicate = chain.iloc[[5]].assign(Contracts=9999)
        result = overlay.select_option_points(pd.concat([chain, duplicate], ignore_index=True), outlier_count=0)
        self.assertEqual(len(result), 3)
        self.assertEqual(result['Contracts'].iloc[0], 9999)

    def test_labels_use_strike_and_short_expiry(self):
        label = overlay.option_point_label({'Strike Price': 24500, 'Expiry': '2026-09-22'})
        self.assertEqual(label, '(24500, 22 Sep)')

    def test_no_foreign_tickers_in_selection(self):
        chain = self.chain(8)
        chain.loc[0, 'Symbol'] = 'BANKNIFTY'
        with self.assertRaisesRegex(ValueError, 'one underlying'):
            overlay.select_option_points(chain)


class OptionBenchmarkTests(unittest.TestCase):
    def test_baseline_uses_exact_tenor_and_no_future_prices(self):
        dates = pd.bdate_range('2024-01-01', periods=100)
        prices = pd.DataFrame({'Close': np.arange(100)}, index=dates)
        points = pd.DataFrame({
            'Date': [dates[60], dates[60], dates[80]], 'Tenor sessions': [10, 10, 5],
            'IV': [0.3, 0.2, 0.25],
        })
        calls = []
        def estimator(history, window):
            calls.append((history.index.max(), window, len(history)))
            return pd.Series(0.15, index=history.index[window:])
        result = overlay.attach_realized_benchmarks(points, prices, estimator)
        self.assertEqual(calls, [(dates[60], 10, 61), (dates[80], 5, 81)])
        np.testing.assert_allclose(result['RV mean'], [0.15, 0.15, 0.15])
        np.testing.assert_allclose(result['IV minus RV'], [0.15, 0.05, 0.10])
        self.assertEqual(result['RV count'].tolist(), [51, 51, 76])

    def test_too_short_or_expiry_day_baseline_is_unavailable(self):
        dates = pd.bdate_range('2024-01-01', periods=40)
        prices = pd.DataFrame({'Close': 100}, index=dates)
        points = pd.DataFrame({'Date': [dates[-1], dates[-1]], 'Tenor sessions': [1, 35], 'IV': [0.3, 0.4]})
        with patch.object(overlay, 'score_option_smile'):
            result = overlay.attach_realized_benchmarks(points, prices, lambda history, window: pd.Series(dtype=float))
        self.assertTrue(result['RV mean'].isna().all())
        self.assertTrue(result['RV count'].eq(0).all())


class OptionIVTests(unittest.TestCase):
    def derivatives(self):
        rows = []
        date = pd.Timestamp('2026-09-01')
        expiry = pd.Timestamp('2026-09-22')
        for side, flag in [('CE', 'c'), ('PE', 'p')]:
            premium = black(flag, 24500.0, 24500.0, 21 / 365, 0.065, 0.20)
            rows.append({'Date': date, 'Expiry': expiry, 'Symbol': 'NIFTY', 'Instrument': 'IDO',
                         'Option type': side, 'Strike Price': 24500, 'Contracts': 100,
                         'Settle Price': premium, 'Close': premium})
        rows.append({'Date': date, 'Expiry': expiry, 'Symbol': 'NIFTY', 'Instrument': 'IDF',
                     'Option type': 'XX', 'Strike Price': 0, 'Contracts': 100,
                     'Settle Price': 24500.0, 'Close': 24500.0})
        return pd.DataFrame(rows)

    def test_black76_iv_is_recovered_from_matched_settlement_prices(self):
        frame, diagnostic = overlay.prepare_option_iv(self.derivatives(), 'NIFTY', ['2026-09-01'])
        np.testing.assert_allclose(frame['IV'], [0.20, 0.20], atol=1e-10)
        self.assertTrue(frame['IV source'].eq('Black-76 estimate').all())
        self.assertTrue(frame['Price basis'].eq('Settlement').all())
        self.assertEqual(diagnostic['estimated_iv'], 2)
        self.assertEqual(frame['Tenor sessions'].tolist(), [15, 15])

    def test_reported_iv_takes_precedence_and_does_not_require_a_future(self):
        derivatives = self.derivatives().iloc[:2].assign(**{'Implied Volatility': ['22%', '23%']})
        with patch.object(overlay, 'implied_volatility') as solver:
            frame, diagnostic = overlay.prepare_option_iv(derivatives, 'NIFTY', ['2026-09-01'])
        solver.assert_not_called()
        np.testing.assert_allclose(frame['IV'], [0.22, 0.23])
        self.assertEqual(diagnostic['reported_iv'], 2)

    def test_missing_iv_requires_exact_future_date_expiry_and_ticker(self):
        for column, value in [('Date', pd.Timestamp('2026-08-31')),
                               ('Expiry', pd.Timestamp('2026-10-27')), ('Symbol', 'BANKNIFTY')]:
            with self.subTest(column=column):
                derivatives = self.derivatives()
                derivatives.loc[2, column] = value
                frame, diagnostic = overlay.prepare_option_iv(derivatives, 'NIFTY', ['2026-09-01'])
                self.assertTrue(frame.empty)
                self.assertEqual(diagnostic['missing_forward'], 2)

    def test_invalid_prices_expiry_day_and_ambiguous_futures_are_rejected(self):
        derivatives = self.derivatives()
        derivatives.loc[0, 'Settle Price'] = 30000
        frame, diagnostic = overlay.prepare_option_iv(derivatives, 'NIFTY', ['2026-09-01'])
        self.assertEqual(len(frame), 1)
        self.assertEqual(diagnostic['invalid_premium'], 1)
        derivatives = self.derivatives()
        derivatives['Date'] = derivatives['Expiry']
        frame, _ = overlay.prepare_option_iv(derivatives, 'NIFTY', ['2026-09-22'])
        self.assertTrue(frame.empty)
        derivatives = pd.concat([self.derivatives(), self.derivatives().iloc[[2]].assign(Instrument='FUTIDX')])
        frame, diagnostic = overlay.prepare_option_iv(derivatives, 'NIFTY', ['2026-09-01'])
        self.assertTrue(frame.empty)
        self.assertEqual(diagnostic['ambiguous_futures'], 2)

    def test_explicit_decimal_units_and_matching_close_fallback(self):
        derivatives = self.derivatives().assign(**{'Settle Price': np.nan, 'IV': [0.25, np.nan, np.nan]})
        frame, _ = overlay.prepare_option_iv(derivatives, 'NIFTY', ['2026-09-01'], reported_iv_unit='decimal')
        np.testing.assert_allclose(frame['IV'], [0.25, 0.20], atol=1e-10)
        self.assertEqual(frame['Price basis'].iloc[1], 'Close')
        derivatives['IV'] = '25%'
        with self.assertRaisesRegex(ValueError, 'conflicts'):
            overlay.prepare_option_iv(derivatives, 'NIFTY', ['2026-09-01'], reported_iv_unit='decimal')

    def test_missing_solver_preserves_reported_iv(self):
        derivatives = self.derivatives().assign(IV=[25.0, np.nan, np.nan])
        with patch.object(overlay, 'implied_volatility', None):
            frame, diagnostic = overlay.prepare_option_iv(derivatives, 'NIFTY', ['2026-09-01'])
        self.assertEqual(len(frame), 1)
        self.assertTrue(diagnostic['solver_unavailable'])
        self.assertEqual(frame['IV source'].iloc[0], 'Reported')


class OptionPlotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import matplotlib
        matplotlib.use('Agg')

    def test_history_pages_show_sides_labels_and_outlier_outlines(self):
        import matplotlib.pyplot as plt
        fixture = OptionSelectionTests()
        frames = []
        for side in ['CE', 'PE']:
            for date in pd.to_datetime(['2026-09-01', '2026-09-02']):
                chain = fixture.chain().assign(**{'Option type': side, 'Date': date})
                chain.loc[10, 'IV'] += 0.17
                frames.append(chain)
        selected = overlay.select_option_points(pd.concat(frames, ignore_index=True))
        selected['IV source'] = 'Reported'
        selected['RV mean'] = 0.16
        selected['RV std'] = 0.02
        selected['IV minus RV'] = selected['IV'] - selected['RV mean']
        profile = {'points': selected, 'top_count': 5, 'outlier_count': 2,
                   'rate': 0.065, 'min_contracts': 10, 'estimator': 'YangZhang',
                   'diagnostics': {'reported_iv': len(selected), 'estimated_iv': 0,
                                   'missing_forward': 0, 'invalid_premium': 0, 'solver_failures': 0}}
        document = Mock()
        count = overlay.plot_option_history(profile, 'NIFTY', pdf_pages=document)
        self.assertEqual(count, 1)
        figure = document.savefig.call_args.args[0]
        calls, puts = figure.axes[:2]
        self.assertEqual(len(calls.texts), 12)
        self.assertEqual(len(puts.texts), 12)
        self.assertTrue(all('22 Sep)' in text.get_text() for text in calls.texts + puts.texts))
        self.assertIn('CE IV', [collection.get_label() for collection in calls.collections])
        self.assertIn('PE IV', [collection.get_label() for collection in puts.collections])
        self.assertIn('Smile MAD outlier', [collection.get_label() for collection in calls.collections])
        self.assertTrue(any('IV - mean (pp)' in cell.get_text().get_text()
                            for cell in figure.axes[2].tables[0].get_celld().values()))
        self.assertFalse(plt.get_fignums())

    def test_history_page_skips_weekends_and_holidays(self):
        fixture = OptionSelectionTests()
        dates = pd.to_datetime(['2026-08-28', '2026-08-31', '2026-09-02'])   # Fri, Mon, Wed (Tue holiday)
        frames = [fixture.chain().assign(**{'Date': date, 'Option type': side})
                  for date in dates for side in ['CE', 'PE']]
        selected = overlay.select_option_points(pd.concat(frames, ignore_index=True))
        selected['IV source'] = 'Reported'
        selected['RV mean'] = 0.16
        selected['RV std'] = 0.02
        selected['IV minus RV'] = selected['IV'] - selected['RV mean']
        profile = {'points': selected, 'top_count': 5, 'outlier_count': 2,
                   'rate': 0.065, 'min_contracts': 10, 'estimator': 'YangZhang',
                   'diagnostics': {'reported_iv': len(selected), 'estimated_iv': 0,
                                   'missing_forward': 0, 'invalid_premium': 0, 'solver_failures': 0}}
        document = Mock()
        overlay.plot_option_history(profile, 'NIFTY', pdf_pages=document)
        figure = document.savefig.call_args.args[0]
        figure.canvas.draw()
        for axes in figure.axes[:2]:
            realized = next(line for line in axes.get_lines() if line.get_label() == 'Historical realized mean')
            self.assertEqual(realized.get_xdata().tolist(), [0.0, 1.0, 2.0])
            markers = np.concatenate([collection.get_offsets()[:, 0] for collection in axes.collections
                                      if collection.get_label() in ('CE IV', 'PE IV')])
            self.assertEqual(sorted(set(markers)), [0.0, 1.0, 2.0])
            self.assertEqual([label.get_text() for label in axes.get_xticklabels()],
                             ['28 Aug', '31 Aug', '02 Sep'])

    def test_dense_five_date_labels_stay_inside_axes_without_overlaps(self):
        import matplotlib.pyplot as plt
        fixture = OptionSelectionTests()
        frames = []
        for date_index, date in enumerate(pd.bdate_range(end='2026-09-02', periods=5)):
            for side in ['CE', 'PE']:
                chain = fixture.chain().assign(**{'Date': date, 'Option type': side})
                chain['IV'] += date_index * 0.001 + (0.004 if side == 'PE' else 0)
                chain.loc[10, 'IV'] += 0.17
                chain.loc[7, 'IV'] -= 0.10
                frames.append(chain)
        points = overlay.select_option_points(pd.concat(frames, ignore_index=True))
        figure = plt.figure(figsize=(30, 17))
        try:
            for side, left in [('CE', 0.06), ('PE', 0.55)]:
                axes = figure.add_axes((left, 0.46, 0.40, 0.42))
                selected = points[points['Option type'].eq(side)]
                dates = selected['Date'].drop_duplicates().sort_values()
                axes.plot(dates, np.repeat(0.071, len(dates)), label='Historical realized mean')
                labels = overlay.plot_option_markers(axes, selected, 'Date')
                figure.canvas.draw()
                renderer = figure.canvas.get_renderer()
                bounds = [label.get_window_extent(renderer) for label in labels]
                self.assertEqual(len(bounds), 35)
                for position, box in enumerate(bounds):
                    self.assertGreaterEqual(box.x0, axes.bbox.x0 - 1)
                    self.assertLessEqual(box.x1, axes.bbox.x1 + 1)
                    self.assertGreaterEqual(box.y0, axes.bbox.y0 - 1)
                    self.assertLessEqual(box.y1, axes.bbox.y1 + 1)
                    for other in bounds[position + 1:]:
                        self.assertFalse(box.overlaps(other), f'{side} labels overlap')
        finally:
            plt.close(figure)


class OptionIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import matplotlib
        matplotlib.use('Agg')
        spec = importlib.util.spec_from_file_location('ogn_option_test', Path(__file__).with_name('Option-OGN.py'))
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def prices(self):
        dates = pd.bdate_range(end='2026-09-02', periods=300)
        generator = np.random.default_rng(89)
        close = 24500 + generator.normal(0, 80, len(dates)).cumsum()
        return pd.DataFrame({'Open': close - 5, 'High': close + 50, 'Low': close - 55,
                             'Close': close, 'Volume': 100}, index=dates)

    def test_loader_uses_all_expiries_and_attaches_historical_benchmarks(self):
        fixture = OptionSelectionTests()
        chain = pd.concat([
            fixture.chain().assign(**{'Date': date, 'Expiry': expiry, 'Option type': side,
                                      'IV': fixture.chain()['IV'] * 100})
            for date in pd.to_datetime(['2026-09-01', '2026-09-02'])
            for expiry in pd.to_datetime(['2026-09-22', '2026-10-27'])
            for side in ['CE', 'PE']
        ], ignore_index=True)
        with patch.object(self.module, 'load_derivatives', return_value=chain) as loader:
            profile = self.module.build_volatility_option_overlay(self.prices(), 'NIFTY', 'YangZhang', date_count=2)
        self.assertEqual(len(profile['points']), 40)
        self.assertEqual(profile['points']['Expiry'].nunique(), 2)
        self.assertTrue(profile['points']['RV count'].ge(30).all())
        loader.assert_called_once_with('NIFTY', start='2026-09-01', end='2026-09-02')

    def test_no_derivatives_or_nonvolatility_estimators_do_not_draw_options(self):
        with patch.object(self.module, 'load_derivatives', side_effect=FileNotFoundError):
            self.assertIsNone(self.module.build_volatility_option_overlay(self.prices(), 'NIFTY', 'YangZhang'))
        with patch.object(self.module, 'load_derivatives') as loader:
            self.assertIsNone(self.module.build_volatility_option_overlay(self.prices(), 'NIFTY', 'Skew'))
            loader.assert_not_called()

    def test_volatility_page_and_expiry_page_receive_overlay(self):
        derivatives = OptionIVTests().derivatives().assign(Date=pd.Timestamp('2026-09-02'))
        with patch.object(self.module, 'load_derivatives', return_value=derivatives), \
                patch.object(self.module, 'plot_volatility') as plot, \
                patch.object(overlay, 'plot_option_history') as history:
            result = self.module.volatility_analysis(self.prices(), 'NIFTY')
        self.assertIsNotNone(result['option_overlay'])
        self.assertIn(14, result['cone']['windows'])
        plot.assert_called_once()
        history.assert_called_once()

    def test_cli_exposes_explicit_pricing_and_selection_settings(self):
        arguments = ['Option-OGN.py', '--pdf', 'NIFTY', '--option-dates', '10',
                     '--option-min-contracts', '50', '--option-outliers', '0',
                     '--option-rate', '0.055', '--option-iv-unit', 'decimal']
        with patch.object(self.module.sys, 'argv', arguments), patch.object(self.module, 'FnOAnalysis') as analyse:
            self.module.main()
        parameters = analyse.call_args.kwargs
        self.assertEqual(parameters['option_dates'], 10)
        self.assertEqual(parameters['option_min_contracts'], 50)
        self.assertEqual(parameters['option_outliers'], 0)
        self.assertEqual(parameters['option_rate'], 0.055)
        self.assertEqual(parameters['option_iv_unit'], 'decimal')
        self.assertIsNone(parameters['days'])


if __name__ == '__main__':
    unittest.main()