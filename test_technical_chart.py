"""Regression checks for technical-page windows, gap-free axes, the Buy/Sell/Hold audit and swing pages."""

import importlib.util
import io
import itertools
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

    def run_report(self, frame, days=None, compare_with=None, **patches):
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
            module.FnOAnalysis(single_scrip='TEST', pdf_path='unused.pdf',
                               days=days, compare_with=compare_with)
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

    def test_single_symbol_window_limits_primary_pages_without_losing_indicator_warmup(self):
        frame = self.prices()
        for days in (1, 30, 250, 400, len(frame) + 100):
            with self.subTest(days=days):
                chart, trendlines, volatility = Mock(), Mock(), Mock()
                self.run_report(
                    frame, days=days, REPORT_SECTIONS=['technical', 'trendlines', 'volatility'],
                    plot_chart=chart, trendline_analysis=trendlines, volatility_analysis=volatility)
                indicators, bars = chart.call_args.args[:2]
                self.assertEqual(bars, min(days, len(frame)))
                self.assertEqual(len(indicators), len(frame))
                self.assertAlmostEqual(indicators['200DMA'].iloc[-1], frame['Close'].tail(200).mean())
                self.assertAlmostEqual(indicators['9DMA-E'].iloc[-1],
                                       frame['Close'].ewm(span=9, adjust=False).mean().iloc[-1])
                expected = frame.set_index('Date').tail(days)
                pd.testing.assert_frame_equal(trendlines.call_args.args[0], expected)
                pd.testing.assert_frame_equal(volatility.call_args.args[0], expected)

    def test_single_symbol_window_is_drawn_on_the_indicator_panels(self):
        for days in (250, 400):
            with self.subTest(days=days):
                figure = self.run_report(self.prices(), days=days).savefig.call_args.args[0]
                for x in self.indicator_lines(figure):
                    np.testing.assert_array_equal(x, np.arange(days))

    def test_pairwise_window_leaves_primary_pages_at_their_existing_defaults(self):
        frame = self.prices()
        chart, trendlines, volatility, comparison = Mock(), Mock(), Mock(), Mock()
        self.run_report(
            frame, days=250, compare_with='PEER',
            REPORT_SECTIONS=['technical', 'trendlines', 'volatility', 'comparison'],
            plot_chart=chart, trendline_analysis=trendlines,
            volatility_analysis=volatility, compare_series=comparison)
        self.assertEqual(chart.call_args.args[1], self.module.technical_window_bars(frame['Date']))
        expected = frame.set_index('Date')
        pd.testing.assert_frame_equal(trendlines.call_args.args[0], expected)
        pd.testing.assert_frame_equal(volatility.call_args.args[0], expected)
        self.assertEqual(comparison.call_args.args, ('TEST', 'PEER'))
        self.assertEqual(comparison.call_args.kwargs['days'], 250)

    def test_single_symbol_window_reports_when_less_history_is_available(self):
        frame = self.prices()
        days = len(frame) + 100
        with patch.object(self.module.sys, 'stdout', new_callable=io.StringIO) as output:
            self.run_report(frame, days=days, plot_chart=Mock())
        self.assertIn(f'fewer than the {days:,} requested', output.getvalue())

    def test_window_ending_early_excludes_later_bars_from_every_primary_page(self):
        frame = self.prices()
        chart, trendlines, volatility = Mock(), Mock(), Mock()
        self.run_report(frame, days='350d-25d', REPORT_SECTIONS=['technical', 'trendlines', 'volatility'],
                        plot_chart=chart, trendline_analysis=trendlines, volatility_analysis=volatility)
        indicators, bars = chart.call_args.args[:2]
        expected = frame.set_index('Date').iloc[-350:-25]
        self.assertEqual(bars, 325)
        self.assertEqual(len(indicators), len(frame) - 25)
        self.assertEqual(indicators['Date'].iloc[-1], expected.index[-1])
        self.assertAlmostEqual(indicators['200DMA'].iloc[-1], frame['Close'].iloc[-225:-25].mean())
        pd.testing.assert_frame_equal(trendlines.call_args.args[0], expected)
        pd.testing.assert_frame_equal(volatility.call_args.args[0], expected)

    def test_month_window_covers_calendar_months_and_skips_empty_ones(self):
        frame = self.prices()
        chart, volatility = Mock(), Mock()
        self.run_report(frame, days='Mar2026-Apr2026', REPORT_SECTIONS=['technical', 'volatility'],
                        plot_chart=chart, volatility_analysis=volatility)
        indicators, bars = chart.call_args.args[:2]
        inside = frame[(frame['Date'] >= '2026-03-01') & (frame['Date'] <= '2026-04-30')]
        self.assertEqual(bars, len(inside))
        self.assertEqual(indicators['Date'].iloc[-1], inside['Date'].iloc[-1])
        pd.testing.assert_frame_equal(volatility.call_args.args[0], inside.set_index('Date'))
        chart.reset_mock()
        with patch.object(self.module.sys, 'stdout', new_callable=io.StringIO) as output:
            self.run_report(frame, days='Jan2030', plot_chart=chart)
        chart.assert_not_called()
        self.assertIn('No TEST observations in window Jan2030', output.getvalue())

    def test_max_pain_page_follows_the_technical_page_for_the_range_end(self):
        frame = self.prices()
        order = []
        pages = {name: Mock(side_effect=lambda *args, name=name, **kwargs: order.append(name))
                 for name in ('plot_chart', 'max_pain_analysis', 'trendline_analysis')}
        self.run_report(frame, days='350d-25d', REPORT_SECTIONS=['trendlines', 'max_pain', 'technical'], **pages)
        self.assertEqual(order, ['plot_chart', 'max_pain_analysis', 'trendline_analysis'])
        self.assertEqual(pages['max_pain_analysis'].call_args.args[:2], ('TEST', frame['Date'].iloc[-26]))
        self.assertEqual(pages['max_pain_analysis'].call_args.kwargs['start'], frame['Date'].iloc[-350])
        pages['max_pain_analysis'].side_effect = ValueError('no TEST options in the month to 22 Oct 2026')
        with patch.object(self.module.sys, 'stdout', new_callable=io.StringIO) as output:
            self.run_report(frame, REPORT_SECTIONS=['max_pain'], max_pain_analysis=pages['max_pain_analysis'])
        self.assertIn('[max pain skipped] no TEST options', output.getvalue())

    def test_swing_pages_follow_the_technical_page_on_history_to_the_range_end(self):
        frame = self.prices()
        names = ('plot_chart', 'candlestick_analysis', 'swing_structure_analysis', 'pivot_analysis',
                 'formation_analysis', 'max_pain_analysis')
        order = []
        pages = {name: Mock(side_effect=lambda *args, name=name, **kwargs: order.append(name)) for name in names}
        self.run_report(frame, REPORT_SECTIONS=['max_pain', 'formations', 'pivots', 'swing_structure',
                                                'candlesticks', 'technical'], **pages)
        self.assertEqual(order, list(names))
        six_months = int((frame['Date'] >= pd.Timestamp('2026-04-22')).sum())
        for name in names[1:5]:
            history, ticker, bars = pages[name].call_args.args
            pd.testing.assert_frame_equal(history, frame.set_index('Date'))
            self.assertEqual((ticker, bars), ('TEST', six_months))

        self.run_report(frame, days='350d-25d', REPORT_SECTIONS=['pivots'], **pages)
        history, _, bars = pages['pivot_analysis'].call_args.args
        pd.testing.assert_frame_equal(history, frame.set_index('Date').iloc[:-25])  # nothing after the range end
        self.assertEqual(bars, 325)

        pages['pivot_analysis'].side_effect = ValueError('only 3 bars; a pivot needs 5 bars on each side')
        pages['formation_analysis'].reset_mock()
        with patch.object(self.module.sys, 'stdout', new_callable=io.StringIO) as output:
            self.run_report(frame, REPORT_SECTIONS=['pivots', 'formations'], **pages)
        self.assertIn('[pivots skipped] only 3 bars', output.getvalue())
        pages['formation_analysis'].assert_called_once()

    def test_analysis_rejects_nonpositive_windows_before_opening_a_pdf(self):
        for days in (0, -1):
            with self.subTest(days=days), patch.object(self.module, 'PdfPages') as document:
                with self.assertRaisesRegex(ValueError, 'observations must be positive'):
                    self.module.FnOAnalysis(single_scrip='TEST', pdf_path='unused.pdf', days=days)
                document.assert_not_called()

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


