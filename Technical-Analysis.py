# -*- coding: utf-8 -*-
"""
Created on Sun Jul 26 17:11:12 2020
Technical Analysis Modules
@author: HRTR
"""
#Includes
import datetime as dt
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import urllib.request, urllib.error, urllib.parse
import pandas as pd
import pyarrow
import pyarrow.feather as feather
from stocktrends import Renko
from stocktrends import indicators
import numpy as np
import statsmodels.api as sm
import copy
import sys
import talib
%matplotlib inline
import seaborn as sns
import matplotlib.ticker as mticker
import matplotlib.dates as mdates
from matplotlib.dates import date2num
from mpl_finance import candlestick_ohlc
import trendln
import pylab
matplotlib.rcParams.update({'font.size': 9})
import os

sns.set(style='darkgrid', context='talk', palette='Dark2')

my_year_month_fmt = mdates.DateFormatter('%m/%y')

talib.get_function_groups()

DailyOHLCFilePath = "ohlc.ftr";
IntradayFilePath = "intraday.ftr"
MonthlyFuturesFilePath = "monthly-futures.ftr"
MonthlyOptionsFilePath = "monthly-options.ftr"
FXHistory = "FXHistory.ftr"
PEHistory = "PEHistory.ftr"

NSE500ScripList = ["3MINDIA","ACC","AIAENG","APLAPOLLO","AUBANK","AARTIIND","AAVAS","ABBOTINDIA",
                    "ADANIGAS","ADANIGREEN","ADANIPORTS","ADANIPOWER","ADANITRANS","ABCAPITAL","ABFRL",
                    "ADVENZYMES","AEGISCHEM","AFFLE","AJANTPHARM","AKZOINDIA","APLLTD","ALKEM","ALLCARGO",
                    "AMARAJABAT","AMBER","AMBUJACEM","APOLLOHOSP","APOLLOTYRE","ARVINDFASN","ASAHIINDIA",
                    "ASHOKLEY","ASHOKA","ASIANPAINT","ASTERDM","ASTRAZEN","ASTRAL","ATUL","AUROPHARMA",
                    "AVANTIFEED","DMART","AXISBANK","BASF","BEML","BSE","BAJAJ-AUTO","BAJAJCON","BAJAJELEC",
                    "BAJFINANCE","BAJAJFINSV","BAJAJHLDNG","BALKRISIND","BALMLAWRIE","BALRAMCHIN","BANDHANBNK",
                    "BANKBARODA","BANKINDIA","MAHABANK","BATAINDIA","BAYERCROP","BERGEPAINT","BDL","BEL",
                    "BHARATFORG","BHEL","BPCL","BHARTIARTL","INFRATEL","BIOCON","BIRLACORPN","BSOFT",
                    "BLISSGVS","BLUEDART","BLUESTARCO","BBTC","BOMDYEING","BOSCHLTD","BRIGADE","BRITANNIA",
                    "CARERATING","CCL","CESC","CRISIL","CADILAHC","CANFINHOME","CANBK","CAPLIPOINT","CGCL",
                    "CARBORUNIV","CASTROLIND","CEATLTD","CENTRALBK","CDSL","CENTURYPLY","CERA","CHALET",
                    "CHAMBLFERT","CHENNPETRO","CHOLAHLDNG","CHOLAFIN","CIPLA","CUB","COALINDIA","COCHINSHIP",
                    "COLPAL","CONCOR","COROMANDEL","CREDITACC","CROMPTON","CUMMINSIND","CYIENT","DBCORP",
                    "DCBBANK","DCMSHRIRAM","DLF","DABUR","DALBHARAT","DEEPAKNTR","DELTACORP","DHFL","DBL",
                    "DISHTV","DCAL","DIVISLAB","DIXON","LALPATHLAB","DRREDDY","EIDPARRY","EIHOTEL","EDELWEISS",
                    "EICHERMOT","ELGIEQUIP","EMAMILTD","ENDURANCE","ENGINERSIN","EQUITAS","ERIS","ESCORTS",
                    "ESSELPACK","EXIDEIND","FDC","FEDERALBNK","FMGOETZE","FINEORG","FINCABLES","FINPIPE","FSL",
                    "FORTIS","FCONSUMER","FLFL","FRETAIL","GAIL","GEPIL","GET&D","GHCL","GMRINFRA","GALAXYSURF",
                    "GARFIBRES","GAYAPROJ","GICRE","GILLETTE","GLAXO","GLENMARK","GODFRYPHLP","GODREJAGRO",
                    "GODREJCP","GODREJIND","GODREJPROP","GRANULES","GRAPHITE","GRASIM","GESHIP","GREAVESCOT",
                    "GRINDWELL","GUJALKALI","GUJGASLTD","GMDCLTD","GNFC","GPPL","GSFC","GSPL","GULFOILLUB",
                    "HEG","HCLTECH","HDFCAMC","HDFCBANK","HDFCLIFE","HFCL","HATSUN","HAVELLS","HEIDELBERG",
                    "HERITGFOOD","HEROMOTOCO","HEXAWARE","HSCL","HIMATSEIDE","HINDALCO","HAL","HINDCOPPER",
                    "HINDPETRO","HINDUNILVR","HINDZINC","HONAUT","HUDCO","HDFC","ICICIBANK","ICICIGI",
                    "ICICIPRULI","ISEC","ICRA","IDBI","IDFCFIRSTB","IDFC","IFBIND","IFCI","IIFL","IRB",
                    "IRCON","ITC","ITDCEM","ITI","INDIACEM","ITDC","IBULHSGFIN","IBULISL","IBREALEST",
                    "IBVENTURES","INDIAMART","INDIANB","IEX","INDHOTEL","IOC","IOB","INDOSTAR","IGL",
                    "INDUSINDBK","INFIBEAM","NAUKRI","INFY","INOXLEISUR","INTELLECT","INDIGO","IPCALAB",
                    "JBCHEPHARM","JKCEMENT","JKLAKSHMI","JKPAPER","JKTYRE","JMFINANCIL","JSWENERGY","JSWSTEEL",
                    "JAGRAN","JAICORPLTD","JISLJALEQS","J&KBANK","JAMNAAUTO","JINDALSAW","JSLHISAR","JSL",
                    "JINDALSTEL","JCHAC","JUBLFOOD","JUBILANT","JUSTDIAL","JYOTHYLAB","KPRMILL","KEI","KNRCON",
                    "KPITTECH","KRBL","KAJARIACER","KALPATPOWR","KANSAINER","KTKBANK","KARURVYSYA","KSCL",
                    "KEC","KENNAMET","KIRLOSENG","KOLTEPATIL","KOTAKBANK","L&TFH","LTTS","LICHSGFIN",
                    "LAXMIMACH","LAKSHVILAS","LTI","LT","LAURUSLABS","LEMONTREE","LINDEINDIA","LUPIN",
                    "LUXIND","MASFIN","MMTC","MOIL","MRF","MAGMA","MGL","MAHSCOOTER","MAHSEAMLES","M&MFIN",
                    "M&M","MAHINDCIE","MHRIL","MAHLOG","MANAPPURAM","MRPL","MARICO","MARUTI","MFSL",
                    "METROPOLIS","MINDTREE","MINDACORP","MINDAIND","MIDHANI","MOTHERSUMI","MOTILALOFS",
                    "MPHASIS","MCX","MUTHOOTFIN","NATCOPHARM","NBCC","NCC","NESCO","NHPC","NIITTECH",
                    "NLCINDIA","NMDC","NTPC","NH","NATIONALUM","NFL","NBVENTURES","NAVINFLUOR","NESTLEIND",
                    "NETWORK18","NILKAMAL","NAM-INDIA","OBEROIRLTY","ONGC","OIL","OMAXE","OFSS","ORIENTCEM",
                    "ORIENTELEC","ORIENTREF","PCJEWELLER","PIIND","PNBHOUSING","PNCINFRA","PTC","PVR",
                    "PAGEIND","PARAGMILK","PERSISTENT","PETRONET","PFIZER","PHILIPCARB","PHOENIXLTD",
                    "PIDILITIND","PEL","POLYCAB","PFC","POWERGRID","PRAJIND","PRESTIGE","PRSMJOHNSN","PGHL",
                    "PGHH","PNB","QUESS","RBLBANK","RECLTD","RITES","RADICO","RVNL","RAIN","RAJESHEXPO",
                    "RALLIS","RCF","RATNAMANI","RAYMOND","REDINGTON","RELAXO","RELCAPITAL","RELIANCE",
                    "RELINFRA","RPOWER","REPCOHOME","RESPONIND","SHK","SBILIFE","SJVN","SKFINDIA","SRF",
                    "SADBHAV","SANOFI","SCHAEFFLER","SIS","SFL","SHILPAMED","SHOPERSTOP","SHREECEM","RENUKA",
                    "SHRIRAMCIT","SRTRANSFIN","SIEMENS","SOBHA","SOLARINDS","SONATSOFTW","SOUTHBANK",
                    "SPANDANA","SPICEJET","STARCEMENT","SBIN","SAIL","STRTECH","STAR","SUDARSCHEM","SPARC",
                    "SUNPHARMA","SUNTV","SUNCLAYLTD","SUNDARMFIN","SUNDRMFAST","SUNTECK","SUPRAJIT",
                    "SUPREMEIND","SUZLON","SWANENERGY","SYMPHONY","SYNGENE","TCIEXP","TCNSBRANDS","TTKPRESTIG",
                    "TVTODAY","TV18BRDCST","TVSMOTOR","TAKE","TASTYBITE","TCS","TATAELXSI","TATAGLOBAL",
                    "TATAINVEST","TATAMTRDVR","TATAMOTORS","TATAPOWER","TATASTLBSL","TATASTEEL","TEAMLEASE",
                    "TECHM","TECHNOE","NIACL","RAMCOCEM","THERMAX","THYROCARE","TIMETECHNO","TIMKEN","TITAN",
                    "TORNTPHARM","TORNTPOWER","TRENT","TRIDENT","TRITURBINE","TIINDIA","UCOBANK","UFLEX","UPL",
                    "UJJIVAN","ULTRACEMCO","UNIONBANK","UBL","MCDOWELL-N","VGUARD","VMART","VIPIND","VRLLOG",
                    "VSTIND","WABAG","VAIBHAVGBL","VAKRANGEE","VTL","VARROC","VBL","VEDL","VENKEYS",
                    "VINATIORGA","IDEA","VOLTAS","WABCOINDIA","WELCORP","WELSPUNIND","WESTLIFE","WHIRLPOOL",
                    "WIPRO","WOCKPHARMA","YESBANK","ZEEL","ZENSARTECH","ZYDUSWELL","ECLERX","TATACONSUM",
                    "DEEPAKFERT","ADANIENT","CGPOWER","PENIND","BANKNIFTY","NIFTY"]

