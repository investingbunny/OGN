# -*- coding: utf-8 -*-
"""
Created on Sat Oct  3 17:35:42 2020
This file is intended to download F&O data from the new NSE website.
The file is a consolidated daily report which has to be dissected.
@author: User
"""
import requests
from zipfile import ZipFile
import pandas as pd
import datetime
from datetime import date
from dateutil.relativedelta import *
import time
import numpy as np
import io
import os
import pyarrow
import pyarrow.feather as feather
from functools import reduce

# FnOStartDate = date(2020,9,28)
FnOReport = 'https://archives.nseindia.com/archives/fo/mkt/'
FnOVolatility = 'https://archives.nseindia.com/archives/nsccl/volt/'
FnOSettlement = 'https://archives.nseindia.com/archives/nsccl/sett/'
FnOBhavcopy = 'https://archives.nseindia.com/content/historical/DERIVATIVES/'
MonthlyFuturesFilePath = "monthly-futures.ftr"
FullFuturesFilePath = "full-futures.ftr"
MonthlyOptionsFilePath = "monthly-options.ftr"

# OHLCStartDate = date(2020,10,1)
OHLCVolatility = 'https://archives.nseindia.com/archives/nsccl/volt/' # CMVOLT_09102020.CSV
OHLCBhavCopy = 'https://archives.nseindia.com/products/content/' #sec_bhavdata_full_15102020.csv
OHLCBhavPR = 'https://archives.nseindia.com/archives/equities/bhavcopy/pr/' #PR151020.zip
DailyOHLCFilePath = "ohlc.ftr"

HolidayList = ['26-Jan-21','11-Mar-21','29-Mar-21','30-Mar-21','31-Mar-21','02-Apr-21','14-Apr-21','21-Apr-21','13-May-21','21-Jul-21','19-Aug-21','10-Sep-21','15-Oct-21','05-Nov-21','19-Nov-21']
HolidayList = pd.to_datetime(pd.Series(HolidayList), format='%d-%b-%y')

def FindFeather(name, path):
    for root, dirs, files in os.walk(path):
        if name in files:
            return os.path.join(root, name)

def UpdateBusinessDays():
    #Check Index futures for last update NiftyFullFutures.info()
    NiftyFullFutures = feather.read_feather('./Datastore/NIFTY_full-futures.ftr')
    FuturesStartDate = NiftyFullFutures.iloc[-1].Date
    FuturesStartDate += datetime.timedelta(days=1)
    YesterdayDate = datetime.date.today() - datetime.timedelta(days=1) # weekday = YesterdayDate

    bday = pd.bdate_range(FuturesStartDate, YesterdayDate) #To be replaced with LastRecordDate, CurrentDate
    bday = set(bday).difference(HolidayList)
    print('UpdateBusinessDays complete ')

def UpdateOHLCBusinessDays():
    #Check Index futures for last update
    SBINOHLC = feather.read_feather('./Datastore/SBIN_ohlc.ftr')
    OHLCStartDate = SBINOHLC.iloc[-1].Date
    OHLCStartDate += datetime.timedelta(days=1)
    YesterdayOHLCDate = datetime.date.today() - datetime.timedelta(days=1)

    ohlcbday = pd.bdate_range(OHLCStartDate, YesterdayOHLCDate) #To be replaced with LastRecordDate, CurrentDate
    ohlcbday = set(ohlcbday).difference(HolidayList)
    print('UpdateOHLCBusinessDays complete ')

