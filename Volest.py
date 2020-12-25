import datetime
import os
import pyarrow
import pyarrow.feather as feather
import pandas
import numpy
import numpy as np
import statsmodels.api as sm
import matplotlib
import matplotlib.mlab as mlab
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import math
from nsepy.derivatives import get_expiry_date
import datetime
from datetime import date
from dateutil.relativedelta import *
import pandas as pd
import glob

ExpiryDates = []
ExpiryDateList = []

def FindFeather(name, path):
    for root, dirs, files in os.walk(path):
        if name in files:
            return os.path.join(root, name)

def UpdateOptionChainTable(ExpiryDate):
    OptionChain = CurrentDate.strftime("%Y-%m-%d") + '-NIFTYoption-chain-equity-derivatives-'+ ExpiryDate.strftime("%Y-%m-%d") + '.csv'
    
    OptionChainCSVdf = pd.read_csv('./Option chain - Dec 14/'+OptionChain, header = 1)
    OptionChainCSVdf = OptionChainCSVdf.rename(columns=lambda x: x.strip())
    OptionChainCSVdf = OptionChainCSVdf.applymap(lambda x: x.strip() if isinstance(x, str) else x)
    
    OptionChainCSVdf.drop("Unnamed: 0", axis=1, inplace=True)
    OptionChainCSVdf.drop("Unnamed: 22", axis=1, inplace=True)
    CallOptionChaindf = OptionChainCSVdf.iloc[:,0:11]
    PutOptionChaindf = OptionChainCSVdf.iloc[:,10:21]
    if 'IV.1' in PutOptionChaindf.columns:
        PutOptionChaindf.rename(columns={'IV.1': 'IV1'}, inplace=True)
    
    
    CallOptionChainIVdf = CallOptionChaindf[CallOptionChaindf.IV != '-']
    PutOptionChainIVdf = PutOptionChaindf[PutOptionChaindf.IV1 != '-']
    
    # covert IV string to an integer  to plot it
    CallOptionChainIVdf['IV'] = CallOptionChainIVdf['IV'].astype(float) 
    PutOptionChainIVdf['IV1'] = PutOptionChainIVdf['IV1'].astype(float) 
    CallOptionChainIVdf['IV'] = CallOptionChainIVdf['IV'].div(100).round(4)
    PutOptionChainIVdf['IV1'] = PutOptionChainIVdf['IV1'].div(100).round(4)
    #Reset the index
    CallOptionChainIVdf.reset_index(level=0, inplace=True, drop=True)
    PutOptionChainIVdf.reset_index(level=0, inplace=True, drop=True)
    
    CallOptionChainIVdf['Date'] = CurrentDate
    CallOptionChainIVdf['Expiry'] = ExpiryDate
    PutOptionChainIVdf['Date'] = CurrentDate
    PutOptionChainIVdf['Expiry'] = ExpiryDate
    # d = ExpiryDate - CurrentDate Can add this to a column directly?
    CallOptionChainIVdf[['Date','Expiry']] = CallOptionChainIVdf[['Date','Expiry']].apply(pd.to_datetime) #if conversion required
    CallOptionChainIVdf['DaysToExpiry'] = (CallOptionChainIVdf['Expiry'] - CallOptionChainIVdf['Date']).dt.days
    PutOptionChainIVdf[['Date','Expiry']] = PutOptionChainIVdf[['Date','Expiry']].apply(pd.to_datetime) #if conversion required
    PutOptionChainIVdf['DaysToExpiry'] = (PutOptionChainIVdf['Expiry'] - PutOptionChainIVdf['Date']).dt.days

    return CallOptionChainIVdf,PutOptionChainIVdf


#from volatility import models

ESTIMATORS = [
    'GarmanKlass',
    'HodgesTompkins',
    'Kurtosis',
    'Parkinson',
    'Raw',
    'RogersSatchell',
    'Skew',
    'YangZhang'
]
PRICE_COLUMNS = {
    'Open',
    'High',
    'Low',
    'Close'
}


def array_to_dataframe(ndarray):
    return pandas.DataFrame(
        ndarray,
        columns=['Open', 'High', 'Low', 'Close']
    )


