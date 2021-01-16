from selenium import webdriver
from selenium.webdriver import Firefox
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
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
import math
from nsepy.derivatives import get_expiry_date
import datetime as dt
from datetime import date
from dateutil.relativedelta import *
import pandas as pd
import glob
import models
from scipy.stats import norm

ExpiryDates = []
ExpiryDateList = []
ThreeThursdayDateList = []
AllThursdayDateList = []
TopRecos = 2

OptionChainHolidayList = ['2021-01-26','2021-03-11','2021-03-29','2021-04-02','2021-04-14','2021-04-21','2021-05-13','2021-07-21','2021-08-19','2021-09-10','2021-10-15','2021-11-05','2021-11-19']
OptionChainHolidayList = [dt.datetime.strptime(date, '%Y-%m-%d').date() for date in OptionChainHolidayList]

def Next3Thursdays(dt):
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
   CurrentDate = datetime.date.today()   # Today
   CurrentYear = CurrentDate.year
   CurrentMonth = CurrentDate.month
   d += timedelta(days = (3 - d.weekday() + 7) % 7)         # First Thursday
   while d.year == CurrentYear and d.month < (CurrentMonth + 3):
      yield d
      d += timedelta(days = 7)
        
def DownloadOptionChain(sym):
    CurrentDate = datetime.date.today()
    Next3Thursdays(CurrentDate)

    for d in AllThursdays(CurrentDate):
        if d in OptionChainHolidayList:
            d -= relativedelta(days=1) 
        AllThursdayDateList.append(d)

    ChainOptions = webdriver.ChromeOptions()
    ChainOptions.add_argument("--disable-blink-features")
    ChainOptions.add_argument("--disable-blink-features=AutomationControlled")
    # ChainOptions.add_argument('--headless')
    browser = webdriver.Chrome(options=ChainOptions)
    browser.implicitly_wait(10)
    browser.set_page_load_timeout(20)
    browser.get('https://www.nseindia.com/option-chain')
    
    timeout = 5
    try:
        element_present = EC.presence_of_element_located((By.ID, 'select_symbol'))
        WebDriverWait(browser, timeout).until(element_present)
    except TimeoutException:
        print('Timed out waiting for page to load')

    if(sym == 'NIFTY' or sym == 'BANKNIFTY' or sym == 'FINNIFTY'):
        search_form = browser.find_element_by_id('equity_optionchain_select')
        search_form.send_keys(sym)
        for ExpiryDateDownload in AllThursdayDateList:
            search_form = browser.find_element_by_id('expirySelect')
            search_form.send_keys(ExpiryDateDownload.strftime("%d-%b-%Y"))
            time.sleep(2)
            content = browser.find_element_by_class_name('xlsdownload').click()
            while not os.path.exists(r'C:\Users\User\Downloads\option-chain-equity-derivatives.csv'):
                time.sleep(1)
            shutil.move(r'C:\Users\User\Downloads\option-chain-equity-derivatives.csv',r'.\Option chain - Dec 14\option-chain-equity-derivatives.csv')
            shutil.move(r'.\Option chain - Dec 14\option-chain-equity-derivatives.csv',r'.\Option chain - Dec 14\\' + 
              CurrentDate.strftime("%Y-%m-%d") + '-'+ sym + 'option-chain-equity-derivatives-' +  
              ExpiryDateDownload.strftime("%Y-%m-%d") + '.csv')
    else:
        search_form = browser.find_element_by_id('select_symbol')
        search_form.send_keys(sym)
        search_form = browser.find_element_by_id("symbolSearchGo")
        # clicking on the button
        search_form.click()
        for ExpiryDateDownload in ThreeThursdayDateList:
            search_form = browser.find_element_by_id('expirySelect')
            search_form.send_keys(ExpiryDateDownload.strftime("%d-%b-%Y"))
            time.sleep(2)
            content = browser.find_element_by_class_name('xlsdownload').click()
            while not os.path.exists(r'C:\Users\User\Downloads\option-chain-equity-derivatives.csv'):
                time.sleep(1)
            shutil.move(r'C:\Users\User\Downloads\option-chain-equity-derivatives.csv',r'.\Option chain - Dec 14\option-chain-equity-derivatives.csv')
            shutil.move(r'.\Option chain - Dec 14\option-chain-equity-derivatives.csv',r'.\Option chain - Dec 14\\' + 
              CurrentDate.strftime("%Y-%m-%d") + '-'+ sym + 'option-chain-equity-derivatives-' +  
              ExpiryDateDownload.strftime("%Y-%m-%d") + '.csv')

    browser.close()

def FindFeather(name, path):
    for root, dirs, files in os.walk(path):
        if name in files:
            return os.path.join(root, name)