def DownloadNewNSEFnO():        
    #Loop through dates to download NSE Futures data
    for weekday in bday:
        # 2020/OCT/fo14OCT2020bhav.csv.zip
        FnOBhavMonth = weekday.strftime("%b").upper()
        FnOBhavYear = weekday.strftime("%Y")
        
        print('Download NSEFnOBhav for '+ weekday.strftime("%Y-%m-%d"))
        #FnO Bhav report download
        FnOBhavArg = 'fo' + weekday.strftime("%d%b%Y").upper() + 'bhav.csv.zip'
        FnOBhavURL = FnOBhavcopy + FnOBhavYear + '/' + FnOBhavMonth + '/' + FnOBhavArg
        try:
            r = requests.get(FnOBhavURL) #Download FnO Market report for 'weekday'
            open('./New NSE site/'+FnOBhavArg, 'wb').write(r.content)
            print('Download:'+ FnOBhavURL)
        except:
            print('Couldnt download:'+ FnOBhavURL)
        
        print('DownloadNewNSEFnO for'+ weekday.strftime("%Y-%m-%d"))
        #FnO Market report download
        FnOReportArg = 'fo' + weekday.strftime("%d%m%Y") + '.zip'
        FnOReportURL = FnOReport + FnOReportArg
        try:
            r = requests.get(FnOReportURL, allow_redirects=True) #Download FnO Market report for 'weekday'
            open('./New NSE site/'+FnOReportArg, 'wb').write(r.content)
        except:
            print('Couldnt download:'+ FnOReportURL)
            
        #FnO Volatility report download
        # FnOVolatilityArg = 'FOVOLT_' + weekday.strftime("%d%m%Y") + '.csv'
        # FnOVolatilityURL = FnOVolatility + FnOVolatilityArg
        # try:
        #     r = requests.get(FnOVolatilityURL, allow_redirects=True) #Download FnO Volatility report for 'weekday'
        #     if r.ok:
        #         data = r.content.decode('utf8')
        #         Voldf = pd.read_csv(io.StringIO(data))
        #         Voldf = Voldf.rename(columns=lambda x: x.strip())
        #         Voldf = Voldf.applymap(lambda x: x.strip() if isinstance(x, str) else x)
        # except:
        #     print('Couldnt download:'+ FnOVolatilityURL)    
            
        # if not Voldf.empty:
        #     feather.write_feather(Voldf, './New NSE site/'+FnOVolatilityArg+'.ftr')

def UpdatetNSEFnOData():
    TotalNewOptionsdf = pd.DataFrame()
    TotalNewFuturesdf = pd.DataFrame()
    for weekday in bday:  # weekday = YesterdayDate
        FnOBhavArg = 'fo' + weekday.strftime("%d%b%Y").upper() + 'bhav'
        print('Processing '+FnOBhavArg)
        zf = ZipFile('New NSE site/'+FnOBhavArg+ '.csv.zip')  #fo12OCT2020bhav.csv.zip
        CSVdf = pd.read_csv(zf.open(FnOBhavArg+'.csv'), parse_dates=[2], dayfirst=True) #fo12OCT2020bhav
        CSVdf = CSVdf.rename(columns=lambda x: x.strip())
        CSVdf = CSVdf.applymap(lambda x: x.strip() if isinstance(x, str) else x)
        NewFnOdf = RefineNSEFnOData(CSVdf)
        NewFuturesdf = NewFnOdf[(NewFnOdf["Instrument"] == 'FUTIDX') | (NewFnOdf["Instrument"] == 'FUTSTK')]
        NewOptionsdf = NewFnOdf[(NewFnOdf["Instrument"] == 'OPTIDX') | (NewFnOdf["Instrument"] == 'OPTSTK')]
        
        TotalNewOptionsdf = TotalNewOptionsdf.append(NewOptionsdf, ignore_index=True)
        TotalNewFuturesdf = TotalNewFuturesdf.append(NewFuturesdf, ignore_index=True)
    
    TotalNewOptionsdf = TotalNewOptionsdf.sort_values(by=['Symbol', 'Date'])
    TotalNewFuturesdf = TotalNewFuturesdf.sort_values(by=['Symbol', 'Date'])
    TotalNewOptionsdf = TotalNewOptionsdf.drop_duplicates()
    TotalNewFuturesdf = TotalNewFuturesdf.drop_duplicates()
    
    FnOSymbollist = []
    #Adding values to list
    FnOSymbollist = list(TotalNewOptionsdf['Symbol'])
    #Removing duplicates in list
    FnOSymbollist = list(dict.fromkeys(FnOSymbollist))
    
    for sym in FnOSymbollist: #sym = 'NIFTY'
        MergeOptdf = pd.DataFrame()
        #Update the old Options file
        OptionsFileName = sym + '_' + MonthlyOptionsFilePath
        #Read from feather
        if (FindFeather(OptionsFileName, './Datastore/')):
            OldOptionsdf = feather.read_feather('./Datastore/'+OptionsFileName)
            # OldOptionsdf = OldOptionsdf[OldOptionsdf.Date < FnOStartDate] 
            print('Updating Options for '+ sym)
            MergeOptdf = OldOptionsdf.append(TotalNewOptionsdf[TotalNewOptionsdf["Symbol"] == sym], ignore_index = True)            
        else: #A new symbol has been added, create a feather for it
            print('Creating new Options DB for '+ sym)
            MergeOptdf.reset_index(level=0, inplace=True, drop=True)
            MergeOptdf = TotalNewOptionsdf[TotalNewOptionsdf["Symbol"] == sym]
            
        if not MergeOptdf.empty:
            feather.write_feather(MergeOptdf, './Datastore/'+OptionsFileName)
        
        #Update the old Futures file
        FuturesFileName = sym + '_' + FullFuturesFilePath
        #Read from feather
        MergeFutdf = pd.DataFrame()
        if (FindFeather(FuturesFileName, './Datastore/')):
            OldFuturesdf = feather.read_feather('./Datastore/'+FuturesFileName)
            # OldFuturesdf = OldFuturesdf[OldFuturesdf.Date < FnOStartDate]
            print('Updating Futures for '+ sym)
            MergeFutdf = OldFuturesdf.append(TotalNewFuturesdf[TotalNewFuturesdf["Symbol"] == sym], ignore_index = True)            
        else: #A new symbol has been added, create a feather for it
            print('Creating new Futures DB for '+ sym)
            MergeFutdf.reset_index(level=0, inplace=True, drop=True)
            MergeFutdf = TotalNewFuturesdf[TotalNewFuturesdf["Symbol"] == sym]
            
        if not MergeFutdf.empty:
            MergeFutdf.drop("Strike Price", axis=1, inplace=True)
            MergeFutdf.drop("Option type", axis=1, inplace=True)
            feather.write_feather(MergeFutdf, './Datastore/'+FuturesFileName)

