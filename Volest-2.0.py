import shutil
import os
import calendar
import time
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
from adjustText import adjust_text
import math
from nsepy.derivatives import get_expiry_date
import datetime
from datetime import date
from datetime import timedelta
from dateutil.relativedelta import *
import pandas as pd
import glob
import models
import TechnicalAnalysis
from scipy.stats import norm
from nsepython import *

ExpiryDates = []
ExpiryDateList = []
ThreeThursdayDateList = []
AllThursdayDateList = []
CurrentDate = datetime.date.today()
TopRecos = 1
# global tech1, tech2, tech3, tech4

OptionChainHolidayList = ['2021-01-26','2021-03-11','2021-03-29','2021-04-02','2021-04-14','2021-04-21','2021-05-13','2021-07-21','2021-08-19','2021-09-10','2021-10-15','2021-11-05','2021-11-19']
OptionChainHolidayList = [datetime.datetime.strptime(date, '%Y-%m-%d').date() for date in OptionChainHolidayList]
DailyOHLCFilePath = "ohlc.ftr";

def Next3Thursdays(dt):
    global ThreeThursdayDateList
    ThreeThursdayDateList = []
    dt += relativedelta(day=31, weekday=TH(-1))
    if dt in OptionChainHolidayList:
        dt -= relativedelta(days=1)
    ThreeThursdayDateList.append(dt)
    for month in range(1,3):
        dt += relativedelta(months=1)
        dt += relativedelta(day=31, weekday=TH(-1))
        if dt in OptionChainHolidayList:
            dt -= relativedelta(days=1)
        ThreeThursdayDateList.append(dt)
        
def AllThursdays(d):
   # CurrentDate = datetime.date.today()   # Today
   CurrentYear = CurrentDate.year
   CurrentMonth = CurrentDate.month
   d += timedelta(days = (3 - d.weekday() + 7) % 7)         # First Thursday
   while d.year == CurrentYear and d.month < (CurrentMonth + 3):
      yield d
      d += timedelta(days = 7)

def check_for_files(filepath):
    for filepath_object in glob.glob(filepath):
        if os.path.isfile(filepath_object):
            return True

    return False
        
def DownloadOptionChain(sym):
    OptionsCumulative = pd.DataFrame()
    global ThreeThursdayDateList
    global AllThursdayDateList

    if(sym == 'NIFTY' or sym == 'BANKNIFTY' or sym == 'FINNIFTY'):
        for ExpiryDateDownload in AllThursdayDateList:
            print('Downloading option chain for '+ sym + 'Expiry = ' + ExpiryDateDownload.strftime("%d-%b-%Y"))
            try:
                oi_data, ltp, crontime = oi_chain_builder(sym,ExpiryDateDownload.strftime("%d-%b-%Y"),"full")
            except:
                print('Timed out waiting for options page to load for '+ sym)
            if not oi_data.empty:
                feather.write_feather(oi_data, './Option chain - Dec 14/'+ CurrentDate.strftime("%Y-%m-%d") + '-'+ sym + 
                'option-chain-equity-derivatives-' + ExpiryDateDownload.strftime("%Y-%m-%d")+'.ftr')
            else:
                print('Options df failed to load for '+ sym + 'for expiry' + ExpiryDateDownload.strftime("%Y-%m-%d"))
    else:
        for ExpiryDateDownload in ThreeThursdayDateList:
            print('Downloading option chain for '+ sym + ', Expiry = ' + ExpiryDateDownload.strftime("%d-%b-%Y"))
            try:
                oi_data, ltp, crontime = oi_chain_builder(sym,ExpiryDateDownload.strftime("%d-%b-%Y"),"full")
            except:
                print('Timed out waiting for options page to load for '+ sym)
            if not oi_data.empty:
                # 2021-06-13-NIFTYoption-chain-equity-derivatives-2021-08-26
                feather.write_feather(oi_data, './Option chain - Dec 14/'+ CurrentDate.strftime("%Y-%m-%d") + '-'+ sym + 
                'option-chain-equity-derivatives-' + ExpiryDateDownload.strftime("%Y-%m-%d")+'.ftr')
            else:
                print('Options df failed to load for '+ sym)

def FindFeather(name, path):
    for root, dirs, files in os.walk(path):
        if name in files:
            return os.path.join(root, name)