NSEFnOList = ["BANKNIFTY","NIFTY","ACC","ADANIENT","ADANIPORTS","AMARAJABAT","AMBUJACEM","APOLLOHOSP",
              "APOLLOTYRE","ASHOKLEY","ASIANPAINT","AUROPHARMA","AXISBANK","BAJAJ-AUTO","BAJAJFINSV",
              "BAJFINANCE","BALKRISIND","BANDHANBNK","BANKBARODA","BATAINDIA","BEL","BERGEPAINT","BHARATFORG",
              "BHARTIARTL","BHEL","BIOCON","BOSCHLTD","BPCL","BRITANNIA","CADILAHC","CANBK","CENTURYTEX",
              "CHOLAFIN","CIPLA","COALINDIA","COLPAL","CONCOR","CUMMINSIND","DABUR","DIVISLAB","DLF",
              "DRREDDY","EICHERMOT","EQUITAS","ESCORTS","EXIDEIND","FEDERALBNK","GAIL","GLENMARK","GMRINFRA",
              "GODREJCP","GODREJPROP","GRASIM","HAVELLS","HCLTECH","HDFC","HDFCBANK","HDFCLIFE","HEROMOTOCO",
               "HINDALCO","HINDPETRO","HINDUNILVR","IBULHSGFIN","ICICIBANK","ICICIPRULI","IDEA","IDFCFIRSTB",
               "IGL","INDIGO","INDUSINDBK","INFRATEL","INFY","IOC","ITC","JINDALSTEL","JSWSTEEL","JUBLFOOD",
               "JUSTDIAL","KOTAKBANK","L&TFH","LICHSGFIN","LT","LUPIN","M&M","M&MFIN","MANAPPURAM","MARICO",
              "MARUTI","MCDOWELL-N","MFSL","MGL","MINDTREE","MOTHERSUMI","MRF","MUTHOOTFIN","NATIONALUM",
              "NAUKRI","NCC","NESTLEIND","NIITTECH","NMDC","NTPC","ONGC","PAGEIND","PEL","PETRONET","PFC",
              "PIDILITIND","PNB","POWERGRID","PVR","RAMCOCEM","RBLBANK","RECLTD","RELIANCE","SAIL","SBILIFE",
              "SBIN","SHREECEM","SIEMENS","SRF","SRTRANSFIN","SUNPHARMA","SUNTV","TATACHEM","TATACONSUM",
              "TATAMOTORS","TATAPOWER","TATASTEEL","TCS","TECHM","TITAN","TORNTPHARM","TORNTPOWER","TVSMOTOR",
              "UBL","UJJIVAN","ULTRACEMCO","UPL","VEDL","VOLTAS","WIPRO","ZEEL"]