def RefineNSEFnOData(DF):
    df = DF.copy()
    
    if 'INSTRUMENT' in df.columns:
        df.rename(columns={'INSTRUMENT': 'Instrument'}, inplace=True)
        
    if 'SYMBOL' in df.columns:
        df.rename(columns={'SYMBOL': 'Symbol'}, inplace=True)
    
    if 'EXPIRY_DT' in df.columns:
        df.rename(columns={'EXPIRY_DT': 'Expiry'}, inplace=True)
        # df["Expiry"] = df["EXP_DATE"].apply(pd.to_datetime, format='%d-%b-%Y')
        df['Expiry'] = df['Expiry'].dt.date

    if 'STRIKE_PR' in df.columns:
        df.rename(columns={'STRIKE_PR': 'Strike Price'}, inplace=True)

    if 'OPTION_TYP' in df.columns:
        df.rename(columns={'OPTION_TYP': 'Option type'}, inplace=True)
        
    if 'OPEN' in df.columns:
        df.rename(columns={'OPEN': 'Open'}, inplace=True)        
        
    if 'HIGH' in df.columns:
        df.rename(columns={'HIGH': 'High'}, inplace=True)

    if 'LOW' in df.columns:
        df.rename(columns={'LOW': 'Low'}, inplace=True)
    
    if 'CLOSE' in df.columns:
        df.rename(columns={'CLOSE': 'Close'}, inplace=True)

    if 'SETTLE_PR' in df.columns:
        df.rename(columns={'SETTLE_PR': 'Settle Price'}, inplace=True)
        
    if 'CONTRACTS' in df.columns:
        df.rename(columns={'CONTRACTS': 'No. of contracts'}, inplace=True)          

    if 'VAL_INLAKH' in df.columns:
        df.rename(columns={'VAL_INLAKH': 'Turnover in Lacs'}, inplace=True)

    if 'OPEN_INT' in df.columns:
        df.rename(columns={'OPEN_INT': 'Open Int'}, inplace=True)

    if 'CHG_IN_OI' in df.columns:
        df.rename(columns={'CHG_IN_OI': 'Change in OI'}, inplace=True)
        
    if 'TIMESTAMP' in df.columns:
        df.rename(columns={'TIMESTAMP': 'Date'}, inplace=True)
        df["Date"] = df["Date"].apply(pd.to_datetime, format='%d-%b-%Y')
        df['Date'] = df['Date'].dt.date
        
    if 'Unnamed: 15' in df.columns:
        df.drop("Unnamed: 15", axis=1, inplace=True)
        
    return df

