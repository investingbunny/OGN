# -*- coding: utf-8 -*-
"""
Created on Tue Aug 18 11:54:38 2020

@author: User
"""

            
        # #FnO Settlement Report download    
        # FnOSettleArg = 'FOSett_prce_' + weekday.strftime("%d%m%Y") + '.csv'
        # FnOSettlementURL = FnOSettlement + FnOSettleArg
        # try:
        #     r = requests.get(FnOSettlementURL, allow_redirects=True) #Download FnO Volatility report for 'weekday'
        #     if r.ok:
        #         data = r.content.decode('utf8')
        #         Setdf = pd.read_csv(io.StringIO(data))
        #         Setdf = Setdf.rename(columns=lambda x: x.strip())
        #         Setdf = Setdf.applymap(lambda x: x.strip() if isinstance(x, str) else x)
        #         Setdf = RefineNewNSEFutures(Setdf)
        # except:
        #     print('Couldnt download:'+ FnOSettlementURL)    
            
        # if not Setdf.empty:
        #     feather.write_feather(Setdf, './New NSE site/'+FnOSettleArg+'.ftr')    


def RefineNewNSEFutures(DF):
    df = DF.copy()
    
    if 'INSTRUMENT' in df.columns:
        df.rename(columns={'INSTRUMENT': 'Instrument'}, inplace=True)
        
    if 'SYMBOL' in df.columns:
        df.rename(columns={'SYMBOL': 'Symbol'}, inplace=True)
    
    if 'EXP_DATE' in df.columns:
        df.rename(columns={'EXP_DATE': 'Expiry'}, inplace=True)
        # df["Expiry"] = df["EXP_DATE"].apply(pd.to_datetime, format='%d-%b-%Y')
        df['Expiry'] = df['Expiry'].dt.date
     
    if 'OPEN_PRICE' in df.columns:
        df.rename(columns={'OPEN_PRICE': 'Open'}, inplace=True) 
        
    if 'HI_PRICE' in df.columns:
        df.rename(columns={'HI_PRICE': 'High'}, inplace=True)
        
    if 'LO_PRICE' in df.columns:
        df.rename(columns={'LO_PRICE': 'Low'}, inplace=True)
    
    if 'CLOSE_PRICE' in df.columns:
        df.rename(columns={'CLOSE_PRICE': 'Close'}, inplace=True)

    if 'OPEN_INT*' in df.columns:
        df.rename(columns={'OPEN_INT*': 'Open Interest'}, inplace=True)

    if 'TRD_VAL' in df.columns:
        df.rename(columns={'TRD_VAL': 'Turnover'}, inplace=True)                  
        
    if 'NO_OF_CONT' in df.columns:
        df.rename(columns={'NO_OF_CONT': 'Number of Contracts'}, inplace=True)      

    if 'DATE' in df.columns:
        df.rename(columns={'DATE': 'Date'}, inplace=True)
        df['Date'] = df['Date'].apply(pd.to_datetime, format='%d-%b-%Y')
        df['Date'] = df['Date'].dt.date
    
    if 'UNDERLYING' in df.columns:
        df.rename(columns={'UNDERLYING': 'Symbol'}, inplace=True)

    if 'INSTRUMENT' in df.columns:
        df.rename(columns={'INSTRUMENT': 'Instrument'}, inplace=True)

    if 'EXPIRY DATE' in df.columns:
        df.rename(columns={'EXPIRY DATE': 'Expiry'}, inplace=True)
        df['Expiry'] = df['Expiry'].apply(pd.to_datetime, format='%d-%b-%Y')
        df['Expiry'] = df['Expiry'].dt.date

    if 'MTM SETTLEMENT PRICE' in df.columns:
        df.rename(columns={'MTM SETTLEMENT PRICE': 'Settle Price'}, inplace=True)
        
    return df

# for sym in FnOSymbollist:
#     FuturesFileName = sym + '_' + FullFuturesFilePath
#     #Read from feather
#     if (FindFeather(FuturesFileName, './Datastore/')):
#         OldFuturesdf = feather.read_feather('./Datastore/'+FuturesFileName)
#         df = OldFuturesdf.copy()
#         print('Updating Futures for '+ sym)
#         if 'Number of Contracts' in df.columns:
#             df.rename(columns={'Number of Contracts': 'No. of contracts'}, inplace=True)
        
#         if 'Turnover' in df.columns:
#             df.rename(columns={'Turnover': 'Turnover in Lacs'}, inplace=True)

#         if 'Open Interest' in df.columns:
#             df.rename(columns={'Open Interest': 'Open Int'}, inplace=True)
        
#     if not df.empty:
#         feather.write_feather(df, './Datastore/'+FuturesFileName)

    
            # ###########OldFuturesdf.drop("index", axis=1, inplace=True) #DO NOT ENABLE!!!
            # ############OldFuturesdf = OldFuturesdf[OldFuturesdf.Date < FnOStartDate] #DO NOT ENABLE!!!
            # ########OldOptionsdf = OldOptionsdf[OldOptionsdf.Date < FnOStartDate] #DO NOT ENABLE!!!            
            
            
