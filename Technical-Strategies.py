# =============================================================================
# Backtesting strategy - IV : combining renko with other MACD, OBV
# Author : HRTR
# =============================================================================

import numpy as np
import pandas as pd
from stocktrends import Renko
from stocktrends import indicators
import statsmodels.api as sm
import copy
import pyarrow
import pyarrow.feather as feather
import datetime
from datetime import date

tickers = []
ohlc_intraday = {}
ohlc_renko = {}
tickers_signal = {}
tickers_ret = {}

def GetTickers():
    NiftyOHLC = feather.read_feather('./Datastore/NIFTY_ohlc.ftr')
    OHLCStartDate = NiftyOHLC.iloc[-1].Date
    OHLCBhavFtr = 'sec_bhavdata_full_' + OHLCStartDate.strftime("%d%m%Y") + '.csv.ftr'
    NSESymbols = feather.read_feather('./New NSE site/'+ OHLCBhavFtr)
    tickers.append(NSESymbols['SYMBOL'])

def slope(ser,n):
    "function to calculate the slope of n consecutive points on a plot"
    slopes = [i*0 for i in range(n-1)]
    for i in range(n,len(ser)+1):
        y = ser[i-n:i]
        x = np.array(range(n))
        y_scaled = (y - y.min())/(y.max() - y.min())
        x_scaled = (x - x.min())/(x.max() - x.min())
        x_scaled = sm.add_constant(x_scaled)
        model = sm.OLS(y_scaled,x_scaled)
        results = model.fit()
        slopes.append(results.params[-1])
    slope_angle = (np.rad2deg(np.arctan(np.array(slopes))))
    return np.array(slope_angle)

def ATR(DF,n):
    "function to calculate True Range and Average True Range"
    df = DF.copy()
    df['H-L']=abs(df['High']-df['Low'])
    df['H-PC']=abs(df['High']-df['Close'].shift(1))
    df['L-PC']=abs(df['Low']-df['Close'].shift(1))
    df['TR']=df[['H-L','H-PC','L-PC']].max(axis=1,skipna=False)
    df['ATR'] = df['TR'].rolling(n).mean()
    #df['ATR'] = df['TR'].ewm(span=n,adjust=False,min_periods=n).mean()
    df2 = df.drop(['H-L','H-PC','L-PC'],axis=1)
    return df2
    
def renko_DF(DF,ticker):
    "function to convert ohlc data into renko bricks"
    df = DF.copy()
    if(ticker is "NIFTY" or ticker is "BANKNIFTY"):
        df = df.iloc[:,[0,2,3,1,4,5]]
    else:    
        df = df.iloc[:,[0,5,6,4,8,10]]
    df.rename(columns = {"Date" : "date", "High" : "high","Low" : "low", "Open" : "open","Close" : "close", "Volume" : "volume"}, inplace = True)
    df2 = Renko(df)
    df2.brick_size = max(0.5,round(DF["ATR"].iloc[-1],0))
    renko_df = df2.get_ohlc_data()
    renko_df["bar_num"] = np.where(renko_df["uptrend"]==True,1,np.where(renko_df["uptrend"]==False,-1,0))
    for i in range(1,len(renko_df["bar_num"])):
        if renko_df["bar_num"][i]>0 and renko_df["bar_num"][i-1]>0:
            renko_df["bar_num"][i]+=renko_df["bar_num"][i-1]
        elif renko_df["bar_num"][i]<0 and renko_df["bar_num"][i-1]<0:
            renko_df["bar_num"][i]+=renko_df["bar_num"][i-1]
    renko_df.drop_duplicates(subset="date",keep="last",inplace=True)
    return renko_df

 # directory with ohlc value for each stock            

def ReadDataFrames(Depth):
    # Depth = 200
    for i in tickers:
        ScripFileName = i + '-dataframe.ftr'
        # ScripFileName = 'REDINGTON-dataframe.ftr'
        try:
            Tickerdf = feather.read_feather('./TechnicalFrames/'+ScripFileName)
            ohlc_intraday[i] = Tickerdf.tail(Depth).reset_index(drop=True)
        except:
            print(i," :failed to fetch data...retrying")
            continue

################################Backtesting####################################
#Merging renko df with original ohlc df
# ticker = "NIFTY"
def RenkoMerge():
    df = copy.deepcopy(ohlc_intraday)
    tickers = list(ohlc_intraday.keys()) # redefine tickers variable after removing any tickers with corrupted data
    for ticker in tickers:
        print("merging for ",ticker)
        # demo = df[ticker]
        renko = renko_DF(df[ticker],ticker)
        renko.columns = ["Date","open","high","low","close","uptrend","bar_num"]
        ohlc_renko[ticker] = df[ticker].merge(renko.loc[:,["Date","bar_num"]],how="outer",on="Date")
        ohlc_renko[ticker]["bar_num"].fillna(method='ffill',inplace=True)
        ohlc_renko[ticker]["macd_slope"] = slope(ohlc_renko[ticker]["MACD"],5)
        ohlc_renko[ticker]["macd_sig_slope"] = slope(ohlc_renko[ticker]["Signal"],5)
        ohlc_renko[ticker]["obv_slope"]= slope(ohlc_renko[ticker]["OBV"],5)
        ohlc_renko[ticker]["adx_slope"]= slope(ohlc_renko[ticker]["ADX"],5)
        tickers_signal[ticker] = ""
        # tickers_ret[ticker] = []
       
