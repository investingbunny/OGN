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
from datetime import date
from datetime import datetime
import io
import os
import pyarrow
import pyarrow.feather as feather
from functools import reduce

FnOStartDate = date(2020,9,1)
FnOReport = 'https://archives.nseindia.com/archives/fo/mkt/'
FnOVolatility = 'https://archives.nseindia.com/archives/nsccl/volt/'
# FnOBhavCopy = 'https://archives.nseindia.com/content/historical/DERIVATIVES/'#2020/OCT/fo01OCT2020bhav.csv.zip

# FnOReportArg #fo30092020.zip
# FnOVolatilityArg #FOVOLT_29092020.csv
HolidayList = ['21-Feb-20','10-Mar-20','2-Apr-20','6-Apr-20','10-Apr-20','14-Apr-20','1-May-20','25-May-20','2-Oct-20','16-Nov-20','30-Nov-20','25-Dec-20']
HolidayList = pd.to_datetime(pd.Series(HolidayList), format='%d-%b-%y')
bday = pd.bdate_range("2020-09-01", "2020-10-04") #To be replaced with LastRecordDate, CurrentDate
bday = set(bday).difference(HolidayList)

def FindFeather(name, path):
    for root, dirs, files in os.walk(path):
        if name in files:
            return os.path.join(root, name)

def DownloadNewNSEFnO():

    #Loop through dates to download NSE data
    for weekday in bday:
        print(weekday.strftime("%d%m%Y"))
        FnOReportArg = 'fo' + weekday.strftime("%d%m%Y") + '.zip'
        FnOReportURL = FnOReport + FnOReportArg
        try:
            r = requests.get(FnOReportURL, allow_redirects=True) #Download FnO Market report for 'weekday'
            open(FnOReportArg, 'wb').write(r.content)
        except:
            print('Couldnt download:'+ FnOReportURL)

def DownloadNewNSEVolatility():        
    #Loop through dates to download NSE data
    for weekday in bday:
        FnOVolatilityArg = 'FOVOLT_' + weekday.strftime("%d%m%Y") + '.csv'
        FnOVolatilityURL = FnOVolatility + FnOVolatilityArg
        try:
            r = requests.get(FnOVolatilityURL, allow_redirects=True) #Download FnO Volatility report for 'weekday'
            if r.ok:
                data = r.content.decode('utf8')
                Voldf = pd.read_csv(io.StringIO(data))
                Voldf = Voldf.rename(columns=lambda x: x.strip())
        except:
            print('Couldnt download:'+ FnOVolatilityURL)    
            
        if not Voldf.empty:
            feather.write_feather(Voldf, './New NSE site/'+FnOVolatilityArg+'.ftr')
            
def ExtractNSEFnOData():
    # bday = pd.bdate_range("2020-09-01", "2020-10-03") #To be replaced with LastRecordDate, CurrentDate
    # FnOReportArg = 'fo' + weekday.strftime("%d%m%Y") + '.zip'
    FnOReportArg = 'fo01102020'
    FnOVolatilityArg = 'FOVOLT_01102020.csv.ftr'

    zf = ZipFile('New NSE site/'+FnOReportArg+'.zip') 
    CSVdf = pd.read_csv(zf.open(FnOReportArg+'.csv'), parse_dates=[2], dayfirst=True)
    CSVdf = CSVdf.rename(columns=lambda x: x.strip())
    NewFuturesdf = RefineNewNSEFutures(CSVdf)

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
        Futdf = Futdf.rename(columns=lambda x: x.strip())
        Futdf = Futdf.applymap(lambda x: x.strip() if isinstance(x, str) else x)
        Volatilitydf = pd.merge(Futdf, Volatilitydf, how="outer", on=["Symbol"])
    
def RefineNewNSEFutures(DF):
    # df.info()
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
        df.rename(columns={'CLOSE_PRICE': 'Settle Price'}, inplace=True)

    if 'OPEN_INT*' in df.columns:
        df.rename(columns={'OPEN_INT*': 'Open Interest'}, inplace=True)

    if 'TRD_VAL' in df.columns:
        df.rename(columns={'TRD_VAL': 'Turnover'}, inplace=True)                  
        
    if 'NO_OF_CONT' in df.columns:
        df.rename(columns={'NO_OF_CONT': 'Number of Contracts'}, inplace=True)      

    return df
