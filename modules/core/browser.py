# modules/core/browser.py
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException, InvalidElementStateException, InvalidArgumentException, ElementClickInterceptedException # type: ignore
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.common.alert import Alert
from webdriver_manager.chrome import ChromeDriverManager
from typing import List
import time
from urllib.parse import urlparse
import config.env_config as env_config

class Browser:

    def __init__(self):
        self.driver = self._setup_browser()

    def _setup_browser(self):
        """Initialize Selenium WebDriver."""

        if env_config.BROWSER_NAME == "Brave":
            # Define possible Brave paths
            brave_paths = [
                r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
                r"C:\Users\{}\AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe".format(os.getenv('USERNAME'))
            ]
            
            # Find the correct Brave path
            brave_path = next((path for path in brave_paths if os.path.exists(path)), None)
            
            if not brave_path:
                raise Exception("Brave browser not found. Please install Brave or update the path.")

            options = Options()
            options.binary_location = brave_path
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')

            # Create a new automated instance of Brave
            driver = webdriver.Chrome(options=options)

        elif env_config.BROWSER_NAME == "Chrome": 
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
            
        return driver

    def extract_domain(url):
            parsed_url = urlparse(url)
            return parsed_url.netloc

    def open_page(self, url: str):
        """Open the specified URL in the browser."""
        self.driver.get(url)
        self.wait_for_page_load()

    def wait_for_element(self, locator, timeout=10):
        """
        Waits for an element to be present on the page.

        Args:
            locator (tuple): A tuple containing the By strategy and the locator
                            value (e.g., (By.ID, "myElement")).
            timeout (int): The maximum time to wait for the element to appear, in seconds.

        Returns:
            WebElement: The located element.
        """
        return WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located(locator)
        )

    def wait_for_element_to_be_clickable(self, locator: tuple, timeout=10) -> WebElement:
        """
        Waits for an element to be clickable on the page.

        Args:
            locator (tuple): A tuple containing the By strategy and the locator
                            value (e.g., (By.ID, "myElement")).
            timeout (int): The maximum time to wait for the element to be clickable, in seconds.

        Returns:
            WebElement: The located and clickable element.
        """
        return WebDriverWait(self.driver, timeout).until(
            EC.element_to_be_clickable(locator)
        )

    def wait_for_element_to_be_visible(self, locator: tuple, timeout=10) -> WebElement:
        """
        Waits for an element to be visible on the page.

        Args:
            locator (tuple): A tuple containing the By strategy and the locator
                            value (e.g., (By.ID, "myElement")).
            timeout (int): The maximum time to wait for the element to be visible, in seconds.

        Returns:
            WebElement: The located element that is visible.
        """
        return WebDriverWait(self.driver, timeout).until(
            EC.visibility_of_element_located(locator)
        )

    def wait_for_elements_to_be_present(self, locator: tuple, timeout=10) -> List[WebElement]:
        """
        Waits for multiple elements to be present on the page.

        Args:
            locator (tuple): A tuple containing the By strategy and the locator
                            value (e.g., (By.CSS_SELECTOR, ".myElements")).
            timeout (int): The maximum time to wait for the elements to be present, in seconds.

        Returns:
            List[WebElement]: A list of located elements.
        """
        return WebDriverWait(self.driver, timeout).until(
            EC.presence_of_all_elements_located(locator)
        )
    
    def wait_for_element_to_disappear(self, locator: tuple, timeout=10) -> bool:
        """
        Waits for an element to become not visible from the page.

        Args:
            locator (tuple): A tuple containing the By strategy and the locator
                            value (e.g., (By.ID, "myElement")).
            timeout (int): The maximum time to wait for the element to disappear, in seconds.

        Returns:
            bool: True if the element disappeared within the timeout, False otherwise.
        """
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.invisibility_of_element_located(locator)
            )
            return True
        except TimeoutException:
            return False

    def wait_for_element_to_be_selected(self, locator: tuple, timeout=10) -> WebElement:
        """
        Waits for an element to be selected (e.g., a checkbox or radio button).

        Args:
            locator (tuple): A tuple containing the By strategy and the locator
                            value (e.g., (By.ID, "myCheckbox")).
            timeout (int): The maximum time to wait for the element to be selected, in seconds.

        Returns:
            WebElement: The located element that is selected.
        """
        return WebDriverWait(self.driver, timeout).until(
            EC.element_to_be_selected(locator)
        )

    def wait_for_alert(self, timeout=10) -> Alert:
        """
        Waits for an alert to be present on the page.

        Args:
            timeout (int): The maximum time to wait for the alert to appear, in seconds.

        Returns:
            Alert: The alert object if an alert is found.
        """
        return WebDriverWait(self.driver, timeout).until(EC.alert_is_present())

    def wait_for_frame_to_be_available_and_switch_to_it(self, locator: tuple, timeout=10) -> None:
        """
        Waits for an iframe to be available on the page and switches to it.

        Args:
            locator (tuple): A tuple containing the By strategy and the locator
                            value (e.g., (By.ID, "myIframe")).
            timeout (int): The maximum time to wait for the iframe, in seconds.

        Returns:
            None
        """
        iframe = WebDriverWait(self.driver, timeout).until(
            EC.frame_to_be_available_and_switch_to_it(locator)
        )

    def wait_for_url_to_be(self, url: str, timeout=10) -> bool:
        """
        Waits for the page's URL to be the expected value.

        Args:
            url (str): The URL that you are expecting the page to navigate to.
            timeout (int): The maximum time to wait for the URL, in seconds.

        Returns:
            bool: True if the URL matches, False if the timeout is reached.
        """
        try:
            WebDriverWait(self.driver, timeout).until(EC.url_to_be(url))
            return True
        except TimeoutException:
            return False

    def wait_for_url_contains(self, substring: str, timeout=10) -> bool:
        """
        Waits for the page's URL to contain a specific substring.

        Args:
            substring (str): The substring to check for in the URL.
            timeout (int): The maximum time to wait for the URL to contain the substring, in seconds.

        Returns:
            bool: True if the URL contains the substring, False if the timeout is reached.
        """
        try:
            WebDriverWait(self.driver, timeout).until(EC.url_contains(substring))
            return True
        except TimeoutException:
            return False

    def wait_for_text_in_element(self, locator: tuple, text: str, timeout=10) -> WebElement:
        """
        Waits for a specific text to appear within an element.

        Args:
            locator (tuple): A tuple containing the By strategy and the locator
                            value (e.g., (By.ID, "myElement")).
            text (str): The text that you want to appear in the element.
            timeout (int): The maximum time to wait for the text, in seconds.

        Returns:
            WebElement: The located element containing the expected text.
        """
        return WebDriverWait(self.driver, timeout).until(
            EC.text_to_be_present_in_element(locator, text)
        )

    def wait_for_page_load(self, timeout=10, padding=3):
        def page_has_loaded(driver):
            '''
            document.readyState tells us how loaded the page is:
            > "loading": still loading
            > "interactive": DOM is ready but subresources (e.g., images) may not be
            > "complete": everything is loaded
            '''
            return driver.execute_script("return document.readyState") == "complete"
        
        wait = WebDriverWait(self.driver, timeout)
        wait.until(page_has_loaded)
        time.sleep(padding)