#Identifying signals and calculating daily return

def CalculateSignals():
    tickers = list(ohlc_intraday.keys())
    for ticker in tickers:
        print("calculating signal for ",ticker)
        for i in range(len(ohlc_intraday[ticker])):
            if tickers_signal[ticker] == "":
                # tickers_ret[ticker].append(0)
                if i > 0:
                    # if ohlc_renko[ticker]["bar_num"][i]>=2 and ohlc_renko[ticker]["MACD"][i]>ohlc_renko[ticker]["Signal"][i] and ohlc_renko[ticker]["macd_slope"][i]>ohlc_renko[ticker]["macd_sig_slope"][i]:
                    CandleLength = 0.1 * (ohlc_renko[ticker]["High"][i]-ohlc_renko[ticker]["Low"][i])
                    VolumeSpike = 1.15 * (ohlc_renko[ticker]['VolRoll5'][i])
                    WickSize = ohlc_renko[ticker]["High"][i]-ohlc_renko[ticker]["Close"][i]
                    if ohlc_renko[ticker]["bar_num"][i]>=2 and ohlc_renko[ticker]["macd_slope"][i]>ohlc_renko[ticker]["macd_sig_slope"][i] and ohlc_renko[ticker]["obv_slope"][i]>30 and ohlc_renko[ticker]["adx_slope"][i]>30 and ohlc_renko[ticker]["DIplusN"][i]>ohlc_renko[ticker]["DIminusN"][i] and ohlc_renko[ticker]['Volume'][i] > VolumeSpike and WickSize < CandleLength and (ohlc_renko[ticker]['Close'][i] - ohlc_renko[ticker]['Close'][i-1])>0:
                        tickers_signal[ticker] = "Buy"
                    elif ohlc_renko[ticker]["bar_num"][i]<=-2 and ohlc_renko[ticker]["macd_slope"][i]<ohlc_renko[ticker]["macd_sig_slope"][i] and ohlc_renko[ticker]["obv_slope"][i]<-30 and ohlc_renko[ticker]["DIplusN"][i]<ohlc_renko[ticker]["DIminusN"][i]:
                        tickers_signal[ticker] = "Sell"
            
            elif tickers_signal[ticker] == "Buy":
                # tickers_ret[ticker].append((ohlc_renko[ticker]["Close"][i]/ohlc_renko[ticker]["Close"][i-1])-1)
                if i > 0:
                    if ohlc_renko[ticker]["bar_num"][i]<=-2 and ohlc_renko[ticker]["obv_slope"][i]<-30 and ohlc_renko[ticker]["macd_slope"][i]<ohlc_renko[ticker]["macd_sig_slope"][i] and ohlc_renko[ticker]["DIplusN"][i]>ohlc_renko[ticker]["DIminusN"][i]:
                        tickers_signal[ticker] = "Sell"
                    elif ohlc_renko[ticker]["MACD"][i]<ohlc_renko[ticker]["Signal"][i] and ohlc_renko[ticker]["macd_slope"][i]<ohlc_renko[ticker]["macd_sig_slope"][i] and ohlc_renko[ticker]["obv_slope"][i]<-30 and ohlc_renko[ticker]["adx_slope"][i]<-30 and ohlc_renko[ticker]["DIplusN"][i]<ohlc_renko[ticker]["DIminusN"][i]:
                        tickers_signal[ticker] = ""
                    
            elif tickers_signal[ticker] == "Sell":
                # tickers_ret[ticker].append((ohlc_renko[ticker]["Close"][i-1]/ohlc_renko[ticker]["Close"][i])-1)
                if i > 0:
                    CandleLength = 0.1 * (ohlc_renko[ticker]["High"][i]-ohlc_renko[ticker]["Low"][i])
                    VolumeSpike = 1.15 * (ohlc_renko[ticker]['VolRoll5'][i])
                    WickSize = ohlc_renko[ticker]["High"][i]-ohlc_renko[ticker]["Close"][i]
                    if ohlc_renko[ticker]["bar_num"][i]>=2 and ohlc_renko[ticker]["obv_slope"][i]>30 and ohlc_renko[ticker]["macd_slope"][i]>ohlc_renko[ticker]["macd_sig_slope"][i] and ohlc_renko[ticker]["adx_slope"][i]>30 and ohlc_renko[ticker]["DIplusN"][i]>ohlc_renko[ticker]["DIminusN"][i] and ohlc_renko[ticker]['Volume'][i] > VolumeSpike and WickSize < CandleLength and (ohlc_renko[ticker]['Close'][i] - ohlc_renko[ticker]['Close'][i-1])>0:
                        tickers_signal[ticker] = "Buy"
                    elif ohlc_renko[ticker]["MACD"][i]>ohlc_renko[ticker]["Signal"][i] and ohlc_renko[ticker]["macd_slope"][i]>ohlc_renko[ticker]["macd_sig_slope"][i]:
                        tickers_signal[ticker] = ""

def main():
    GetTickers()
    ReadDataFrames(Depth = 50)    
    RenkoMerge()
    CalculateSignals()
    df = pd.DataFrame.from_dict(tickers_signal,orient='index')
    df.to_csv("Shortterm"+str(date.today()))