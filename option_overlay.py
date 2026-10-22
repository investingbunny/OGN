"""Volume-ranked option IV overlays and expiry-specific robust smile diagnostics."""

import warnings
import math

import numpy as np
import pandas as pd
from scipy.stats import median_abs_deviation
from statsmodels.robust.norms import HuberT
from statsmodels.robust.robust_linear_model import RLM

from date_axis import DateAxis

try:
    from vollib.black.implied_volatility import implied_volatility
except ImportError:
    implied_volatility = None


OPTION_TOP_COUNT = 5
OPTION_OUTLIER_COUNT = 2
OPTION_MIN_CONTRACTS = 10
OPTION_MIN_SMILE_POINTS = 12
OPTION_MAD_THRESHOLD = 3.5
OPTION_MIN_IV_SCALE = 0.005
OPTION_HISTORY_DATES = 5
OPTION_DATES_PER_PAGE = 5
OPTION_RATE = 0.065
OPTION_MIN_RV_OBSERVATIONS = 30
OPTION_COLOURS = {'CE': '#15803d', 'PE': '#dc2626'}


def prepare_option_iv(derivatives, ticker, observation_dates, rate=OPTION_RATE,
                       reported_iv_unit='percent', min_contracts=OPTION_MIN_CONTRACTS):
    """Read reported IV or infer Black-76 IV from exactly matched futures prices.

    Prices prefer settlement for both legs, then close for both legs. Tenor is
    actual calendar days / 365 for pricing; expiry day itself is excluded because
    daily data cannot identify its remaining intraday option lifetime.
    """
    if reported_iv_unit not in ('percent', 'decimal'):
        raise ValueError('Reported IV unit must be percent or decimal')
    if not np.isfinite(rate) or not -1 < rate < 1 or min_contracts < 1:
        raise ValueError('Use a finite annual decimal rate between -1 and 1 and positive minimum volume')
    required = {'Date', 'Expiry', 'Symbol', 'Option type', 'Strike Price', 'Contracts'}
    if not required.issubset(derivatives.columns):
        raise ValueError(f'Missing derivatives columns: {sorted(required - set(derivatives.columns))}')
    frame = derivatives[derivatives['Symbol'].astype(str).str.strip().str.upper().eq(ticker.upper())].copy()
    for column in ['Date', 'Expiry']:
        dates = pd.to_datetime(frame[column], errors='coerce')
        if dates.dt.tz is not None:
            dates = dates.dt.tz_localize(None)
        frame[column] = dates.dt.normalize()
    observed = pd.DatetimeIndex(pd.to_datetime(observation_dates, errors='coerce')).dropna()
    if observed.tz is not None:
        observed = observed.tz_localize(None)
    frame = frame[frame['Date'].isin(observed.normalize()) & (frame['Expiry'] > frame['Date'])]
    frame['Option type'] = frame['Option type'].astype(str).str.strip().str.upper()
    for column in ['Strike Price', 'Contracts', 'Settle Price', 'Close']:
        if column not in frame:
            frame[column] = np.nan
        frame[column] = pd.to_numeric(frame[column], errors='coerce')
    instrument = frame.get('Instrument', pd.Series('', index=frame.index)).astype(str).str.strip().str.upper()
    future_mask = instrument.str.startswith('FUT') | instrument.isin(['IDF', 'STF'])
    futures = frame[future_mask & ~frame['Option type'].isin(['CE', 'PE'])].copy()
    if 'Instrument' in futures:
        futures = futures.drop_duplicates(['Date', 'Expiry', 'Instrument'], keep='last')
    ambiguous = futures.duplicated(['Date', 'Expiry'], keep=False)
    futures = futures[~ambiguous][['Date', 'Expiry', 'Settle Price', 'Close']].rename(
        columns={'Settle Price': 'Forward settlement', 'Close': 'Forward close'})
    options = frame[frame['Option type'].isin(['CE', 'PE'])].copy()
    eligible = (np.isfinite(options[['Strike Price', 'Contracts']]).all(axis=1)
                & (options['Strike Price'] > 0) & (options['Contracts'] >= min_contracts))
    options = options[eligible].drop_duplicates(
        ['Date', 'Expiry', 'Option type', 'Strike Price'], keep='last')
    options = options.merge(futures, on=['Date', 'Expiry'], how='left', validate='many_to_one')
    iv_column = next((name for name in ['Implied Volatility', 'IV'] if name in options), None)
    reported = pd.Series(np.nan, index=options.index, dtype=float)
    if iv_column is not None:
        text = options[iv_column].astype('string').str.strip()
        if reported_iv_unit == 'decimal' and text.str.endswith('%').fillna(False).any():
            raise ValueError('Percent-suffixed IV conflicts with the requested decimal unit')
        reported = pd.to_numeric(text.str.rstrip('%').str.replace(',', '', regex=False), errors='coerce')
        reported = reported.astype(float) / (100.0 if reported_iv_unit == 'percent' else 1.0)
    options['IV'] = reported.where(np.isfinite(reported) & (reported > 0))
    options['IV source'] = np.where(options['IV'].notna(), 'Reported', '')
    options['Premium'] = np.nan
    options['Forward'] = np.nan
    options['Price basis'] = ''
    options['Calendar days'] = (options['Expiry'] - options['Date']).dt.days
    options['Tenor sessions'] = np.busday_count(
        options['Date'].to_numpy().astype('datetime64[D]'),
        options['Expiry'].to_numpy().astype('datetime64[D]'))
    diagnostics = {
        'eligible_contracts': len(options), 'reported_iv': int(options['IV'].notna().sum()),
        'estimated_iv': 0, 'missing_forward': 0, 'invalid_premium': 0,
        'solver_failures': 0, 'ambiguous_futures': int(ambiguous.sum()),
        'solver_unavailable': implied_volatility is None,
    }
    for position, contract in options[options['IV'].isna()].iterrows():
        forward = np.nan
        premium = np.nan
        basis = ''
        for price_column, forward_column, name in [
                ('Settle Price', 'Forward settlement', 'Settlement'),
                ('Close', 'Forward close', 'Close')]:
            candidate_forward = contract[forward_column]
            candidate_premium = contract[price_column]
            if (np.isfinite(candidate_forward) and candidate_forward > 0
                    and np.isfinite(candidate_premium) and candidate_premium > 0):
                forward, premium, basis = candidate_forward, candidate_premium, name
                break
        if not basis:
            forward_quotes = contract[['Forward settlement', 'Forward close']].to_numpy(dtype=float)
            key = 'invalid_premium' if ((forward_quotes > 0) & np.isfinite(forward_quotes)).any() else 'missing_forward'
            diagnostics[key] += 1
            continue
        strike = float(contract['Strike Price'])
        lifetime = float(contract['Calendar days']) / 365.0
        discount = math.exp(-rate * lifetime)
        call = contract['Option type'] == 'CE'
        lower = discount * max(forward - strike if call else strike - forward, 0.0)
        upper = discount * (forward if call else strike)
        tolerance = max(forward, strike) * 1e-12
        if not lower + tolerance < premium < upper - tolerance:
            diagnostics['invalid_premium'] += 1
            continue
        if implied_volatility is None:
            continue
        try:
            implied = float(implied_volatility(premium, forward, strike, rate, lifetime, 'c' if call else 'p'))
            if not np.isfinite(implied) or implied <= 0:
                raise ValueError('No positive finite implied volatility')
        except Exception:
            diagnostics['solver_failures'] += 1
            continue
        options.loc[position, ['IV', 'Premium', 'Forward', 'Price basis', 'IV source']] = [
            implied, premium, forward, basis, 'Black-76 estimate']
        diagnostics['estimated_iv'] += 1
    return options[options['IV'].notna()].reset_index(drop=True), diagnostics


