# -*- coding: utf-8 -*-
"""
Getting data Using yfinance library

@author: Mayank Rasu (http://rasuquant.com/wp/)
"""

import yfinance as yf
import datetime
import time
from dateutil.relativedelta import *

YahooScriplist = ["RELIANCE.NS", "HDFCBANK.NS", "TATASTEEL.NS", "TCS.NS", "TATAMOTORS.NS","TATAPOWER.NS","INDIGO.NS"]

# get ohlcv data for any ticker by period.
data = yf.download("MSFT", period='1mo', interval="5m")

# get ohlcv data for any ticker by start date and end date
CurrentDate = datetime.date.today()
WeekStartDate = CurrentDate + relativedelta(months=-1)
WeekStartDate += datetime.timedelta(days=1) #One time adjustment
PlusOneWeek = WeekStartDate + datetime.timedelta(weeks=+1)

data = yf.download("RELIANCE.NS", start=WeekStartDate.strftime("%Y-%m-%d"), 
                   end=PlusOneWeek.strftime("%Y-%m-%d"), interval="1m")
WeekStartDate = PlusOneWeek
PlusOneWeek = WeekStartDate + datetime.timedelta(weeks=+1)


                data.reset_index(level=0, inplace=True)
                new = data.append(new, ignore_index=True)


#Append
WeekStartDate = ((data.tail(1)).iloc[0]['Datetime'])
WeekStartDate += datetime.timedelta(days=1) 
PlusOneWeek = WeekStartDate + datetime.timedelta(weeks=+1)
new = yf.download("RELIANCE.NS", start=WeekStartDate.strftime("%Y-%m-%d"), 
                   end=PlusOneWeek.strftime("%Y-%m-%d"), interval="1m")
new.reset_index(level=0, inplace=True)







# get intraday data for fany ticker by period.
data = yf.download("RELIANCE.NS", period='1m', interval="1m")
data.reset_index(level=0, inplace=True)
LastDateIntradaydf = ((data.tail(1)).iloc[0]['Datetime'])


data = yf.download("RELIANCE.NS", start="2010-06-23", end="2010-07-23", interval="5m")