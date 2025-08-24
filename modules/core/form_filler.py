# modules/form_filler.py
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, ElementNotInteractableException, StaleElementReferenceException, InvalidElementStateException, ElementClickInterceptedException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.common.alert import Alert
from selenium.webdriver.support.select import Select
from typing import Dict, List, Any, Union, Optional, Literal, Iterable, Tuple
import json
import time
from datetime import datetime
import re
import logging
from lxml import html as lxml_html, etree
from lxml.html import tostring
import os
from pathlib import Path
# Modules Import
from modules.core.web_parser import field_identifiers, stardard_field_search_keys, standard_label_keys
from modules.core.web_parser import WebParserUtils, ParsedDataUtils, HtmlDiffer, LinguisticTextEvaluator
from modules.core.upload_manager import queue_file_upload
from modules.utils.logger_config import setup_logger
from langchain_core.prompts import ChatPromptTemplate
from modules.prompt_engine import PromptAgent
import config.env_config as env_config 
from selenium.webdriver.common.action_chains import ActionChains
import config.blacklist
import config.user_data_config as user_data_config
import config.system_config as system_config

logger = setup_logger(__name__, level=env_config.LOG_LEVEL, log_to_file=False)

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

def _generate_question_prompt(metadata: str) -> str:
    template = """Below given is the metadata of a field from the job application form.
    
Extract a clear question or title (label) from the given metadata without explanations or additional comments.
If relevant field label already exist in 'Label(s):', return it exactly, otherwise use the overall context of metadata to return the most appropriate label.

<metadata>
{metadata}
</metadata>

Return format: Do not give clarifications, justifications, description, etc. Also don't mention if the label was found or not in metadata. Directly return the consise field's 'label' only (could be in few words).
"""
    return ChatPromptTemplate.from_template(template).format_messages(
        metadata=metadata
    )[0].content

def _orphan_options_prompt(options: list[str], multi_select: bool = False) -> str:
    
    choices = "\n".join([f"- {opt}" for opt in options])
    
    instruction = (
        "Select *all* options that are most appropriate one based on reasonable assumptions."
        if multi_select else
        "Select the *one best option* based on reasonable assumptions."
    )

    template = """You are a helpful assistant that answers job application questions.

The question for this field is not available! 
Rely on reasonable assumptions and common best practices to select the most appropriate {return_format} based on typical job application behavior for this unknown field.

<options>
{choices}
</options>

{instruction}

Return only the exact text of the selected {return_format}, with no explanations or additional comments. Do not repeat the question, and do not mention the context or your reasoning.
NOTE: If none clearly apply, directly return 'N/A' text as output to this prompt (return one word 'N/A' if {return_format} {choice_scope} inappropriate, or could hinder my chances of hiring if I select).
Do not mention the context, reasoning process, or how you chose the answer.
"""

    prompt = ChatPromptTemplate.from_template(template)
    
    return prompt.format_messages(
        choices=choices,
        instruction=instruction,
        return_format="options (as a list)" if multi_select else "option",
        choice_scope="are" if multi_select else "is"
    )[0].content

def _update_set(valid_set, *args):
    """
    Adds one or more strings, or a list of strings to the set.

    Args:
        valid_set (set): The set to be updated.
        *args: The strings or list(s) of strings to add to the set.

    Returns:
        None: The set is updated in place.
    """
    # Check if args contains a list
    for item in args:
        if isinstance(item, str):
            valid_set.add(item)  # Add the single string to the set
        elif isinstance(item, list):
            valid_set.update(item)  # If it's a list, add all elements in the list
        else:
            raise ValueError(f"Unsupported type: {type(item)}. Only strings or lists of strings are supported.")

def find_matching_option(possible_answers: Iterable[str], option_keys: Iterable[str], exact_match: bool = False, normalize_whitespace: bool = False, case_sensitive: bool = False) -> int | None:
    """
    Finds the index of the first matching option from option_keys that matches a value in possible_answers.

    Args:
        possible_answers (Iterable[str]): Iterable of answer options to check (e.g., list, set).
        option_keys (Iterable[str]): Iterable of options to compare against.
        exact_match (bool): If True, looks for an exact string match.
        normalize_whitespace (bool): If True, strips and collapses whitespace before comparison.
        case_sensitive (bool): If True, comparisons are case-sensitive.

    Returns:
        Optional[int]: Index of the first matching item in option_keys or None if no match.
    """
    def normalize(text: str) -> str:
        if normalize_whitespace:
            text = re.sub(r'\s+', '', text.strip())
        return text if case_sensitive else text.lower()

    # Convert iterables to lists for indexing
    option_keys = list(option_keys)
    possible_answers = list(possible_answers)

    option_keys_processed = [normalize(key) for key in option_keys]
    answers_processed = [normalize(ans) for ans in possible_answers]

    for answer in answers_processed:
        if exact_match:
            if answer in option_keys_processed:
                return option_keys_processed.index(answer)
        else:
            for i, key in enumerate(option_keys_processed):
                if answer in key:
                    return i
    return None