Scriplist = ["TCS","TATAPOWER","REDINGTON","SAIL"]
YahooScriplist = ["RELIANCE.NS", "HDFCBANK.NS", "TATASTEEL.NS", "TCS.NS", "TATAMOTORS.NS","TATAPOWER.NS","INDIGO.NS","IDEA.NS","OIL.NS","AUROPHARMA.NS","CIPLA.NS","FEDERALBNK.NS","AXISBANK.NS","ZEEL.NS"]
IndexList = ["NIFTY","NIFTYIT","BANKNIFTY","INDIAVIX"]
#################################Global Variables
#Creating strike List
strike = []
expiry = []
date = []
#Check for file

def FindFeather(name, path):
    for root, dirs, files in os.walk(path):
        if name in files:
            return os.path.join(root, name)

def call_otm(df, date):
	copy_df = df
	copy_df = copy_df[copy_df['Option type'] == 'CE']
	copy_df = copy_df[copy_df['Date'] == date]
	copy_df.sort_values('Strike Price', axis=0, ascending = False, inplace = True)
	copy_df['cumsum_c'] = pd.Series.cumsum(copy_df['Open Int'])
	return copy_df        
        
def put_otm(df, date):
	copy_df = df
	copy_df = copy_df[copy_df['Option type'] == 'PE']
	copy_df = copy_df[copy_df['Date'] == date]
	copy_df.sort_values('Strike Price', axis=0, ascending = True, inplace = True)
	copy_df['cumsum_p'] = pd.Series.cumsum(copy_df['Open Int'])
	return copy_df       
        
# (5) Find strike with maximum cumulative options OTM.
def max_pain_strike(call_sums, put_sums):
	cumulative = pd.merge(call_sums,put_sums, on = 'Strike Price', how = 'inner') #Merge or join?
	cumulative['cp_sum'] = cumulative['cumsum_c'] + cumulative['cumsum_p']
	mpp = cumulative['Strike Price'][cumulative['cp_sum'].idxmax()]
	return mpp    

def GetMaxPain(Scrip): #Depth is considered in months to see historical expiry and pain
    # for Scrip in NSEFnOList:
    # Scrip = 'RELIANCE'
    OptionsFileName = Scrip + '_' + MonthlyOptionsFilePath
    # FromWhen = 500 #How much back in time. 1 is default minimum
    # MLdf = Tempdf.tail(1)

    #Read from feather
    if (FindFeather(OptionsFileName, './Datastore')):
        ReadOptionsdf = feather.read_feather('./Datastore/'+OptionsFileName)
        OptionsSlice = ReadOptionsdf.copy()
        MaxPaindf = pd.DataFrame()
        # MLdf = ReadOptionsdf[(ReadOptionsdf['Date'] ==  SelectDate)]
        # ExpiryDate = MLdf['Expiry'].values[0] #The month in focus
        # OptionsSlice = ReadOptionsdf[(ReadOptionsdf['Expiry'] ==  ExpiryDate)]
        
        date = []
        #Adding values to list
        date = list(OptionsSlice['Date'])
        #Removing duplicates in list
        date = list(dict.fromkeys(date))
        #Sorting list
        date.sort()
        
        for Focusdate in date:
            call_sums = call_otm(OptionsSlice, Focusdate)
            put_sums = put_otm(OptionsSlice, Focusdate)
            PCR = put_sums['Open Int'].sum()/call_sums['Open Int'].sum()
            MP = max_pain_strike(call_sums, put_sums)
            MaxPaindf['Date'] = Focusdate
            MaxPaindf['MaxPain'] = MP
            MaxPaindf['Expiry'] = ExpiryDate
            MaxPaindf['PCR'] = PCR
            # print(Scrip,ExpiryDate,Focusdate,MP,PCR)
        return MaxPaindf
        
