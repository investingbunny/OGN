# -*- coding: utf-8 -*-
"""
Created on Tue Aug  4 19:10:02 2020

@author: User
"""


from pynse import *
import datetime
import time
# path where data will be stored
datapath='E:/Harish/nsepywork/pynse/'

nse=Nse(path=datapath)

nse.market_status()

nse.info('SBIN')

nse.get_quote('RELIANCE')

nse.get_quote('TCS', segment=Segment.FUT, expiry=dt.date( 2020, 6, 25 ))

nse.get_quote('HDFC', segment=Segment.OPT, optionType=OptionType.PE)

nse.bhavcopy()

nse.bhavcopy(dt.date(2020,6,17))

nse.bhavcopy_fno()

nse.bhavcopy_fno(dt.date(2020,6,17))

nse.pre_open()

infy = nse.option_chain('INFY')

infyfno = nse.option_chain('INFY','30-Jul-2020')

nse.fii_dii()

nse.get_hist('SBIN')

nse.get_hist('NIFTY 50', from_date=dt.date(2020,1,1),to_date=dt.date(2020,6,26))

nse.get_indices(IndexSymbol.NiftyInfra)

nse.top_gainers(10)

nse.top_losers(10)