def score_option_smile(group, min_points=OPTION_MIN_SMILE_POINTS):
    """Score IV residuals from a same-date, same-expiry, same-side robust smile.

    IV is an annualized decimal, not percent. A quadratic in centered log strike
    captures the local smile; a constant forward shift leaves this fit unchanged.
    End strikes cannot be outlier candidates because they lack two-sided support.
    """
    result = group.copy()
    result['Smile IV'] = np.nan
    result['MAD score'] = np.nan
    result['Smile supported'] = False
    if len(result) < min_points or result['Strike Price'].nunique() < min_points:
        return result
    strikes = result['Strike Price'].to_numpy(dtype=float)
    implied = result['IV'].to_numpy(dtype=float)
    coordinates = np.log(strikes / np.median(strikes))
    spread = np.std(coordinates)
    if not np.isfinite(spread) or spread <= 0:
        return result
    coordinates = coordinates / spread
    design = np.column_stack([np.ones(len(result)), coordinates, coordinates ** 2])
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            fitted = RLM(implied, design, M=HuberT()).fit(maxiter=100)
        predicted = np.asarray(fitted.predict(design), dtype=float)
        if not np.isfinite(predicted).all() or fitted.fit_history.get('iteration', 0) >= 100:
            return result
    except (ValueError, np.linalg.LinAlgError, ZeroDivisionError):
        return result
    residuals = implied - predicted
    scale = max(float(median_abs_deviation(residuals, scale='normal')), OPTION_MIN_IV_SCALE)
    scores = (residuals - np.median(residuals)) / scale
    ordered_strikes = np.sort(np.unique(strikes))
    supported = (strikes >= ordered_strikes[2]) & (strikes <= ordered_strikes[-3])
    result['Smile IV'] = predicted
    result['MAD score'] = scores
    result['Smile supported'] = supported & (predicted > 0)
    return result


