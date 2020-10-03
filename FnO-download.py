# -*- coding: utf-8 -*-
"""
Created on Sat Oct  3 17:35:42 2020
This file is intended to download F&O data from the new NSE website.
The file is a consolidated daily report which has to be dissected.
@author: User
"""
import requests
from zipfile import ZipFile 

FnOStartDate = date(2020,9,1)
FnOReport = 'https://archives.nseindia.com/archives/fo/mkt/'
FnOVolatility = 'https://archives.nseindia.com/archives/nsccl/volt/'

# FnOReportArg #fo30092020.zip
# FnOVolatilityArg #FOVOLT_29092020.csv

def DownloadNewNSEdata():
    bday = pd.bdate_range("2020-09-01", "2020-10-03") #To be replaced with LastRecordDate, CurrentDate
    #Loop through dates to download NSE data
    for weekday in bday:
        # print(weekday.strftime("%d%m%Y"))
        FnOReportArg = 'fo' + weekday.strftime("%d%m%Y") + '.zip'
        FnOReportURL = FnOReport + FnOReportArg
        try:
            r = requests.get(FnOReportURL, allow_redirects=True) #Download FnO Market report for 'weekday'
            open(FnOReportArg, 'wb').write(r.content)
        except:
            print('Couldnt download:'+ FnOReportURL)
        
        FnOVolatilityArg = 'FOVOLT_' + weekday.strftime("%d%m%Y") + '.csv'
        FnOVolatilityURL = FnOReport + FnOReportArg
        try:
            r = requests.get(FnOVolatilityURL, allow_redirects=True) #Download FnO Volatility report for 'weekday'
            open(FnOVolatilityArg, 'wb').write(r.content)
        except:
            print('Couldnt download:'+ FnOVolatilityURL)    

def ExtractNSEFnOData():
    # bday = pd.bdate_range("2020-09-01", "2020-10-03") #To be replaced with LastRecordDate, CurrentDate
    # FnOReportArg = 'fo' + weekday.strftime("%d%m%Y") + '.zip'
    FnOReportArg = 'fo01102020'

    zf = ZipFile('New NSE site/'+FnOReportArg+'.zip') 
    CSVdf = pd.read_csv(zf.open(FnOReportArg+'.csv'), parse_dates=[2], dayfirst=True)
    CSVdf = CSVdf.rename(columns=lambda x: x.strip())
    NewFuturesdf = RefineNewNSEFutures(CSVdf)


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