class VolatilityEstimator(object):

    def __init__(self, price_data, estimator, bench_data=None):
        """Constructor for volatility estimators
        
        Parameters
        ----------
        price_data: pandas.DataFrame or numpy.ndarray
            If pandas.DataFrame, must include columns Open, High, Low, Close. Also
            must include property symbol with the symbol we're working with. If
            numpy.ndarray, must be of shape (r, 4) with columns in order of open,
            high, low, close prices. If numpy.ndarray, will be coerced to pandas.DataFrame
            with no date data
        estimator : string
            Estimator estimator; valid arguments are:
                "GarmanKlass", "HodgesTompkins", "Kurtosis", "Parkinson", "Raw",
                "RogersSatchell", "Skew", "YangZhang"
        """

        if not isinstance(price_data, numpy.ndarray) and not \
                isinstance(price_data, pandas.DataFrame):
            raise ValueError('price_data must be of type numpy.ndarray or pandas.DataFrame')
        if isinstance(price_data, numpy.ndarray) and price_data.shape[0] != 4:
            raise ValueError('price_data of type numpy.ndarray shape of (r, 4)')
        if isinstance(price_data, pandas.DataFrame) and not \
                PRICE_COLUMNS.issubset(price_data.columns):
            raise ValueError('price_data requires Open, High, Low, Close')
        if price_data.symbol is None:
            raise ValueError('Symbol required as property of price_data')
        if estimator not in ESTIMATORS:
            raise ValueError('Acceptable volatility model is required')

        if isinstance(price_data, numpy.ndarray):
            price_data = array_to_dataframe(price_data)
            price_data.symbol = '-NA-'
            start = price_data.index[0]
            end = price_data.index[0]
        else:
            start = price_data.index[0]#.to_pydatetime().strftime('%Y-%m-%d')
            end = price_data.index[-1]#.to_pydatetime().strftime('%Y-%m-%d')

        if bench_data is not None:
            # if price_data.shape != bench_data.shape:
            #     raise ValueError('price_data and bench_data must be same shape')
            if not isinstance(bench_data, numpy.ndarray) and not \
                    isinstance(bench_data, pandas.DataFrame):
                raise ValueError('bench_data must be of type numpy.ndarray or pandas.DataFrame')
            if isinstance(bench_data, numpy.ndarray) and bench_data.shape[0] != 4:
                raise ValueError('bench_data of type numpy.ndarray shape of (r, 4)')
            if isinstance(bench_data, pandas.DataFrame) and not \
                    PRICE_COLUMNS.issubset(bench_data.columns):
                raise ValueError('bench_data requires Open, High, Low, Close')
            if bench_data.symbol is None:
                raise ValueError('Symbol required as property of bench_data')

            # bench_data = bench_data.loc[start:end]

            if isinstance(bench_data, numpy.ndarray):
                bench_data = array_to_dataframe(bench_data)
                bench_data.symbol = '-NA-'

            self._bench_data = bench_data
            self._bench_symbol = bench_data.symbol

        self._price_data = price_data
        self._symbol = price_data.symbol
        self._start = start
        self._end = end
        self._estimator = estimator
        
        matplotlib.rc('image', origin='upper')

        matplotlib.rcParams['font.size'] = '11'
        
        matplotlib.rcParams['grid.color'] = 'lightgrey'
        matplotlib.rcParams['grid.linestyle'] = '-'
        
        matplotlib.rcParams['figure.subplot.left'] = 0.1
        matplotlib.rcParams['figure.subplot.bottom'] = 0.13
        matplotlib.rcParams['figure.subplot.right'] = 0.9
        matplotlib.rcParams['figure.subplot.top'] = 0.9

    def _get_estimator(self, window, price_data, clean=True):
        """Selector for volatility estimator
        
        Parameters
        ----------
        window : int
            Rolling window for which to calculate the estimator
        clean : boolean
            Set to True to remove the NaNs at the beginning of the series
        
        Returns
        -------
        y : pandas.DataFrame
            Estimator series values
        """

        return get_estimator(
            price_data=price_data,
            window=window,
            clean=clean
        )
   
    def cones(self, windows=[30, 60, 90, 120], quantiles=[0.25, 0.75]):
        """Plots volatility cones
        
        Parameters
        ----------
        windows : [int, int, ...]
            List of rolling windows for which to calculate the estimator cones
        quantiles : [lower, upper]
            List of lower and upper quantiles for which to plot the cones
        """

        price_data = self._price_data

        if len(windows) < 2:
            raise ValueError(
                'Two or more window periods required')
        if len(quantiles) != 2:
            raise ValueError(
                'A two element list of quantiles is required, lower and upper')
        if quantiles[0] + quantiles[1] != 1.0:
            raise ValueError(
                'The sum of the quantiles must equal 1.0')
        if quantiles[0] > quantiles[1]:
            raise ValueError(
                'The lower quantiles (first element) must be less than the upper quantile (second element)')
        
        max_ = []
        min_ = []
        top_q = []
        median = []
        bottom_q = []
        realized = []
        data = []

        for window in windows:
            
            estimator = self._get_estimator(
                window=window,
                price_data=price_data
            )

            max_.append(estimator.max())
            top_q.append(estimator.quantile(quantiles[1]))
            median.append(estimator.median())
            bottom_q.append(estimator.quantile(quantiles[0]))
            min_.append(estimator.min())
            realized.append(estimator[-1])

            data.append(estimator)

        if self._estimator is "Skew" or self._estimator is "Kurtosis":
            f = lambda x: "%i" % round(x, 0)
        else:
            f = lambda x: "%i%%" % round(x*100, 0)
        # print(*data, sep='\n')
        # print("The length of list is: ", len(data)) 
        # figure
        fig = plt.figure(figsize=(8, 6))
        fig.autofmt_xdate()
        left, width = 0.07, 0.65
        bottom, height = 0.2, 0.7
        left_h = left+width+0.02
        rect_cones = [left, bottom, width, height]
        rect_box = [left_h, bottom, 0.17, height]
        cones = fig.add_axes(rect_cones)
        box = fig.add_axes(rect_box)

        # set the plots
        cones.plot(windows, max_, label="Max")
        cones.plot(windows, top_q, label=str(int(quantiles[1]*100)) + " Prctl")
        cones.plot(windows, median, label="Median")
        cones.plot(windows, bottom_q, label=str(int(quantiles[0]*100)) + " Prctl")
        cones.plot(windows, min_, label="Min")
        cones.plot(windows, realized, 'r-.', label="Realized")
        
        for i in ExpiryDateList:
                if i > CurrentDate:
                    try:
                        CallOptionChainIVdf, PutOptionChainIVdf = UpdateOptionChainTable(i)
                        cones.scatter(CallOptionChainIVdf['DaysToExpiry'],CallOptionChainIVdf['IV'],color='g')
                        cones.scatter(PutOptionChainIVdf['DaysToExpiry'],PutOptionChainIVdf['IV1'],color='r')
                    except:
                        print('Couldnt update table for date'+i.strftime("%Y%m%d"))

        # set the x ticks and limits
        cones.set_xticks(windows)
        cones.set_xlim((windows[0]-5, windows[-1]+5))

        # set and format the y-axis labels
        locs = cones.get_yticks()
        cones.set_yticklabels(map(f, locs))

        # turn on the grid
        cones.grid(True, axis='y', which='major', alpha=0.5)

        # set the title
        # cones.set_title(self._estimator + ' (' + self._symbol + ', daily ' + self._start.strftime("%Y%m%d") + ' to ' + self._end.strftime("%Y%m%d") + ')')

        # set the legend
        cones.legend()#loc='upper center', bbox_to_anchor=(0.5, -0.05), ncol=3)

        # box plot
        box.boxplot(data, notch=1, sym='+')
        box.plot([i for i in range(1, len(windows)+1)], realized, color='r', marker='*', markeredgecolor='k')

        # set and format the y-axis labels
        locs = box.get_yticks()
        box.set_yticklabels(map(f, locs))

        # move the y-axis ticks on the right side
        box.yaxis.tick_right()

        # turn on the grid
        box.grid(True, axis='y', which='major', alpha=0.5)
        
        return fig, plt


        
