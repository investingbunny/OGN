from selenium import webdriver


chrome_options = webdriver.ChromeOptions()
chrome_options.add_argument('--disable-extensions')
chrome_options.add_argument('--profile-directory=Default')
chrome_options.add_argument("--incognito")
chrome_options.add_argument("--disable-plugins-discovery");
chrome_options.add_argument("--start-maximized")
driver = webdriver.Chrome(chrome_options=chrome_options)

driver.get('https://www.nseindia.com/option-chain')

search_form = driver.find_element_by_id('equity_optionchain_select')
search_form.send_keys('BANKNIFTY')

# getting the button by class name
button = driver.find_element_by_id("symbolSearchGo")
 
# clicking on the button
button.click()

content = driver.find_element_by_class_name('xlsdownload').click()
content = driver.find_element_by_id('option-chain-equity-derivatives.csv').click()


driver.close()
quit()