# def UpdatetNSEFuturesData():
#     TotalNewFuturesdf = pd.DataFrame()
#     for weekday in bday:
#         FnOReportArg = 'fo' + weekday.strftime("%d%m%Y")
#         FnOSettleArg = 'FOSett_prce_' + weekday.strftime("%d%m%Y") + '.csv.ftr'
    
#         zf = ZipFile('New NSE site/'+FnOReportArg + '.zip') 
#         CSVdf = pd.read_csv(zf.open(FnOReportArg+'.csv'), parse_dates=[2], dayfirst=True)
#         CSVdf = CSVdf.rename(columns=lambda x: x.strip())
#         CSVdf = CSVdf.applymap(lambda x: x.strip() if isinstance(x, str) else x)
#         NewFuturesdf = RefineNewNSEFutures(CSVdf)
        
#         if (FindFeather(FnOSettleArg, './New NSE site/')):
#             Settledf = feather.read_feather('./New NSE site/'+FnOSettleArg) #Volatilitydf.info()
#             NewFuturesdf = pd.merge(NewFuturesdf, Settledf, how="inner", on=["Symbol","Expiry","Instrument"])
#         else:
#             print('Couldnt find settlement info for '+ FnOSettleArg)
        
#         TotalNewFuturesdf = TotalNewFuturesdf.append(NewFuturesdf, ignore_index=True)
    
#     TotalNewFuturesdf = TotalNewFuturesdf.sort_values(by=['Symbol', 'Date'])
#     FnOSymbollist = []
#     #Adding values to list
#     FnOSymbollist = list(TotalNewFuturesdf['Symbol'])
#     #Removing duplicates in list
#     FnOSymbollist = list(dict.fromkeys(FnOSymbollist))
    
#     #Update the old Futures file
#     for sym in FnOSymbollist:
        
#         FuturesFileName = sym + '_' + FullFuturesFilePath
#         #Read from feather
#         if (FindFeather(FuturesFileName, './Datastore/')):
#             OldFuturesdf = feather.read_feather('./Datastore/'+FuturesFileName)
#             print('Updating Futures for '+ sym)
#             Mergedf = OldFuturesdf.append(TotalNewFuturesdf[TotalNewFuturesdf["Symbol"] == sym], ignore_index = True)            
#         else: #A new symbol has been added, create a feather for it
#             print('Creating new Futures DB for '+ sym)
#             Mergedf = TotalNewFuturesdf[TotalNewFuturesdf["Symbol"] == sym]#, ignore_index = True)
            
#         if not Mergedf.empty:
#             feather.write_feather(Mergedf, './Datastore/'+FuturesFileName)


    ExpiryDatedf = NewFuturesdf.groupby('Symbol')['Expiry'].apply(lambda x: pd.Series(list(x))).unstack() 
    ExpiryDatedf = ExpiryDatedf.reset_index(level=0)
    ExpiryDatedf = ExpiryDatedf.rename(columns={0: 'NearExpiry',1:'MidExpiry',2:'FarExpiry'})
    
    SettlePricedf = NewFuturesdf.groupby('Symbol')['Settle Price'].apply(lambda x: pd.Series(list(x))).unstack()
    SettlePricedf = SettlePricedf.reset_index(level=0)
    SettlePricedf = SettlePricedf.rename(columns={0: 'NearSettlePrice',1:'MidSettlePrice',2:'FarSettlePrice'})
  
    OpenInterestdf = NewFuturesdf.groupby('Symbol')['Open Interest'].apply(lambda x: pd.Series(list(x))).unstack()
    OpenInterestdf = OpenInterestdf.reset_index(level=0)
    OpenInterestdf = OpenInterestdf.rename(columns={0: 'NearOpenInterest',1:'MidOpenInterest',2:'FarOpenInterest'})        
    
    NoOfContractsdf = NewFuturesdf.groupby('Symbol')['Number of Contracts'].apply(lambda x: pd.Series(list(x))).unstack()
    NoOfContractsdf = NoOfContractsdf.reset_index(level=0)
    NoOfContractsdf = NoOfContractsdf.rename(columns={0: 'NearNoOfContracts',1:'MidNoOfContracts',2:'FarNoOfContracts'})        
    
  
    dfs = [ExpiryDatedf, OpenInterestdf, SettlePricedf, NoOfContractsdf]
    Futdf = reduce(lambda left,right: pd.merge(left,right,on='Symbol'), dfs)   
    

    if (FindFeather(FnOVolatilityArg, './New NSE site/')):
        Volatilitydf = feather.read_feather('./New NSE site/'+FnOVolatilityArg) #Volatilitydf.info()
        #Below Formatting is needed to clean up the csv and remove whitespaces
        Volatilitydf = Volatilitydf.rename(columns=lambda x: x.strip())
        Volatilitydf = Volatilitydf.applymap(lambda x: x.strip() if isinstance(x, str) else x)
        Mergedf = pd.merge(NewFuturesdf, Volatilitydf, how="outer", on=["Symbol"])