def select_option_points(chain, top_count=OPTION_TOP_COUNT,
                         outlier_count=OPTION_OUTLIER_COUNT,
                         min_contracts=OPTION_MIN_CONTRACTS,
                         mad_threshold=OPTION_MAD_THRESHOLD):
    """Select top-volume and up to two additional MAD outliers per side/expiry/date."""
    if top_count < 1 or outlier_count < 0 or min_contracts < 1 or mad_threshold <= 0:
        raise ValueError('Option selection parameters must be positive; outlier count may be zero')
    required = {'Date', 'Expiry', 'Option type', 'Strike Price', 'Contracts', 'IV'}
    if not required.issubset(chain.columns):
        raise ValueError(f'Missing option selection columns: {sorted(required - set(chain.columns))}')
    frame = chain.copy()
    if 'Symbol' in frame and frame['Symbol'].dropna().nunique() > 1:
        raise ValueError('Select option overlays for one underlying ticker at a time')
    for column in ['Date', 'Expiry']:
        dates = pd.to_datetime(frame[column], errors='coerce')
        if dates.dt.tz is not None:
            dates = dates.dt.tz_localize(None)
        frame[column] = dates.dt.normalize()
    frame['Option type'] = frame['Option type'].astype(str).str.strip().str.upper()
    for column in ['Strike Price', 'Contracts', 'IV']:
        frame[column] = pd.to_numeric(frame[column], errors='coerce')
    frame = frame.dropna(subset=list(required))
    valid = (np.isfinite(frame[['Strike Price', 'Contracts', 'IV']]).all(axis=1)
             & frame['Option type'].isin(['CE', 'PE'])
             & (frame['Contracts'] >= min_contracts)
             & (frame['Strike Price'] > 0) & (frame['IV'] > 0)
             & (frame['Expiry'] > frame['Date']))
    frame = frame[valid].drop_duplicates(
        ['Date', 'Expiry', 'Option type', 'Strike Price'], keep='last').reset_index(drop=True)
    output = []
    for _, group in frame.groupby(['Date', 'Expiry', 'Option type'], sort=True):
        scored = score_option_smile(group) if outlier_count else group.assign(
            **{'Smile IV': np.nan, 'MAD score': np.nan, 'Smile supported': False})
        scored['Is outlier'] = scored['Smile supported'] & (scored['MAD score'].abs() >= mad_threshold)
        ranked = scored.sort_values(['Contracts', 'Strike Price'], ascending=[False, True], kind='stable')
        primary = ranked.head(top_count).copy()
        primary['Selection'] = 'Top volume'
        extra = scored.loc[~scored.index.isin(primary.index) & scored['Is outlier']].copy()
        extra['Absolute score'] = extra['MAD score'].abs()
        extra = extra.sort_values(['Absolute score', 'Contracts', 'Strike Price'],
                                  ascending=[False, False, True], kind='stable').head(outlier_count)
        extra['Selection'] = 'MAD outlier'
        output.extend([primary, extra.drop(columns='Absolute score')])
    if not output:
        return frame.assign(**{'Smile IV': np.nan, 'MAD score': np.nan,
                               'Smile supported': False, 'Is outlier': False, 'Selection': ''})
    return pd.concat(output, ignore_index=True)


