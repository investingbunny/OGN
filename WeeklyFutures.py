# -*- coding: utf-8 -*-
"""
Created on Sun Jul 19 21:16:37 2020

@author: User
"""
from nsepy import get_history
from nsepy.derivatives import get_expiry_date
from datetime import date
import yfinance as yf
import pandas as pd
import pyarrow
import pyarrow.feather as feather
import matplotlib
import datetime
import time
from dateutil.relativedelta import *
import os

DailyOHLCFilePath = "ohlc.ftr";
IntradayFilePath = "intraday.ftr"
MonthlyFuturesFilePath = "monthly-futures.ftr"
OptionsFilePath = "options.ftr"
WeeklyFuturesFilePath = "weekly-futures.ftr"

Scriplist = ["HDFCBANK","NIFTY"]#, "monthly-", "RELIANCE"]
FuturesIndexList = ["NIFTY","NIFTYIT","BANKNIFTY"]

#Check for file

def FindFeather(name, path):
    for root, dirs, files in os.walk(path):
        if name in files:
            return os.path.join(root, name)

def IndexFuturesUpdate:
    for Scrip in FuturesIndexList:
        Futuresdf = None
        CurrentDate = datetime.date.today()
        CurrentMonth = CurrentDate.month
        CurrentYear = CurrentDate.year
        FuturesFileName = Scrip + '_' + WeeklyFuturesFilePath
        #Read from feather
        if (FindFeather(FuturesFileName, './Datastore')):
            Futuresdf = feather.read_feather('./Datastore/'+FuturesFileName)
            LastDateFutures = ((Futuresdf.tail(1)).iloc[0]['Date'])
            LastDateFutures += datetime.timedelta(days=1) #Added this to start from the next day - TBV
            LastYearFutures = LastDateFutures.year
            LastMonthFutures = LastDateFutures.month
            if(CurrentDate > LastDateFutures):
                #Update Dataframe
                print(FuturesFileName + ' is being updated from' + LastDateFutures.strftime("%Y-%m-%d %H:%M") )
                if(CurrentMonth == LastMonthFutures): #works unless you don't update for a year
                    FreshFutures = get_history(symbol=Scrip, start=LastDateFutures, 
                                        end=CurrentDate,futures=True,
                                        expiry_date=max(get_expiry_date(CurrentYear,CurrentMonth)))
                    Futuresdf = Futuresdf.append(FreshFutures, ignore_index=True)
                    print(FuturesFileName + ' is being updated for same month' + LastDateFutures.strftime("%Y-%m-%d %H:%M"))
                else:
                    FreshFutures = None
                    LastDateFutures = ((Futuresdf.tail(1)).iloc[0]['Date'])
                    LastDateFutures += datetime.timedelta(days=1)
                    while True:
                        LastYearFutures = LastDateFutures.year
                        LastMonthFutures = LastDateFutures.month
                        FreshFutures = get_history(symbol=Scrip, start=LastDateFutures, 
                                        end=LastDateFutures + relativedelta(day=31),futures=True,
                                        expiry_date=max(get_expiry_date(LastYearFutures,LastMonthFutures)))
                        FreshFutures.reset_index(level=0, inplace=True)
                        Futuresdf = Futuresdf.append(FreshFutures, ignore_index=True)
                        print(FuturesFileName + ' is being updated for '
                              + LastDateFutures.strftime("%Y-%m-%d %H:%M"))
                        LastDateFutures += relativedelta(months=1)
                        LastDateFutures.replace(day=1)
                        if(LastDateFutures > CurrentDate):
                            break
            else:
                print(FuturesFileName + 'is upto date')
        else:
            #Create Dataframe for new Scrip added
            FuturesStartDate = date(2005,1,1)
            print(FuturesFileName + ' is being created from' + FuturesStartDate.strftime("%Y-%m-%d %H:%M")) 
            Futuresdf = get_history(symbol=Scrip, start=FuturesStartDate, 
                                        end=FuturesStartDate + relativedelta(day=31),futures=True,
                                        expiry_date=max(get_expiry_date(FuturesStartDate.year,FuturesStartDate.month)))
            # Todo : Add null check here
            Futuresdf.reset_index(level=0, inplace=True) # Required for any new data fetch
            LastDateFutures = ((Futuresdf.tail(1)).iloc[0]['Date'])
            LastDateFutures += relativedelta(months=1)
            LastDateFutures = LastDateFutures.replace(day = 1) #Start from the month beginning
            LastYearFutures = LastDateFutures.year
            LastMonthFutures = LastDateFutures.month
            #now to fill it up - TBD - can be done recursively            
            if(CurrentDate > LastDateFutures):
                #Update Dataframe
                print(FuturesFileName + ' is being updated from ' + LastDateFutures.strftime("%Y-%m-%d %H:%M"))
                while True:
                    FreshFutures = None
                    FreshFutures = get_history(symbol=Scrip, start=LastDateFutures, 
                                    end=LastDateFutures+ relativedelta(day=31),futures=True,
                                    expiry_date=max(get_expiry_date(LastYearFutures,LastMonthFutures)))
                    FreshFutures.reset_index(level=0, inplace=True)
                    Futuresdf = Futuresdf.append(FreshFutures, ignore_index=True)
                    print(FuturesFileName + ' is being updated for ' + LastDateFutures.strftime("%Y-%m-%d %H:%M"))
                    LastDateFutures += relativedelta(months=1)
                    LastDateFutures = LastDateFutures.replace(day = 1)
                    LastYearFutures = LastDateFutures.year
                    LastMonthFutures = LastDateFutures.month
                    if(LastDateFutures > CurrentDate):
                        break
        
        #Update Feather        
        feather.write_feather(Futuresdf, './Datastore/'+ FuturesFileName)