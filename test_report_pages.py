"""Checks for the volatility guide page and timestamped report files."""

import datetime
import importlib.util
import itertools
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


if __name__ == '__main__':
    unittest.main()
