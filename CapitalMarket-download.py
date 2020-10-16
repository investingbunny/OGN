# -*- coding: utf-8 -*-
"""
Created on Sun Oct  11 17:35:42 2020
This file is intended to download Capital market data from the new NSE website.
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
import io
import os
import pyarrow
import pyarrow.feather as feather
from functools import reduce

# OHLCStartDate = date(2020,10,1) YesterdayDate = date(2020,9,30)
OHLCVolatility = 'https://archives.nseindia.com/archives/nsccl/volt/' # CMVOLT_09102020.CSV
OHLCBhavCopy = 'https://archives.nseindia.com/products/content/' #sec_bhavdata_full_15102020.csv
OHLCBhavPR = 'https://archives.nseindia.com/archives/equities/bhavcopy/pr/' #PR151020.zip
DailyOHLCFilePath = "ohlc.ftr"

# sec_bhavdata_full_09102020.csv

HolidayList = ['21-Feb-20','10-Mar-20','2-Apr-20','6-Apr-20','10-Apr-20','14-Apr-20','1-May-20','25-May-20','2-Oct-20','16-Nov-20','30-Nov-20','25-Dec-20']
HolidayList = pd.to_datetime(pd.Series(HolidayList), format='%d-%b-%y')

def FindFeather(name, path):
    for root, dirs, files in os.walk(path):
        if name in files:
            return os.path.join(root, name)

def UpdateOHLCBusinessDays():
    #Check Index futures for last update
    SBINOHLC = feather.read_feather('./Datastore/SBIN_ohlc.ftr')
    OHLCStartDate = SBINOHLC.iloc[-1].Date
    OHLCStartDate += datetime.timedelta(days=1)
    LastOHLCDate = datetime.date.today() - datetime.timedelta(days=1)

    ohlcbday = pd.bdate_range(OHLCStartDate, LastOHLCDate) #To be replaced with LastRecordDate, CurrentDate
    ohlcbday = set(ohlcbday).difference(HolidayList)
    print('UpdateOHLCBusinessDays complete ')

def DownloadNewNSEOHLC():        
    #Loop through dates to download NSE OHLC data
    for weekday in ohlcbday: # weekday = YesterdayDate
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
    for weekday in ohlcbday:
        OHLCBhavArg = 'sec_bhavdata_full_' + weekday.strftime("%d%m%Y") + '.csv.ftr'
        if (FindFeather(OHLCBhavArg, './New NSE site/')):
            OHLCBhavdf = feather.read_feather('./New NSE site/'+OHLCBhavArg) #OHLCBhavdf.info()
            TotalNewOHLCdf = TotalNewOHLCdf.append(OHLCBhavdf, ignore_index=True)
        else:
            print('Couldnt find: ' + OHLCBhavArg)
            continue
    
    TotalNewOHLCdf = RefineNewNSEOHLC(TotalNewOHLCdf) #TotalNewOHLCdf.info()
    TotalNewOHLCdf = TotalNewOHLCdf[TotalNewOHLCdf.Series == "EQ"] #Only considering EQ, no debentures(?)
    TotalNewOHLCdf = TotalNewOHLCdf.sort_values(by=['Symbol', 'Date'])
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

    return df

def main():
    UpdateOHLCBusinessDays()
    DownloadNewNSEOHLC()
    UpdatetNSEOHLCData()
    