def MACD(DF,a,b,c):
    """function to calculate MACD
       typical values a = 12; b =26, c =9"""
    df = DF.copy()
    df["MA_Fast"]=df["Close"].ewm(span=a,min_periods=a).mean()
    df["MA_Slow"]=df["Close"].ewm(span=b,min_periods=b).mean()
    df["MACD"]=df["MA_Fast"]-df["MA_Slow"]
    df["Signal"]=df["MACD"].ewm(span=c,min_periods=c).mean()
    df.dropna(inplace=True)
    return df

def RSI(DF,n):
    "function to calculate RSI"
    df = DF.copy()
    df['delta']=df['Close'] - df['Close'].shift(1)
    df['gain']=np.where(df['delta']>=0,df['delta'],0)
    df['loss']=np.where(df['delta']<0,abs(df['delta']),0)
    avg_gain = []
    avg_loss = []
    gain = df['gain'].tolist()
    loss = df['loss'].tolist()
    for i in range(len(df)):
        if i < n:
            avg_gain.append(np.NaN)
            avg_loss.append(np.NaN)
        elif i == n:
            avg_gain.append(df['gain'].rolling(n).mean().tolist()[n])
            avg_loss.append(df['loss'].rolling(n).mean().tolist()[n])
        elif i > n:
            avg_gain.append(((n-1)*avg_gain[i-1] + gain[i])/n)
            avg_loss.append(((n-1)*avg_loss[i-1] + loss[i])/n)
    df['avg_gain']=np.array(avg_gain)
    df['avg_loss']=np.array(avg_loss)
    df['RS'] = df['avg_gain']/df['avg_loss']
    df['RSI'] = 100 - (100/(1+df['RS']))
    return df['RSI']

def ADX(DF,n):
    "function to calculate ADX"
    # df2 = Indicatordf.copy()
    # n = 20
    df2 = DF.copy()
    df2['TR'] = ATR(df2,n)['TR'] #the period parameter of ATR function does not matter because period does not influence TR calculation
    df2['DMplus']=np.where((df2['High']-df2['High'].shift(1))>(df2['Low'].shift(1)-df2['Low']),df2['High']-df2['High'].shift(1),0)
    df2['DMplus']=np.where(df2['DMplus']<0,0,df2['DMplus'])
    df2['DMminus']=np.where((df2['Low'].shift(1)-df2['Low'])>(df2['High']-df2['High'].shift(1)),df2['Low'].shift(1)-df2['Low'],0)
    df2['DMminus']=np.where(df2['DMminus']<0,0,df2['DMminus'])
    TRn = []
    DMplusN = []
    DMminusN = []
    TR = df2['TR'].tolist()
    DMplus = df2['DMplus'].tolist()
    DMminus = df2['DMminus'].tolist()
    for i in range(len(df2)):
        if i < n:
            TRn.append(np.NaN)
            DMplusN.append(np.NaN)
            DMminusN.append(np.NaN)
        elif i == n:
            TRn.append(df2['TR'].rolling(n).sum().tolist()[n])
            DMplusN.append(df2['DMplus'].rolling(n).sum().tolist()[n])
            DMminusN.append(df2['DMminus'].rolling(n).sum().tolist()[n])
        elif i > n:
            TRn.append(TRn[i-1] - (TRn[i-1]/n) + TR[i])
            DMplusN.append(DMplusN[i-1] - (DMplusN[i-1]/n) + DMplus[i])
            DMminusN.append(DMminusN[i-1] - (DMminusN[i-1]/n) + DMminus[i])
    df2['TRn'] = np.array(TRn)
    df2['DMplusN'] = np.array(DMplusN)
    df2['DMminusN'] = np.array(DMminusN)
    df2['DIplusN']=100*(df2['DMplusN']/df2['TRn'])
    df2['DIminusN']=100*(df2['DMminusN']/df2['TRn'])
    df2['DIdiff']=abs(df2['DIplusN']-df2['DIminusN'])
    df2['DIsum']=df2['DIplusN']+df2['DIminusN']
    df2['DX']=100*(df2['DIdiff']/df2['DIsum'])
    ADX = []
    DX = df2['DX'].tolist()
    for j in range(len(df2)):
        if j < 2*n-1:
            ADX.append(np.NaN)
        elif j == 2*n-1:
            ADX.append(df2['DX'][j-n+1:j+1].mean())
        elif j > 2*n-1:
            ADX.append(((n-1)*ADX[j-1] + DX[j])/n)
    df2['ADX']=np.array(ADX)
    return df2#['ADX']['DIplusN']['DIminusN']

def OBV(DF):
    """function to calculate On Balance Volume"""
    df = DF.copy()
    df['daily_ret'] = df['Close'].pct_change()
    df['direction'] = np.where(df['daily_ret']>=0,1,-1)
    df['direction'][0] = 0
    df['vol_adj'] = df['Volume'] * df['direction']
    df['obv'] = df['vol_adj'].cumsum()
    return df
            
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