def UpdateOptionChainTable(ExpiryDate,Symbol):
    OptionsFileName = CurrentDate.strftime("%Y-%m-%d") + '-' + Symbol + 'option-chain-equity-derivatives-'+ ExpiryDate.strftime("%Y-%m-%d") + '.ftr'
    OptionChainCSVdf = feather.read_feather('./Option chain - Dec 14/'+OptionsFileName)    
    
    OptionChainCSVdf = OptionChainCSVdf.rename(columns=lambda x: x.strip())
    OptionChainCSVdf = OptionChainCSVdf.applymap(lambda x: x.strip() if isinstance(x, str) else x)
    
    OptionChainCSVdf.drop("CALLS_Chart", axis=1, inplace=True)
    OptionChainCSVdf.drop("PUTS_Chart", axis=1, inplace=True)
    CallOptionChaindf = OptionChainCSVdf.iloc[:,0:11]
    PutOptionChaindf = OptionChainCSVdf.iloc[:,10:21]
    
    CallOptionChainIVdf = CallOptionChaindf[CallOptionChaindf.CALLS_IV != 0]
    PutOptionChainIVdf = PutOptionChaindf[PutOptionChaindf.PUTS_IV != 0]
    
    # covert IV string to an integer  to plot it
    CallOptionChainIVdf['CALLS_IV'] = CallOptionChainIVdf['CALLS_IV'].div(100).round(4)
    PutOptionChainIVdf['PUTS_IV'] = PutOptionChainIVdf['PUTS_IV'].div(100).round(4)
    #Reset the index ???
    CallOptionChainIVdf.reset_index(level=0, inplace=True, drop=True)
    PutOptionChainIVdf.reset_index(level=0, inplace=True, drop=True)
    
    CallOptionChainIVdf['Date'] = CurrentDate
    CallOptionChainIVdf['Expiry'] = ExpiryDate
    PutOptionChainIVdf['Date'] = CurrentDate
    PutOptionChainIVdf['Expiry'] = ExpiryDate
    # d = ExpiryDate - CurrentDate Can add this to a column directly?
    CallOptionChainIVdf[['Date','Expiry']] = CallOptionChainIVdf[['Date','Expiry']].apply(pd.to_datetime) #if conversion required
    CallOptionChainIVdf['DaysToExpiry'] = (CallOptionChainIVdf['Expiry'] - CallOptionChainIVdf['Date'])
    CallOptionChainIVdf['DaysToExpiry'] = CallOptionChainIVdf['DaysToExpiry'].dt.days
    PutOptionChainIVdf[['Date','Expiry']] = PutOptionChainIVdf[['Date','Expiry']].apply(pd.to_datetime) #if conversion required
    PutOptionChainIVdf['DaysToExpiry'] = (PutOptionChainIVdf['Expiry'] - PutOptionChainIVdf['Date'])
    PutOptionChainIVdf['DaysToExpiry'] = PutOptionChainIVdf['DaysToExpiry'].dt.days

    # df["Date"] = df["Date"].apply(pd.to_datetime, format='%d-%b-%Y')
    CallOptionChainIVdf['Date'] = CallOptionChainIVdf['Date'].dt.date
    CallOptionChainIVdf['Expiry'] = CallOptionChainIVdf['Expiry'].dt.date
    PutOptionChainIVdf['Date'] = PutOptionChainIVdf['Date'].dt.date
    PutOptionChainIVdf['Expiry'] = PutOptionChainIVdf['Expiry'].dt.date
    
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

        return getattr(models, self._estimator).get_estimator(
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
        Conesfig = plt.figure(figsize=(16, 12))
        ax0 = plt.subplots()
        Conesfig.autofmt_xdate()
        left, width = 0.07, 0.65
        bottom, height = 0.2, 0.7
        left_h = left+width+0.02
        rect_cones = [left, bottom, width, height]
        rect_box = [left_h, bottom, 0.17, height]
        cones = Conesfig.add_axes(rect_cones)
        box = Conesfig.add_axes(rect_box)

        # set the plots
        cones.plot(windows, max_, label="Max")
        cones.plot(windows, top_q, label=str(int(quantiles[1]*100)) + " Prctl")
        cones.plot(windows, median, label="Median")
        cones.plot(windows, bottom_q, label=str(int(quantiles[0]*100)) + " Prctl")
        cones.plot(windows, min_, label="Min")
        cones.plot(windows, realized, 'r-.', label="Realized")

        arrowprops = dict( 
        arrowstyle = "->", 
        color='red',
        connectionstyle = "angle3,angleA=90,angleB=0")
          # connectionstyle = "angle, angleA = 0, angleB = 90,rad = 10"
          
        buyarrowprops = dict( 
        arrowstyle = "->",
        color='blue',
        connectionstyle = "angle, angleA = 0, angleB = 90,rad = 10")          
        offset = 72
        
        global ExpiryDateList
        
        for i in ExpiryDateList:
                if i > CurrentDate:
                    try:
                            # print('Scattering for date '+ i.strftime("%Y%m%d"))
                        # CallOptionChainIVdf, PutOptionChainIVdf = UpdateOptionChainTable(datetime.date(2021, 6, 24),'RELIANCE')
                        CallOptionChainIVdf, PutOptionChainIVdf = UpdateOptionChainTable(i,self._symbol[1])
                        cones.scatter(CallOptionChainIVdf['DaysToExpiry'],CallOptionChainIVdf['CALLS_IV'],color='b')
                        cones.scatter(PutOptionChainIVdf['DaysToExpiry'],PutOptionChainIVdf['PUTS_IV'],color='r')
                        #Important to annotate only outlier points
                        CallOptionChainIVdf = CallOptionChainIVdf.sort_values(by=['CALLS_IV']) 
                        PutOptionChainIVdf = PutOptionChainIVdf.sort_values(by=['PUTS_IV'])
                        # ind = 1
                        #Sell Recos for CE       + ',IV = ' (CallOptionChainIVdf['IV'][ind]*100).astype(str),
                        for ind in CallOptionChainIVdf[-TopRecos:].index:
                            OptionString = str(CallOptionChainIVdf['Strike Price'][ind]) + ' CE, ' + str(CallOptionChainIVdf['CALLS_LTP'][ind]) + ' ' + CallOptionChainIVdf['Expiry'][ind].strftime("%b-%d")
                            cones.annotate(OptionString,
                                            xy = (CallOptionChainIVdf['DaysToExpiry'][ind], CallOptionChainIVdf['CALLS_IV'][ind]),
                                            color='r', xytext =(1.5 * offset,6 * CallOptionChainIVdf['DaysToExpiry'][ind]), textcoords ='offset points',arrowprops = arrowprops,
                                            horizontalalignment='right', verticalalignment='top')
                            # texts.append(cones.text(CallOptionChainIVdf['DaysToExpiry'][ind], CallOptionChainIVdf['IV'][ind], OptionString),ha='center', va='center')
                            print('[SELL '+ self._symbol[1] +'] '+ OptionString, sep='\n')
                        # Sell Recos for PE     + ',IV1 = ' + (PutOptionChainIVdf['IV1'][ind]*100).astype(str)
                        for ind in PutOptionChainIVdf[-TopRecos:].index:
                            OptionString = str(PutOptionChainIVdf['Strike Price'][ind]) + ' PE, ' + str(PutOptionChainIVdf['PUTS_LTP'][ind]) + ' ' + PutOptionChainIVdf['Expiry'][ind].strftime("%b-%d")
                            cones.annotate(OptionString,
                                            xy = (PutOptionChainIVdf['DaysToExpiry'][ind], PutOptionChainIVdf['PUTS_IV'][ind]),
                                            color='r', xytext =(1.5 * PutOptionChainIVdf['DaysToExpiry'][ind], 6 * PutOptionChainIVdf['DaysToExpiry'][ind]), textcoords ='offset points',arrowprops = arrowprops ,
                                            horizontalalignment='left', verticalalignment='top')
                            # texts.append(cones.text(PutOptionChainIVdf['DaysToExpiry'][ind], PutOptionChainIVdf['IV1'][ind], OptionString),ha='center', va='center')
                            print('[SELL '+ self._symbol[1] +'] '+ OptionString, sep='\n')
                        #Buy Recos for CE    + ',IV = ' + (CallOptionChainIVdf['IV'][ind]*100).astype(str)
                        for ind in CallOptionChainIVdf.head(TopRecos).index:
                            OptionString = str(CallOptionChainIVdf['Strike Price'][ind]) + ' CE, ' + str(CallOptionChainIVdf['CALLS_LTP'][ind]) + ' ' + CallOptionChainIVdf['Expiry'][ind].strftime("%b-%d")
                            cones.annotate(OptionString,
                                            xy = (CallOptionChainIVdf['DaysToExpiry'][ind], CallOptionChainIVdf['CALLS_IV'][ind]),
                                            color='b', xytext =(2 * CallOptionChainIVdf['DaysToExpiry'][ind], -3 * CallOptionChainIVdf['DaysToExpiry'][ind]), textcoords ='offset points', arrowprops = buyarrowprops,
                                            horizontalalignment='left', verticalalignment='bottom')
                            # texts.append(cones.text(CallOptionChainIVdf['DaysToExpiry'][ind], CallOptionChainIVdf['IV'][ind], OptionString),ha='center', va='center')
                            print('[BUY '+ self._symbol[1] +'] '+ OptionString, sep='\n')
                        #Buy Recos for PE      + ',IV1 = ' + (PutOptionChainIVdf['IV1'][ind]*100).astype(str)
                        for ind in PutOptionChainIVdf.head(TopRecos).index:
                            OptionString = str(PutOptionChainIVdf['Strike Price'][ind]) + ' PE, ' + str(PutOptionChainIVdf['PUTS_LTP'][ind]) + ' ' + PutOptionChainIVdf['Expiry'][ind].strftime("%b-%d")
                            cones.annotate(OptionString,
                                            xy = (PutOptionChainIVdf['DaysToExpiry'][ind], PutOptionChainIVdf['PUTS_IV'][ind]),
                                            color='b', xytext =(4 * offset, -4 * PutOptionChainIVdf['DaysToExpiry'][ind]), textcoords ='offset points', arrowprops = buyarrowprops,
                                            horizontalalignment='right', verticalalignment='bottom')
                            # texts.append(cones.text(PutOptionChainIVdf['DaysToExpiry'][ind], PutOptionChainIVdf['IV1'][ind], OptionString),ha='center', va='center')
                            print('[BUY '+ self._symbol[1] +'] '+ OptionString, sep='\n')
                    except:
                        print('Couldnt plot IV spread for '+i.strftime("%Y%m%d"))
                        # print("Oops!", sys.exc_info()[0], "occurred.")

        # set the x ticks and limits
        cones.set_xticks(windows)
        cones.set_xlim((windows[0]-5, windows[-1]+5))

        # set and format the y-axis labels
        locs = cones.get_yticks()
        cones.set_yticklabels(map(f, locs))

        # turn on the grid
        cones.grid(True, axis='y', which='major', alpha=0.5)

        # set the title
        cones.set_title('Volatility Cone ' + self._estimator + ' (' + self._symbol[1] + ', daily ' + self._start.strftime("%Y-%m-%d") + ' to ' + self._end.strftime("%Y-%m-%d") + ')')

        # set the legend
        cones.legend()#loc='upper center', bbox_to_anchor=(0.5, -0.05), ncol=3)
        # adjust_text(texts, only_move={'points':'xy', 'texts':'xy'}, arrowprops=dict(arrowstyle="-", color='k', lw=0.5))

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
        
        return Conesfig, plt


    def rolling_quantiles(self, window=30, quantiles=[0.25, 0.75]):
        """Plots rolling quantiles of volatility
        
        Parameters
        ----------
        window : int
            Rolling window for which to calculate the estimator
        quantiles : [lower, upper]
            List of lower and upper quantiles for which to plot
        """

        price_data = self._price_data

        if len(quantiles) != 2:
            raise ValueError(
                'A two element list of quantiles is required, lower and upper')
        if quantiles[0] + quantiles[1] != 1.0:
            raise ValueError(
                'The sum of the quantiles must equal 1.0')
        if quantiles[0] > quantiles[1]:
            raise ValueError(
                'The lower quantiles (first element) must be less than the upper quantile (second element)')
        
        estimator = self._get_estimator(
            window=window,
            price_data=price_data
        )
        date = estimator.index
        
        top_q = estimator.rolling(window=window, center=False).quantile(quantiles[1])
        median = estimator.rolling(window=window, center=False).median()
        bottom_q = estimator.rolling(window=window, center=False).quantile(quantiles[0])
        realized = estimator
        last = estimator[-1]

        if self._estimator is "Skew" or self._estimator is "Kurtosis":
            f = lambda x: "%i" % round(x, 0)
        else:
            f = lambda x: "%i%%" % round(x*100, 0)

        # figure
        fig = plt.figure(figsize=(8, 6))
        fig.autofmt_xdate()
        left, width = 0.07, 0.65
        bottom, height = 0.2, 0.7
        left_h = left+width+0.02
        
        rect_cones = [left, bottom, width, height]
        rect_box = [left_h, bottom, 0.17, height]
        
        cones = plt.axes(rect_cones)
        box = plt.axes(rect_box)

        # set the plots
        cones.plot(date, top_q, label=str(int(quantiles[1]*100)) + " Prctl")
        cones.plot(date, median, label="Median")
        cones.plot(date, bottom_q, label=str(int(quantiles[0]*100)) + " Prctl")
        cones.plot(date, realized, 'r-.', label="Realized")
        
        # set and format the y-axis labels
        locs = cones.get_yticks()
        cones.set_yticklabels(map(f, locs))
        
        # turn on the grid
        cones.grid(True, axis='y', which='major', alpha=0.5)
        
        # set the title
        cones.set_title('rolling_quantiles ' + self._estimator + ' (' + self._symbol[1] + ', daily ' + self._start.strftime("%Y-%m-%d") + ' to ' + self._end.strftime("%Y-%m-%d") + ')')
        
        # set the legend
        cones.legend(loc='upper center', bbox_to_anchor=(0.5, -0.05), ncol=3)

        # box plots
        box.boxplot(realized, notch=1, sym='+')
        box.plot(1, last, color='r', marker='*', markeredgecolor='k')
        
        # set and format the y-axis labels
        locs = box.get_yticks()
        box.set_yticklabels(map(f, locs))
        
        # move the y-axis ticks on the right side
        box.yaxis.tick_right()
        
        # turn on the grid
        box.grid(True, axis='y', which='major', alpha=0.5)
        
        return fig, plt

    def rolling_extremes(self, window=30):
        """Plots rolling max and min of volatility estimator
        
        Parameters
        ----------
        window : int
            Rolling window for which to calculate the estimator
        """

        price_data = self._price_data

        estimator = self._get_estimator(
            window=window,
            price_data=price_data
        )
        date = estimator.index
        max_ = estimator.rolling(window=window, center=False).max()
        min_ = estimator.rolling(window=window, center=False).min()
        realized = estimator
        last = estimator[-1]

        if self._estimator is "Skew" or self._estimator is "Kurtosis":
            f = lambda x: "%i" % round(x, 0)
        else:
            f = lambda x: "%i%%" % round(x*100, 0)

        # figure
        fig = plt.figure(figsize=(8, 6))
        fig.autofmt_xdate()
        left, width = 0.07, 0.65
        bottom, height = 0.2, 0.7
        left_h = left+width+0.02
        
        rect_cones = [left, bottom, width, height]
        rect_box = [left_h, bottom, 0.17, height]
        
        cones = plt.axes(rect_cones)
        box = plt.axes(rect_box)

        # set the plots
        cones.plot(date, max_, label="Max")
        cones.plot(date, min_, label="Min")
        cones.plot(date, realized, 'r-.', label="Realized")
        
        # set and format the y-axis labels
        locs = cones.get_yticks()
        cones.set_yticklabels(map(f, locs))
        
        # turn on the grid
        cones.grid(True, axis='y', which='major', alpha=0.5)
        
        # set the title
        cones.set_title('rolling_extremes '+ self._estimator + ' (' + self._symbol[1] + ', daily ' + self._start.strftime("%Y-%m-%d") + ' to ' + self._end.strftime("%Y-%m-%d") + ')')
        
        # set the legend
        cones.legend(loc='upper center', bbox_to_anchor=(0.5, -0.05), ncol=3)

        # box plot
        box.boxplot(realized, notch=1, sym='+')
        box.plot(1, last, color='r', marker='*', markeredgecolor='k')
        
        # set and format the y-axis labels
        locs = box.get_yticks()
        box.set_yticklabels(map(f, locs))
        
        # move the y-axis ticks on the right side
        box.yaxis.tick_right()
        
        # turn on the grid
        box.grid(True, axis='y', which='major', alpha=0.5)
        
        return fig, plt

    def rolling_descriptives(self, window=30):
        """Plots rolling first and second moment of volatility estimator
        
        Parameters
        ----------
        window : int
            Rolling window for which to calculate the estimator
        """

        price_data = self._price_data

        estimator = self._get_estimator(
            window=window,
            price_data=price_data
        )
        date = estimator.index
        mean = estimator.rolling(window=window, center=False).mean()
        std = estimator.rolling(window=window, center=False).std()
        z_score = (estimator - mean) / std
        
        realized = estimator
        last = estimator[-1]

        if self._estimator is "Skew" or self._estimator is "Kurtosis":
            f = lambda x: "%i" % round(x, 0)
        else:
            f = lambda x: "%i%%" % round(x*100, 0)

        # figure
        fig = plt.figure(figsize=(8, 6))
        fig.autofmt_xdate()
        left, width = 0.07, 0.65
        left_h = left+width+0.02
        
        rect_cones = [left, 0.35, width, 0.55]
        rect_box = [left_h, 0.15, 0.17, 0.75]
        rect_z = [left, 0.15, width, 0.15]
        
        cones = plt.axes(rect_cones)
        box = plt.axes(rect_box)
        z = plt.axes(rect_z)
        
        if self._estimator is "Skew" or self._estimator is "Kurtosis":
            f = lambda x: "%i" % round(x, 0)
        else:
            f = lambda x: "%i%%" % round(x*100, 0)

        # set the plots
        cones.plot(date, mean, label="Mean")
        cones.plot(date, std, label="Std. Dev.")
        cones.plot(date, realized, 'r-.', label="Realized")
        
        # set and format the y-axis labels
        locs = cones.get_yticks()
        cones.set_yticklabels(map(f, locs))
        
        # turn on the grid
        cones.grid(True, axis='y', which='major', alpha=0.5)
        
        # set the title
        cones.set_title('rolling_descriptives '+self._estimator + ' (' + self._symbol[1] + ', daily ' + self._start.strftime("%Y-%m-%d") + ' to ' + self._end.strftime("%Y-%m-%d") + ')')
        
        # shrink the plot up a bit and set the legend
        pos = cones.get_position()
        cones.set_position([pos.x0, pos.y0 + pos.height * 0.1, pos.width, pos.height * 0.9]) #
        cones.legend(loc='upper center', bbox_to_anchor=(0.5, -0.05), ncol=3)

        # box plot
        box.boxplot(realized, notch=1, sym='+')
        box.plot(1, last, color='r', marker='*', markeredgecolor='k')
        
        # set and format the y-axis labels
        locs = box.get_yticks()
        box.set_yticklabels(map(f, locs))
        
        # move the y-axis ticks on the right side
        box.yaxis.tick_right()
        
        # turn on the grid
        box.grid(True, axis='y', which='major', alpha=0.5)

        # z-score set the plots
        z.plot(date, z_score, 'm-', label="Z-Score")
        
        # turn on the grid
        z.grid(True, axis='y', which='major', alpha=0.5)
        
        # create a horizontal line at y=0
        z.axhline(0, 0, 1, linestyle='-', linewidth=1.0, color='black')
        
        # set the legend
        z.legend(loc='upper center', bbox_to_anchor=(0.5, -0.2), ncol=3)
        
        return fig, plt

    def histogram(self, window=90, bins=100, density=True):
        """
        
        Parameters
        ----------
        window : int
            Rolling window for which to calculate the estimator
        bins : int
            
        """

        price_data = self._price_data

        estimator = self._get_estimator(
            window=window,
            price_data=price_data
        )
        mean = estimator.mean()
        std = estimator.std()
        last = estimator[-1]

        fig = plt.figure(figsize=(8, 6))
        
        n, bins, patches = plt.hist(estimator, bins, density=density, facecolor='blue', alpha=0.25)
        
        if density:
            y = norm.pdf(bins, mean, std)
            plt.plot(bins, y, 'g--', linewidth=1)

        plt.axvline(last, 0, 1, linestyle='-', linewidth=1.5, color='r')

        plt.grid(True, axis='y', which='major', alpha=0.5)
        plt.title('Distribution of ' + self._estimator +
                  ' estimator values (' + self._symbol[1] +
                  ', daily ' + self._start.strftime("%Y-%m-%d") + ' to ' + self._end.strftime("%Y-%m-%d") + ')')
        
        return fig, plt
    
    def benchmark_compare(self, window=90):
        """
        
        Parameters
        ----------
        window : int
            Rolling window for which to calculate the estimator
        bins : int
            
        """

        price_data = self._price_data
        bench_data = self._bench_data

        y = self._get_estimator(
            window=window,
            price_data=price_data
        )
        x = self._get_estimator(
            window=window,
            price_data=bench_data
        )
        date = y.index
        
        ratio = y / x

        if self._estimator is "Skew" or self._estimator is "Kurtosis":
            f = lambda x: "%i" % round(x, 0)
        else:
            f = lambda x: "%i%%" % round(x*100, 0)
        
        # figure
        fig = plt.figure(figsize=(8, 6))
        fig.autofmt_xdate()
        left, width = 0.07, .9
        
        rect_cones = [left, 0.4, width, .5]
        rect_box = [left, 0.15, width, 0.15]
        
        cones = plt.axes(rect_cones)
        box = plt.axes(rect_box)

        # set the plots
        cones.plot(date, y, label=self._symbol[1])
        cones.plot(date, x, label=self._bench_symbol[1])
        
        # set and format the y-axis labels
        locs = cones.get_yticks()
        cones.set_yticklabels(map(f, locs))
        
        # turn on the grid
        cones.grid(True, axis='y', which='major', alpha=0.5)
        
        # set the title
        cones.set_title('benchmark_compare ' + self._estimator + ' (' + self._symbol[1] +
                        ' v. ' + self._bench_symbol[1] + ', daily ' +
                        self._start.strftime("%Y-%m-%d") + ' to ' + self._end.strftime("%Y-%m-%d") + ')')
        
        # shrink the plot up a bit and set the legend
        cones.legend(loc='upper center', bbox_to_anchor=(0.5, -0.05), ncol=3)

        # set the plot
        box.plot(date, ratio, label=self._symbol[1] + '/' + self._bench_symbol[1])
        
        # set the y-limits
        box.set_ylim((ratio.min() - 0.05, ratio.max() + 0.05))
        
        # fill the area
        box.fill_between(date, ratio, 0, color='blue', alpha=0.25)
        
        # set the legend
        box.legend(loc='upper center', bbox_to_anchor=(0.5, -0.2), ncol=3)

        return fig, plt

    def benchmark_correlation(self, window=90):
        """
        
        Parameters
        ----------
        window : int
            Rolling window for which to calculate the estimator
        bins : int
            
        """
        
        price_data = self._price_data
        bench_data = self._bench_data

        y = self._get_estimator(
            window=window,
            price_data=price_data
        )
        x = self._get_estimator(
            window=window,
            price_data=bench_data
        )
        date = y.index

        corr = x.rolling(window=window).corr(other=y)

        if self._estimator is "Skew" or self._estimator is "Kurtosis":
            f = lambda x: "%i" % round(x, 0)
        else:
            f = lambda x: "%i%%" % round(x*100, 0)
        
        # figure
        fig = plt.figure(figsize=(8, 6))
        cones = plt.axes()

        # set the plots
        cones.plot(date, corr)

        # set the y-limits
        cones.set_ylim((corr.min() - 0.05, corr.max() + 0.05))

        # set and format the y-axis labels
        locs = cones.get_yticks()
        cones.set_yticklabels(map(f, locs))

        # turn on the grid
        cones.grid(True, axis='y', which='major', alpha=0.5)

        # set the title
        cones.set_title('benchmark_correlation ' + self._estimator + ' (Correlation of ' +
                        self._symbol[1] + ' v. ' + self._bench_symbol[1] +
                        ', daily ' + self._start.strftime("%Y-%m-%d") + ' to ' + self._end.strftime("%Y-%m-%d") + ')')
        
        return fig, plt

    def benchmark_regression(self, window=90):
        """
        
        Parameters
        ----------
        window : int
            Rolling window for which to calculate the estimator
        bins : int
            
        """
        price_data = self._price_data
        bench_data = self._bench_data

        y = self._get_estimator(
            window=window,
            price_data=price_data
        )
        X = self._get_estimator(
            window=window,
            price_data=bench_data
        )
        
        model = sm.OLS(y, X)
        results = model.fit()

        return results.summary()

    
    def term_sheet(
            self,
            window=30,
            windows=[30, 60, 90, 120],
            quantiles=[0.25, 0.75],
            bins=100,
            density=True,
            open=False):

        tech1, tech2, tech3, tech4 = Technicals(self._symbol[1])        
        cones_fig, cones_plt = self.cones(windows=windows, quantiles=quantiles)
        rolling_quantiles_fig, rolling_quantiles_plt = self.rolling_quantiles(window=window, quantiles=quantiles)
        rolling_extremes_fig, rolling_extremes_plt = self.rolling_extremes(window=window)
        rolling_descriptives_fig, rolling_descriptives_plt = self.rolling_descriptives(window=window)
        histogram_fig, histogram_plt = self.histogram(window=window, bins=bins, density=density)
        benchmark_compare_fig, benchmark_compare_plt = self.benchmark_compare(window=window)
        benchmark_corr_fig, benchmark_corr_plt = self.benchmark_correlation(window=window)
        benchmark_regression = self.benchmark_regression(window=window)
        
        filename = self._symbol[1] + self._estimator + '_termsheet_' + pd.datetime.now().strftime("%Y-%m-%d--%H-%M-%S %p") + '.pdf'
        fn = os.path.abspath(os.path.join(u'..', u'nsepywork/term-sheets', filename))
        pp = PdfPages(fn)
        
        pp.savefig(tech1)
        pp.savefig(cones_fig)
        pp.savefig(tech2)
        pp.savefig(tech3)
        pp.savefig(tech4)        
        pp.savefig(rolling_quantiles_fig)
        pp.savefig(rolling_extremes_fig)
        pp.savefig(rolling_descriptives_fig)
        pp.savefig(histogram_fig)
        pp.savefig(benchmark_compare_fig)
        pp.savefig(benchmark_corr_fig)

        fig = plt.figure(figsize=(8, 6))
        ax = fig.add_subplot(111)
        ax.text(
            0, .2,
            benchmark_regression,
            family='monospace',
            fontsize=9
        )

        plt.axis('off')
        fig.tight_layout()
        pp.savefig(fig)
        pp.close()
        
        print('%s output complete' % filename)

def plot_chart(DF, n, ticker, Dividend):

    # n = 100
    # ticker = "AXISBANK"
    # data = Indicatordf.copy()
    data = DF.copy()

    Renkodata = Renko_DF(data,ticker)
    #DF amd number of latest bricks
    tech1 = PlotRenko(Renkodata,100)

    data = data.iloc[-n:]    
    if(ticker != "NIFTY" and ticker != "BANKNIFTY"):
        data.drop(data.iloc[:, [1,2,3,7]], inplace = True, axis = 1) #This line is required for candles

    OptionsFileName = ticker + '_' + MonthlyOptionsFilePath
    #Read from feather
    if (FindFeather(OptionsFileName, './Datastore/')):
        OptionsFrameStart = data.iloc[0].Date
        Mpdf = GetMaxPain(ticker,OptionsFrameStart)
        data = pd.merge(data,Mpdf, on = 'Date', how = 'outer')
        
    FuturesFileName = ticker + '_' + FullFuturesFilePath
    #Read from feather
    if (FindFeather(FuturesFileName, './Datastore/')):
        ReadFuturesdf = feather.read_feather('./Datastore/'+FuturesFileName)
       
        d = OptionsFrameStart - datetime.timedelta(days=1) #Date to start from for axis alignment
        FuturesSlice = ReadFuturesdf[ReadFuturesdf.Date > d]
        Futdf = FuturesSlice[['Date', 'Expiry','Settle Price','Open Int']].copy()
        Futdf = Futdf.sort_values(by=['Date', 'Expiry'])
        Futdf = Futdf.reset_index(drop=True)
        
        SettlePricedf = Futdf.groupby('Date')['Settle Price'].apply(lambda x: pd.Series(list(x))).unstack()
        OpenInterestdf = Futdf.groupby('Date')['Open Int'].apply(lambda x: pd.Series(list(x))).unstack()
        ExpiryDatedf = Futdf.groupby('Date')['Expiry'].apply(lambda x: pd.Series(list(x))).unstack()

        ExpiryDatedf = ExpiryDatedf.reset_index(level=0)
        ExpiryDatedf = ExpiryDatedf.rename(columns={0: 'NearExpiry',1:'MidExpiry',2:'FarExpiry'})
        
        OpenInterestdf = OpenInterestdf.reset_index(level=0)
        OpenInterestdf = OpenInterestdf.rename(columns={0: 'NearOpenInterest',1:'MidOpenInterest',2:'FarOpenInterest'})        
        
        SettlePricedf = SettlePricedf.reset_index(level=0)
        SettlePricedf = SettlePricedf.rename(columns={0: 'NearSettlePrice',1:'MidSettlePrice',2:'FarSettlePrice'})
        
        dfs = [ExpiryDatedf, OpenInterestdf, SettlePricedf]
        Futdf = reduce(lambda left,right: pd.merge(left,right,on='Date'), dfs)
        Futdf = pd.merge(data,Futdf, on = 'Date', how = 'outer')
    
    data.index = data["Date"].apply(lambda x: pd.Timestamp(x))
    data.drop("Date", axis=1, inplace=True)
    
    # Create figure and set axes for subplots
    tech2 = plt.figure()
    # plt.title(ticker)
    # fig.set_size_inches((20, 16))
    # ax_candle = fig.add_axes((0, 0.72, 1, 0.32))
    # ax_macd = fig.add_axes((0, 0.48, 1, 0.2), sharex=ax_candle)
    # ax_rsi = fig.add_axes((0, 0.24, 1, 0.2), sharex=ax_candle)
    # ax_vol = fig.add_axes((0, 0, 1, 0.2), sharex=ax_candle)
    
    #plt.title(ticker)
    tech2.set_size_inches((32, 18))
    ax_candle = tech2.add_axes((0, 0.72, 0.49, 0.32))
    ax_macd = tech2.add_axes((0, 0.48, 0.49, 0.2), sharex=ax_candle)
    ax_rsi = tech2.add_axes((0, 0.24, 0.49, 0.2), sharex=ax_candle)
    ax_vol = tech2.add_axes((0, 0, 0.49, 0.2), sharex=ax_candle)
    
    ax_bba = tech2.add_axes((0.51, 0.72,0.49, 0.32), sharex=ax_candle)
    ax_obv = tech2.add_axes((0.51, 0.48, 0.49, 0.2), sharex=ax_candle)
    ax_atr = tech2.add_axes((0.51, 0.24, 0.49, 0.2), sharex=ax_candle)
    ax_beta = tech2.add_axes((0.51, 0, 0.49, 0.2), sharex=ax_candle)
    
    # Format x-axis ticks as dates
    ax_candle.xaxis_date()
    
    # Get nested list of date, open, high, low and close prices
    ohlc = []
    for date, row in data.iterrows():
        openp, highp, lowp, closep = row[:4]
        ohlc.append([date2num(date), openp, highp, lowp, closep])
 
    # Plot candlestick chart
    ax_candle.plot(data.index, data["Close"], label=ticker +" Price")
    ax_candle.plot(data.index, data["10DMA"], label="MA10")
    ax_candle.plot(data.index, data["50DMA"], label="MA50")
    candlestick_ohlc(ax_candle, ohlc, colorup="g", colordown="r", width=0.8)
    ax_candle.legend()
    
    # Plot MACD
    ax_macd.plot(data.index, data["MACD"], label="MACD")
    ax_macd.bar(data.index, (data["MACD"] -data["Signal"]) * 3, label="hist")
    ax_macd.plot(data.index, data["Signal"], label="Signal")
    ax_macd.legend()
    
    # Plot RSI & ADX bands
    # Above 70% = overbought, below 30% = oversold
    ax_rsi.set_ylabel("(%)")
    ax_rsi.plot(data.index, [80] * len(data.index), label="overbought")
    ax_rsi.plot(data.index, [20] * len(data.index), label="oversold")
    ax_rsi.plot(data.index, [50] * len(data.index))
    ax_rsi.plot(data.index, data["RSI"], label="RSI", color = 'lightpink')
    ax_rsi.plot(data.index, data["ADX"], label="ADX", color = 'blue')
    ax_rsi.plot(data.index, data["DIplusN"], label="DI+", color = 'green')
    ax_rsi.plot(data.index, data["DIminusN"], label="DI-", color = 'red')
    ax_rsi.legend()
    
    # Show volume in millions
    ax_vol.bar(data.index, data["Volume"] / 100000, label="Volume")
    if(ticker != "NIFTY" and ticker != "BANKNIFTY"):
        ax_vol.bar(data.index, data["Deliverable Volume"] / 100000, label="Deliverable")
    ax_vol.set_ylabel("(Lakh(s))")
    ax_vol.legend()

    # # Plot BB
    # # MA, BB_up and BB_dn. Expansion = Greater Volatility
    # ax_bba.set_ylabel("BBands")
    ax_bba.plot(data.index, data["BB_up"], label="BB_up")
    ax_bba.plot(data.index, data["BB_dn"], label="BB_dn")
    ax_bba.plot(data.index, data["MA"], label="MA")
    ax_bba.legend()
    
    # # Plot OBV
    # # MA, BB_up and BB_dn. Expansion = Greater Volatility   
    # ax_obv.set_ylabel("On Balance Volume")
    ax_obv.plot(data.index, data["OBV"]/ 100000, label="OBV")
    ax_obv.set_ylabel("(Lakh(s))")
    ax_obv.legend()

    # # Plot ATR
    # # MA, BB_up and BB_dn. Expansion = Greater Volatility    
    # ax_atr.set_ylabel("Trading range")
    ax_atr.plot(data.index, data["TR"], label="TR")
    ax_atr.plot(data.index, data["ATR"], label="ATR")
    ax_atr.legend()
    
    # Plot Beta and deliverable
    # Above 70% = overbought, below 30% = oversold
    #ax_beta.set_ylabel("Beta")
    ax_beta.plot(data.index, data["Beta"], label="Beta")
    if(ticker != "NIFTY" and ticker != "BANKNIFTY"):    
        ax_beta.plot(data.index, data["%Deliverble"], label="% Deliverable")
    ax_beta.legend()    

    # Save the chart as PNG
    #fig.savefig("charts/" + ticker + ".png", bbox_inches="tight")
    
    plt.show()
    
    tech3 = plt.figure()
    tech3.set_size_inches((32, 18))
    #[left, bottom, width, height] 
    # ax_sma = fig2.add_axes((0, 0.72, 0.49, 0.32))
    # ax_ema = fig2.add_axes((0.51, 0.72, 0.49, 0.32), sharex=ax_sma)
    # ax_trades = fig2.add_axes((0, 0.48, 0.49, 0.2), sharex=ax_candle)
    # ax_turnover = fig2.add_axes((0.51, 0.48, 0.49, 0.2), sharex=ax_candle)
    # ax_slope = fig2.add_axes((0, 0.24, 1, 0.2), sharex=ax_candle)
    
    ax_sma = tech3.add_axes((0, 0.72, 0.49, 0.32))
    ax_trades = tech3.add_axes((0, 0.48, 0.49, 0.2), sharex=ax_sma)
    ax_fibret = tech3.add_axes((0, 0.24, 0.49, 0.2), sharex=ax_sma)
    ax_slope = tech3.add_axes((0, 0, 0.49, 0.2), sharex=ax_sma)
    
    ax_ema = tech3.add_axes((0.51, 0.72, 0.49, 0.32), sharex=ax_sma)
    ax_maxpain = tech3.add_axes((0.51, 0.48, 0.49, 0.2), sharex=ax_sma)
    ax_futures = tech3.add_axes((0.51, 0, 0.49, 0.45), sharex=ax_sma)
      
    ax_sma.xaxis_date()
    
    # Plot SMA chart
    ax_sma.plot(data.index, data["Close"], label= ticker +" Price")
    ax_sma.plot(data.index, data["10DMA"], label="10DMA")
    ax_sma.plot(data.index, data["20DMA"], label="20DMA")
    ax_sma.plot(data.index, data["50DMA"], label="50DMA")
    ax_sma.plot(data.index, data["100DMA"], label="100DMA")
    ax_sma.plot(data.index, data["200DMA"], label="200DMA")       
    ax_sma.legend()
    
    # Plot MACD & Slope
    ax_ema.plot(data.index, data["Close"], label= ticker +" Price")
    ax_ema.plot(data.index, data["10DMA-E"], label="10DMA-E")
    ax_ema.plot(data.index, data["20DMA-E"], label="20DMA-E")
    ax_ema.plot(data.index, data["50DMA-E"], label="50DMA-E")
    ax_ema.plot(data.index, data["80DMA-E"], label="80DMA-E")
    ax_ema.plot(data.index, data["140DMA-E"], label="140DMA-E")       
    ax_ema.legend()

    #Read from feather
    if (FindFeather(FuturesFileName, './Datastore/')):
        StdDev = data['Log_Ret'].std() # Daily Std Deviation for volatility
        DailyRet = data['Log_Ret'].mean()
        pd.to_datetime(Futdf['Date'])
        # Futdf.info()
        # np.busday_count( pd.to_datetime(Futdf['Date']).values.astype('datetime64[D]'), pd.to_datetime(Futdf['NearExpiry']).values.astype('datetime64[D]'))
        # np.busday_count(np.datetime64('2011-07-11'), np.datetime64('2011-07-18'))
        
        days = np.busday_count( OptionsFrameStart, datetime.date.today()) # Business days
        Futdf["NearFuturesFormula"] = Futdf["Close"] * (1+ (RiskFreeRate * (business_days( pd.to_datetime(Futdf['Date']),  pd.to_datetime(Futdf['NearExpiry']))/365))) - Dividend
        Futdf["MidFuturesFormula"] = Futdf["Close"] * (1+ (RiskFreeRate * (business_days( pd.to_datetime(Futdf['Date']), pd.to_datetime(Futdf['MidExpiry']))/365))) - Dividend
        Futdf["FarFuturesFormula"] = Futdf["Close"] * (1+ (RiskFreeRate * (business_days( pd.to_datetime(Futdf['Date']), pd.to_datetime(Futdf['FarExpiry']))/365))) - Dividend
        # Futdf["OISlope"] = slope(Futdf["Open Interest"],10)
        Average = DailyRet * days
        SD = StdDev * math.sqrt(days)
        
        SD1up = Average + SD
        SD1down = Average - SD
        SD2up = Average + (2 * SD)
        SD2down = Average - (2 * SD)
        SD3up = Average + (3 * SD)
        SD3down = Average - (3 * SD)
        
        StartingPrice = data.iloc[0].Close
        
        SD1upLevel = StartingPrice * math.exp(SD1up)
        SD1downLevel = StartingPrice * math.exp(SD1down)
        SD2upLevel = StartingPrice * math.exp(SD2up)
        SD2downLevel = StartingPrice * math.exp(SD2down)
        SD3upLevel = StartingPrice * math.exp(SD3up)
        SD3downLevel = StartingPrice * math.exp(SD3down)
        
        Futdf.index = Futdf["Date"]
        Futdf.drop("Date", axis=1, inplace=True)

        ax_futures.plot(Futdf.index, Futdf["Close"], color="black",label="Price")
        ax_futures.plot(Futdf.index, Futdf["NearSettlePrice"], color="gray",label="NearSP")
        ax_futures.plot(Futdf.index, Futdf["NearFuturesFormula"], color="silver",label="NearFF")
        
        ax_futures.plot(Futdf.index, Futdf["MidSettlePrice"], color="blue",label="MidSP")
        ax_futures.plot(Futdf.index, Futdf["MidFuturesFormula"], color="skyblue",label="MidFF")
        
        ax_futures.plot(Futdf.index, Futdf["FarSettlePrice"], color="darkorchid",label="FarSP")
        ax_futures.plot(Futdf.index, Futdf["FarFuturesFormula"], color="plum",label="FarFF")
        
        # ax_oi= ax_futures.twinx()
        # ax_oi.plot(Futdf.index, Futdf["Open Interest"],color="oldlace", alpha = 0.3, label="OpenInterest")
        ax_futures.set_ylabel('Price')
        # ax_oi.set_ylabel('Open Interest')
        # ax_oi.grid(b=False)
        # ax_futures.legend()
        # ax_oi.legend()
        # ax_futures.plot(Futdf.index, Futdf["FuturesFormula"],color="blue", label="FuturesFormula")
        # ax_futures.plot(Futdf.index, Futdf["Settle Price"],color="green", label="SettlePrice")

        ax_futures.plot(data.index, [StartingPrice] * len(data.index),label='SD1: '+str(SD)+',Average: '+str(Average) )
        # ax_futures.axhspan(SD2downLevel, SD3downLevel, alpha=0.5, color='lightcoral', label=str(SD3downLevel) + ' -SD3')
        # ax_futures.axhspan(SD1downLevel, SD2downLevel, alpha=0.5, color='lightsalmon', label=str(SD2downLevel)+ ' -SD2')
        ax_futures.axhspan(StartingPrice, SD1downLevel, alpha=0.5, color='mistyrose', label=str(SD1downLevel)+ ' -SD1')
        ax_futures.axhspan(SD1upLevel, StartingPrice, alpha=0.5, color='greenyellow', label=str(SD1upLevel)+ ' +SD1')
        # ax_futures.axhspan(SD2upLevel, SD1upLevel, alpha=0.5, color='lime', label=str(SD2upLevel)+ ' +SD2')
        # ax_futures.axhspan(SD3upLevel, SD2upLevel, alpha=0.5, color='green', label = str(SD3upLevel)+ ' +SD3')
        ax_futures.legend()

    if(ticker != "NIFTY" and ticker != "BANKNIFTY"):
        ax_trades.plot(data.index, data["Trades"], label="Trades")
    ax_trades.plot(data.index, data["Turnover"]/ 100000, label="Turnover")
    # ax_trades.set_ylabel("(Lakh(s))")
    ax_trades.legend()
   
    ax_slope.plot(data.index, data["Slope"], label="Slope")
    ax_close = ax_slope.twinx()
    ax_close.plot(data.index, data["Close"],color="blue",marker="o", label="Price")
    ax_slope.set_ylabel('Slope')
    ax_close.set_ylabel('Closing price')
    ax_close.grid(b=False) # turn off grid #2
    # ax_slope.plot(data.index, data["Close"], label="Price")
    ax_slope.legend()
    
    "Retracement -23.6%, 38.2%, 50%, 61.8%, and 78.6%"
    "Fibonacci extension levels are 161.8%, 261.8% and 423.6%."
    # retracements = [23.6,38.2,50.00,61.8,76.4,78.6,85.40]
    # extensions = [127.2,138.2,150.00,161.8,176.4,261.8,423.6]   

    price_min = data.Low.min()
    price_max = data.High.max()
    diff = price_max - price_min
    #Retracements
    # level1 = price_max - 0.236 * diff
    # level2 = price_max - 0.382 * diff
    # level3 = price_max - 0.5 * diff
    # level4 = price_max - 0.618 * diff
    # level5 = price_max - 0.786 * diff
    level1 = price_min + 0.236 * diff
    level2 = price_min + 0.382 * diff
    level3 = price_min + 0.5 * diff
    level4 = price_min + 0.618 * diff
    level5 = price_min + 0.786 * diff    
    
    ax_fibret.axhspan(level1, price_min, alpha=0.4, color='lightcoral', label=str(level1) + ' (0.236)')
    ax_fibret.axhspan(level2, level1, alpha=0.5, color='lightsalmon', label=str(level2)+ ' (0.382)')
    ax_fibret.axhspan(level3, level2, alpha=0.5, color='mistyrose', label=str(level3)+ ' (0.5)')
    ax_fibret.axhspan(level4, level3, alpha=0.5, color='greenyellow', label=str(level4)+ ' (0.618)')
    ax_fibret.axhspan(level5, level4, alpha=0.5, color='lime', label=str(level5)+ ' (0.786)')
    ax_fibret.axhspan(price_max, level5, alpha=0.5, color='green', label = str(price_max)+ ' (1)')
    ax_fibret.legend()
    # ax_fibret.axhspan(level1, price_min, alpha=0.4, color='lightcoral', label=str(level1) + ' (0.236)')
    # ax_fibret.axhspan(level2, level1, alpha=0.5, color='lightsalmon', label=str(level2)+ ' (0.382)')
    # ax_fibret.axhspan(level3, level2, alpha=0.5, color='mistyrose', label=str(level3)+ ' (0.5)')
    # ax_fibret.axhspan(level4, level3, alpha=0.5, color='lightcyan', label=str(level4)+ ' (0.618)')
    # ax_fibret.axhspan(level5, level4, alpha=0.5, color='powderblue', label=str(level5)+ ' (0.786)')
    # ax_fibret.axhspan(price_max, level5, alpha=0.5, color='deepskyblue')
    # ax_fibret.plot(data.index, level1 * len(data.index), label=str(level1))
    # ax_fibret.plot(data.index, level2 * len(data.index), label=str(level2))
    # ax_fibret.plot(data.index, level3 * len(data.index), label=str(level3))
    # ax_fibret.plot(data.index, level4 * len(data.index), label=str(level4))
    # ax_fibret.plot(data.index, level5 * len(data.index), label=str(level5))
    candlestick_ohlc(ax_fibret, ohlc, colorup="g", colordown="r", width=0.8)


    #Extensons
    level6 = price_max - 1.272 * diff    
    level7 = price_max - 1.382 * diff 
    level8 = price_max - 1.5 * diff 
    level9 = price_max - 1.618 * diff 
    level10 = price_max - 2.618 * diff
    level11 = price_max - 4.236 * diff
    # level6 = price_min + 1.272 * diff    
    # level7 = price_min + 1.382 * diff 
    # level8 = price_min + 1.5 * diff 
    # level9 = price_min + 1.618 * diff 
    # level10 = price_min + 2.618 * diff
    # level11 = price_min + 4.236 * diff
    
    if (FindFeather(OptionsFileName, './Datastore/')):
        ax_maxpain.plot(data.index, data["Close"], label="Price")
        ax_maxpain.plot(data.index, data["MaxPain"],color="blue",marker="o", label="MaxPain")
        ax_pcr = ax_maxpain.twinx()
        ax_pcr.plot(data.index, data["PCR"],color="black",marker="*", label="PCR")
        ax_maxpain.set_ylabel('Price')
        ax_pcr.set_ylabel('PCR')
        ax_pcr.grid(b=False) # turn off grid #2
        # ax_maxpain.plot(data.index, data["Close"], label="Price")
        ax_maxpain.legend()
    else:
        ax_maxpain.axhspan(level6, price_max, alpha=0.5, color='limegreen', label=str(level6)+ ' (1.272)')
        ax_maxpain.axhspan(level7, level6, alpha=0.5, color='lime', label=str(level7)+ ' (1.382)')
        ax_maxpain.axhspan(level8, level7, alpha=0.5, color='deepskyblue', label=str(level8)+ ' (1.5)')
        ax_maxpain.axhspan(level9, level8, alpha=0.5, color='powderblue', label=str(level9)+ ' (1.618)')
        ax_maxpain.legend()
        # ax_fibadv.plot(data.index, level6 * len(data.index), label=str(level6))
        # ax_fibadv.plot(data.index, level7 * len(data.index), label=str(level7))
        # ax_fibadv.plot(data.index, level8 * len(data.index), label=str(level8))
        # ax_fibadv.plot(data.index, level9 * len(data.index), label=str(level9))
        candlestick_ohlc(ax_maxpain, ohlc, colorup="g", colordown="r", width=0.8)    
    
    plt.show()
    
    #Trendlines
    # this will serve as an example for security or index closing prices, or low and high prices
    Trendlinedf = data.copy()
    TLClose = Trendlinedf[-n:].Close
    mins, maxs = trendln.calc_support_resistance(TLClose)
    minimaIdxs, pmin, mintrend, minwindows = trendln.calc_support_resistance((Trendlinedf[-n:].Low, None)) #support only
    mins, maxs = trendln.calc_support_resistance((Trendlinedf[-n:].Low, Trendlinedf[-n:].High))
    (minimaIdxs, pmin, mintrend, minwindows), (maximaIdxs, pmax, maxtrend, maxwindows) = mins, maxs

    idx = Trendlinedf[-n:].index
    tech4 = trendln.plot_sup_res_date((Trendlinedf[-n:].Low, Trendlinedf[-n:].High), idx) #requires pandas
    tech4.set_size_inches((16, 9))
    # plt.savefig('suppres.svg', format='svg')
    plt.show()
    
    return tech1, tech2, tech3, tech4

def Technicals(Scrip):
    OHLCdf = None
    Indicatordf = None
    # Scrip = "RELIANCE"
    print('Technicals for '+ Scrip)
    OHLCFileName = Scrip + '_' + DailyOHLCFilePath #'2020-08-31-G1dataframe.ftr'#
    #Read from feather
    if (FindFeather(OHLCFileName, './Datastore/')):
        OHLCdf = feather.read_feather('./Datastore/'+OHLCFileName)
        Indicatordf = OHLCdf.copy()
        Indicatordf = Indicatordf.set_index("Date")
        if(Scrip is not "INDIAVIX"):
            Indicatordf = MACD(Indicatordf, 12, 26, 9)
        
        Indicatordf = BollBnd(Indicatordf,20)
        # Calculate ATR
        Indicatordf = ATR(Indicatordf,20) #20 day rolling mean

        # Indicatordf["ADX"] = talib.ADX(Indicatordf["High"], Indicatordf["Low"],
        #                                Indicatordf["Close"], timeperiod=20)
        ADXdf = ADX(Indicatordf,20)
        Indicatordf['ADX'] = ADXdf['ADX']
        Indicatordf['DIplusN'] = ADXdf['DIplusN']
        Indicatordf['DIminusN'] = ADXdf['DIminusN']
        #5 day rolling ADX
        Indicatordf['ADXRoll5'] = Indicatordf['ADX'].rolling(5).mean()
        #15 day rolling volume
        Indicatordf['ADXRoll10'] = Indicatordf['ADX'].rolling(15).mean()            
        #5 day rolling volume
        Indicatordf['VolRoll5'] = Indicatordf['Volume'].rolling(5).mean()
        #10 day rolling volume
        Indicatordf['VolRoll10'] = Indicatordf['Volume'].rolling(10).mean()

        # Identify chart patterns (e.g. two crows, three crows, three inside, engulging pattern etc.)
        # OHLCdf["3I"] = talib.CDL3WHITESOLDIERS(OHLCdf["Open"],
        #                                              OHLCdf["High"],
        #                                              OHLCdf["Low"],
        #                                              OHLCdf["Close"])
        
        # Statistical functions (e.g. beta, correlation etc.)
        Indicatordf["Beta"] = talib.BETA(Indicatordf["High"],Indicatordf["Low"],timeperiod=14)
        
        Indicatordf["RSI"] = RSI(Indicatordf,14)
        
        OBVdf = OBV(Indicatordf)
        Indicatordf["OBV"] = OBVdf["obv"]
        Indicatordf["Daily_Ret"] = OBVdf['daily_ret']
        Indicatordf["Log_Ret"] = np.log(1+ OBVdf['daily_ret'])
        
        Indicatordf["Slope"] = slope(Indicatordf["Close"],5)
        
        # Simple DMA - If you change MA timeframes here, you have to hcange in plot_chart
        Indicatordf["10DMA"] = Indicatordf["Close"].rolling(window=10).mean()
        Indicatordf["20DMA"] = Indicatordf["Close"].rolling(window=20).mean()
        Indicatordf["50DMA"] = Indicatordf["Close"].rolling(window=50).mean()
        Indicatordf["100DMA"] = Indicatordf["Close"].rolling(window=100).mean()
        Indicatordf["200DMA"] = Indicatordf["Close"].rolling(window=200).mean() 
       # Indicatordf.iloc[-150:,[8,-1,-2,-3,-4,-5]].plot(figsize=(16,9),grid = True,title = Scrip)     
        # Exponential DMA - If you change MA timeframes here, you have to hcange in plot_chart
        Indicatordf["10DMA-E"] = Indicatordf["Close"].ewm(span=10, adjust=False).mean()
        Indicatordf["20DMA-E"] = Indicatordf["Close"].ewm(span=20, adjust=False).mean()
        Indicatordf["50DMA-E"] = Indicatordf["Close"].ewm(span=50, adjust=False).mean()
        Indicatordf["80DMA-E"] = Indicatordf["Close"].ewm(span=80, adjust=False).mean()
        Indicatordf["140DMA-E"] = Indicatordf["Close"].ewm(span=140, adjust=False).mean()
        #Indicatordf.iloc[-150:,[8,-1,-2,-3,-4,-5]].plot(figsize=(16,9),grid = True,title = Scrip) 
        Indicatordf.reset_index(level=0, inplace=True)
# ###################################################################################################            
        tech1, tech2, tech3, tech4 = plot_chart(Indicatordf,50,Scrip,0)
###################################################################################################
        # feather.write_feather(Indicatordf, 'E:/Harish/OGN/TechnicalFrames/'+Scrip+'-dataframe.ftr')
    return tech1, tech2, tech3, tech4

def GetVolatilityData(sym,data_file_path,bench_file_path):
    # Prepare the price and benchmark data to be used to calculate volatility
    
    price_data = feather.read_feather(data_file_path)
    price_data = price_data.iloc[-300:]
        
    if 'Symbol' in price_data.columns:
        price_data.rename(columns={'Symbol': 'symbol'}, inplace=True)
    price_data = price_data.assign(symbol=sym)        
    price_data = price_data.set_index('Date')
            
    bench_data = feather.read_feather(bench_file_path)
    if sym == 'NIFTY' or sym == 'BANKNIFTY' or sym == 'FINNIFTY':
        bench_data = bench_data.iloc[-300:]
    else:
        AnamolyDate = date(2020,9,28) #September 28 data for stock prices not available
        #March30 and march 31-2021 FnO data is not available on NSE site!!!!!!
        bench_data = bench_data.iloc[-301:]
        bench_data = bench_data[bench_data.Date != AnamolyDate]
        
    if 'Symbol' in bench_data.columns:
        bench_data.rename(columns={'Symbol': 'symbol'}, inplace=True)
    bench_data = bench_data.assign(symbol='NIFTY')        
    bench_data = bench_data.set_index('Date')
    
    return price_data, bench_data
    
#######################################################################################3
   
#     ESTIMATORS = [
#     'GarmanKlass',
#     'HodgesTompkins',
#     'Kurtosis',
#     'Parkinson',
#     'Raw',
#     'RogersSatchell',
#     'Skew',
#     'YangZhang'
# ]
# estimator windows

def VolatilityTest(sym):
    # sym = 'RELIANCE'
    window = 30
    windows = [3, 5, 10, 20, 30, 60, 90]
    quantiles = [0.25, 0.75]
    bins = 100
    density = True
    est = 'YangZhang'
    TopRecos = 1
    global ExpiryDateList
    global ThreeThursdayDateList
    global AllThursdayDateList
    
    ThreeThursdayDateList = []
    AllThursdayDateList = []
    Next3Thursdays(CurrentDate)

    for d in AllThursdays(CurrentDate):
        if d in OptionChainHolidayList:
            d -= relativedelta(days=1) 
        AllThursdayDateList.append(d)
    
    DownloadOptionChain(sym)
    
    if(sym == 'NIFTY' or sym == 'BANKNIFTY' or sym == 'FINNIFTY'):
        ExpiryDateList = AllThursdayDateList
    else:
        ExpiryDateList = ThreeThursdayDateList
        
    
    if sym == 'FINNIFTY':
        sym = 'Nifty Fin Service'
    
    # bench = 'NIFTY' #None #'NIFTY'
    data_file_path = './Datastore/'+sym+'_ohlc.ftr'
    bench_file_path = './Datastore/NIFTY_ohlc.ftr'
    price_data, bench_data = GetVolatilityData(sym,data_file_path,bench_file_path)
    
    # initialize class
    vol = VolatilityEstimator(
        price_data=price_data,
        estimator=est,
        bench_data=bench_data
    )
    
    vol.term_sheet(
        window,
        windows,
        quantiles,
        bins,
        density
    )


def OnlyTechnicalCharts(sym):
    tech1, onlytech1, onlytech2, onlytech3 = Technicals(sym)
    
    filename = sym + '_Technicals_' + pd.datetime.now().strftime("%Y-%m-%d--%H-%M-%S %p") + '.pdf'
    fn = os.path.abspath(os.path.join(u'..', u'nsepywork/term-sheets', filename))
    ppt = PdfPages(fn)
    
    ppt.savefig(tech1)
    ppt.savefig(onlytech1)
    ppt.savefig(onlytech2)
    ppt.savefig(onlytech3)        

    figt = plt.figure(figsize=(8, 6))

    plt.axis('off')
    figt.tight_layout()
    ppt.savefig(figt)
    ppt.close()
    
    print('%s output complete' % filename)

# VolatilityTest('COROMANDEL')
# OnlyTechnicalCharts('COROMANDEL')
############################################################################
# OldOptionsdf = feather.read_feather('./Option chain - Dec 14/2021-06-13-RELIANCEoption-chain-equity-derivatives-2021-08-26.ftr')
# call plt.show() on any of the below...
# _, plt = vol.cones(windows=windows, quantiles=quantiles)
# _, plt = vol.rolling_quantiles(window=window, quantiles=quantiles)
# _, plt = vol.rolling_extremes(window=window)
# _, plt = vol.rolling_descriptives(window=window)
# _, plt = vol.histogram(window=window, bins=bins, density=density)

# if bench is not None:
#     _, plt = vol.benchmark_compare(window=window)
#     _, plt = vol.benchmark_correlation(window=window)
# plt.show()


