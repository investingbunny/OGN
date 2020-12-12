from selenium import webdriver
from selenium.webdriver import Firefox
from selenium.webdriver.firefox.options import Options

opts = Options()
opts.headless = True
assert opts.headless  # Operating in headless mode
browser = Firefox(options=opts)
browser.get('https://www.nseindia.com/option-chain')

search_form = browser.find_element_by_id('equity_optionchain_select')
search_form.send_keys('BANKNIFTY')
search_form.submit()

results = browser.find_elements_by_class_name('result')
print(results[0].text)




from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

# To prevent download dialog
opts = Options()
opts.headless = True
profile = webdriver.FirefoxProfile()
profile.set_preference('browser.download.folderList', 2) # custom location
profile.set_preference('browser.download.manager.showWhenStarting', False)
profile.set_preference('browser.download.dir', '/tmp')
profile.set_preference('browser.helperApps.neverAsk.saveToDisk', 'text/csv')

browser = webdriver.Firefox(profile,options=opts)
browser.get("https://www.nseindia.com/option-chain")

# search_form = browser.find_element_by_id('equity_optionchain_select')
# search_form.send_keys('BANKNIFTY')

WebDriverWait(browser, 20).until(EC.element_to_be_clickable((By.LINK_TEXT, "Download (.csv)"))).click()
WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.ID, "option-chain-equity-derivatives.csv"))).click()
browser.find_element_by_id('exportpt').click()
browser.find_element_by_id('exporthlgt').click()



from selenium import webdriver
from selenium.webdriver.firefox.options import Options
profile = webdriver.FirefoxProfile()
options = Options()
options.headless = True

options.set_preference("browser.download.folderList",2)
options.set_preference("browser.download.manager.showWhenStarting", True)
options.set_preference("browser.download.dir", r"C:\Users\User\Downloads")
driver  = webdriver.Firefox(profile,options=opts)
driver.get("https://www.nseindia.com/option-chain")
elem = driver.find_element_by_id('option-chain-equity-derivatives.csv')
elem.click()


browser.close()
quit()