def DownloadNewNSEOHLC():        
    #Loop through dates to download NSE OHLC data
    for weekday in ohlcbday: # weekday = date(2020,9,28)
        print('DownloadNewNSEOHLC for'+ weekday.strftime("%Y-%m-%d"))
        #OHLC Market report download # sec_bhavdata_full_09102020.csv
        OHLCBhavArg = 'sec_bhavdata_full_' + weekday.strftime("%d%m%Y") + '.csv'
        OHLCReportURL = OHLCBhavCopy + OHLCBhavArg
        try:
            r = requests.get(OHLCReportURL, allow_redirects=True) #Download OHLC Market report for 'weekday'
            if r.ok:
                data = r.content.decode('utf8')
                OHLCdf = pd.read_csv(io.StringIO(data))
                OHLCdf = OHLCdf.rename(columns=lambda x: x.strip())
                OHLCdf = OHLCdf.applymap(lambda x: x.strip() if isinstance(x, str) else x)
        except:
            print('Couldnt download:'+ OHLCReportURL)    
            
        if not OHLCdf.empty:
            feather.write_feather(OHLCdf, './New NSE site/'+OHLCBhavArg+'.ftr')
            
        #OHLC Volatility report download
        OHLCVolatilityArg = 'CMVOLT_' + weekday.strftime("%d%m%Y") + '.CSV' # CMVOLT_09102020.CSV
        OHLCVolatilityURL = OHLCVolatility + OHLCVolatilityArg
        try:
            r = requests.get(OHLCVolatilityURL, allow_redirects=True) #Download OHLC Volatility report for 'weekday'
            if r.ok:
                data = r.content.decode('utf8')
                Voldf = pd.read_csv(io.StringIO(data))
                Voldf = Voldf.rename(columns=lambda x: x.strip())
                Voldf = Voldf.applymap(lambda x: x.strip() if isinstance(x, str) else x)
        except:
            print('Couldnt download:'+ OHLCVolatilityURL)    
            
        if not Voldf.empty:
            feather.write_feather(Voldf, './New NSE site/'+OHLCVolatilityArg+'.ftr')

        print('Download Bhav PR for '+ weekday.strftime("%Y-%m-%d"))
        #Bhav PR report download
        OHLCBhavPRArg = 'PR' + weekday.strftime("%d%m%y") + '.zip' #PR151020.zip
        OHLCBhavPRURL = OHLCBhavPR + OHLCBhavPRArg
        try:
            r = requests.get(OHLCBhavPRURL, allow_redirects=True) #Download Bhav PR report for 'weekday'
            open('./New NSE site/'+OHLCBhavPRArg, 'wb').write(r.content)
        except:
            print('Couldnt download:'+ OHLCBhavPRURL)

def UpdatetNSEOHLCData():
    TotalNewOHLCdf = pd.DataFrame()
    TotalNewIndexOHLCdf = pd.DataFrame()
    for weekday in ohlcbday:
        OHLCBhavArg = 'sec_bhavdata_full_' + weekday.strftime("%d%m%Y") + '.csv.ftr'
        print('Adding OHLC data for '+ weekday.strftime("%d%m%Y"))
        if (FindFeather(OHLCBhavArg, './New NSE site/')):
            OHLCBhavdf = feather.read_feather('./New NSE site/'+OHLCBhavArg) #OHLCBhavdf.info()
            TotalNewOHLCdf = TotalNewOHLCdf.append(OHLCBhavdf, ignore_index=True)
        else:
            print('Couldnt find: ' + OHLCBhavArg)
            continue
        
        IndexBhavZip = 'PR' + weekday.strftime("%d%m%y") #IndexBhavZip = 'PR161020'
        IndexBhavArg = 'Pr' + weekday.strftime("%d%m%y") #IndexBhavArg = 'Pr161020'
        print('Processing '+ IndexBhavZip)
        zf = ZipFile('New NSE site/'+IndexBhavZip + '.zip')  #PR161020.zip
        CSVIndexdf = pd.read_csv(zf.open(IndexBhavArg+'.csv'), parse_dates=[2], dayfirst=True,error_bad_lines=False) #fo12OCT2020bhav
        CSVIndexdf = CSVIndexdf.head(57)
        CSVIndexdf = CSVIndexdf.rename(columns=lambda x: x.strip())
        CSVIndexdf = CSVIndexdf.applymap(lambda x: x.strip() if isinstance(x, str) else x)
        
        if not 'Date' in CSVIndexdf.columns:
            CSVIndexdf["Date"] = np.nan
        CSVIndexdf.Date = pd.to_datetime(weekday)
        
        TotalNewIndexOHLCdf = TotalNewIndexOHLCdf.append(CSVIndexdf, ignore_index=True)
        