def get_estimator(price_data, window=30, trading_periods=252, clean=True):

    log_ho = (price_data['High'] / price_data['Open']).apply(np.log)
    log_lo = (price_data['Low'] / price_data['Open']).apply(np.log)
    log_co = (price_data['Close'] / price_data['Open']).apply(np.log)
    
    log_oc = (price_data['Open'] / price_data['Close'].shift(1)).apply(np.log)
    log_oc_sq = log_oc**2
    
    log_cc = (price_data['Close'] / price_data['Close'].shift(1)).apply(np.log)
    log_cc_sq = log_cc**2
    
    rs = log_ho * (log_ho - log_co) + log_lo * (log_lo - log_co)
    
    close_vol = log_cc_sq.rolling(
        window=window,
        center=False
    ).sum() * (1.0 / (window - 1.0))
    open_vol = log_oc_sq.rolling(
        window=window,
        center=False
    ).sum() * (1.0 / (window - 1.0))
    window_rs = rs.rolling(
        window=window,
        center=False
    ).sum() * (1.0 / (window - 1.0))

    k = 0.34 / (1 + (window + 1) / (window - 1))
    result = (open_vol + k * close_vol + (1 - k) * window_rs).apply(np.sqrt) * math.sqrt(trading_periods)

    if clean:
        return result.dropna()
    else:
        return result 


# ESTIMATORS = [
#     'GarmanKlass',
#     'HodgesTompkins',
#     'Kurtosis',
#     'Parkinson',
#     'Raw',
#     'RogersSatchell',
#     'Skew',
#     'YangZhang'
# ]

# data
sym = 'NIFTY'
# bench = '^GSPC'
data_file_path = './Datastore/'+sym+'_ohlc.ftr'
bench_file_path = './Datastore/NIFTY_ohlc.ftr'
est = 'Parkinson'