def UpdateOptionChainTable(ExpiryDate,Symbol):
    OptionChain = CurrentDate.strftime("%Y-%m-%d") + '-' + Symbol + 'option-chain-equity-derivatives-'+ ExpiryDate.strftime("%Y-%m-%d") + '.csv'
    # OptionChain = CurrentDate.strftime("%Y-%m-%d") + '-TATAMOTORSoption-chain-equity-derivatives-'+ ExpiryDate.strftime("%Y-%m-%d") + '.csv'
    # print('Symbol = ' + Symbol)
    # print('expiry = ',ExpiryDate.strftime("%Y-%m-%d"))
    
    OptionChainCSVdf = pd.read_csv('./Option chain - Dec 14/'+ OptionChain, header = 1)
    
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
        fig = plt.figure(figsize=(16, 12))
        ax0 = plt.subplots()
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

        arrowprops = dict( 
        arrowstyle = "->", 
        connectionstyle = "angle3,angleA=90,angleB=0")
          # connectionstyle = "angle, angleA = 0, angleB = 90,rad = 10"
          
        buyarrowprops = dict( 
        arrowstyle = "->", 
        connectionstyle = "angle, angleA = 0, angleB = 90,rad = 10")          
        offset = 72
        
        for i in ExpiryDateList:
                if i > CurrentDate:
                    try:
                            # print('Scattering for date '+ i.strftime("%Y%m%d"))
                        CallOptionChainIVdf, PutOptionChainIVdf = UpdateOptionChainTable(i,self._symbol[1])
                        cones.scatter(CallOptionChainIVdf['DaysToExpiry'],CallOptionChainIVdf['IV'],color='b')
                        cones.scatter(PutOptionChainIVdf['DaysToExpiry'],PutOptionChainIVdf['IV1'],color='r')
                        #Important to annotate only outlier points
                        CallOptionChainIVdf = CallOptionChainIVdf.sort_values(by=['IV']) 
                        PutOptionChainIVdf = PutOptionChainIVdf.sort_values(by=['IV1'])
                        
                        #Sell Recos for CE       + ',IV = ' (CallOptionChainIVdf['IV'][ind]*100).astype(str),
                        for ind in CallOptionChainIVdf[-TopRecos:].index:
                            OptionString = str(CallOptionChainIVdf['STRIKE PRICE'][ind]) + ' CE, LTP: ' + CallOptionChainIVdf['LTP'][ind] + ' ' + CallOptionChainIVdf['Expiry'][ind].strftime("%b-%d")
                            cones.annotate(OptionString,
                                           xy = (CallOptionChainIVdf['DaysToExpiry'][ind], CallOptionChainIVdf['IV'][ind]),
                                           color='r', xytext =(3 * offset,2 * offset), textcoords ='offset points',arrowprops = arrowprops,
                                           horizontalalignment='right', verticalalignment='top')
                            print('[SELL '+ self._symbol[1] +'] '+ OptionString, sep='\n')
                        # Sell Recos for PE     + ',IV1 = ' + (PutOptionChainIVdf['IV1'][ind]*100).astype(str)
                        for ind in PutOptionChainIVdf[-TopRecos:].index:
                            OptionString = str(PutOptionChainIVdf['STRIKE PRICE'][ind]) + ' PE, LTP: ' + PutOptionChainIVdf['LTP.1'][ind] + ' ' + PutOptionChainIVdf['Expiry'][ind].strftime("%b-%d")
                            cones.annotate(OptionString,
                                            xy = (PutOptionChainIVdf['DaysToExpiry'][ind], PutOptionChainIVdf['IV1'][ind]),
                                            color='r', xytext =(3 * offset, 1 * offset), textcoords ='offset points',arrowprops = arrowprops ,
                                            horizontalalignment='left', verticalalignment='top')
                            print('[SELL '+ self._symbol[1] +'] '+ OptionString, sep='\n')
                        #Buy Recos for CE    + ',IV = ' + (CallOptionChainIVdf['IV'][ind]*100).astype(str)
                        for ind in CallOptionChainIVdf.head(TopRecos).index:
                            OptionString = str(CallOptionChainIVdf['STRIKE PRICE'][ind]) + ' CE, LTP: ' + CallOptionChainIVdf['LTP'][ind] + ' ' + CallOptionChainIVdf['Expiry'][ind].strftime("%b-%d")
                            cones.annotate(OptionString,
                                            xy = (CallOptionChainIVdf['DaysToExpiry'][ind], CallOptionChainIVdf['IV'][ind]),
                                            color='b', xytext =(2 * CallOptionChainIVdf['DaysToExpiry'][ind], -3 * CallOptionChainIVdf['DaysToExpiry'][ind]), textcoords ='offset points', arrowprops = buyarrowprops,
                                            horizontalalignment='left', verticalalignment='bottom')
                            print('[BUY '+ self._symbol[1] +'] '+ OptionString, sep='\n')
                        #Buy Recos for PE      + ',IV1 = ' + (PutOptionChainIVdf['IV1'][ind]*100).astype(str)
                        for ind in PutOptionChainIVdf.head(TopRecos).index:
                            OptionString = str(PutOptionChainIVdf['STRIKE PRICE'][ind]) + ' PE, LTP: ' + PutOptionChainIVdf['LTP.1'][ind] + ' ' + PutOptionChainIVdf['Expiry'][ind].strftime("%b-%d")
                            cones.annotate(OptionString,
                                            xy = (PutOptionChainIVdf['DaysToExpiry'][ind], PutOptionChainIVdf['IV1'][ind]),
                                            color='b', xytext =(4 * offset, -4 * PutOptionChainIVdf['DaysToExpiry'][ind]), textcoords ='offset points', arrowprops = buyarrowprops,
                                            horizontalalignment='right', verticalalignment='bottom')
                            print('[BUY '+ self._symbol[1] +'] '+ OptionString, sep='\n')
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
        cones.set_title('Volatility Cone ' + self._estimator + ' (' + self._symbol[1] + ', daily ' + self._start.strftime("%Y-%m-%d") + ' to ' + self._end.strftime("%Y-%m-%d") + ')')

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
        
        cones_fig, cones_plt = self.cones(windows=windows, quantiles=quantiles)
        rolling_quantiles_fig, rolling_quantiles_plt = self.rolling_quantiles(window=window, quantiles=quantiles)
        rolling_extremes_fig, rolling_extremes_plt = self.rolling_extremes(window=window)
        rolling_descriptives_fig, rolling_descriptives_plt = self.rolling_descriptives(window=window)
        histogram_fig, histogram_plt = self.histogram(window=window, bins=bins, density=density)
        benchmark_compare_fig, benchmark_compare_plt = self.benchmark_compare(window=window)
        benchmark_corr_fig, benchmark_corr_plt = self.benchmark_correlation(window=window)
        benchmark_regression = self.benchmark_regression(window=window)
        
        filename = self._symbol[1] + self._estimator + '_termsheet_' + CurrentDate.strftime("%Y-%m-%d--%H-%M-%S %p") + '.pdf'
        fn = os.path.abspath(os.path.join(u'..', u'nsepywork/term-sheets', filename))
        pp = PdfPages(fn)
        
        pp.savefig(cones_fig)
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


