"""Date x-axes that leave out days without data.

Daily observations (prices, rates, option IV) are drawn at consecutive x
positions, so weekends, exchange holidays and any other day without data take
no space on the chart. Ticks fall on the first trading day of a week, month,
quarter or year, and labels and the cursor readout still show dates.

Weekly and slower series keep a calendar axis: they have no weekend or holiday
gaps, and calendar spacing keeps a genuinely missing period visible.

    axis = DateAxis(frame.index)
    ax.plot(axis.x(frame.index), frame['Close'])
    axis.format(ax)
"""

import numpy as np
import pandas as pd
from matplotlib.dates import AutoDateLocator, ConciseDateFormatter, DateFormatter, date2num
from matplotlib.ticker import Formatter, Locator

# Largest median spacing, in calendar days, still treated as daily data:
# trading days are 1 apart (3 across a weekend), weekly data is 7 apart.
DAILY_MAX_MEDIAN_GAP_DAYS = 4
DEFAULT_MAX_TICKS = 8


def as_dates(values) -> pd.DatetimeIndex:
    """Timezone-naive midnight timestamps; unparseable values become NaT."""
    dates = pd.DatetimeIndex(pd.to_datetime(values, errors='coerce'))
    if dates.tz is not None:
        dates = dates.tz_localize(None)
    return dates.normalize()


def _day_numbers(dates) -> np.ndarray:
    """Whole days since 1970-01-01, whatever unit pandas stores the dates in."""
    return np.asarray(dates.to_numpy().astype('datetime64[D]').astype(np.int64))


def is_daily(dates) -> bool:
    """True when observations are a day apart, apart from weekends and holidays."""
    unique = as_dates(dates).dropna().unique().sort_values()
    if len(unique) < 2:
        return True
    return float(np.median(np.diff(_day_numbers(unique)))) <= DAILY_MAX_MEDIAN_GAP_DAYS


class DateAxis:
    """Maps dates to x coordinates, without gaps for daily data.

    `skip_gaps=None` decides from the data (see is_daily); True or False forces
    trading-day positions or a calendar axis.
    """

    def __init__(self, dates, skip_gaps=None):
        self.dates = as_dates(dates).dropna().unique().sort_values()
        self.skips_gaps = is_daily(self.dates) if skip_gaps is None else bool(skip_gaps)
        self._days = _day_numbers(self.dates)

    def x(self, dates) -> np.ndarray:
        """x coordinates of `dates`: positions on a trading-day axis, date numbers otherwise.

        Dates that are not on the axis sit between their neighbours, or a
        business day apart beyond either end; missing dates give NaN.
        """
        values = as_dates(dates)
        known = ~values.isna()
        result = np.full(len(values), np.nan)
        if not known.any():
            return result
        if not self.skips_gaps:
            result[known] = date2num(values[known].to_numpy())
            return result
        if len(self.dates) == 0:
            return result
        days = np.zeros(len(values), dtype=np.int64)
        days[known] = _day_numbers(values[known])
        positions = np.searchsorted(self._days, days)
        on_axis = known & (positions < len(self._days))
        on_axis[on_axis] = self._days[positions[on_axis]] == days[on_axis]
        result[on_axis] = positions[on_axis]
        between = known & ~on_axis
        if between.any():
            result[between] = self._between(days[between])
        return result

    def _between(self, days: np.ndarray) -> np.ndarray:
        first, last = self._days[0], self._days[-1]
        result = np.interp(days, self._days, np.arange(len(self._days), dtype=float))
        before, after = days < first, days > last
        as_day = lambda number: np.asarray(number, dtype='datetime64[D]')
        result[before] = -np.busday_count(as_day(days[before]), as_day(first)).astype(float)
        result[after] = len(self._days) - 1 + np.busday_count(as_day(last), as_day(days[after])).astype(float)
        return result

    def format(self, axes, max_ticks=DEFAULT_MAX_TICKS, date_format=None):
        """Puts date ticks on `axes`, and on every axes sharing its x-axis.

        `date_format` is a strftime pattern for every label; by default labels
        show day and month, month, or year to suit the visible span, with the
        year added where it changes.
        """
        if self.skips_gaps:
            locator = TradingDayLocator(self.dates, max_ticks)
            formatter = TradingDayFormatter(self.dates, date_format)
        else:
            locator = AutoDateLocator(minticks=3, maxticks=max_ticks)
            formatter = DateFormatter(date_format) if date_format else ConciseDateFormatter(locator)
        axes.xaxis.set_major_locator(locator)
        axes.xaxis.set_major_formatter(formatter)
        return axes


