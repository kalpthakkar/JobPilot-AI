# modules/web_parser.py
from selenium.webdriver.common.by import By # type: ignore
from selenium.webdriver.support.ui import WebDriverWait # type: ignore
from selenium.webdriver.support import expected_conditions as EC # type: ignore
from selenium.common.exceptions import NoSuchElementException, TimeoutException, InvalidSelectorException, WebDriverException, StaleElementReferenceException, ElementClickInterceptedException, InvalidElementStateException, InvalidArgumentException # type: ignore
from selenium.webdriver.remote.webelement import WebElement # type: ignore
from selenium.webdriver.remote.webdriver import WebDriver # type: ignore
from selenium import webdriver

from typing import Dict, List, Any, Union, Optional, Iterable, Literal
from lxml import html as lxml_html, etree
from lxml.html import tostring, HtmlElement
import hashlib
import json
import pprint
import time
import re
import string

import nltk
from nltk.corpus import words as nltk_words, stopwords
from nltk.data import find
from nltk.stem import WordNetLemmatizer
from nltk.tag import pos_tag, PerceptronTagger
from nltk.util import ngrams
from pathlib import Path

from difflib import SequenceMatcher

from config.system_config import *
from config.env_config import LOG_LEVEL, NLTK_DATA_DIR, USER_JSON_FILE
from modules.utils.logger_config import setup_logger
import config.blacklist


logger = setup_logger(__name__, level=LOG_LEVEL, log_to_file=False)

# Global constants — initialized on first call
ENGLISH_WORDS = None
STOPWORDS = None
LEMMATIZER = None
# Broader POS tag sets (grouped semantically)
VALID_POS_TAGS = {
    'NN', 'NNS', 'NNP', 'NNPS',  # Nouns
    'VB', 'VBD', 'VBG', 'VBN', 'VBP', 'VBZ',  # Verbs
    'JJ', 'JJR', 'JJS',  # Adjectives
    'RB', 'RBR', 'RBS'   # Adverbs
}
PHRASE_PATTERNS = [
    ('JJ', 'NN'),
    ('NN', 'NN'),
    ('VB', 'NN'),
    ('RB', 'VB'),
    ('PRP', 'VB'),
    ('DT', 'NN'),
    ('VB', 'DT'),
    ('UH', 'VB')
]
NLTK_DATA_DIR = Path(NLTK_DATA_DIR)
if str(NLTK_DATA_DIR) not in nltk.data.path:
    nltk.data.path.insert(0, str(NLTK_DATA_DIR))


stardard_field_search_keys = ["label-srcTag", "label-srcText", "label-srcAttribute", "label-custom", "name", "id", "id-custom"]
stardard_button_search_keys = ["text", "label-srcTag", "label-srcText", "label-srcAttribute", "label-custom", "name", "id", "id-custom"]
standard_label_keys = ["label-srcTag", "label-srcText", "label-srcAttribute", "label-custom"]
field_identifiers = {
    'job_title': ['job title', 'job role', 'position'],
    'company': ['company', 'employer'],
    'location': ['location'],
    'currently_working': ['current', 'work here', 'working here', 'ongoing'],
    'school': ['school', 'university', 'college', 'institution'],
    'degree': ['degree', 'qualification', 'education level'],
    'field_of_study': ['field of study', 'major', 'discipline'],
    'gpa_or_grade': ['overall result', 'gpa', 'grade'],
    'currently_enrolled': ['current', 'ongoing', 'graduate'],
    'role_description': ['description', 'responsibilit'],
    'date': ['date', 'year', 'month'],
    'start_date': ['from date', 'start date', 'first year', 'start year'],
    'start_date_case_sensitive': ['From', 'Start', 'Joined'],
    'end_date': ['to date', 'end date', 'last year', 'end year'],
    'end_date_case_sensitive': ['To', 'End', 'Left'],
    'upload_file': ['upload', 'resume', 'add attachment', 'browse file'],
    'resume': ['resume'],
    'cloud_or_mannual_upload': ['dropbox', 'google', 'drive', 'cloud', 'manually'],
    'verification': ['verify','verification', 'pin-code', 'pincode', 'one-time-pass', 'one time pass', 'code digit', 'digit code']
}

def initialize_nltk_resources():
    """
    Ensures NLTK resources are downloaded and initializes global constants.
    Only runs once.
    """
    global ENGLISH_WORDS, STOPWORDS, LEMMATIZER

    if ENGLISH_WORDS is not None:
        return  # Already initialized

    # Ensure all required NLTK resources are available
    def ensure_nltk_resource(resource_name: str):
        """
        Safely ensures the specified NLTK resource is available.
        Handles both .zip and extracted forms.
        """
        try:
            # Attempt to use the resource — triggers LookupError if not available
            nltk.data.find(resource_name + '.zip')
        except LookupError:
            logger.info(f"⏳ Downloading NLTK resource: {resource_name}")
            nltk.download(resource_name.split('/')[-1], download_dir=str(NLTK_DATA_DIR))

    resources = [
        'corpora/words',
        'corpora/stopwords',
        'corpora/wordnet',
        'corpora/omw-1.4',
        'tokenizers/punkt',
        'taggers/averaged_perceptron_tagger_eng'
    ]

    for resource in resources:
        ensure_nltk_resource(resource)


    # Safe to initialize globals
    ENGLISH_WORDS = set(nltk_words.words())
    STOPWORDS = set(stopwords.words('english'))
    LEMMATIZER = WordNetLemmatizer()

    logger.debug("✅ NLTK resources loaded successfully.")

class UserData:

    def __init__(self, file_path):
        self.data: Dict[str, Any] = self.read_json_file(file_path)

    def read_json_file(self, file_path: Path) -> Optional[dict]:
        try:
            with open(file_path, 'r') as file:
                return json.load(file)
        except FileNotFoundError:
            print(f"❌ File not found: {file_path}")
        except json.JSONDecodeError:
            print(f"❌ Invalid JSON format in: {file_path}")
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
        return None

    def find_dicts_by_key_value(
        self,
        parent_key: str,
        match_key: str,
        match_value: Any,
        first_only: bool = False
    ) -> Union[Dict[str, Any], List[Dict[str, Any]], None]:
        """
        Search within a list of dictionaries under a specific parent key in a nested dict.

        Parameters:
        - data (dict): The main dictionary.
        - parent_key (str): The top-level key whose value should be a list of dicts.
        - match_key (str): The key to match inside each dictionary in the list.
        - match_value (Any): The value to search for.
        - first_only (bool): If True, return the first match. Otherwise return a list of all matches.

        Returns:
        - A dict (first match), list of dicts (all matches), or None if nothing matches.
        """
        value = self.data.get(parent_key)

        if not isinstance(value, list):
            print(f"[!] '{parent_key}' is not a list.")
            return None

        if first_only:
            for item in value:
                if isinstance(item, dict) and item.get(match_key) == match_value:
                    return item
            return None
        else:
            matches = [item for item in value if isinstance(item, dict) and item.get(match_key) == match_value]
            return matches if matches else None

USER_DATA = UserData(USER_JSON_FILE)
TOTAL_JOBS_ENTRY = len(USER_DATA.data["Work Experience"])
TOTAL_EDUCATION_ENTRY = len(USER_DATA.data["Education"])