class FormInteractorUtils:

    def __init__(self, driver):
        self.driver = driver
        self.WebParserUtils = WebParserUtils(driver)

    def click_safe_heading_to_unfocus(self):
        """
        Simulates a real mouse click on a safe DOM element (like a heading) to unfocus or dismiss listboxes.
        Works across modern JavaScript frameworks like React, Angular, Vue, etc.

        Args:
            driver (selenium.webdriver): The active Selenium WebDriver instance.

        Returns:
            bool: True if click dispatched successfully, False otherwise.
        """
        js_script = """
            (function() {
                const target = document.querySelector("h1, h2, h3, h4, h5, h6, p, div");
                if (target) {
                    const rect = target.getBoundingClientRect();
                    const x = rect.left + 5;
                    const y = rect.top + 5;

                    ['mousedown', 'mouseup', 'click'].forEach(type => {
                        const event = new MouseEvent(type, {
                            view: window,
                            bubbles: true,
                            cancelable: true,
                            clientX: x,
                            clientY: y
                        });
                        target.dispatchEvent(event);
                    });

                    return true;
                } else {
                    return false;
                }
            })();
        """
        return self.driver.execute_script(js_script)

    def scroll_to_element(self, element_or_xpath: Union[str, WebElement]) -> bool:
        try:
            if isinstance(element_or_xpath, str):
                element = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, element_or_xpath))
                )
            elif isinstance(element_or_xpath, WebElement):
                element = element_or_xpath
            else:
                return False

            self.driver.execute_script(
                "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element
            )

            # Wait until the element's Y coordinate is stable
            previous_y = None
            for _ in range(10):  # Check up to 10 times
                current_y = self.driver.execute_script("return arguments[0].getBoundingClientRect().top;", element)
                if previous_y is not None and abs(current_y - previous_y) < 1:
                    break  # Scrolling has stabilized
                previous_y = current_y
                time.sleep(1)

            time.sleep(0.5)
            return True

        except Exception as e:
            print(f"[!] Error scrolling to an element: {e}")
            return False
        
    def click_action_chain(self, element) -> None:
        ActionChains(self.driver).move_to_element(element).click().perform()

    def click_js_dispatch_mouse_event(self, xpath) -> None:
        self.driver.execute_script("""
            const xpath = arguments[0];
            const el = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
            if (el) {
                ['mousedown', 'mouseup', 'click'].forEach(type => {
                    const event = new MouseEvent(type, {
                        view: window,
                        bubbles: true,
                        cancelable: true
                    });
                    el.dispatchEvent(event);
                });
            }
        """, xpath)

    def click(self, xpath: str, scroll: bool = True, raise_on_fail: bool = False) -> bool:
        """
        Attempts to click an element using JavaScript first (document.evaluate), 
        then with smooth scrolling fallback using self.driver.execute_script, 
        and finally with Selenium click if both fail.

        Args:
            xpath (str): The target element's XPath.
            scroll (bool): Whether to scroll to the element before clicking.
            raise_on_fail (bool): If True, raises the encountered exception instead of returning False.

        Returns:
            bool: True if click was successful, otherwise False (unless raise_on_fail=True).
        """
        def handle_click(element) -> bool:
            """
            Attempts to click the given element using multiple fallback strategies:
            1. ActionChains
            2. JavaScript mouse event dispatch
            3. JavaScript scroll + click
            4. JavaScript element.click()
            5. Selenium's element.click()

            Returns:
                bool: True if click succeeded, False otherwise.
            """
            try:
                if scroll:
                    self.scroll_to_element(element)

                # Method 1: ActionChains (most human-like and reliable for many UIs)
                try:
                    self.click_action_chain(element)
                    time.sleep(1)
                    logger.info("✅  Click successful via ActionChains.")
                    return True
                except Exception as e:
                    logger.warning(f"⚠️  ActionChains click failed: {e}")

                # Method 2: JS Dispatch Mouse Events
                try:
                    self.click_js_dispatch_mouse_event(xpath)
                    time.sleep(0.5)
                    logger.info("✅  Click successful via JS dispatchEvent.")
                    return True
                except Exception as e:
                    logger.warning(f"⚠️  JS dispatchEvent failed: {e}")

                # Method 3: JS scrollIntoView + click
                try:
                    self.driver.execute_script("""
                        const el = arguments[0];
                        if (el) {
                            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            el.click();
                        }
                    """, element)
                    time.sleep(0.5)
                    logger.info("✅  Click successful via JS scroll + click.")
                    return True
                except Exception as e:
                    logger.warning(f"⚠️  JS scroll + click failed: {e}")

                # Method 4: JS element.click()
                try:
                    self.driver.execute_script("""
                        const xpath = arguments[0];
                        const el = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                        if (el) el.click();
                    """, xpath)
                    time.sleep(0.5)
                    logger.info("✅  Click successful via JS element.click().")
                    return True
                except Exception as e:
                    logger.warning(f"⚠️  JS element.click() failed: {e}")

                # Method 5: Selenium's built-in element.click()
                try:
                    if element.is_enabled():
                        element.click()
                        WebDriverWait(self.driver, 10).until(
                            lambda d: d.execute_script("return document.readyState") == "complete"
                        )
                        time.sleep(0.5)
                        logger.info("✅  Click successful via Selenium element.click().")
                        return True
                    else:
                        raise InvalidElementStateException("Element is not interactable.")
                except (ElementClickInterceptedException, NoSuchElementException, InvalidElementStateException) as e:
                    logger.error(f"🔴  Selenium element.click() failed: {e}")
                    if raise_on_fail:
                        raise e
                except Exception as e:
                    logger.error(f"🔴  General Selenium click failed: {e}")
                    if raise_on_fail:
                        raise e

            except Exception as outer:
                logger.error(f"🔴  Click operation fully failed: {outer}")
                if raise_on_fail:
                    raise outer

            return False

        # Handle the case where xpath is a string and looking for matching elements
        if isinstance(xpath, str):
            elements = self.driver.find_elements(By.XPATH, xpath)
            for element in elements:
                if handle_click(element):
                    return True
            return False
        else:
            err = ValueError("Invalid argument: XPath must be a string")
            logger.error(err)
            if raise_on_fail:
                raise err
            return False
        
    def open_link(self, href: str, open_in_new_tab: bool = True) -> bool:
        try:
            if open_in_new_tab:
                # Open in new tab
                self.driver.execute_script("window.open(arguments[0], '_blank');", href)
                # Wait until the page is fully loaded
                self.WebParserUtils.wait_for_stable_dom(padding=1)
                # Switch to new tab
                self.driver.switch_to.window(self.driver.window_handles[-1])
            else:
                # Open in same tab
                self.driver.get(href)
                # Wait until the page is fully loaded
                self.WebParserUtils.wait_for_stable_dom(padding=1)
            return True
        except Exception as e:
            print(f"Failed to open link: {e}")
            return False

    def is_interactable(self, xpath: str) -> bool:
        """
        Check if an element is interactable using JavaScript evaluation via XPath.
        
        Args:
            driver (WebDriver): Selenium WebDriver instance.
            xpath (str): XPath string to locate the element.

        Returns:
            bool: True if the element is visible, enabled, and not read-only. False otherwise.
        """

        # JavaScript function to check if element is interactable (enabled)
        js_script = """
        return (function(xpath) {
            try {
                const result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                const elem = result.singleNodeValue;
                if (!elem) return false;
                return !elem.disabled;  // Check if the element is not disabled
            } catch (e) {
                return false;
            }
        })(arguments[0]);
        """
 
        try:
            # Execute script to check if the element is interactable
            return self.driver.execute_script(js_script, xpath)
        except Exception as e:
            logger.error(f"🔸  Failed to evaluate XPath: {xpath} — {e}")
            return False

    def clear_input_field(self, xpath: str, allow_click: bool = True, raise_or_fail: bool = False) -> bool:
        """
        Attempts to clear an input field identified by an XPath.
        Tries multiple fallback methods if the standard ones fail.

        Args:
            xpath (str): XPath string to locate the input field.
            allow_click (bool): Control whether to use methods involving click as fallback or just pure JS.
            raise_or_fail (bool): Whether to raise exceptions on failure (default False).

        Returns:
            bool: True if cleared successfully, False otherwise.

        Raises:
            Exception: If raise_or_fail is True and all clearing methods fail.
        """
        # --- Method to check if element is cleared ---
        def is_cleared(element):
            """Returns True if the element is cleared (value is empty or no text)."""
            value = element.get_attribute("value")
            # Check if value is empty or if no text content is present
            return value == "" or not value or element.get_attribute('textContent').strip() == ""

        # --- Fallback 1: JS Method using XPath --- 
        try:
            success = self.driver.execute_script("""
                return (function(xpath) {
                    const result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                    const input = result.singleNodeValue;
                    if (input && input instanceof HTMLElement && !input.disabled && !input.readOnly) {
                        input.focus();
                        input.value = "";  // Clear the value
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                        
                        // Retry mechanism with a small delay to check if the value is empty
                        let attempt = 0;
                        let maxRetries = 5;
                        let delay = 100;    // 100ms delay for checking
                        
                        while (attempt < maxRetries) {
                            // Check if the value is actually cleared    
                            if (input.value === "") {
                                return true;  // Successfully cleared
                            }
                            // Wait for a small delay before the next check
                            var startTime = new Date().getTime();
                            while (new Date().getTime() - startTime < delay) {}
                            attempt += 1;   
                        }
                        
                        return input.value === "";  // Return false if not cleared within retry limit
                    } else {
                        return false;
                    }
                })(arguments[0]);
            """, xpath)

            if success:
                return True

        except Exception as e:
            logger.warning(f"Failed to clear field using JS Method using XPath: {e}")
            pass  # Continue to fallback methods

        # --- Fallback 2: ActionChains (most human-like and reliable for many UIs) ---
        if allow_click:
            try:
                self.scroll_to_element(self.driver.find_element(By.XPATH, xpath))
                self.click_js_dispatch_mouse_event(xpath)
                time.sleep(0.2)
                ActionChains(self.driver).key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).perform()
                time.sleep(0.2)
                ActionChains(self.driver).send_keys(Keys.BACKSPACE).perform()
                time.sleep(0.2)
                # Unfocus field if needed
                self.driver.execute_script("if (document.activeElement) document.activeElement.blur();")
                self.click_safe_heading_to_unfocus()
                # Ensure the field is cleared
                if is_cleared(self.driver.find_element(By.XPATH, xpath)):
                    return True
            except Exception as e:
                logger.warning(f"Failed to clear field using ActionChain: {e}")
                pass

        # --- Fallback 3: JS clear via element reference ---
        try:
            element = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            self.driver.execute_script("arguments[0].value = '';", element)
            time.sleep(0.2)
            if is_cleared(element):
                return True
        except Exception as e:
            logger.warning(f"Failed to clear field using JS clear via element reference: {e}")
            pass

        # --- Fallback 4: send_keys select + delete ---
        if allow_click:
            try:
                element = self.driver.find_element(By.XPATH, xpath)
                element.click()
                element.send_keys(Keys.CONTROL + "a")
                element.send_keys(Keys.DELETE)
                time.sleep(0.2)
                if is_cleared(element):
                    return True
            except Exception as e:
                logger.warning(f"Failed to clear field using send_keys select + delete: {e}")
                pass

        # --- Fallback 5: native clear ---
        try:
            element = self.driver.find_element(By.XPATH, xpath)
            element.clear()
            time.sleep(0.2)
            # Verify the element was cleared
            if is_cleared(element):
                return True
        except Exception as e:
            logger.warning(f"Failed to clear field using native clear: {e}")
            pass

        # --- Final handling ---
        if raise_or_fail:
            raise ElementNotInteractableException(f"Unable to clear input at XPath: {xpath}")
        return False

    def clear_special_input_field(self, xpath: str) -> bool:
        """
        Clears input fields with custom behavior, such as date pickers, range sliders, or select fields.
        These fields may not store their values in the 'value' attribute and may require different handling.
        Also clears dynamic fields like range sliders that rely on 'aria-valuenow'.

        Args:
            xpath (str): The XPath of the input element to clear.

        Returns:
            bool: True if the field was successfully cleared, False otherwise.
        """
        try:
            js_script = """
            return (function(xpath) {
                const result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                const input = result.singleNodeValue;
                if (input && input instanceof HTMLElement && !input.disabled && !input.readOnly) {
                    // Handle specific cases for different types of inputs (e.g., date, range, or select)
                    
                    // For Date input fields
                    if (input.type === 'date') {
                        input.value = "";  // Clear the date
                    }
                    // For Range sliders
                    else if (input.type === 'range') {
                        input.value = 0;  // Reset the slider
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                    // For elements with aria-valuenow (such as range sliders)
                    else if (input.hasAttribute('aria-valuenow')) {
                        input.setAttribute('aria-valuenow', 0);  // Reset the value
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                    // For Select input fields
                    else if (input.tagName === 'SELECT') {
                        input.selectedIndex = -1;  // Clear select options
                    }
                    // Default behavior for text-based or other input types
                    else {
                        input.value = "";  // Clear the value
                    }
                    
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                }
                return false;
            })(arguments[0]);
            """
            # Execute JavaScript to clear the field
            success = self.driver.execute_script(js_script, xpath)
            
            return success
        except Exception as e:
            logger.warning(f"Error clearing special input field: {e}")
            return False

    def type_with_action_chains(self, text, delay: float = 0.2, click_before_xpath: bool = None, unfocus_after: bool = False):

        try:
            if click_before_xpath:
                # Ensure the element is interactable
                self.click_js_dispatch_mouse_event(click_before_xpath)
                time.sleep(0.5)

            actions = ActionChains(self.driver)
            # Type each character one at a time
            for char in text:
                actions.send_keys(char)
                actions.pause(delay)  # Optional: slight delay between keypresses
            actions.perform()
            time.sleep(0.2)

            # Optional: Unfocus field if needed
            if unfocus_after:
                if (not click_before_xpath) or (click_before_xpath and (not "[@role='spinbutton']" in click_before_xpath)):
                    self.driver.execute_script("if (document.activeElement) document.activeElement.blur();")
                    self.click_safe_heading_to_unfocus()
            logger.info(f"✅  Successfully sent keys: '{text}'")
            return True
        except Exception as e:
            logger.error(f"❌  Failed to send keys using ActionChain: {e}")

    def safe_send_keys(self, xpath: str, value: Any, clear_before: bool = False, allow_click: bool = True, retries: int = 0, delay: float = 0.5):
        """
        Safely sends keys to a web element, retrying on certain exceptions.

        Args:
            xpath (str): The target element as XPath string.
            value (str | Path): Text or file path to input.
            clear_before (bool): Control whether the element should be cleared before sending keys.
            allow_click (bool): Control whether to use methods involving click as fallback or just pure JS.
            retries (int): Number of retry attempts on failure.
            delay (float): Time to wait between retries in seconds.

        Returns:
            bool: True if successful, False otherwise.
        """
        if not isinstance(xpath, str):
            err = ValueError("Invalid xpath argument: must be string type")
            logger.error(err)
            return False
        if not self.is_interactable(xpath):
            return True

        for attempt in range(0, retries + 1):
            try:
                if clear_before:
                    self.clear_input_field(xpath, allow_click=allow_click)
                self.driver.find_element(By.XPATH, xpath).send_keys(value)
                logger.info(f"✅  Successfully sent keys on attempt {attempt}: '{value}'")
                return True
            except StaleElementReferenceException as e:
                logger.warning(f"⚠️  StaleElementReferenceException on attempt {attempt}. Element may have been removed or changed. Error: {e}")
            except NoSuchElementException as e:
                logger.error(f"❌  NoSuchElementException on attempt {attempt}. The element could not be located. Error: {e}")
                return False
            except ElementClickInterceptedException as e:
                logger.warning(f"⚠️  ElementClickInterceptedException on attempt {attempt}. The click action was intercepted. Error: {e}")
            except Exception as e:
                logger.warning(f"⚠️  Unexpected exception on attempt {attempt}. Error: {e}")
            time.sleep(delay)

        logger.warning("🔄  All attempts with send_keys failed. Falling back to DOM-level input simulation via JavaScript...")
        try:
            if self.driver.execute_script("""
                return (function(xpath, value) {
                    var element = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                    if (element) {
                        element.focus();
                        element.value = value;
                        
                        // Trigger the 'input' event
                        var inputEvent = new Event('input', { bubbles: true, cancelable: true });
                        element.dispatchEvent(inputEvent);
                        
                        // Trigger the 'change' event
                        var changeEvent = new Event('change', { bubbles: true });
                        element.dispatchEvent(changeEvent);
                        
                        return true;
                    } else {
                        return false;
                    }
                })(arguments[0], arguments[1]);
            """, xpath, value):
                logger.info(f"✅    JavaScript fallback for sending keys succeeded: '{value}'")
                return True
        except:
            logger.error("❌  JavaScript fallback failed to find or interact with the element.")

        logger.error(f"❌  Failed to send keys after {retries} attempts and fallback.")
        return False

    def get_updated_dom_after_click(self, element_or_xpath: Union[str, WebElement], scroll: bool = True,  wait: float = 1) -> Union[str, List[str]]:
        """
        Captures HTML before and after clicking an element.
        Returns the diff block of the updated DOM.
        """

        # Initialize XPath
        if isinstance(element_or_xpath, str):
            xpath = element_or_xpath
        elif isinstance(element_or_xpath, WebElement):
            xpath = self.WebParserUtils.get_xpath(element_or_xpath)
        else:
            return '', []
        
        # 1. Scroll to element
        if scroll:
            self.scroll_to_element(element_or_xpath)

        # 2. Capture the HTML before clicking
        html_before = self.driver.page_source

        # 3. Click the element
        self.click(xpath)

        # 4. Wait briefly for DOM changes to apply
        self.WebParserUtils.wait_for_stable_dom(padding=wait)

        # 5. Capture the HTML after clicking
        html_after = self.driver.page_source

        # 6. Compute and return the diff
        html_diff = HtmlDiffer()
        html_diff_dom, html_diff_parents_xPath = html_diff.html_diff(html_before, html_after)
        return html_diff_dom, html_diff_parents_xPath

    def get_updated_dom_after_scroll(self, element_or_xpath: Union[str, WebElement], wait: float = 1) -> Union[str, List[str]]:
        """
        Captures HTML before and after scrolling an element.
        Returns the diff block of the updated DOM.
        """

        # 1. Capture the HTML before clicking
        html_before = self.driver.page_source

        # 2. Scroll to element
        self.scroll_to_element(element_or_xpath)

        # 3. Wait briefly for DOM changes to apply
        self.WebParserUtils.wait_for_stable_dom(padding=wait)

        # 4. Capture the HTML after clicking
        html_after = self.driver.page_source

        # 5. Compute and return the diff
        html_diff = HtmlDiffer()
        html_diff_dom, html_diff_parents_xPath = html_diff.html_diff(html_before, html_after)
        return html_diff_dom, html_diff_parents_xPath

    def get_updated_dom_after_typing(self, text: str, delay: float = 0.2, click_before_xpath: bool = None, unfocus_after: bool = False, wait: float = 1) -> Union[str, List[str]]:
        """
        Captures HTML before and after sending keys to an element.
        Returns the diff block of the updated DOM.
        """

        # 1. Capture the HTML before sending keys
        html_before = self.driver.page_source

        # 2. Send keys to the element
        self.type_with_action_chains(text=text, delay=delay, click_before_xpath=click_before_xpath, unfocus_after=unfocus_after)
        
        # 3. Wait briefly for DOM changes to apply
        self.WebParserUtils.wait_for_stable_dom(padding=wait)

        # 4. Capture the HTML after sending keys
        html_after = self.driver.page_source

        # 5. Compute and the diff
        html_diff = HtmlDiffer()
        html_diff_dom, html_diff_parents_xPath = html_diff.html_diff(html_before, html_after)

        # 6. Return the diff
        if (
            (html_diff_dom is None) or (html_diff_dom == "") 
            or (html_diff_dom.startswith("<script") and html_diff_dom.endswith("</script>")) 
            or ((html_diff_dom.startswith("<noscript") or html_diff_dom.startswith("</noscript")) and html_diff_dom.endswith("</noscript>"))
        ):
            return '',[]
        return html_diff_dom, html_diff_parents_xPath
    
    def get_updated_dom_after_enterkey(self, wait: float = 1) -> Union[str, List[str]]:
        """
        Captures HTML before and after sending keys to an element.
        Returns the diff block of the updated DOM.
        """

        # 1. Capture the HTML before sending keys
        html_before = self.driver.page_source

        # 2. Press Enter Key
        actions = ActionChains(self.driver)
        actions.send_keys(Keys.ENTER).perform()

        # 3. Wait briefly for DOM changes to apply
        self.WebParserUtils.wait_for_stable_dom(padding=wait)

        # 4. Capture the HTML after sending keys
        html_after = self.driver.page_source

        # 5. Compute and the diff
        html_diff = HtmlDiffer()
        html_diff_dom, html_diff_parents_xPath = html_diff.html_diff(html_before, html_after)

        # 6. Return the diff
        if (
            (html_diff_dom is None) or (html_diff_dom == "") 
            or (html_diff_dom.startswith("<script") and html_diff_dom.endswith("</script>")) 
            or ((html_diff_dom.startswith("<noscript") or html_diff_dom.startswith("</noscript")) and html_diff_dom.endswith("</noscript>"))
        ):
            return '',[]
        return html_diff_dom, html_diff_parents_xPath

    def get_updated_dom_after_send_keys(self, element_or_xpath: Union[str, WebElement], value: Any, clear_before: bool = False, allow_click: bool = True, wait: float = 1, retries: int = 0, delay: float = 0.5) -> Union[str, List[str]]:
        """
        Captures HTML before and after sending keys to an element.
        Returns the diff block of the updated DOM.
        """

        # Initialize XPath
        if isinstance(element_or_xpath, str):
            xpath = element_or_xpath
        elif isinstance(element_or_xpath, WebElement):
            xpath = self.WebParserUtils.get_xpath(element_or_xpath)
        else:
            return '', []
        
        # 1. Capture the HTML before sending keys
        html_before = self.driver.page_source

        # 2. Send keys to the element
        self.safe_send_keys(xpath, value, clear_before=clear_before, allow_click=allow_click, retries=retries, delay=delay)
        
        # 3. Wait briefly for DOM changes to apply
        self.WebParserUtils.wait_for_stable_dom(padding=wait)

        # 4. Capture the HTML after sending keys
        html_after = self.driver.page_source

        # 5. Compute and the diff
        html_diff = HtmlDiffer()
        html_diff_dom, html_diff_parents_xPath = html_diff.html_diff(html_before, html_after)

        # 6. Return the diff
        if (
            (html_diff_dom is None) or (html_diff_dom == "") 
            or (html_diff_dom.startswith("<script") and html_diff_dom.endswith("</script>")) 
            or ((html_diff_dom.startswith("<noscript") or html_diff_dom.startswith("</noscript")) and html_diff_dom.endswith("</noscript>"))
        ):
            return '',[]
        return html_diff_dom, html_diff_parents_xPath

