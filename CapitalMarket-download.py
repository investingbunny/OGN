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

# OHLCStartDate = date(2020,9,1)
OHLCReport = 'https://archives.nseindia.com/products/content/'
OHLCVolatility = 'https://archives.nseindia.com/archives/nsccl/volt/'
DailyOHLCFilePath = "ohlc.ftr"

# sec_bhavdata_full_09102020.csv
# CMVOLT_09102020.CSV
HolidayList = ['21-Feb-20','10-Mar-20','2-Apr-20','6-Apr-20','10-Apr-20','14-Apr-20','1-May-20','25-May-20','2-Oct-20','16-Nov-20','30-Nov-20','25-Dec-20']
HolidayList = pd.to_datetime(pd.Series(HolidayList), format='%d-%b-%y')

def FindFeather(name, path):
    for root, dirs, files in os.walk(path):
        if name in files:
            return os.path.join(root, name)

def UpdateBusinessDays():
    #Check Index futures for last update
    NiftyOHLC = feather.read_feather('./Datastore/NIFTY_ohlc.ftr')
    OHLCStartDate = NiftyOHLC.iloc[-1].Date
    OHLCStartDate += datetime.timedelta(days=1)
    YesterdayDate = datetime.date.today()# - datetime.timedelta(days=1)

    bday = pd.bdate_range(OHLCStartDate, YesterdayDate) #To be replaced with LastRecordDate, CurrentDate
    bday = set(bday).difference(HolidayList)
    print('UpdateBusinessDays complete ')

def DownloadNewNSEOHLC():        
    #Loop through dates to download NSE OHLC data
    for weekday in bday:
        print('DownloadNewNSEOHLC for'+ weekday.strftime("%Y-%m-%d"))
        #OHLC Market report download # sec_bhavdata_full_09102020.csv
        OHLCReportArg = 'sec_bhavdata_full_' + weekday.strftime("%d%m%Y") + '.csv'
        OHLCReportURL = OHLCReport + OHLCReportArg
        try:
            r = requests.get(OHLCReportURL, allow_redirects=True) #Download OHLC Market report for 'weekday'
            if r.ok:
                data = r.content.decode('utf8')
                OHLCdf = pd.read_csv(io.StringIO(data))
                OHLCdf = OHLCdf.rename(columns=lambda x: x.strip())
                OHLCdf = OHLCdf.applymap(lambda x: x.strip() if isinstance(x, str) else x)
        except:
            print('Couldnt download:'+ OHLCVolatilityURL)    
            
        if not OHLCdf.empty:
            feather.write_feather(OHLCdf, './New NSE site/'+OHLCReportArg+'.ftr')

            
        #OHLC Volatility report download
        OHLCVolatilityArg = 'CMVOLT_' + weekday.strftime("%d%m%Y") + '.CSV'
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

def UpdatetNSEOHLCData():
    TotalNewOHLCdf = pd.DataFrame()
    for weekday in bday:
        OHLCReportArg = 'fo' + weekday.strftime("%d%m%Y")
        OHLCSettleArg = 'FOSett_prce_' + weekday.strftime("%d%m%Y") + '.csv.ftr'
    
        zf = ZipFile('New NSE site/'+OHLCReportArg + '.zip') 
        CSVdf = pd.read_csv(zf.open(OHLCReportArg+'.csv'), parse_dates=[2], dayfirst=True)
        CSVdf = CSVdf.rename(columns=lambda x: x.strip())
        CSVdf = CSVdf.applymap(lambda x: x.strip() if isinstance(x, str) else x)
        NewOHLCdf = RefineNewNSEOHLC(CSVdf)
        
        if (FindFeather(OHLCSettleArg, './New NSE site/')):
            Settledf = feather.read_feather('./New NSE site/'+OHLCSettleArg) #Volatilitydf.info()
            NewOHLCdf = pd.merge(NewOHLCdf, Settledf, how="inner", on=["Symbol","Expiry","Instrument"])
        else:
            print('Couldnt find settlement info for '+ OHLCSettleArg)
        
        TotalNewOHLCdf = TotalNewOHLCdf.append(NewOHLCdf, ignore_index=True)
    
    TotalNewOHLCdf = TotalNewOHLCdf.sort_values(by=['Symbol', 'Date'])
    OHLCSymbollist = []
    #Adding values to list
    OHLCSymbollist = list(TotalNewOHLCdf['Symbol'])
    #Removing duplicates in list
    OHLCSymbollist = list(dict.fromkeys(OHLCSymbollist))
    
    #Update the old OHLC file
    for sym in OHLCSymbollist:
        
        OHLCFileName = sym + '_' + FullOHLCFilePath
        #Read from feather
        if (FindFeather(OHLCFileName, './Datastore/')):
            OldOHLCdf = feather.read_feather('./Datastore/'+OHLCFileName)
            # OldOHLCdf.drop("index", axis=1, inplace=True) #DO NOT ENABLE!!!
            # OldOHLCdf = OldOHLCdf[OldOHLCdf.Date < OHLCStartDate] #DO NOT ENABLE!!!
            print('Updating OHLC for '+ sym)
            Mergedf = OldOHLCdf.append(TotalNewOHLCdf[TotalNewOHLCdf["Symbol"] == sym], ignore_index = True)            
        else: #A new symbol has been added, create a feather for it
            print('Creating new OHLC DB for '+ sym)
            Mergedf = TotalNewOHLCdf[TotalNewOHLCdf["Symbol"] == sym]#, ignore_index = True)
            Mergedf.reset_index(level=0, inplace=True)
            Mergedf.drop("index", axis=1, inplace=True)
            
        if not Mergedf.empty:
            feather.write_feather(Mergedf, './Datastore/'+OHLCFileName)

def RefineNewNSEOHLC(DF):
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

def main():
    UpdateBusinessDays()
    DownloadNewNSEOHLC()
    UpdatetNSEOHLCData()
    