df = pd.DataFrame({'Date': ['05-01-2018', '02-20-2020']})

df['Date'] = pd.to_datetime(df['Date'])
df['Month'] = df['Date'].dt.month
df['Month-str'] = df['Date'].dt.strftime('%b')
df['Month-str-full'] = df['Date'].dt.strftime('%B')

    for Scrip in NSEFnOList:
        Scrip = "OIL"
        Optionsdf = None
        CurrentDate = datetime.date.today()
        CurrentMonth = CurrentDate.month
        CurrentYear = CurrentDate.year
        print('For'+Scrip)
        OptionsFileName = Scrip + '_' + MonthlyOptionsFilePath
        #Read from feather
        if (FindFeather(OptionsFileName, './Datastore')):
            Optionsdf = feather.read_feather('./Datastore/'+OptionsFileName)
            try:
                # Optionsdf['Date'] = Optionsdf['Date'].dt.date
                Optionsdf['Expiry'] = Optionsdf['Expiry'].dt.date
            except:
                print(Scrip," :already done")
                continue
            feather.write_feather(Optionsdf, './Datastore/'+ OptionsFileName)
            # continue

# def MACDVisual(MACDdf,Scrip):
#     DF = MACDdf.copy()         
#     plt.subplot(311)
#     plt.figsize=(16,9)
    
#     if(Scrip == "NIFTY"):
#         plt.plot(DF.iloc[-100:,3])
#     else:
#         plt.plot(DF.iloc[-100:,[7,8]])
#         plt.legend(('Close','VWAP'),loc='upper left')
    
#     plt.title(Scrip)
#     plt.xticks([])
#     plt.grid(True)
    
#     plt.subplot(312)
#     plt.figsize=(16,9)
#     if(Scrip == "NIFTY"):
#         plt.plot(DF.iloc[-100:,4].index, DF.iloc[-100:,4].values)
#     else:
#         plt.plot(DF.iloc[-100:,[9,12]].index, DF.iloc[-100:,[9,12]].values)
#         plt.legend(('Volume','Delivered'),loc='upper left')
#     plt.title('Volume/Delivered')
#     plt.xticks([])
#     plt.grid(True)
    
#     plt.subplot(313)
#     plt.figsize=(16,9)
#     plt.plot(DF.iloc[-100:,[-2,-1]])
#     plt.title('MACD')
#     plt.legend(('MACD','Signal'),loc='upper left')
#     plt.grid(True)
    
#     plt.show()
    
    # fig, (ax0, ax1) = plt.subplots(nrows=2,ncols=1, sharex=True, sharey=False, figsize=(10, 6), gridspec_kw = {'height_ratios':[2.5, 1]})
    # OHLCdf.iloc[-100:,8].plot(ax=ax0)
    # ax0.set(ylabel='Close')
    
    # OHLCdf.iloc[-100:,[-2,-1]].plot(ax=ax1)
    # ax1.set(xlabel='Date', ylabel='MACD/Signal')
    
    # # Title the figure
    # fig.suptitle('Stock Price with MACD', fontsize=14, fontweight='bold')
            # plt.subplot(312)
            # plt.plot(Indicatordf.iloc[-100:,[-2,-1]])
            # plt.figsize=(16,9)
            # plt.title(" TR & ATR")
            # plt.grid(True)
            # #Deliverable volume %
            # plt.subplot(313)
            # plt.plot(Indicatordf.iloc[-100:,-3])
            # plt.figsize=(16,9)
            # plt.title('%Deliverable')
            # plt.grid(True)            
            # plt.show()
    
            # OHLCdf["ADX"] = talib.ADX(OHLCdf["High"],
            #                                     OHLCdf["Low"],
            #                                     OHLCdf["Close"],
            #                                     timeperiod=14)
            
            # Indicatordf["ADX"] = ADX(Indicatordf,20)
            
                        # plt.subplot(311)
            # plt.plot(Indicatordf.iloc[-100:,[-4,-3,-2]])
            # plt.figsize=(16,9)
            # plt.title(Scrip+' Bollinger Band')
            # plt.grid(True)
            
            
                                # data[data['Value'] == True]
            
                    # .reset_index(level=0, inplace=True)
            
            #Using OHLCData here as it is not time serie data. Todo: Figure out a way to cache this
            # Renkodata = Renko_DF(OHLCdf)
            # #DF amd number of latest bricks
            # PlotRenko(Renkodata,100)
# df.sort_values(by='col1', ascending=False)
# MonthlyFuturesFilePath = "monthly-futures.ftr"
# MonthlyOptionsFilePath = "monthly-options.ftr"