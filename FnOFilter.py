# -*- coding: utf-8 -*-
"""
Created on Sun Feb  6 14:50:42 2022

@author: User
"""

DailyOHLCFilePath = "ohlc.ftr";
IntradayFilePath = "intraday.ftr"
MonthlyFuturesFilePath = "monthly-futures.ftr"
FullFuturesFilePath = "full-futures.ftr"
MonthlyOptionsFilePath = "monthly-options.ftr"
FXHistory = "FXHistory.ftr"
PEHistory = "PEHistory.ftr"

FnONewList = ['NIFTY','BANKNIFTY','FINNIFTY','MIDCPNIFTY','AARTIIND','ABB','ABBOTINDIA',
            'ABCAPITAL','ABFRL','ACC','ADANIENT','ADANIPORTS','ALKEM','AMARAJABAT',
            'AMBUJACEM','APLLTD','APOLLOHOSP','APOLLOTYRE','ASHOKLEY','ASIANPAINT',
            'ASTRAL','ATUL','AUBANK','AUROPHARMA','AXISBANK','BAJAJ-AUTO','BAJAJFINSV',
            'BAJFINANCE','BALKRISIND','BALRAMCHIN','BANDHANBNK','BANKBARODA','BATAINDIA',
            'BEL','BERGEPAINT','BHARATFORG','BHARTIARTL','BHEL','BIOCON','BOSCHLTD',
            'BPCL','BRITANNIA','BSOFT','CADILAHC','CANBK','CANFINHOME','CHAMBLFERT',
            'CHOLAFIN','CIPLA','COALINDIA','COFORGE','COLPAL','CONCOR','COROMANDEL',
            'CROMPTON','CUB','CUMMINSIND','DABUR','DALBHARAT','DEEPAKNTR','DELTACORP',
            'DIVISLAB','DIXON','DLF','DRREDDY','EICHERMOT','ESCORTS','EXIDEIND',
            'FEDERALBNK','FSL','GAIL','GLENMARK','GMRINFRA','GNFC','GODREJCP','GODREJPROP',
            'GRANULES','GRASIM','GSPL','GUJGASLTD','HAL','HAVELLS','HCLTECH','HDFC',
            'HDFCAMC','HDFCBANK','HDFCLIFE','HEROMOTOCO','HINDALCO','HINDCOPPER',
            'HINDPETRO','HINDUNILVR','HONAUT','IBULHSGFIN','ICICIBANK','ICICIGI',
            'ICICIPRULI','IDEA','IDFC','IDFCFIRSTB','IEX','IGL','INDHOTEL','INDIACEM',
            'INDIAMART','INDIGO','INDUSINDBK','INDUSTOWER','INFY','INTELLECT','IOC',
            'IPCALAB','IRCTC','ITC','JINDALSTEL','JKCEMENT','JSWSTEEL','JUBLFOOD',
            'KOTAKBANK','L&TFH','LALPATHLAB','LAURUSLABS','LICHSGFIN','LT','LTI',
            'LTTS','LUPIN','M&M','M&MFIN','MANAPPURAM','MARICO','MARUTI','MCDOWELL-N',
            'MCX','METROPOLIS','MFSL','MGL','MINDTREE','MOTHERSUMI','MPHASIS','MRF',
            'MUTHOOTFIN','NAM-INDIA','NATIONALUM','NAUKRI','NAVINFLUOR','NBCC',
            'NESTLEIND','NMDC','NTPC','OBEROIRLTY','OFSS','ONGC','PAGEIND','PEL',
            'PERSISTENT','PETRONET','PFC','PFIZER','PIDILITIND','PIIND','PNB','POLYCAB',
            'POWERGRID','PVR','RAIN','RAMCOCEM','RBLBANK','RECLTD','RELIANCE','SAIL',
            'SBICARD','SBILIFE','SBIN','SHREECEM','SIEMENS','SRF','SRTRANSFIN','STAR',
            'SUNPHARMA','SUNTV','SYNGENE','TATACHEM','TATACOMM','TATACONSUM',
            'TATAMOTORS','TATAPOWER','TATASTEEL','TCS','TECHM','TITAN','TORNTPHARM',
            'TORNTPOWER','TRENT','TVSMOTOR','UBL','ULTRACEMCO','UPL','VEDL','VOLTAS',
            'WHIRLPOOL','WIPRO','ZEEL']

def PlotFnoFilter(DF, n, ticker, Dividend):

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
    tech2.set_size_inches((40, 20))
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
    ax_ema.plot(data.index, data["100DMA-E"], label="100DMA-E")       
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

    candlestick_ohlc(ax_fibret, ohlc, colorup="g", colordown="r", width=0.8)


    #Extensons
    level6 = price_max - 1.272 * diff    
    level7 = price_max - 1.382 * diff 
    level8 = price_max - 1.5 * diff 
    level9 = price_max - 1.618 * diff 
    level10 = price_max - 2.618 * diff
    level11 = price_max - 4.236 * diff
    
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
    
    plt.show()
    
    return tech1, tech2, tech3


def FnOFilter():
    Finaldf = pd.DataFrame()

    for Scrip in FnONewList:
        try:
            OHLCdf = None
            Indicatordf = None
            # Scrip = "RELIANCE"
            OHLCFileName = Scrip + '_' + DailyOHLCFilePath #'2020-08-31-G1dataframe.ftr'#
            #Read from feather
            if (FindFeather(OHLCFileName, './Datastore/')):
                OHLCdf = feather.read_feather('./Datastore/'+OHLCFileName)
                Indicatordf = OHLCdf.copy()
                
                Indicatordf = Indicatordf.set_index("Date")

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
                Indicatordf["100DMA-E"] = Indicatordf["Close"].ewm(span=100, adjust=False).mean()
                #Indicatordf.iloc[-150:,[8,-1,-2,-3,-4,-5]].plot(figsize=(16,9),grid = True,title = Scrip) 
                Indicatordf.reset_index(level=0, inplace=True)
                
                if Indicatordf["Close"]. iloc[-1] > Indicatordf["100DMA-E"]. iloc[-1]:
                    continue
                else:
                    print(Scrip + ' Close is less than 100EMA')
                
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

    # ###################################################################################################            
                # FnoImg1. FnoImg2, FnoImg3 = PlotFnoFilter(Indicatordf,20,Scrip,0)
                
                # filename = sym + '_FnOFilter_' + pd.datetime.now().strftime("%Y-%m-%d--%H-%M-%S %p") + '.pdf'
                # fn = os.path.abspath(os.path.join(u'..', u'nsepywork/term-sheets', filename))
                # ppt = PdfPages(fn)
                
                # ppt.savefig(FnoImg1)
                # ppt.savefig(FnoImg2)
                # ppt.savefig(FnoImg3)
  
                # figt = plt.figure(figsize=(8, 6))
            
                # plt.axis('off')
                # figt.tight_layout()
                # ppt.savefig(figt)
                # ppt.close()
    
        except:
            print('Couldnt Analyze FnO Filter for:'+ Scrip)
            

###################################################################################################

#def plot_chart(DF, n, ticker):
def main():
    FnOFilter()