def option_point_label(row):
    """Compact strike and expiry label; strike is an identifier, not dot height."""
    strike = format(float(row['Strike Price']), 'g')
    expiry = pd.Timestamp(row['Expiry'])
    return f'({strike}, {expiry.day} {expiry:%b})'


def attach_realized_benchmarks(points, price_data, estimator_function):
    """Compare IV to same-tenor realized history available on the observation date."""
    result = points.copy()
    result['RV mean'] = np.nan
    result['RV std'] = np.nan
    result['RV count'] = 0
    result['IV minus RV'] = np.nan
    if result.empty:
        return result
    history = price_data.copy()
    history.index = pd.DatetimeIndex(pd.to_datetime(history.index, errors='coerce'))
    if history.index.tz is not None:
        history.index = history.index.tz_localize(None)
    history.index = history.index.normalize()
    history = history[history.index.notna()].sort_index()
    if history.index.duplicated().any():
        raise ValueError('Option benchmarks require one underlying OHLC observation per date')
    for (date, tenor), group in result.groupby(['Date', 'Tenor sessions']):
        available = history.loc[history.index <= date]
        if tenor < 2 or len(available) < tenor + OPTION_MIN_RV_OBSERVATIONS:
            continue
        values = estimator_function(available, int(tenor))
        values = pd.to_numeric(values, errors='coerce')
        values = values[np.isfinite(values) & (values >= 0)]
        if len(values) < OPTION_MIN_RV_OBSERVATIONS:
            continue
        result.loc[group.index, ['RV mean', 'RV std', 'RV count']] = [
            float(values.mean()), float(values.std()), len(values)]
    result['IV minus RV'] = result['IV'] - result['RV mean']
    return result


