"""Regression checks for the technical page: 1-year gap-free axis and the Buy/Sell/Hold audit."""

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

INDICATOR_PANELS = {'MACD (12, 26, 9)', 'RSI & ADX', 'Fibonacci Retracements',
                    'Bollinger Bands & OBV', 'EMA Crossover', 'SMA Crossover'}


class TechnicalChartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import matplotlib
        matplotlib.use('Agg')
        spec = importlib.util.spec_from_file_location(
            'ogn_technical_test', Path(__file__).with_name('Option-OGN.py'))
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    @staticmethod
    def prices():
        # Weekdays only, minus two exchange holidays inside the last year.
        dates = pd.bdate_range('2024-06-03', '2026-10-22').drop(
            pd.DatetimeIndex(['2026-10-02', '2026-10-20']))
        close = 1000 + 50 * np.sin(np.arange(len(dates)) / 9.0) + np.arange(len(dates))
        return pd.DataFrame({'Date': dates, 'Open': close - 2, 'High': close + 5,
                             'Low': close - 5, 'Close': close, 'Volume': 1000.0})

    def run_report(self, frame, **patches):
        """Run only the technical section for `frame`; return the PdfPages mock."""
        module = self.module
        document = Mock()
        replacements = {
            'REPORT_SECTIONS': ['technical'],
            'load_analysis_frame': Mock(return_value=(frame, 'test')),
            'load_full_futures': Mock(side_effect=FileNotFoundError('offline')),
            'PdfPages': Mock(return_value=document),
            **patches,
        }
        with patch.multiple(module, **replacements):
            module.FnOAnalysis(single_scrip='TEST', pdf_path='unused.pdf')
        return document

    def indicator_lines(self, figure):
        """x data of every plotted series on the six indicator panels and the OBV twin."""
        shared = [ax for ax in figure.axes if ax.get_title() in INDICATOR_PANELS
                  or (not ax.get_title() and ax.get_lines())]
        self.assertEqual(len(shared), 7)
        return [np.asarray(line.get_xdata(), dtype=float)
                for ax in shared for line in ax.get_lines() if len(line.get_xdata()) > 2]

    @staticmethod
    def tick_labels(axis):
        formatter = axis.xaxis.get_major_formatter()
        return [formatter(tick, index) for index, tick in enumerate(axis.get_xticks())]

    def test_window_bars_cover_one_calendar_year(self):
        dates = self.prices()['Date']
        expected = int((dates >= pd.Timestamp('2025-10-22')).sum())
        self.assertEqual(self.module.technical_window_bars(dates), expected)
        self.assertEqual(self.module.technical_window_bars(dates, years=2),
                         int((dates >= pd.Timestamp('2024-10-22')).sum()))
        self.assertEqual(self.module.technical_window_bars(pd.Series([], dtype='datetime64[ns]')), 0)

    def test_panels_show_last_year_without_weekend_or_holiday_gaps(self):
        frame = self.prices()
        shown = frame[frame['Date'] >= pd.Timestamp('2025-10-22')]
        renko = Mock(wraps=self.module.PlotRenko)
        figure = self.run_report(frame, PlotRenko=renko).savefig.call_args.args[0]

        for x in self.indicator_lines(figure):
            np.testing.assert_array_equal(x, np.arange(len(shown)))
        macd = next(ax for ax in figure.axes if ax.get_title() == 'MACD (12, 26, 9)')
        self.assertEqual(macd.get_xlim(), (-1.0, float(len(shown))))
        bars = sorted(bar.get_x() + bar.get_width() / 2 for bar in macd.patches)
        np.testing.assert_allclose(bars, np.arange(len(shown)))

        # Ticks name the first trading day of each month.
        labels = pd.to_datetime(self.tick_labels(macd), format='%d-%b-%y')
        first_of_month = set(shown.groupby(shown['Date'].dt.to_period('M'))['Date'].min())
        self.assertGreaterEqual(len(labels), 11)
        self.assertTrue(set(labels) <= first_of_month)

        # Renko keeps its own history and brick count, not the 1-year window.
        if self.module.HAS_RENKO:
            bricks, count = renko.call_args.args[:2]
            self.assertEqual(count, 100)
            self.assertLess(pd.Timestamp(bricks['date'].min()), shown['Date'].iloc[0])

    def test_rows_without_a_price_add_no_bars(self):
        module = self.module
        captured = Mock()
        self.run_report(self.prices(), plot_chart=captured)
        indicators, bars = captured.call_args.args[:2]

        # Dates merged in from other sources (e.g. option-only days) carry no price.
        extra = pd.DataFrame({'Date': pd.to_datetime(['2026-10-03', '2026-10-24'])})
        merged = pd.concat([indicators, extra]).sort_values('Date', ignore_index=True)
        audit = Mock(wraps=module.analyze_stock)
        document = Mock()
        with patch.object(module, 'load_full_futures', side_effect=FileNotFoundError('offline')), \
                patch.object(module, 'analyze_stock', audit):
            module.plot_chart(merged, bars, 'TEST', pdf_pages=document)

        for x in self.indicator_lines(document.savefig.call_args.args[0]):
            np.testing.assert_array_equal(x, np.arange(bars))
        audited = audit.call_args.args[0]
        self.assertEqual(len(audited), bars)
        self.assertTrue(audited['Close'].notna().all())
        self.assertEqual(audited.index[-1], pd.Timestamp('2026-10-22'))

    def test_missing_indicator_value_does_not_break_the_line(self):
        figure, axis = self.module.plt.subplots()
        values = np.array([1.0, 2.0, np.nan, 4.0, 5.0])
        line, = self.module._plot_available(axis, np.arange(5), values)
        np.testing.assert_array_equal(line.get_xdata(), [0, 1, 3, 4])
        self.module.plt.close(figure)

    def test_short_window_labels_evenly_spaced_bars(self):
        figure, axis = self.module.plt.subplots()
        dates = pd.bdate_range('2026-09-01', periods=30)
        axis.plot(np.arange(len(dates)), np.arange(len(dates)))
        self.module._label_trading_days(axis, dates)
        labels = self.tick_labels(axis)
        self.assertEqual(labels[0], '01-Sep-26')
        self.assertEqual(labels[-1], dates[-1].strftime('%d-%b-%y'))
        self.assertLessEqual(len(labels), 6)
        self.module.plt.close(figure)

    @staticmethod
    def audit_frame(**last):
        """70 flat bars (60-bar swing 800-1200, ATR 100); `last` overrides the final bar."""
        frame = pd.DataFrame({
            'Close': 1000.0, 'High': 1010.0, 'Low': 990.0, 'Volume': 1000.0, 'ATR': 100.0,
            '5DMA-E': 1000.0, '9DMA-E': 1000.0, '13DMA-E': 1000.0, '21DMA-E': 1000.0,
            '48DMA-E': 1000.0, '20DMA': 1000.0, '50DMA': 1000.0, '200DMA': 1000.0, 'MA': 1000.0,
            'MACD': 0.0, 'Signal': 0.0, 'RSI': 50.0}, index=pd.bdate_range('2026-01-01', periods=70))
        frame.iloc[20, frame.columns.get_loc('High')] = 1200.0
        frame.iloc[30, frame.columns.get_loc('Low')] = 800.0
        for column, value in last.items():
            frame.iloc[-1, frame.columns.get_loc(column)] = value
        return frame

    def test_audit_reads_buy_sell_or_hold(self):
        bullish = self.module.analyze_stock(self.audit_frame(
            Close=1100.0, Volume=3000.0, **{'50DMA': 1100.0, '9DMA-E': 1050.0, '13DMA-E': 1005.0,
                                             'MACD': 30.0, 'RSI': 65.0}), 'TEST')
        self.assertEqual(bullish['Status'].tolist(),
                         ['Buy', 'Buy', 'Hold', 'Hold', 'Buy', 'Buy', 'Buy', 'Buy', 'Buy'])
        self.assertEqual(bullish['Verdict'].iloc[0], 'Bullish market regime')
        self.assertEqual(bullish['Condition'].iloc[5], 'RSI 14 (65)')
        self.assertEqual(bullish.iloc[7].tolist(), ['Fib 61.8% (1047)', 'Buy', 'Holding above pivot'])
        self.assertEqual(bullish['Verdict'].iloc[8], 'Volume confirms up day')

        bearish = self.module.analyze_stock(self.audit_frame(
            Close=900.0, Volume=3000.0, **{'50DMA': 900.0, '9DMA-E': 950.0, '13DMA-E': 995.0,
                                            '5DMA-E': 990.0, 'MACD': -30.0, 'RSI': 35.0}), 'TEST')
        self.assertEqual(bearish['Status'].tolist(),
                         ['Sell', 'Sell', 'Hold', 'Hold', 'Sell', 'Sell', 'Sell', 'Sell', 'Sell'])
        self.assertEqual(bearish['Verdict'].iloc[0], 'Bearish market regime')
        self.assertEqual(bearish['Verdict'].iloc[7], 'Below 38.2% (953)')
        self.assertEqual(bearish['Verdict'].iloc[8], 'Volume confirms down day')

        # Within the band, neutral RSI, between the Fib levels and no volume surge: Hold
        neutral = self.module.analyze_stock(self.audit_frame(Close=1005.0), 'TEST')
        self.assertTrue(neutral['Status'].eq('Hold').all())
        self.assertEqual(neutral['Verdict'].iloc[5], 'Neutral zone (40-60)')
        self.assertEqual(neutral['Verdict'].iloc[7], 'Between 38.2% and 61.8%')

    def test_audit_band_and_missing_inputs(self):
        # Hold band = 0.1 x ATR: 10 with the stored ATR of 100, 2 from ATR(20) of these bars (20)
        frame = self.audit_frame(**{'13DMA-E': 1005.0})
        self.assertEqual(self.module.analyze_stock(frame, 'TEST')['Status'].iloc[2], 'Hold')
        self.assertEqual(self.module.analyze_stock(frame.drop(columns='ATR'), 'TEST')['Status'].iloc[2], 'Buy')
        frame = self.audit_frame(**{'13DMA-E': 1001.0}).drop(columns='ATR')
        self.assertEqual(self.module.analyze_stock(frame, 'TEST')['Status'].iloc[2], 'Hold')
        missing = self.module.analyze_stock(self.audit_frame(RSI=np.nan, **{'200DMA': np.nan}), 'TEST')
        self.assertEqual(missing.iloc[0, 1:].tolist(), ['Hold', 'Not enough history'])
        self.assertEqual(missing.iloc[5].tolist(), ['RSI 14', 'Hold', 'Not enough history'])

    def test_audit_table_colours_each_status(self):
        from matplotlib.colors import to_rgba
        figure = self.run_report(self.prices()).savefig.call_args.args[0]
        axes = next(ax for ax in figure.axes if ax.get_title().endswith('Technical Audit'))
        cells = axes.tables[0].get_celld()
        statuses = [cell.get_text().get_text() for (row, column), cell in cells.items()
                    if row > 0 and column == 1]
        self.assertGreaterEqual(len(statuses), 8)
        for (row, column), cell in cells.items():
            if row > 0 and column == 1:
                status = cell.get_text().get_text()
                self.assertIn(status, self.module.AUDIT_COLOURS)
                self.assertEqual(cell.get_facecolor(), to_rgba(self.module.AUDIT_COLOURS[status]))


if __name__ == '__main__':
    unittest.main()