@unittest.skipUnless(importlib.util.find_spec('pandas_ta_classic') and importlib.util.find_spec('swingtrend'),
                     'the swing pages need pandas-ta-classic and swingtrend')
class SwingPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import matplotlib
        matplotlib.use('Agg')
        spec = importlib.util.spec_from_file_location(
            'ogn_swing_pages_test', Path(__file__).with_name('Option-OGN.py'))
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    @staticmethod
    def bars(knots, lead=40, spread=0.3):
        """Flat closes at 100, then straight runs to each (target, sessions); bars open at the prior close."""
        path = [100.0] * lead
        for target, steps in knots:
            path.extend(np.linspace(path[-1], target, steps + 1)[1:])
        close = np.asarray(path)
        opening = np.concatenate([[close[0]], close[:-1]])
        return pd.DataFrame({'Symbol': 'TEST', 'Open': opening, 'High': np.maximum(opening, close) + spread,
                             'Low': np.minimum(opening, close) - spread, 'Close': close},
                            index=pd.bdate_range('2026-03-02', periods=len(close)))

    def test_candlestick_signals_carry_direction_and_follow_through_without_look_ahead(self):
        close = np.linspace(120, 100, 40)
        frame = pd.DataFrame({'Open': close + 0.5, 'High': close + 1.0, 'Low': close - 1.0, 'Close': close},
                             index=pd.bdate_range('2026-01-01', periods=40))
        frame.iloc[30] = [104.5, 105.0, 102.8, 103.0]
        frame.iloc[31] = [102.5, 106.0, 102.2, 105.5]  # Bullish engulfing
        frame.iloc[35] = [101.0, 101.3, 96.0, 101.2]   # Hammer after the decline
        signals = self.module.compute_candlestick_signals(frame.iloc[:36], 15)['signals']  # Ends on the hammer
        self.assertEqual(signals[['Date', 'Direction']].values.tolist(),
                         [[frame.index[31], 'Bullish'], [frame.index[35], 'Bullish']])
        self.assertEqual(signals['Bullish'].tolist(), [['Engulfing'], ['Hammer']])
        self.assertEqual(signals['Follow-through'].tolist(), [f'Failed {frame.index[35]:%d %b}', 'Pending'])

        full = self.module.compute_candlestick_signals(frame, 15)['signals']
        self.assertEqual(full['Date'].tolist(), signals['Date'].tolist())  # Later bars change no signal
        self.assertEqual(full['Follow-through'].iloc[1], f'Confirmed {frame.index[36]:%d %b}')  # Close above 101.3

        with self.assertRaisesRegex(ValueError, 'real open/high/low/close'):
            self.module.compute_candlestick_signals(frame.assign(Open=close, High=close, Low=close), 15)
        with patch.object(self.module, 'HAS_PANDAS_TA', False), \
                self.assertRaisesRegex(ValueError, 'pip install pandas-ta-classic'):
            self.module.compute_candlestick_signals(frame, 15)

    def test_swing_structure_follows_breaks_and_reversals_bar_by_bar(self):
        path = np.concatenate([np.linspace(100, 120, 15), np.linspace(120, 110, 6), np.linspace(110, 126, 12),
                               np.linspace(126, 118, 5), np.linspace(118, 130, 8), np.linspace(130, 100, 14)])
        # Close before High: swingtrend's own run() would read these columns by position.
        frame = pd.DataFrame({'Symbol': 'TEST', 'Close': path, 'High': path + 0.6, 'Low': path - 0.6,
                              'Open': path}, index=pd.bdate_range('2026-01-01', periods=len(path)))
        profile = self.module.compute_swing_structure(frame, 30)
        events = profile['events']
        self.assertEqual(events[['Date', 'Event', 'Trend']].values.tolist(), [
            [pd.Timestamp('2026-02-11'), 'BOS', 'UP'], [pd.Timestamp('2026-03-04'), 'BOS', 'UP'],
            [pd.Timestamp('2026-03-16'), 'Reversal', 'DOWN']])
        np.testing.assert_allclose(events['Level'], [120.6, 126.6, 117.4])
        current = profile['current']
        self.assertEqual((current['trend'], current['since'], current['legs']),
                         ('DOWN', pd.Timestamp('2026-03-16'), 0))
        self.assertAlmostEqual(current['coc'], 130.6)
        self.assertIsNone(current['breakout'])  # Still making new lows: no swing point to break yet
        self.assertEqual(len(profile['shown']), 30)
        self.assertTrue(profile['state'].loc['2026-03-16':, 'Trend'].eq('DOWN').all())
        with self.assertRaisesRegex(ValueError, 'positive'):
            self.module.compute_swing_structure(frame.assign(Low=path - 200), 30)

    def test_confirmed_pivots_skip_unconfirmed_edges_plateaus_and_flat_stretches(self):
        path = np.array([5] * 12 + [6, 7, 8, 9, 10, 9, 8, 7, 6, 5, 6, 7, 8, 9, 9, 8, 7, 6, 5, 4, 5, 6, 7, 8, 10, 9],
                        dtype=float)
        frame = pd.DataFrame({'Open': path, 'High': path + 0.5, 'Low': path - 0.5, 'Close': path},
                             index=pd.bdate_range('2026-06-01', periods=len(path)))
        highs, lows = self.module.confirmed_pivots(frame)
        self.assertEqual(highs.tolist(), [16, 25])    # Equal highs 25-26 count once; 36 lacks five later bars
        self.assertEqual(lows.tolist(), [7, 21, 31])  # The flat base has one low, where it starts to lift
        profile = self.module.compute_pivot_levels(frame, len(frame))
        self.assertEqual((profile['resistance'], profile['support']), (9.5, 4.5))
        self.assertEqual(profile['structure'], 'lower high and lower low: down-trend structure')
        recent = self.module.compute_pivot_levels(frame, 15)
        self.assertEqual([(position, price) for position, price, _ in recent['lows']], [(8, 3.5)])
        with self.assertRaisesRegex(ValueError, 'a pivot needs 5 bars'):
            self.module.compute_pivot_levels(frame.head(10), 10)

    def test_formations_follow_the_atr_rules_and_reject_misfit_triangles(self):
        shoulders = self.module.compute_formations(
            self.bars([(110, 8), (103, 7), (116, 9), (106, 8), (110.5, 7), (101, 10)]), 120)
        formation, = shoulders['formations']  # LS-H-RS highs are not also a flat triangle top
        self.assertEqual((formation['Pattern'], formation['Bias'], shoulders['basis']),
                         ('Head and Shoulders', 'Bearish', 'ATR(14)'))
        self.assertEqual([point['Label'] for point in formation['Points']], ['LS', 'H', 'RS'])
        np.testing.assert_allclose([point['Price'] for point in formation['Points']], [110.3, 116.3, 110.8])
        self.assertAlmostEqual(formation['Neckline'], 102.7)  # Lowest low from shoulder to shoulder
        self.assertEqual(formation['Status'], 'Confirmed: close below the neckline')

        triangle = self.module.compute_formations(
            self.bars([(110, 8), (100, 8), (110, 8), (103, 8), (110, 8), (106, 8), (108, 4)]), 120)
        self.assertEqual([(f['Pattern'], f['Bias'], f['Status']) for f in triangle['formations']], [
            ('Double Top', 'Bearish', 'Watching: needs a close below 102.70'),
            ('Ascending Triangle', 'Bullish', 'Inside: watch 103.77 / 110.30')])
        self.assertEqual(self.module.compute_formations(self.bars([(130, 60)]), 120)['formations'], [])

    def test_each_page_draws_chart_tables_and_reading_notes_inside_the_page(self):
        generator = np.random.default_rng(7)
        dates = pd.bdate_range(end='2026-11-20', periods=400)
        close = 24000 * np.exp(np.cumsum(generator.normal(0.0002, 0.011, len(dates))))
        opening = np.concatenate([[close[0]], close[:-1]]) * (1 + generator.normal(0, 0.003, len(dates)))
        spread = np.abs(generator.normal(0, 0.006, len(dates))) * close
        frame = pd.DataFrame({'Open': opening, 'High': np.maximum(opening, close) + spread,
                              'Low': np.minimum(opening, close) - spread, 'Close': close}, index=dates)
        pages = [('Candlestick Reversal Setups', self.module.candlestick_analysis),
                 ('Swing Structure', self.module.swing_structure_analysis),
                 ('Confirmed Pivot Highs & Lows', self.module.pivot_analysis),
                 ('Geometric Formations', self.module.formation_analysis)]
        for title, page in pages:
            with self.subTest(page=title), patch.object(self.module.sys, 'stdout', new_callable=io.StringIO):
                document = Mock()
                page(frame, 'TEST', 126, pdf_pages=document)
                figure = document.savefig.call_args.args[0]
                self.assertIn(f'TEST   {title}   |   ', figure.get_suptitle())
                self.assertTrue({'How to read this page', 'What you see', 'How to read', 'Now'}
                                <= {text.get_text() for text in figure.texts})
                chart = figure.axes[0]
                self.assertEqual(chart.get_xlim(), (-1.0, 126.0))  # The last 126 sessions, without gaps
                tables = [axes for axes in figure.axes if axes.tables]
                self.assertTrue(tables)
                figure.canvas.draw()
                renderer = figure.canvas.get_renderer()
                blocks = [text.get_window_extent(renderer) for text in figure.texts if text.get_text()]
                blocks += [axes.get_tightbbox(renderer) for axes in tables]
                for box in blocks:
                    self.assertTrue(figure.bbox.x0 <= box.x0 and box.x1 <= figure.bbox.x1
                                    and figure.bbox.y0 <= box.y0 and box.y1 <= figure.bbox.y1)
                for first, second in itertools.combinations(blocks, 2):
                    self.assertFalse(first.overlaps(second))
                area = chart.get_window_extent(renderer)
                for text in chart.texts:
                    box = text.get_window_extent(renderer)
                    if text.get_text():
                        self.assertTrue(area.x0 <= box.x0 and box.x1 <= area.x1
                                        and area.y0 <= box.y0 and box.y1 <= area.y1, text.get_text())
        self.assertFalse(self.module.plt.get_fignums())


if __name__ == '__main__':
    unittest.main()
