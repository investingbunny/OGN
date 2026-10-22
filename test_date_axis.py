"""Checks that charts of daily data leave no gaps for weekends and holidays."""

import contextlib
import importlib.util
import io
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.dates import date2num

from date_axis import DateAxis, TradingDayFormatter, TradingDayLocator, is_daily

HOLIDAY = pd.Timestamp('2026-10-05')   # a Monday without data


def trading_days(start='2026-09-28', periods=26):
    days = pd.bdate_range(start, periods=periods)
    return days[days != HOLIDAY]


def string_modes():
    """pandas 2 object strings, plus pandas 3's `str` dtype where it can be switched on."""
    modes = [contextlib.nullcontext]
    try:
        pd.get_option('future.infer_string')
        modes.append(lambda: pd.option_context('future.infer_string', True))
    except Exception:
        pass
    return modes


class DateAxisTests(unittest.TestCase):
    def test_daily_dates_sit_at_consecutive_positions(self):
        days = trading_days()
        axis = DateAxis(days[::-1])
        self.assertTrue(axis.skips_gaps)
        np.testing.assert_array_equal(axis.x(days), np.arange(len(days), dtype=float))
        stored_in_seconds = DateAxis(days.as_unit('s'))
        np.testing.assert_array_equal(stored_in_seconds.x(days.as_unit('us')), np.arange(len(days)))

    def test_inputs_of_any_date_type_map_to_the_same_positions(self):
        days = trading_days(periods=5)
        axis = DateAxis(pd.Series(days).dt.tz_localize('Asia/Kolkata'))
        for values in (list(days.date), days.strftime('%Y-%m-%d').tolist(), pd.Series(days), days.to_numpy()):
            np.testing.assert_array_equal(axis.x(values), np.arange(len(days), dtype=float))

    def test_weekly_and_slower_series_keep_calendar_spacing(self):
        weekly = pd.date_range('2025-01-03', periods=30, freq='W-FRI')
        monthly = pd.date_range('2020-01-01', periods=30, freq='MS')
        for dates in (weekly, monthly):
            axis = DateAxis(dates)
            self.assertFalse(axis.skips_gaps)
            np.testing.assert_allclose(axis.x(dates), date2num(dates.to_numpy()))
        self.assertTrue(is_daily(trading_days()))
        self.assertTrue(DateAxis(trading_days(), skip_gaps=True).skips_gaps)
        self.assertFalse(DateAxis(trading_days(), skip_gaps=False).skips_gaps)

    def test_dates_off_the_axis_are_placed_between_or_beyond_it(self):
        axis = DateAxis(trading_days())   # ... Fri 02 Oct = 4, Tue 06 Oct = 5 ...
        result = axis.x(pd.to_datetime(['2026-10-03', '2026-10-05', '2026-09-25', '2026-11-03', None]))
        np.testing.assert_array_equal(result[:4], [4.25, 4.75, -1.0, 25.0])
        self.assertTrue(np.isnan(result[4]))
        self.assertTrue(np.isnan(DateAxis([]).x(['2026-10-01'])).all())

    def test_weekly_ticks_fall_on_the_first_trading_day_of_each_week(self):
        days = trading_days()
        locator = TradingDayLocator(DateAxis(days).dates, max_ticks=8)
        ticks = locator.tick_values(-1, len(days))
        self.assertEqual([days[int(tick)].strftime('%a %d %b') for tick in ticks],
                         ['Mon 28 Sep', 'Tue 06 Oct', 'Mon 12 Oct', 'Mon 19 Oct', 'Mon 26 Oct', 'Mon 02 Nov'])
        labels = TradingDayFormatter(DateAxis(days).dates).format_ticks(ticks)
        self.assertEqual(labels, ['28 Sep\n2026', '06 Oct', '12 Oct', '19 Oct', '26 Oct', '02 Nov'])
        np.testing.assert_array_equal(locator.tick_values(3.2, 7.9), [4, 5, 6, 7])

    def test_longer_spans_tick_months_or_years_with_the_year_where_it_changes(self):
        year = DateAxis(pd.bdate_range('2025-09-17', '2026-09-30'))
        ticks = TradingDayLocator(year.dates, max_ticks=8).tick_values(0, len(year.dates) - 1)
        self.assertEqual(TradingDayFormatter(year.dates).format_ticks(ticks),
                         ['Nov\n2025', 'Jan\n2026', 'Mar', 'May', 'Jul', 'Sep'])
        five_years = DateAxis(pd.bdate_range('2021-09-01', '2026-09-30'))
        ticks = TradingDayLocator(five_years.dates, max_ticks=6).tick_values(-10, len(five_years.dates) + 10)
        self.assertEqual(TradingDayFormatter(five_years.dates).format_ticks(ticks),
                         ['2022', '2023', '2024', '2025', '2026'])

    def test_fixed_format_and_cursor_readout(self):
        days = trading_days(periods=5)
        formatter = TradingDayFormatter(DateAxis(days).dates, '%d %b')
        self.assertEqual(formatter.format_ticks([0, 1, 9]), ['28 Sep', '29 Sep', ''])
        self.assertEqual(formatter.format_data_short(1.4), '2026-09-29')
        self.assertEqual(formatter.format_data_short(-3), '')

    def test_zooming_recomputes_ticks_on_shared_axes(self):
        days = trading_days()
        figure = plt.figure()
        try:
            top = figure.add_subplot(2, 1, 1)
            bottom = figure.add_subplot(2, 1, 2, sharex=top)
            axis = DateAxis(days)
            top.plot(axis.x(days), np.arange(len(days)))
            bottom.bar(axis.x(days), np.ones(len(days)))
            axis.format(top)
            figure.canvas.draw()
            self.assertEqual(bottom.get_xticklabels()[0].get_text(), '28 Sep\n2026')
            top.set_xlim(8.5, 12.5)
            figure.canvas.draw()
            self.assertEqual([label.get_text() for label in bottom.get_xticklabels()],
                             ['12 Oct\n2026', '13 Oct', '14 Oct', '15 Oct'])
            self.assertEqual(top.format_xdata(9), '2026-10-12')
        finally:
            plt.close(figure)


class ChartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('ogn_date_axis_test', Path(__file__).with_name('Option-OGN.py'))
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def prices(self, periods=300):
        dates = pd.bdate_range(end='2026-09-04', periods=periods)
        dates = dates[~dates.isin(pd.to_datetime(['2026-08-14', '2026-08-27']))]
        generator = np.random.default_rng(5)
        close = 400 + generator.normal(0, 3, len(dates)).cumsum()
        return pd.DataFrame({'Date': dates, 'Open': close - 1, 'High': close + 2, 'Low': close - 2,
                             'Close': close, 'Volume': 1000.0})

    def test_technical_page_has_no_gaps_even_for_option_only_days(self):
        prices = self.prices()
        last_price_day = prices['Date'].iloc[-1]
        # Derivatives one day ahead of the cash data merge a row without a price.
        option_day = pd.DataFrame({'Date': [last_price_day + pd.offsets.BDay(1)], 'MaxPain': [400.0], 'PCR': [1.0]})
        for mode in string_modes():
            with self.subTest(mode=mode), mode(), \
                    patch.object(self.module, 'REPORT_SECTIONS', ['technical']), \
                    patch.object(self.module, 'load_analysis_frame', return_value=(prices.copy(), 'test')), \
                    patch.object(self.module, 'GetMaxPain', return_value=option_day), \
                    patch.object(self.module, 'PdfPages') as document, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.module.FnOAnalysis(single_scrip='TEST', pdf_path=str(Path(__file__).with_name('unused.pdf')))
                figure = document.return_value.savefig.call_args.args[0]
                figure.canvas.draw()
                ax_macd = figure.axes[0]
                expected = np.arange(25, dtype=float)
                centres = sorted(bar.get_x() + bar.get_width() / 2 for bar in ax_macd.patches)
                np.testing.assert_allclose(centres, expected)
                for axes in figure.axes:
                    for line in axes.get_lines():
                        if len(line.get_xdata()) > 2:
                            np.testing.assert_array_equal(line.get_xdata(), expected)
                labels = [label.get_text() for label in ax_macd.get_xticklabels()]
                self.assertEqual(labels[0], '03 Aug\n2026')
                self.assertTrue(all(label.endswith(('Aug', 'Sep')) for label in labels[1:]), labels)
                self.assertEqual(ax_macd.format_xdata(24), f'{last_price_day:%Y-%m-%d}')
                plt.close(figure)

    def test_rolling_volatility_panel_has_no_gaps(self):
        price_data = self.prices(400).set_index('Date')
        profile = self.module.compute_volatility_profile(price_data, 'YangZhang')
        document = Mock()
        self.module.plot_volatility(profile, 'TEST', pdf_pages=document)
        figure = document.savefig.call_args.args[0]
        figure.canvas.draw()
        rolling = next(axes for axes in figure.axes if axes.get_title().startswith('Rolling'))
        expected = np.arange(len(profile['rolling']), dtype=float)
        for line in rolling.get_lines():
            np.testing.assert_array_equal(line.get_xdata(), expected)
        labels = [label.get_text() for label in rolling.get_xticklabels()]
        self.assertTrue(labels and '2025' in labels[0], labels)


if __name__ == '__main__':
    unittest.main()
