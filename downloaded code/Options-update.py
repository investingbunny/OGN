# -*- coding: utf-8 -*-
"""
Created on Thu Jul 23 19:14:25 2020

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

Scriplist = ["RELIANCE", "HDFCBANK", "TATASTEEL", "TCS", "TATAMOTORS","TATAPOWER","INDIGO","IDEA","OIL","AUROPHARMA","CIPLA"]
YahooScriplist = ["RELIANCE.NS", "HDFCBANK.NS", "TATASTEEL.NS", "TCS.NS", "TATAMOTORS.NS","TATAPOWER.NS","INDIGO.NS","IDEA.NS","OIL.NS","AUROPHARMA.NS","CIPLA.NS"]
FuturesIndexList = ["NIFTY","NIFTYIT","BANKNIFTY"]
#Scrip = "RELIANCE.NS"
#Check for file

def FindFeather(name, path):
    for root, dirs, files in os.walk(path):
        if name in files:
            return os.path.join(root, name)

def MonthlyFuturesUpdate():
    for Scrip in Scriplist:
        Futuresdf = None
        CurrentDate = datetime.date.today()
        CurrentMonth = CurrentDate.month
        CurrentYear = CurrentDate.year
        FuturesFileName = Scrip + '_' + MonthlyFuturesFilePath
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
                    FreshFutures.reset_index(level=0, inplace=True)
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
            LastDateFutures = FuturesStartDate
            print(FuturesFileName + ' is being created from' + FuturesStartDate.strftime("%Y-%m-%d %H:%M")) 
            Futuresdf = get_history(symbol=Scrip, start=FuturesStartDate, 
                                        end=FuturesStartDate + relativedelta(day=31),futures=True,
                                        expiry_date=max(get_expiry_date(FuturesStartDate.year,FuturesStartDate.month)))
            Futuresdf.reset_index(level=0, inplace=True) # Required for any new data fetch
            
            if not Futuresdf.empty:
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
        
        
        
        
        
import pandas as pd
import requests
from datetime import datetime

# Colunn at which strike price is listed in NSE option chain table
strike_price_column_index = 11

# Encapuslate NSE option data and function
class OptionChain:

    # static variable to hold current running expiry date
    expiry = ''

    # Common Utility to find maxinum value in the column, its index and then return the strike price with respect to index value
    def find_max_strike_price(self, df, option_type, column_name):

        # Covert "-" as 0 so that all data can be treated as integer
        temp_df = df[option_type].replace("-", "0")
        # Delete the last row which will have summation of all the data
        temp_df = temp_df[:-1]
        # Set the specific column as integer (by default it is string)
        temp_df[column_name]=temp_df[column_name].astype(int)
        # Dind the index value where the max value exists
        max_at_index = temp_df[column_name].idxmax()
        # Return the strike price which is available in the index value
        return(int(df.iloc[max_at_index, strike_price_column_index]))

    # Get strike prices where max OI /change in OI for CE and PE
    def get_max_OI_data(self, symbol, expiry):

        url ="https://www.nseindia.com/live_market/dynaContent/live_watch/option_chain/optionKeys.jsp?symbol=" + symbol + "&date" + expiry
        header = {
          "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/50.0.2661.75 Safari/537.36",
          "X-Requested-With": "XMLHttpRequest"
        }

        # Pull NSE option chain
        r = requests.get(url, headers=header)
        # Convert html page as Table and read the first table which has option data
        df = pd.read_html(r.text)[1]

        # Get all max OI data and store to local object variables
        self.max_high_oi_ce = self.find_max_strike_price(df, "CALLS", "OI")
        self.max_change_oi_ce = self.find_max_strike_price(df, "CALLS", "Chng in OI")
        self.max_high_oi_pe = self.find_max_strike_price(df, "PUTS", "OI")
        self.max_change_oi_pe = self.find_max_strike_price(df, "PUTS", "Chng in OI")

    # Constructor for OptionChain which will run for every script like Nifty and Banknifty
    def __init__(self, symbol):

        # Store the symbol
        self.symbol = symbol
        # Find out the expiry for which we need to pull the details

        if not OptionChain.expiry: # If expiry is not yet found
            # List the expiry details and read the first expiry
            base_url = 'https://www.capitalzone.in/test.php?symbol=' + symbol
            page_output = str(requests.get(base_url).content)
            expiry_list = page_output.split(",")
            OptionChain.expiry = expiry_list[0].split("\"")[1]
            expirydate = datetime.strptime(OptionChain.expiry, '%d%b%Y').date()
            todaydate = datetime.today().date()

            # If today is greater than expiry, then it is expired. Choose the next expiry in the list
            if todaydate > expirydate:
                NSEOption.expiry = expiry_list[1].split("\"")[1]

        # Form the actual URL from which we can pull PCR and max pain
        base_url = 'https://www.capitalzone.in/test.php?symbol=' + symbol + "&expiry=" + OptionChain.expiry

        # Load the page and sent to HTML parse
        page_output = str(requests.get(base_url).content)
        # Locate the string where max pain string is available
        loc = page_output.find("\"max_pain\"")
        data = page_output[loc:].split("\"")
        # Get max pain and convert from float to integer
        self.max_pain = int(float(data[3]))
        # Get max pain and convert from string to float
        self.pcr = float(data[11])
        self.get_max_OI_data(symbol, OptionChain.expiry)

    # Tracing utility to display elements of this class if needed (For debugging purpose)
    def display_all(self):

        print(self.max_pain, self.pcr);