#####################################################################################
    TotalNewOHLCdf = RefineNewNSEOHLC(TotalNewOHLCdf) #TotalNewOHLCdf.info()
    TotalNewOHLCdf = TotalNewOHLCdf[TotalNewOHLCdf.Series == "EQ"] #Only considering EQ, no debentures(?)
    TotalNewOHLCdf = TotalNewOHLCdf.sort_values(by=['Symbol', 'Date'])
    TotalNewOHLCdf = TotalNewOHLCdf.drop_duplicates()
    OHLCSymbollist = []
    #Adding values to list
    OHLCSymbollist = list(TotalNewOHLCdf['Symbol'])
    #Removing duplicates in list
    OHLCSymbollist = list(dict.fromkeys(OHLCSymbollist))
    
    #Update the old OHLC file
    for sym in OHLCSymbollist: # sym = 'HDFC'
        OHLCFileName = sym + '_' + DailyOHLCFilePath
        #Read from feather
        if (FindFeather(OHLCFileName, './Datastore/')):
            OldOHLCdf = feather.read_feather('./Datastore/'+OHLCFileName) # OldOHLCdf.info()
            # OldOHLCdf = OldOHLCdf[OldOHLCdf.Date < FnOStartDate]
            print('Updating OHLC for '+ sym)
            Mergedf = OldOHLCdf.append(TotalNewOHLCdf[TotalNewOHLCdf["Symbol"] == sym], ignore_index = True)            
        else: #A new symbol has been added, create a feather for it
            print('Creating new OHLC DB for '+ sym)
            Mergedf = TotalNewOHLCdf[TotalNewOHLCdf["Symbol"] == sym]
            Mergedf.reset_index(level=0, inplace=True, drop=True)
            
        if not Mergedf.empty:
            feather.write_feather(Mergedf, './Datastore/'+OHLCFileName)
        else:
            print(sym + ' not updated, in Series '+ Mergedf.iloc[-1].Series)
            
############################################## For Indices below

    TotalNewIndexOHLCdf.drop(["MKT","IND_SEC","CORP_IND"], axis=1, inplace=True)
    TotalNewIndexOHLCdf['Date'] = TotalNewIndexOHLCdf['Date'].dt.date
    NewNSEIndexdf = RefineNewNSEOHLC(TotalNewIndexOHLCdf) # NewNSEIndexdf.info()

    cols=[i for i in NewNSEIndexdf.columns if i not in ["Symbol","Date"]]
    for col in cols:
        NewNSEIndexdf[col]=pd.to_numeric(NewNSEIndexdf[col])
        
    NewNSEIndexdf['Symbol'].replace('Nifty 50','NIFTY',inplace=True)
    NewNSEIndexdf['Symbol'].replace('Nifty Bank','BANKNIFTY',inplace=True)
    NewNSEIndexdf = NewNSEIndexdf.sort_values(by=['Date', 'Symbol'])
    NewNSEIndexdf = NewNSEIndexdf.drop_duplicates()

    IndexSymbollist = []
    #Adding values to list
    IndexSymbollist = list(NewNSEIndexdf['Symbol'])
    #Removing duplicates in list
    IndexSymbollist = list(dict.fromkeys(IndexSymbollist))
        
    #Update the old OHLC file
    for sym in IndexSymbollist: # sym = 'HDFC'
        OHLCFileName = sym + '_' + DailyOHLCFilePath
        #Read from feather
        if (FindFeather(OHLCFileName, './Datastore/')):
            OldIndexOHLCdf = feather.read_feather('./Datastore/'+OHLCFileName) # OldOHLCdf.info()
            # OldIndexOHLCdf = OldIndexOHLCdf[OldIndexOHLCdf.Date < FnOStartDate]
            print('Updating OHLC for '+ sym)
            MergeIndexdf = OldIndexOHLCdf.append(NewNSEIndexdf[NewNSEIndexdf["Symbol"] == sym], ignore_index = True)            
        else: #A new symbol has been added, create a feather for it
            print('Creating new OHLC DB for '+ sym)
            MergeIndexdf = NewNSEIndexdf[NewNSEIndexdf["Symbol"] == sym]
            MergeIndexdf.reset_index(level=0, inplace=True, drop=True)
            
        if not MergeIndexdf.empty:
            feather.write_feather(MergeIndexdf, './Datastore/'+OHLCFileName)
        else:
            print(sym + ' not updated, is empty')