class FormInteractor:
    """
    Handles automated interaction with web form elements based on parsed field metadata.
    Supports complex form interactions including dynamic fields and custom controls.
    """
    
    def __init__(self, driver, wait_timeout: int = 10):
        """
        Initialize with a WebDriver instance and optional timeout configuration.
        
        Args:
            driver: Selenium WebDriver instance
            wait_timeout: Default timeout for element interactions in seconds
        """
        self.driver = driver
        self.refresh_answer = True
        self.wait_timeout = wait_timeout
        self.logger = logging.getLogger(__name__)
        self.ParsedDataUtils = ParsedDataUtils(parsed_data=None)
        self.LinguisticTextEvaluator = LinguisticTextEvaluator()
        self.WebParserUtils = WebParserUtils(driver)
        self.FormInteractorUtils = FormInteractorUtils(driver)
        self.UserData = UserData(env_config.USER_JSON_FILE)
        self.PromptAgent = PromptAgent(env_config.LLM_MODEL, env_config.EMBED_MODEL, env_config.CHROMA_DB_DIR, env_config.EMBED_COLLECTION_NAME)

    def _get_question(self, element_metadata: Dict[str, Any], min_words: int = 1, merge_parent_if_exists: bool = True) -> str | None:

        def get_question_from_label(element_metadata: Dict[str, Any], min_words: int = 1, merge_parent_if_exists: bool = True) -> str | None:
            
            question: Optional[str] = None

            # Rely on pre-existing label if exists
            question_srcTag: str | None = element_metadata['label-srcTag'] 
            question_srcText: str | None = element_metadata['label-srcText'] 

            # Both labels exists
            if question_srcTag and question_srcText:    
                if self.ParsedDataUtils.string_match_percentage(question_srcTag, question_srcText) > 66:    # Labels are similar
                    question = max(question_srcTag, question_srcText, key=len)  # Assign longest label
                else:   # Labels not similar
                    question = '\n'.join([question_srcTag, question_srcText]) # Use both labels for question.
            # One label exists
            elif question_srcTag or question_srcText:
                question = question_srcTag or question_srcText  # Assign the label that exists
                
            # Set question if label satisfies minimum word count to give context, else set None.
            question = question if isinstance(question, str) and len(question.split()) >= min_words else None
            
            # Add Parent question (if exists)
            if merge_parent_if_exists and element_metadata.get('label-parent'):
                if question:
                    question = f"Parent Question:\n{element_metadata.get('label-parent')}\nMain Question (current question):\n{question}"
                else:
                    pass # Get question from LLM and append parent there.

            return question

        def get_question_LLM(element_metadata: Dict[str, Any], min_words: int = 1, merge_parent_if_exists: bool = True) -> str | None:
            
            dynamic_threshold: float = 0.2
            question: Optional[str] = None
            
            while not question and dynamic_threshold > 0:
                question = self.LinguisticTextEvaluator.filter_normalized_metadata(self.ParsedDataUtils.normalize_metadata(element_metadata), threshold=dynamic_threshold)
                dynamic_threshold -= 0.04
            
            # Set to 'None' if doesn't satisfy minimum word count.
            question = question if isinstance(question, str) and len(question.split()) >= min_words else None

            if question:
                prompt_input = {"metadata": question}
                response = self.PromptAgent.resolve(custom_prompt_fn=_generate_question_prompt, custom_prompt_args=prompt_input)
                if merge_parent_if_exists and element_metadata.get('label-parent'):
                    response = f"Parent Question:\n{element_metadata.get('label-parent')}\nMain Question (current question):\n{response}"
                return response
            else:
                if merge_parent_if_exists and element_metadata.get('label-parent'):
                    logger.info("🪜  Unable to normalize question from metadata, but found parent question from payload.")
                    return f"Parent Question:\n{element_metadata.get('label-parent')}"
                logger.warning('⚠️  Unable to normalize question from metadata')
                return None

        question: Optional[str] = None
        ''' Build Question from Pre-Existing Labels '''
        question = get_question_from_label(element_metadata, min_words=min_words, merge_parent_if_exists=merge_parent_if_exists)
        ''' Build Question using LLM '''
        if not question:    # Label does not exists or non-reliable to give context.
            logger.info("🕵️  Question not available in pre-existing field item. Asking LLM Agent to build question using metadata...")
            question = get_question_LLM(element_metadata, min_words=min_words, merge_parent_if_exists=merge_parent_if_exists) # Get question/label through LLM using existing metadata.

        return question

    def _retrieve_relevant_options(self, options:dict, search_text:str, threshold:int=None, top_k:int=None) -> List:
        """
        Returns a list of dictionaries with {'option': option_key, 'xPath': option_xpath, 'similarity': score}
        sorted by the similarity score of the option's key compared to the given search_text string.

        Args:
            options_dict (dict): Dictionary of options where keys are option texts and values are their corresponding xPaths.
            search_text (str): The desired text to compare the options against (e.g. The response from the LLM, Desired answer.)
            threshold (int, optional): Minimum similarity score to filter the options.
            top_k (int, optional): Number of top matches to return.

        Returns:
            list: List of dictionaries sorted by match score, with 'option', 'xPath', and 'similarity'.
        """
        if (not options) or (not isinstance(options, dict)) or (not search_text):
            return []

        # Step 1: Calculate similarity scores for each option key
        match_scores = []
        for key, xPath in options.items():
            score = self.ParsedDataUtils.string_match_percentage(key, search_text)
            match_scores.append({
                'option': key,
                'xPath': xPath,
                'similarity': score
            })

        # Step 2: Filter by threshold if it's specified
        if threshold is not None:
            match_scores = [item for item in match_scores if item['similarity'] >= threshold]

        # Step 3: Sort the options by similarity score in descending order
        match_scores = sorted(match_scores, key=lambda x: x['similarity'], reverse=True)

        # Step 4: Limit to top_k results if specified
        if top_k is not None:
            match_scores = match_scores[:top_k]

        # Step 5: Return the sorted list of dictionaries
        return match_scores

    def _get_answer_xpath(self, element_metadata: Dict[str, Any], options: dict) -> str | None:

        ''' 
        Initialize best option's xPath
        '''
        answer_xPath:str = ''
        
        '''
        Number of option(s)
        '''
        option_keys, option_values = zip(*options.items())
        option_keys = list(option_keys)
        option_values = list(option_values)
        num_of_options = len(options)
        if num_of_options == 0:
            logger.warning('⚠️  0 options for found. Skipping...')
            return None

        '''
        Function which tries to get answer using predefined settings.
        '''
        def resolve_predefined_fields(element_metadata):

            nonlocal answer_xPath

            if num_of_options == 1: ### Single independent option
                ## Agreement
                if self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['I authorize', 'acknowledge', 'agree', 'accept', 'terms and conditions', 'policy', 'read and understood'], normalize_whitespace=True):
                    answer_xPath = option_values[0]
                    return
            elif num_of_options == 2: ### Paired options
                ## Agreement
                if self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['I authorize','acknowledge', 'agree', 'accept', 'terms and conditions', 'policy', 'read and understood'], normalize_whitespace=True):
                    if re.search(r'^(Yes|I agree)', option_keys[0]):
                        answer_xPath = option_values[0]
                        return
                ## Yes/No Questions
                is_yes_no_question = re.search(r'^(Yes)', option_keys[0]) and re.search(r'^(No)', option_keys[1])
                if is_yes_no_question: # Handle Yes/No questions using custom identifiers.
                    yes_question_identifiers = ['future require sponsorship', 'future require our sponsorship', 'future, require sponsorship', 'considered for other roles', 'contact your previous or present employer', 'willing to relocate', 'able to work on a daily basis', 'submit a background check', 'upon employment provide proof' , 'can you provide proof', 'have work authorization', 'standard message rates may apply', 'now or in the future require sponsorship', 'future require visa sponsorship', 'require any immigration filing or visa sponsorship', 'at least 18 years','live within commuting distance','contact you via', 'communicate with me via', "you reside in the country you're applying", "you reside in the country you are applying", 'do you reside in the united states', 'do you consent']
                    no_questions_identifiers = [ 'you now require sponsorship', 'do you currently require sponsorship', 'have you ever been employed by', 'do you currently work at', 'you previously applied', 'you ever worked at', 'are you currently employed by one of', 'are you related to any current', 'are you related to a current', 'related to an employee', 'do you have a relative or friend', 'employed by the U.S.', 'employed by the federal', 'Iran, Cuba, North Korea', 'subject to a non-compete', 'subject to any non-compete', 'non-solicitation, employment agreement', 'obligation with another employer that could affect your ability', 'government ever proposed that you be excluded', 'debarred, suspended', 'any disciplinary action taken on', 'employed by a federal', 'lawful permanent resident', 'granted asylum or refugee', 'spouse or partner of', 'hispanic/latino', 'hispanic or latino', 'previously worked for or are you currently working for']
                    if self.ParsedDataUtils.is_substrings_in_item(element_metadata, standard_label_keys, yes_question_identifiers, normalize_whitespace=True):
                        answer_xPath = option_values[0] # Select 'Yes'
                        return
                    if self.ParsedDataUtils.is_substrings_in_item(element_metadata, standard_label_keys, no_questions_identifiers, normalize_whitespace=True):
                        answer_xPath = option_values[1] # Select 'No'
                        return
                    if self.ParsedDataUtils.is_substrings_in_item(element_metadata, standard_label_keys, ['legally eligible to work', 'legal right to work', 'authorized to work', 'sponsorship or immigration support to work'], normalize_whitespace=True):
                        if self.ParsedDataUtils.is_substrings_in_item(element_metadata, standard_label_keys, ['without visa', 'without sponsorship', 'U.S. citizen or national', 'lawful temporary resident', 'refugee', 'asylum'], normalize_whitespace=True):
                            answer_xPath = option_values[1] # Select 'No'
                            return
                        else:
                            answer_xPath = option_values[0] # Select 'Yes'
                            return
            elif num_of_options == 3: ### Three options
                ## Yes/No Questions
                is_yes_no_question = re.search(r'^(Yes)', option_keys[0]) and re.search(r'^(No)', option_keys[1])
                if is_yes_no_question: # Handle Yes/No questions using custom identifiers.
                    yes_question_identifiers = []
                    no_questions_identifiers = ['spouse or partner of', 'veteran', 'you identify as transgender', 'suspended']
                    if self.ParsedDataUtils.is_substrings_in_item(element_metadata, standard_label_keys, yes_question_identifiers, normalize_whitespace=True):
                        answer_xPath = option_values[0] # Select 'Yes'
                        return
                    if self.ParsedDataUtils.is_substrings_in_item(element_metadata, standard_label_keys, no_questions_identifiers, normalize_whitespace=True):
                        answer_xPath = option_values[1] # Select 'No'
                        return
                ## Disability
                if self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['disability']):
                    if re.search(r"^No, I do(n't| not)", option_keys[1]):
                        answer_xPath = option_values[1]
                        return
                    else:
                        desired_answer = 'No, I do not have a disability and have not had one in the past'
                        answer_xPath = self._retrieve_relevant_options(options, search_text=desired_answer, top_k=1)[0]['xPath']
                        return
                # Hispanic/Latino
                if self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['hispanic/latino', 'hispanic or latino']):
                    if re.search(r"^No", option_keys[1]):
                        answer_xPath = option_values[1]
                        return
                    else:
                        idx = find_matching_option(['No'], option_keys, exact_match=True) or find_matching_option(['Not hispanic or'], option_keys, exact_match=False)
                        if idx is not None:
                            answer_xPath = option_values[idx]
                            return
            else: ### Multiple (>3) options
                ## Gender
                if self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['select your gender', 'select the gender', 'title']):
                    possible_options = ['Male', 'Man', 'He/Him/His', 'Mr.']
                    idx = find_matching_option(possible_options, option_keys, exact_match=True) # enable exact match to avoid 'male' falsely classified as 'female'
                    if idx is not None:
                        answer_xPath = option_values[idx]
                        return
                ## Sexual orientation
                elif self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['select your gender', 'select the gender', 'sexual orientation']):
                    possible_options = ['Heterosexual', 'Straight']
                    idx = find_matching_option(possible_options, option_keys)
                    if idx is not None:
                        answer_xPath = option_values[idx]
                        return
                ## Race/Ethnicity
                elif self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['ethnicity', 'race']):
                    possible_options = ['Asian (United States of America)', 'Asian']
                    idx = find_matching_option(possible_options, option_keys)
                    if idx is not None:
                        answer_xPath = option_values[idx]
                        return
                # Veteran Status
                elif self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['veteran status']):
                    possible_options = ['I am not a protected veteran', 'I am not a veteran']
                    idx = find_matching_option(possible_options, option_keys, exact_match=True)
                    if idx is not None:
                        answer_xPath = option_values[idx]
                        return  
                # Country
                elif (
                    self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['country'])
                ):
                    possible_options = ['United States of America', 'United States']
                    idx = find_matching_option(possible_options, option_keys, exact_match=True)
                    if idx is not None:
                        answer_xPath = option_values[idx]
                        return  
                # Citizen
                elif self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['Citizen', 'citizenship'], case_sensitive=True):
                    possible_options = ['India']
                    idx = find_matching_option(possible_options, option_keys)
                    if idx is not None:
                        answer_xPath = option_values[idx]
                        return  


            ''' Fields irrespective of the number of options '''
            def get_nested_value(key_path: str):
                return self.ParsedDataUtils.get_nested_value(element_metadata, key_path)
            if (
                self.ParsedDataUtils.is_match(element_metadata, {"options.category": "Education"})
            ):
                candidate_answer_label = self.UserData.data[get_nested_value('options.category')][get_nested_value('options.id')-1][get_nested_value('options.type')]
                if self.ParsedDataUtils.is_match(element_metadata, {"options.type": "School or University"}):
                    if candidate_answer_label in option_keys:   # Exact answer labeled in option
                        answer_xPath = options[candidate_answer_label]  # Directly return its XPath
                    else:    # Identify closest matching option label
                        closest_option = self._retrieve_relevant_options(options, search_text=candidate_answer_label, top_k=1)[0]
                        if closest_option['similarity'] > 92:
                            answer_xPath = closest_option['xPath']
                            return
                        answer_xPath = self._retrieve_relevant_options(options, search_text='Other', top_k=1)[0]['xPath']
                        return
                elif self.ParsedDataUtils.is_match(element_metadata, {"options.type": "Field of Study or Major"}):
                    if candidate_answer_label in option_keys:   # Exact answer labeled in option
                        answer_xPath = options[candidate_answer_label]  # Directly return its XPath
                    else:   # Identify closest matching option label
                        answer_xPath = self._retrieve_relevant_options(options, search_text=candidate_answer_label, top_k=1)[0]['xPath']
                    return
                elif self.ParsedDataUtils.is_match(element_metadata, {"options.type": "Degree"}):
                    if candidate_answer_label in option_keys:   # Exact answer labeled in option
                        answer_xPath = options[candidate_answer_label]  # Directly return its XPath
                    else:   # Identify closest matching option label
                        answer_xPath = self._retrieve_relevant_options(options, search_text=candidate_answer_label, top_k=1)[0]['xPath']
                    return

            # City
            if self.ParsedDataUtils.is_substrings_in_item(element_metadata, standard_label_keys, ['City', 'City*'], normalize_whitespace=True, case_sensitive=True):
                candidate_answer = self.UserData.data['City']
                answer_xPath = self._retrieve_relevant_options(options, search_text=candidate_answer, top_k=1)[0]['xPath']
                return           
            # State
            elif self.ParsedDataUtils.is_substrings_in_item(element_metadata, standard_label_keys, ['State', 'State*'], normalize_whitespace=True, case_sensitive=True):
                candidate_answer = self.UserData.data['State']
                answer_xPath = self._retrieve_relevant_options(options, search_text=candidate_answer, top_k=1)[0]['xPath']
                return
            # PhoneDevice Type
            elif self.ParsedDataUtils.is_substrings_in_item(element_metadata, standard_label_keys, ['Phone Device Type', 'Phone Type'], normalize_whitespace=True):
                candidate_answer = self.UserData.data['Phone Device Type']
                answer_xPath = self._retrieve_relevant_options(options, search_text=candidate_answer, top_k=1)[0]['xPath']
                return
             # Country
            elif (
                self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['Country Territory', 'Country/Territory'], normalize_whitespace=True)
                or self.ParsedDataUtils.is_substrings_in_item(element_metadata, standard_label_keys, ['Country', 'Country*'], normalize_whitespace=True, case_sensitive=True)
            ):
                candidate_answer = self.UserData.data['Country']
                answer_xPath = self._retrieve_relevant_options(options, search_text=candidate_answer, top_k=1)[0]['xPath']
                return
            # Employeed by any of the company's subsidiaries
            elif (
                self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['employed by'])
                and self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['subsidiar'])
            ):
                idx = find_matching_option(['No'], option_keys, exact_match=False, case_sensitive=True)
                if idx is not None:
                    answer_xPath = option_values[idx]
                    return
            elif (
                self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys + ['placeholder'], ['salary'])
                and (
                    self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys + ['placeholder'], ['desired'])
                    or self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys + ['placeholder'], ['expect'])
                )
            ):
                candidate_answer = self.UserData.data["Salary Expectation"]
                answer_xPath = self._retrieve_relevant_options(options, search_text=candidate_answer, top_k=1)[0]['xPath']
                return
            elif (
                self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['relocat'])
                and not self.ParsedDataUtils.is_substrings_in_item(element_metadata, standard_label_keys, ['company to', 'sponsor'])
            ):
                for i in range(len(option_keys)):  
                    if re.search(r'^(Yes)', option_keys[i]):
                        answer_xPath = option_values[i]
                        return
            return # No relevant answer discovered. Fallback to proceed with LLM

        ''' 
        Get Answer 
        '''
        logger.info("🔎  Searching for answer in predefined fields...")
        resolve_predefined_fields(element_metadata) # Try to determine answer using predefined settings
        if answer_xPath:
            logger.info("🪶  Answer found in predefined settings.")
        else: # Use LLM, if unable to determine answer from predefined settings
            logger.info("🔹  Answer not available in predefined fields.")
            question = self._get_question(element_metadata)
            ''' Get LLM Answer '''
            if question: # Succefully normalized fields and fetched a question from LLM
                logger.info("🤖  LLM Agent selecting the best possible answer...")
                llm_response = self.PromptAgent.resolve(question=question, options=list(options.keys()), multi_select=False, top_k=15) # Resolve the question/label using LLM.
                logger.info("🤖  Agent Response: %s", llm_response)
            else: # Unsuccessful to normalize and fetch question. Ask LLM to predict orphan option using best practice.
                logger.info("🤖  Unable to normalize and fetch question. Ask LLM to predict orphan option...")
                llm_response = self.PromptAgent.resolve(custom_prompt_fn=_orphan_options_prompt, custom_prompt_args={"options": list(options.keys()), "multi_select": False})
                logger.info("🤖  Agent Response: %s", llm_response)
                if ("n/a" in llm_response.lower() or "not applicable" in llm_response.lower()) and not element_metadata['required']: # Condition is true if "n/a" or "not applicable" is found
                    logger.info('📝  Options not applicable. Skipping...')
                    return None # Don't select any option
            ''' Match Options with LLM Response '''
            relevant_options = self._retrieve_relevant_options(options, llm_response)
            # self.ParsedDataUtils.pretty_print(relevant_options) # Print relevant options
            answer_xPath = relevant_options[0]['xPath'] # Top-most option (having highest similarity score) is selected.
        logger.info("📦  Returning XPath of the best possible answer.")
        return answer_xPath

    def _progressive_answer_resolver(self, element_metadata: Dict[str, Any], options: dict) -> str | None:
        """
        Attempts to resolve and return the XPath of a matching answer option based on known structured user data.

        This method uses predefined logic to match user-provided data against available options as they arrive, 
        enabling early selection without needing to analyze the full list.

        It prioritizes exact string matches using context-aware metadata:
        - Education-related fields like School, Degree, and Field of Study.
        - Location-based fields such as City, State, and Country.
        - Other fields (which could need deep traveral for collection options)

        If a high-confidence match is found, the corresponding XPath is returned.
        If no match is found, the function returns None.

        Args:
            element_metadata (Dict[str, Any]): Structured metadata for the current form field.
            options (dict): Dictionary mapping option labels (keys) to their corresponding XPath (values).

        Returns:
            Optional[str]: The XPath of the selected answer if a confident match is found from user data, else None.
        """
        
        '''
        Unpack option(s)
        '''
        option_keys, option_values = zip(*options.items())
        option_keys = list(option_keys)
        option_values = list(option_values)
        num_of_options = len(options)
        if num_of_options == 0:
            logger.warning('⚠️  0 options for found. Skipping...')
            return None
        
        '''
        Search answer using predefined settings.
        '''
        def get_nested_value(key_path: str):
            return self.ParsedDataUtils.get_nested_value(element_metadata, key_path)
        if (
            self.ParsedDataUtils.is_match(element_metadata, {"options.category": "Education"})
        ):
            candidate_answer_label = self.UserData.data[get_nested_value('options.category')][get_nested_value('options.id')-1][get_nested_value('options.type')]
            
            if self.ParsedDataUtils.is_match(element_metadata, {"options.type": "School or University"}):  
                if candidate_answer_label in option_keys:   # Exact answer labeled in option
                    return options[candidate_answer_label]  # Directly return its XPath
            elif self.ParsedDataUtils.is_match(element_metadata, {"options.type": "Degree"}):
                if candidate_answer_label in option_keys:   # Exact answer labeled in option
                    return options[candidate_answer_label]  # Directly return its XPath
                idx = find_matching_option(possible_answers=user_data_config.education_degree_full[get_nested_value('options.id')-1], option_keys=option_keys, exact_match=True, normalize_whitespace=True)
                if idx is not None:                         # Exact answer match from user_data_config
                    return option_values[idx]               # Directly return its XPath
            elif self.ParsedDataUtils.is_match(element_metadata, {"options.type": "Field of Study or Major"}):
                if candidate_answer_label in option_keys:   # Exact answer match fron user_data json
                    return options[candidate_answer_label]  # Directly return its XPath
                idx = find_matching_option(possible_answers=user_data_config.education_field_of_study_full[get_nested_value('options.id')-1], option_keys=option_keys, exact_match=True, normalize_whitespace=True)
                if idx is not None:                         # Exact answer match from user_data_config
                    return option_values[idx]               # Directly return its XPath

        # City
        elif self.ParsedDataUtils.is_substrings_in_item(element_metadata, standard_label_keys, ['City', 'City*'], normalize_whitespace=True, case_sensitive=True):
            candidate_answer = self.UserData.data['City']
            if candidate_answer in option_keys:             # Exact answer match fron user_data json
                return options[candidate_answer]            # Directly return its XPath
        
        # State
        elif self.ParsedDataUtils.is_substrings_in_item(element_metadata, standard_label_keys, ['State', 'State*'], normalize_whitespace=True, case_sensitive=True):
            candidate_answer = self.UserData.data['State']
            if candidate_answer in option_keys:             # Exact answer match fron user_data json
                return options[candidate_answer]            # Directly return its XPath
        
        # Country
        elif (
            self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['Country Territory', 'Country/Territory'], normalize_whitespace=True)
            or self.ParsedDataUtils.is_substrings_in_item(element_metadata, standard_label_keys, ['Country', 'Country*'], normalize_whitespace=True, case_sensitive=True)
        ):
            candidate_answer = self.UserData.data['Country']
            if candidate_answer in option_keys:             # Exact answer match fron user_data json
                return options[candidate_answer]            # Directly return its XPath


        return None # No relevant answer discovered. Fallback to proceed with LLM

    def _get_multiple_answers_xpaths(self, element_metadata: Dict[str, Any], options: dict) -> Optional[set]:

        ''' 
        Initialize set of valid option's xPath container
        '''
        answer_xPaths = set()
        
        '''
        Initialize option(s)
        '''
        option_keys, option_values = zip(*options.items())
        option_keys = list(option_keys)
        option_values = list(option_values)
        num_of_options = len(options)
        
        '''
        Function which tries to collect relevant answer using predefined settings.
        '''
        def _resolve_predefined_fields(element_metadata) -> bool:
            '''
            Return 'True': We can proceed with current field. (Doesn't necessarily mean that we successfully discovered answer.)
            Return 'False': Do not to proceed with current field. (Checkbox not meant to be selected.)
            '''

            def get_nested_value(key_path: str):
                return self.ParsedDataUtils.get_nested_value(element_metadata, key_path)

            ## Currently employeed or enrolled here
            if (
                self.ParsedDataUtils.is_match(element_metadata, {"options.category": "Work Experience"})
                or self.ParsedDataUtils.is_match(element_metadata, {"options.category": "Education"})
            ):
                xpath = self.WebParserUtils.get_validated_xpath(element_metadata)
                if not xpath:
                    logger.warning("⚠️  Failed to get valid xpath for this checkbox. Skipping...")
                    return False
                # Check if employee is currently employed [UserData: I currently work here]
                if options['category'] == "Work Experience":
                    currently_working = self.UserData.data[get_nested_value('options.category')][get_nested_value('options.id')-1][get_nested_value('options.type')]
                    if currently_working:
                        _update_set(answer_xPaths, xpath)
                        return True
                # Check if student is 'currently studying' or 'graduated' [UserData: Graduated]
                elif options['category'] == "Education":                    
                    graduated = self.UserData.data[get_nested_value('options.category')][get_nested_value('options.id')-1][get_nested_value('options.type')]
                    # Checkbox Type: Is_Enrolled?
                    if self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['current', 'ongoing']):
                        if not graduated:
                            _update_set(answer_xPaths, xpath)
                            return True
                    # Checkbox Type: Is_Graduated?
                    else:
                        if graduated:
                            _update_set(answer_xPaths, xpath)
                            return True
                # Don't select this xPath (checkbox)
                return False 

            if num_of_options == 1: ### Single independent checkbox
                ## Agreement
                if self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['I authorize', 'acknowledge', 'agree', 'accept', 'terms and conditions', 'policy', 'read and understood'], normalize_whitespace=True):
                    _update_set(answer_xPaths, option_values)
                    return True
                # Preferred name
                elif self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['preferred name'], normalize_whitespace=True):
                    return False
            elif num_of_options == 2: ### Paired checkbox
                ## Agreement
                if self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['I authorize', 'acknowledge', 'agree', 'accept', 'terms and conditions', 'policy', 'read and understood'], normalize_whitespace=True):
                    if re.search(r'^(Yes|I agree)', option_keys[0]):
                        _update_set(answer_xPaths, option_values[0])
                        return True
            else: ### Multiple (>2) checkboxes
                ## Disability
                if self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['disability']):
                    if num_of_options == 3 and re.search(r"^No, I do(n't| not)", option_keys[1]):
                        _update_set(answer_xPaths, option_values[1])
                        return True
                    else:
                        desired_answer = 'No, I do not have a disability and have not had one in the past'
                        _update_set(answer_xPaths, self._retrieve_relevant_options(options, search_text=desired_answer, top_k=1)[0]['xPath'])
                        return True          
            return True # Fallback returning true to proceed with LLM

        ''' 
        Get Answer(s): 
            Identify 'Correct Option(s)' for Checkbox 
        '''
        logger.info("🔎  Searching for answer in predefined fields...")
        proceed_to_resolve = _resolve_predefined_fields(element_metadata)
        if not proceed_to_resolve: # Indicates, not to proceed selecting any option(s). (Checkbox(s) not meant to be selected)
            logger.info(f"🔹  Checkbox(s) not meant to be selected. Returning.")
            return # No selection was made.
        # Fallback to LLM model if no answer(s) were identified using predefined settings.
        if answer_xPaths:
            logger.info("🪶  Answer found in predefined settings.")
        else: # Use LLM, if unable to determine answer from predefined settings
            logger.info("🔹  Answer not available in predefined fields.")
            ''' Build Question '''
            question = self._get_question(element_metadata)
            ''' Get LLM Answer '''
            multiSelect = False if num_of_options == 1 else True
            if question: # Succefully normalized fields and fetched a question from LLM
                logger.info("🤖  LLM Agent selecting the best possible answer(s)...")
                llm_response = self.PromptAgent.resolve(question=question, options=list(options.keys()), multi_select=multiSelect, top_k=15) # Resolve the question/label using LLM.
                logger.info("🤖  Agent Response: %s", llm_response)
            else: # Unsuccessful to normalize and fetch question. Ask LLM to predict orphan option using best practice.
                logger.info("🤖  Unable to normalize and fetch question. Asking LLM to predict orphan option using best practice...")
                llm_response = self.PromptAgent.resolve(custom_prompt_fn=_orphan_options_prompt, custom_prompt_args={"options": list(options.keys()), "multi_select": multiSelect})
                logger.info("🤖  Agent Response: %s", llm_response)
                if "n/a" in llm_response.lower() or "not applicable" in llm_response.lower(): # Agent denied to select any option(s): "n/a" or "not applicable" in response
                    logger.info('📝  Checkbox(s) not applicable. Skipping...')
                    return # Don't select any option
            if num_of_options == 1 and 'false' in llm_response.lower():
                # Check if response is short relative to the question, thus identifying true 'False' and not a word normally occuring in some sentence.
                if (
                    question and len(llm_response.split(' ')) < len(question.split(' '))+3 
                    or not question
                    or question and (self.ParsedDataUtils.string_match_percentage(llm_response.lower(), question.lower()) > 75)
                ):
                    logger.info('📝  Agent denied to select. Skipping...')
                    return # Selection not required.
            ''' Match Options with LLM Response '''
            relevant_options = self._retrieve_relevant_options(options, llm_response)
            self.ParsedDataUtils.pretty_print(relevant_options) # Print relevant options
            filtered_options_above_90 = [item for item in relevant_options if item['similarity'] >= 90]
            filtered_options_above_80 = [item for item in relevant_options if item['similarity'] >= 80]
            min_threshold = 40
            filtered_options_above_min_threshold = [item for item in relevant_options if item['similarity'] >= min_threshold]
            if len(filtered_options_above_90) != 0: 
                for filtered_option in filtered_options_above_90: # Select all options above 90 threshold  
                    _update_set(answer_xPaths, filtered_option['xPath'])
            elif len(filtered_options_above_80) != 0:
                if len(filtered_options_above_80) > 1 and len(options) > 3: 
                    for filtered_option in filtered_options_above_80: # Select all options above 80 threshold
                        _update_set(answer_xPaths, filtered_option['xPath'])
                else:
                    _update_set(answer_xPaths, filtered_options_above_80[0]['xPath']) # Select one option having highest similarity score.
            elif len(filtered_options_above_min_threshold) != 0 or element_metadata['required']: # Select one option having highest similarity score.
                 _update_set(answer_xPaths, relevant_options[0]['xPath']) # Ensures atleast one option is selected.
            else: # If all options has similarity score below minimum threshold and the field is not required
                logger.debug(f'💬  All options score below minimum similarity threshold ({min_threshold}) and field is optional. Skipping...')
                return
        return answer_xPaths

    def _extract_options_from_dom(self, dom: str, dom_parents_xpath: list = [], current_element_xpath: str = None, multiselect_field_metadata: Dict[str, Any] = None, filter_if_input: bool = False) -> Dict[str, str]:

        '''
        Extract Options
        '''
        # Parse the updated HTML DOM using lxml (fragment of HTML as string).
        tree = lxml_html.fragment_fromstring(dom, create_parent="div")
        # Dictionary to store option text mapped to their XPath.
        options = {}
        # Log valid xpath into options
        def log_xpath_option(option:str, xpath:str) -> bool:
            """
            Helper function to validate and store option if XPath is unique and appears after the target element in DOM order.
            Returns True if option logged successfully, else False.
            """
            if (
                (xpath) 
                and (self.WebParserUtils.is_unique_xpath(xpath)) 
                and ((not current_element_xpath) or (current_element_xpath and self.WebParserUtils.is_element_after(xpath, current_element_xpath)))
                and not any(blk.lower() in option.lower() for blk in config.blacklist.list_option_blacklist_partial)
            ):
                options[option] = xpath
                return True
            return False

        visited_elements = set()

        logger.info("👣 Traversing DOM Difference Tree in search for options...")

        # Iterate over all elements in the updated DOM fragment to identify options.
        for el in tree.iter():
            # Handle special case for multiselect elements with nested option identifiers.
            if multiselect_field_metadata:
                if multiselect_field_metadata['type'] == "multiselect" and isinstance(multiselect_field_metadata['options'], str):
                    multiselect_option_identifier = multiselect_field_metadata['options']
                    if any(val == multiselect_option_identifier for val in el.attrib.values()):
                        # Skip elements that contain nested children with the same option identifier.
                        has_nested_matches = False
                        for child in el.iterdescendants():
                            if child in visited_elements:
                                continue # Iter next child if this element is already visited
                            # Check if element 'el' has nested matches (children having `multiselect_option_identifier` attr_value)
                            if any(val == multiselect_option_identifier for val in child.attrib.values()):
                                has_nested_matches = True
                                break
                        if has_nested_matches:
                            continue # Skip this element if it contains nested matchs

            # Skip elements containing multiple input descendants to avoid ambiguous options.
            inputs = el.findall(".//input")
            if len(inputs) > 1:
                continue

            # Extract trimmed text content; skip if empty or blacklisted.
            text_content = el.text_content().strip() if el.text_content() else None
            # Skip elements without text content or those containing blacklisted options in their text.
            if not text_content or any(blk.lower() in text_content.lower() for blk in config.blacklist.default_options_placeholder_blacklist):
                continue # Skip elements without text content or contain blacklisted options  

            # Skip elements having children with their own meaningful text content (avoid nested option duplicates).
            allowed_child_text_partial = ['*'] # Partially matched (optionally implement exact match exceptions list in future)
            has_text_child = any(
                (
                    (child.text_content().strip()) # Check if the child has non-empty text content.
                    and (child.text_content().strip() not in allowed_child_text_partial)
                )
                for child in el.iterchildren()
                if child.text_content()
            )
            if has_text_child:
                continue  # Skip elements with text-containing children

            # If 'el' has one input descendant, get its XPath as per Complete DOM
            if len(inputs) == 1:
                is_new_input_loaded = False
                if log_xpath_option(text_content, self.WebParserUtils.compute_relative_xpath_lxml(inputs[0], verify_xpath=True)): # log if valid, otherwise fallback finding absolute XPath
                    is_new_input_loaded = True
                elif log_xpath_option(text_content, self.WebParserUtils.compute_relative_xpath_lxml(inputs[0], verify_xpath=True)): # fallback finding absolute XPath
                    is_new_input_loaded = True
                else:
                    pass # Continue finding XPath for current el, and forget about its input-child
                if is_new_input_loaded:
                    if filter_if_input: # Filter the dictionary if atleast one option is identified
                        # Filter the dictionary keeping only items having 'input' element's xpath. (Discard items whose xpath points other elements like 'div', 'li', etc.) 
                        options = {k: v for k, v in options.items() if "input" in v.rsplit('/', 1)[-1]} # Remove div fields if atleast one input can be added to the options to advance processing.
                    continue # Proceed with next element. 
            
            # If we've reached here, we have an element (containing text*) with no children containing text or input fields.
            else: # Generate XPath of current 'el'
                # Generate relative xPath for lxml.html.Element instance.
                xpath = self.WebParserUtils.compute_relative_xpath_lxml(el, verify_xpath=True)
                if (not xpath) or (not log_xpath_option(text_content, xpath)):
                    # Implement parent fallback for n tries | Strategy to find unique XPath by traversing back through parents
                    if not xpath: # If `compute_relative_xpath_lxml` returned 'None', it means XPath wasn't unique.
                        xpath = self.WebParserUtils.get_valid_parent_xpath(el)
                        if xpath and log_xpath_option(text_content, xpath): # Successfully discovered unique xpath
                            continue    # Search next element if valid xpath was discovered and logged.
                    if dom_parents_xpath:
                        valid_xpath: set = self.WebParserUtils.build_absolute_xpath_lxml(tree, el, dom_parents_xpath)
                        for xpath in valid_xpath:
                            log_xpath_option(text_content, xpath) # log if valid
                        # Final Fallback: If we failed to build absolute xPath using this strategy
                        if not text_content in options: 
                            # Compute XPath using the JS algorithm implemented within `compute_absolute_xpath_lxml`.
                            log_xpath_option(text_content, self.WebParserUtils.compute_absolute_xpath_lxml(el)) # log if valid
        return options

    def _extract_options_from_dom_advance(self, dom: str, dom_parents_xpath: list = [], current_element_xpath: str = None, multiselect_field_metadata: Dict[str, Any] = None, filter_if_input: bool = False, blacklist: list = config.blacklist.default_options_placeholder_blacklist, get_input_elements: bool = True, get_button_elements: bool = True, get_text_elements: bool = True) -> Dict[str, str]:
        '''
        Extract Options
        '''
        # Parse the updated HTML DOM using lxml (fragment of HTML as string).
        tree = lxml_html.fragment_fromstring(dom, create_parent="div")
        # Initialize an empty dictionary to store the options mapped with its corresponding xPath.
        options = {}
        # Log valid xpath into options
        def log_xpath_option(option:str, xpath:str) -> bool:
            """
            Helper function to validate and store option if XPath is unique and appears after the target element in DOM order.
            Returns True if option logged successfully, else False.
            """
            if (
                (xpath) 
                and (self.WebParserUtils.is_unique_xpath(xpath)) 
                and ((not current_element_xpath) or (current_element_xpath and self.WebParserUtils.is_element_after(xpath, current_element_xpath)))
                and not any(blk.lower() in option.lower() for blk in config.blacklist.list_option_blacklist_partial)
            ):
                options[option] = xpath
                return True
            return False
        
        visited_elements = set()
        # Iterate over all elements in the parsed HTML fragment.
        for el in tree.iter():
            # Check if type is 'multiselect' and has associated id (useful for searching options) in metadata under 'options'.
            if multiselect_field_metadata:
                if multiselect_field_metadata['type'] == "multiselect" and isinstance(multiselect_field_metadata['options'], str):
                    multiselect_option_identifier = multiselect_field_metadata['options']
                    if any(val == multiselect_option_identifier for val in el.attrib.values()):
                        # Check if element contains nested elements with target attribute
                        has_nested_matches = False
                        for child in el.iterdescendants():
                            if child in visited_elements:
                                continue # Iter next child if this element is already visited
                            # Check if element 'el' has nested matches (children having `multiselect_option_identifier` attr_value)
                            if any(val == multiselect_option_identifier for val in child.attrib.values()):
                                has_nested_matches = True
                                break
                        if has_nested_matches:
                            continue # Skip this element if it contains nested matchs
            
            # Get nested input and button elements
            nested_input_elements = el.findall(".//input")
            nested_button_elements = el.xpath(".//*[self::button or (self::input and (@type='button' or @type='submit')) or @role='button']")
            if (get_input_elements and len(nested_input_elements) > 1) or (get_button_elements and len(nested_button_elements) > 1):
                continue # Skip if current el nests multiple inputs or buttons
            
            # Extract and clean text content of the current element (strip leading/trailing spaces).
            text_content = el.text_content().strip() if el.text_content() else None

            ''' Log Input Fields '''
            if get_input_elements and len(nested_input_elements) == 1: # If 'el' has one input descendant, get its XPath as per Complete DOM
                is_new_el_loaded = False
                if log_xpath_option(text_content, self.WebParserUtils.compute_relative_xpath_lxml(nested_input_elements[0], verify_xpath=True)): # log if valid, otherwise fallback finding absolute XPath
                    is_new_el_loaded = True
                elif log_xpath_option(text_content, self.WebParserUtils.compute_relative_xpath_lxml(nested_input_elements[0], verify_xpath=True)): # fallback finding absolute XPath
                    is_new_el_loaded = True
                else:
                    pass # Continue finding XPath for current el, and forget about its input-child
                if is_new_el_loaded:
                    continue # Proceed with next element. 
            
            ''' Log Button Fields '''
            if get_button_elements and len(nested_button_elements) == 1:  # If 'el' has one button descendant, get its XPath as per Complete DOM
                is_new_el_loaded = False
                if log_xpath_option(text_content, self.WebParserUtils.compute_relative_xpath_lxml(nested_button_elements[0], verify_xpath=True)): # log if valid, otherwise fallback finding absolute XPath
                    is_new_el_loaded = True
                elif log_xpath_option(text_content, self.WebParserUtils.compute_relative_xpath_lxml(nested_button_elements[0], verify_xpath=True)): # fallback finding absolute XPath
                    is_new_el_loaded = True
                else:
                    pass # Continue finding XPath for current el, and forget about its button-child
                if is_new_el_loaded:
                    continue # Proceed with next element.

            ''' Log Text Fields '''
            if get_text_elements:
                # Skip elements without text content or those containing blacklisted options in their text.
                if not text_content or any(blk.lower() in text_content.lower() for blk in blacklist):   # No text nested or text having blacklisted value.
                    continue # Skip elements without text content or contain blacklisted options   
                # Check if any direct child element of the current element has non-empty text content.
                allowed_child_text_partial = ['*'] # Partially matched (optionally implement exact match exceptions list in future)
                has_text_child = any(
                    (
                        (child.text_content().strip()) # Check if the child has non-empty text content.
                        and (child.text_content().strip() not in allowed_child_text_partial)
                    )
                    for child in el.iterchildren()
                    if child.text_content()
                )
                # If the element has text-containing children, skip it.
                if has_text_child:
                    continue  # Skip elements with text-containing children
                # If we've reached here, we have an element (containing text*) with no children containing text or input fields.
                # Generate relative xPath for lxml.html.Element instance.
                xpath = self.WebParserUtils.compute_relative_xpath_lxml(el, verify_xpath=True)
                if (not xpath) or (not log_xpath_option(text_content, xpath)):
                    # Implement parent fallback for n tries | Strategy to find unique XPath by traversing back through parents
                    if not xpath: # If `compute_relative_xpath_lxml` returned 'None', it means XPath wasn't unique.
                        xpath = self.WebParserUtils.get_valid_parent_xpath(el)
                        if xpath and log_xpath_option(text_content, xpath): # Successfully discovered unique xpath
                            continue    # Search next element if valid xpath was discovered and logged.
                    valid_xpath: set = self.WebParserUtils.build_absolute_xpath_lxml(tree, el, dom_parents_xpath)
                    for xpath in valid_xpath:
                        log_xpath_option(text_content, xpath) # log if valid
                    # Final Fallback: If we failed to build absolute xPath using this strategy
                    if not text_content in options: 
                        # Compute XPath using the JS algorithm implemented within `compute_absolute_xpath_lxml`.
                        log_xpath_option(text_content, self.WebParserUtils.compute_absolute_xpath_lxml(el)) # log if valid

    def _get_options(self, element_metadata: Dict[str, Any], target_action: Literal["click","scroll"], target_xpath: str = None, searchable_options_and_expected_answers: Dict[str,list] = {}, filter_if_input: bool = False) -> Dict[str,str]:
        """
        Extracts option elements that appear after performing a UI interaction (click or scroll) 
        on a target web element.

        Args:
            element_metadata (Dict[str, Any]): Metadata describing the target form field.
            target_action (Literal["click", "scroll"]): Type of user interaction to perform.
            target_xpath (str, optional): XPath of the target element to interact with.
            searchable_options_and_expected_answers (Dict[str, list], optional): 
                A dictionary of search inputs and expected matching results (for searchable dropdowns).
            filter_if_input (bool): Whether to apply filtering logic when options come from an input field.

        Returns:
            Dict[str, str]: A dictionary mapping option text to their corresponding XPaths.
        """

        # -------------------------------------------------------------------------
        # Step 1: Cache All DOM Elements Before Interaction
        # -------------------------------------------------------------------------
        ''' Snapshot DOM Before Action '''
        self.driver.execute_script("""
            window._elementsBeforeClick = [];
            function traverse(node) {
                if (!node) return;
                window._elementsBeforeClick.push(node);
                node.childNodes.forEach(traverse);
                if (node.shadowRoot) traverse(node.shadowRoot);
            }
            traverse(document.body);
        """)

        options: Dict[str, str] = {}

        # -------------------------------------------------------------------------
        # Step 2: Perform Action Based on the Target Type (Click / Scroll)
        # -------------------------------------------------------------------------
        if target_action.lower() == 'click':

            ''' Click Field '''
            # Fetch the updated HTML DOM after clicking the element, along with possible parent xPaths.
            html_diff_dom, html_diff_parents_xPath = self.FormInteractorUtils.get_updated_dom_after_click(target_xpath, wait=1)  # type : str, List[str]

            # Capture the currently focused (active) element and its characteristics
            active_element = self.driver.execute_script("return document.activeElement")
            li_count = self.driver.execute_script("""
                const el = document.activeElement;
                return el.querySelectorAll('li').length;
            """)
            active_element_info = self.driver.execute_script("""
                const el = document.activeElement;
                return {
                    tag: el.tagName,
                    role: el.getAttribute('role'),
                };
            """)


            # ---------------------------------------------------------------------
            # Step 2(a): Handle Searchable Dropdowns (Input-Based Search)
            # ---------------------------------------------------------------------
            ''' If input is searchable and suggestions are expected '''
            if active_element.tag_name.lower() == 'input' and searchable_options_and_expected_answers:
                # Search using type-keys
                for search_candidate in searchable_options_and_expected_answers.keys():
                    
                    # Type into input and capture changed DOM
                    candidate_diff_dom, candidate_diff_parents_xPath = self.FormInteractorUtils.get_updated_dom_after_typing(search_candidate, delay=0.1, wait=2)  # type : str, List[str]
                    fragments = lxml_html.fragments_fromstring(candidate_diff_dom)
                    candidate_diff_dom_innerText = '\n'.join(fragment.text_content().strip() for fragment in fragments if hasattr(fragment, 'text_content')) # Join the text from each fragment
                    
                    # ''' Case 1: Auto-suggestion appears on typing '''
                    if candidate_diff_dom_innerText:
                        active_element_xpath: str = self.WebParserUtils.get_xpath(self.driver.execute_script("return document.activeElement"))
                        # Extract options (proceed identifying the answer of the corresponding search_candidate)
                        options = self._extract_options_from_dom(
                            dom = candidate_diff_dom, 
                            dom_parents_xpath = candidate_diff_parents_xPath, 
                            current_element_xpath = active_element_xpath, 
                            multiselect_field_metadata = element_metadata if element_metadata['type'] == 'multiselect' else None,
                            filter_if_input = filter_if_input
                        )

                    # ''' Case 2: Auto-searching not supported. Suggestion would appears after pressing Enter '''
                    else:
                        # Press enter and capture difference dom.
                        candidate_diff_dom, candidate_diff_parents_xPath = self.FormInteractorUtils.get_updated_dom_after_enterkey(wait=1) # type : str, List[str]
                        current_element_xpath = self.WebParserUtils.get_validated_xpath(element_metadata)
                        options = self._extract_options_from_dom(
                            dom = candidate_diff_dom, 
                            dom_parents_xpath = candidate_diff_parents_xPath, 
                            current_element_xpath = current_element_xpath,
                            multiselect_field_metadata = element_metadata if element_metadata['type'] == 'multiselect' else None,
                            filter_if_input = filter_if_input
                        )

                        # Search resulted in a single, auto-selected value — return empty to signal resolution
                        if self.driver.execute_script("return document.activeElement").tag_name.lower() != 'input' and self.driver.execute_script("return document.activeElement.innerText;") and len(options) == 1:
                            return {}   # Returning no options since pressing enter key already resolved field. Returning empty options ensures field resolution is treated as true.
                        
                        # Fallback: Click again if nothing was captured, and proceed with standard DOM difference search.
                        elif not options:
                            # Unfocus selection
                            self.driver.execute_script("if (document.activeElement) document.activeElement.blur();")
                            self.FormInteractorUtils.click_safe_heading_to_unfocus()
                            html_diff_dom, html_diff_parents_xPath = self.FormInteractorUtils.get_updated_dom_after_click(current_element_xpath, wait=1)  # type : str, List[str]
                            break

                        # Options exists and was not auto-selected
                        else:
                            pass # Proceed identifying the corresponding answer of the search_candidate
                    
                    # Match options against expected answers using fuzzy matching
                    if options:
                        for expected_answer in searchable_options_and_expected_answers[search_candidate]:
                            relevant_option: List = self._retrieve_relevant_options(options, expected_answer, threshold=92, top_k=1)
                            if relevant_option:
                                return {relevant_option[0]['option']: relevant_option[0]['xPath']}

                    # Clear input and search for next candidate
                    actions = ActionChains(self.driver)
                    for _ in range(len(search_candidate)+1):
                        actions.send_keys(Keys.BACKSPACE)
                        actions.pause(0.1)
                    actions.perform()
                
                options = {} # Reset if no matches found 

            # ---------------------------------------------------------------------
            # Step 2(b): Handle Static Listboxes (UL-List Based)
            # ---------------------------------------------------------------------
            elif active_element.tag_name.lower() != 'input' and active_element_info['tag'] == 'ul' and active_element_info['role'] == 'listbox' and li_count > 0:
                active_element_html = self.driver.execute_script("return document.activeElement.outerHTML;")
                options = self._extract_options_from_dom(dom=active_element_html)

        elif target_action.lower() == 'scroll':
            
            ''' Scroll Field '''
            # Fetch the updated HTML DOM after scrolling the element, along with possible parent xPaths.
            html_diff_dom, html_diff_parents_xPath = self.FormInteractorUtils.get_updated_dom_after_scroll(target_xpath, wait=0)  # type : str, List[str]

        else:
            logger.error(f"❌    Invalid argument: `target_action` must be either 'click' or 'scroll'. Given: {target_action}.")
            return dict()

        # -------------------------------------------------------------------------
        # Step 3: Extract Options from Final DOM Snapshot (Fallback/Default Case)
        # -------------------------------------------------------------------------
        if not options:
            # Get the updated XPath of the target element.
            # Remapping of original input element's xpath if the structure was changed in DOM after performing the action. 
            current_element_xpath = self.WebParserUtils.get_validated_xpath(element_metadata)

            options = self._extract_options_from_dom(
                dom = html_diff_dom, 
                dom_parents_xpath = html_diff_parents_xPath, 
                current_element_xpath = current_element_xpath if current_element_xpath else None, 
                multiselect_field_metadata = element_metadata if element_metadata['type'] == 'multiselect' else None, 
                filter_if_input=filter_if_input
            )

        # -------------------------------------------------------------------------
        # Step 6: Filter Options
        # -------------------------------------------------------------------------
        # Filter out options that existed in the DOM before the action, using elements cached in window._elementsBeforeClick.
        filtered_valid_options_xpath: List[str] = self.driver.execute_script("""
            const newXpaths = arguments[0];

            function elementFromXPath(xpath) {
                const result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                return result.singleNodeValue;
            }

            const elementsBefore = window._elementsBeforeClick || [];
            const filteredXpaths = [];

            newXpaths.forEach(xpath => {
                const el = elementFromXPath(xpath);
                if (!el) return;

                const isNew = !elementsBefore.some(beforeEl => beforeEl.isSameNode(el));
                if (isNew) filteredXpaths.push(xpath);
            });

            return filteredXpaths;
        """, list(options.values()))
        # Keep only filtered options which are truly new.
        options = {k:v for k,v in options.items() if v in filtered_valid_options_xpath}
        # Filter by blacklist
        options = {k:v for k,v in options.items() if not any(blk.lower() in k.lower() for blk in config.blacklist.list_option_blacklist_partial)}

        # -------------------------------------------------------------------------
        # Step 7: Return
        # -------------------------------------------------------------------------
        logger.info(f"📦    Returning {len(options)} discovered options...")
        return options

    def _get_search_option_candidates(self, element_metadata: Dict[str, Any]) -> Dict[str, list]:
        search_option_candidates: Dict[str, list] = {}
        if (
            self.ParsedDataUtils.is_match(element_metadata, {"options.category": "Education"})
            and (
                self.ParsedDataUtils.is_match(element_metadata, {"options.type": "School or University"}) 
                or self.ParsedDataUtils.is_match(element_metadata, {"options.type": "Degree"}) 
                or self.ParsedDataUtils.is_match(element_metadata, {"options.type": "Field of Study or Major"})
            )
        ):
            def get_nested_value(key_path: str):
                return self.ParsedDataUtils.get_nested_value(element_metadata, key_path)
            search_option_candidates: Dict[str, list] = user_data_config.search_option_candidates[get_nested_value('options.category')][get_nested_value('options.id')-1][get_nested_value('options.type')]
        return search_option_candidates

    def _click_answer_and_capture_new_fields(self, answer_xPath: str, current_element_xPath: str, selector: Select = None) -> set:
        """
        Clicks a selectable answer (e.g., radio/option), waits for DOM to stabilize,
        and returns a set of XPath strings for newly added fields/buttons that appear after
        the current element in the DOM.

        Args:
            answer_xPath (str): XPath of the answer to click or visible text if using Select.
            current_element_xPath (str): XPath of the current element used to determine DOM order.
            selector (Select, optional): Selenium Select object if the answer is part of a dropdown.

        Returns:
            set: A set of relative XPath strings for newly added, visible form fields/buttons.
        """
        
        # Capture DOM state before interaction
        dom_before = self.driver.page_source

        # Perform the click or selection
        if selector:
            selector.select_by_visible_text(answer_xPath) # We treated option text as xPath
        else:
            self.FormInteractorUtils.click(answer_xPath) # Click the answer

        # Wait for DOM to stabilize after interaction
        self.WebParserUtils.wait_for_stable_dom(padding=0)

        # Capture DOM state after interaction
        dom_after = self.driver.execute_script("return document.body.innerHTML")
        
        # Define field-related search queries
        search_queries = [
            "input",
            "//textarea",
            "//select",
            ".//button",
            ".//input[@type='submit']",
            ".//input[@type='button']",
            ".//*[@role='button']"
        ]

        # Identify new elements added to the DOM
        new_elements: List[str] = self.WebParserUtils.get_new_elements(dom_before, dom_after, search_queries, return_html=True)
        
        # Convert new elements to relative XPath
        new_elements_xPaths: set[str] = self.WebParserUtils.compute_relative_xpath_str(new_elements, verify_xpath=True) # (Note: There are still possibilities of false positives.)    
        
        # Keep only visible elements
        new_elements_xPaths: set[str] = {xPath for xPath in new_elements_xPaths if self.WebParserUtils.is_xpath_visible(xPath)}
        
        # Retain only those fields that appear after the current element in DOM
        new_elements_xPaths: set[str] = {xPath for xPath in new_elements_xPaths if self.WebParserUtils.is_element_after(xPath, current_element_xPath)}

        return new_elements_xPaths

    def handle_text_input(self, element_metadata: Dict[str, Any]):

        def _resolve_predefined_text_fields(element_metadata) -> Optional[str]:
            
            def get_nested_value(key_path: str):
                return self.ParsedDataUtils.get_nested_value(element_metadata, key_path)

            if (
                self.ParsedDataUtils.is_match(element_metadata, {"options.category": "Work Experience"})
                or self.ParsedDataUtils.is_match(element_metadata, {"options.category": "Education"})
            ):
                text = self.UserData.data[get_nested_value('options.category')][get_nested_value('options.id')-1][get_nested_value('options.type')]
                return text

            text = None
            # Email
            if self.ParsedDataUtils.is_substrings_in_item(element_metadata, standard_label_keys, ['Email'], case_sensitive=True):
                text = self.UserData.data["Email"]
            # Password
            elif (
                element_metadata['type'] == 'password'
                or self.ParsedDataUtils.is_substrings_in_item(element_metadata, standard_label_keys, ['Password'], case_sensitive=True)
            ):
                text = self.UserData.data["Password"]
            # First Name
            elif self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['first name'], normalize_whitespace=True):
                if self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['preferred']) and not element_metadata['required']:
                    return True
                text = self.UserData.data["First Name"]
            # Last Name
            elif self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['last name'], normalize_whitespace=True):
                text = self.UserData.data["Last Name"]
            # Full Name / Signature
            elif (
                self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['Name', 'Signature'], case_sensitive=True)
                and not self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['Middle'])
            ):
                if self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['preferred']) and not element_metadata['required']:
                    return True
                text = self.UserData.data["Name / Full Name / Signature"]
            # Postal/Zip Code
            elif self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['postal code', 'zip code'], normalize_whitespace=True):
                text = self.UserData.data["Postal_code"]
            # Address Line 2
            elif self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['address line 2'], normalize_whitespace=True):
                text = self.UserData.data["Address Line 2"]
            # Address Line 1
            elif self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['address line 1', 'address line'], normalize_whitespace=True):
                text = self.UserData.data["Address Line 1"]
            # City
            elif self.ParsedDataUtils.is_substrings_in_item(element_metadata, standard_label_keys, ['City'], case_sensitive=True):
                text = self.UserData.data["City"]
            # State
            elif self.ParsedDataUtils.is_substrings_in_item(element_metadata, standard_label_keys, ['State'], case_sensitive=True):
                text = self.UserData.data["State"]
            # Phone Extension
            elif self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['phone extension'], normalize_whitespace=True):
                text = self.UserData.data["Phone Extension"]
            # Phone Number
            elif (
                self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['phone number', 'mobile number', 'mobile phone'], normalize_whitespace=True) 
                or self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, ['phone', 'phone*'], exact_match=True, normalize_whitespace=True) 
            ):
                text = self.UserData.data["Phone Number"]
            # Country
            elif self.ParsedDataUtils.is_substrings_in_item(element_metadata, standard_label_keys, ['Country'], case_sensitive=True):
                text = self.UserData.data["Country"]
            # Location
            elif self.ParsedDataUtils.is_substrings_in_item(element_metadata, standard_label_keys, ['Location'], case_sensitive=True):
                text = self.UserData.data["Location"]
            # Address Line 1
            elif self.ParsedDataUtils.is_substrings_in_item(element_metadata, standard_label_keys, ['Address'], case_sensitive=True):
                text = self.UserData.data["Address Line 1"]
            # LinkedIn
            elif self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys + ['placeholder'], ['linkedin']):
                text = self.UserData.data["LinkedIn Profile"]
            # GitHub
            elif self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys + ['placeholder'], ['github']):
                text = self.UserData.data["GitHub Profile"]
            # Salary Expectation
            elif (
                self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys + ['placeholder'], ['salary'])
                and (
                    self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys + ['placeholder'], ['desired'])
                    or self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys + ['placeholder'], ['expect'])
                ) 
                and element_metadata['required']
            ):
                text = self.UserData.data["Salary Expectation"]

            return text

        ''' 
        Initialize xPath
        '''
        xPath = self.WebParserUtils.get_validated_xpath(element_metadata)
        if not xPath: # Valid xPath does not exists. Could have shifted in DOM
            return not element_metadata['required']
        if not self.FormInteractorUtils.is_interactable(xPath):
            logger.info("💬 Element not interactable. Skipping.")
            return True

        ''' Return if element is not enabled '''
        if not self.WebParserUtils.get_element(xPath).is_enabled():
            return not element_metadata['required']

        ''' Identify 'Answer' for Input '''
        answer = _resolve_predefined_text_fields(element_metadata)
        if answer:
            logger.info("🪶  Answer found in predefined settings.")
            field_value = val if (val := self.WebParserUtils.get_element(xPath).get_attribute("value")) not in [""] else None
            if field_value and (field_value == answer):
                logger.info("✔️  Field already contains the correct predefined answer; skipping input.")
                return True
        else: 
            # Avoid nonessential field
            if not element_metadata['required']:
                return True
            
            question: str | None = self._get_question(element_metadata)
            if question:
                logger.info("🤖  LLM Agent generating the best possible response...")
                answer = self.PromptAgent.resolve(question=question) # Get answer using LLM.
                logger.info("🤖 Agent Response: %s", answer)
            else:
                answer = 'N/A'

        try:
            self.FormInteractorUtils.scroll_to_element(xPath)
            return self.FormInteractorUtils.safe_send_keys(xPath, answer, clear_before=True)
        except Exception as e:
            logger.warning(f"📝  Failed to send keys: {e}")
            return not element_metadata['required']

    def handle_radio(self, element_metadata: Dict[str, Any]) -> Union[bool, set]:
        """ Handle radio button selection """

        ''' 
        Initialize xPath
        '''
        xPath = self.WebParserUtils.get_validated_xpath(element_metadata)
        if not xPath: # Valid xPath does not exists. Could have shifted in DOM
            return not element_metadata['required']
        if not self.FormInteractorUtils.is_interactable(xPath):
            logger.info("💬  Element not interactable. Skipping.")
            return True

        '''
        Scroll to element
        '''
        self.FormInteractorUtils.scroll_to_element(xPath)

        '''
        Get Answer
        '''
        answer_xPath = self._get_answer_xpath(element_metadata, element_metadata['options'])
        if not answer_xPath:
            logger.info("Answer not returned. The field could be optional and irrelevant. Skipping...")
            return True

        ''' 
        Click Answer
        '''
        current_element_xPath = self.WebParserUtils.get_validated_xpath(element_metadata)
        new_elements_xPaths = self._click_answer_and_capture_new_fields(answer_xPath, current_element_xPath)
        
        ''' 
        Return 
        '''
        if new_elements_xPaths: # New fields were added
            return new_elements_xPaths # Return set of xPaths of those new fields.
        return True # Return success
   
    def handle_dynamic_list(self, element_metadata: Dict[str, Any], answer: str = None) -> Union[bool, set]:
        
        ''' 
        Initialize Field xPath
        '''
        logger.info("👉  Resolving Dynamic List Field")
        target_xpath: str = self.WebParserUtils.get_validated_xpath(element_metadata)
        if not target_xpath: # Valid xPath does not exists. Could have shifted in DOM
            return not element_metadata['required']
        if not self.FormInteractorUtils.is_interactable(target_xpath):
            logger.info("💬  Element not interactable. Skipping.")
            return True

        '''
        Get Option(s)
        '''
        options: Dict = {}
        logger.info("🔎  Fetching Options...")
        search_option_candidates: Dict[str, list] = self._get_search_option_candidates(element_metadata)
        options: Dict = self._get_options(
            element_metadata, 
            target_action = 'click',
            target_xpath = target_xpath,
            searchable_options_and_expected_answers = search_option_candidates
        )

        if not options:
            logger.info(f"💬  No options were returned. Returning {not element_metadata['required']} since the field if of type -> 'required':{element_metadata['required']}.")
            self.FormInteractorUtils.click_safe_heading_to_unfocus()
            return not element_metadata['required']
        # Flow Control for pre-selected option
        if (
            # Flow Control Variable (refresh disabled for known identifiers)
            not self.refresh_answer 
            # Option is selected and is not a default placeholder
            and (
                element_metadata['placeholder'] in options.keys()
                and not any(blk.lower() in element_metadata['placeholder'].lower() for blk in config.blacklist.default_options_placeholder_blacklist)
            )
            # Field is mentioned in escape refresh identifier
            and (
                self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, system_config.escape_refresh_dynamic_list_identifiers_partial, normalize_whitespace=True)
                or self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, system_config.escape_refresh_dynamic_list_identifiers_full, normalize_whitespace=True, exact_match=True)
            )
        ):
            self.FormInteractorUtils.click_safe_heading_to_unfocus()
            return True

        '''
        Get Answer
        '''
        logger.info("🧪  Resolving Answer...")
        if answer:  # Check if answer was already provided.
            if answer in options:
                answer_xPath = options.get(answer)
            else:
                relevant_options = self._retrieve_relevant_options(options, answer)
                self.ParsedDataUtils.pretty_print(relevant_options) # Print relevant options
                answer_xPath = relevant_options[0]['xPath'] # Top-most option (having highest similarity score) is selected.
        else:   # Use LLM to get the answer, if not provided.
            answer_xPath: Optional[str] = self._get_answer_xpath(element_metadata, options)
            if not answer_xPath:
                logger.info("Answer not returned. The field could be optional and irrelevant. Skipping...")
                self.FormInteractorUtils.click_safe_heading_to_unfocus()
                return True

        ''' 
        Click Answer
        '''
        current_element_xPath = self.WebParserUtils.get_validated_xpath(element_metadata)
        new_elements_xPaths = self._click_answer_and_capture_new_fields(answer_xPath, current_element_xPath)

        ''' 
        Return 
        '''
        if new_elements_xPaths: # New fields were added
            return new_elements_xPaths # Return set of xPaths of those new fields.
        return True # Return success

    def handle_dynamic_multiselect(self, element_metadata: Dict[str, Any]) -> bool:

        '''
        Initialize initial XPath and Maximum Iterations
        '''
        target_xpath: str = self.WebParserUtils.get_validated_xpath(element_metadata)
        if not target_xpath: # Valid xPath does not exists. Could have shifted in DOM
            return not element_metadata['required']
        if not self.FormInteractorUtils.is_interactable(target_xpath):
            logger.info("💬  Element not interactable. Skipping.")
            return True
        # If absolute XPath is lost, then update default XPath
        # This makes overall execution efficient, by avoiding re-calculation of XPath again and again.
        if not self.WebParserUtils.is_absolute_xpath(target_xpath):
            element_metadata['xPath'] = target_xpath
        # Set maximum iterations. Depth of option should be less than 'max_iterations'
        max_iterations: int = 3

        '''
        Flow Control Variable
        '''
        # If refresh is disabled, avoid refreshing known entries from config file.
        if not self.refresh_answer and self.ParsedDataUtils.is_substrings_in_item(element_metadata, stardard_field_search_keys, system_config.escape_refresh_multiselect_identifiers_partial, normalize_whitespace=True):
            target_element = self.WebParserUtils.get_element(target_xpath)
            if target_element:
                parent_element = target_element.find_element(By.XPATH, '..').find_element(By.XPATH, '..')
                parent_element_text: str = self.driver.execute_script(f"""
                    var xpath = "{self.WebParserUtils.get_xpath(parent_element)}";
                    var element = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
                    var text = element ? (element.textContent || element.innerText) : '';
                    return (typeof text === 'string') ? text : ''
                """)
                some_selection_identifiers: set = {'1 item selected'}
                # Check if 'some option (selection)' is associated with the field
                if any(identifier in parent_element_text.lower() for identifier in some_selection_identifiers):
                    logger.info("💬  An option is already selected. Returning...")
                    return True # Continue to next element. Abort processing field

        '''
        Loop until the selection/sub-selection(s) is/are cleared.
        Loop stops with a guranteed return statement or max_iteration condition.
        '''
        answer_label: str = None
        for _ in range(max_iterations):

            '''
            Get Initial Option(s)
            '''
            options: Dict[str, str] = {}
            search_option_candidates: Dict[str, list] = self._get_search_option_candidates(element_metadata)
            captured_snapshot: Dict[str, str] = self._get_options(
                element_metadata, 
                target_action = 'click', 
                target_xpath = target_xpath, 
                searchable_options_and_expected_answers = search_option_candidates, 
                filter_if_input = True
            )

            if (
                not captured_snapshot
                or (self.driver.execute_script("return document.activeElement").tag_name.lower() != 'input' and not self.driver.execute_script("return document.activeElement.innerText;"))
                or (len(captured_snapshot) == 1 and answer_label and self.driver.execute_script("return document.activeElement.innerText;") == answer_label)    # Answer already selected during the search process.
            ):
                if not captured_snapshot and (answer_label is None) and self.ParsedDataUtils.is_match(element_metadata, {"options.category": "Education"}) and not self.driver.execute_script("return document.activeElement.innerText;"):
                    logger.info(f"Unable to resolve. Education Section ID: {self.ParsedDataUtils.get_nested_value(element_metadata, "options.id")}")
                    return False
                self.FormInteractorUtils.click_safe_heading_to_unfocus()
                return True
            current_snapshot = captured_snapshot   # `current_snapshot` preserves valid snapshot of options in frame
            options |= captured_snapshot  # Append new options
            logger.info(f"📦    Collected {len(options)} options...")

            '''
            Scroll: Until New Option(s) Arrives
            '''
            answer_matched = False
            while True:
                # Attempt answer resolution during the collection phase
                answer_xPath = self._progressive_answer_resolver(element_metadata, current_snapshot)
                if answer_xPath:
                    answer_matched = True
                    # Input element in XPath signifies end of search.
                    if 'input' in answer_xPath.rsplit('/', 1)[-1] or answer_xPath.startswith('//input'):
                        return self.FormInteractorUtils.click(answer_xPath) # Click Answer & Return
                    # Nest down to reveal options generated by current answer in next iteration.
                    else: 
                        target_xpath = answer_xPath
                        answer_label = next(k for k,v in captured_snapshot.items() if v == answer_xPath)
                        break

                # Target XPath becomes XPath of the last valid element in current_snapshot.
                target_xpath = next((xpath for xpath in reversed(current_snapshot.values()) if self.WebParserUtils.is_unique_xpath(xpath)), None)
                captured_snapshot: Dict[str, str] = self._get_options(element_metadata, target_action='scroll', target_xpath=target_xpath, filter_if_input=True)
                if (not captured_snapshot) or (captured_snapshot.keys() == current_snapshot.keys()): # End of options.
                    break
                current_snapshot = captured_snapshot   # `current_snapshot` preserves valid snapshot of options in frame
                options |= captured_snapshot  # Append new options
                logger.info(f"📦    Collected {len(options)} options...")
            if answer_matched: 
                continue    # Nest down next iteration (with updated target_xpath as answer_xPath)

            '''
            Filter All Options
            '''
            logger.info(f"📦    Total {len(options)} options. Applying Filter...")
            options = {
                k: v for k, v in options.items()
                if k not in config.blacklist.multiselect_option_blacklist_full
                and not any(keyword in v for keyword in config.blacklist.multiselect_xpath_keyword_blacklist_partial)
            }
            logger.info(f"📦    Preserved {len(options)} options. Searching answer...")

            '''
            Get Answer
            '''
            answer_xPath: Optional[str] = self._get_answer_xpath(element_metadata, options)
            if not answer_xPath:
                logger.info("Answer not returned. The field could be optional and irrelevant. Skipping...")
                self.FormInteractorUtils.click_safe_heading_to_unfocus()
                return True
            # We'd loose the XPath while tracing back, therefore, save the name.
            answer_label = next((k for k, v in options.items() if v == answer_xPath), None)
            logger.info(f"💡    Found Answer: {answer_label}")

            '''
            Search Answer (Traceback options)
            '''
            # Search answer by label while tracing back through scroll.
            answer_matched = False
            while True:
                if answer_label in current_snapshot and self.WebParserUtils.is_unique_xpath(current_snapshot[answer_label]):
                    # Match found
                    answer_matched = True
                    # Set 'newly found XPath' of the answer.
                    answer_xPath = current_snapshot[answer_label]
                    # Input element in XPath signifies end of search.
                    if 'input' in answer_xPath.rsplit('/', 1)[-1] or answer_xPath.startswith('//input'):
                        return self.FormInteractorUtils.click(answer_xPath) # Click Answer & Return
                    # Nest down to reveal options generated by current answer in next iteration.
                    else: 
                        target_xpath = answer_xPath
                        break

                # Target XPath becomes XPath of the first valid element in current_snapshot.
                target_xpath = next((xpath for xpath in current_snapshot.values() if self.WebParserUtils.is_unique_xpath(xpath)), None)
                captured_snapshot: Dict[str, str] = self._get_options(element_metadata, target_action='scroll', target_xpath=target_xpath, filter_if_input=True)
                if (not captured_snapshot) or (captured_snapshot.keys() == current_snapshot.keys()): # Break if new options were not discovered.
                    break   # Returns false outside loop since 'answer_matched' was not marked true.
                current_snapshot = captured_snapshot    # `current_snapshot` preserves valid snapshot of options in frame
            
            if answer_matched: 
                continue    # Nest down next iteration (with updated target_xpath as answer_xPath)
            logger.error("❌    Unable to re-discover option during traceback.")
            self.FormInteractorUtils.click_safe_heading_to_unfocus()
            return False

        '''
        Return
        '''
        logger.error("❌    Reached maximum number of iterations.")
        self.FormInteractorUtils.click_safe_heading_to_unfocus()
        return False

    def handle_checkbox(self, element_metadata: Dict[str, Any]) -> bool:
        """Handle checkbox toggling with state validation"""

        ''' 
        Initialize xPath
        '''
        xPath = self.WebParserUtils.get_validated_xpath(element_metadata)
        if not xPath: # Valid xPath does not exists. Could have shifted in DOM
            return not element_metadata['required']
        if not self.FormInteractorUtils.is_interactable(xPath):
            logger.info("💬  Element not interactable. Skipping.")
            return True

        '''
        Scroll to element
        '''
        self.FormInteractorUtils.scroll_to_element(xPath)

        '''
        Get Options
        '''
        options = element_metadata['options']
        num_of_options = len(options)
        if num_of_options == 0:
            logger.warning('⚠️  0 options for found. Skipping...')
            return False

        '''
        Get Answer(s)
        '''
        answer_xPaths = self._get_multiple_answers_xpaths(element_metadata, options)
        if not answer_xPaths:
            return True # Return true if None is returned

        '''
        Select Option(s) and Return
        '''
        def is_click_required(selection, xpath):
            return (selection and not self.WebParserUtils.get_element(xpath).is_selected()) or (not selection and self.WebParserUtils.get_element(xpath).is_selected())
        selection: bool = True
        for xPath in answer_xPaths:
            if is_click_required(selection, xPath):
                self.FormInteractorUtils.click(xPath)
                if is_click_required(selection, xPath):
                    logger.warning("🟡  Initial attempt failed: Unable to click checkbox. Retrying.")
                    self.FormInteractorUtils.click_js_dispatch_mouse_event(xPath) 
                    if is_click_required(selection, xPath):
                        logger.warning("🟡  Second attempt failed: Unable to click checkbox.")
                        return False
                    else:
                        logger.info("🟢  Checkbox resolved on second attempt.")
        return True

    def handle_dropdown(self, element_metadata: Dict[str, Any]) -> Union[bool, set]:
        """Handle both single and multi-select dropdowns"""

        ''' 
        Initialize Field xPath and Dropdown Selector
        '''
        xPath: str = self.WebParserUtils.get_validated_xpath(element_metadata)
        ''' 
        Initialize xPath
        '''
        xPath = self.WebParserUtils.get_validated_xpath(element_metadata)
        if not xPath: # Valid xPath does not exists. Could have shifted in DOM
            return not element_metadata['required']
        if not self.FormInteractorUtils.is_interactable(xPath):
            logger.info("💬  Element not interactable. Skipping.")
            return True
        select = Select(self.WebParserUtils.get_element(xPath))

        '''
        Scroll to element
        '''
        self.FormInteractorUtils.scroll_to_element(xPath)
        
        '''
        Get Options
        '''
        options_list = [opt.text for opt in select.options] # List of options text
        options = {option: option for option in options_list} # Option's text will itself be treated as xPath since we can directly use the text-value for selection using the `select` selector.
 
        if select.is_multiple:
            '''
            Get Answer(s)
            '''
            # Note: We are treating option's text itself as xPath
            answer_xPaths = self._get_multiple_answers_xpaths(element_metadata, options)
            if not answer_xPaths:
                return True # Return true if None is returned
            
            '''
            Select Option(s) and Return
            '''
            # Note: We are treating option's text itself as xPath
            for xPath in answer_xPaths:
                select.select_by_visible_text(xPath)
            return True # Return success

        else:
            '''
            Get Answer
            '''
            answer_xPath = self._get_answer_xpath(element_metadata, options)
            if not answer_xPath:
                logger.info("Answer not returned. The field could be optional and irrelevant. Skipping...")
                return True

            ''' 
            Select Answer
            '''
            current_element_xPath = self.WebParserUtils.get_validated_xpath(element_metadata)
            new_elements_xPaths = self._click_answer_and_capture_new_fields(answer_xPath, current_element_xPath, selector=select)
            
            ''' 
            Return 
            '''
            if new_elements_xPaths: # New fields were added
                return new_elements_xPaths # Return set of xPaths of those new fields.
            return True # Return success

    def handle_date_field(self, element_metadata: Dict[str, Any]) -> Union[bool, set]:
        """Handle date fields"""
        '''
        Helper Function(s)
        '''
        def reformat_date(date_str: str, output_format: str) -> Optional[str]:
            """
            Converts a date string from 'MM/DD/YYYY' format to a custom format.

            Parameters:
            - date_str (str): Date in 'MM/DD/YYYY' format (e.g. '04/02/2001')
            - output_format (str): Desired output format using combinations like 'DD', 'MM/YYYY', 'DD-MM-YYYY'

            Returns:
            - str: Reformatted date string
            - None: If input format is invalid
            """
            try:
                month, day, year = date_str.split('/')
                format_map = {
                    "MM": month.zfill(2),
                    "DD": day.zfill(2),
                    "YYYY": year
                }

                # Replace each token in the format
                result = output_format
                for key in ["MM", "DD", "YYYY"]:
                    result = result.replace(key, format_map[key])

                return result
            except Exception as e:
                print(f"[!] Error parsing date: {e}")
                return None

        def get_today_date_by_format(output_format: str) -> Optional[str]:
            """
            Returns today's date formatted according to the given output format.

            Supported formats:
                - "MMDDYYYY"
                - "DDMMYYYY"
                - "MMYYYY"
                - "DD"
                - "MM"
                - "YYYY"

            Args:
                output_format (str): The desired output format.

            Returns:
                Optional[str]: The formatted date as a string, or None if format is unsupported.
            """
            today = datetime.now()

            format_mappings = {
                "MMDDYYYY": today.strftime("%m%d%Y"),
                "DDMMYYYY": today.strftime("%d%m%Y"),
                "MMYYYY": today.strftime("%m%Y"),
                "DD": today.strftime("%d"),
                "MM": today.strftime("%m"),
                "YYYY": today.strftime("%Y")
            }

            if output_format in format_mappings:
                return format_mappings.get(output_format)
            return None

        '''
        Initialize XPath
        '''
        xPath: str = self.WebParserUtils.get_validated_xpath(element_metadata)
        if not xPath: # Valid xPath does not exists. Could have shifted in DOM
            return not element_metadata['required']
        if not self.FormInteractorUtils.is_interactable(xPath):
            logger.info("💬  Element not interactable. Skipping.")
            return True
        
        '''
        Scroll to element
        '''
        self.FormInteractorUtils.scroll_to_element(xPath)
        
        '''
        Identify Field Role
        '''
        is_spinbutton = True if self.driver.find_element(By.XPATH, xPath).get_attribute("role") == "spinbutton" else False
        
        '''
        Filter XPath

        The value attributes might update as we type therefore, its recommended to filter out all dynamic attributes from relative XPath.
        Option in current approach: We already capture element first by a simple click. Later just send keystrokes using action chain irrespective of element getting updated.
        '''
        if not self.WebParserUtils.is_absolute_xpath(xPath):    # Check for relative XPath
            filtered_xPath = self.ParsedDataUtils.clean_dynamic_attributes(xPath, aggressive=True)
            if self.WebParserUtils.is_unique_xpath(filtered_xPath):
                xPath = filtered_xPath
            else:
                filtered_xPath = self.ParsedDataUtils.clean_dynamic_attributes(xPath, aggressive=False)
                if self.WebParserUtils.is_unique_xpath(filtered_xPath):
                    xPath = filtered_xPath
 
        '''
        Initialize Search Parameters
        '''
        # Handle date input based on metadata category (e.g., work experience, education, other)
        options: dict = element_metadata.get('options', {})
        field_category: str = options.get('category')   # Examples: 'Work Experience', 'Education', 'other'
        field_id: int = options.get('id')    # Index of category (Example: 3 -> 3rd work-exp)
        field_type: str = options.get('type') # Examples: 'From Start Date', 'To End Date', 'To End Date (Actual or Expected)'
        base_format: str = options.get('format') # Base Formats: ['MMDDYYYY', 'MMYYYY', 'DD', 'MM', 'YYYY']

        '''
        Handle Unknown Date Format 
        '''
        if not base_format:
            if not element_metadata['required']:
                logger.warning('⚠️  Base format not found for date input. Skipping...')
                return True
            logger.warning('⚠️  Base format not found for date input. Setting to default MMDDYYYY')
            base_format = "MMDDYYYY" # Try with default format

        '''
        Send Keys
        '''
        try:
            if field_category in {'Work Experience', 'Education'}:
                # Check if the requested work experience ID exists in the user data
                category_list = self.UserData.data.get(field_category, [])
                if category_list and (field_id <= len(category_list)):
                    full_date = category_list[field_id - 1].get(field_type)
                    formatted_date = reformat_date(full_date, base_format)
                    if formatted_date:
                        if element_metadata['type'] == 'date':

                            if formatted_date == element_metadata['value']:
                                logger.info("✔️  Field already contains the correct predefined answer; skipping input.")
                                return True

                            if is_spinbutton:
                                return self.FormInteractorUtils.type_with_action_chains(formatted_date, click_before_xpath=xPath)
                            else:
                                return self.FormInteractorUtils.safe_send_keys(xPath, formatted_date, clear_before=True)
                       
                        elif element_metadata['type'] == 'datelist':

                            if formatted_date == element_metadata['placeholder']:
                                logger.info("✔️  Field already contains the correct predefined answer; skipping input.")
                                return True

                            return self.handle_dynamic_list(element_metadata, answer=formatted_date)
                    else:
                        logger.error(f"❓  Invalid date format ({full_date}) in user data at Category: {field_category} -> ID: {field_id} -> Type: {field_type}")
                else:
                    raise IndexError
            elif field_category in {'other', '', None}:
                # Enter Today's Date is type not defined (neither start/end type)
                if not field_type:
                    formatted_date = get_today_date_by_format(base_format) # Get today’s date in desired format
                    if is_spinbutton:
                        return self.FormInteractorUtils.type_with_action_chains(formatted_date, click_before_xpath=xPath)
                    else:
                        return self.FormInteractorUtils.safe_send_keys(xPath, formatted_date, clear_before=True)
                else:
                    if not element_metadata['required']:
                        return True # Skip if the field is not required
                    else:
                        logger.error(f'❓  Unknown date field. Category: {field_category}, ID: {field_id}, Type: {field_type}, Base Format: {base_format}')
            else: # Catch-all: Unrecognized case
                logger.error(f'❓  Unable to identify date context. Category: {field_category}, ID: {field_id}, Type: {field_type}, Base Format: {base_format}')
                if not element_metadata['required']:
                    return True # Skip if the field is not required

        except IndexError:
            logger.error(f"⛔  {field_category} {field_id} does not exist in user data.")

        except Exception as e:
            logger.error(f"❌  Failed to input date: {e}")

        '''
        Return
        '''
        return False # Fallback returning 'False' if unable to resolve until this point.
    
    def handle_file_upload(self, element_metadata: Dict[str, Any]):

        ''' 
        Initialize xPath
        '''
        xPath = self.WebParserUtils.get_validated_xpath(element_metadata)
        if not xPath: # Valid xPath does not exists. Could have shifted in DOM
            return not element_metadata['required']
        if not self.FormInteractorUtils.is_interactable(xPath):
            logger.info("💬  Element not interactable. Skipping.")
            return True

        '''
        Scroll to element
        '''
        self.FormInteractorUtils.scroll_to_element(xPath)

        '''
        Initialize File Path
        '''
        file_path = os.path.normpath(self.UserData.data['Resume']) # Default resume file path
        file_name = file_path.split('\\')[-1] # File name

        def set_file_name_and_path(path: str) -> None:
            nonlocal file_path, file_name
            file_path = os.path.normpath(path) # Set file path
            file_name = file_path.split('\\')[-1] # Set file name

        html_diff_dom = '' # Initialize `send_keys()` success identifier
        tag_name = self.WebParserUtils.get_tag_name(self.WebParserUtils.get_element(xPath))

        def get_nested_value(key_path: str):
            return self.ParsedDataUtils.get_nested_value(element_metadata, key_path)

        ### Upload request coming from <input> field
        if tag_name == 'input':
            
            ## Initialize relevant file path
            if get_nested_value('options.type') == 'resume': # Upload request for resume
                set_file_name_and_path(self.UserData.data['Resume'])
            else: # Input field not asking for resume
                if element_metadata['required'] is True: # Upload only if it's required
                    # Unknown file type: Uploading resume to avoid crash
                    set_file_name_and_path(self.UserData.data['Resume'])
                else: # Element is not resume type, and optional.
                    return True # Return success (without uploading)
                
            # Scroll to element
            self.FormInteractorUtils.scroll_to_element(xPath)
            
            ### Ensure the file is not already uploaded by checking if the file name is present in the page source
            if (file_name not in self.driver.page_source):
                self.FormInteractorUtils.safe_send_keys(xPath, file_path, allow_click=False)  # Use send_keys to upload the file
                time.sleep(3) # Wait briefly for the file to upload
                # Verify if the file has been uploaded successfully by checking the page source
                if file_name in self.driver.page_source: # File is uploaded
                    return True # Return success
                # If not uploaded, attempt to trigger the file dialog again on this new element and upload through the dialog
                else:
                    '''
                    Check if input is dynamic:
                    > True: Handle dynamic upload (likely not dynamic field)
                    > False: Attempt upload through dialog window. (highly possible)
                    '''
                    pass # Handled when turn comes in queue
            ### File was previously uploaded on portal.
            else:
                # Attempt file upload while fetching 'html_diff_dom' to verify if existing file was replaced.
                html_diff_dom = self.FormInteractorUtils.get_updated_dom_after_send_keys(self.WebParserUtils.get_element(xPath), file_path, allow_click=False)[0]
                # Verify if the file has been uploaded successfully by checking the updated block of html dom 
                if ((html_diff_dom != '') and (file_name in html_diff_dom)): # Uploaded successfully using `send_keys`.
                    return True
                else: # File was not uploaded
                    '''
                    Check if input is dynamic:
                    > True: Handle dynamic upload (likely not dynamic field)
                    > False: Attempt upload through dialog window. (highly possible)
                    '''
                    pass # Handled when turn comes in queue
        ### Upload request coming from button (<button> or role="button").
        else:
            ## Upload request for resume
            if self.ParsedDataUtils.is_substrings_in_item(element_metadata, keys=["label-srcTag", "label-srcText", "label-srcAttribute", "label-custom", "name", "text", "id", "id-custom"], substrings=['resume'], exact_match=False):
                set_file_name_and_path(self.UserData.data['Resume'])
                '''
                Handle file-upload button irrespective of file is already uploaded or not.

                Possibilities:
                > Button programatically triggers hidden input file upload element. (equally possible)
                    > Handle using file upload dialog
                > Button dynamically reveals input upload element. (equally possible)
                    > Handle using dynamic algorithm, fetch input element
                        > Attempt send_keys
                            > If failed, handle using file upload dialog
                '''
                pass # Handled when turn comes in queue
            ## Upload requested for other document
            else:
                if not element_metadata['required']:
                    return True # Return success (without uploading)
        queue_file_upload(self, xPath, file_path)
        return True

    def handle_button(self, element_metadata: Dict[str, Any], delta_thresh: float = 0.6) -> Union[bool, set]:

        ''' 
        Initialize xPath
        '''
        xPath = self.WebParserUtils.get_validated_xpath(element_metadata)
        if not self.FormInteractorUtils.is_interactable(xPath):
            logger.info("💬  Element not interactable. Skipping.")
            return True

        '''
        Scroll to element
        '''
        self.FormInteractorUtils.scroll_to_element(xPath)

        '''
        Click
        '''
        # Get the DOM before clicking
        dom_before = self.driver.execute_script("return document.body.innerHTML")
        # Click the element
        self.FormInteractorUtils.click(xPath)
        logger.info(f"🖱️  Clicked Button: {element_metadata.get('text', None)}")
        # Wait for DOM to stabilize
        self.WebParserUtils.wait_for_stable_dom(padding=2)
        # Get the DOM after clicking
        dom_after = self.driver.execute_script("return document.body.innerHTML")

        '''
        Check Progress
        '''
        scroll_position = self.driver.execute_script("""
            return {
                top: window.pageYOffset || document.documentElement.scrollTop,
                left: window.pageXOffset || document.documentElement.scrollLeft
            };
        """)
        if self.WebParserUtils.has_dom_significantly_changed_lxml(dom_before, dom_after, threshold=delta_thresh):
            return True
        
        '''
        Record new elements (If not progressed)
        '''
        search_queries = [
            "input",
            "//textarea",
            "//select",
            ".//button",
            ".//input[@type='submit']",
            ".//input[@type='button']",
            ".//*[@role='button']"
        ]
        new_elements: List[str] = self.WebParserUtils.get_new_elements(dom_before, dom_after, search_queries, return_html=True)
        new_elements_xPaths = self.WebParserUtils.compute_relative_xpath_str(new_elements, verify_xpath=True) # Extract relative xPath of newly identified elements.

        '''
        Filter New Elements
        '''
        filtered_new_elements_xPaths: set[str] = set()
        for new_element_xPath in new_elements_xPaths:
            if self.WebParserUtils.is_xpath_visible(new_element_xPath):
                tag_name = self.WebParserUtils.get_tag_name(new_element_xPath)
                element = self.WebParserUtils.get_element(new_element_xPath)
                if tag_name == 'button':
                    button_text = button_text if (button_text := self.ParsedDataUtils.clean_text(element.text.strip().lower())) != '' else None
                    if not button_text:
                        button_text = val if (val := element.get_attribute("title")) not in [""] else None
                    button_id = val if (val := element.get_attribute("id")) not in [""] else None
                    button_id_attributes = self.WebParserUtils.search_attribute(["id"], element)
                    button_customId = (diff_set := set((button_id_attributes or {}).values()).difference({element.get_attribute("id")})) and diff_set.pop() or None
                    ''' Exclude BLACKLISTED buttons text '''
                    # Exclude button that match the full blacklist
                    if self.ParsedDataUtils.match_full_blacklist(config.blacklist.new_button_blacklist_text_full, (button_text,)):
                        # If button_text is empty and 'onclick' attribute is not None, skip continue
                        if button_text == '' and element.get_attribute('onclick') is not None:
                            pass  # Do not continue, allow processing of this button
                        else:
                            continue  # Continue to the next button otherwise
                    # Exclude button that partially match any keyword in the partial blacklist
                    if self.ParsedDataUtils.match_partial_blacklist(config.blacklist.new_button_blacklist_text_partial, (button_text,)):
                        continue
                    ''' Exclude BLACKLISTED buttons id '''
                    # Exclude button that match the full blacklist
                    if self.ParsedDataUtils.match_full_blacklist(config.blacklist.new_button_blacklist_id_full, (button_id, button_customId)):
                        continue
                    # Exclude button that partially matchs any keyword in the partial blacklist
                    if self.ParsedDataUtils.match_partial_blacklist(config.blacklist.new_button_blacklist_id_partial, (button_id, button_customId)):
                        continue
                elif tag_name in {'input', 'textarea', 'select'}:
                    field_id = val if (val := element.get_attribute("id")) not in [""] else None
                    field_customId = (diff_set := set((self.WebParserUtils.search_attribute(["id"], element) or {}).values()).difference({element.get_attribute("id")})) and diff_set.pop() or None
                    # Exclude field that fully/partially matchs the respective blacklist
                    if (
                        self.ParsedDataUtils.match_full_blacklist(config.blacklist.new_field_blacklist_id_full, (field_id, field_customId))
                        or self.ParsedDataUtils.match_partial_blacklist(config.blacklist.new_field_blacklist_id_partial, (field_id, field_customId)) 
                    ):
                        continue
                filtered_new_elements_xPaths.add(new_element_xPath)
   

        return filtered_new_elements_xPaths if filtered_new_elements_xPaths else False







