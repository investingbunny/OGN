"""Focused tests for option volume selection, IV diagnostics and chart overlays."""

import math
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

    def test_mismatched_future_is_never_used_and_parity_forward_fills_in(self):
        for column, value in [('Date', pd.Timestamp('2026-08-31')),
                               ('Expiry', pd.Timestamp('2026-10-27')), ('Symbol', 'BANKNIFTY')]:
            with self.subTest(column=column):
                derivatives = self.derivatives()
                derivatives.loc[2, column] = value
                derivatives.loc[2, ['Settle Price', 'Close']] = 30000.0
                frame, diagnostic = overlay.prepare_option_iv(derivatives, 'NIFTY', ['2026-09-01'])
                np.testing.assert_allclose(frame['IV'], [0.20, 0.20], atol=1e-10)
                np.testing.assert_allclose(frame['Forward'], [24500.0, 24500.0])
                self.assertTrue(frame['IV source'].eq('Black-76 parity estimate').all())
                self.assertEqual(diagnostic['parity_iv'], 2)
                self.assertEqual(diagnostic['missing_forward'], 0)

    def test_without_a_future_or_a_call_put_pair_iv_is_unavailable(self):
        derivatives = self.derivatives().iloc[[0]]
        frame, diagnostic = overlay.prepare_option_iv(derivatives, 'NIFTY', ['2026-09-01'])
        self.assertTrue(frame.empty)
        self.assertEqual(diagnostic['missing_forward'], 1)
        self.assertEqual(diagnostic['parity_iv'], 0)

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
        pages = Mock()
        with patch.object(self.module, 'load_derivatives', return_value=derivatives), \
                patch.object(self.module, 'plot_volatility', pages.volatility), \
                patch.object(self.module, 'plot_volatility_guide', pages.guide), \
                patch.object(overlay, 'plot_option_history', pages.history):
            result = self.module.volatility_analysis(self.prices(), 'NIFTY')
        self.assertIsNotNone(result['option_overlay'])
        self.assertIn(14, result['cone']['windows'])
        self.assertEqual([call[0] for call in pages.mock_calls], ['volatility', 'guide', 'history'])
        with patch.object(self.module, 'REPORT_SECTIONS', ['volatility', 'option_overlay']), \
                patch.object(self.module, 'load_derivatives', return_value=derivatives), \
                patch.object(self.module, 'plot_volatility'), \
                patch.object(self.module, 'plot_volatility_guide') as guide, \
                patch.object(overlay, 'plot_option_history'):
            self.module.volatility_analysis(self.prices(), 'NIFTY')
        guide.assert_not_called()

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


