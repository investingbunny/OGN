from selenium import webdriver
from selenium.webdriver import Firefox
from selenium.webdriver.chrome.options import Options
from datetime import date, timedelta
from dateutil.relativedelta import *
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
import datetime
from datetime import date
import numpy as np
import os
import calendar



CurrentDate = datetime.date.today()
CurrentMonth = CurrentDate.month
CurrentYear = CurrentDate.year

ThreeThursdayDateList = []
AllThursdayDateList = []

def Last3Thursdays(dt):
    ThreeThursdayDateList.append(dt + relativedelta(day=31, weekday=TH(-1)))
    for month in range(1,3):
        dt += relativedelta(months=1)
        ThreeThursdayDateList.append(dt + relativedelta(day=31, weekday=TH(-1)))
        
Last3Thursdays(CurrentDate)


def AllThursdays(CurrentYear,CurrentMonth):
   d = date(CurrentYear,CurrentMonth, 1)                    # 1st of a month
   d += timedelta(days = (3 - d.weekday() + 7) % 7)         # First Thursday
   while d.year == CurrentYear and d.month < (CurrentMonth + 3):
      yield d
      d += timedelta(days = 7)

for d in AllThursdays(CurrentYear,CurrentMonth):
   AllThursdayDateList.append(d)


def AllThursdays(CurrentYear,CurrentMonth):
   d = date(CurrentYear,CurrentMonth, 1)                    # 1st of a month
   d += timedelta(days = (3 - d.weekday() + 7) % 7)         # First Thursday
   while d.year == CurrentYear and d.month < (CurrentMonth + 3):
      yield d
      d += timedelta(days = 7)

ChainOptions = webdriver.ChromeOptions()
ChainOptions.add_argument("--disable-blink-features")
ChainOptions.add_argument("--disable-blink-features=AutomationControlled")
# ChainOptions.add_argument('--headless')

browser = webdriver.Chrome(options=ChainOptions)
browser.implicitly_wait(10)
browser.set_page_load_timeout(20)
browser.get('https://www.nseindia.com/option-chain')

if(sym == 'NIFTY' or sym == 'BANKNIFTY'):
    search_form = browser.find_element_by_id('equity_optionchain_select')
    search_form.send_keys(sym)
    search_form = browser.find_element_by_id('expirySelect')
    search_form.send_keys(DownloadExpiryDate)


content = browser.find_element_by_class_name('xlsdownload').click()

os.rename(r'.\Option chain - Dec 14\option-chain-equity-derivatives.csv',r'.\Option chain - Dec 14\\' + 
          datetime.date.today().strftime("%Y-%m-%d") + '-'+ sym + 'option-chain-equity-derivatives-' +  
          datetime.date.today().strftime("%Y-%m-%d") + '.csv')

# delays = [7, 4, 6, 2, 10, 19]
# delay = np.random.choice(delays)  datetime.date.today().strftime("%Y-%m-%d")
# time.sleep(delay)

search_form = browser.find_element_by_id('equity_optionchain_select')
search_form.send_keys('BANKNIFTY')
search_form.send_keys('NIFTY')

search_form = browser.find_element_by_id('expirySelect')
search_form.send_keys('25-Mar-2021')

search_form = browser.find_element_by_id('select_symbol')
search_form.send_keys('RELIANCE')

# getting the button by class name
search_form = browser.find_element_by_id("symbolSearchGo")
# clicking on the button
search_form.click()


browser.close()
# quit()