def slope(ser,n):
    "function to calculate the slope of regression line for n consecutive points on a plot"
    ser = (ser - ser.min())/(ser.max() - ser.min())
    x = np.array(range(len(ser)))
    x = (x - x.min())/(x.max() - x.min())
    slopes = [i*0 for i in range(n-1)]
    for i in range(n,len(ser)+1):
        y_scaled = ser[i-n:i]
        x_scaled = x[i-n:i]
        x_scaled = sm.add_constant(x_scaled)
        model = sm.OLS(y_scaled,x_scaled)
        results = model.fit()
        #results.summary()
        slopes.append(results.params[-1])
    slope_angle = (np.rad2deg(np.arctan(np.array(slopes))))
    return np.array(slope_angle)

def Renko_DF(DF):
    "function to convert ohlc data into renko bricks"
    df = DF.copy()
    df = df.iloc[:,[0,5,6,4,8,10]]
    df.rename(columns = {"Date" : "date", "High" : "high","Low" : "low", "Open" : "open","Close" : "close", "Volume" : "volume"}, inplace = True)
    df2 = Renko(df)
    df2.brick_size = round(ATR(DF,120)["ATR"].iloc[-1],0)
    renko_df = df2.get_ohlc_data() #if using older version of the library please use get_bricks() instead
    return renko_df

def PlotRenko(DF,num_bars):
    # Turn interactive mode off
    plt.ioff()

    df = DF.copy()
    # get the last num_bars
    df = df.tail(num_bars)
    renkos = zip(df['open'],df['close'])
 
    # compute the price movement in the Renko
    price_move = abs(df.iloc[1]['open'] - df.iloc[1]['close'])
 
    # create the figure
    fig = plt.figure(1)
    fig.clf()
    axes = fig.gca()
 
    # plot the bars, blue for 'up', red for 'down'
    index = 1
    for open_price, close_price in renkos:
        if (open_price < close_price):
            renko = matplotlib.patches.Rectangle((index,open_price), 1, close_price-open_price, edgecolor='darkgreen', facecolor='green', alpha=0.5)
            axes.add_patch(renko)
        else:
            renko = matplotlib.patches.Rectangle((index,open_price), 1, close_price-open_price, edgecolor='darkred', facecolor='red', alpha=0.5)
            axes.add_patch(renko)
        index = index + 1
 
    # adjust the axes
    plt.xlim([0, num_bars])
    plt.ylim([min(min(df['open']),min(df['close'])), max(max(df['open']),max(df['close']))])
    fig.suptitle('Bars from ' + min(df['date']).strftime("%d-%b-%Y") + " to " + max(df['date']).strftime("%d-%b-%Y") \
        + '\nPrice movement = ' + str(price_move), fontsize=14)
    plt.xlabel('Bar Number')
    plt.ylabel('Price')
    #plt.figsize = (16,9)
    plt.grid(True)
    plt.show()

def BollBnd(DF,n):
    "function to calculate Bollinger Band"
    df = DF.copy()
    df["MA"] = df['Close'].rolling(n).mean()
    df["BB_up"] = df["MA"] + 2*df['Close'].rolling(n).std(ddof=0) #ddof=0 is required since we want to take the standard deviation of the population and not sample
    df["BB_dn"] = df["MA"] - 2*df['Close'].rolling(n).std(ddof=0) #ddof=0 is required since we want to take the standard deviation of the population and not sample
    df["BB_width"] = df["BB_up"] - df["BB_dn"]
    df.dropna(inplace=True)
    return df

