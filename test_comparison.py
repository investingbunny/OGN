"""Regression checks for comparisons across market and macro data frequencies."""

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch
from unittest.mock import Mock

import numpy as np
import pandas as pd


class ComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import matplotlib
        matplotlib.use('Agg')
        spec = importlib.util.spec_from_file_location(
            'ogn_comparison_test', Path(__file__).with_name('Option-OGN.py'))
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def series(self, dates, values, frequency=None, aggregation=None):
        result = pd.Series(values, index=pd.to_datetime(dates), dtype=float)
        if frequency:
            result.attrs['frequency'] = frequency
        if aggregation:
            result.attrs['aggregation'] = aggregation
        return result

    def test_daily_monthly_uses_period_mean_not_first_day(self):
        monthly = self.series(['2025-02-01', '2025-03-01'], [1, 2], 'Monthly')
        dates = pd.bdate_range('2025-02-03', '2025-03-31')
        daily = self.series(dates, np.arange(len(dates)))
        result, details = self.module.align_comparison_series(monthly, daily, 'Japan', 'WTI')
        self.assertEqual(len(result), 2)
        self.assertEqual(result.index.strftime('%Y-%m-%d').tolist(), ['2025-02-28', '2025-03-31'])
        self.assertAlmostEqual(result['WTI'].iloc[0], daily.loc['2025-02'].mean())
        self.assertAlmostEqual(result['WTI'].iloc[1], daily.loc['2025-03'].mean())
        self.assertEqual(details['frequency'], 'monthly')
        self.assertEqual(details['lag_unit'], 'months')
        self.assertEqual(details['aggregation'], ['native', 'mean'])

    def test_month_start_and_month_end_represent_same_period(self):
        first = self.series(['2024-01-01', '2024-02-01'], [3, 4], 'monthly')
        last = self.series(['2024-01-31', '2024-02-29'], [30, 40], 'monthly')
        result, _ = self.module.align_comparison_series(first, last, 'First', 'Last')
        self.assertEqual(result['Last'].tolist(), [30, 40])

    def test_quarterly_flow_sum_and_stock_last(self):
        months = pd.date_range('2024-01-01', periods=6, freq='MS')
        flow = self.series(months, [1, 2, 3, 4, 5, 6], 'monthly', 'sum')
        stock = self.series(months, [10, 20, 30, 40, 50, 60], 'monthly', 'last')
        result, details = self.module.align_comparison_series(
            flow, stock, 'Flow', 'Stock', frequency='quarterly')
        self.assertEqual(result['Flow'].tolist(), [6, 15])
        self.assertEqual(result['Stock'].tolist(), [30, 60])
        self.assertEqual(details['aggregation'], ['sum', 'last'])

    def test_no_upsampling_and_no_filled_gap(self):
        first = self.series(['2024-01-01', '2024-03-01', '2024-04-01'], [1, 3, 4], 'monthly')
        second = self.series(pd.date_range('2024-01-31', periods=4, freq='ME'), [10, 20, 30, 40], 'monthly')
        with self.assertRaisesRegex(ValueError, 'upsample'):
            self.module.align_comparison_series(first, second, 'First', 'Second', frequency='daily')
        result, details = self.module.align_comparison_series(first, second, 'First', 'Second')
        self.assertEqual(result['First'].tolist(), [3, 4])
        self.assertEqual(details['dropped_for_gaps'], 1)

    def test_current_month_is_excluded(self):
        today = pd.Timestamp.today().normalize()
        current = today.to_period('M').start_time
        previous = current - pd.offsets.MonthBegin(1)
        series = self.series([previous, current], [1, 999], 'monthly')
        result, details = self.module.align_comparison_series(series, series, 'Left', 'Right')
        self.assertEqual(result['Left'].tolist(), [1])
        self.assertEqual(details['dropped_open_periods'], [1, 1])

    def test_incomplete_daily_month_does_not_become_monthly_average(self):
        monthly = self.series(['2025-01-01', '2025-02-01'], [1, 2], 'monthly')
        dates = pd.bdate_range('2025-01-01', '2025-02-05')
        daily = self.series(dates, np.arange(len(dates)), 'daily')
        result, details = self.module.align_comparison_series(monthly, daily, 'Monthly', 'Daily')
        self.assertEqual(len(result), 1)
        self.assertEqual(result.index[0], pd.Timestamp('2025-01-31'))
        self.assertEqual(details['dropped_incomplete_periods'], [0, 1])

    def test_weekly_last_observation_and_friday_ending_alignment(self):
        weekly = self.series(['2025-01-06', '2025-01-07', '2025-01-14'], [1, 2, 3], 'weekly')
        dates = pd.bdate_range('2025-01-06', '2025-01-17')
        daily = self.series(dates, np.arange(len(dates)), 'daily')
        result, details = self.module.align_comparison_series(weekly, daily, 'CFTC', 'WTI')
        self.assertEqual(result.index.strftime('%Y-%m-%d').tolist(), ['2025-01-10', '2025-01-17'])
        self.assertEqual(result['CFTC'].tolist(), [2, 3])
        self.assertEqual(result['WTI'].tolist(), [2, 7])
        self.assertEqual(details['consolidated_weekly_observations'], [1, 0])

    def test_local_monthly_dates_survive_timezone_removal(self):
        japan_dates = pd.date_range('2025-01-01', periods=3, freq='MS', tz='Asia/Tokyo')
        japan_series = self.series(japan_dates, [1, 2, 3], 'monthly')
        us_series = self.series(pd.date_range('2025-01-31', periods=3, freq='ME'), [10, 20, 30], 'monthly')
        result, _ = self.module.align_comparison_series(japan_series, us_series, 'Japan', 'US')
        self.assertEqual(result['Japan'].tolist(), [1, 2, 3])
        self.assertEqual(result.index[0], pd.Timestamp('2025-01-31'))

    def test_annual_native_metadata_prevents_month_start_misclassification(self):
        annual = self.series(['2023-01-01', '2024-01-01'], [6, 7], 'annual')
        months = pd.date_range('2023-01-01', periods=24, freq='MS')
        monthly = self.series(months, np.arange(24), 'monthly')
        result, details = self.module.align_comparison_series(annual, monthly, 'GDP', 'Price')
        self.assertEqual(result['Price'].tolist(), [5.5, 17.5])
        self.assertEqual(details['frequency'], 'annual')

    def test_weekly_to_monthly_rejects_sparse_coverage(self):
        weeks = pd.to_datetime(['2025-01-07', '2025-01-14', '2025-01-21', '2025-01-28',
                                '2025-02-04'])
        weekly = self.series(weeks, [1, 2, 3, 4, 5], 'weekly')
        monthly = self.series(['2025-01-01', '2025-02-01'], [10, 20], 'monthly')
        result, details = self.module.align_comparison_series(weekly, monthly, 'Weekly', 'Monthly')
        self.assertEqual(result['Weekly'].tolist(), [2.5])
        self.assertEqual(details['dropped_incomplete_periods'], [1, 0])

    def test_missing_month_is_not_a_complete_quarter_total(self):
        dates = ['2025-01-01', '2025-03-01', '2025-04-01', '2025-05-01', '2025-06-01']
        flow = self.series(dates, [1, 3, 4, 5, 6], 'monthly', 'sum')
        quarter = self.series(['2025-03-31', '2025-06-30'], [10, 20], 'quarterly')
        result, details = self.module.align_comparison_series(flow, quarter, 'Flow', 'Quarter')
        self.assertEqual(result['Flow'].tolist(), [15])
        self.assertEqual(details['dropped_incomplete_periods'], [1, 0])

    def test_loader_preserves_native_metadata_and_aggregation(self):
        frame = pd.DataFrame({'Date': pd.date_range('2025-01-01', periods=3, freq='MS'),
                               'Value': [10, 20, 30], 'Frequency': 'Monthly',
                               'Unit': 'Billions of JPY'})
        series, column = self.module._comp_to_daily_series(frame, 'JPCURRENT')
        self.assertEqual(column, 'Value')
        self.assertEqual(series.attrs['frequency'], 'Monthly')
        self.assertEqual(series.attrs['aggregation'], 'sum')
        self.assertEqual(series.attrs['unit'], 'Billions of JPY')
        stock, _ = self.module._comp_to_daily_series(frame, 'JPFOREIGN')
        self.assertEqual(stock.attrs['aggregation'], 'last')

    def test_ratio_uses_common_periods_for_mixed_frequency_legs(self):
        monthly = pd.DataFrame({'Date': pd.to_datetime(['2025-02-01', '2025-03-01']),
                                'Value': [20, 30], 'Frequency': 'Monthly'})
        dates = pd.bdate_range('2025-02-03', '2025-03-31')
        daily = pd.DataFrame({'Date': dates, 'Value': 10.0, 'Frequency': 'Daily'})
        with patch.object(self.module, '_comp_load_symbol', side_effect=[
                (None, None), (monthly, 'Macro'), (daily, 'Macro')]):
            result, label, description = self.module.resolve_comp_series('JPMONTH__WTI')
        self.assertEqual(result.tolist(), [2, 3])
        self.assertEqual(result.attrs['frequency'], 'monthly')
        self.assertIn('monthly', description)

    def test_statistics_use_monthly_window_and_percentage_point_changes(self):
        dates = pd.bdate_range('2015-01-01', '2024-12-31')
        generator = np.random.default_rng(42)
        daily = self.series(dates, 80 + generator.normal(size=len(dates)).cumsum(), 'daily')
        monthly = self.series(pd.date_range('2015-01-01', periods=120, freq='MS'),
                              3 + generator.normal(0, 0.1, 120).cumsum(), 'monthly')
        monthly.attrs['unit'] = 'Percent'
        result = self.module.compute_comparison(daily, monthly, 'WTI', 'JP10Y', days=72)
        self.assertEqual(result['frequency'], 'monthly')
        self.assertEqual(len(result['aligned']), 72)
        self.assertEqual(result['lag_unit'], 'months')
        self.assertEqual(result['transforms']['JP10Y'], 'percentage-point changes')
        pd.testing.assert_series_equal(result['changes']['JP10Y'],
                                       result['aligned']['JP10Y'].diff().dropna())
        text = self.module.build_comparison_table(result).to_string(index=False)
        self.assertNotIn('day(s)', text)

    def test_table_defines_every_measure(self):
        dates = pd.date_range('2000-01-01', periods=20, freq='YS')
        first = self.series(dates, np.arange(20) ** 1.2 + 1, 'annual')
        second = self.series(dates, np.arange(20) ** 1.3 + 1, 'annual')
        table = self.module.build_comparison_table(
            self.module.compute_comparison(first, second, 'Growth', 'Oil'))
        self.assertEqual(table.columns.tolist(),
                         ['Measure', 'Definition', 'Value', 'Reading', 'What it tells you'])
        self.assertEqual(table['Measure'].tolist()[0], 'Cointegration')
        self.assertTrue(table['Definition'].str.len().gt(40).all())
        self.assertEqual(table.loc[1, 'Definition'], table.loc[2, 'Definition'])

    def test_short_annual_sample_retains_charts_but_not_significance(self):
        dates = pd.date_range('2000-01-01', periods=20, freq='YS')
        first = self.series(dates, np.arange(20) ** 1.2 + 1, 'annual')
        second = self.series(dates, np.arange(20) ** 1.3 + 1, 'annual')
        with patch.object(self.module, 'coint') as cointegration, \
                patch.object(self.module, 'granger_min_pvalue') as granger:
            result = self.module.compute_comparison(first, second, 'Growth', 'Oil')
        self.assertEqual(len(result['aligned']), 20)
        self.assertEqual(result['lag_unit'], 'years')
        self.assertEqual(result['max_lag'], 2)
        self.assertIn('60 aligned', result['coint']['error'])
        self.assertIn('60 aligned', result['granger_ab']['error'])
        cointegration.assert_not_called()
        granger.assert_not_called()

    def test_cointegration_requires_supported_integration_order(self):
        dates = pd.date_range('2000-01-01', periods=100, freq='MS')
        generator = np.random.default_rng(11)
        first = self.series(dates, generator.normal(size=100) + 5, 'monthly')
        second = self.series(dates, generator.normal(size=100) + 10, 'monthly')
        with patch.object(self.module, 'adfuller', return_value=(0, 0.01)), \
                patch.object(self.module, 'coint') as cointegration:
            result = self.module.compute_comparison(first, second, 'First', 'Second')
        self.assertIn('I(1)', result['coint']['error'])
        cointegration.assert_not_called()

    def test_daily_daily_comparison_retains_common_trading_dates(self):
        dates = pd.bdate_range('2024-01-01', periods=80)
        generator = np.random.default_rng(19)
        first = self.series(dates, 100 + generator.normal(size=80).cumsum(), 'daily')
        second = self.series(dates.delete(10), 80 + generator.normal(size=79).cumsum(), 'daily')
        result = self.module.compute_comparison(first, second, 'Gold', 'Silver', days=60)
        self.assertEqual(result['frequency'], 'daily')
        self.assertEqual(result['lag_unit'], 'observations')
        self.assertEqual(len(result['aligned']), 60)
        self.assertTrue(result['aligned'].index.isin(second.index).all())

    def test_cli_passes_sampling_choices_and_uses_observation_filename(self):
        arguments = ['Option-OGN.py', '--pdf', '--periods', '72',
                     '--compare-frequency', 'quarterly', '--compare-aggregation', 'last',
                     'WTI', 'JP10Y']
        with patch.object(self.module.sys, 'argv', arguments), \
                patch.object(self.module, 'FnOAnalysis') as analyse:
            self.module.main()
        options = analyse.call_args.kwargs
        self.assertEqual(options['days'], 72)
        self.assertEqual(options['comparison_frequency'], 'quarterly')
        self.assertEqual(options['comparison_aggregation'], 'last')
        self.assertEqual(options['pdf_path'], str(
            self.module.CHARTS_DIR / 'WTI_vs_JP10Y_72obs_quarterly_last_Analysis.pdf'))
        self.assertEqual(self.module.CHARTS_DIR, Path(r'C:\OGN-OneDrive\OneDrive\Github projects\OGN') / 'charts')

    def test_chart_uses_period_labels_and_standardizes_negative_levels(self):
        dates = pd.date_range('2010-01-01', periods=80, freq='MS')
        generator = np.random.default_rng(73)
        first = self.series(dates, generator.normal(size=80).cumsum(), 'monthly')
        second = self.series(dates, generator.normal(size=80).cumsum(), 'monthly')
        result = self.module.compute_comparison(first, second, 'Rate', 'Oil', days=72)
        document = Mock()
        self.module.plot_comparison(result, self.module.build_comparison_table(result),
                                    'Macro', 'Macro', pdf_pages=document)
        figure = document.savefig.call_args.args[0]
        texts = [label.get_text() for label in figure.texts]
        axes_titles = [axes.get_title() for axes in figure.axes]
        self.assertTrue(any('monthly (metadata)' in text for text in texts))
        self.assertTrue(any('last 72 months' in text for text in texts))
        self.assertTrue(any('not a release-time backtest' in text for text in texts))
        self.assertTrue(any('Standardized levels' in title for title in axes_titles))
        self.assertIn('Lag (months)', figure.axes[3].get_xlabel())
        self.assertTrue(all('common days' not in title for title in axes_titles))
        figure.canvas.draw()
        renderer = figure.canvas.get_renderer()
        table = figure.axes[4].tables[0]
        footer = next(label for label in figure.texts
                      if label.get_text().startswith('Excluded open periods:'))
        self.assertGreater(table.get_window_extent(renderer).y0,
                           footer.get_window_extent(renderer).y1)
        for cell in table.get_celld().values():
            text_box = cell.get_text().get_window_extent(renderer)
            cell_box = cell.get_window_extent(renderer)
            self.assertLessEqual(text_box.width, cell_box.width)
            self.assertLessEqual(text_box.height, cell_box.height)
        # Monthly observations keep calendar spacing on the date panels.
        from matplotlib.dates import date2num
        levels = figure.axes[0].get_lines()[0].get_xdata()
        np.testing.assert_allclose(levels, date2num(result['aligned'].index.to_numpy()))

    def test_daily_chart_skips_weekends_and_holidays(self):
        dates = pd.bdate_range('2025-01-01', periods=160)
        dates = dates[~dates.isin(pd.to_datetime(['2025-01-20', '2025-02-17']))]
        generator = np.random.default_rng(11)
        first = self.series(dates, 100 + generator.normal(size=len(dates)).cumsum())
        second = self.series(dates, 50 + generator.normal(size=len(dates)).cumsum())
        result = self.module.compute_comparison(first, second, 'Gold', 'Silver')
        document = Mock()
        self.module.plot_comparison(result, self.module.build_comparison_table(result),
                                    'Macro', 'Macro', pdf_pages=document)
        figure = document.savefig.call_args.args[0]
        figure.canvas.draw()
        ax_raw, ax_norm, ax_spread = figure.axes[0], figure.axes[1], figure.axes[2]
        expected = np.arange(len(result['aligned']), dtype=float)
        for axes in (ax_raw, ax_norm, ax_spread):
            np.testing.assert_array_equal(axes.get_lines()[0].get_xdata(), expected)
        np.testing.assert_array_equal(figure.axes[-1].get_lines()[0].get_xdata(), expected)
        labels = [label.get_text() for label in ax_raw.get_xticklabels()]
        self.assertTrue(labels and all(label.split('\n')[0] in
                                       ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug')
                                       for label in labels), labels)
        self.assertIn('\n2025', labels[0])


if __name__ == '__main__':
    unittest.main()