# -*- coding: utf-8 -*-
"""
Created on Sat Aug 22 19:03:16 2020

@author: User
"""

import numpy as np
import pandas as pd
from stocktrends import Renko
from stocktrends import indicators
import statsmodels.api as sm
import copy
import pyarrow
import pyarrow.feather as feather
import os
import matplotlib.pyplot as plt
NSEFnOList = ["BANKNIFTY","NIFTY","AXISBANK"]
# ,"ADANIENT","ADANIPORTS","AMARAJABAT","AMBUJACEM","APOLLOHOSP",
#               "APOLLOTYRE","ASHOKLEY","ASIANPAINT","AUROPHARMA","AXISBANK","BAJAJ-AUTO","BAJAJFINSV",
#               "BAJFINANCE","BALKRISIND","BANDHANBNK","BANKBARODA","BATAINDIA","BEL","BERGEPAINT","BHARATFORG",
#               "BHARTIARTL","BHEL","BIOCON","BOSCHLTD","BPCL","BRITANNIA","CADILAHC","CANBK","CENTURYTEX",
#               "CHOLAFIN","CIPLA","COALINDIA","COLPAL","CONCOR","CUMMINSIND","DABUR","DIVISLAB","DLF",
#               "DRREDDY","EICHERMOT","EQUITAS","ESCORTS","EXIDEIND","FEDERALBNK","GAIL","GLENMARK","GMRINFRA",
#               "GODREJCP","GODREJPROP","GRASIM","HAVELLS","HCLTECH","HDFC","HDFCBANK","HDFCLIFE","HEROMOTOCO",
#                "HINDALCO","HINDPETRO","HINDUNILVR","IBULHSGFIN","ICICIBANK","ICICIPRULI","IDEA","IDFCFIRSTB",
#                "IGL","INDIGO","INDUSINDBK","INFRATEL","INFY","IOC","ITC","JINDALSTEL","JSWSTEEL","JUBLFOOD",
#                "JUSTDIAL","KOTAKBANK","L&TFH","LICHSGFIN","LT","LUPIN","M&M","M&MFIN","MANAPPURAM","MARICO",
#               "MARUTI","MCDOWELL-N","MFSL","MGL","MINDTREE","MOTHERSUMI","MRF","MUTHOOTFIN","NATIONALUM",
#               "NAUKRI","NCC","NESTLEIND","NIITTECH","NMDC","NTPC","ONGC","PAGEIND","PEL","PETRONET","PFC",
#               "PIDILITIND","PNB","POWERGRID","PVR","RAMCOCEM","RBLBANK","RECLTD","RELIANCE","SAIL","SBILIFE",
#               "SBIN","SHREECEM","SIEMENS","SRF","SRTRANSFIN","SUNPHARMA","SUNTV","TATACHEM","TATACONSUM",
#               "TATAMOTORS","TATAPOWER","TATASTEEL","TCS","TECHM","TITAN","TORNTPHARM","TORNTPOWER","TVSMOTOR",
#               "UBL","UJJIVAN","ULTRACEMCO","UPL","VEDL","VOLTAS","WIPRO","ZEEL"]

MonthlyOptionsFilePath = "monthly-options.ftr"

#################################Global Variables
#Creating strike List
strike = []
expiry = []
date = []

def FindFeather(name, path):
    for root, dirs, files in os.walk(path):
        if name in files:
            return os.path.join(root, name)

        
def call_otm(df, date):
	copy_df = df
	copy_df = copy_df[copy_df['Option type'] == 'CE']
	copy_df = copy_df[copy_df['Date'] == date]
	copy_df.sort_values('Strike Price', axis=0, ascending = False, inplace = True)
	copy_df['cumsum_c'] = pd.Series.cumsum(copy_df['Open Int'])
	return copy_df        
        
def put_otm(df, date):
	copy_df = df
	copy_df = copy_df[copy_df['Option type'] == 'PE']
	copy_df = copy_df[copy_df['Date'] == date]
	copy_df.sort_values('Strike Price', axis=0, ascending = True, inplace = True)
	copy_df['cumsum_p'] = pd.Series.cumsum(copy_df['Open Int'])
	return copy_df       
        
# (5) Find strike with maximum cumulative options OTM.
def max_pain_strike(call_sums, put_sums):
	cumulative = pd.merge(call_sums,put_sums, on = 'Strike Price', how = 'inner') #Merge or join?
	cumulative['cp_sum'] = cumulative['cumsum_c'] + cumulative['cumsum_p']
	mpp = cumulative['Strike Price'][cumulative['cp_sum'].idxmax()]
	return mpp    

def GetMaxPain(Scrip,FirstDate): #Depth is considered in months to see historical expiry and pain
    # for Scrip in NSEFnOList:
    # Scrip = 'RELIANCE'
    OptionsFileName = Scrip + '_' + MonthlyOptionsFilePath
    # FromWhen = 500 #How much back in time. 1 is default minimum
    # MLdf = Tempdf.tail(1)

    #Read from feather
    if (FindFeather(OptionsFileName, './Datastore')):
        ReadOptionsdf = feather.read_feather('./Datastore/'+OptionsFileName)
        OptionsSlice = ReadOptionsdf.copy()

        # MLdf = ReadOptionsdf[(ReadOptionsdf['Date'] ==  SelectDate)]
        # ExpiryDate = MLdf['Expiry'].values[0] #The month in focus
        # OptionsSlice = ReadOptionsdf[(ReadOptionsdf['Expiry'] ==  ExpiryDate)]
        d = FirstDate - timedelta(days=1)
        OptionsSlice[OptionsSlice.Date > d]
        
        date = []
        #Adding values to list
        date = list(OptionsSlice['Date'])
        #Removing duplicates in list
        date = list(dict.fromkeys(date))
        #Sorting list
        date.sort()
        
        for Focusdate in date:
            call_sums = call_otm(OptionsSlice, Focusdate)
            put_sums = put_otm(OptionsSlice, Focusdate)
            PCR = put_sums['Open Int'].sum()/call_sums['Open Int'].sum()
            MP = max_pain_strike(call_sums, put_sums)
            MaxPaindf['Date'] = Focusdate
            MaxPaindf['MaxPain'] = MP
            MaxPaindf['Expiry'] = ExpiryDate
            MaxPaindf['PCR'] = PCR
            # print(Scrip,ExpiryDate,Focusdate,MP,PCR)
        return MaxPaindf
    

Mpdf = GetMaxPain(ScripName)