def plot_option_markers(axes, points, x_column, fontsize=10, date_axis=None):
    """Draw side-coloured IV dots, outlined anomalies and collision-adjusted labels.

    With x_column 'Date', a DateAxis places the dates (gap-free for trading
    days); without one they go on a calendar date axis.
    """
    from adjustText import adjust_text
    from matplotlib.dates import date2num

    if points.empty:
        return []
    frame = points.reset_index(drop=True)
    if x_column == 'Date' and date_axis is not None:
        positions = date_axis.x(frame['Date'])
    elif x_column == 'Date':
        positions = np.asarray(date2num(pd.to_datetime(frame['Date']).to_numpy()))
        axes.xaxis_date()
    else:
        positions = frame[x_column].to_numpy(dtype=float)
    implied = frame['IV'].to_numpy(dtype=float)
    for side, colour in OPTION_COLOURS.items():
        mask = frame['Option type'].eq(side).to_numpy()
        if mask.any():
            axes.scatter(positions[mask], implied[mask], s=38, color=colour,
                         marker='o', zorder=5, label=f'{side} IV')
    outliers = frame['Is outlier'].to_numpy(dtype=bool)
    if outliers.any():
        axes.scatter(positions[outliers], implied[outliers], s=100,
                     facecolors='none', edgecolors='#202020', linewidths=1.4,
                     zorder=6, label='Smile MAD outlier')
    padding = max(float(np.ptp(positions)) * 0.08, 0.8)
    left, right = axes.get_xlim()
    axes.set_xlim(min(left, positions.min() - padding), max(right, positions.max() + padding))
    axes.margins(y=0.25)
    legend = axes.legend(fontsize=10, loc='upper right')
    axes.figure.canvas.draw()
    targets = axes.transData.transform(np.column_stack([positions, implied]))
    label_positions = targets.copy()
    line_height = fontsize * axes.figure.dpi / 72.0 * 1.8
    for coordinate in np.unique(positions):
        members = np.flatnonzero(positions == coordinate)
        members = members[np.argsort(implied[members], kind='stable')]
        packed = targets[members, 1] + line_height * 0.6
        for position in range(1, len(packed)):
            packed[position] = max(packed[position], packed[position - 1] + line_height)
        packed -= np.median(packed - targets[members, 1])
        packed -= max(0.0, packed[-1] - (axes.bbox.y1 - line_height))
        packed += max(0.0, axes.bbox.y0 + line_height - packed[0])
        label_positions[members, 1] = packed
    label_positions = axes.transData.inverted().transform(label_positions)
    texts = []
    for position, row in frame.iterrows():
        texts.append(axes.text(
            label_positions[position, 0], label_positions[position, 1],
            option_point_label(row), fontsize=fontsize, color=OPTION_COLOURS[row['Option type']],
            ha='center', va='center', zorder=7,
            bbox={'facecolor': 'white', 'edgecolor': 'none', 'alpha': 0.75, 'pad': 0.25}))
    adjust_text(texts, x=positions, y=implied, target_x=positions, target_y=implied,
                objects=[legend], ax=axes, ensure_inside_axes=True,
                expand=(1.15, 1.30), force_text=(0.3, 0.6),
                force_pull=(0.005, 0.005), max_move=(20, 20), iter_lim=500,
                arrowprops={'arrowstyle': '-', 'color': '#777777', 'lw': 0.5})
    return texts


