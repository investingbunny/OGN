from nsepy import get_history
from datetime import date
import yfinance as yf
import pandas as pd
import pyarrow
import pyarrow.feather as feather
import matplotlib

#pingInfoFilePath = "./serverpings.ftr";

data = get_history(symbol="HDFC", start=date(2015,1,1), end=date(2015,1,31))
data[['Close']].plot()

sbin = get_history(symbol='SBIN',
                   start=date(2015,1,1),
                   end=date(2015,1,10))
stock_fut = get_history(symbol="SBIN",start=date(2015,1,1), end=date(2015,1,10),
                        futures=True,expiry_date=date(2015,1,29))
stock_fut[['Open Interest']].plot()

data.info()

data.reset_index(level=0, inplace=True)

data['Date'] = pd.to_datetime(data['Date'])



data.info()

feather.write_feather(data, 'dffeather')
df2 = feather.read_feather('dffeather')