def plot_chart(DF, n, ticker):
    # Filter number of observations to plot
    # n = 300
    # ticker = "REDINGTON"
    # data = Indicatordf.copy()
    data = DF.copy()
    # data = data.reset_index()
    Renkodata = Renko_DF(data)
    #DF amd number of latest bricks
    PlotRenko(Renkodata,100)
    
    data.drop(data.iloc[:, [1,2,3,7]], inplace = True, axis = 1) 
    data = data.iloc[-n:]
    
    data.index = data["Date"].apply(lambda x: pd.Timestamp(x))
    data.drop("Date", axis=1, inplace=True)
    
    # Create figure and set axes for subplots
    fig = plt.figure()
    # plt.title(ticker)
    # fig.set_size_inches((20, 16))
    # ax_candle = fig.add_axes((0, 0.72, 1, 0.32))
    # ax_macd = fig.add_axes((0, 0.48, 1, 0.2), sharex=ax_candle)
    # ax_rsi = fig.add_axes((0, 0.24, 1, 0.2), sharex=ax_candle)
    # ax_vol = fig.add_axes((0, 0, 1, 0.2), sharex=ax_candle)
    
    #plt.title(ticker)
    fig.set_size_inches((40, 20))
    ax_candle = fig.add_axes((0, 0.72, 0.49, 0.32))
    ax_macd = fig.add_axes((0, 0.48, 0.49, 0.2), sharex=ax_candle)
    ax_rsi = fig.add_axes((0, 0.24, 0.49, 0.2), sharex=ax_candle)
    ax_vol = fig.add_axes((0, 0, 0.49, 0.2), sharex=ax_candle)
    
    ax_bba = fig.add_axes((0.51, 0.72,0.49, 0.32), sharex=ax_candle)
    ax_obv = fig.add_axes((0.51, 0.48, 0.49, 0.2), sharex=ax_candle)
    ax_atr = fig.add_axes((0.51, 0.24, 0.49, 0.2), sharex=ax_candle)
    ax_beta = fig.add_axes((0.51, 0, 0.49, 0.2), sharex=ax_candle)
    
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
    ax_beta.plot(data.index, data["%Deliverble"], label="% Deliverable")
    ax_beta.legend()    

    # Save the chart as PNG
    #fig.savefig("charts/" + ticker + ".png", bbox_inches="tight")
    
    plt.show()
    
    fig2 = plt.figure()
    fig2.set_size_inches((32, 18))
    #[left, bottom, width, height] 
    # ax_sma = fig2.add_axes((0, 0.72, 0.49, 0.32))
    # ax_ema = fig2.add_axes((0.51, 0.72, 0.49, 0.32), sharex=ax_sma)
    # ax_trades = fig2.add_axes((0, 0.48, 0.49, 0.2), sharex=ax_candle)
    # ax_turnover = fig2.add_axes((0.51, 0.48, 0.49, 0.2), sharex=ax_candle)
    # ax_slope = fig2.add_axes((0, 0.24, 1, 0.2), sharex=ax_candle)
    
    ax_sma = fig2.add_axes((0, 0.72, 0.49, 0.32))
    ax_trades = fig2.add_axes((0, 0.48, 0.49, 0.2), sharex=ax_sma)
    ax_fibret = fig2.add_axes((0, 0.24, 0.49, 0.2), sharex=ax_sma)
    ax_slope = fig2.add_axes((0, 0, 1, 0.2), sharex=ax_sma)
    
    ax_ema = fig2.add_axes((0.51, 0.72, 0.49, 0.32), sharex=ax_sma)
    ax_turnover = fig2.add_axes((0.51, 0.48, 0.49, 0.2), sharex=ax_sma)
    ax_fibadv = fig2.add_axes((0.51, 0.24, 0.49, 0.2), sharex=ax_sma)
      
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
    
    ax_trades.plot(data.index, data["Trades"], label="Trades")
    ax_trades.legend()
    
    ax_turnover.plot(data.index, data["Turnover"]/ 100000, label="Turnover")
    ax_turnover.set_ylabel("(Lakh(s))")
    ax_turnover.legend()
    
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
    ax_fibret.axhspan(level1, price_min, alpha=0.4, color='lightcoral', label=str(level1) + ' (0.236)')
    ax_fibret.axhspan(level2, level1, alpha=0.5, color='lightsalmon', label=str(level2)+ ' (0.382)')
    ax_fibret.axhspan(level3, level2, alpha=0.5, color='mistyrose', label=str(level3)+ ' (0.5)')
    ax_fibret.axhspan(level4, level3, alpha=0.5, color='lightcyan', label=str(level4)+ ' (0.618)')
    ax_fibret.axhspan(level5, level4, alpha=0.5, color='powderblue', label=str(level5)+ ' (0.786)')
    ax_fibret.axhspan(price_max, level5, alpha=0.5, color='deepskyblue', label = str(price_max)+ ' (1)')
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
    
    ax_fibadv.axhspan(level6, price_max, alpha=0.4, color='limegreen', label=str(level6)+ ' (1.272)')
    ax_fibadv.axhspan(level7, level6, alpha=0.5, color='lime', label=str(level7)+ ' (1.382)')
    ax_fibadv.axhspan(level8, level7, alpha=0.5, color='deepskyblue', label=str(level8)+ ' (1.5)')
    ax_fibadv.axhspan(level9, level8, alpha=0.5, color='powderblue', label=str(level9)+ ' (1.618)')
    ax_fibadv.legend()
    # ax_fibadv.plot(data.index, level6 * len(data.index), label=str(level6))
    # ax_fibadv.plot(data.index, level7 * len(data.index), label=str(level7))
    # ax_fibadv.plot(data.index, level8 * len(data.index), label=str(level8))
    # ax_fibadv.plot(data.index, level9 * len(data.index), label=str(level9))
    candlestick_ohlc(ax_fibadv, ohlc, colorup="g", colordown="r", width=0.8)    
    
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
    fig3 = trendln.plot_sup_res_date((Trendlinedf[-n:].Low, Trendlinedf[-n:].High), idx) #requires pandas
    fig3.set_size_inches((16, 9))
    # plt.savefig('suppres.svg', format='svg')
    plt.show()
    # plt.clf() #clear figure

#def plot_chart(DF, n, ticker):

