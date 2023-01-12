import base64
import json
import os
import time
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.print_page_options import PrintOptions
from selenium.webdriver.common.proxy import Proxy, ProxyType
from termcolor import colored
from tqdm import tqdm

CONFIG = {
    'URI': "",
    'USER': "",
    'PASS': "",
    'PROXY_IP': None,
    'PROXY_PORT': None,
    'LOGIN_URL': 'https://login.vitalsource.com/?redirect_uri=https%3A%2F%2Fbookshelf.vitalsource.com%2F%23%2F&brand=bookshelf.vitalsource.com'
}


def opts():
    global CONFIG
    parser = ArgumentParser(
        description='Scraping the VitalSource website and convert to pdf',
        formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument('-w', '--website', dest='URI', help='URI/Website to the Ebook Page')
    parser.add_argument('-u', '--user', dest='USER', help='Login Username')
    parser.add_argument('-p', '--password', dest='PASS', help='Login Password')
    parser.add_argument('--socks_proxy_ip', dest='PROXY_IP', help="IP of the proxy", default=None)
    parser.add_argument('--socks_proxy_port', dest='PROXY_PORT', help="Port of the proxy", default=None)
    arguments = parser.parse_args()
    CONFIG.update(vars(arguments))


def process_browser_log_entry(entry):
    response = json.loads(entry['message'])['message']
    return response


class Scraper:
    def __init__(self, config):
        self.config = config
        self.visited_urls = set([])

        settings = {
            "recentDestinations": [{
                "id": "Save as PDF",
                "origin": "local",
                "account": "",
            }],
            "selectedDestinationId": "Save as PDF",
            "version": 2
        }

        capabilities = webdriver.DesiredCapabilities.CHROME.copy()
        capabilities['acceptInsecureCerts'] = True
        capabilities['javascriptEnabled'] = True
        capabilities['locationContextEnabled'] = True
        capabilities['applicationCacheEnabled'] = True
        capabilities['goog:loggingPrefs'] = {'performance': 'ALL'}

        if not self.config['PROXY_IP'] is None:
            prox = Proxy()
            prox.proxy_type = ProxyType.MANUAL
            prox.socks_proxy = f"{self.config['PROXY_IP']}:{self.config['PROXY_PORT']}"
            prox.socks_version = 5
            prox.add_to_capabilities(capabilities)

        chrome_options = webdriver.ChromeOptions()
        prefs = {'printing.print_preview_sticky_settings.appState': json.dumps(settings)}
        chrome_options.add_experimental_option('prefs', prefs)
        chrome_options.add_argument('--kiosk-printing')
        chrome_options.add_argument('--start-maximized')
        chrome_options.add_argument('--headless')
        self.driver = webdriver.Chrome(options=chrome_options, desired_capabilities=capabilities)
        self.driver.set_window_size(1920, 1000)
        self.driver.implicitly_wait(20)

    def find_one_element(self, element_type, attr, value):
        element = self.driver.find_elements(by=By.TAG_NAME, value=element_type)
        for element_tag in element:
            if element_tag.get_attribute(attr) == value:
                return element_tag

        return None

    def save_page(self, browser_log, filepath, current_page):
        log = [x['message'] for x in browser_log if
               "encrypted/1600" in x['message'] and "Network.responseReceived" in x['message']]

        urls = [json.loads(x)['message']['params']['response']['url'] for x in log]
        urls = [url for url in urls if url not in self.visited_urls]
        index = current_page
        for url in urls:
            self.driver.get(url)
            pdf = self.driver.print_page().encode()
            with open(f"{filepath}_{index}.pdf", "wb") as f:
                f.write(base64.decodebytes(pdf))
            self.visited_urls.add(url)
            index += 1

        return current_page + (len(urls) - 1)

    def scrape_page(self):
        print(colored('[*]', 'blue'), "Logging in...")
        # Call login
        self.driver.get(self.config['LOGIN_URL'])
        time.sleep(5)
        email_field = self.driver.find_element(by=By.ID, value="email-field")
        password_field = self.driver.find_element(by=By.ID, value="password-field")
        submit_button = self.driver.find_element(by=By.ID, value="submit-btn")
        email_field.send_keys(self.config['USER'])
        password_field.send_keys(self.config['PASS'])
        submit_button.submit()
        time.sleep(10)
        print(colored('[+]', 'green'), "Log in successful")

        # Call given webpage
        self.driver.get(f"{self.config['URI']}{0}")
        time.sleep(10)
        print(colored('[+]', 'green'), "Target webpage opened")
        self.driver.refresh()
        time.sleep(5)

        buttons = self.driver.find_elements(by=By.TAG_NAME, value="button")
        for button in buttons:
            attr = button.get_attribute("class")
            if attr == "Button__button-bxKYZL eldFzh":
                button.click()
                print(colored('[+]', 'green'), "Cookie banner accepted")
                break

        current_page_input = self.find_one_element(element_type="input",
                                                   attr="class",
                                                   value="InputControl__input-fbzQBk hDtUvs TextField__InputControl-iza-dmV iISUBf")
        if current_page_input is None:
            print(colored("[-]", "red"), "Current Page input not found")
            return

        last_page = self.find_one_element(element_type="div",
                                          attr="class",
                                          value="sc-ePIFMk hopdXc")
        if last_page is None:
            print(colored("red", "[-]"), "Last page text field not found")
            return

        print(colored('[*]', 'blue'), "Starting scraping...")
        first_page = int(current_page_input.get_attribute("value"))
        last_page = int(last_page.text.split(" ")[1])
        current_page = first_page
        title = self.driver.find_element(by=By.TAG_NAME, value="img")\
            .get_attribute("alt")\
            .replace("(", "_") \
            .replace(")", "_") \
            .replace(" ", "_")
        directory = f"/home/tommy/{title}"
        os.system(f"mkdir -p {directory}")
        print(colored('[*]', 'blue'), f"Storing results in {directory}")
        counter = 0
        with tqdm(total=(last_page - current_page)) as pbar:
            while current_page <= last_page:
                current_page = self.save_page(browser_log=self.driver.get_log('performance'),
                                              filepath=f"/home/tommy/{title}/{title}",
                                              current_page=current_page)

                current_page += 1
                counter += 1
                self.driver.get(f"{self.config['URI']}{current_page}")
                time.sleep(5)
                pbar.update(1)

        print(colored('[+]', 'green'), "Scraping done")

    def close(self):
        self.driver.close()


if __name__ == "__main__":
    os.system('color')
    opts()
    scaper = Scraper(CONFIG)
    try:
        scaper.scrape_page()
    finally:
        scaper.close()
