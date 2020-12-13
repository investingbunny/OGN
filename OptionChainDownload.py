from selenium import webdriver
from selenium.webdriver import Firefox
from selenium.webdriver.chrome.options import Options

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

# opts = Options()
# opts.headless = True

Bprofile = webdriver.FirefoxProfile()
Bprofile.set_preference('browser.download.folderList', 2) # custom location
Bprofile.set_preference('browser.download.manager.showWhenStarting', False)
Bprofile.set_preference('browser.download.dir', '/tmp')
Bprofile.set_preference('browser.helperApps.neverAsk.saveToDisk', 'text/csv')

assert opts.headless  # Operating in headless mode
browser = firefox(firefox_profile=Bprofile)
browser.get('https://www.nseindia.com/option-chain')




search_form = browser.find_element_by_id('equity_optionchain_select')
search_form.send_keys('BANKNIFTY')

# getting the button by class name
button = browser.find_element_by_id("symbolSearchGo")
 
# clicking on the button
button.click()

content = browser.find_element_by_class_name('xlsdownload').click()
# content = browser.find_element_by_id('option-chain-equity-derivatives.csv').click()

WebDriverWait(browser, 20).until(EC.element_to_be_clickable((By.LINK_TEXT, "Download (.csv)"))).click()
WebDriverWait(browser, 20).until(EC.element_to_be_clickable((By.ID, "option-chain-equity-derivatives.csv"))).click()

browser.close()
quit()