def RefineNewNSEOHLC(DF):
    df = DF.copy()
    
    if 'SERIES' in df.columns:
        df.rename(columns={'SERIES': 'Series'}, inplace=True)
        
    if 'SYMBOL' in df.columns:
        df.rename(columns={'SYMBOL': 'Symbol'}, inplace=True)
    
    if 'DATE1' in df.columns:
        df.rename(columns={'DATE1': 'Date'}, inplace=True)
        df["Date"] = df["Date"].apply(pd.to_datetime, format='%d-%b-%Y')
        df['Date'] = df['Date'].dt.date

    if 'PREV_CLOSE' in df.columns:
        df.rename(columns={'PREV_CLOSE': 'Prev Close'}, inplace=True) 

    if 'OPEN_PRICE' in df.columns:
        df.rename(columns={'OPEN_PRICE': 'Open'}, inplace=True) 
        
    if 'HIGH_PRICE' in df.columns:
        df.rename(columns={'HIGH_PRICE': 'High'}, inplace=True)
        
    if 'LOW_PRICE' in df.columns:
        df.rename(columns={'LOW_PRICE': 'Low'}, inplace=True)

    if 'LAST_PRICE' in df.columns:
        df.rename(columns={'LAST_PRICE': 'Last'}, inplace=True)
        df['Last'] = pd.to_numeric(df['Last'], errors='coerce')
    
    if 'CLOSE_PRICE' in df.columns:
        df.rename(columns={'CLOSE_PRICE': 'Close'}, inplace=True)

    if 'AVG_PRICE' in df.columns:
        df.rename(columns={'AVG_PRICE': 'VWAP'}, inplace=True)

    if 'TTL_TRD_QNTY' in df.columns:
        df.rename(columns={'TTL_TRD_QNTY': 'Volume'}, inplace=True)                  
        
    if 'TURNOVER_LACS' in df.columns:
        df.rename(columns={'TURNOVER_LACS': 'Turnover'}, inplace=True)      

    if 'NO_OF_TRADES' in df.columns:
        df.rename(columns={'NO_OF_TRADES': 'Trades'}, inplace=True)

    if 'DELIV_QTY' in df.columns:
        df.rename(columns={'DELIV_QTY': 'Deliverable Volume'}, inplace=True)
        df['Deliverable Volume'] = pd.to_numeric(df['Deliverable Volume'], errors='coerce')
        
    if 'DELIV_PER' in df.columns:
        df.rename(columns={'DELIV_PER': '%Deliverble'}, inplace=True)
        df['%Deliverble'] = pd.to_numeric(df['%Deliverble'], errors='coerce')
        df['%Deliverble'] = df['%Deliverble'].div(100)

####Specific for Index below
    if 'SECURITY' in df.columns:
        df.rename(columns={'SECURITY': 'Symbol'}, inplace=True)

    if 'PREV_CL_PR' in df.columns:
        df.rename(columns={'PREV_CL_PR': 'Prev Close'}, inplace=True)

    if 'NET_TRDVAL' in df.columns:
        df.rename(columns={'NET_TRDVAL': 'Turnover'}, inplace=True)

    if 'NET_TRDQTY' in df.columns:
        df.rename(columns={'NET_TRDQTY': 'Volume'}, inplace=True)

    if 'TRADES' in df.columns:
        df.rename(columns={'TRADES': 'No. of Trades'}, inplace=True)
        
    return df

def main():
    NiftyFullFutures = feather.read_feather('./Datastore/NIFTY_full-futures.ftr')
    FuturesStartDate = NiftyFullFutures.iloc[-1].Date
    FuturesStartDate += datetime.timedelta(days=1)
    YesterdayDate = datetime.date.today() - datetime.timedelta(days=1) # weekday = YesterdayDate

    bday = pd.bdate_range(FuturesStartDate, YesterdayDate) #To be replaced with LastRecordDate, CurrentDate
    bday = set(bday).difference(HolidayList)
    print('UpdateBusinessDays complete ')
    
    SBINOHLC = feather.read_feather('./Datastore/SBIN_ohlc.ftr')
    OHLCStartDate = SBINOHLC.iloc[-1].Date
    OHLCStartDate += datetime.timedelta(days=1)
    YesterdayOHLCDate = datetime.date.today() - datetime.timedelta(days=1)

    ohlcbday = pd.bdate_range(OHLCStartDate, YesterdayOHLCDate) #To be replaced with LastRecordDate, CurrentDate
    ohlcbday = set(ohlcbday).difference(HolidayList)
    print('UpdateOHLCBusinessDays complete ')
    
    DownloadNewNSEFnO()
    UpdatetNSEFnOData()
    DownloadNewNSEOHLC()
    UpdatetNSEOHLCData()