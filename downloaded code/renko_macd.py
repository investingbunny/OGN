# =============================================================================
# Backtesting strategy - IV : combining renko with other MACD
# Author : Mayank Rasu

# Please report bug/issues in the Q&A section
# =============================================================================

import numpy as np
import pandas as pd
from stocktrends import Renko
import statsmodels.api as sm
import copy

tickers = ["3MINDIA","ACC","AIAENG","APLAPOLLO","AUBANK","AARTIIND","AAVAS","ABBOTINDIA",
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

def renko_DF(DF):
    "function to convert ohlc data into renko bricks"
    df = DF.copy()
    df.reset_index(inplace=True)
    df = df.iloc[:,[0,1,2,3,4,5]]
    df.columns = ["date","open","high","low","close","volume"]
    df2 = Renko(df)
    df2.brick_size = max(0.5,round(ATR(DF,120)["ATR"][-1],0))
    renko_df = df2.get_bricks()
    renko_df["bar_num"] = np.where(renko_df["uptrend"]==True,1,np.where(renko_df["uptrend"]==False,-1,0))
    for i in range(1,len(renko_df["bar_num"])):
        if renko_df["bar_num"][i]>0 and renko_df["bar_num"][i-1]>0:
            renko_df["bar_num"][i]+=renko_df["bar_num"][i-1]
        elif renko_df["bar_num"][i]<0 and renko_df["bar_num"][i-1]<0:
            renko_df["bar_num"][i]+=renko_df["bar_num"][i-1]
    renko_df.drop_duplicates(subset="date",keep="last",inplace=True)
    return renko_df

ohlc_intraday = {} # directory with ohlc value for each stock            

def ReadDataFrames():
    ScripFileName = Scrip + '-dataframe.ftr'
    for i in range(len(tickers)):
        try:
            ohlc_intraday[tickers[i]] = feather.read_feather('./TechnicalFrames/'+ScripFileName)
        except:
            print(tickers[i]," :failed to fetch data...retrying")
            continue
    tickers = ohlc_intraday.keys() # redefine tickers variable after removing any tickers with corrupted data

################################Backtesting####################################

#Merging renko df with original ohlc df

def RenkoMerge():
    ohlc_renko = {}
    df = copy.deepcopy(ohlc_intraday)
    tickers_signal = {}
    tickers_ret = {}
    for ticker in tickers:
        print("merging for ",ticker)
        renko = renko_DF(df[ticker])
        renko.columns = ["Date","open","high","low","close","uptrend","bar_num"]
        # df[ticker]["Date"] = df[ticker].index
        ohlc_renko[ticker] = df[ticker].merge(renko.loc[:,["Date","bar_num"]],how="outer",on="Date")
        ohlc_renko[ticker]["bar_num"].fillna(method='ffill',inplace=True)
        ohlc_renko[ticker]["macd_slope"] = slope(ohlc_renko[ticker]["MACD"],5)
        ohlc_renko[ticker]["macd_sig_slope"] = slope(ohlc_renko[ticker]["Signal"],5)
        tickers_signal[ticker] = ""
        # tickers_ret[ticker] = []
       
#Identifying signals and calculating daily return

def CalculateSignals():
    for ticker in tickers:
        print("calculating daily returns for ",ticker)
        for i in range(len(ohlc_intraday[ticker])):
            if tickers_signal[ticker] == "":
                tickers_ret[ticker].append(0)
                if i > 0:
                    if ohlc_renko[ticker]["bar_num"][i]>=2 and ohlc_renko[ticker]["macd"][i]>ohlc_renko[ticker]["macd_sig"][i] and ohlc_renko[ticker]["macd_slope"][i]>ohlc_renko[ticker]["macd_sig_slope"][i]:
                        tickers_signal[ticker] = "Buy"
                    elif ohlc_renko[ticker]["bar_num"][i]<=-2 and ohlc_renko[ticker]["macd"][i]<ohlc_renko[ticker]["macd_sig"][i] and ohlc_renko[ticker]["macd_slope"][i]<ohlc_renko[ticker]["macd_sig_slope"][i]:
                        tickers_signal[ticker] = "Sell"
            
            elif tickers_signal[ticker] == "Buy":
                tickers_ret[ticker].append((ohlc_renko[ticker]["Adj Close"][i]/ohlc_renko[ticker]["Adj Close"][i-1])-1)
                if i > 0:
                    if ohlc_renko[ticker]["bar_num"][i]<=-2 and ohlc_renko[ticker]["macd"][i]<ohlc_renko[ticker]["macd_sig"][i] and ohlc_renko[ticker]["macd_slope"][i]<ohlc_renko[ticker]["macd_sig_slope"][i]:
                        tickers_signal[ticker] = "Sell"
                    elif ohlc_renko[ticker]["macd"][i]<ohlc_renko[ticker]["macd_sig"][i] and ohlc_renko[ticker]["macd_slope"][i]<ohlc_renko[ticker]["macd_sig_slope"][i]:
                        tickers_signal[ticker] = ""
                    
            elif tickers_signal[ticker] == "Sell":
                tickers_ret[ticker].append((ohlc_renko[ticker]["Adj Close"][i-1]/ohlc_renko[ticker]["Adj Close"][i])-1)
                if i > 0:
                    if ohlc_renko[ticker]["bar_num"][i]>=2 and ohlc_renko[ticker]["macd"][i]>ohlc_renko[ticker]["macd_sig"][i] and ohlc_renko[ticker]["macd_slope"][i]>ohlc_renko[ticker]["macd_sig_slope"][i]:
                        tickers_signal[ticker] = "Buy"
                    elif ohlc_renko[ticker]["macd"][i]>ohlc_renko[ticker]["macd_sig"][i] and ohlc_renko[ticker]["macd_slope"][i]>ohlc_renko[ticker]["macd_sig_slope"][i]:
                        tickers_signal[ticker] = ""
        ohlc_renko[ticker]["ret"] = np.array(tickers_ret[ticker])

