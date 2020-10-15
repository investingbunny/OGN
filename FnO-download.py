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
import io
import os
import pyarrow
import pyarrow.feather as feather
from functools import reduce

FnOStartDate = date(2020,9,1)
FnOReport = 'https://archives.nseindia.com/archives/fo/mkt/'
FnOVolatility = 'https://archives.nseindia.com/archives/nsccl/volt/'
FnOSettlement = 'https://archives.nseindia.com/archives/nsccl/sett/'
FnOBhavcopy = 'https://archives.nseindia.com/content/historical/DERIVATIVES/'
MonthlyFuturesFilePath = "monthly-futures.ftr"
FullFuturesFilePath = "full-futures.ftr"
MonthlyOptionsFilePath = "monthly-options.ftr"

# FnOBhavCopy = 'https://archives.nseindia.com/content/historical/DERIVATIVES/'#2020/OCT/fo01OCT2020bhav.csv.zip

# FnOReportArg #fo30092020.zip
# FnOVolatilityArg #FOVOLT_29092020.csv
HolidayList = ['21-Feb-20','10-Mar-20','2-Apr-20','6-Apr-20','10-Apr-20','14-Apr-20','1-May-20','25-May-20','2-Oct-20','16-Nov-20','30-Nov-20','25-Dec-20']
HolidayList = pd.to_datetime(pd.Series(HolidayList), format='%d-%b-%y')

def FindFeather(name, path):
    for root, dirs, files in os.walk(path):
        if name in files:
            return os.path.join(root, name)

def UpdateBusinessDays():
    #Check Index futures for last update
    NiftyFullFutures = feather.read_feather('./Datastore/NIFTY_full-futures.ftr')
    FuturesStartDate = NiftyFullFutures.iloc[-1].Date
    FuturesStartDate += datetime.timedelta(days=1)
    YesterdayDate = datetime.date.today() - datetime.timedelta(days=1)

    bday = pd.bdate_range(FnOStartDate, YesterdayDate) #To be replaced with LastRecordDate, CurrentDate
    bday = set(bday).difference(HolidayList)
    print('UpdateBusinessDays complete ')

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
            r = requests.get(FnOBhavURL, allow_redirects=True) #Download FnO Market report for 'weekday'
            open('./New NSE site/'+FnOBhavArg, 'wb').write(r.content)
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
        FnOVolatilityArg = 'FOVOLT_' + weekday.strftime("%d%m%Y") + '.csv'
        FnOVolatilityURL = FnOVolatility + FnOVolatilityArg
        try:
            r = requests.get(FnOVolatilityURL, allow_redirects=True) #Download FnO Volatility report for 'weekday'
            if r.ok:
                data = r.content.decode('utf8')
                Voldf = pd.read_csv(io.StringIO(data))
                Voldf = Voldf.rename(columns=lambda x: x.strip())
                Voldf = Voldf.applymap(lambda x: x.strip() if isinstance(x, str) else x)
        except:
            print('Couldnt download:'+ FnOVolatilityURL)    
            
        if not Voldf.empty:
            feather.write_feather(Voldf, './New NSE site/'+FnOVolatilityArg+'.ftr')
            
        #FnO Settlement Report download    
        FnOSettleArg = 'FOSett_prce_' + weekday.strftime("%d%m%Y") + '.csv'
        FnOSettlementURL = FnOSettlement + FnOSettleArg
        try:
            r = requests.get(FnOSettlementURL, allow_redirects=True) #Download FnO Volatility report for 'weekday'
            if r.ok:
                data = r.content.decode('utf8')
                Setdf = pd.read_csv(io.StringIO(data))
                Setdf = Setdf.rename(columns=lambda x: x.strip())
                Setdf = Setdf.applymap(lambda x: x.strip() if isinstance(x, str) else x)
                Setdf = RefineNewNSEFutures(Setdf)
        except:
            print('Couldnt download:'+ FnOSettlementURL)    
            
        if not Setdf.empty:
            feather.write_feather(Setdf, './New NSE site/'+FnOSettleArg+'.ftr')