def plot_option_history(overlay, ticker, pdf_pages=None):
    """One page per expiry keeps changing daily top-volume selections readable."""
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter

    points = overlay['points']
    pages = 0
    page_groups = []
    for expiry, group in points.groupby('Expiry', sort=True):
        dates = sorted(group['Date'].unique())
        for start in range(0, len(dates), OPTION_DATES_PER_PAGE):
            page_groups.append((expiry, group[group['Date'].isin(dates[start:start + OPTION_DATES_PER_PAGE])]))
    for expiry, expiry_points in page_groups:
        figure = plt.figure(figsize=(30, 17), facecolor='white')
        last_date = expiry_points['Date'].max()
        # Both sides share the page's trading dates, without weekend or holiday gaps.
        dates = DateAxis(expiry_points['Date'])
        page_span = dates.x(dates.dates)[[0, -1]] + np.array([-0.5, 0.5])
        figure.suptitle(f'{ticker} | Option IV | Expiry {expiry:%d %b %Y}',
                        fontsize=29, fontweight='bold', y=0.975)
        figure.text(0.05, 0.934,
                    f"Top {overlay['top_count']} CE and PE per expiry/date by contracts | "
                    f"{expiry_points['Date'].nunique()} trading dates | "
                    f"{overlay['estimator']} historical mean at matching weekday tenor",
                    fontsize=14, color='#444444')
        for side, left in [('CE', 0.06), ('PE', 0.55)]:
            axes = figure.add_axes((left, 0.46, 0.40, 0.42))
            side_points = expiry_points[expiry_points['Option type'].eq(side)]
            axes.set_title(f'{side} | Implied vs realized volatility', fontsize=21, fontweight='bold', pad=12)
            axes.set_ylabel('Annualized volatility', fontsize=14)
            axes.grid(alpha=0.25)
            axes.tick_params(labelsize=12)
            axes.yaxis.set_major_formatter(PercentFormatter(xmax=1.0, decimals=0))
            dates.format(axes, max_ticks=OPTION_DATES_PER_PAGE, date_format='%d %b')
            if side_points.empty:
                axes.set_xlim(*page_span)
                axes.text(0.5, 0.5, 'No eligible contracts with valid IV',
                          transform=axes.transAxes, ha='center', va='center', fontsize=15)
                continue
            baseline = side_points.drop_duplicates('Date').sort_values('Date')
            usable = baseline.dropna(subset=['RV mean', 'RV std'])
            if not usable.empty:
                axes.plot(dates.x(usable['Date']), usable['RV mean'], color='#222222', linestyle='--',
                          linewidth=1.6, label='Historical realized mean')
                axes.fill_between(dates.x(usable['Date']), (usable['RV mean'] - usable['RV std']).clip(lower=0),
                                  usable['RV mean'] + usable['RV std'], color='#b5b5b5', alpha=0.18,
                                  label='Realized mean +/- 1 SD')
            plot_option_markers(axes, side_points, 'Date', fontsize=10, date_axis=dates)
        latest = expiry_points[expiry_points['Date'].eq(last_date)].sort_values(
            ['Option type', 'Selection', 'Contracts'], ascending=[True, True, False])
        rows = []
        for _, contract in latest.iterrows():
            rows.append([
                contract['Option type'], format(contract['Strike Price'], 'g'),
                f'{expiry.day} {expiry:%b}', f"{contract['Contracts']:,.0f}",
                f"{contract['IV'] * 100:.2f}", contract['IV source'],
                '--' if pd.isna(contract['RV mean']) else f"{contract['RV mean'] * 100:.2f}",
                '--' if pd.isna(contract['IV minus RV']) else f"{contract['IV minus RV'] * 100:+.2f}",
                '--' if pd.isna(contract['MAD score']) else f"{contract['MAD score']:+.2f}",
                contract['Selection'],
            ])
        table_axes = figure.add_axes((0.05, 0.12, 0.90, 0.25))
        table_axes.axis('off')
        table_axes.set_title(f'Latest selected contracts | {last_date:%d %b %Y}',
                              fontsize=18, fontweight='bold', pad=14)
        table = table_axes.table(
            cellText=rows,
            colLabels=['Side', 'Strike', 'Expiry', 'Contracts', 'IV (%)', 'IV source',
                       'RV mean (%)', 'IV - mean (pp)', 'Smile MAD', 'Selection'],
            colWidths=[0.045, 0.08, 0.075, 0.08, 0.07, 0.17, 0.10, 0.13, 0.09, 0.16],
            cellLoc='left', bbox=(0, 0, 1, 1))
        table.auto_set_font_size(False)
        table.set_fontsize(11)
        for (row_number, _), cell in table.get_celld().items():
            cell.set_edgecolor('#cccccc')
            if row_number == 0:
                cell.set_facecolor('#4472c4')
                cell.set_text_props(color='white', fontweight='bold')
        diagnostics = overlay['diagnostics']
        figure.text(0.05, 0.078,
                    f"Full overlay window, all expiries: {diagnostics['reported_iv']} reported IV, "
                    f"{diagnostics['estimated_iv']} Black-76 estimates; skipped "
                    f"{diagnostics['missing_forward']} missing matched futures, "
                    f"{diagnostics['invalid_premium']} invalid premiums, "
                    f"{diagnostics['solver_failures']} solver failures. Minimum volume: "
                    f"{overlay['min_contracts']} contracts.", fontsize=11, color='#555555')
        figure.text(0.05, 0.054,
                    f"Black-76: annual rate {overlay['rate']:.2%}, ACT/365; realized volatility: 252/year. "
                    'Weekday tenors omit weekends, not exchange holidays. Historical means use no later dates.',
                    fontsize=11, color='#555555')
        figure.text(0.05, 0.03,
                    f"Outlines: |smile residual MAD score| >= {OPTION_MAD_THRESHOLD:g}; "
                    f"up to {overlay['outlier_count']} extra contracts per side/date. "
                    'An IV-minus-realized gap is not itself an outlier, mispricing or a trade signal.',
                    fontsize=11, color='#555555')
        if pdf_pages is not None:
            try:
                pdf_pages.savefig(figure)
            finally:
                plt.close(figure)
        else:
            plt.show()
        pages += 1
    return pages