class WebParserUtils:
    
    def __init__(self, driver):
        self.driver = driver

    def detect_xml_namespaces(self) -> Optional[bool]:
        if self.driver.current_url.startswith(("data:", "about:blank")): # URL not loaded on driver
            return None
        namespace_prefixes = set(re.findall(r'<([a-zA-Z0-9]+):[a-zA-Z0-9]+', self.driver.page_source)) # set(namespace_tags)
        # If namespace prefixes is detected in page source, then XPath queries may require namespace-aware evaluation
        return bool(namespace_prefixes)

    def wait_for_stable_dom(self, timeout: float = 15.0, check_interval: float = 1, padding: int = 1) -> bool:
        """
        Waits until the DOM becomes visually stable by checking that the page source
        does not change for a certain number of consecutive checks.

        This is useful for modern dynamic websites where `document.readyState == 'complete'`
        might return too early, while the DOM continues to change due to asynchronous content loading.

        Args:
            timeout (float): Total time to wait for DOM to become stable (in seconds).
            check_interval (float): Time between consecutive checks (in seconds).
            padding (int): Wait seconds after the DOM stable.

        Returns:
            bool: True if the DOM stabilized within the timeout period, False otherwise.
        """

        def wait_for_stable_dom(timeout: float = 15.0, check_interval: float = 0.5) -> bool:

            # Store the initial page source and initialize counters
            previous_source = ""
            stable_checks = 0

            # Number of consecutive unchanged page sources needed to consider the DOM stable
            required_stable_checks = 3

            # Calculate the deadline time
            deadline = time.time() + timeout

            while time.time() < deadline:
                # Capture the current HTML of the page
                current_source = self.driver.page_source

                if current_source == previous_source:
                    # Page source hasn't changed since last check
                    stable_checks += 1

                    if stable_checks >= required_stable_checks:
                        # DOM has been stable for enough checks
                        return True
                else:
                    # Page source changed — reset the counter
                    stable_checks = 0
                    previous_source = current_source

                # Wait before rechecking
                time.sleep(check_interval)

            # Timeout reached before DOM became stable
            return False

        WebDriverWait(self.driver, 10).until(lambda d: d.execute_script("return document.readyState") == "complete")
        is_stable = wait_for_stable_dom(timeout=timeout, check_interval=check_interval)
        if not is_stable:
            logger.warning(f"❗  Page is unstable since last {timeout} seconds.")
            return False
        time.sleep(padding)
        return True

    def get_element(self, xPath: str) -> Optional[WebElement]:
        try:
            if isinstance(xPath, WebElement):
                return xPath
            # Attempt to find the element using the given xPath
            return self.driver.find_element(By.XPATH, xPath)
        except NoSuchElementException:
            # If the element is not found, return None
            logger.error(f"❌ NoSuchElementException: Element does not exists for given xPath: {xPath}")
            return None
        except Exception as e:
            logger.error(f"❌ Unable to fetch element for given xPath: {xPath} | Exception: {e}")
            return None

    def count_elements_by_xpath(self, xpath: str) -> int:
        """
        Counts the number of elements matching a given XPath globally in the DOM.

        Args:
            xpath (str): The XPath query to search for elements in the DOM.

        Returns:
            int: Number of matching elements in the DOM.
        """
        if xpath:
            try:
                return len(self.driver.find_elements(By.XPATH, xpath))
            except Exception as e:
                print(f"[!] Error counting elements: {e}")
        return 0

    def get_xpath(self, element: Union[WebElement, etree._Element], verify_xpath: bool = True) -> Optional[str]:
        """
        Generates the XPath for a given element.

        Args:
            element: The element to generate the XPath for.
            verify_xpath: 
                > True: xPath must exist, else returns None.
                > False: return xPath without verifying.

        Returns:
            str: The XPath of the element.
        """

        if self.detect_xml_namespaces():
            '''
            Generate -> Relative XPath with Attributes
            > Starts from root?	            No (// searches globally)
            > Resilient to DOM changes?	    Yes
            > Uses attributes?	            Yes
            > Preferred in practice?        Frequently (especially for automation)
            '''
            if isinstance(element, etree._Element):
                xpath = self.compute_relative_xpath_lxml(element, verify_xpath=verify_xpath)
            elif isinstance(element, WebElement):
                xpath = self.compute_relative_xpath_selenium(element, optimized=not verify_xpath)
            else:
                logger.warning(f"⚠️  Invalid Argument. Must be 'WebElement' or 'etree._Element'. Got: {type(element)}")
                return None
            
            if not xpath:
                logger.warning(f"⚠️  Unable to build relative xPath for element: {element}")
                return None
            
            if verify_xpath:
                try:
                    matches = self.driver.find_elements(By.XPATH, xpath)
                    return xpath if len(matches) == 1 else None
                except InvalidSelectorException as e:
                    logger.error(f"❌ Invalid XPath generated: {xpath}")
                    return None
            else:
                return xpath    
        
        else:
            '''
            Generate -> Absolute XPath
            > Starts from root?	            Yes (/html/body/...)
            > Resilient to DOM changes?	    No
            > Uses attributes?	            No
            > Preferred in practice?        Rarely
            '''
            if isinstance(element, etree._Element):
                xpath = self.compute_absolute_xpath_lxml(element, verify_xpath=verify_xpath)
            elif isinstance(element, WebElement):
                xpath = self.compute_absolute_xpath_selenium(element)
            else:
                logger.warning(f"⚠️  Invalid Argument. Must be 'WebElement' or 'etree._Element'. Got: {type(element)}")
                return None
            
            if not xpath:
                logger.warning(f"⚠️  Unable to build absolute xPath for element: {element}. Falback to finding relative xPath")
                return None

            if verify_xpath:
                if len(self.driver.find_elements(By.XPATH, xpath)) == 1:
                    return xpath
                else: # Fallback to finding 'Relative XPath with Attributes'
                    if isinstance(element, etree._Element):
                        xpath = self.compute_relative_xpath_lxml(element, verify_xpath=verify_xpath)
                    elif isinstance(element, WebElement):
                        xpath = self.compute_relative_xpath_selenium(element, optimized=not verify_xpath)
                    return xpath if len(self.driver.find_elements(By.XPATH, xpath)) == 1 else None
            else:
                return xpath

    def compute_absolute_xpath_lxml(self, lxml_element: etree._Element, verify_xpath: bool = False)  -> Optional[str]:

        if self.detect_xml_namespaces():
            return None

        tag = lxml_element.tag.lower()

        # Serialize the lxml element to HTML string (minified)
        lxml_html = re.sub(r">\s+<", "><", tostring(lxml_element, encoding='unicode').strip())

        # Get all elements of the same tag in the Selenium DOM
        selenium_elements = self.driver.find_elements(By.TAG_NAME, tag)

        for sel_el in selenium_elements:
            try:
                # Get the outerHTML of the element in Selenium
                sel_html = self.driver.execute_script("return arguments[0].outerHTML;", sel_el)
                sel_html = re.sub(r">\s+<", "><", sel_html.strip())  # Normalize

                # Exact or loose match
                if lxml_html in sel_html or sel_html in lxml_html:
                    # Match found — now get full XPath
                    xpath = self.driver.execute_script("""
                        function absoluteXPath(element) {
                            if (element.tagName.toLowerCase() === 'html')
                                return '/html[1]';
                            if (element === document.body)
                                return '/html[1]/body[1]';

                            let ix = 0;
                            const siblings = element.parentNode ? element.parentNode.childNodes : [];
                            for (let i = 0; i < siblings.length; i++) {
                                const sibling = siblings[i];
                                if (sibling === element)
                                    return absoluteXPath(element.parentNode) + '/' + element.tagName.toLowerCase() + '[' + (ix + 1) + ']';
                                if (sibling.nodeType === 1 && sibling.tagName === element.tagName)
                                    ix++;
                            }
                        }
                        return absoluteXPath(arguments[0]);
                    """, sel_el)
                    if (not verify_xpath) or (verify_xpath and self.is_unique_xpath(xpath)):
                        return xpath
                    else:
                        continue
            except Exception as e:
                continue

        # print("[!] xPath not found: compute_absolute_xpath_lxml(self, element)")
        return None  # No match found
 
    def compute_absolute_xpath_selenium(self, selenium_element: WebElement)  -> Optional[str]:
        """
        Uses JavaScript to compute the absolute XPath of a WebElement.

        Args:
            selenium_element: The WebElement to analyze.

        Returns:
            str: The absolute XPath.
        """

        if self.detect_xml_namespaces():
            return None

        return self.driver.execute_script("""
            function absoluteXPath(el) {
                if (el === document.body)
                    return '/html/body';

                let ix = 0;
                const siblings = el.parentNode ? el.parentNode.childNodes : [];
                for (let i = 0; i < siblings.length; i++) {
                    const sib = siblings[i];
                    if (sib === el)
                        return absoluteXPath(el.parentNode) + '/' + el.tagName.toLowerCase() + '[' + (ix + 1) + ']';
                    if (sib.nodeType === 1 && sib.tagName === el.tagName)
                        ix++;
                }
            }
            return absoluteXPath(arguments[0]);
        """, selenium_element)

    def compute_relative_xpath_lxml(self, lxml_element: etree._Element, verify_xpath: bool = False) -> Optional[str]:
        '''
        Structured XPath resolution using all attributes present in element
        '''
        tag_name = lxml_element.tag.lower()
        xpath = f"//{tag_name}"

        # Iterate through attributes and add them to the XPath expression
        for attr_name, attr_value in lxml_element.attrib.items():
            # Ignore empty attribute values
            if attr_value:
                # If the attribute contains a JavaScript function (i.e., has '(' in value) 
                # or contains HTML-encoded quotation marks ('&quot;') or non-encoded ('"'), we need to handle both cases.
                if '(' in attr_value or '"' in attr_value or '&quot;' in attr_value:
                    # Extract the function name before the first '(' (ignoring arguments in parentheses)
                    function_name_1 = attr_value.split('(')[0].strip()
                
                    # Extract the portion before the first occurrence of '&quot;' (ignore HTML-encoded quotes)
                    function_name_2 = attr_value.split('&quot;')[0].strip()
                
                    # Extract the portion before the first occurrence of '"' (quotes)
                    function_name_3 = attr_value.split('"')[0].strip()
                
                    # Choose the shortest string to ensure we handle all cases correctly
                    function_name = min(function_name_1, function_name_2, function_name_3, key=len)  # Get the shortest string
                
                    # Handle potential special characters in the function name
                    xpath += f"[contains(@{attr_name}, '{function_name}')]"

                else: # For non-JavaScript attributes, use exact matching
                    xpath += f"[@{attr_name}='{attr_value}']"
            else: # Attribute name exists without value (e.g. required, checked)
                xpath += f"[@{attr_name}]"
        # Return xpath
        if (not verify_xpath) or (verify_xpath and self.is_unique_xpath(xpath)):
            return xpath
        return None
    
    def compute_relative_xpath_str(self, tags: set[str], verify_xpath: bool = False) -> set:
        '''
        Structured XPath resolution using all attributes present in set of tags.
        Sample set tag looks like: <input type="text" value>, and its relative xPath = "//input[@type='text'][@value]"
        '''

        def extract_attributes(tag: str) -> dict:
            # Regular expression to match attributes in the tag, including those with JavaScript functions and hyphenated attribute names.
            pattern = r'([a-zA-Z0-9\-]+)\s*=\s*"([^"]*)"|([a-zA-Z0-9\-]+)\s*(?=\s|>)'
            
            # Find all matches
            matches = re.findall(pattern, tag)
            
            # Create a dictionary to store the attributes
            attributes = {}

            visited_tag_name = False # Skip mapping tag_name as attribute
            # Process the matches and store the attributes in the dictionary
            for match in matches:
                if visited_tag_name:
                    if match[0] and match[1]:  # Attribute with a value
                        attributes[match[0]] = match[1]
                    elif match[2]:  # Attribute without a value (like 'value', 'checked')
                        attributes[match[2]] = ''
                else:
                    visited_tag_name = True
                    continue
            
            return attributes

        xpath_set = set()

        for tag in tags:
            tag = tag.split('>')[0] + '>' # Nested correction (get parent)
            tag_name = tag.split(' ')[0].lstrip('<').lower() # Get tag name
            xpath = f"//{tag_name}" # Initialize start
            # Iterate through attributes and add them to the XPath expression
            for attr_name, attr_value in extract_attributes(tag).items():
                # Ignore empty attribute values
                if attr_value:
                    # If the attribute contains a JavaScript function (i.e., has '(' in value) 
                    # or contains HTML-encoded quotation marks ('&quot;') or non-encoded ('"'), we need to handle both cases.
                    if '(' in attr_value or '"' in attr_value or '&quot;' in attr_value:
                        # Extract the function name before the first '(' (ignoring arguments in parentheses)
                        function_name_1 = attr_value.split('(')[0].strip()
                    
                        # Extract the portion before the first occurrence of '&quot;' (ignore HTML-encoded quotes)
                        function_name_2 = attr_value.split('&quot;')[0].strip()
                    
                        # Extract the portion before the first occurrence of '"' (quotes)
                        function_name_3 = attr_value.split('"')[0].strip()
                    
                        # Choose the shortest string to ensure we handle all cases correctly
                        function_name = min(function_name_1, function_name_2, function_name_3, key=len)  # Get the shortest string
                    
                        # Handle potential special characters in the function name
                        xpath += f"[contains(@{attr_name}, '{function_name}')]"

                    else: # For non-JavaScript attributes, use exact matching
                        xpath += f"[@{attr_name}='{attr_value}']"
                else: # Attribute name exists without value (e.g. required, checked)
                    xpath += f"[@{attr_name}]"
            # Append to the set of xpath(s)
            if (not verify_xpath) or (verify_xpath and self.is_unique_xpath(xpath)):
                xpath_set.add(xpath)
        # Return set of xpath(s)
        return xpath_set

    def compute_relative_xpath_selenium(self, selenium_element: WebElement, optimized: bool = True)  -> Optional[str]:
        '''
        Structured XPath resolution fallback mechanism based on attribute presence, in the following order of priority:
        > field_customId
        > field_id
        > field_labelCustom
        > All attributes (used as fallback or when optimized is false)

        Each of these should be matched against the value in the appropriate *_attributes dictionary 
        (id_attributes or label_attributes), to get the corresponding attribute name (the key), 
        then form an XPath like:
        > //input[@<attr_name>='<value>'][...]

        Stop as soon as a valid unique XPath is found
        '''
        xpath = None

        tag_name = selenium_element.tag_name

        id_attributes : dict = self.search_attribute("id", selenium_element)
        label_attributes : dict = self.search_attribute("label", selenium_element)

        customId = (diff_set := set((id_attributes or {}).values()).difference({selenium_element.get_attribute("id")})) and diff_set.pop() or None
        id = val if (val := selenium_element.get_attribute("id")) not in [""] else None
        labelCustom = (diff_set := set((label_attributes or {}).values()).difference({selenium_element.get_attribute("label")})) and diff_set.pop() or None

        if optimized:
            # Step 1: Check for field_customId
            if customId:
                for attr_name, value in id_attributes.items():
                    if value == customId:
                        test_xpath = f"//{tag_name}[@{attr_name}='{customId}']"
                        num_of_elements = len(self.driver.find_elements(By.XPATH, test_xpath))
                        if num_of_elements == 1:
                            return test_xpath  # Return immediately if 1 element is found
                        elif num_of_elements > 1:
                            xpath = test_xpath  # Save the XPath if there are multiple elements

            # Step 2: Check for field_id
            if id:
                for attr_name, value in id_attributes.items():
                    if value == id:
                        test_xpath = f"{xpath}[@{attr_name}='{id}']" if xpath else f"//{tag_name}[@{attr_name}='{id}']"
                        num_of_elements = len(self.driver.find_elements(By.XPATH, test_xpath))
                        if num_of_elements == 1:
                            return test_xpath
                        elif num_of_elements > 1:
                            xpath = test_xpath

            # Step 3: Check for field_labelCustom
            if labelCustom:
                for attr_name, value in label_attributes.items():
                    if value == labelCustom:
                        test_xpath = f"{xpath}[@{attr_name}='{labelCustom}']" if xpath else f"//{tag_name}[@{attr_name}='{labelCustom}']"
                        num_of_elements = len(self.driver.find_elements(By.XPATH, test_xpath))
                        if num_of_elements == 1:
                            return test_xpath
                        elif num_of_elements > 1:
                            xpath = test_xpath

        # Step 4: Create path using all attributes
        test_xpath = f"//{tag_name}"
        for attr in selenium_element.get_property('attributes'):
            attr_name = attr['name']
            attr_value = attr['value']
            # Skip invalid attribute names
            if not attr_name or '"' in attr_name or "'" in attr_name or "=" in attr_name:
                continue
            # Attribute name exists with value
            if attr_value:
                # If the attribute contains a JavaScript function (i.e., has '(' in value) 
                # or contains HTML-encoded quotation marks ('&quot;') or non-encoded ('"'), we need to handle both cases.
                if '(' in attr_value or '"' in attr_value or '&quot;' in attr_value:
                    # Extract the function name before the first '(' (ignoring arguments in parentheses)
                    function_name_1 = attr_value.split('(')[0].strip()
                
                    # Extract the portion before the first occurrence of '&quot;' (ignore HTML-encoded quotes)
                    function_name_2 = attr_value.split('&quot;')[0].strip()
                
                    # Extract the portion before the first occurrence of '"' (quotes)
                    function_name_3 = attr_value.split('"')[0].strip()
                
                    # Choose the shortest string to ensure we handle all cases correctly
                    function_name = min(function_name_1, function_name_2, function_name_3, key=len)  # Get the shortest string
                
                    # Handle potential special characters in the function name
                    test_xpath += f"[contains(@{attr_name}, '{function_name}')]"
                else:
                    # For non-JavaScript attributes, use exact matching
                    test_xpath += f"[@{attr_name}='{attr_value}']"
            else: # Attribute name exists without value (e.g. required, checked)
                test_xpath += f"[@{attr_name}]"

        return test_xpath

    def build_absolute_xpath_lxml(self, tree: etree._ElementTree, el: etree._Element, parent_xpath: list[str]) -> set[str]:
        """
        Build and return a set of valid absolute XPaths for a given lxml element.

        This method is used as a fallback when XML namespaces are not detected.
        It constructs the element's XPath relative to the parsed HTML fragment (`tree`),
        then appends it to each of the provided parent XPaths to form complete absolute paths.
        Each resulting path is validated for uniqueness using `self.is_unique_xpath()`.

        Args:
            tree (lxml.etree._ElementTree): The parsed HTML tree containing the target element.
            el (lxml.etree._Element): The element for which to generate absolute XPath.
            parent_xpath (list[str]): List of base parent XPaths (prefixes) to combine with the local path.

        Returns:
            set[str]: A set of valid absolute XPath strings that uniquely identify the element.
        """
        valid_xpath: set[str] = set()

        if not self.detect_xml_namespaces():  # Fallback if namespaces are not detected
            xpath = tree.getroottree().getpath(el)
            updated_xpath = '/' + '/'.join(xpath.strip('/').split('/')[1:])  # Remove the extra parent div

            for parent in parent_xpath:
                full_xpath = parent.rstrip('/') + updated_xpath
                if self.is_unique_xpath(full_xpath):
                    valid_xpath.add(full_xpath)

        return valid_xpath

    def get_nth_parent(self, element: HtmlElement, n: int) -> Optional[HtmlElement]:
        """
        Returns the nth parent of the given lxml HtmlElement.

        Args:
            element (HtmlElement): The current element whose ancestor is needed.
            n (int): The number of levels to go up in the parent chain.

        Returns:
            Optional[HtmlElement]: The nth parent element if it exists, otherwise None.

        Example:
            # Get the 3rd parent of an element:
            parent = get_nth_parent(el, 3)
            if parent:
                print(parent.tag)
        """
        parent = element
        for _ in range(n):
            if parent is None:
                return None  # Reached the root before n steps
            parent = parent.getparent()
        return parent

    def get_valid_parent_xpath(self, el: etree._Element, max_fallbacks: int = 5) -> Optional[str]:
        """
        Traverse up to `max_fallbacks` parent levels from the given element and
        attempt to compute a valid XPath using the provided `compute_xpath_func`.

        Args:
            el (_Element): The starting lxml element.
            compute_xpath_func (Callable[[ _Element], Optional[str]]):
                A function that takes an element and returns its XPath if valid, else None.
            max_fallbacks (int): Maximum number of parent levels to attempt.

        Returns:
            Optional[str]: A valid XPath string if found, else None.
        """
        for parent_n in range(1, max_fallbacks + 1):
            parent_el = self.get_nth_parent(el, parent_n)
            if parent_el is None:
                break
            parent_xpath = self.compute_relative_xpath_lxml(parent_el, verify_xpath=True)
            if parent_xpath:
                return parent_xpath

        return None

    def is_unique_xpath(self, xpath: str) -> bool:
        """
        Safely checks if the given XPath uniquely identifies exactly one element.
        """
        try:
            return len(self.driver.find_elements(By.XPATH, xpath)) == 1
        except (InvalidSelectorException, WebDriverException):
            return False
        except:
            return False

    def is_element_misplaced(self, element_metadata: Dict[str, Any]) -> bool:
        """
        Determine if an element is misplaced based on the uniqueness of its XPath locators.

        Args:
            element_metadata (Dict[str, Any]): Metadata dictionary expected to contain
                'xPath' and/or 'xPath-relative' keys with XPath strings.

        Returns:
            bool: True if element is misplaced (not uniquely identified by relative XPath),
                False if uniquely identified by either XPath.
        """
        # Get the helper XPath (could be absolute or relative)
        xPath_any = element_metadata.get('xPath')
        # Get the relative XPath (usually shorter, relative path)
        xPath_relative = element_metadata.get('xPath-relative')

        # If helper XPath exists and is relative, check uniqueness
        if xPath_any and not self.is_absolute_xpath(xPath_any):
            if self.count_elements_by_xpath(xPath_any) == 1:
                return False  # Uniquely found — element is not misplaced

        # If relative XPath exists, check uniqueness
        if xPath_relative:
            if self.count_elements_by_xpath(xPath_relative) == 1:
                return False  # Uniquely found — element is not misplaced

        # Otherwise, element is considered misplaced (ambiguous or missing XPath)
        return True

    def get_new_elements(self, dom_before: str, dom_after: str, element_queries: List[str], return_html: bool = True) -> List[Union[str, etree._Element]]:
        """
        Returns newly added elements that match given tag names or XPath expressions.

        Args:
            dom_before (str): HTML DOM before an event occured.
            dom_after (str): HTML DOM after an event occured.
            element_queries (List[str]): List of tag names (e.g., "input") or XPath queries (e.g., ".//*[@role='button']").
            return_html (bool): If True, returns HTML strings; else returns lxml element objects.

        Returns:
            List[Union[str, _Element]]: List of newly added elements (as HTML or lxml elements).
        """

        # Parse both DOMs
        tree_before = lxml_html.fragment_fromstring(dom_before, create_parent="div")
        tree_after = lxml_html.fragment_fromstring(dom_after, create_parent="div")

        # Detect if item is a tag (alphanumeric only) or a full XPath
        def extract_elements(tree, queries):
            elements = []
            for query in queries:
                if query.isalpha():  # assume it's a tag name
                    elements.extend(tree.findall(f".//{query}"))
                else:  # assume it's an XPath expression
                    elements.extend(tree.xpath(query))
            return elements

        # Get matching elements before and after the click
        before_set = {
            lxml_html.tostring(el, encoding="unicode")
            for el in extract_elements(tree_before, element_queries)
        }

        after_elements = extract_elements(tree_after, element_queries)

        # Compare and find new elements
        new_elements = []
        for el in after_elements:
            html_str = lxml_html.tostring(el, encoding="unicode")
            if html_str not in before_set:
                new_elements.append(html_str if return_html else el)

        return new_elements

    def has_dom_significantly_changed_regex(self, dom_before: str, dom_after: str, threshold: float = 0.6) -> bool:
        """
        Checks whether the DOM has changed significantly based on interactive elements.

        Args:
            dom_before (str): HTML DOM before click.
            dom_after (str): HTML DOM after click.
            threshold (float): If more than this % of elements remain, change is insignificant.

        Returns:
            bool: True if DOM has significantly changed, False otherwise.

        | Feature                         | Regex-Based       | lxml-Based (has_dom_significantly_changed_lxml)   |
        | ------------------------------- | ----------------- | ------------------------------------------------  |
        | Accuracy                        | Good              | ✅ Excellent                                     |
        | Attribute normalization         | Partial           | ✅ Fully normalized                              |
        | Handles malformed HTML          | Sometimes fragile | ✅ Robust via `lxml`                             |
        | Performance                     | ✅ Very fast      | ⚠️ Slightly slower (but still fast)              |
        | Element positioning & structure | ❌ No             | ✅ Yes                                           |
        """

        def extract_element_fingerprints(html: str) -> set[str]:
            """
            Extract simplified fingerprints of interactive elements based on attributes.

            Returns:
                Set[str]: Hashes/fingerprints representing each interactive element.
            """
            element_patterns = [
                r'<input\b[^>]*>',
                r'<textarea\b[^>]*>',
                r'<select\b[^>]*>',
                r'<button\b[^>]*>',
                r'<[^>]*\brole=["\']button["\'][^>]*>'
            ]

            matches = []
            for pattern in element_patterns:
                matches.extend(re.findall(pattern, html, flags=re.IGNORECASE))

            fingerprints = set()
            for tag in matches:
                attrs = dict(re.findall(r'(\w[\w-]*)=["\']?([^"\'> ]*)', tag))
                key_attrs = ['name', 'id', 'placeholder', 'type', 'aria-label', 'role']
                signature = '|'.join([f"{k}:{attrs.get(k, '')}" for k in key_attrs])
                hash_val = hashlib.sha1(signature.encode()).hexdigest()
                fingerprints.add(hash_val)

            return fingerprints

        before_fingerprints = extract_element_fingerprints(dom_before)
        after_fingerprints = extract_element_fingerprints(dom_after)

        if not before_fingerprints:
            return True  # No interactive elements to compare

        preserved = before_fingerprints.intersection(after_fingerprints)
        preserved_ratio = len(preserved) / len(before_fingerprints)

        return preserved_ratio < threshold

    def has_dom_significantly_changed_lxml(self, dom_before: str, dom_after: str, threshold: float = 0.6) -> bool:
        """
        Compares DOMs using parsed trees via lxml to check whether the page has advanced significantly.

        Args:
            dom_before (str): HTML before click.
            dom_after (str): HTML after click.
            threshold (float): Percentage (0.0 to 1.0). If preserved elements >= threshold, DOM is unchanged. (False 0.0 <---> 1.0 True)

        Returns:
            bool: True if DOM significantly changed, else False.
        """

        def extract_fingerprints_from_tree(tree) -> set[str]:
            interactive_tags = ['input', 'select', 'textarea', 'button']
            role_button_xpath = "//*[@role='button']"
            all_elements = set()

            for tag in interactive_tags:
                for el in tree.findall(f".//{tag}"):
                    all_elements.add(el)

            all_elements.update(tree.xpath(role_button_xpath))

            fingerprints = set()
            for el in all_elements:
                attrs = el.attrib
                key_attrs = ['name', 'id', 'placeholder', 'type', 'aria-label', 'role']
                signature = '|'.join([f"{k}:{attrs.get(k, '')}" for k in key_attrs])
                hash_val = hashlib.sha1(signature.encode()).hexdigest()
                fingerprints.add(hash_val)

            return fingerprints

        # Parse the HTML fragments
        tree_before = lxml_html.fragment_fromstring(dom_before, create_parent="div")
        tree_after = lxml_html.fragment_fromstring(dom_after, create_parent="div")

        before_fingerprints = extract_fingerprints_from_tree(tree_before)
        after_fingerprints = extract_fingerprints_from_tree(tree_after)

        if not before_fingerprints:
            return True

        preserved = before_fingerprints.intersection(after_fingerprints)
        preserved_ratio = len(preserved) / len(before_fingerprints)

        print('Preserved Ratio:', preserved_ratio)
        return preserved_ratio < threshold

    def search_attribute(self, substring: List[str], element_or_xpath: Union[str, WebElement]) -> Optional[dict]:
        """
        Search for attributes on an element whose names match patterns based on the given substring(s).

        Args:
            substring (List[str]): List of substrings to match against attribute names.
            element_or_xpath (Union[str, WebElement]): Either an XPath string to locate the element or a WebElement instance.

        Returns:
            Optional[dict]: Dictionary of matching attributes {attribute_name: value}, or None if no matches found.
        """
        # Locate the element if XPath string provided; else use given WebElement
        if isinstance(element_or_xpath, str):
            element = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, element_or_xpath))
            )
        elif isinstance(element_or_xpath, WebElement):
            element = element_or_xpath
        else:
            # Invalid input type
            return None

        matches = {}

        # Check each attribute of the element against the substring patterns
        for attr in element.get_property('attributes'):
            attr_name = attr['name'].lower()

            # Check each substring pattern in the list
            for sub in substring:
                if (
                    attr_name == sub or
                    re.search(rf'-{re.escape(sub)}$', attr_name) or   # ends with -{sub}
                    re.search(rf'_{re.escape(sub)}$', attr_name) or   # ends with _{sub}
                    re.match(rf'aria-{re.escape(sub)}', attr_name)    # starts with aria-{sub}
                ):
                    matches[attr_name] = attr['value']
                    break  # stop checking other substrings for this attribute

        # Return matches dict or None if empty
        return matches or None

    def search_attribute_value(self, substrings: List[str], element_or_xpath: Union[str, WebElement]) -> Optional[Dict[str, str]]:
        """
        Find an element using xpath or use a WebElement, then check if any of the substrings match
        any of the values of the element's attributes.

        Args:
            substrings: List of substrings to search for in the element's attribute values.
            element_or_xpath: The XPath string or a Selenium WebElement.

        Returns:
            dict: A dictionary with the matching attribute name and value if found, otherwise None.
        """
        if isinstance(element_or_xpath, str):
            try:
                element = WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.XPATH, element_or_xpath)))
            except Exception as e:
                print(f"[!] Error waiting for element: {e}")
                return None
        elif isinstance(element_or_xpath, WebElement):
            element = element_or_xpath
        else:
            # print("[!] Invalid Argument: element_or_xpath must be an XPath string or a WebElement.")
            return None
        
        if isinstance(substrings, str): # Check if substrings is a string (not a list)
            substrings = [substrings]  # Convert it to a list

        try:
            for attr in element.get_property('attributes'):
                attr_value = attr['value']
                # Check if any substring exists in the attribute value
                if any(substring.lower() in attr_value.lower() for substring in substrings):
                    return {attr['name']: attr_value}
            return None  # No match found
        except Exception as e:
            print(f"[!] Error reading attributes: {e}")
            return None

    def is_absolute_xpath(self, xpath: str) -> bool:
        """
        Checks whether the given XPath is absolute or relative.

        Absolute XPath starts with a single slash '/'.
        Relative XPath typically starts with '//' or does not start with '/'.

        :param xpath: XPath string
        :return: True if absolute, False if relative
        """
        try:
            xpath = xpath.strip()
            return xpath.startswith('/') and not xpath.startswith('//')
        except Exception:
            # On any unexpected error, return False (treat as relative XPath)
            return False

    def get_tag_name(self, element_or_xpath: Union[str, WebElement]) -> str | None:
        """
        Retrieve the tag name of an element identified by a WebElement or an XPath.

        Args:
            element_or_xpath (Union[str, WebElement]): WebElement instance or XPath string to locate the element.

        Returns:
            str | None: Lowercase tag name of the element if found; None if element is not found or argument is invalid.
        """
        # If input is a WebElement, return its tag name directly
        if isinstance(element_or_xpath, WebElement):
            return element_or_xpath.tag_name.lower()

        # If input is an XPath string, locate the element and return its tag name
        elif isinstance(element_or_xpath, str):
            try:
                element = self.driver.find_element(By.XPATH, element_or_xpath)
                return element.tag_name.lower()
            except NoSuchElementException:
                # Element not found for given XPath
                return None

        # Input is neither WebElement nor string, return None
        else:
            return None

    def get_tag_count(self, element_or_xpath: Union[str, WebElement], tag_name: str, use_js: bool = True) -> Union[int, None]:
        """
        Returns the count of a specific HTML tag within a given WebElement or XPath.
        
        Args:
            element_or_xpath (str | WebElement): XPath string or Selenium WebElement to search within.
            tag_name (str): HTML tag name to count (e.g., 'label', 'input').
            use_js (bool): Whether to use JavaScript for faster in-browser counting.

        Returns:
            int | None: Number of elements found or None on failure.
        """
        try:
            if isinstance(element_or_xpath, str):
                web_element = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, element_or_xpath))
                )
            elif isinstance(element_or_xpath, WebElement):
                web_element = element_or_xpath
            else:
                raise TypeError("element_or_xpath must be a string XPath or a WebElement.")

            if use_js:
                return web_element.parent.execute_script(
                    "return arguments[0].getElementsByTagName(arguments[1]).length;", 
                    web_element, tag_name
                )
            else:
                return len(web_element.find_elements(By.TAG_NAME, tag_name))

        except Exception as e:
            print(f"[!] Error counting <{tag_name}> tags: {e}")
            return None

    def get_element_outerhtml_str(self, element: WebElement) -> str:
        """
        Returns the full HTML of a given Selenium WebElement (outerHTML).

        Args:
            driver (WebDriver): Selenium WebDriver instance.
            element (WebElement): The element to extract HTML from.

        Returns:
            str: The outerHTML string of the element.
        """
        if not isinstance(element, WebElement):
            raise TypeError("Argument must be a Selenium WebElement.")

        return self.driver.execute_script("return arguments[0].outerHTML;", element)

    def find_associated_text(self, element_or_xpath: Union[str, WebElement]) -> str | None:
        """
        Find associated text for an element specified by XPath by tracing back through its ancestors.
        
        Args:
            element_or_xpath (Union[str, WebElement]): The XPath of the target element
            
        Returns:
            Union[str, None]: The extracted text or None if not found
        """
        
        # Initialize XPath
        if isinstance(element_or_xpath, str):
            xpath = element_or_xpath
        elif isinstance(element_or_xpath, WebElement):
            xpath = self.get_xpath(element_or_xpath)
        else: # Invalid argument
            return None
        
        if (
            not xpath # xPath is None
            or not self.is_absolute_xpath(xpath) # xPath is Relative
            or self.detect_xml_namespaces() # DOM contains namespace
            or not isinstance(xpath,str) # xPath is not string type
        ):
            return None

        # If the element is already contained within label
        element = self.get_element(xpath)
        if not element:
            return None  # Bail out early if target element isn't found
        

        is_radio_or_checkbox = element.get_attribute("type") in {'radio', 'checkbox'}
        # Skip radio/checkbox element since this in-xpath label for this `element` represents the 'option' 
        # and not true-label associated as the title representing the overall field.
        if 'label' in xpath and not is_radio_or_checkbox:
            label_xpath = xpath.split('/label')[0] + '/label' # Get XPath up to 'label'
            label_element = self.get_element(label_xpath)
            if label_element and label_element.text:
                return label_element.text

        # Early exit capturing label-like text if the field block is properly encapsulated within 'fieldset'
        components = xpath.split('/')[1:]  # Correct way to split, keeping 'html' in the list
        if 'fieldset' in xpath:
            fieldset_boundary_pct = 33.33 # %
            fieldset_component_boundary_idx = int((len(components) * fieldset_boundary_pct) // 100)
            if any('fieldset' in item for item in components[len(components)-fieldset_component_boundary_idx:]):
                # Count <h1>-<h6> and <p> elements inside a given root element that have visible text longer than 1 words
                js_script = r"""
                    const root = arguments[0];
                    const tags = ['h1','h2','h3','h4','h5','h6','p','label'];
                    const minWords = 2;
                    let results = [];

                    tags.forEach(tag => {
                        const elements = root.querySelectorAll(tag);
                        elements.forEach(el => {
                            const text = el.innerText.trim();
                            const words = text.split(/\s+/);
                            if (words.length > minWords) {
                                results.push(text);
                            }
                        });
                    });

                    return results;
                """
                fieldset_xpath: str = xpath[:xpath.rfind('/fieldset') + len('/fieldset')]
                fieldset_element: WebElement | None = self.get_element(fieldset_xpath)
                if fieldset_element:
                    qualified_text: list[str] = self.driver.execute_script(js_script, fieldset_element)
                    qualified_text_el_count: int = len(qualified_text)
                    if qualified_text_el_count < 4: # Max 3 label-like elements allowed in fieldset.
                        return '\n'.join(qualified_text)

        MAX_TRACEBACKS = 8
        lst_ignoreText = []

        allowed_split_boundary = 4 # Splitting acceptable for {#} traceback
        max_splits_length = 5 # Individual split should not exceed {#}
        max_split_occurence = 2 # Split should not occur more than {#} in given boundary

        for i in range(1, MAX_TRACEBACKS + 1):
            if i > len(components):
                break  # Prevent index out of range

            # Break if we are about to pop an element having a split
            if '[' in components[-i] and ']' in components[-i]:  
                # Special handling for 'radio' and 'checkbox' types to account for early true-sibling splits, 
                # preventing misinterpretation as sectional splits in traceback.
                if is_radio_or_checkbox:
                    if i < 5: 
                        n_trueSibs = int(components[-i].split('[')[-1].strip(']'))
                        base_component = '/' + '/'.join(components[:-i])
                        for n in range(1,n_trueSibs+1):
                            ignore_component = base_component + '/' + str(components[-i].split('[')[0]) + '[' + str(n) + ']'
                            try:
                                text = self.driver.execute_script("""
                                var xpath = arguments[0];
                                return [...document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue?.childNodes || []].filter(n => n.nodeType === 3 || (n.nodeType === 1 && n.tagName !== 'BUTTON')).map(n => n.textContent.trim()).join(" ");
                                """, ignore_component)
                            except Exception as e:
                                print(f"Error extracting text: {e}")
                            lst_ignoreText.append(text.strip(' '))

                if ((i > allowed_split_boundary) and (int(re.search(r'\[(\d+)\]', components[-i]).group(1)) != 1)) or (int(re.search(r'\[(\d+)\]', components[-i]).group(1)) > max_splits_length) or (max_split_occurence == -1):         
                    try:
                        if i > allowed_split_boundary:
                            open_text = self.driver.find_element(By.XPATH, '/' + '/'.join(components[:-i])).text
                            if open_text:
                                if (
                                    (is_radio_or_checkbox and len(open_text.split('\n')) < 9)
                                    or (not is_radio_or_checkbox and len(open_text.split('\n')) < 6)
                                ):
                                    label = open_text.split('\n')[0]
                                    return label # Return 1st (top-most) label
                    except:
                        break
                    break
                else:
                    # Element having [1] is not considered split
                    if int(re.search(r'\[(\d+)\]', components[-i]).group(1)) != 1: # Check if split {#} type is not "# = 1"
                        max_split_occurence -= 1 # Deduct if split is not 1.

            current_components = components[:-i]
            if (
                not current_components  # Reached root element
                or current_components[-1] == 'body'
            ):
                break # Break if when search reaches top of DOM. Possible when length of xPath is nearly equal to MAX_TRACEBACKS

            current_path = '/' + '/'.join(current_components)

            try:
                # Find the current ancestor element
                ancestor_element = self.driver.find_element(By.XPATH, current_path)
                
                # Search for label and heading elements within this ancestor
                search_elements = ancestor_element.find_elements(By.XPATH, ".//label | .//h1 | .//h2 | .//h3 | .//h4 | .//h5 | .//h6 | .//p")

                original_element = self.driver.find_element(By.XPATH, xpath)

                found_text = None
                for el in search_elements:
                    try:
                        # Use a more robust text extraction method
                        text = self.driver.execute_script("""
                            function extractText(element) {
                                let text = '';
                                for (let node of element.childNodes) {
                                    if (node.nodeType === Node.TEXT_NODE) {
                                        text += node.textContent.trim();
                                    } else if (node.nodeType === Node.ELEMENT_NODE && node.tagName.toLowerCase() !== 'button') {
                                        text += extractText(node);
                                    }
                                }
                                return text;
                            }
                            return extractText(arguments[0]).replace(/\\s+/g, ' ').trim();
                        """, el)

                        if text:

                            # Check if the element is before or wrapping our target element
                            is_before_or_parent = self.driver.execute_script("""
                                let el = arguments[0];
                                let target = arguments[1];
                                return (el.compareDocumentPosition(target) & Node.DOCUMENT_POSITION_FOLLOWING) || el.contains(target);
                            """, el, original_element)

                            if is_before_or_parent:
                                # For radio/checkbox, lst_ignoreText will be populated with options, and remains empty for other types.
                                if text not in lst_ignoreText:
                                    if is_radio_or_checkbox: # For radio/checkbox, we allow duplicate labels, therefore always return
                                        return text
                                    # Check if the identified text element (el) comes before original element
                                    if self.is_element_after(original_element, el) and text!='': # original element comes after identified text-holding element
                                        found_text = text
                                    else:
                                        break

                    except StaleElementReferenceException:
                        continue
                # for ends here
                if found_text:
                    return found_text

            except (NoSuchElementException, StaleElementReferenceException):
                continue

            # Label not found until max_traceback
            if i == MAX_TRACEBACKS:
                open_text = ancestor_element.text
                if open_text:
                    if (
                        (is_radio_or_checkbox and len(open_text.split('\n')) < 9)
                        or (not is_radio_or_checkbox and len(open_text.split('\n')) < 6)
                    ):
                        label = open_text.split('\n')[0]
                        return label

        return None  # Return None if no text is found after all tracebacks

    def extract_input_tags(self, html:str) -> set:
        # Split the HTML string by '<input'
        input_tags = set()
        parts = html.split('<input')
        
        # For each part after the first split, split by '>' and extract the input tag
        for part in parts[1:]:  # Skip the first part before the first <input tag
            input_tag = '<input' + part.split('>')[0] + '>'  # Recreate the full <input> tag
            input_tags.add(input_tag)
        
        return input_tags

    def is_element_after(self, xpath1: str, xpath2: str) -> bool:
        """
        Returns True if element1 (xpath1) comes after element2 (xpath2) in the DOM order.
        Uses compareDocumentPosition (bitmask 2 = preceding).
        """
        try:
            # Resolve xpath1 to WebElement if necessary
            element1 = self.driver.find_element(By.XPATH, xpath1) if isinstance(xpath1, str) else xpath1
            element2 = self.driver.find_element(By.XPATH, xpath2) if isinstance(xpath2, str) else xpath2

            if not element1 or not element2:
                return False  # Elements not found or invalid

            # 2 = DOCUMENT_POSITION_PRECEDING (element1 is after element2)
            result = self.driver.execute_script("""
                return arguments[0].compareDocumentPosition(arguments[1]);
            """, element1, element2)

            return bool(result & 2)
        
        except Exception as e:
            # Optional: log the exception if needed
            # logger.warning(f"DOM comparison failed: {e}")
            return False

    def is_text_present_on_webpage(self, text: Union[str, Iterable[str]]) -> bool:
        """
        Check if a specific string or any string from an iterable is present in the webpage's body text.

        Args:
            text (Union[str, Iterable[str]]): A single string or iterable of strings to search for.

        Returns:
            bool: True if the string or any of the strings is found, otherwise False.
        """
        body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()

        if isinstance(text, str):
            return text.lower() in body_text
        return any(identifier.lower() in body_text for identifier in text)

    def get_cleaned_text(self, element: WebElement) -> str:

        def clean_text(raw_text: str) -> str:
            # Remove leading/trailing spaces, newline characters, or special symbols
            cleaned_text = raw_text.strip()
            # Remove any unwanted characters like newlines (\n), special characters (e.g., ), etc.
            cleaned_text = re.sub(r'[^\w\s.,;:*()"\-]', '', cleaned_text)  # Keep only basic punctuation and word chars
            # Replace multiple spaces or newlines with a single space
            cleaned_text = re.sub(r'[\n\s]+', ' ', cleaned_text)
            return cleaned_text.strip()

        raw_text = element.text

        return clean_text(raw_text)

    def is_element_in_tag(self, element: WebElement, tag_names: List[str]) -> bool:
        """
        Checks if a given WebElement is inside any of the specified HTML tag names.

        Args:
            element (WebElement): The Selenium WebElement to check.
            tag_names (List[str]): List of HTML tag names (case-insensitive).

        Returns:
            bool: True if the element is within any of the specified tags, False otherwise.
        """
        try:
            tag_names = [tag.lower() for tag in tag_names]
            while element:
                if element.tag_name.lower() in tag_names:
                    return True
                element = element.find_element(By.XPATH, "..")  # Traverse to parent
        except Exception:
            pass  # Likely hit the root element or a stale element

        return False

    def get_visible_iframes(self) -> List[WebElement]:
        """
        Returns a list of visible <iframe> elements using JavaScript for performance.

        Returns:
            List[WebElement]: List of visible iframe WebElements.
        """
        try:
            return self.driver.execute_script("""
                return Array.from(document.getElementsByTagName('iframe')).filter(function(iframe) {
                    const rect = iframe.getBoundingClientRect();
                    const style = window.getComputedStyle(iframe);
                    return (
                        rect.width > 0 &&
                        rect.height > 0 &&
                        style.display !== 'none' &&
                        style.visibility !== 'hidden' &&
                        style.opacity !== '0'
                    );
                });
            """)
        except Exception as e:
            print(f"[!] Error fetching visible iframes: {e}")
            return []

    def contains_substring_in_tags(self, substrings: List[str], tags: List[str], case_sensitive: bool = False) -> bool:
        """
        Check if any of the specified substrings are present in the visible text content
        of the given HTML tags on the current page.

        Args:
            substrings (List[str]): Substrings to search for in the element text.
            tags (List[str]): HTML tag names to inspect (e.g., ['label', 'h1', 'h2']).
            case_sensitive (bool): Whether to match substrings with case sensitivity.

        Returns:
            bool: True if any substring is found in any tag's text content, False otherwise.
        """
        elements = []
        for tag in tags:
            elements.extend(self.driver.find_elements(By.TAG_NAME, tag))

        for el in elements:
            try:
                text = el.text.strip()

                if case_sensitive:
                    match = any(sub in text for sub in substrings)
                else:
                    text_lower = text.lower()
                    match = any(sub.lower() in text_lower for sub in substrings)

                if match:
                    return True
            except Exception:
                continue  # Skip elements that throw exceptions

        return False

    def _reduce_xpath_to_unique_match(self, relative_xpath: str) -> Optional[str]:
        """
        Shortens a complex relative XPath with multiple filters (including contains, @attr)
        and returns the longest version that uniquely identifies one element.
        
        Example:
            "//input[@type='text'][@placeholder='Search'][contains(@class, 'foo')]"
            => "//input[@type='text'][@placeholder='Search']" (if unique)

        :param relative_xpath: Full relative XPath string.
        :return: Longest valid XPath (str) or None.
        """
        # Extract tag and attribute filters
        pattern = r"//(\w+)((\[[^\]]+\])*)"
        match = re.match(pattern, relative_xpath)
        if not match:
            return None  # Invalid XPath structure

        tag = match.group(1)
        attrs_str = match.group(2)

        # Extract all attribute bracketed filters like [@...], [contains(...)], etc.
        attr_filters = re.findall(r"(\[[^\]]+\])", attrs_str)

        # Try reducing attributes from right to left
        for i in reversed(range(len(attr_filters))):
            test_xpath = f"//{tag}" + ''.join(attr_filters[:i+1])
            if self.is_unique_xpath(test_xpath):
                return test_xpath

        # As last resort, try with only the tag (e.g., "//input")
        minimal_xpath = f"//{tag}"
        if self.is_unique_xpath(minimal_xpath):
            return minimal_xpath
        
        return None

    def _clean_dynamic_attributes(self, relative_xpath: str, aggressive: bool = False):

        if not aggressive:
            # Pattern to match any attribute that contains 'value' OR is 'tabindex'
            pattern = r'\[@[^=]*value[^=]*=[^\]]*\]|\[@tabindex=[^\]]*\]'
            # Remove the matched patterns
            cleaned_xpath = re.sub(pattern, '', relative_xpath)
            # Optional: Remove redundant brackets from consecutive conditions
            cleaned_xpath = re.sub(r'\]\[', '][', cleaned_xpath)
            return cleaned_xpath.strip()
        else:
            # Define a list of dynamic attribute patterns to remove
            dynamic_attrs = [
                r'id',
                r'class',
                r'tabindex',
                r'placeholder',
                r'style',
                r'autocomplete',
                r'data-[^=]*',           # matches all data-* attributes
                r'[^=]*value[^=]*'       # matches any attribute name containing "value"
            ]     
            # Combine into a regex to match any of the listed attributes with a value
            pattern = r'\[@(?:' + '|'.join(dynamic_attrs) + r')=[^\]]*\]'
            # Remove all matching attributes from XPath
            cleaned_xpath = re.sub(pattern, '', relative_xpath)
            # Optionally clean up extra brackets between attributes
            cleaned_xpath = re.sub(r'\]\[', '][', cleaned_xpath)
            return cleaned_xpath.strip()

    def remap_relative_xpath(self, xpath: str) -> str | None:
        """
        Attempts to validate and uniquely remap a given relative XPath.

        The method performs the following steps:
        1. Checks if the XPath uniquely identifies one element.
        2. If multiple or no matches, tries to reduce the XPath step-by-step to achieve uniqueness.
        3. Attempts to clean common dynamic attributes in safe mode to improve uniqueness.
        4. If still unsuccessful, performs aggressive attribute cleanup.
        5. Returns the first uniquely matched XPath or None if all attempts fail.

        Args:
            xpath (str): The relative XPath string to validate and remap.

        Returns:
            str | None: A uniquely matched XPath string after remapping or None if no unique match is found.
        """

        count = self.count_elements_by_xpath(xpath)
        if count == 1:
            logger.info("✅  Valid relative XPath found.")
            return xpath
        elif count > 1:
            logger.warning("⚠️  Relative XPath matched multiple elements.")
        else:
            logger.warning("⚠️  Relative XPath matched no elements.")

        # Fallback 1: Try reducing the XPath step by step
        logger.info("🛠️  Trying to reduce relative XPath to unique match...")
        reduced_xpath = self._reduce_xpath_to_unique_match(xpath)
        if reduced_xpath:
            logger.info("🪄  Reduced XPath matched uniquely.")
            return reduced_xpath
        else:
            logger.warning("⚠️  Reduced XPath still invalid.")

        # Fallback 2: Clean dynamic attributes (safe mode)
        logger.info("🧹  Trying to clean common dynamic attributes...")
        cleaned_xpath = self._clean_dynamic_attributes(xpath, aggressive=False)
        if cleaned_xpath and self.count_elements_by_xpath(cleaned_xpath) == 1:
            logger.info("✅ Cleaned XPath (safe mode) matched uniquely.")
            return cleaned_xpath

        # Fallback 3: Clean dynamic attributes (aggressive mode)
        logger.info("⚠️  Safe cleaning failed. Trying aggressive attribute cleanup...")
        cleaned_xpath_aggressive = self._clean_dynamic_attributes(xpath, aggressive=True)
        if cleaned_xpath_aggressive and self.count_elements_by_xpath(cleaned_xpath_aggressive) == 1:
            logger.info("✅  Cleaned XPath (aggressive mode) matched uniquely.")
            return cleaned_xpath_aggressive
        
        logger.warning("⚠️  Unable to remap relative xpath.")
        return None

    def get_validated_xpath(self, element_metadata: Dict[str, Any]) -> str | None:
        """
        Validates and returns a usable XPath from the given element metadata.

        Args:
            element_metadata (Dict[str, Any]): Dictionary containing:
                - "xPath-relative": Relative XPath string

        Returns:
            str | None: A valid, uniquely matching XPath string, or None if not found.
        """
        relative_xpaths: list[str] = []

        xpath_any: str = element_metadata.get("xPath")
        xpath_relative: str = element_metadata.get("xPath-relative")

        # Add xpath_any if it exists, is relative, and not equal to xpath_relative
        if not self.is_absolute_xpath(xpath_any):
            if xpath_any != xpath_relative:
                relative_xpaths.append(xpath_any)
        
        # Add xpath_relative if it exists
        if xpath_relative:
            relative_xpaths.append(xpath_relative)

        for relative_xpath in relative_xpaths:
            logger.debug(f"🔍  Checking relative XPath: {relative_xpath}")
            relative_xpath: str | None = self.remap_relative_xpath(relative_xpath)
            if relative_xpath:
                return relative_xpath

        if self.is_absolute_xpath(xpath_any) and self.is_unique_xpath(xpath_any):
            logger.warning("❗  No valid relative XPath found. Returning valid absolute XPath as last resort.") # Not gurantted to reference to correct element.
            return xpath_any
        
        logger.error("❌  No valid XPath could be found.")
        return None

    def is_field_required(self, element: WebElement) -> bool:
        """Check whether a form field is required based on various attributes and DOM context."""
        
        if element.get_attribute("required") is not None:
            return True
        if element.get_attribute("data-required") is not None and element.get_attribute("data-required").strip().lower() in {"", "true", "1"}:
            return True
        if "true" in (self.search_attribute("required", element) or dict()).values(): # Covers other attributes like "aria-required", etc.
            return True
        if element.get_attribute("aria-invalid") == "true":
            return True

        class_name = element.get_attribute("class") or ""
        if any(keyword in class_name.lower() for keyword in ["required", "error", "has-error"]):
            return True

        try:
            parent = element.find_element(By.XPATH, "./ancestor::*[1]")
            error_spans = parent.find_elements(By.XPATH, ".//*[contains(text(), 'required') or contains(@class, 'error')]")
            for span in error_spans:
                if span.is_displayed():
                    return True
        except Exception:
            pass

        try:
            is_invalid = self.driver.execute_script("return arguments[0].willValidate && !arguments[0].checkValidity();", element)
            if is_invalid:
                return True
        except Exception:
            pass

        return False

    def is_list_type(self, element: WebElement) -> bool:
        return (
            element.get_attribute("role") == "combobox" 
            or element.get_attribute("aria-autocomplete") == "list" 
            or element.get_attribute("list") 
            or self.search_attribute_value(['listbox'], element)
        )

    def xpath_matches_tag(self, xpath: str, tag_name: str) -> bool:
        """
        Check if the final node in an XPath string matches the given tag name.

        Args:
            xpath (str): An absolute or relative XPath.
            tag_name (str): The tag name to check.

        Returns:
            bool: True if the XPath ends with the specified tag, False otherwise.
        """
        if not xpath or not tag_name:
            return False

        # Remove predicates like [@id='main'] or [1]
        xpath_cleaned = re.sub(r'\[[^\]]*\]', '', xpath.strip())

        # Split into parts, ignoring leading/trailing slashes
        parts = xpath_cleaned.strip('/').split('/')

        if not parts:
            return False

        last_tag = parts[-1]

        # Handle wildcard
        if last_tag == '*':
            return tag_name == '*'

        # Check for namespace prefix (e.g., ns:div) and compare only the tag
        last_tag_only = last_tag.split(':')[-1]

        return last_tag_only == tag_name

    def is_xpath_visible(self, xpath: str) -> bool:
        if isinstance(xpath, str):
            is_visible = self.driver.execute_script("return document.evaluate(arguments[0], document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue?.offsetParent !== null;", xpath)
            return True if is_visible else False
        return False

    def query_all_elements(self, tag_names: Optional[Union[str, List[str]]] = '*', predicate_js: Optional[str] = None) -> List[WebElement]:
        """
        Retrieve elements (from both DOM and shadow DOMs) matching tag names and optional JavaScript predicate.

        Args:
            tag_names (str | List[str] | None): Single tag name, list of tag names, or '*' for all. Default is '*'.
            predicate_js (str | None): Optional JavaScript condition as string that receives `el` and returns a boolean.

        Returns:
            List[WebElement]: List of matching WebElement handles.
        """

        js = """
            const tags = arguments[0];
            const predicateSource = arguments[1];

            const matches = [];

            const predicate = predicateSource
                ? new Function('el', predicateSource)
                : null;

            function deepSearch(node) {
                if (!node || node.nodeType !== 1) return;

                const tag = node.tagName.toLowerCase();
                const tagMatches = tags.includes(tag);
                const predMatches = predicate ? predicate(node) : true;

                if (tagMatches && predMatches) {
                    matches.push(node);
                }

                // Recurse into shadow root if present
                if (node.shadowRoot) {
                    Array.from(node.shadowRoot.children).forEach(deepSearch);
                }

                // Recurse into child elements
                Array.from(node.children).forEach(deepSearch);
            }

            deepSearch(document.body);
            return matches;
        """

        # Normalize tag_names input
        if tag_names is None:
            return []

        if isinstance(tag_names, str):
            tag_names = [tag_names.lower()]
        elif isinstance(tag_names, list):
            tag_names = [tag.lower() for tag in tag_names]
        else:
            raise ValueError("tag_names must be a string, list of strings, or None.")

        # If tag_names is ['*'], treat as wildcard
        tags = '*' if tag_names == ['*'] else tag_names

        return self.driver.execute_script(js, tags, predicate_js)


class LinguisticTextEvaluator:

    def __init__(self):
        initialize_nltk_resources()  # Ensures one-time global setup (downloads NLTK resources)

    def _split_tokens(self, text: str):
        """
        Splits camelCase, snake_case, kebab-case, and alphanumeric words
        into lowercase tokens.
        """
        # Replace common separators with space
        text = re.sub(r"[_\-]+", " ", text)
        # Split camelCase (add space before capital letters following lowercase)
        text = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text)
        # Split between letters and numbers
        text = re.sub(r'(?<=[a-zA-Z])(?=[0-9])', ' ', text)
        text = re.sub(r'(?<=[0-9])(?=[a-zA-Z])', ' ', text)

        return text.lower().split()
    
    def _is_valid_token(self, token: str) -> bool:
        """
        Returns True if token is mostly alphabetic and at least 2 characters (not purely numeric or symbolic).
        """
        return re.match(r'^[a-zA-Z]{2,}$', token) is not None

    def _is_technical_token(self, text: str) -> bool:
        """
        Detects whether a token is likely an identifier, internal field name,
        or non-natural linguistic string, with dynamic analysis based on text structure.
        
        Args:
            text (str): The text to evaluate.
            
        Returns:
            bool: True if the text is identified as an identifier, False if it's natural text.
        """
        
        # Early check for empty strings or non-string input
        if not text or not isinstance(text, str):
            return True  # Treat empty strings as identifiers

        # Clean up text (strip leading/trailing spaces)
        text = text.strip()

        # --- 1. Hash-like strings (hexadecimal and long) ---
        if len(text) > 30 and re.fullmatch(r'[a-f0-9]{32,}', text, re.IGNORECASE):
            return True  # Likely a hash value (e.g., SHA256)

        # --- 2. UUID pattern ---
        if re.fullmatch(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', text, re.IGNORECASE):
            return True  # Common UUID format (e.g., '123e4567-e89b-12d3-a456-426614174000')

        # --- 3. Strings with no alphabetic characters ---
        if not re.search(r'[a-zA-Z]', text):
            return True  # If no alphabetic characters, it's likely a code or ID

        # --- 4. Excessive numbers ---
        if sum(c.isdigit() for c in text) / len(text) > 0.5:
            return True  # Mostly numbers, so it's likely a numeric code

        # --- 5. Strings with too many symbols or punctuation ---
        if sum(c in string.punctuation for c in text) / len(text) > 0.5:
            return True  # If punctuation marks dominate the string, it's likely an identifier

        # --- 6. Hyphen or underscore in field names (Dynamic Analysis) ---
        # Checking for multiple fragments separated by hyphens or underscores (e.g., 'user-name', 'email_address')
        if '--' in text or '_' in text:
            # Split text by hyphen or underscore
            fragments = re.split(r'[-_]', text)
            
            # Calculate the percentage of the string affected by these separators
            num_fragments = len(fragments)
            total_length = len(text)
            
            # Set a threshold of 25% or more of the text being split into fragments
            fragment_threshold = 0.25
            if (num_fragments / total_length) > fragment_threshold:
                return True  # If more than 25% of the text is structured, treat as an identifier

        # --- 7. CamelCase with separators ---
        if re.search(r'[a-z][A-Z]', text) and re.search(r'[_\-]', text):
            return True  # CamelCase with underscores or hyphens indicates technical field names

        # --- 8. Short fragments split by hyphens or underscores ---
        parts = re.split(r'[-_]', text)
        if len(parts) >= 3 and all(len(p) <= 4 or p.lower() not in ENGLISH_WORDS for p in parts):
            return True  # If fragmented into short, technical-like words
        
        # If none of the above match, it's likely natural text
        return False

    def is_non_natural_text(self, text: str) -> bool:
        """
        Detects if the input text is primarily an identifier, or contains a significant
        proportion of machine-generated fragments (camelCase, kebab-case, snake_case, etc).
        Returns True if the string is more likely to be a technical identifier than valid text.
        """

        if not text or not isinstance(text, str):
            return True  # Treat empty or invalid input as identifier

        original_text = text.strip()

        # Quick early rejection: very short or entirely alphanumeric gibberish
        if len(original_text) < 5:
            return True

        # --------------------------------------
        # 1. Split text into "words"
        words = re.split(r'\s+', original_text)
        total_words = len(words)

        # Normalize separators for identifier parts
        identifier_like_words = [
            word for word in words
            if re.search(r'[_\-]{1,2}', word)           # snake_case, kebab-case, --delimiter
            or re.search(r'[a-z][A-Z]', word)           # camelCase
            or re.search(r'\w+\d+\w*', word)            # embedded digits
        ]

        identifier_ratio = len(identifier_like_words) / total_words if total_words else 1.0

        # Debug example
        # print(f"[DEBUG] Identifier-like: {identifier_like_words}, ratio={identifier_ratio}")

        # --------------------------------------
        # 2. Heuristic: More than 30% of the words look like identifiers
        if identifier_ratio > 0.3:
            return True

        # --------------------------------------
        # 3. Heuristic: Long sentence with one identifier at end (likely valid)
        if (
            total_words > 5
            and len(identifier_like_words) == 1
            and words[-1] == identifier_like_words[0]
        ):
            return False  # e.g., "Please upload to personalInfoUS--uploadDocument"

        # --------------------------------------
        # 4. Heuristic: If most characters are non-space and non-punctuation
        # Suggests a dense, compact identifier-like blob
        text_no_spaces = re.sub(r'\s+', '', original_text)
        non_alpha_ratio = sum(1 for c in text_no_spaces if not c.isalpha()) / len(text_no_spaces)
        if non_alpha_ratio > 0.5 and total_words <= 3:
            return True

        # --------------------------------------
        # 5. Heuristic: No sentence-like structure (no verbs, no punctuation, no natural phrasing)
        # If the whole string lacks verbs or sentence flow, likely not meaningful
        if not re.search(r'[.?!]', original_text) and total_words <= 4:
            if all(w in identifier_like_words for w in words):
                return True

        return False  # Default: treat as valid natural text

    def is_relevant_string(
        self,
        text: str,
        threshold: float = 0.2,
        min_token_length: int = 3,
        use_stopwords: bool = False,
        use_lemmatizer: bool = False,
        min_relevant_words: int = 2,
        min_valid_phrases: int = 1,
        filter_technical_token: bool = True,
        filter_technical_text: bool = True
    ) -> bool:
        """
        Determines whether a given string is meaningful natural-language text 
        or is likely to be technical metadata, identifiers, or form field names.

        Applies multiple filters:
        - Token-level validation (dictionary, POS tags, stopwords, length)
        - Phrase-level validation using POS-tagged bigrams
        - Global text check to catch full-line identifiers (e.g. "workExperience--startDate")

        Args:
            text (str): The input string to evaluate.
            threshold (float): Proportion of valid English words required to accept.
            min_token_length (int): Minimum length of a token to be considered.
            use_stopwords (bool): Whether to remove common stopwords.
            use_lemmatizer (bool): Whether to lemmatize tokens before checking.
            min_relevant_words (int): Minimum number of valid English tokens required.
            min_valid_phrases (int): Minimum number of valid linguistic bigrams required.
            filter_technical_token (bool): Whether to filter out jargon-like tokens (e.g. "resumeUploader-9").
            filter_technical_text (bool): Whether to discard entire strings that appear technical.

        Returns:
            bool: True if the string is relevant human-readable text, False otherwise.
        """

        # Early rejection for strings that look like structured/technical identifiers
        if filter_technical_text and self.is_non_natural_text(text):
            return False

        # Reject empty or invalid inputs
        if not text or not isinstance(text, str):
            return False

        # Tokenize the input string
        tokens = self._split_tokens(text)
        if not tokens:
            return False

        # Part-of-speech tagging for each token
        tagger = PerceptronTagger()
        tagged_tokens = tagger.tag(tokens)

        valid_tokens = []

        for token, tag in tagged_tokens:
            # Discard technical or non-language tokens like "field--uploadData"
            if filter_technical_token and self._is_technical_token(token):
                continue

            # Skip tokens that aren't valid alphabetic words
            if not self._is_valid_token(token):
                continue

            # Skip very short tokens (noise)
            if len(token) < min_token_length:
                continue

            # Only consider linguistically relevant POS tags
            if tag not in VALID_POS_TAGS:
                continue

            # Optionally filter out stopwords
            if use_stopwords and (token.lower() in STOPWORDS):
                continue

            # Optionally lemmatize (e.g., "running" -> "run")
            if use_lemmatizer:
                token = LEMMATIZER.lemmatize(token)

            # Only accept tokens found in English dictionary
            if token.lower() in ENGLISH_WORDS:
                valid_tokens.append(token.lower())

        # Phrase-level check: count meaningful POS-tagged bigrams
        valid_phrases = 0
        bigrams = list(ngrams(tagged_tokens, 2))
        for (w1, t1), (w2, t2) in bigrams:
            if (t1, t2) in PHRASE_PATTERNS:
                valid_phrases += 1

        # Final decision based on valid token ratio and thresholds
        return (
            (len(valid_tokens) / len(tokens)) >= threshold and
            len(valid_tokens) >= min_relevant_words and
            valid_phrases >= min_valid_phrases
        )

    def filter_normalized_metadata(self, normalized: dict, threshold: float = 0.3) -> str:
        parts = []

        # Flatten and join labels if they exist and are relevant
        
        relevant_labels = [label for label in normalized["labels"] if self.is_relevant_string(label, threshold, min_token_length=3, use_stopwords=False, use_lemmatizer=True, min_relevant_words=2, min_valid_phrases=1, filter_technical_token=True, filter_technical_text=True)]
        if relevant_labels:
            parts.append(f"Label(s): {', '.join(relevant_labels)}")

        # Flatten and join IDs if they exist and are relevant
        relevant_ids = [i for i in normalized["ids"] if self.is_relevant_string(i, threshold, min_token_length=3, use_stopwords=False, use_lemmatizer=False, min_relevant_words=2, min_valid_phrases=0, filter_technical_token=True, filter_technical_text=False)]
        if relevant_ids:
            parts.append(f"Id(s): {', '.join(relevant_ids)}")

        # Name
        if normalized["name"] and self.is_relevant_string(normalized["name"], threshold, min_token_length=3, use_stopwords=False, use_lemmatizer=False, min_relevant_words=1, min_valid_phrases=0, filter_technical_token=True, filter_technical_text=False):
            parts.append(f"Name: {normalized['name']}")

        # Placeholder
        if normalized["placeholder"] and self.is_relevant_string(normalized["placeholder"], threshold, min_token_length=3, use_stopwords=False, use_lemmatizer=False, min_relevant_words=1, min_valid_phrases=0, filter_technical_token=True, filter_technical_text=False):
            parts.append(f"Placeholder: {normalized['placeholder']}")

        if not parts:
            return None  # Skip irrelevant or noisy metadata

        return "\n".join(parts)

class ParsedDataUtils:

    def __init__(self, parsed_data: Dict[str, Any] = dict()):
        self.parsed_data = parsed_data

    def get_fields(self) -> List[Dict[str, Any]]:
        """Returns the fields from the parsed data."""
        return self.parsed_data.get('fields', [])

    def get_field(self, index:int) -> Dict[str, Any]:
        """Returns the field at given index from the parsed data."""
        try:
            fields = self.parsed_data.get('fields', [])
            if index > len(fields)-1:
                logger.error(f"❌ Index out of range. Total {len(fields)} fields. Given index '{index}' as argument.")
            else:
                return fields[index]
        except Exception as e:
            logger.error(e)

    def get_field_index(self, target_field: Dict[str, Any]) -> Optional[int]:
        """Returns the index of the given field in parsed data, if it exists."""
        try:
            fields = self.parsed_data.get('fields', [])
            return fields.index(target_field)
        except ValueError:
            logger.warning("⚠️ Field not found in parsed data.")
        except Exception as e:
            logger.error(f"Error while finding field index: {e}")
        return None

    def get_buttons(self) -> List[Dict[str, Any]]:
        """Returns the buttons from the parsed data."""
        return self.parsed_data.get('buttons', [])

    def get_links(self) -> List[Dict[str, Any]]:
        """Returns the links from the parsed data."""
        return self.parsed_data.get('links', [])

    def match_full_blacklist(self, blacklist: set, candidates: Iterable[str]) -> bool:
        return any(val.lower() in blacklist for val in candidates if val is not None)

    def match_partial_blacklist(self, blacklist: set, candidates: Iterable[str]) -> bool:
        return any(
            partial.lower() in val.lower()
            for val in candidates if val
            for partial in blacklist
        )

    def _is_iterable(self, variable: Any) -> bool:
        return isinstance(variable, Iterable) and not isinstance(variable, (str, bytes))

    def search_items(self, sections: List[str], start_index: int = 0, keys: List[str] = None, substrings: Union[str,Iterable[str]] = None, order_search_by_substring: bool = False, filter_dict: Dict[str, Any] = None, return_first_only : bool = False, normalize_whitespace : bool = False) -> List[Dict[str, Any]]:
        """
        Searches for the first item in the given sections where any of the specified keys
        contains the given substring.

        Args:
            sections (list[str]): Sections to search in (e.g., ['fields', 'buttons']).
            keys (list[str]): Keys to inspect in each item (e.g., ['label-srcTag', 'id']). If 'None', use all keys in item for search.
            substrings (Union[str,Iterable[str]]): Substring (str) or Iterable of substrings to search for. If 'None', return all items matching other parameters like filter.
            order_search_by_substring (bool): Order the search into section(s) by substring (first substring match appendes first). Otherwise, search by seations in top-down fashion, while checking if any substring(s) is/are present. 
            filter_dict (dict[str,Any]): Filter the items before performing search. Only search if the key-value pair exists in the item.
            return_first_only (bool): If True, return the first match only. If False, return all matches.
            normalize_whitespace (bool): If True, spaces will be removed from the values before matching the substring.

        Returns:
            List[Dict]: The first matching item (if `return_first_only` is True), 
            a list of matching items (if `return_first_only` is False), or empty list if no matches are found.
        """
        matched_items = []
        # Refine substrings to remove spaces and convert to lowercase
        if isinstance(substrings, str): # Check if substrings is a string (not a list)
            substrings = [substrings]  # Convert it to a list
        elif self._is_iterable(substrings):
            substrings = list(substrings)
        if substrings:
            for i, substring in enumerate(substrings):  # Enumerate to get the index
                if normalize_whitespace:
                    substring = substring.replace(' ', '')  # Remove spaces
                substrings[i] = substring.lower()  # Update the list element with the modified substring

        if order_search_by_substring:
            for substring in substrings or []:
                for section in sections:
                    for idx, item in enumerate(self.parsed_data.get(section, [])):
                        if idx < start_index:
                            continue
                        if filter_dict and not all(item.get(k) == v for k, v in filter_dict.items()):
                            continue
                        for key in (keys or item.keys()):
                            value = item.get(key)
                            if isinstance(value, str):
                                value = value.lower()
                                match_value = value.replace(' ', '') if normalize_whitespace else value
                                match_substring = substring.replace(' ', '') if normalize_whitespace or key in ["id", "id-custom"] else substring
                                if match_substring in match_value:
                                    if return_first_only:
                                        return [item]
                                    if item not in matched_items:
                                        matched_items.append(item)
                                    break  # Don't double-match same item across keys
        else:
            for section in sections: # Loop through the sections
                for idx, item in enumerate(self.parsed_data.get(section, [])): # Loop through the items in each section
                    if idx < start_index:
                        continue
                    if filter_dict: # Check if filter_dict is provided
                        # If any filter condition is not met, skip this item
                        if not all(item.get(key) == value for key, value in filter_dict.items()):
                            continue
                    if substrings is None: # Return all filtered items (when substring not given)
                        matched_items.append(item)
                        continue
                    item_matched = False  # Flag to track if item has been matched
                    for key in (keys or item.keys()): # Loop through each key in the item. Search all keys if not passed as argument.
                        value = item.get(key)
                        if isinstance(value, str): # Check if the value is a string
                            value = value.lower()  # Convert value to lowercase for case-insensitive comparison
                            
                            # Remove spaces in the value if `normalize_whitespace` is True
                            if normalize_whitespace:
                                value = value.replace(' ', '')

                            for substring in substrings:
                                # Shrink the substring if the key is "id" or "id-custom"
                                if key in ["id", "id-custom"]:
                                    substring = substring.replace(' ', '') # Remove spaces from substring
                                if substring in value: # Check if any of the substring is present in the value
                                    if return_first_only:
                                        return [item] # Return the first match if `return_first_only` is True
                                    item_matched = True  # Mark that the item has been matched
                                    matched_items.append(item)
                                    break # Break out of the loop if a match is found
                        
                        if item_matched:  # Stop checking further keys once we have matched the item
                            break  # Exit the loop for the current item

        return matched_items # Return matched items

    def is_substrings_in_item(self, item: dict, keys: Iterable[str], substrings: Iterable[str], normalize_whitespace: bool = False, exact_match: bool = False, case_sensitive: bool = False) -> bool:
        """
        Checks if any of the provided substrings appear in the values of the specified keys in the item dictionary.

        Args:
            item (dict): The dictionary representing the item to check.
            keys (Iterable[str]): The keys in the item to look into.
            substrings (Iterable[str]): Substrings to search for in the values.
            normalize_whitespace (bool): If True, normalizes whitespace in values and substrings before comparison.
            exact_match (bool): If True, checks for exact match instead of substring containment.
            case_sensitive (bool): If True, performs case-sensitive matching. Defaults to False.

        Returns:
            bool: True if any substring is found in the specified keys' values, False otherwise.
        """
        if not substrings or not keys:
            return False

        if isinstance(substrings, str):
            substrings = [substrings]
        if isinstance(keys, str):
            keys = [keys]

        def normalize(text: str) -> str:
            if normalize_whitespace:
                text = re.sub(r'\s+', '', text.strip())
            return text if case_sensitive else text.lower()

        for key in keys:
            value = item.get(key)
            if value and isinstance(value, str):
                norm_value = normalize(value)
                for substring in substrings:
                    norm_substring = normalize(substring)
                    if (exact_match and norm_value == norm_substring) or (not exact_match and norm_substring in norm_value):
                        return True
        return False

    def is_substrings_in_item_optimized(self, item: dict, keys: Union[List[str], str], substrings: Union[List[str], str], normalize_whitespace: bool = False, exact_match: bool = False, case_sensitive: bool = False, combine_fields: bool = False) -> bool:
        """
        Checks if any of the provided substrings appear in the values of the specified keys in the item dictionary.
        If `combine_fields` is True, all values are joined into a single string before comparison.
        """

        if not substrings or not keys:
            return False

        substrings = [substrings] if isinstance(substrings, str) else substrings
        keys = [keys] if isinstance(keys, str) else keys

        def normalize(text: str) -> str:
            if not case_sensitive:
                text = text.lower()
            return re.sub(r'\s+', '', text) if normalize_whitespace else text

        normalized_substrings = set(normalize(s) for s in substrings)

        if combine_fields:
            combined = " ".join(str(item.get(k, '') or '') for k in keys).strip()
            norm_combined = normalize(combined)
            if exact_match:
                return norm_combined in normalized_substrings
            return any(sub in norm_combined for sub in normalized_substrings)

        else:
            for key in keys:
                val = item.get(key)
                if isinstance(val, str):
                    norm_val = normalize(val)
                    if exact_match:
                        if norm_val in normalized_substrings:
                            return True
                    else:
                        for sub in normalized_substrings:
                            if sub in norm_val:
                                return True

        return False

    def string_match_percentage(self, str1: str, str2: str) -> int:
        """
        Returns a similarity percentage (0 to 100) between two strings.

        Args:
            str1 (str): First string.
            str2 (str): Second string.

        Returns:
            int: Match percentage (0 = no match, 100 = exact match).
        """
        ratio = SequenceMatcher(None, str1.lower(), str2.lower()).ratio()
        return int(round(ratio * 100))

    def is_item_similar(self, item1: Dict, item2: Dict, keys_to_compare: List[str], threshold: int, min_match_count: int = 1) -> bool:
        """
        Compares specified keys between two dictionaries and checks if at least
        `min_match_count` keys meet or exceed the similarity threshold.
        If threshold == 100, uses strict equality.
        Skip if either value is empty, zero, or otherwise falsy

        Args:
            item1 (dict): First item dictionary.
            item2 (dict): Second item dictionary.
            keys_to_compare (list): List of keys to compare.
            threshold (int): Similarity threshold (0-100).
            min_match_count (int): Minimum number of keys that must match

        Returns:
            bool: True if any key's value has similarity >= threshold.
        """

        match_count = 0

        for key in keys_to_compare:
            val1 = item1.get(key)
            val2 = item2.get(key)

            if val1 and val2:
        
                if threshold == 100:
                    if val1 == val2:
                        match_count += 1
                else:
                    similarity = self.string_match_percentage(val1, val2)
                    if similarity >= threshold:
                        match_count += 1

                if match_count >= min_match_count:
                    return True

        return False

    def clean_text(self, raw_text: str) -> str:
        # Remove leading/trailing spaces, newline characters, or special symbols
        cleaned_text = raw_text.strip()
        # Remove any unwanted characters like newlines (\n), special characters (e.g., ), etc.
        cleaned_text = re.sub(r'[^\w\s.,;:*()"\-]', '', cleaned_text)  # Keep only basic punctuation and word chars
        # Replace multiple spaces or newlines with a single space
        cleaned_text = re.sub(r'[\n\s]+', ' ', cleaned_text)
        return cleaned_text.strip()

    def get_item_text(self, item: dict, keys: List[str]):
        return " ".join(str(item.get(k, '') or '') for k in keys).strip()

    def pretty_print(self, data) -> None:
        printer = pprint.PrettyPrinter(indent=4, width=100, sort_dicts=False)
        printer.pprint(data)

    def normalize_metadata(self, element_metadata: Dict[str, Any]) -> dict:
        # Step 1: Normalize label-related fields
        raw_labels = {
            element_metadata.get("label-srcTag"),
            element_metadata.get("label-srcText"),
            element_metadata.get("label-srcAttribute"),
            element_metadata.get("label-custom"),
        }
        labels = list(filter(None, {label.strip() for label in raw_labels if isinstance(label, str)}))

        # Step 2: Normalize id-related fields
        ids = list(filter(None, {
            element_metadata.get("id"),
            element_metadata.get("id-custom")
        }))

        # Step 3: Keep name and placeholder as is
        name = element_metadata.get("name")
        placeholder = element_metadata.get("placeholder")

        return {
            "labels": labels,
            "ids": ids,
            "name": name,
            "placeholder": placeholder
        }

    def filter_metadata(self, section_key: str, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Filters a list of dictionaries within a given section of metadata based on a nested query.

        Parameters:
            section_key (str): The section to filter ('fields', 'buttons', 'links', etc.).
            query (dict): A dictionary with keys representing keys and nested keys (e.g., 'required', 'options.category') and their expected values.

        Returns:
            List[dict]: List of matching dictionaries from the section.
        """
        def match(item: Dict[str, Any], query: Dict[str, Any]) -> bool:
            for key_path, expected_value in query.items():
                keys = key_path.split(".")
                current = item
                for key in keys:
                    if isinstance(current, dict) and key in current:
                        current = current[key]
                    else:
                        return False
                if current != expected_value:
                    return False
            return True

        return [item for item in self.parsed_data.get(section_key, []) if match(item, query)]

    def is_match(self, item: dict, query: dict) -> bool:
        """
        Checks whether a metadata dictionary satisfies a nested query condition.
        
        Supports dot notation in query keys to access nested fields (e.g., "options.category").
        
        Args:
            item (dict): The dictionary to check.
            query (dict): A dictionary of key-value pairs where keys can include dot notation.
        
        Returns:
            bool: True if all query conditions match in item, False otherwise.
        """
        def get_nested_value(d: dict, path: str):
            keys = path.split(".")
            current = d
            for key in keys:
                if not isinstance(current, dict) or key not in current:
                    return None
                current = current[key]
            return current

        for key_path, expected_value in query.items():
            actual_value = get_nested_value(item, key_path)
            if actual_value != expected_value:
                return False
        return True

    def get_nested_value(self, item: dict, key_path: str, default=None):
        """
        Safely retrieves a value from a nested dictionary using dot-separated keys.

        Args:
            item (dict): The dictionary to retrieve data from.
            key_path (str): Dot-separated string representing the key path (e.g. "options.id").
            default (Any): The value to return if any key along the path is missing or invalid.

        Returns:
            The retrieved value, or `default` if the path doesn't exist.
        """
        current = item
        for key in key_path.split('.'):
            if isinstance(current, dict):
                current = current.get(key, default)
            else:
                return default
        return current

    def clean_dynamic_attributes(self, xpath, aggressive:bool = False):

        if not aggressive:
            # Pattern to match any attribute that contains 'value' OR is 'tabindex'
            pattern = r'\[@[^=]*value[^=]*=[^\]]*\]|\[@tabindex=[^\]]*\]'
            # Remove the matched patterns
            cleaned_xpath = re.sub(pattern, '', xpath)
            # Optional: Remove redundant brackets from consecutive conditions
            cleaned_xpath = re.sub(r'\]\[', '][', cleaned_xpath)
            return cleaned_xpath.strip()
        else:
            # Define a list of dynamic attribute patterns to remove
            dynamic_attrs = [
                r'id',
                r'class',
                r'tabindex',
                r'placeholder',
                r'style',
                r'autocomplete',
                r'data-[^=]*',           # matches all data-* attributes
                r'[^=]*value[^=]*'       # matches any attribute name containing "value"
            ]     
            # Combine into a regex to match any of the listed attributes with a value
            pattern = r'\[@(?:' + '|'.join(dynamic_attrs) + r')=[^\]]*\]'
            # Remove all matching attributes from XPath
            cleaned_xpath = re.sub(pattern, '', xpath)
            # Optionally clean up extra brackets between attributes
            cleaned_xpath = re.sub(r'\]\[', '][', cleaned_xpath)
            return cleaned_xpath.strip()

class WebPageParser:
    """
    A class to parse web pages using Selenium WebDriver, extracting key elements
    such as forms, fields, buttons, labels, and metadata. This parser is designed
    to handle both pre-authentication (e.g., login page) and post-authentication
    parsing, adapting to dynamic web structures.
    """

    def __init__(self, driver):
        """
        Initializes the AuthenticatedWebParser with a Selenium WebDriver instance.

        Args:
            driver (WebDriver): The Selenium WebDriver instance to use for parsing.
        """
        self.driver = driver
        self.fields = []
        self.WebParserUtils = WebParserUtils(driver)
        self.ParsedDataUtils = ParsedDataUtils()
        self.dom_contains_xml_namespaces = self.WebParserUtils.detect_xml_namespaces() # If namespace prefixes is detected in page source, then XPath queries may require namespace-aware evaluation

    def set_default(self):

        # If namespace prefixes is detected in page source, then XPath queries may require namespace-aware evaluation
        self.dom_contains_xml_namespaces = self.WebParserUtils.detect_xml_namespaces()

        # Initialize empty fields -> List[Dict] 
        self.fields = []

        # Helps identify change in section
        self.work_experience_initial_comparison_parameters = None # Comparison parameters (e.g. ['job title', 'job role'] if initial work fields relates job-title) of initial field which relates to work experience (Most likely: Job Title or Company)
        self.education_initial_comparison_parameters = None # Comparison parameters (e.g. ['school', 'university'] if initial education fields relates university) of initial field which relates to education section (Most likely: University or Degree)
        self.work_experience_sectionID_primary = 0 # Group counter for work experience section (Example: For 1st work experience, it hold 1 as sectionId). Primarily used to detect new sections and handle date fields.
        self.education_sectionID_primary = 0 # Group counter for education section (Example: For 1st education section, it hold 1 as sectionId). Primarily used to detect new sections and handle date fields.
        self.work_experience_sectionID = { # Define the section ID for each field in work experience section
            'Job Title': 0,
            'Company': 0,
            'Location': 0,
            'I currently work here': 0,
            'Role Description': 0
        }
        self.education_sectionID = { # Define the section ID for each field in education section
            'School or University': 0,
            'Degree': 0,
            'Field of Study or Major': 0,
            'Overall Result (GPA) or Grade': 0,
            'Graduated': 0
        }        
        self.last_edu_or_work_section: Optional[Literal['work-exp', 'edu']] = None # Tracks the latest section type (work experience or education)
        self.verification_digit = 0
    
    def parse_page(self) -> Dict[str, Any]:
        """
        Parses the current page and extracts structured information about
        its key elements.

        Returns:
            Dict[str, Any]: A dictionary containing metadata, forms, buttons,
                             links, tables, and content containers.
        """
        # Initialize default page state by cleaning existing memory.
        self.set_default()

        # Extract 'input: text, checkbox, radio, etc', 'textarea', 'select' fields information
        self._extract_fields()

        # Extract 'button' information
        buttons = self._extract_buttons()
        if not buttons:
            buttons = []

        # Post processing fields (after synchronization with buttons)
        self._post_processing_fields()

        return {
            "metadata": self._get_page_metadata(),
            "fields": self.fields,
            "buttons": buttons,
            "links": self._extract_links(),
            # "tables": self._extract_tables(),
            # "content_containers": self._extract_content_containers()
        }

    def _get_page_metadata(self) -> Dict[str, str]:
        """
        Extracts the page's metadata, including title, URL, and description.

        Returns:
            Dict[str, str]: A dictionary containing the page's metadata.
        """
        return {
            "title": self.driver.title,
            "url": self.driver.current_url,
            "description": self._get_meta_description()
        }

    def _get_meta_description(self) -> Union[str, None]:
        """
        Extracts the meta description from the page, if available.

        Returns:
            Union[str, None]: The meta description or None if not found.
        """
        try:
            return self.driver.find_element(By.CSS_SELECTOR, 'meta[name="description"]').get_attribute("content")
        except Exception:
            return None

    def _extract_fields(self) -> List[Dict[str, Any]]:
        """
        Extracts all input fields on the page, regardless of whether they are
        contained within a <form> element or not.

        Returns:
            List[Dict[str, Any]]: A list of dictionaries containing information
                                   about each input field.
        """
        logger.info("🧼  Fetching and synchronizing input type fields...")
        predicate_js = """
            const tag = el.tagName.toLowerCase();
            const inputType = (el.getAttribute("type") || "").toLowerCase();
            const isListType = (
                el.getAttribute("role") === "combobox" ||
                el.getAttribute("aria-autocomplete") === "list" ||
                el.hasAttribute("list") ||
                (el.outerHTML && el.outerHTML.includes("listbox"))
            );

            return (
                (tag === "input" && !["submit", "button", "reset"].includes(inputType)) ||
                tag === "textarea" ||
                tag === "select" ||
                (tag === "button" && isListType)
            );
        """

        elements: List[WebElement] = self.WebParserUtils.query_all_elements(tag_names=['input', 'textarea', 'select', 'button'], predicate_js=predicate_js)
        # elements: List[WebElement] = self.driver.execute_script("return Array.from(document.querySelectorAll('input'));")
        for element in elements:
            if not ((hidden_value := self.WebParserUtils.search_attribute(['hidden'], element)) and 'true' in map(str.lower, hidden_value.values())):
                # Append to self.fields(type:list) if dictionary is returned
                if (field_info := self._synchronize_fields(self._extract_field_info(element))): self.fields.append(field_info) 
        return self.fields

    def _synchronize_fields(self, field_info: dict) -> Dict[str, Any] | None:
        """
        Synchronizes [currently fetched element -> field_info] with [existing elements -> self.fields] or itself.
        """

        # Return if field_info is None or empty
        if not field_info:
            return None
        
        return_field_info = True # Flag to indicate if field_info should be returned or not

        '''
        Verification Button
        '''
        if field_info['type'] in {'number', 'text'}:
            if (
                self.ParsedDataUtils.is_substrings_in_item(field_info, stardard_field_search_keys, substrings=field_identifiers.get('verification'), normalize_whitespace=True)
                or self.ParsedDataUtils.is_substrings_in_item(field_info, ['placeholder'], ['###'])
            ):
                field_info['options'] = {
                    'category': 'verification',
                    'id': self.verification_digit + 1
                }
                self.verification_digit += 1

        '''
        Identify date field
        '''
        # Check if the field is a date field
        if self.ParsedDataUtils.is_substrings_in_item(field_info, stardard_field_search_keys, field_identifiers.get('date'), normalize_whitespace=True):
            is_date_type = True
            # Exclude based on label length (word count) assumption
            for label_src in standard_label_keys:
                if field_info.get(label_src) and any(date_identifier in field_info.get(label_src) for date_identifier in field_identifiers.get('date')):
                    if len(field_info.get(label_src).split(' ')) > 3 :
                        is_date_type = False
            # Exclude misinterpreted fields (e.g., candidate, update, validate, etc. which has 'date' in their name)
            misidentifiers = ['candidate', 'validate', 'update']
            if self.ParsedDataUtils.is_substrings_in_item(field_info, stardard_field_search_keys, misidentifiers, normalize_whitespace=True):
                is_date_type = False
            if is_date_type and field_info['type'] != 'hidden':
                field_info['type'] = 'datelist' if field_info['type'] == 'list' else 'date'

        '''
        Group related radio/checkbox fields -> merging options into existing field_info
        '''
        if field_info["type"] in {"radio", "checkbox"}: # Only process if it's 'radio' or 'checkbox' type

            # Avoid merging independent checkbox that shares similar metadata
            if (
                not (
                        (
                            self.ParsedDataUtils.is_substrings_in_item(field_info, stardard_field_search_keys, field_identifiers.get('currently_working'), normalize_whitespace=True)
                            or self.ParsedDataUtils.is_substrings_in_item(field_info, stardard_field_search_keys, field_identifiers.get('currently_enrolled'), normalize_whitespace=True)
                    ) and all(v is None or (isinstance(v, str) and len(v.split()) < 5) for k in standard_label_keys if (v := field_info.get(k)) is not None or k in field_info) # ∀(label), length should be less than 5 words
                )
            ):
                
                for existing_field in self.fields:
                    if ((field_info["type"] == "radio" and existing_field["type"] != "radio")
                        or (field_info["type"] == "checkbox" and existing_field["type"] != "checkbox")
                    ):
                        continue
            
                    field_options = field_info["options"]
                    # Condition 1: Check if any of the keys match and are not None (Exact match)
                    # Condition 2 (OR): Check by keys similarity score (Partial match)
                    if (any(field_info[k] and field_info[k] == existing_field[k] for k in ("label-srcText", "label-srcAttribute", "label-custom", "name", "id", "id-custom"))
                        or self.ParsedDataUtils.is_item_similar(field_info, existing_field, ['id', 'id-custom'], threshold=50)
                    ):
                        # Merge options without overwriting existing ones
                        existing_field["options"].update({k: v for k, v in field_options.items() if k not in existing_field["options"]})
                        existing_field["label-srcTag"] = None # Since we are merging, context is lost. Therefore, set to None.
                        return_field_info = False  # Merged successfully. No need to add a new entry.
                        break

        '''
        Work Experience and Education field handling
        '''
        # Helper in segragating fields during search
        is_type_radio_checkbox_textarea_date_datelist = field_info['type'] in {'radio', 'checkbox', 'textarea', 'date', 'datelist'}

        label_length: int = len((field_info.get('label-srcTag') or field_info.get('label-srcText') or '').split())
        max_label_words_work_or_edu: int = 7
        workedu_label_within_limit: bool = (label_length <= max_label_words_work_or_edu)
        if workedu_label_within_limit:
            if self.work_experience_initial_comparison_parameters is None:
                # Check if the field relates job-title
                if self.ParsedDataUtils.is_substrings_in_item(field_info, stardard_field_search_keys, field_identifiers.get('job_title'), normalize_whitespace=True):
                    self.work_experience_initial_comparison_parameters = field_identifiers.get('job_title') # Set the initial field parameters of the work experience section.
                # Check if the field relates to company
                elif self.ParsedDataUtils.is_substrings_in_item(field_info, stardard_field_search_keys, field_identifiers.get('company'), normalize_whitespace=True):
                    self.work_experience_initial_comparison_parameters = field_identifiers.get('company') # Set the initial field parameters of the work experience section.
            if self.education_initial_comparison_parameters is None:
                # Check if the field relates to university or college
                if self.ParsedDataUtils.is_substrings_in_item(field_info, stardard_field_search_keys, field_identifiers.get('school'), normalize_whitespace=True):
                    self.education_initial_comparison_parameters = field_identifiers.get('school') # Set the initial field parameters of the education section.
                # Check if the field relates to degree
                elif self.ParsedDataUtils.is_substrings_in_item(field_info, stardard_field_search_keys, field_identifiers.get('degree'), normalize_whitespace=True):
                    self.education_initial_comparison_parameters = field_identifiers.get('degree') # Set the initial field parameters of the education section.
            
            # Check any of the field categories and update field_info['options']:"Job Title","Company","Location","I currently work here","From Start Date","To End Date","Role Description"
            if self.work_experience_initial_comparison_parameters:

                # Check if the field is work experience related and update section IDs accordingly
                if (
                    self.ParsedDataUtils.is_substrings_in_item(field_info, stardard_field_search_keys, self.work_experience_initial_comparison_parameters, normalize_whitespace=True)
                    and not is_type_radio_checkbox_textarea_date_datelist
                ):
                    self.last_edu_or_work_section = 'work-exp' # Set the latest work/edu section type to work experience
                    self.work_experience_sectionID_primary += 1 # Increment the groupId indicating new work experience section

                # Check if the field relates to job-title
                if (
                    self.ParsedDataUtils.is_substrings_in_item(field_info, stardard_field_search_keys, field_identifiers.get('job_title'), normalize_whitespace=True)
                    and not is_type_radio_checkbox_textarea_date_datelist
                ):
                    if (not self.work_experience_sectionID['Job Title'] < TOTAL_JOBS_ENTRY) or (field_info['type'] == 'hidden'):
                        return None
                    self.work_experience_sectionID['Job Title'] += 1 # Increment the groupId indicating new job title section
                    field_info['options'] = {
                        'category': 'Work Experience',
                        'id': self.work_experience_sectionID['Job Title'],
                        'type': 'Job Title'
                    }
                # Check if the field relates to company
                elif (
                    self.ParsedDataUtils.is_substrings_in_item(field_info, stardard_field_search_keys, field_identifiers.get('company'), normalize_whitespace=True)
                    and not is_type_radio_checkbox_textarea_date_datelist
                ):
                    if (not self.work_experience_sectionID['Company'] < TOTAL_JOBS_ENTRY) or (field_info['type'] == 'hidden'):
                        return None
                    self.work_experience_sectionID['Company'] += 1 # Increment the groupId indicating new company section
                    field_info['options'] = {
                        'category': 'Work Experience',
                        'id': self.work_experience_sectionID['Company'],
                        'type': 'Company'
                    }
                # Check if the field relates to location
                elif (
                    self.ParsedDataUtils.is_substrings_in_item(field_info, stardard_field_search_keys, field_identifiers.get('location'), normalize_whitespace=True)
                    and not is_type_radio_checkbox_textarea_date_datelist
                ):
                    if (self.ParsedDataUtils.is_substrings_in_item(field_info, ["id", "id-custom"], ['work'], normalize_whitespace=True)
                        or self.WebParserUtils.search_attribute_value(['work','experience'], field_info['webElement'])
                    ):
                        # Exclude if entry not coming from field and at the same time entry limit has reached, to avoid overlap or mis-interpretation through extra fields.
                        if (not self.work_experience_sectionID['Location'] < TOTAL_JOBS_ENTRY) or (field_info['type'] == 'hidden'):
                            return None
                        self.work_experience_sectionID['Location'] += 1 # Increment the groupId indicating new location section
                        field_info['options'] = {
                            'category': 'Work Experience',
                            'id': self.work_experience_sectionID['Location'],
                            'type': 'Location'
                        }
                # Check if the field relates to current work status
                elif (
                    self.ParsedDataUtils.is_substrings_in_item(field_info, stardard_field_search_keys, field_identifiers.get('currently_working'), normalize_whitespace=True)
                    and field_info['type'] == 'checkbox'
                    and self.last_edu_or_work_section == 'work-exp'
                    and all(v is None or (isinstance(v, str) and len(v.split()) < 8) for k in standard_label_keys if (v := field_info.get(k)) is not None or k in field_info) # ∀(label), length should be less than 8 words
                ):
                    # Exclude if entry not coming from field and at the same time entry limit has reached, to avoid overlap or mis-interpretation through extra fields.
                    if (not self.work_experience_sectionID['I currently work here'] < TOTAL_JOBS_ENTRY) or (field_info['type'] == 'hidden'):
                        return None
                    self.work_experience_sectionID['I currently work here'] += 1 # Increment the groupId indicating new current work status section
                    field_info['options'] = {
                        'category': 'Work Experience',
                        'id': self.work_experience_sectionID['I currently work here'],
                        'type': 'I currently work here'
                    }
                # Check if the field relates to role description
                elif (
                    self.ParsedDataUtils.is_substrings_in_item(field_info, stardard_field_search_keys, field_identifiers.get('role_description'), normalize_whitespace=True)
                    and (field_info['webElement'].tag_name == "textarea") or (field_info['type'] == 'text' and field_info['required'] == 'false') 
                ):
                    # Exclude if entry not coming from field and at the same time entry limit has reached, to avoid overlap or mis-interpretation through extra fields.
                    if (not self.work_experience_sectionID['Role Description'] < TOTAL_JOBS_ENTRY) or (field_info['type'] == 'hidden'):
                        return None
                    self.work_experience_sectionID['Role Description'] += 1 # Increment the groupId indicating new role description section
                    field_info['options'] = {
                        'category': 'Work Experience',
                        'id': self.work_experience_sectionID['Role Description'],
                        'type': 'Role Description'
                    }

            # Check any of the field categories and update field_info['options']:"School or University","Degree","Field of Study or Major","Overall Result (GPA) or Grade","Graduated","From Start Date","To End Date (Actual or Expected)"
            if self.education_initial_comparison_parameters:

                # Check if the field is education related and update section IDs accordingly
                if (
                    self.ParsedDataUtils.is_substrings_in_item(field_info, stardard_field_search_keys, self.education_initial_comparison_parameters, normalize_whitespace=True)
                    and not is_type_radio_checkbox_textarea_date_datelist
                ):
                    self.last_edu_or_work_section = 'edu' # Set the latest work/edu section type to education
                    self.education_sectionID_primary += 1 # Increment the groupId indicating new education section

                # Check if the field relates to school or university
                if (
                    self.ParsedDataUtils.is_substrings_in_item(field_info, stardard_field_search_keys, field_identifiers.get('school'), normalize_whitespace=True)
                    and not is_type_radio_checkbox_textarea_date_datelist
                ):
                    # Exclude if entry not coming from field and at the same time entry limit has reached, to avoid overlap or mis-interpretation through extra fields.
                    if (not self.education_sectionID['School or University'] < TOTAL_EDUCATION_ENTRY) or (field_info['type'] == 'hidden'):
                        return None
                    self.education_sectionID['School or University'] += 1 # Increment the groupId indicating new school/university section
                    field_info['options'] = {
                        'category': 'Education',
                        'id': self.education_sectionID['School or University'],
                        'type': 'School or University'
                    }
                # Check if the field relates to degree
                elif (
                    self.ParsedDataUtils.is_substrings_in_item(field_info, stardard_field_search_keys, field_identifiers.get('degree'), normalize_whitespace=True)
                    and not is_type_radio_checkbox_textarea_date_datelist
                ):
                    # Exclude if entry not coming from field and at the same time entry limit has reached, to avoid overlap or mis-interpretation through extra fields.
                    if (not self.education_sectionID['Degree'] < TOTAL_EDUCATION_ENTRY) or (field_info['type'] == 'hidden'):
                        return None
                    self.education_sectionID['Degree'] += 1 # Increment the groupId indicating new degree section
                    field_info['options'] = {
                        'category': 'Education',
                        'id': self.education_sectionID['Degree'],
                        'type': 'Degree'
                    }
                # Check if the field relates to field of study or major
                elif (
                    self.ParsedDataUtils.is_substrings_in_item(field_info, stardard_field_search_keys, field_identifiers.get('field_of_study'), normalize_whitespace=True)
                    and not is_type_radio_checkbox_textarea_date_datelist
                ):
                    # Exclude if entry not coming from field and at the same time entry limit has reached, to avoid overlap or mis-interpretation through extra fields.
                    if (not self.education_sectionID['Field of Study or Major'] < TOTAL_EDUCATION_ENTRY) or (field_info['type'] == 'hidden'):
                        return None
                    self.education_sectionID['Field of Study or Major'] += 1 # Increment the groupId indicating new field of study/major section
                    field_info['options'] = {
                        'category': 'Education',
                        'id': self.education_sectionID['Field of Study or Major'],
                        'type': 'Field of Study or Major'
                    }
                # Check if the field relates to overall result (GPA) or grade
                elif (
                    self.ParsedDataUtils.is_substrings_in_item(field_info, stardard_field_search_keys, field_identifiers.get('gpa_or_grade'), normalize_whitespace=True)
                    and not is_type_radio_checkbox_textarea_date_datelist
                ):
                    # Exclude if entry not coming from field and at the same time entry limit has reached, to avoid overlap or mis-interpretation through extra fields.
                    if (not self.education_sectionID['Overall Result (GPA) or Grade'] < TOTAL_EDUCATION_ENTRY) or (field_info['type'] == 'hidden'):
                        return None
                    self.education_sectionID['Overall Result (GPA) or Grade'] += 1 # Increment the groupId indicating new overall result/grade section
                    field_info['options'] = {
                        'category': 'Education',
                        'id': self.education_sectionID['Overall Result (GPA) or Grade'],
                        'type': 'Overall Result (GPA) or Grade'
                    }
                # Check if the field relates to current enrollment status
                elif (
                    self.ParsedDataUtils.is_substrings_in_item(field_info, stardard_field_search_keys, field_identifiers.get('currently_enrolled'), normalize_whitespace=True)
                    and field_info['type'] == 'checkbox'
                    and self.last_edu_or_work_section == 'edu'
                    and all(v is None or (isinstance(v, str) and len(v.split()) < 8) for k in standard_label_keys if (v := field_info.get(k)) is not None or k in field_info) # ∀(label), length should be less than 8 words
                ):
                    # Exclude if entry not coming from field and at the same time entry limit has reached, to avoid overlap or mis-interpretation through extra fields.
                    if (not self.fields_parse_ongoing or self.education_sectionID['Graduated'] < TOTAL_EDUCATION_ENTRY) or (field_info['type'] == 'hidden'):
                        return None
                    self.education_sectionID['Graduated'] += 1 # Increment the groupId indicating new current work status section
                    field_info['options'] = {
                        'category': 'Education',
                        'id': self.education_sectionID['Graduated'],
                        'type': 'Graduated'
                    }

        '''
        Date field handling
        '''
        def is_date_variant_in_metadata(date_format_variants):
            """
            This function checks if any of the given date_format_variants is found in the element metadata.
            """
            # Check if any of the substrings (e.g., "DD/MM/YYYY", "Day", "YYYY", etc.) is found in the element's metadata keys
            for date_format in date_format_variants:
                if self.ParsedDataUtils.is_substrings_in_item(field_info, ["placeholder"], [date_format], exact_match=True, case_sensitive=False):
                    return True
                elif self.ParsedDataUtils.is_substrings_in_item(field_info, ["placeholder", "label-srcAttribute", "label-custom", "id", "id-custom", "label-srcTag", "label-srcText", "name"], [date_format], normalize_whitespace=True, case_sensitive=True):
                    return True
            return False

        def get_date_base_format():
            """
            Determines the base date format of a web form element based on common date format variants.

            This function checks the metadata of a form element against predefined date format variants 
            (e.g., "MM/DD/YYYY", "Month/Year", "Day", etc.) to identify the base format category 
            (such as "MMDDYYYY", "MMYYYY", "DD", etc.).

            Returns:
                str or None: The matching base date format key (e.g., "MMDDYYYY", "MMYYYY"), or 
                None if no known format matches the element metadata.

            Dependencies:
                `self.is_date_variant_in_metadata(variants)` 
                is a helper function that checks whether any variant in the list is present 
                in the given metadata.
            """

            # Define a mapping of date formats and corresponding format types with possible variants
            date_formats = {
                "MMDDYYYY": ["MM/DD/YYYY", "MM-DD-YYYY", "month.day.year", "month-day-year"],
                "DDMMYYYY": ["DD/MM/YYYY", "DD-MM-YYYY", "day.month.year", "day-month-year"],
                "MMYYYY": ["MM/YYYY", "Month/Year", "Month Year", "month-year"],
                "DD": ["DD", "Day", ".day", "-day"],
                "MM": ["MM", "Month", ".month", "-month"],
                "YYYY": ["YYYY", "Year", ".year", ]
            }

            # Iterate over the date_formats mapping to check each date type in the element_metadata
            for base_format, date_format_variants in date_formats.items():
                if is_date_variant_in_metadata(date_format_variants):
                    return base_format
            return None
        
        # Check if the field is a date field
        if field_info['type'] in {'date', 'datelist'}:

            ''' Get the base format'''
            # Get the base_format of date (e.g., 'MMDDYYY', 'YYYY', 'DD', 'MMYYYY', etc.)
            base_format = get_date_base_format()
            if not base_format:
                # Flatten and normalize all relevant metadata fields into a single lowercase string
                flatten_field_data = self.ParsedDataUtils.get_item_text(field_info, ["placeholder", "label-srcAttribute", "label-custom", "id", "id-custom", "label-srcTag", "label-srcText", "name"])
                # Check presence of date components
                has_day = 'DD' in flatten_field_data
                has_month = 'MM' in flatten_field_data
                has_year = 'YYYY' in flatten_field_data
                if not (has_day or has_month or has_year):
                    has_day = 'day' in flatten_field_data
                    has_month = 'month' in flatten_field_data
                    has_year = 'year' in flatten_field_data
                
                if not (has_day or has_month or has_year):

                    if field_info['webElement'].get_attribute('type') == 'text':
                        # Fallback assigning default base format if the field is text type.
                        base_format = 'MMDDYYYY'
                    else:
                        logger.warning("❓  Unable to determine base date format from metadata.")

                else:
                    # Decide the most likely base format based on components found
                    if has_day and has_month and has_year:
                        base_format = 'MMDDYYYY'
                    elif has_month and has_year:
                        base_format = 'MMYYYY'
                    elif has_day and not has_month and not has_year:
                        base_format = 'DD'
                    elif has_month and not has_day and not has_year:
                        base_format = 'MM'
                    elif has_year and not has_day and not has_month:
                        base_format = 'YYYY'

                

            # Check if the field is a start date field
            if (self.ParsedDataUtils.is_substrings_in_item(field_info, stardard_field_search_keys, field_identifiers.get('start_date'), normalize_whitespace=True)
                or self.ParsedDataUtils.is_substrings_in_item(field_info, stardard_field_search_keys, field_identifiers.get('start_date_case_sensitive'), normalize_whitespace=True, case_sensitive=True)
            ): 
                if self.last_edu_or_work_section == 'work-exp' and workedu_label_within_limit:
                    field_info['options'] = {
                        'category': 'Work Experience',
                        'id': self.work_experience_sectionID_primary,
                        'type': 'From Start Date',
                        'format': base_format
                    }
                elif self.last_edu_or_work_section == 'edu' and workedu_label_within_limit:
                    field_info['options'] = {
                        'category': 'Education',
                        'id': self.education_sectionID_primary,
                        'type': 'From Start Date',
                        'format': base_format
                    }
                else:
                    field_info['options'] = {
                        'category': 'other',
                        'id': 0,
                        'type': 'From Start Date',
                        'format': base_format
                    }
            # Check if the field is an end date field
            elif (self.ParsedDataUtils.is_substrings_in_item(field_info, stardard_field_search_keys, field_identifiers.get('end_date'), normalize_whitespace=True)
                or self.ParsedDataUtils.is_substrings_in_item(field_info, stardard_field_search_keys, field_identifiers.get('end_date_case_sensitive'), normalize_whitespace=True, case_sensitive=True)
            ):    
                if self.last_edu_or_work_section == 'work-exp' and workedu_label_within_limit:
                    field_info['options'] = {
                        'category': 'Work Experience',
                        'id': self.work_experience_sectionID_primary,
                        'type': 'To End Date',
                        'format': base_format
                    }
                elif self.last_edu_or_work_section == 'edu' and workedu_label_within_limit:
                    field_info['options'] = {
                        'category': 'Education',
                        'id': self.education_sectionID_primary,
                        'type': 'To End Date (Actual or Expected)',
                        'format': base_format
                    }
                else:
                    field_info['options'] = {
                        'category': 'other',
                        'id': 0,
                        'type': 'To End Date',
                        'format': base_format
                    }
            # Neither Start/End Date
            else:
                field_info['options'] = {
                    'category': 'other',
                    'id': 0,
                    'type': '',
                    'format': base_format
                }

        '''
        File upload field handling
        '''
        if (
            self.WebParserUtils.get_tag_name(field_info['xPath']) in {'input', 'button'}
            and (
                field_info['type'] == 'file' 
                or self.WebParserUtils.search_attribute_value(field_identifiers.get('resume'), field_info['webElement'])
                or self.ParsedDataUtils.is_substrings_in_item(field_info, stardard_field_search_keys, field_identifiers.get('upload_file'), normalize_whitespace=True)
            ) 
        ):

            field_info['type'] = 'file'
            # Exclude Dropbox, Google Drive, etc. file upload fields
            if self.ParsedDataUtils.is_substrings_in_item(field_info, stardard_field_search_keys, field_identifiers.get('cloud_or_mannual_upload'), normalize_whitespace=True):
                return_field_info = False # Exclude this field from being added to the list
            else:
                # Check if the field is a resume upload field
                if (self.ParsedDataUtils.is_substrings_in_item(field_info, stardard_field_search_keys, field_identifiers.get('resume'), normalize_whitespace=True)
                    or self.WebParserUtils.search_attribute_value(field_identifiers.get('resume'), field_info['webElement'])
                ):
                    field_info['options'] = {
                        'category': 'file-upload',
                        'type': 'resume'
                    }
                else:
                    field_info['options'] = {
                        'category': 'file-upload',
                        'type': 'other'
                    }
            
        # Final call
        if return_field_info:
            return field_info # Return a synchronized item
        else:
            return None # Return None if item merged successfully or a junk entry.

    def _extract_field_info(self, element: WebElement, force_insert: bool = False, payload: dict = {}) -> Dict[str, Any] | None:
        """
        Extracts detailed information about a given input field element.

        Args:
            element: The input field element to extract information from.

        Returns:
            Dict[str, Any]: A dictionary containing detailed information about
                             the input field element, including its type, name,
                             label, placeholder, required status, and more.
        """
        # Check if field is hidden or non-interactable for users.
        if element.get_attribute("type") == 'hidden' and not element.is_enabled(): 
            return None

        ''' Initialize xPath '''
        field_xPath = self.WebParserUtils.get_xpath(element, verify_xpath=True) or None    # Could be absolute or relative (1st try for absolute)
        if not field_xPath: return None # Exclude field element if xPath doesn't exists
        field_relative_xPath = field_xPath if not self.WebParserUtils.is_absolute_xpath(field_xPath) else self.WebParserUtils.compute_relative_xpath_selenium(element, optimized=False)
        
        # Exclude headder/footer fields
        if self.WebParserUtils.is_absolute_xpath(field_xPath):
            if 'header' in field_xPath or 'footer' in field_xPath: # Return fields if they are contained in header or footer
                return None
        else:
            # For relative xPath, we use element-traceback approach to identify if it's contained within header or footer. 
            if self.WebParserUtils.is_element_in_tag(element, ['header','footer']):
                return None
            
        ''' Initialize Field Type '''
        field_type = element.get_attribute("type") or element.tag_name
        if element.tag_name == 'select': field_type = 'select'
        if element.tag_name == 'textarea': field_type = 'textarea'
        # Check for 'combobox' role, ARIA autocomplete, or 'list' attribute for <datalist>, or 'listbox' as attribute's value.
        if self.WebParserUtils.is_list_type(element): field_type = 'list' # For dynamic dropdown field.

        # Initialize Labels 
        field_labelSrcTag = self._get_field_label(element)
        field_label_attributes : dict = self.WebParserUtils.search_attribute(["label"], element)
        field_labelSrcAttribute = next(iter(field_label_attributes.values()), None) if field_label_attributes else None
        field_labelSrcAttribute = val if field_labelSrcAttribute is None and (val := element.get_attribute("aria-label")) not in ["", None] else field_labelSrcAttribute
        field_labelCustom = (diff_set := set((field_label_attributes or {}).values()).difference({element.get_attribute("label")})) and diff_set.pop() or None
        field_labelSrcText = self.WebParserUtils.find_associated_text(field_xPath)
        # Initialize IDs
        field_id = val if (val := element.get_attribute("id")) not in [""] else None
        field_customId = (diff_set := set((self.WebParserUtils.search_attribute(["id"], element) or {}).values()).difference({element.get_attribute("id")})) and diff_set.pop() or None
        # Required
        field_required = self.WebParserUtils.is_field_required(element)
        field_required = True if field_required or ((field_labelSrcTag and (field_labelSrcTag[0] == '*' or field_labelSrcTag[-1] == '*')) or (field_labelSrcText and field_labelSrcText[-1] == '*')) else False
        # Placeholder
        if element.tag_name.lower() == 'button':    # Treat 'inner text' as placeholder  
            field_placeholder = self.ParsedDataUtils.clean_text(element.text.strip())
        else:
            field_placeholder = val if (val := element.get_attribute("placeholder")) not in [""] else None

        ''' Execute BLACKLISTED '''
        if not force_insert:
            if not field_required: # Execute Blacklist check over 'optional' fields
                # Exclude field that fully/partially matchs the respective blacklist
                if (
                    # Exclude BLACKLISTED field label 
                    self.ParsedDataUtils.match_full_blacklist(config.blacklist.field_blacklist_label_full, (field_labelSrcTag, field_labelSrcText, field_labelSrcAttribute, field_labelCustom))
                    or self.ParsedDataUtils.match_partial_blacklist(config.blacklist.field_blacklist_label_partial, (field_labelSrcTag, field_labelSrcText, field_labelSrcAttribute, field_labelCustom))
                    # Exclude BLACKLISTED field id
                    or self.ParsedDataUtils.match_full_blacklist(config.blacklist.field_blacklist_id_full, (field_id, field_customId))
                    or self.ParsedDataUtils.match_partial_blacklist(config.blacklist.field_blacklist_id_partial, (field_id, field_customId)) 
                    # Exclude BLACKLISTED field placeholder
                    or self.ParsedDataUtils.match_full_blacklist(config.blacklist.field_blacklist_placeholder_full, (field_placeholder,))
                    or self.ParsedDataUtils.match_partial_blacklist(config.blacklist.field_blacklist_placeholder_partial, (field_placeholder,))
                ):
                    return None

                # Exclude BLACKLISTED field attribute values
                for full in config.blacklist.field_blacklist_attribute_value_full: # Check for full blacklist matches first
                    if any((attr['value'] or '').lower() == full.lower() for attr in element.get_property('attributes')):
                        return None  # Return None if there's a full match
                for partial in config.blacklist.field_blacklist_attribute_value_partial: # Check for partial blacklist matches if no full match was found
                    if any(partial.lower() in (attr['value'] or '').lower() for attr in element.get_property('attributes')):
                        return None  # Return None if there's a partial match
                
        ''' Initialize Name '''
        field_name = val if (val := element.get_attribute("name")) else None
                
        ''' Initialize Value '''
        field_value = val if (val := element.get_attribute("value")) not in [""] else None

        field_options = None
        # Find the first attribute whose name contains 'multiselect' and ends with '-id' or '_id' (case-insensitive),
        # and assign it to multiselectId_attr; return None if no such attribute is found.
        multiselectId_attr = next((attr for attr in element.get_property('attributes') if 'multiselect' in attr['name'].lower() and re.search(r'[-_]id$', attr['name'].lower())), None)
        if multiselectId_attr:
            field_type = 'multiselect'
            field_options = multiselectId_attr['value']
        elif field_type == 'select' or element.tag_name == 'select':
            field_options = self._extract_select_options(element)
        elif field_type == 'radio' or field_type == 'checkbox':
            if field_labelSrcTag:
                field_options = {field_labelSrcTag:field_xPath}
            elif field_labelSrcAttribute:
                field_options = {field_labelSrcAttribute:field_xPath}
            elif field_labelCustom:
                field_options = {field_labelCustom:field_xPath}
            elif field_labelSrcText:
                field_options = {field_labelSrcText:field_xPath}

        ''' BLACKLIST By Field Type '''
        if not force_insert:
            # Exclude field that fully/partially matchs the respective blacklist based on its field type.
            standard_field_search_candidates = (field_labelSrcTag, field_labelSrcText, field_labelSrcAttribute, field_labelCustom, field_name, field_id, field_customId, field_placeholder)
            if field_type == 'text':
                if (
                    self.ParsedDataUtils.match_full_blacklist(config.blacklist.text_type_blacklist_full, standard_field_search_candidates)
                    or self.ParsedDataUtils.match_partial_blacklist(config.blacklist.text_type_blacklist_partial, standard_field_search_candidates)    
                ):
                    return None
            elif field_type == 'list':
                if (
                    self.ParsedDataUtils.match_full_blacklist(config.blacklist.list_type_blacklist_full, standard_field_search_candidates)
                    or self.ParsedDataUtils.match_partial_blacklist(config.blacklist.list_type_blacklist_partial, standard_field_search_candidates)    
                ):
                    return None
            elif field_type == 'multiselect':
                if (
                    self.ParsedDataUtils.match_full_blacklist(config.blacklist.multiselect_type_blacklist_full, standard_field_search_candidates)
                    or self.ParsedDataUtils.match_partial_blacklist(config.blacklist.multiselect_type_blacklist_partial, standard_field_search_candidates)    
                ):
                    return None
            elif field_type == 'select':
                if (
                    self.ParsedDataUtils.match_full_blacklist(config.blacklist.dropdown_type_blacklist_full, standard_field_search_candidates)
                    or self.ParsedDataUtils.match_partial_blacklist(config.blacklist.dropdown_type_blacklist_partial, standard_field_search_candidates)    
                ):
                    return None

        # Check the visibility of element using WebElement or xPath through JS
        ''' 
                > Set `field_type` to hidden. 
                > If the field relates to button, update `field_type -> button` and `field's xPath -> button's xPath`.
                > Delete leftover `field_type -> hidden` in post-cleaning process.
        '''
        if not self.WebParserUtils.is_xpath_visible(field_xPath):
            field_type = 'hidden'
        
        field_info = {
            "label-srcTag": field_labelSrcTag,
            "label-srcText": field_labelSrcText,
            "label-srcAttribute": field_labelSrcAttribute,
            "label-custom": field_labelCustom,
            "label-parent": payload.get('label-parent'),
            "name": field_name,
            "id": field_id,
            "id-custom": field_customId,
            "type":  field_type,
            "required": field_required,
            "placeholder": field_placeholder,
            "value": field_value,
            "options": field_options,
            "webElement": element,
            "xPath": field_xPath,
            "xPath-relative": field_relative_xPath
        }

        return field_info

    def _post_processing_fields(self) -> None:

        ''' Delete entries where `field_type -> hidden` '''
        self.fields = [field for field in self.fields if field.get('type') != 'hidden']

    def _extract_buttons(self) -> List[Dict[str, Any]]:
        """
        Extracts all buttons on the page.

        Returns:
            List[Dict[str, Any]]: A list of dictionaries containing information
                                   about each button.
        """
        buttons = []
        logger.info("🧼  Fetching and synchronizing button-like elements...")
        predicate_js = """
            const tag = el.tagName.toLowerCase();
            const type = el.getAttribute("type");
            const isListType = (
                el.getAttribute("role") === "combobox" ||
                el.getAttribute("aria-autocomplete") === "list" ||
                el.hasAttribute("list") ||
                (el.outerHTML && el.outerHTML.includes("listbox"))
            );

            return !isListType && (
                tag === "button" ||
                (tag === "input" && ["submit", "button", "reset"].includes(type)) ||
                el.getAttribute("role") === "button"
            );
        """
        elements: List[WebElement] = self.WebParserUtils.query_all_elements(tag_names = ["button", "input"], predicate_js = predicate_js)
        for btn in elements:
            if (button_info := self._synchronize_button(self._extract_button_info(btn))): buttons.append(button_info)
        return buttons

    def _synchronize_button(self, button_info: Optional[Dict[str, Any]]) -> Dict[str, Any] | None:
        """
        Synchronizes [currently fetched element -> button_info] with [existing fields elements -> self.fields]
        """

        if not button_info:
            return None

        ''' Discard Empty Button '''
        if (
            not button_info.get("label-srcTag")
            and not button_info.get("label-srcText")
            and not button_info.get("label-custom")
            and not button_info.get("name")
            and not button_info.get("text")
            and not button_info.get("id")
            and not button_info.get("id-custom")
        ):
            return None # Don't append

        ''' Correct button type '''

        '''
        File upload field handling
        '''
        if (
            self.WebParserUtils.get_tag_name(button_info['xPath']) in {'input', 'button'}
            and (
                button_info['type'] == 'file' 
                or self.WebParserUtils.search_attribute_value(field_identifiers.get('resume'), button_info['webElement'])
                or self.ParsedDataUtils.is_substrings_in_item(button_info, stardard_button_search_keys, field_identifiers.get('upload_file'), normalize_whitespace=True)
            ) 
        ):

            button_info['type'] = 'file'
            # Exclude Dropbox, Google Drive, etc. file upload fields
            if self.ParsedDataUtils.is_substrings_in_item(button_info, stardard_button_search_keys, field_identifiers.get('cloud_or_mannual_upload'), normalize_whitespace=True):
                return None # Exclude this button from being added to the list
            else:
                # Check if the field is a resume upload field
                if (self.ParsedDataUtils.is_substrings_in_item(button_info, stardard_button_search_keys, field_identifiers.get('resume'), normalize_whitespace=True)
                    or self.WebParserUtils.search_attribute_value(field_identifiers.get('resume'), button_info['webElement'])
                ):
                    button_info['name'] = 'Resume'
                else:
                    button_info['name'] = 'Other'
                return button_info

        '''
        Merges button element into a matching input entry (within self.fields) if they both are associated with same field.
        '''
        if button_info.get('type') != 'submit':
            for field in self.fields:
                if any(button_info[k] not in {None, ''} and button_info[k] == field.get(k) for k in ("label-srcTag", "label-srcText", "label-custom", "name", "id", "id-custom", "value")): # MATCH FOUND
                    # Match Found

                    # Mapping of dynamic list with optional xPath of button.
                    if field['type'] == 'list':
                        field['xPath'] = button_info['xPath-relative']

                    # Selectively update values
                    for k, v in button_info.items():
                        if v is not None:
                            if k in field:
                                if (field[k] is None): # Only update if the field value is None
                                    field[k] = v
                                if (v) and (k in ('id', 'id-custom')) and (field['type'] == 'file'): # Force edit for 'id' if file type
                                    field[k] = v
                    
                    # Ensure 'hidden' fiels are mapped with buttons
                    #  Note: All left-over hidden fields are later removed in post-cleaning process.
                    if field['type'] == 'hidden' and button_info['type'] != 'file':
                        field['type'] = 'button'
                        field['xPath'] = button_info['xPath-relative']

                    return None # Merged successfully

        # No match found, should be added as a new entry.
        return button_info 

    def _extract_button_info(self, element: WebElement, force_insert: bool = False) -> Dict[str, Any] | None:

        # Initialize xPath
        button_xPath = self.WebParserUtils.get_xpath(element, verify_xpath=True) # Compute xPath
        # Exclude button element if xPath doesn't exists
        if not button_xPath: return None
        button_relative_xPath = button_xPath if not self.WebParserUtils.is_absolute_xpath(button_xPath) else self.WebParserUtils.compute_relative_xpath_selenium(element, optimized=False)

        # Get button type
        has_type_attr = self.driver.execute_script("return arguments[0].hasAttribute('type');", element)
        button_type = element.get_attribute("type") if has_type_attr else "button"
        # Final cleaning of button_type.
        button_type = "button" if button_type not in {"submit"} else button_type

        # Get button text
        if element.tag_name.lower() == 'input': # Could be type -> 'button', 'submit', or 'reset'
            button_text = val if (val := element.get_attribute("value")) else None
        else:
            button_text = button_text if (button_text := self.ParsedDataUtils.clean_text(element.text.strip())) != '' else None
            if not button_text:
                button_text = val if (val := element.get_attribute("title")) not in [""] else None

        # Get button ID
        button_id = val if (val := element.get_attribute("id")) not in [""] else None
        button_id_attributes = self.WebParserUtils.search_attribute(["id"], element)
        button_customId = (diff_set := set((button_id_attributes or {}).values()).difference({element.get_attribute("id")})) and diff_set.pop() or None

        # Get Label
        button_labelSrcTag = self._get_field_label(element)
        button_labelCustom = (diff_set := set((self.WebParserUtils.search_attribute(["label"], element) or {}).values()).difference({element.get_attribute("label")})) and diff_set.pop() or None
        button_labelSrcText = None
        if force_insert and not self.dom_contains_xml_namespaces:
            if self.WebParserUtils.is_absolute_xpath(button_xPath):
                button_labelSrcText = self.WebParserUtils.find_associated_text(button_xPath)
        
        # Get name
        button_name = val if (val := element.get_attribute("name")) not in [""] else None
        if not button_name:
            button_name = val if (val := element.get_attribute("title")) not in [""] else None

        '''
        Disable blacklist when `force_insert` is set True.
        '''
        if not force_insert:
            ''' Exclude headder/footer button '''
            if self.WebParserUtils.is_absolute_xpath(button_xPath):
                if (
                    ('header' in button_xPath) 
                    or ('footer' in button_xPath and button_type != 'submit')
                ): # Return fields if they are contained in 'header' or 'footer with non-submit type'
                    return None
            else:
                # For relative xPath, we use element-traceback approach to identify if it's contained within header or footer. 
                if (
                    self.WebParserUtils.is_element_in_tag(element, ['header','footer'])
                    and button_type != 'submit'
                ):
                    return None

            ''' Exclude BLACKLISTED button attribute values '''
            match_found = False
            # Check full blacklist first
            for full in config.blacklist.button_blacklist_attribute_value_full:
                # Exclude button if any of its attribute value exactly matchs the full blacklist
                if any((attr['value'] or '').lower() == full.lower() for attr in element.get_property('attributes')):
                    match_found = True
                    break
            # Check partial blacklist if no full match was found
            if not match_found:
                for partial in config.blacklist.button_blacklist_attribute_value_partial:
                    # Exclude button if any of its attribute value partially matchs the partial blacklist
                    if any(partial.lower() in (attr['value'] or '').lower() for attr in element.get_property('attributes')):
                        match_found = True
                        break
            if match_found:
                return None  # Skip this button and move to the next one

            ''' Exclude BLACKLISTED buttons text '''
            # Exclude button that match the full blacklist
            if self.ParsedDataUtils.match_full_blacklist(config.blacklist.button_blacklist_text_full, (button_text,)):
                # If button_text is empty and 'onclick' attribute is not None, skip continue
                if button_text == '' and element.get_attribute('onclick') is not None:
                    pass  # Do not continue, allow processing of this button
                else:
                    return None  # Continue to the next button otherwise
            # Exclude button that partially match any keyword in the partial blacklist
            if self.ParsedDataUtils.match_partial_blacklist(config.blacklist.button_blacklist_text_partial, (button_text,)):
                return None

            ''' Exclude BLACKLISTED buttons id '''
            # Exclude button that match the full blacklist
            if self.ParsedDataUtils.match_full_blacklist(config.blacklist.button_blacklist_id_full, (button_id, button_customId)):
                return None
            # Exclude button that partially matchs any keyword in the partial blacklist
            if self.ParsedDataUtils.match_partial_blacklist(config.blacklist.button_blacklist_id_partial, (button_id, button_customId)):
                return None

            ''' Label lookup BLACKLIST '''
            search_label_text = True
            # Check if the button has visible text
            if element.text != '' and element.tag_name == 'button':
                # Disable label lookup that match the full blacklist (based on Text)
                if self.ParsedDataUtils.match_full_blacklist(config.blacklist.find_associated_text_blacklist_text_full, (button_text,)):
                    search_label_text = False
                # Disable label lookup that match the full blacklist (based on ID)
                if self.ParsedDataUtils.match_full_blacklist(config.blacklist.find_associated_text_blacklist_id_full, (button_id, button_customId)):
                    search_label_text = False
                # Disable label lookup that match the partial blacklist (based on Text)
                if self.ParsedDataUtils.match_partial_blacklist(config.blacklist.find_associated_text_blacklist_text_partial, (button_text,)):
                    search_label_text = False
                # Disable label lookup that match the partial blacklist (based on ID)
                if self.ParsedDataUtils.match_partial_blacklist(config.blacklist.find_associated_text_blacklist_id_partial, (button_id, button_customId)):
                    search_label_text = False
            # Search associated label text if the buttons' id/text was not blacklisted
            if search_label_text and not self.dom_contains_xml_namespaces:
                if self.WebParserUtils.is_absolute_xpath(button_xPath):
                    button_labelSrcText = self.WebParserUtils.find_associated_text(button_xPath)

            '''' Exclude BLACKLISTED buttons label '''
            # Exclude button that match the full blacklist
            if self.ParsedDataUtils.match_full_blacklist(config.blacklist.button_blacklist_label_full, (button_labelSrcTag, button_labelSrcText, button_labelCustom)):
                return None
            # Exclude button that partially match any keyword in the partial blacklist
            if self.ParsedDataUtils.match_partial_blacklist(config.blacklist.button_blacklist_label_partial, (button_labelSrcTag, button_labelSrcText, button_labelCustom)):
                return None

        ''' Refine metadata '''
        if button_labelSrcText is None:
            if any('resume' in (btn_id or '').lower() for btn_id in [button_id, button_customId]):
                button_labelSrcText = "Resume"

        button_info = {
            "label-srcTag": button_labelSrcTag,
            "label-srcText": button_labelSrcText,
            "label-custom": button_labelCustom,
            "name": button_name,
            "text": button_text,
            "id": button_id,
            "id-custom": button_customId,
            "type": button_type,
            "value": val if (val := element.get_attribute("value")) else None,
            "disabled": element.get_attribute("disabled") is not None,
            "webElement": element,
            "xPath": button_xPath,
            "xPath-relative": button_relative_xPath
        }

        return button_info
    
    def _extract_links(self) -> List[Dict[str, Any]]:
        """
        Extracts all links on the page.

        Returns:
            List[Dict[str, Any]]: A list of dictionaries containing information
                                   about each link.
        """
        links = []
        logger.info("🧼  Fetching and synchronizing links...")
        elements: List[WebElement] = self.WebParserUtils.query_all_elements(tag_names = ["a"])
        for link_el in elements:
            # Append to links(type:list) if dictionary is returned
            if (link_info := self._synchronize_link(self._extract_link_info(link_el))): links.append(link_info)
        return links

    def _synchronize_link(self, link_info: dict) -> Dict[str, Any] | None:
        """
        Synchronizes links by filtering and other operations.
        """
        # Return if link_data is None or empty
        if not link_info:
            return None
        
        link_whitelist = set(start_apply_btn_identifiers).union(
                                                            signup_auth_btn_identifiers,
                                                            signin_auth_btn_identifiers,
                                                            verify_auth_btn_identifiers,
                                                            other_auth_btn_identifiers
                                                        )

        # List of whitelisted link texts
        if not self.ParsedDataUtils.is_substrings_in_item(link_info, ["text"], link_whitelist, normalize_whitespace=True, exact_match=True, case_sensitive=False):
            return None # Exclude if not in whitelist
        return link_info

    def _extract_link_info(self, element: WebElement) -> Dict[str, Any] | None:

        # Initialize xPath
        link_xPath = self.WebParserUtils.get_xpath(element) # Compute xPath
        # Exclude button element if xPath doesn't exists
        if not link_xPath: return None
        link_relative_xPath = link_xPath if not self.WebParserUtils.is_absolute_xpath(link_xPath) else self.WebParserUtils.compute_relative_xpath_selenium(element, optimized=False)

        link_labelSrcTag = self._get_field_label(element)
        field_labelSrcText = None
        if self.WebParserUtils.is_absolute_xpath(link_xPath):
            field_labelSrcText = self.WebParserUtils.find_associated_text(link_xPath)

        link_info = {
            "label-srcTag": link_labelSrcTag,
            "label-srcText": field_labelSrcText,
            "text": element.text.strip(),
            "href": element.get_attribute("href"),
            "rel": element.get_attribute("rel"),
            'type': 'link',
            "webElement": element,
            "xPath": link_xPath,
            "xPath-relative": link_relative_xPath
        }

        return link_info

    def _extract_tables(self) -> List[Dict[str, Any]]:
        """
        Extracts all tables on the page.

        Returns:
            List[Dict[str, Any]]: A list of dictionaries containing information
                                   about each table.
        """
        tables = []
        for table in self.driver.find_elements(By.TAG_NAME, 'table'):
            table_data = {
                "headers": [th.text.strip() for th in table.find_elements(By.TAG_NAME, 'th')],
                "rows": [[td.text.strip() for td in tr.find_elements(By.TAG_NAME, 'td')]
                         for tr in table.find_elements(By.TAG_NAME, 'tr')],
                "selectors": self._get_element_selectors(table)
            }
            tables.append(table_data)
        return tables

    def _extract_content_containers(self) -> List[Dict[str, Any]]:
        """
        Extracts all content containers on the page.

        Returns:
            List[Dict[str, Any]]: A list of dictionaries containing information
                                   about each content container.
        """
        containers = []
        container_types = ['header', 'section', 'article', 'aside', 'nav', 'div', 'span', 'label', 'p']

        for container_type in container_types:
            for container in self.driver.find_elements(By.TAG_NAME, container_type):
                container_data = {
                    "type": container_type,
                    "text": container.text.strip(),
                    "selectors": self._get_element_selectors(container)
                }
                containers.append(container_data)
        return containers

    def _get_field_label(self, element: WebElement) -> Optional[str]:
        """
        Extracts the label associated with a given input field element.

        Args:
            element: The input field element to extract the label for.

        Returns:
            Union[str, None]: The text of the associated label element, or None
                               if no label is found.
        """

        labelCustom = (diff_set := set((self.WebParserUtils.search_attribute(["label"], element) or {}).values()).difference({element.get_attribute("label")})) and diff_set.pop() or None
        defaultId = val if (val := element.get_attribute("id")) not in [""] else None
        customId = (diff_set := set((self.WebParserUtils.search_attribute(["id"], element) or {}).values()).difference({element.get_attribute("id")})) and diff_set.pop() or None

        # Extract all possible ID values that could be associated with label element
        possible_ids = set()
        if labelCustom:
            possible_ids.update(labelCustom.split(' '))
        if defaultId:
            possible_ids.update(defaultId.split(' '))
        if customId:
            possible_ids.update(customId.split(' '))

        # Try to find the label for each possible_id for both "for" and "id" attributes
        for label_id in possible_ids:
            try:
                # Check if label for this id exists
                label = self.driver.find_element(By.CSS_SELECTOR, f'label[for="{label_id}"]')
                label = self.ParsedDataUtils.clean_text(label.text.strip())
                if label: 
                    return label
            except:
                pass  # If not found, continue to next block

            try:
                # Check if label with id attribute exists
                label = self.driver.find_element(By.CSS_SELECTOR, f'label[id="{label_id}"]')
                label = self.ParsedDataUtils.clean_text(label.text.strip())
                if label:
                    return label
            except:
                pass  # If not found, continue to next iteration

        try:
            # Find the label associated by proximity
            label = element.find_element(By.XPATH, f'./ancestor::label')
            label = self.ParsedDataUtils.clean_text(label.text.strip())
            if label:
                return label
        except:
            pass

        try:
            # Check for preceding label
            label = self.driver.execute_script("""
                var el = arguments[0];
                var label = el.previousElementSibling;
                if (label && label.tagName.toLowerCase() === 'label') {
                    return label.textContent.trim();
                }
                return null;
            """, element)
            label = self.ParsedDataUtils.clean_text(label)
            if label:
                return label
        except:
            pass

        return None

    def _extract_select_options(self, select_element: WebElement) -> List[Dict[str, str]]:
        """
        Extracts the options from a given select element.

        Args:
            select_element: The select element to extract options from.

        Returns:
            List[Dict[str, str]]: A list of dictionaries containing the value
                                   and text of each option in the select element.
        """
        options = []

        # Loop through each <option> element in the dropdown
        for option in select_element.find_elements(By.TAG_NAME, 'option'):
            option_value = option.get_attribute("value")
            option_text = self.ParsedDataUtils.clean_text(option.text.strip())

            ''' Exclude BLACKLISTED options ''' 
            # Check for exact match (full match)
            if self.ParsedDataUtils.match_full_blacklist(config.blacklist.dropdown_option_blacklist_full, (option_text,)):
                continue  # Skip this option, it's blacklisted
            # Check for partial match (substring match)
            if self.ParsedDataUtils.match_partial_blacklist(config.blacklist.dropdown_option_blacklist_partial, (option_text,)):
                continue # Skip this option, it's blacklisted

            ''' Add to the options list '''
            options.append({"value": option_value, "text": option_text})
        
        return options
                
    def _get_element_selectors(self, element: WebElement) -> Dict[str, str]:
        """
        Extracts various selectors for a given element.
        
        Args:
        element: The element to extract selectors for.
        
        Returns:
        Dict[str, str]: A dictionary containing the XPath, CSS selector,
        test ID, and aria-label for the element.
        """
        field_xPath = self.WebParserUtils.get_xpath(element)
        field_labelSrcText = None
        if self.WebParserUtils.is_absolute_xpath(field_xPath):
            field_labelSrcText = self.WebParserUtils.find_associated_text(field_xPath)
            
        return {
            "xpath": field_xPath,
            "id": (attr_vals := self.WebParserUtils.search_attribute(['label'], element)).pop() if attr_vals else None,
            "label-srcText": field_labelSrcText,
            "label-srcAttribute": (attr_vals := self.WebParserUtils.search_attribute(['label'], element)) and attr_vals.pop() if attr_vals else None
        }

    def get_submit_buttons(self, visible_only: bool = True) -> List[WebElement]:
        """
        Returns <button type="submit"> elements from the current page.

        Args:
            visible_only (bool): If True, returns only visible buttons. If False, returns all matching buttons.

        Returns:
            List[WebElement]: A list of WebElement instances matching <button type="submit">.
        """
        buttons = self.driver.find_elements("xpath", "//button[@type='submit']")
        return [btn for btn in buttons if btn.is_displayed()] if visible_only else buttons

    def get_required_fields(self) -> list[WebElement]:
        """
        Identify input fields that appear required or invalid based on HTML attributes and visible error indicators.

        Returns:
            List[WebElement]: List of input elements that are likely required or invalid.
        """
        required_fields = []
        input_elements = self.driver.find_elements(By.XPATH, "//input | //textarea | //select")

        for element in input_elements:
            if self.WebParserUtils.is_field_required(element):
                required_fields.append(element)

        return required_fields


class HtmlDiffer:

    def __init__(self):
        self.parent_paths = []

    def get_xpath(self, element, root):
        """Generate XPath of element relative to root"""
        return root.getroottree().getpath(element)

    def compare_elements(self, el_x, el_y, root_x, root_y):
        """
        Recursively compare two elements. If el_y is new or modified compared to el_x,
        return the new element. Also store the parent XPath where the change starts if applicable.
        """
        # Guard: If el_y is None, there's nothing to compare
        if el_y is None:
            return None

        # If el_x is None, el_y is new
        if el_x is None:
            # Get parent of el_y in tree_y and check if it exists in tree_x
            parent_el_y = el_y.getparent()
            if parent_el_y is not None:
                parent_xpath_y = self.get_xpath(parent_el_y, root_y)
                # Check if parent exists in tree_x
                if root_x.xpath(parent_xpath_y):
                    self.parent_paths.append(parent_xpath_y)
            return el_y

        # If tag or attributes differ, treat as modified
        if el_x.tag != el_y.tag or el_x.attrib != el_y.attrib:
            return el_y

        # If text content differs, treat as modified
        if (el_x.text or '').strip() != (el_y.text or '').strip():
            return el_y

        # Compare children recursively
        children_x = list(el_x)
        children_y = list(el_y)
        max_len = max(len(children_x), len(children_y))

        new_children = []
        for i in range(max_len):
            child_x = children_x[i] if i < len(children_x) else None
            child_y = children_y[i] if i < len(children_y) else None
            diff_child = self.compare_elements(child_x, child_y, root_x, root_y)
            if diff_child is not None:
                new_children.append(diff_child)

        if new_children:
            el_copy = lxml_html.Element(el_y.tag, el_y.attrib)
            el_copy.text = el_y.text
            for child in new_children:
                el_copy.append(child)
            return el_copy

        return None

    def html_diff(self, html_x, html_y) -> Union[str, List[str]]:
        """
        Computes the difference in DOM structure from html_x to html_y.
        Returns the new or modified elements as HTML string and the parent XPaths where changes start.
        """
        tree_x = lxml_html.fromstring(html_x)
        tree_y = lxml_html.fromstring(html_y)

        self.parent_paths = []
        diffs = []

        body_x = tree_x.find('.//body')
        body_y = tree_y.find('.//body')

        if body_x is not None and body_y is not None:
            for child_y in body_y:
                matched = None
                for child_x in body_x:
                    if child_x.tag == child_y.tag and child_x.attrib == child_y.attrib:
                        matched = child_x
                        break
                diff = self.compare_elements(matched, child_y, tree_x, tree_y)
                if diff is not None:
                    diffs.append(diff)
        else:
            diff = self.compare_elements(tree_x, tree_y, tree_x, tree_y)
            if diff is not None:
                diffs.append(diff)

        html_diffs = "\n".join(tostring(el, encoding='unicode').strip() for el in diffs)
        return html_diffs, self.parent_paths