def GenerateMLdf(DF,Scrip):
    Tempdf = DF.copy()
    # Tempdf.reset_index(level=0, inplace=True)
    OHLCdepth = 1 #Surface
    FromWhen = 1 #How much back in time. 1 is default minimum
    # MLdf = Tempdf.tail(1)
    MLdf = Tempdf.iloc[[-FromWhen]]
    # MLdf.reset_index(level=0, inplace=True)
    Focusdate = MLdf['Date'].values[0] #The date in focus
    CurrentMonth = Focusdate.month
    # Tempdf.iloc[[-2]]
    while OHLCdepth < 11:
        MLdf["Open-"+str(OHLCdepth)] = Tempdf.iloc[[-OHLCdepth-FromWhen]]["Open"].values[0]
        MLdf["High-"+str(OHLCdepth)] = Tempdf.iloc[[-OHLCdepth-FromWhen]]["High"].values[0]
        MLdf["Low-"+str(OHLCdepth)] = Tempdf.iloc[[-OHLCdepth-FromWhen]]["Low"].values[0]
        MLdf["Close-"+str(OHLCdepth)] = Tempdf.iloc[[-OHLCdepth-FromWhen]]["Close"].values[0]
        MLdf["Volume-"+str(OHLCdepth)] = Tempdf.iloc[[-OHLCdepth-FromWhen]]["Volume"].values[0]
        MLdf["Turnover-"+str(OHLCdepth)] = Tempdf.iloc[[-OHLCdepth-FromWhen]]["Turnover"].values[0]
        if Scrip != "BANKNIFTY" and Scrip != "NIFTY":
            MLdf["Trades-"+str(OHLCdepth)] = Tempdf.iloc[[-OHLCdepth-FromWhen]]["Trades"].values[0]
            MLdf["%Deliverble-"+str(OHLCdepth)] = Tempdf.iloc[[-OHLCdepth-FromWhen]]["%Deliverble"].values[0]
        OHLCdepth += 1
    
    MLdf['Symbol'] = Scrip
        
    FuturesFileName = Scrip + '_' + MonthlyFuturesFilePath
    #Read from feather
    if (FindFeather(FuturesFileName, './Datastore/')):
        ReadFuturesdf = feather.read_feather('./Datastore/'+FuturesFileName)
        Futuresdf = ReadFuturesdf.copy()
        if not Futuresdf.empty:
            if not Futuresdf.tail(1)['Date'].values[0] < Focusdate: #Not past expiry
                FuturesdfIndex = Futuresdf[Futuresdf['Date']==Focusdate].index.values.astype(int)[0] #Date of Futures trade
                OHLCdepth = 0
                while OHLCdepth < 11:
                    IterationMonth = ((Futuresdf.iloc[[FuturesdfIndex-OHLCdepth]]["Date"]).values[0]).month
                    if(CurrentMonth is not IterationMonth):
                        break
                    
                    MLdf["FuturesOpen-"+str(OHLCdepth)] = Futuresdf.iloc[[FuturesdfIndex-OHLCdepth]]["Open"].values[0]
                    MLdf["FuturesHigh-"+str(OHLCdepth)] = Futuresdf.iloc[[FuturesdfIndex-OHLCdepth]]["High"].values[0]
                    MLdf["FuturesLow-"+str(OHLCdepth)] = Futuresdf.iloc[[FuturesdfIndex-OHLCdepth]]["Low"].values[0]
                    MLdf["FuturesClose-"+str(OHLCdepth)] = Futuresdf.iloc[[FuturesdfIndex-OHLCdepth]]["Close"].values[0]
                    MLdf["FuturesSettlePrice-"+str(OHLCdepth)] = Futuresdf.iloc[[FuturesdfIndex-OHLCdepth]]["Settle Price"].values[0]
                    MLdf["FuturesNoContracts-"+str(OHLCdepth)] = Futuresdf.iloc[[FuturesdfIndex-OHLCdepth]]["Number of Contracts"].values[0]
                    MLdf["FuturesTurnover-"+str(OHLCdepth)] = Futuresdf.iloc[[FuturesdfIndex-OHLCdepth]]["Turnover"].values[0]
                    MLdf["FuturesOpenInterest-"+str(OHLCdepth)] = Futuresdf.iloc[[FuturesdfIndex-OHLCdepth]]["Open Interest"].values[0]
                    MLdf["FuturesChangeinOI-"+str(OHLCdepth)] = Futuresdf.iloc[[FuturesdfIndex-OHLCdepth]]["Change in OI"].values[0]
                    OHLCdepth += 1
            
    OptionsFileName = Scrip + '_' + MonthlyOptionsFilePath
    #Read from feather
    if (FindFeather(OptionsFileName, './Datastore/')):
        ReadOptionsdf = feather.read_feather('./Datastore/'+OptionsFileName)
        Optionsdf = ReadOptionsdf.copy()
        if not Optionsdf.empty:
            # Optionsdf['Date'] = Optionsdf['Date'].dt.date
            OHLCdepth = 0
            Optionsdate = Focusdate
            if not Optionsdf.tail(1)['Date'].values[0] < Optionsdate:#Past Monthly expiry
                while OHLCdepth < 11:
                    IterationMonth = Optionsdate.month
                    if(CurrentMonth is not IterationMonth): #Past Monthly expiry
                        break
                    
                    # selecting rows based on condition
                    OptionsPESlice = Optionsdf[(Optionsdf['Option type'] == 'PE') & (Optionsdf['Date'] ==  Optionsdate)] 
                    OptionsPESlice = OptionsPESlice.sort_values(by='Open Int', ascending=False)
                    OptionsCESlice = Optionsdf[(Optionsdf['Option type'] == 'CE') & (Optionsdf['Date'] ==  Optionsdate)]
                    OptionsCESlice = OptionsCESlice.sort_values(by='Open Int', ascending=False)
                    
                    if OptionsPESlice.empty or OptionsCESlice.empty: #Corner case at end of the month
                        break
                    
                    MLdf["PCR-"+str(OHLCdepth)] = OptionsPESlice['Open Int'].sum()/OptionsCESlice['Open Int'].sum()
                    MLdf["PEOI1st-"+str(OHLCdepth)] = OptionsPESlice.iloc[0]['Open Int']
                    MLdf["PEClose1st-"+str(OHLCdepth)] = OptionsPESlice.iloc[0]['Close']
                    MLdf["PEStrike1st-"+str(OHLCdepth)] = OptionsPESlice.iloc[0]['Strike Price']
                    MLdf["PEChangeOI1st-"+str(OHLCdepth)] = OptionsPESlice.iloc[0]['Change in OI']
                    MLdf["PEOI2nd-"+str(OHLCdepth)] = OptionsPESlice.iloc[1]['Open Int']
                    MLdf["PEClose2nd-"+str(OHLCdepth)] = OptionsPESlice.iloc[0]['Close']
                    MLdf["PEStrike2nd-"+str(OHLCdepth)] = OptionsPESlice.iloc[0]['Strike Price']
                    MLdf["PEChangeOI2nd-"+str(OHLCdepth)] = OptionsPESlice.iloc[0]['Change in OI']                    
                    MLdf["PEOI3rd-"+str(OHLCdepth)] = OptionsPESlice.iloc[2]['Open Int']
                    MLdf["PEClose3rd-"+str(OHLCdepth)] = OptionsPESlice.iloc[0]['Close']
                    MLdf["PEStrike3rd-"+str(OHLCdepth)] = OptionsPESlice.iloc[0]['Strike Price']
                    MLdf["PEChangeOI3rd-"+str(OHLCdepth)] = OptionsPESlice.iloc[0]['Change in OI']                    
                    MLdf["PEOI4th-"+str(OHLCdepth)] = OptionsPESlice.iloc[3]['Open Int']
                    MLdf["PEClose4th-"+str(OHLCdepth)] = OptionsPESlice.iloc[0]['Close']
                    MLdf["PEStrike4th-"+str(OHLCdepth)] = OptionsPESlice.iloc[0]['Strike Price']
                    MLdf["PEChangeOI4th-"+str(OHLCdepth)] = OptionsPESlice.iloc[0]['Change in OI']                    
                    MLdf["PEOI5th-"+str(OHLCdepth)] = OptionsPESlice.iloc[4]['Open Int']
                    MLdf["PEClose5th-"+str(OHLCdepth)] = OptionsPESlice.iloc[0]['Close']
                    MLdf["PEStrike5th-"+str(OHLCdepth)] = OptionsPESlice.iloc[0]['Strike Price']
                    MLdf["PEChangeOI5th-"+str(OHLCdepth)] = OptionsPESlice.iloc[0]['Change in OI']                    
                    
                    MLdf["CEOI1st-"+str(OHLCdepth)] = OptionsCESlice.iloc[0]['Open Int']
                    MLdf["CEClose1st-"+str(OHLCdepth)] = OptionsCESlice.iloc[0]['Close']
                    MLdf["CEStrike1st-"+str(OHLCdepth)] = OptionsCESlice.iloc[0]['Strike Price']
                    MLdf["CEChangeOI1st-"+str(OHLCdepth)] = OptionsCESlice.iloc[0]['Change in OI']                    
                    MLdf["CEOI2nd-"+str(OHLCdepth)] = OptionsCESlice.iloc[1]['Open Int']
                    MLdf["CEClose2nd-"+str(OHLCdepth)] = OptionsCESlice.iloc[0]['Close']
                    MLdf["CEStrike2nd-"+str(OHLCdepth)] = OptionsCESlice.iloc[0]['Strike Price']
                    MLdf["CEChangeOI2nd-"+str(OHLCdepth)] = OptionsCESlice.iloc[0]['Change in OI']                   
                    MLdf["CEOI3rd-"+str(OHLCdepth)] = OptionsCESlice.iloc[2]['Open Int']
                    MLdf["CEClose3rd-"+str(OHLCdepth)] = OptionsCESlice.iloc[0]['Close']
                    MLdf["CEStrike3rd-"+str(OHLCdepth)] = OptionsCESlice.iloc[0]['Strike Price']
                    MLdf["CEChangeOI3rd-"+str(OHLCdepth)] = OptionsCESlice.iloc[0]['Change in OI']                   
                    MLdf["CEOI4th-"+str(OHLCdepth)] = OptionsCESlice.iloc[3]['Open Int']
                    MLdf["CEClose4th-"+str(OHLCdepth)] = OptionsCESlice.iloc[0]['Close']
                    MLdf["CEStrike4th-"+str(OHLCdepth)] = OptionsCESlice.iloc[0]['Strike Price']
                    MLdf["CEChangeOI4th-"+str(OHLCdepth)] = OptionsCESlice.iloc[0]['Change in OI']                
                    MLdf["CEOI5th-"+str(OHLCdepth)] = OptionsCESlice.iloc[4]['Open Int']
                    MLdf["CEClose5th-"+str(OHLCdepth)] = OptionsCESlice.iloc[0]['Close']
                    MLdf["CEStrike5th-"+str(OHLCdepth)] = OptionsCESlice.iloc[0]['Strike Price']
                    MLdf["CEChangeOI5th-"+str(OHLCdepth)] = OptionsCESlice.iloc[0]['Change in OI']  
                    
                    OHLCdepth += 1
                    Optionsdate = Tempdf.iloc[[-OHLCdepth-FromWhen]]["Date"].values[0]
                    
    return MLdf