class TradingDayLocator(Locator):
    """Ticks on the first trading day of each week, month, quarter or year.

    Picks the finest of these that leaves at most `max_ticks` ticks in view,
    and ticks every observation when that many fit. Recomputed on zoom.
    """

    # (period, step) from finest to coarsest; a step keeps every n-th period.
    LEVELS = (('week', 1), ('week', 2), ('month', 1), ('month', 2), ('quarter', 1), ('half', 1),
              ('year', 1), ('year', 2), ('year', 5), ('year', 10), ('year', 20),
              ('year', 50), ('year', 100))

    def __init__(self, dates, max_ticks=DEFAULT_MAX_TICKS):
        self.dates = dates
        self.max_ticks = max(2, int(max_ticks))
        self._starts = {}

    def __call__(self):
        vmin, vmax = self.axis.get_view_interval()
        return self.tick_values(vmin, vmax)

    def tick_values(self, vmin, vmax):
        count = len(self.dates)
        low = max(0, int(np.ceil(min(vmin, vmax))))
        high = min(count - 1, int(np.floor(max(vmin, vmax))))
        if count == 0 or high < low:
            return np.array([])
        if high - low + 1 <= self.max_ticks:
            return np.arange(low, high + 1, dtype=float)
        for level in self.LEVELS:
            starts = self._period_starts(*level)
            visible = starts[(starts >= low) & (starts <= high)]
            if 2 <= len(visible) <= self.max_ticks:
                return visible.astype(float)
        return np.unique(np.linspace(low, high, self.max_ticks).round())

    def _period_starts(self, period, step):
        """Positions of the first trading day of each period on the axis."""
        if (period, step) not in self._starts:
            years = self.dates.year.to_numpy()
            months = self.dates.month.to_numpy() - 1
            keys = {
                'week': (_day_numbers(self.dates) + 3) // 7,   # Monday-start weeks
                'month': years * 12 + months,
                'quarter': years * 4 + months // 3,
                'half': years * 2 + months // 6,
                'year': years,
            }[period]
            starts = np.flatnonzero(np.diff(keys) != 0) + 1
            # The first date starts a period only if no weekday of it came before.
            first = self.dates[0]
            period_start = {'week': first - pd.Timedelta(days=first.dayofweek),
                            'month': first.replace(day=1),
                            'quarter': first.replace(month=3 * (months[0] // 3) + 1, day=1),
                            'half': first.replace(month=6 * (months[0] // 6) + 1, day=1),
                            'year': first.replace(month=1, day=1)}[period]
            if np.busday_count(period_start.date(), first.date()) == 0:
                starts = np.concatenate([[0], starts])
            starts = starts[keys[starts] % step == 0]
            self._starts[(period, step)] = starts
        return self._starts[(period, step)]


class TradingDayFormatter(Formatter):
    """Labels positions on a trading-day axis with their dates."""

    def __init__(self, dates, date_format=None):
        self.dates = dates
        self.date_format = date_format

    def _date(self, value):
        if value is None or not np.isfinite(value) or len(self.dates) == 0:
            return None
        position = int(round(value))
        return self.dates[position] if 0 <= position < len(self.dates) else None

    def __call__(self, value, pos=None):
        date = self._date(value)
        return '' if date is None else date.strftime(self.date_format or '%d %b %Y')

    def format_ticks(self, values):
        dates = [self._date(value) for value in values]
        if self.date_format:
            return ['' if date is None else date.strftime(self.date_format) for date in dates]
        known = [date for date in dates if date is not None]
        spacing = (float(np.median(np.diff([date.toordinal() for date in known])))
                   if len(known) > 1 else 0.0)
        if spacing >= 300:
            return ['' if date is None else f'{date:%Y}' for date in dates]
        pattern = '%b' if spacing >= 28 else '%d %b'
        labels, previous_year = [], None
        for date in dates:
            if date is None:
                labels.append('')
                continue
            label = date.strftime(pattern)
            if date.year != previous_year:
                label += f'\n{date:%Y}'
                previous_year = date.year
            labels.append(label)
        return labels

    def format_data_short(self, value):
        date = self._date(value)
        return '' if date is None else f'{date:%Y-%m-%d}'
