# -*- coding: utf-8 -*-
"""
Created on Tue Aug 18 11:54:38 2020

@author: User
"""

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