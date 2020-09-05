# -*- coding: utf-8 -*-
"""
Created on Wed Aug  5 18:32:54 2020

@author: HRTR
"""
# =============================================================================
# Different KPI metrics
# =============================================================================

# Import necesary libraries
import numpy as np
import datetime as dt
import pandas as pd
import pyarrow
import pyarrow.feather as feather
import matplotlib
import time
import os
from stocktrends import Renko
import statsmodels.api as sm
import copy


Scriplist = ["RELIANCE", "HDFCBANK", "TATASTEEL", "TCS", "TATAMOTORS","TATAPOWER",
             "INDIGO","IDEA","OIL","AUROPHARMA","CIPLA","NIFTY","FEDERALBNK","AXISBANK",
             "ZEEL","INDIAVIX","HDFCLIFE","BHARTIARTL","BHEL","SAIL","JINDALSTEL","PNB",
             "HINDALCO","ADANIENT","BANKINDIA","MANAPPURAM","DEEPAKFERT","ITC","MOTHERSUMI","ICICIBANK",
             "BAJFINANCE"]

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
                   "WIPRO","WOCKPHARMA","YESBANK","ZEEL","ZENSARTECH","ZYDUSWELL","ECLERX","TATACONSUM"]

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

# def renko_DF(DF):
#     "function to convert ohlc data into renko bricks"
#     df = DF.copy()
#     df = df.iloc[:,[0,5,6,4,8,10]]
#     df.rename(columns = {"Date" : "date", "High" : "high","Low" : "low", "Open" : "open","Close" : "close", "Volume" : "volume"}, inplace = True)
#     df2 = Renko(df)
#     df2.brick_size = round(ATR(DF,120)["ATR"].iloc[-1],0)
#     renko_df = df2.get_bricks()
#     renko_df["bar_num"] = np.where(renko_df["uptrend"]==True,1,np.where(renko_df["uptrend"]==False,-1,0))
#     for i in range(1,len(renko_df["bar_num"])):
#         if renko_df["bar_num"][i]>0 and renko_df["bar_num"][i-1]>0:
#             renko_df["bar_num"][i]+=renko_df["bar_num"][i-1]
#         elif renko_df["bar_num"][i]<0 and renko_df["bar_num"][i-1]<0:
#             renko_df["bar_num"][i]+=renko_df["bar_num"][i-1]
#     renko_df.drop_duplicates(subset="date",keep="last",inplace=True)
#     return renko_df

def Renko_DF(DF):
    "function to convert ohlc data into renko bricks"
    df = DF.copy()
    df = df.iloc[:,[0,5,6,4,8,10]]
    df.rename(columns = {"Date" : "date", "High" : "high","Low" : "low", "Open" : "open","Close" : "close", "Volume" : "volume"}, inplace = True)
    df2 = Renko(df)
    df2.brick_size = round(["ATR"].iloc[-1],0)
    renko_df = df2.get_ohlc_data() #if using older version of the library please use get_bricks() instead
    return renko_df

# DailyOHLCFilePath = "ohlc.ftr";
AnalyzedFrame = "dataframe.ftr"
IntradayFilePath = "intraday.ftr"
MonthlyFuturesFilePath = "monthly-futures.ftr"
OptionsFilePath = "options.ftr"

def FindFeather(name, path):
    for root, dirs, files in os.walk(path):
        if name in files:
            return os.path.join(root, name)


def CAGR(DF):
    "function to calculate the Cumulative Annual Growth Rate of a trading strategy"
    df = DF.copy()
    df["daily_ret"] = df["Close"].pct_change()
    df["cum_return"] = (1 + df["daily_ret"]).cumprod()
    n = len(df)/252
    CAGR = (df["cum_return"].iloc[-1])**(1/n) - 1
    return CAGR

def Sharpe(DF,rf):
    "function to calculate sharpe ratio ; rf is the risk free rate"
    df = DF.copy()
    sr = (CAGR(df) - rf)/Volatility(df)
    return sr
 
def Sortino(DF,rf):
    "function to calculate sortino ratio ; rf is the risk free rate"
    df = DF.copy()
    df["daily_ret"] = DF["Close"].pct_change()
    df["neg_ret"] = np.where(df["daily_ret"]<0,df["daily_ret"],0)
    neg_vol = df["neg_ret"].std() * np.sqrt(252)
    sr = (CAGR(df) - rf)/neg_vol
    return sr

def Volatility(DF):
    "function to calculate annualized volatility of a trading strategy"
    df = DF.copy()
    df["daily_ret"] = DF["Close"].pct_change()
    vol = df["daily_ret"].std() * np.sqrt(252)
    return vol

def Max_dd(DF):
    "function to calculate max drawdown"
    df = DF.copy()
    df["daily_ret"] = DF["Close"].pct_change()
    df["cum_return"] = (1 + df["daily_ret"]).cumprod()
    df["cum_roll_max"] = df["cum_return"].cummax()
    df["drawdown"] = df["cum_roll_max"] - df["cum_return"]
    df["drawdown_pct"] = df["drawdown"]/df["cum_roll_max"]
    max_dd = df["drawdown_pct"].max()
    return max_dd
    
def Calmar(DF):
    "function to calculate calmar ratio"
    df = DF.copy()
    clmr = CAGR(df)/Max_dd(df)
    return clmr

def main():
    for Scrip in NSE500ScripList:
        # Scrip = "AXISBANK"
        OHLCdf = None
        OHLCFileName = Scrip + '-' + AnalyzedFrame
        #Read from feather
        if (FindFeather(OHLCFileName, './Datastore/Tech Analyzed/')):
            OHLCdf = feather.read_feather('./Datastore/Tech Analyzed/'+OHLCFileName)

            KPIdf = OHLCdf.tail(70) #Pass as argument later on

            ScripCAGR = CAGR(KPIdf)
            print("CAGR = "+ str(ScripCAGR))

            ScripVolatility = Volatility(KPIdf)
            print("Volatility = "+ str(ScripVolatility))
            
            ScripSharpe = Sharpe(KPIdf, 5)
            print("Sharpe ratio = "+ str(ScripSharpe))

            ScripSortino = Sortino(KPIdf, 5)
            print("Sortino ratio = "+ str(ScripSortino))

            ScripMaxDD = Max_dd(KPIdf)
            print("Max drawdown = "+ str(ScripMaxDD))

            ScripCalmar = Calmar(KPIdf)
            print("Calmar ratio = "+ str(ScripCalmar))
        else:
            print(Scrip +" feather not found")