def TechAnalysis():
    Finaldf = pd.DataFrame()
    # for Scrip in NSE500ScripList:#Scriplist:
    for Scrip in NSE500ScripList:        
        OHLCdf = None
        Indicatordf = None
        Scrip = "HDFCBANK"
        print('Now for '+ Scrip)
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
            Indicatordf["Beta"] = talib.BETA(Indicatordf["High"],
                                                 Indicatordf["Low"],
                                                 timeperiod=14)
            
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
            
            Mpdf = GetMaxPain(Scrip)
            OHLCOptdf = pd.merge(Indicatordf,Mpdf, on = 'Date', how = 'inner')
            
###################################################################################################
            feather.write_feather(Indicatordf, 'E:/Harish/nsepywork/TechnicalFrames/'+Scrip+'-dataframe.ftr')
# ###################################################################################################            
            # plot_chart(Indicatordf,200,Scrip)
###################################################################################################
            ReturnMLdf = GenerateMLdf(Indicatordf,Scrip)
            # ReturnMLdf.to_csv(r'./OutputFrames/pandas.txt', header=None, index=None, sep=' ', mode='a')
            Finaldf = Finaldf.append(ReturnMLdf, ignore_index=True)
            
    Focusdate = ReturnMLdf['Date'].values[0]
    if not Finaldf.empty:
        feather.write_feather(Finaldf, './OutputFrames/'+str(Focusdate)+'-G1dataframe.ftr')
###################################################################################################

def main():
   TechAnalysis()
   
   
# G1MLdf = feather.read_feather('./Datastore/PEHistory.ftr')