def UpdatetNSEFuturesData():
    TotalNewFuturesdf = pd.DataFrame()
    for weekday in bday:
        FnOReportArg = 'fo' + weekday.strftime("%d%m%Y")
        FnOSettleArg = 'FOSett_prce_' + weekday.strftime("%d%m%Y") + '.csv.ftr'
    
        zf = ZipFile('New NSE site/'+FnOReportArg + '.zip') 
        CSVdf = pd.read_csv(zf.open(FnOReportArg+'.csv'), parse_dates=[2], dayfirst=True)
        CSVdf = CSVdf.rename(columns=lambda x: x.strip())
        CSVdf = CSVdf.applymap(lambda x: x.strip() if isinstance(x, str) else x)
        NewFuturesdf = RefineNewNSEFutures(CSVdf)
        
        if (FindFeather(FnOSettleArg, './New NSE site/')):
            Settledf = feather.read_feather('./New NSE site/'+FnOSettleArg) #Volatilitydf.info()
            NewFuturesdf = pd.merge(NewFuturesdf, Settledf, how="inner", on=["Symbol","Expiry","Instrument"])
        else:
            print('Couldnt find settlement info for '+ FnOSettleArg)
        
        TotalNewFuturesdf = TotalNewFuturesdf.append(NewFuturesdf, ignore_index=True)
    
    TotalNewFuturesdf = TotalNewFuturesdf.sort_values(by=['Symbol', 'Date'])
    FnOSymbollist = []
    #Adding values to list
    FnOSymbollist = list(TotalNewFuturesdf['Symbol'])
    #Removing duplicates in list
    FnOSymbollist = list(dict.fromkeys(FnOSymbollist))
    
    #Update the old Futures file
    for sym in FnOSymbollist:
        
        FuturesFileName = sym + '_' + FullFuturesFilePath
        #Read from feather
        if (FindFeather(FuturesFileName, './Datastore/')):
            OldFuturesdf = feather.read_feather('./Datastore/'+FuturesFileName)
            # OldFuturesdf.drop("index", axis=1, inplace=True) #DO NOT ENABLE!!!
            # OldFuturesdf = OldFuturesdf[OldFuturesdf.Date < FnOStartDate] #DO NOT ENABLE!!!
            print('Updating Futures for '+ sym)
            Mergedf = OldFuturesdf.append(TotalNewFuturesdf[TotalNewFuturesdf["Symbol"] == sym], ignore_index = True)            
        else: #A new symbol has been added, create a feather for it
            print('Creating new Futures DB for '+ sym)
            Mergedf = TotalNewFuturesdf[TotalNewFuturesdf["Symbol"] == sym]#, ignore_index = True)
            Mergedf.reset_index(level=0, inplace=True)
            Mergedf.drop("index", axis=1, inplace=True)
            
        if not Mergedf.empty:
            feather.write_feather(Mergedf, './Datastore/'+FuturesFileName)
            
def UpdatetNSEOptionsData():
    TotalNewOptionsdf = pd.DataFrame()
    for weekday in bday:  # weekday = YesterdayDate
        FnOBhavArg = 'fo' + weekday.strftime("%d%b%Y").upper() + 'bhav'
        print('Processing '+FnOBhavArg)
        zf = ZipFile('New NSE site/'+FnOBhavArg+ '.csv.zip')  #fo12OCT2020bhav.csv.zip
        CSVdf = pd.read_csv(zf.open(FnOBhavArg+'.csv'), parse_dates=[2], dayfirst=True) #fo12OCT2020bhav
        CSVdf = CSVdf.rename(columns=lambda x: x.strip())
        CSVdf = CSVdf.applymap(lambda x: x.strip() if isinstance(x, str) else x)
        NewOptionsdf = RefineNewNSEOptions(CSVdf)
        NewOptionsdf = NewOptionsdf[(NewOptionsdf["Instrument"] == 'OPTIDX') | (NewOptionsdf["Instrument"] == 'OPTSTK')]
        
        TotalNewOptionsdf = TotalNewOptionsdf.append(NewOptionsdf, ignore_index=True)
    
    TotalNewOptionsdf = TotalNewOptionsdf.sort_values(by=['Symbol', 'Date'])
    FnOSymbollist = []
    #Adding values to list
    FnOSymbollist = list(TotalNewOptionsdf['Symbol'])
    #Removing duplicates in list
    FnOSymbollist = list(dict.fromkeys(FnOSymbollist))
    
    #Update the old Options file
    for sym in FnOSymbollist:
        OptionsFileName = sym + '_' + MonthlyOptionsFilePath
        #Read from feather
        if (FindFeather(OptionsFileName, './Datastore/')):
            OldOptionsdf = feather.read_feather('./Datastore/'+OptionsFileName)
            OldOptionsdf = OldOptionsdf[OldOptionsdf.Date < FnOStartDate] #DO NOT ENABLE!!!
            print('Updating Options for '+ sym)
            Mergedf = OldOptionsdf.append(TotalNewOptionsdf[TotalNewOptionsdf["Symbol"] == sym], ignore_index = True)            
        else: #A new symbol has been added, create a feather for it
            print('Creating new Options DB for '+ sym)
            Mergedf = TotalNewOptionsdf[TotalNewOptionsdf["Symbol"] == sym]
            # Mergedf.reset_index(level=0, inplace=True)
            # Mergedf.drop("index", axis=1, inplace=True)
            
        if not Mergedf.empty:
            feather.write_feather(Mergedf, './Datastore/'+OptionsFileName)

def RefineNewNSEOptions(DF):
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
        
        #CSVdf.info() Unnamed: 15
    if 'Unnamed: 15' in df.columns:
        df.drop("Unnamed: 15", axis=1, inplace=True)
        
    return df

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

def main():
    UpdateBusinessDays()
    DownloadNewNSEFnO()
    UpdatetNSEFuturesData()
    UpdatetNSEOptionsData()
    