def GetVolatilityData(sym,data_file_path,bench_file_path):
    # Prepare the price and benchmark data to be used to calculate volatility
    price_data = feather.read_feather(data_file_path)
    price_data = price_data.iloc[-300:]
        
    if 'Symbol' in price_data.columns:
        price_data.rename(columns={'Symbol': 'symbol'}, inplace=True)
    price_data = price_data.assign(symbol=sym)        
    price_data = price_data.set_index('Date')
            
    bench_data = feather.read_feather(bench_file_path)
    if sym == 'NIFTY' or sym == 'BANKNIFTY':
        bench_data = bench_data.iloc[-300:]
    else:
        AnamolyDate = date(2020,9,28) #September 28 data for stock prices not available
        bench_data = bench_data.iloc[-301:]
        bench_data = bench_data[bench_data.Date != AnamolyDate]
        
    if 'Symbol' in bench_data.columns:
        bench_data.rename(columns={'Symbol': 'symbol'}, inplace=True)
    bench_data = bench_data.assign(symbol='NIFTY')        
    bench_data = bench_data.set_index('Date')
    
    return price_data, bench_data
    
#######################################################################################3

# estimator windows
window = 30
windows = [3, 5, 10, 20, 30, 60, 90]
quantiles = [0.25, 0.75]
bins = 100
density = True
sym = 'RELIANCE'

ThreeThursdayDateList = []
AllThursdayDateList = []
DownloadOptionChain(sym)

# bench = 'NIFTY' #None #'NIFTY'
data_file_path = './Datastore/'+sym+'_ohlc.ftr'
bench_file_path = './Datastore/NIFTY_ohlc.ftr'

CurrentDate = datetime.date.today()
CurrentDay = CurrentDate.day

path = './Option chain - Dec 14/' # use your path
all_files = glob.glob(path + CurrentDate.strftime("%Y-%m-%d") + '-' + sym + "*.csv")

ExpiryDateList.clear()
for filename in all_files:
    Edate = datetime.datetime.strptime(filename[-14:-4], '%Y-%m-%d').date()
    ExpiryDateList.append(Edate)

price_data, bench_data = GetVolatilityData(sym,data_file_path,bench_file_path)
# spx_price_data = data.yahoo_helper(bench, bench_file_path)
# if sym is 'NIFTY':
#     bench_data = None
    
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
# initialize class
est = 'YangZhang'
TopRecos = 2
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

############################################################################

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