class WeeklyExpiryTests(unittest.TestCase):
    """NIFTY-style listing as of 21 Oct 2026: the last listed expiry of each month is the monthly."""
    AS_OF = pd.Timestamp('2026-10-21')
    LISTED = pd.to_datetime(['2026-10-27', '2026-11-03', '2026-11-10', '2026-11-17', '2026-11-24',
                             '2026-12-01', '2026-12-29'])
    MONTHLY = pd.to_datetime(['2026-10-27', '2026-11-24', '2026-12-29'])

    @classmethod
    def setUpClass(cls):
        import matplotlib
        matplotlib.use('Agg')
        spec = importlib.util.spec_from_file_location('ogn_weekly_test', Path(__file__).with_name('Option-OGN.py'))
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def chain(self, dates, expiries, forward=24600.0, iv=0.15, spot=np.nan):
        """Black-76 calls and puts on a mild smile at one forward; futures only for monthly expiries."""
        rows = []
        for date in pd.to_datetime(dates):
            for expiry in expiries:
                lifetime = (expiry - date).days / 365
                for strike in np.arange(23600.0, 25700.0, 100.0):
                    smile = iv + 2.0 * math.log(strike / forward) ** 2 + 0.0005 * math.sin(strike / 100)
                    for side, flag in [('CE', 'c'), ('PE', 'p')]:
                        premium = black(flag, forward, strike, lifetime, 0.065, smile)
                        rows.append({'Date': date, 'Expiry': expiry, 'Symbol': 'NIFTY', 'Instrument': 'IDO',
                                     'Option type': side, 'Strike Price': strike,
                                     'Contracts': 2000 - abs(strike - forward), 'Settle Price': premium,
                                     'Close': premium, 'Underlying Price': spot, 'Model IV': smile})
                if expiry in self.MONTHLY:
                    rows.append({'Date': date, 'Expiry': expiry, 'Symbol': 'NIFTY', 'Instrument': 'IDF',
                                 'Option type': 'XX', 'Strike Price': 0, 'Contracts': 100,
                                 'Settle Price': forward, 'Close': forward, 'Underlying Price': spot})
        return pd.DataFrame(rows)

    def test_last_listed_expiry_of_each_month_is_monthly(self):
        kinds = overlay.classify_expiries(list(self.LISTED) + [self.LISTED[1], pd.Timestamp('2027-03-30')])
        monthly = kinds[kinds.eq('Monthly')].index.strftime('%d %b').tolist()
        self.assertEqual(monthly, ['27 Oct', '24 Nov', '29 Dec', '30 Mar'])
        self.assertEqual(kinds[kinds.eq('Weekly')].index.strftime('%d %b').tolist(),
                         ['03 Nov', '10 Nov', '17 Nov', '01 Dec'])

    def test_weekly_iv_uses_the_same_expiry_parity_forward(self):
        expiries = pd.to_datetime(['2026-10-27', '2026-11-03', '2026-11-24'])
        frame, diagnostic = overlay.prepare_option_iv(self.chain([self.AS_OF], expiries), 'NIFTY', [self.AS_OF])
        weekly = frame[frame['Expiry'].eq(expiries[1])]
        self.assertEqual(len(weekly), 42)
        np.testing.assert_allclose(weekly['IV'], weekly['Model IV'], atol=1e-6)
        np.testing.assert_allclose(weekly['Forward'], 24600.0, rtol=1e-9)
        self.assertTrue(weekly['IV source'].eq('Black-76 parity estimate').all())
        self.assertTrue(weekly['Expiry type'].eq('Weekly').all())
        monthly = frame[~frame['Expiry'].eq(expiries[1])]
        self.assertTrue(monthly['IV source'].eq('Black-76 estimate').all())
        self.assertTrue(monthly['Expiry type'].eq('Monthly').all())
        self.assertEqual(diagnostic['parity_iv'], 42)
        self.assertEqual(diagnostic['estimated_iv'], 126)

    def test_parity_forward_far_from_the_underlying_is_rejected(self):
        expiries = pd.to_datetime(['2026-10-27', '2026-11-03', '2026-11-24'])
        chain = self.chain([self.AS_OF], expiries, spot=30000.0)
        frame, diagnostic = overlay.prepare_option_iv(chain, 'NIFTY', [self.AS_OF])
        self.assertFalse(frame['Expiry'].eq(expiries[1]).any())
        self.assertEqual(diagnostic['missing_forward'], 42)
        self.assertEqual(diagnostic['parity_iv'], 0)

    def test_pages_cover_next_three_monthly_and_next_five_expiries(self):
        listed = list(self.LISTED) + [pd.Timestamp('2027-03-30')]
        kinds = overlay.classify_expiries(listed + [pd.Timestamp('2026-10-20')])
        points = pd.DataFrame({'Date': self.AS_OF, 'Expiry': listed})
        points = pd.concat([points, pd.DataFrame({'Date': [pd.Timestamp('2026-10-19')],
                                                  'Expiry': [pd.Timestamp('2026-10-20')]})])
        points['Expiry type'] = points['Expiry'].map(kinds)
        pages = overlay.select_report_expiries(points)
        self.assertEqual([f'{expiry:%d %b}' for expiry in pages],
                         ['27 Oct', '03 Nov', '10 Nov', '17 Nov', '24 Nov', '29 Dec'])
        monthly_only = points[points['Expiry type'].eq('Monthly')]
        self.assertEqual([f'{expiry:%d %b}' for expiry in overlay.select_report_expiries(monthly_only)],
                         ['27 Oct', '24 Nov', '29 Dec'])

    def test_one_liners_quote_latest_iv_against_realized(self):
        latest = pd.DataFrame({'Option type': ['CE', 'CE', 'PE'], 'IV': [0.14, 0.16, 0.18],
                               'RV mean': 0.17, 'IV minus RV': [-0.03, -0.01, 0.01],
                               'Selection': 'Top volume'})
        notes = overlay.option_page_notes(latest)
        self.assertTrue(all(note.startswith('How to use:') for note in notes.values()))
        self.assertIn('Now 15.0% vs 17.0% (-2.0 pp).', notes['CE'])
        self.assertIn('Now PE 18.0% vs CE 15.0%.', notes['PE'])
        self.assertIn('Now 1 of 3 top-volume contracts price above realized.', notes['table'])
        missing = overlay.option_page_notes(latest.assign(**{'RV mean': np.nan, 'IV minus RV': np.nan}))
        self.assertIn('no realized benchmark yet', missing['CE'])
        self.assertIn('realized benchmark unavailable', missing['table'])

    def test_overlay_pages_add_weekly_series_and_cone_keeps_monthly(self):
        import matplotlib.pyplot as plt
        dates = pd.bdate_range(end=self.AS_OF, periods=300)
        close = 24600 + np.random.default_rng(7).normal(0, 80, len(dates)).cumsum()
        prices = pd.DataFrame({'Open': close - 5, 'High': close + 50, 'Low': close - 55,
                               'Close': close, 'Volume': 100}, index=dates)
        chain = self.chain(dates[-2:], self.LISTED)
        with patch.object(self.module, 'load_derivatives', return_value=chain):
            profile = self.module.build_volatility_option_overlay(prices, 'NIFTY', 'YangZhang', date_count=2)
        self.assertEqual([f'{expiry:%d %b}' for expiry in profile['expiries']],
                         ['27 Oct', '03 Nov', '10 Nov', '17 Nov', '24 Nov', '29 Dec'])
        self.assertEqual(sorted(pd.to_datetime(profile['points']['Expiry'].unique())), profile['expiries'])
        weekly = profile['points'][profile['points']['Expiry type'].eq('Weekly')]
        self.assertTrue(weekly['IV source'].eq('Black-76 parity estimate').all())
        cone = self.module._cone_option_points(profile)
        self.assertEqual(sorted(pd.to_datetime(cone['Expiry'].unique())), list(self.MONTHLY))

        document = Mock()
        self.assertEqual(overlay.plot_option_history(profile, 'NIFTY', pdf_pages=document), 6)
        figures = [call.args[0] for call in document.savefig.call_args_list]
        titles = [figure.get_suptitle() for figure in figures]
        self.assertEqual(titles[:2], ['NIFTY | Option IV | Monthly expiry 27 Oct 2026',
                                      'NIFTY | Option IV | Weekly expiry 03 Nov 2026'])
        self.assertTrue(titles[-1].endswith('Monthly expiry 29 Dec 2026'))

        # Each one-liner sits clear of the charts' tick labels, the table and the footers.
        figure = figures[1]
        figure.canvas.draw()
        renderer = figure.canvas.get_renderer()
        notes = [text for text in figure.texts if text.get_text().startswith('How to use:')]
        self.assertEqual(len(notes), 3)
        others = [text.get_window_extent(renderer) for text in figure.texts if text not in notes]
        table_axes = figure.axes[2]
        others += [table_axes.title.get_window_extent(renderer),
                   table_axes.tables[0].get_window_extent(renderer)]
        for axes in figure.axes[:2]:
            others += [label.get_window_extent(renderer) for label in axes.get_xticklabels() if label.get_text()]
        boxes = [note.get_window_extent(renderer) for note in notes]
        for position, box in enumerate(boxes):
            self.assertGreaterEqual(box.x0, 0)
            self.assertLessEqual(box.x1, figure.bbox.x1)
            self.assertFalse(any(box.overlaps(other) for other in others + boxes[position + 1:]))
        self.assertFalse(plt.get_fignums())


if __name__ == '__main__':
    unittest.main()