CurrentDate = datetime.date.today()
CurrentDay = CurrentDate.day

path = './Option chain - Dec 14/' # use your path
all_files = glob.glob(path + CurrentDate.strftime("%Y-%m-%d") + "*.csv")

ExpiryDateList.clear()
for filename in all_files:
    Edate = datetime.datetime.strptime(filename[72:82], '%Y-%m-%d').date()
    ExpiryDateList.append(Edate)

# estimator windows
window = 30
windows = [3, 5, 10, 20, 30, 60, 90]
quantiles = [0.25, 0.75]
bins = 100
normed = True

# use the yahoo helper to correctly format data from finance.yahoo.com
price_data = feather.read_feather(data_file_path)
price_data = price_data.iloc[-1000:]
if 'Symbol' in price_data.columns:
    price_data.rename(columns={'Symbol': 'symbol'}, inplace=True)
price_data = price_data.assign(symbol=sym)        
price_data = price_data.set_index('Date')
        
bench_data = feather.read_feather(bench_file_path)
bench_data = bench_data.iloc[-1000:]
if 'Symbol' in bench_data.columns:
    bench_data.rename(columns={'Symbol': 'symbol'}, inplace=True)
bench_data = bench_data.assign(symbol='NIFTY')        
bench_data = bench_data.set_index('Date')

# spx_price_data = data.yahoo_helper(bench, bench_file_path)

# initialize class
vol = VolatilityEstimator(
    price_data=price_data,
    estimator=est,
    bench_data=None #bench_data
)

# call plt.show() on any of the below...
_, plt = vol.cones(windows=windows, quantiles=quantiles)

# plt = vol.rolling_quantiles(window=window, quantiles=quantiles)
# plt = vol.rolling_extremes(window=window)
# plt = vol.rolling_descriptives(window=window)
# plt = vol.histogram(window=window, bins=bins, normed=normed)

# plt = vol.benchmark_compare(window=window)
# plt = vol.benchmark_correlation(window=window)
plt.show()


# res = next(x for x, val in enumerate(ExpiryDateList) if val > CurrentDate)
# ExpiryDate = ExpiryDateList[res]



# OptionChainCSV.columns = pd.RangeIndex(OptionChainCSV.columns.size)



# header_row = 0
# OptionChainCSV.columns = OptionChainCSV.iloc[header_row]



# FnOVolatilityURL = FnOVolatility + FnOVolatilityArg
# try:
#     r = requests.get(FnOVolatilityURL, allow_redirects=True) #Download FnO Volatility report for 'weekday'
#     if r.ok:
#         data = r.content.decode('utf8')
###########################################################################
# ExpiryDate = date(2020,12,31)
# OptionChain = CurrentDate.strftime("%Y-%m-%d") + '-NIFTYoption-chain-equity-derivatives-'+ ExpiryDate.strftime("%Y-%m-%d") + '.csv'

# OptionChainCSVdf = pd.read_csv('./Option chain - Dec 14/'+OptionChain, header = 1)
# OptionChainCSVdf = OptionChainCSVdf.rename(columns=lambda x: x.strip())
# OptionChainCSVdf = OptionChainCSVdf.applymap(lambda x: x.strip() if isinstance(x, str) else x)

# OptionChainCSVdf.drop("Unnamed: 0", axis=1, inplace=True)
# OptionChainCSVdf.drop("Unnamed: 22", axis=1, inplace=True)
# CallOptionChaindf = OptionChainCSVdf.iloc[:,0:11]
# PutOptionChaindf = OptionChainCSVdf.iloc[:,10:21]
# if 'IV.1' in PutOptionChaindf.columns:
#     PutOptionChaindf.rename(columns={'IV.1': 'IV1'}, inplace=True)


# CallOptionChainIVdf = CallOptionChaindf[CallOptionChaindf.IV != '-']
# PutOptionChainIVdf = PutOptionChaindf[PutOptionChaindf.IV1 != '-']

# # covert IV string to an integer  to plot it
# CallOptionChainIVdf['IV'] = CallOptionChainIVdf['IV'].astype(float) 
# PutOptionChainIVdf['IV1'] = PutOptionChainIVdf['IV1'].astype(float) 
# CallOptionChainIVdf['IV'] = CallOptionChainIVdf['IV'].div(100).round(4)
# PutOptionChainIVdf['IV1'] = PutOptionChainIVdf['IV1'].div(100).round(4)
###########################################################################
# # ... or create a pdf term sheet with all metrics in term-sheets/
# vol.term_sheet(
#     window,
#     windows,
#     quantiles,
#     bins,
#     normed
# )
