from selenium import webdriver
from selenium.webdriver import Firefox
from selenium.webdriver.chrome.options import Options
from datetime import date, timedelta
from dateutil.relativedelta import *
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
import datetime
import shutil
from datetime import date
import datetime as dt
import numpy as np
import os
import calendar
import time


OptionChainHolidayList = ['2021-01-26','2021-03-11','2021-03-29','2021-04-02','2021-04-14','2021-04-21','2021-05-13','2021-07-21','2021-08-19','2021-09-10','2021-10-15','2021-11-05','2021-11-19']
OptionChainHolidayList = [dt.datetime.strptime(date, '%Y-%m-%d').date() for date in OptionChainHolidayList]

def Next3Thursdays(dt):
    dt += relativedelta(day=31, weekday=TH(-1))
    if dt in OptionChainHolidayList:
        dt -= relativedelta(days=1)
    ThreeThursdayDateList.append(dt)
    for month in range(1,3):
        dt += relativedelta(months=1)
        dt += relativedelta(day=31, weekday=TH(-1))
        if dt in OptionChainHolidayList:
            dt -= relativedelta(days=1)
        ThreeThursdayDateList.append(dt)
        
def AllThursdays(d):
   CurrentDate = dt.date.today()   # Today
   CurrentYear = CurrentDate.year
   CurrentMonth = CurrentDate.month
   d += timedelta(days = (3 - d.weekday() + 7) % 7)         # First Thursday
   while d.year == CurrentYear and d.month < (CurrentMonth + 3):
      yield d
      d += timedelta(days = 7)
        
def DownloadOptionChain(sym):
    CurrentDate = datetime.date.today()
    Next3Thursdays(CurrentDate)

    for d in AllThursdays(CurrentDate):
        if d in OptionChainHolidayList:
            d -= relativedelta(days=1) 
        AllThursdayDateList.append(d)

    ChainOptions = webdriver.ChromeOptions()
    ChainOptions.add_argument("--disable-blink-features")
    ChainOptions.add_argument("--disable-blink-features=AutomationControlled")
    # ChainOptions.add_argument('--headless')
    browser = webdriver.Chrome(options=ChainOptions)
    browser.implicitly_wait(10)
    browser.set_page_load_timeout(20)
    browser.get('https://www.nseindia.com/option-chain')
    
    timeout = 5
    try:
        element_present = EC.presence_of_element_located((By.ID, 'equity_optionChainTable'))
        WebDriverWait(browser, timeout).until(element_present)
    except TimeoutException:
        print('Timed out waiting for initial page to load')

    if(sym == 'NIFTY' or sym == 'BANKNIFTY' or sym == 'FINNIFTY'):
        search_form = browser.find_element_by_id('equity_optionchain_select')
        search_form.send_keys(sym)
        for ExpiryDateDownload in AllThursdayDateList:
            search_form = browser.find_element_by_id('expirySelect')
            search_form.send_keys(ExpiryDateDownload.strftime("%d-%b-%Y"))
            try:
                element_present = EC.presence_of_element_located((By.ID, 'equity_optionChainTable'))
                WebDriverWait(browser, timeout).until(element_present)
            except TimeoutException:
                print('Timed out waiting for index page to load')
            content = browser.find_element_by_class_name('xlsdownload').click()
            while not os.path.exists(r'C:\Users\User\Downloads\option-chain-equity-derivatives.csv'):
                time.sleep(1)
            shutil.move(r'C:\Users\User\Downloads\option-chain-equity-derivatives.csv',r'.\Option chain - Dec 14\option-chain-equity-derivatives.csv')
            shutil.move(r'.\Option chain - Dec 14\option-chain-equity-derivatives.csv',r'.\Option chain - Dec 14\\' + 
              CurrentDate.strftime("%Y-%m-%d") + '-'+ sym + 'option-chain-equity-derivatives-' +  
              ExpiryDateDownload.strftime("%Y-%m-%d") + '.csv')
    else:
        search_form = browser.find_element_by_id('select_symbol')
        search_form.send_keys(sym)
        search_form = browser.find_element_by_id("symbolSearchGo")
        # clicking on the button
        search_form.click()
        for ExpiryDateDownload in ThreeThursdayDateList:
            search_form = browser.find_element_by_id('expirySelect')
            search_form.send_keys(ExpiryDateDownload.strftime("%d-%b-%Y"))
            try:
                element_present = EC.presence_of_element_located((By.ID, 'equity_optionChainTable'))
                WebDriverWait(browser, timeout).until(element_present)
            except TimeoutException:
                print('Timed out waiting for stock page to load')
            content = browser.find_element_by_class_name('xlsdownload').click()
            while not os.path.exists(r'C:\Users\User\Downloads\option-chain-equity-derivatives.csv'):
                time.sleep(1)
            shutil.move(r'C:\Users\User\Downloads\option-chain-equity-derivatives.csv',r'.\Option chain - Dec 14\option-chain-equity-derivatives.csv')
            shutil.move(r'.\Option chain - Dec 14\option-chain-equity-derivatives.csv',r'.\Option chain - Dec 14\\' + 
              CurrentDate.strftime("%Y-%m-%d") + '-'+ sym + 'option-chain-equity-derivatives-' +  
              ExpiryDateDownload.strftime("%Y-%m-%d") + '.csv')

    browser.close()

ThreeThursdayDateList = []
AllThursdayDateList = []
DownloadOptionChain('NIFTY')
# sym = 'RELIANCE'
# delays = [7, 4, 6, 2, 10, 19]
# delay = np.random.choice(delays)  datetime.date.today().strftime("%Y-%m-%d")
# time.sleep(delay)
