# modules/web_interactor.py
from selenium.webdriver.common.by import By # type: ignore
from selenium.webdriver.support.ui import WebDriverWait # type: ignore
from selenium.webdriver.support import expected_conditions as EC # type: ignore
from selenium.common.exceptions import NoSuchElementException, TimeoutException, ElementNotInteractableException, StaleElementReferenceException, InvalidElementStateException, InvalidArgumentException, ElementClickInterceptedException # type: ignore
from selenium.webdriver.remote.webelement import WebElement # type: ignore
from selenium.webdriver.common.alert import Alert # type: ignore
# from selenium.webdriver.remote.webdriver import WebDriver # type: ignore
from selenium.webdriver.support.select import Select # type: ignore
from typing import Dict, List, Any, Union, Optional, Literal, Iterable, Tuple
import json
import time
from pathlib import Path
from enum import IntEnum, Enum
import itertools
# Modules Import
from modules.core.web_parser import WebPageParser, WebParserUtils, ParsedDataUtils
from modules.core.web_parser import field_identifiers, stardard_field_search_keys, stardard_button_search_keys, standard_label_keys
from config.system_config import *
from modules.core.form_filler import FormInteractor, FormInteractorUtils, UserData
from modules.utils.logger_config import setup_logger
import config.env_config as env_config

logger = setup_logger(__name__, level=env_config.LOG_LEVEL, log_to_file=False)

class FormState(IntEnum):
    DESCRIPTION_PAGE = 1
    AUTH_PAGE = 2
    LOGGED_IN = 3
    FORM_SUBMITTED = 4

class AuthType(Enum):
    SIGN_UP = "SignUp"
    SIGN_IN = "SignIn"
    VERIFY = "Verify"



class WebPageInteractor:

    def __init__(self, driver, browser):
        self.driver = driver
        self.WebPageParser = WebPageParser(driver)
        self.ParsedDataUtils = ParsedDataUtils()
        self.WebParserUtils = WebParserUtils(driver)
        self.FormInteractorUtils = FormInteractorUtils(driver)
        self.FormInteractor = FormInteractor(driver)
        self.FormInteractor.refresh_answer = False
        self.UserData = UserData(env_config.USER_JSON_FILE)
        self.Browser = browser # Browser instance
        self.form_state = FormState.DESCRIPTION_PAGE # base state
    
    def parse_page(self):
        self.ParsedDataUtils.parsed_data = self.WebPageParser.parse_page()

    def save_parsed_data(self, file_num, data=None): # Temporary function for development

        def save_json_to_file(data, file_path):
            """
            Save a variable holding JSON data to a file in pretty-printed format.
            If the data contains WebElement objects (as values), they will be replaced with a string.

            Args:
                data (dict or list): The JSON-serializable data to save.
                file_path (str): The path of the file where the data will be saved.

            Returns:
                None
            """
            
            def sanitize(obj):
                if isinstance(obj, WebElement):
                    return "Web Element"
                elif isinstance(obj, dict):
                    return {k: sanitize(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [sanitize(i) for i in obj]
                else:
                    return obj

            try:
                cleaned_data = sanitize(data)
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(cleaned_data, f, indent=4, ensure_ascii=False)
                print(f"✅ JSON data successfully saved to {file_path}")
            except Exception as e:
                print(f"❌ Error while saving JSON data: {e}")
        if not data:
            data = self.ParsedDataUtils.parsed_data
        save_json_to_file(data, Path(__file__).resolve().parents[2] / 'tests' / f'web_preview_{file_num}.json')

    def _is_form_submitted(self) -> bool:

        ack_button = self.ParsedDataUtils.search_items(sections=["buttons"], keys=['text'], substrings=ack_btn_identifiers, return_first_only=True)
        progress_button = self.ParsedDataUtils.search_items(sections=["buttons"], keys=['text'], substrings=progress_btn_identifiers, return_first_only=True)
        auth_btn_identifiers = signup_auth_btn_identifiers | signin_auth_btn_identifiers | verify_auth_btn_identifiers | other_auth_btn_identifiers
        auth_button = self.ParsedDataUtils.search_items(sections=["buttons"], keys=['text'], substrings=auth_btn_identifiers, return_first_only=True)
        apply_button_or_link = self.ParsedDataUtils.search_items(sections=['buttons','links'], keys=["text"], substrings=start_apply_btn_identifiers, return_first_only=True)
        email_field = self.ParsedDataUtils.search_items(sections=['fields'], filter_dict={'type': 'email'}) or self.ParsedDataUtils.search_items(sections=['fields'], keys=stardard_field_search_keys, substrings=['Email'], filter_dict={'type':'text'}, return_first_only=True)
        password_field = self.ParsedDataUtils.search_items(sections=['fields'], filter_dict={"type": "password"}, return_first_only=True)
        fields_cap = len(self.ParsedDataUtils.get_fields()) < 4 # Limit 3 visible fields for submitted page.

        if (
            self.WebParserUtils.is_text_present_on_webpage(application_submitted_page_text_identifiers) and not auth_button and not email_field and not password_field and not ack_button 
            or self.WebParserUtils.is_text_present_on_webpage(already_submitted_page_text_identifiers)
            or (self.form_state == FormState.LOGGED_IN and fields_cap and not progress_button and not ack_button)
            or (self.form_state == FormState.AUTH_PAGE and fields_cap and not email_field and not password_field and not auth_button and not ack_button and not apply_button_or_link)
        ):
            return True
        # Fallback
        return False

    def _is_logged_in_state(self) -> bool:

        first_name_field = self.ParsedDataUtils.search_items(sections=['fields'], keys=stardard_field_search_keys, substrings=['first name'], filter_dict={"type": "text"}, return_first_only=True)
        auth_btn_or_link_identifiers = signup_auth_btn_identifiers | signin_auth_btn_identifiers
        auth_button_or_link = self.ParsedDataUtils.search_items(sections=["buttons", "links"], keys=['text'], substrings=auth_btn_or_link_identifiers, return_first_only=True)
        verify_button = self.ParsedDataUtils.search_items(sections=["buttons"], keys=['text'], substrings=verify_auth_btn_identifiers, return_first_only=True)
        # actual_field_items = len(self.ParsedDataUtils.get_fields()) - len(self.ParsedDataUtils.search_items(sections=['fields'], filter_dict={"type": "button"}))
        # apply_button_or_link = self.ParsedDataUtils.search_items(sections=['buttons','links'], keys=["text"], substrings=start_apply_btn_identifiers, return_first_only=True)
        expand_all_button = self.ParsedDataUtils.search_items(sections=['buttons'], keys=['text'], substrings=['expand all'], return_first_only=True)
        progress_button = self.ParsedDataUtils.search_items(sections=["buttons"], keys=['text'], substrings=progress_btn_identifiers, return_first_only=True)

        if (
            (
                first_name_field 
                and not auth_button_or_link
                and not verify_button
            )
            or (
                expand_all_button 
                and progress_button
                and not auth_button_or_link 
                and not verify_button 
            )
        ):
            return True
        # Fallback
        return False

    def _is_auth_page(self) -> bool:
        password_field = self.ParsedDataUtils.search_items(sections=['fields'], filter_dict={"type": "password"}, return_first_only=True)
        auth_btn_or_link_identifiers = signup_auth_btn_identifiers | signin_auth_btn_identifiers
        auth_button_or_link = self.ParsedDataUtils.search_items(sections=["buttons", "links"], keys=['text'], substrings=auth_btn_or_link_identifiers, return_first_only=True)
        email_field = self.ParsedDataUtils.search_items(sections=['fields'], filter_dict={'type': 'email'}) or self.ParsedDataUtils.search_items(sections=['fields'], keys=stardard_field_search_keys, substrings=['Email'], filter_dict={'type':'text'}, return_first_only=True)
        apply_button_or_link = self.ParsedDataUtils.search_items(sections=['buttons','links'], keys=["text"], substrings=start_apply_btn_identifiers, return_first_only=True)
        fields_cap = len(self.ParsedDataUtils.get_fields()) < 7 # Limit 6 visible fields for auth page.

        if (
            password_field
            or auth_button_or_link
            or (email_field and fields_cap and not apply_button_or_link)
        ):
            return True
        # Fallback
        return False

    def _is_description_page(self) -> bool:
        
        apply_button_or_link = self.ParsedDataUtils.search_items(sections=['buttons','links'], keys=["text"], substrings=start_apply_btn_identifiers, return_first_only=True)
        fields_cap = len(self.ParsedDataUtils.get_fields()) < 5 # Limit 4 visible fields for description page.

        if apply_button_or_link and fields_cap:
            return True
        # Fallback
        return False

    def set_state(self):

        current_state = self.form_state

        if self._is_form_submitted() and FormState.FORM_SUBMITTED > current_state:
            self.form_state = FormState.FORM_SUBMITTED

        elif self._is_logged_in_state() and FormState.LOGGED_IN > current_state:
            self.form_state = FormState.LOGGED_IN

        elif self._is_auth_page() and FormState.AUTH_PAGE > current_state:
            self.form_state = FormState.AUTH_PAGE

        elif self._is_description_page() and FormState.DESCRIPTION_PAGE > current_state:
            self.form_state = FormState.DESCRIPTION_PAGE

        # Optional: fallback state
        else:
            pass  # remain in current state

        logger.info(f"📌  Form State: {self.form_state.name}")

    def _perform_section_expand(self) -> bool:
        '''
        Expand sections to fit the data provided in user_data.json.
        This function will check the number of sections in the parsed data and compare it with the number of entries in user_data.json.
        It will expand or collapse sections as needed.

        `expand_section_progress` is used to track the progress of the expansion process.
          
        Return 'True' if any sections were expanded. Return 'False' to conclude the loop.
        This function will be called in a loop until all sections are expanded or collapsed to fit the data.
        '''

        ''' Section 1: Handle Expand All Button '''
        if self.expand_section_progress == 1:
            # Check if the button is present in the parsed data
            expand_all_button = self.ParsedDataUtils.search_items(sections=['buttons'], keys=['text'], substrings=['expand all'], return_first_only=True)
            if expand_all_button:
                expand_all_button_xpath = expand_all_button[0].get('xPath')
                if expand_all_button_xpath:
                    self.FormInteractorUtils.click(expand_all_button_xpath, scroll=True)
                    time.sleep(1)
                    self.expand_section_progress = 2 # Section 1 completed, move to next section
                    return True
            self.expand_section_progress = 2 # Section 1 completed, move to next section
            
        ''' Section 2: Handle Work Experience Section '''
        has_work_experience_section = (
            self.WebPageParser.work_experience_sectionID_primary > 0
            or self.WebParserUtils.contains_substring_in_tags(["Experience", "EXPERIENCE"], ['label', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'], case_sensitive=True)
        )
        if self.expand_section_progress == 2:
            # Check if Work Experience section is present in the parsed data
            if has_work_experience_section:
                total_companies_worked = len(self.UserData.data["Work Experience"])
                job_title_fields = self.ParsedDataUtils.filter_metadata(section_key="fields", query={"options.category": "Work Experience", "options.type": "Job Title"})
                work_section_count = len(job_title_fields) if job_title_fields else 0
                if work_section_count < total_companies_worked:

                    get_first_add_button_only = False # If work sections were added, we get all 'Add' buttons
                    if work_section_count == 0:
                        get_first_add_button_only = True # If no work sections were added, we only get the first 'Add' button

                    # Get 'Add' button(s)
                    add_buttons = self.ParsedDataUtils.search_items(sections=['buttons'], keys=["text"], substrings=['add'], return_first_only=get_first_add_button_only)
                    if add_buttons:

                        click_xPath = None

                        # If no work sections were added, we need to click the first 'Add' button
                        if work_section_count == 0:
                            click_xPath = add_buttons[0].get('xPath') # xPath of Work Experience 'Add' button

                        # If work sections were added, we need to find the last job title field and click the next 'Add' button
                        else:
                            # Find the last job title field and set click_xPath to the next (associated) 'Add' button
                            for i in range(len(add_buttons)):
                                last_job_title = job_title_fields[-1].get('xPath')
                                current_add_button = add_buttons[i].get('xPath')
                                if last_job_title and current_add_button and self.WebParserUtils.is_element_after(current_add_button, last_job_title):
                                    click_xPath = current_add_button
                                    break
                        
                        if click_xPath:
                            self.FormInteractorUtils.click(click_xPath, scroll=True)
                            print('Found Work-Exp Add button, click & return True')
                            return True
                        else:
                            print("[!] No 'Add' button found to add more Work Experience sections.")
                            # We could have returned `False` here, since it represents no changes made to the webpage.
                            # But we want to keep the loop going to check for other sections (Education section handling). 
                            # Otherwise, it will anyway return `False` at the end of the function thus exit the loop.          
                elif work_section_count > total_companies_worked:
                    # Remove extra work sections
                    remove_buttons: List[Dict[str, Any]] = self.ParsedDataUtils.search_items(sections=['buttons'], keys=["text"], substrings=['delete', 'remove'], return_first_only=False)
                    if remove_buttons:
                        num_of_buttons_to_remove = work_section_count - total_companies_worked
                        # Check if we have enough buttons to remove
                        if num_of_buttons_to_remove <= len(remove_buttons):
                            for i in reversed(range(work_section_count)): # Removing in reversed order helps keeping the posistion of button intact - keep xPath relevant
                                if num_of_buttons_to_remove > 0:
                                    # Click the 'Remove' button
                                    self.FormInteractorUtils.click(remove_buttons[i].get('xPath'), scroll=True)
                                    num_of_buttons_to_remove -= 1
                                    time.sleep(0.5)
                                else:
                                    break
                            return True
                        else:
                            print(f"[!] Not enough 'Remove' buttons to remove {num_of_buttons_to_remove} work sections.")
                            # Remove all
                            for i in reversed(range(len(remove_buttons))):
                                self.FormInteractorUtils.click(remove_buttons[i].get('xPath'), scroll=True)
                                time.sleep(0.5)
                            print(f"[!] Removed all sections. Total removed: {len(remove_buttons)}")
                            return True
                    else:
                        print("[!] No 'Remove' buttons found to remove extra work sections.")
                        # Unknown state identifier. Break the loop
                        return False # Stops the expand section process and try to submit form with existing state
                else:
                    # No action needed, the number of work sections is already correct
                    pass
            self.expand_section_progress = 3 # Section 2 completed, move to next section

        ''' Section 3: Handle Education Section '''
        if self.expand_section_progress == 3:
            if (
                self.WebPageParser.education_sectionID_primary > 0
                or self.WebParserUtils.contains_substring_in_tags(["Education", "EDUCATION"], ['label', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'], case_sensitive=True)
            ):
                total_universities_attended = len(self.UserData.data["Education"])
                university_title_fields = self.ParsedDataUtils.filter_metadata(section_key="fields", query={"options.category": "Education", "options.type": "School or University"})
                education_section_count = len(university_title_fields) if university_title_fields else 0
                if education_section_count < total_universities_attended:

                    # Get 'Add' button(s)
                    add_buttons = self.ParsedDataUtils.search_items(sections=['buttons'], keys=["text"], substrings=['add'], return_first_only=False)
                    if add_buttons:

                        click_xPath = None

                        # If no education sections were added, we need to click the first 'Add' button
                        first_education_add_button_idx = 0
                        if has_work_experience_section:
                            first_education_add_button_idx += 1 # Skip the first 'Add' button if Work Experience section is present
                        if education_section_count == 0:
                            if first_education_add_button_idx < len(add_buttons): # Check if the index is valid
                                click_xPath = add_buttons[first_education_add_button_idx].get('xPath') # xPath of education 'Add' button

                        # If education sections were added, we need to find the last education section field and click the next 'Add' button following it.
                        else:
                            # Find the last education title field and set click_xPath to the next (associated) 'Add' button
                            for i in range(len(add_buttons)):
                                last_university_title = university_title_fields[-1].get('xPath')
                                current_add_button = add_buttons[i].get('xPath')
                                if last_university_title and current_add_button and self.WebParserUtils.is_element_after(current_add_button, last_university_title):
                                    click_xPath = current_add_button
                                    break
                        
                        if click_xPath:
                            self.FormInteractorUtils.click(click_xPath, scroll=True)
                            print('Found Education Add button, click & return True')
                            return True 
                        else:
                            print("[!] No 'Add' button found to add more education sections.")
                            # We could have returned `False` here, since it represents no changes made to the webpage.
                            # But we want to keep the loop going to check for other sections. 
                            # Otherwise, it will anyway return `False` at the end of the function thus exit the loop.           
                elif education_section_count > total_universities_attended:
                    # Remove extra education sections
                    work_exp_padding = 0
                    if self.WebParserUtils.is_text_present_on_webpage("Work Experience"):
                        work_exp_padding = len(self.ParsedDataUtils.filter_metadata(section_key="fields", query={"options.category": "Work Experience", "options.type": "Job Title"}) or [])
                    remove_buttons = self.ParsedDataUtils.search_items(sections=['buttons'], keys=["text"], substrings=['delete', 'remove'], return_first_only=False)
                    if remove_buttons:
                        num_of_buttons_to_remove = education_section_count - total_universities_attended
                        # Check if we have enough buttons to remove
                        if num_of_buttons_to_remove <= len(remove_buttons):
                            for i in reversed(range(work_exp_padding + education_section_count)): # Removing in reversed order helps keeping the posistion of button intact - keep xPath relevant
                                if num_of_buttons_to_remove > 0:
                                    # Click the 'Remove' button
                                    self.FormInteractorUtils.click(remove_buttons[i].get('xPath'), scroll=True)
                                    num_of_buttons_to_remove -= 1
                                    time.sleep(0.5)
                                else:
                                    break
                            return True
                        else:
                            print(f"[!] Not enough 'Remove' buttons to remove {num_of_buttons_to_remove} education sections.")
                            # Remove all
                            for i in reversed(range(len(remove_buttons))):
                                self.FormInteractorUtils.click(remove_buttons[i].get('xPath'), scroll=True)
                                time.sleep(0.5)
                            print(f"[!] Removed all sections. Total removed: {len(remove_buttons)}")
                            return True
                    else:
                        print("[!] No 'Remove' buttons found to remove extra education sections.")
                        # Unknown state identifier. Break the loop
                        return False # Stops the expand section process and try to submit form with existing state
                else:
                    # No action needed, the number of work sections is already correct
                    pass
            self.expand_section_progress = 4 # Section 3 completed, move to next section
        
        ''' Section 4: Handle Delete Uploaded Files '''
        if self.expand_section_progress == 4:
            # Check if the delete file option is present in the parsed data
            file_btn_items = self.ParsedDataUtils.search_items(sections=['buttons'], keys=["label-srcText", "label-srcAttribute", "label-custom", "name", "text", "id", "id-custom"], substrings=['resume','file'])
            is_dom_changed: bool = False
            for btn_item in reversed(file_btn_items): # Removing in reversed order helps keeping the posistion of button intact - keep xPath relevant
                if self.ParsedDataUtils.is_substrings_in_item(btn_item, keys=["label-srcTag", "label-srcText", "label-srcAttribute", "label-custom", "name", "text", "id", "id-custom"], substrings=['delete','remove','clear'], exact_match=False):
                    try:
                        self.FormInteractorUtils.click(btn_item['xPath'], raise_on_fail=True)
                        is_dom_changed = True
                        time.sleep(0.5)
                        continue
                    except (NoSuchElementException, InvalidArgumentException):
                        # Element position was shifted
                        return True # Parse the web-page again (new expand sections iteration)
                    except (ElementClickInterceptedException, ElementNotInteractableException, InvalidElementStateException):
                        continue
                    except:
                        continue
            self.expand_section_progress = 5 # Section 4 completed, move to next section
            if is_dom_changed: return True # Updates page state

        return False # All sections successfully fixed, return False to exit the loop.
    
    def expand_sections(self):
        ''' 
        Expand form sections: Ensure all necessary sections are visible.
        '''
        self.expand_section_progress = 1
        total_expand_section_progress = 4
        iteration = 1
        while self._perform_section_expand():
            progress_percent = (100/total_expand_section_progress)*(self.expand_section_progress-1)
            # if iteration==1 and progress_percent==100:  # Avoid parsing data if no changes were made.
            #     break
            logger.debug(f"🔄   Expanding sections {progress_percent}%... This could take several iterations, current iteration {iteration}.")
            self.parse_page()
            iteration += 1
            if iteration > (5 + len(self.UserData.data["Work Experience"]) + len(self.UserData.data["Education"])):
                logger.debug("[⚠️] Max iterations reached. Exiting the loop.")
                break
        logger.debug('✅    All sections expanded.')

    def _resolve_description_page(self) -> bool:
        # Get the 1st apply now button/link if it exists in the parsed data.
        apply_now_element: List[Dict[str, Any]] = self.ParsedDataUtils.search_items(sections=['buttons','links'], keys=["text"], substrings=start_apply_btn_identifiers, order_search_by_substring=True, return_first_only=True)
        if apply_now_element:
            link: str = apply_now_element[0].get('href')
            if link:
                self.FormInteractorUtils.open_link(link)
            else:
                self.FormInteractorUtils.click(apply_now_element[0].get('xPath')) # Click 'Apply Now' button or link
            return True
        else:
            # Check if form contained in iFrame
            iframe_elements: list = self.WebParserUtils.get_visible_iframes()
            if iframe_elements:
                for iframe_element in iframe_elements:
                    iframe_blacklist = ['recaptcha', 'googleapis']
                    src = iframe_element.get_attribute('src')
                    # Check if none of the blacklist items are in the src string
                    if all(item not in src for item in iframe_blacklist):
                        self.Browser.open_page(src)
                        return True 
        # Fallback
        logger.critical("⚠️  Failed to resolve DESCRIPTION_PAGE")
        return False # Indicating failure to resolve

    def _get_auth_type_and_action_item(self) -> bool | Tuple[AuthType, Dict[str, Any], Dict[AuthType, List[Dict[str, Any]]]]:
        """
        Resolves authentication pages by handling sign-in, create account, or verification steps.
        Returns True on successful form progression, False otherwise.

        auth_btn and auth_type are always initialized together. If auth_btn exists without auth_type, click the button and return True, otherwise return False if seems not resolvable.
        """
        logger.info("🔐  Analyzing authentication page type and action element...")

        # ---------------------------------------------
        # Step 1: Collect Relevant Fields for Inference
        # ---------------------------------------------
        # Try to get 'email' fields by type, or fallback using known key identifiers
        email_fields = self.ParsedDataUtils.search_items(sections=['fields'], filter_dict={'type': 'email'}) or self.ParsedDataUtils.search_items(sections=['fields'], keys=stardard_field_search_keys, substrings=['Email'], filter_dict={'type':'text'})
        # Try to get 'password' fields
        password_fields = self.ParsedDataUtils.search_items(sections=['fields'], filter_dict={'type': 'password'})

        # ---------------------------------------------
        # Step 2: Identify Available Action Buttons
        # ---------------------------------------------
        signup_btn, signin_btn, verify_btn, other_progress_btn = {}, {}, {}, {}

        # Helper function: prioritize 'submit' buttons over non-submit
        def is_submit_preferred(existing, candidate):
                return (not existing) or (candidate.get('type') == 'submit' and existing.get('type') != 'submit')
        
        # Reverse search order: prioritize visually last buttons (e.g., bottom of form)
        for btn in reversed(self.ParsedDataUtils.get_buttons()):    
            if self.ParsedDataUtils.is_substrings_in_item(btn, ['text'], signup_auth_btn_identifiers) and is_submit_preferred(signup_btn, btn):
                signup_btn = btn
            elif self.ParsedDataUtils.is_substrings_in_item(btn, ['text'], signin_auth_btn_identifiers) and is_submit_preferred(signin_btn, btn):
                signin_btn = btn
            elif self.ParsedDataUtils.is_substrings_in_item(btn, ['text'], verify_auth_btn_identifiers) and is_submit_preferred(verify_btn, btn):
                verify_btn = btn
            elif self.ParsedDataUtils.is_substrings_in_item(btn, ['text'], other_auth_btn_identifiers) and is_submit_preferred(other_progress_btn, btn):
                other_progress_btn = btn

        # ---------------------------------------------
        # Step 3: Infer Auth Type from Field Structure
        # ---------------------------------------------
        def infer_auth_type_from_fields():
            email_count = len(email_fields)
            password_count = len(password_fields)

            if password_count == 0:
                if email_count == 1:
                    return AuthType.SIGN_IN
                elif self.ParsedDataUtils.filter_metadata(section_key="fields", query={"options.category": "verification"}):
                    return AuthType.VERIFY
            elif password_count == 1:
                return AuthType.SIGN_IN
            elif password_count == 2:
                return AuthType.SIGN_UP
            return None

        # ---------------------------------------------
        # Step 4: Resolve Auth Button and Type
        # ---------------------------------------------
        auth_btn = auth_type = None
        
        # List of known buttons mapped to their auth types
        btn_type_map = [
            (signup_btn, AuthType.SIGN_UP),
            (signin_btn, AuthType.SIGN_IN),
            (verify_btn, AuthType.VERIFY),
        ]

        # Try to get first valid "submit" button with known type
        auth_btn, auth_type = next(
            ((btn, atype) for btn, atype in btn_type_map if btn and btn.get('type') == 'submit'),
            (None, None)
        )
        if auth_btn: # Apply correction using fields information.
            if auth_btn == signup_btn:
                btn = None
                if len(password_fields) == 1:
                    if signin_btn and signin_btn.get('type') == 'submit':
                        btn = signin_btn
                    elif other_auth_btn_identifiers and other_auth_btn_identifiers.get('type') == 'submit':
                        btn = other_auth_btn_identifiers
                    if btn:
                        auth_btn, auth_type = btn, AuthType.SIGN_IN
            elif auth_btn == signin_btn:
                if len(password_fields) == 2 and (btn := signup_btn or other_auth_btn_identifiers):
                    auth_btn, auth_type = btn, AuthType.SIGN_UP

        # Fallback: infer from field structure if `other_progress_btn` exists and is 'submit'
        if not auth_btn and other_progress_btn and other_progress_btn.get('type') == 'submit':
            auth_type = infer_auth_type_from_fields()
            if auth_type:
                auth_btn = other_progress_btn

        # Final fallback: accept non-submit buttons if nothing found yet
        if not auth_btn:
            auth_btn, auth_type = next(
                ((btn, atype) for btn, atype in btn_type_map if btn),
                (None, None)
            )
            if auth_btn: # Apply correction using fields information.
                if auth_btn == signup_btn:
                    if len(password_fields) == 1 and (btn := signin_btn or other_auth_btn_identifiers):
                        auth_btn, auth_type = btn, AuthType.SIGN_IN
                elif auth_btn == signin_btn:
                    if len(password_fields) == 2 and (btn := signup_btn or other_auth_btn_identifiers):
                        auth_btn, auth_type = btn, AuthType.SIGN_UP

            if not auth_btn and other_progress_btn:
                auth_type = infer_auth_type_from_fields()
                if auth_type:
                    auth_btn = other_progress_btn

        # ---------------------------------------------
        # Step 5: Last Resort — Use Link-Based Navigation
        # ---------------------------------------------
        if not auth_btn:

            if other_progress_btn:
                # Fallback: maybe just a button to proceed or acknowledge info
                self.FormInteractorUtils.click(self.WebParserUtils.get_validated_xpath(other_progress_btn))
                return True # Let the next parsing iteration decide
            
            signup_links: list = list(reversed(self.ParsedDataUtils.search_items(sections=['links'], keys=['text'], substrings=signup_auth_btn_identifiers)))
            signin_links: list = list(reversed(self.ParsedDataUtils.search_items(sections=['links'], keys=['text'], substrings=signin_auth_btn_identifiers)))
            auth_btn: list = signup_links or signin_links
            if auth_btn:
                auth_btn: dict = auth_btn[0]
                # Try clicking link if it's a known auth flow
                self.FormInteractorUtils.click(self.WebParserUtils.get_validated_xpath(auth_btn))
                return True # Let the next parsing iteration decide
            
            apply_button_or_link: list = self.ParsedDataUtils.search_items(sections=['buttons','links'], keys=["text"], substrings=start_apply_btn_identifiers, return_first_only=True)
            if apply_button_or_link:
                # Check if Description element appeared during the ongoing Auth Flow.
                apply_button_or_link: dict = apply_button_or_link[0]
                link: str = apply_button_or_link.get('href')
                if link:
                    self.FormInteractorUtils.open_link(link)
                else:
                    self.FormInteractorUtils.click(apply_button_or_link.get('xPath'))
                return True # Let the next parsing iteration decide

            # Give up if absolutely no usable auth button
            logger.error("❌  Auth button or link not found.")
            return False # Auth button not found.
        
        # ---------------------------------------------
        # Step 6: At This Point, auth_btn and auth_type Should Be Set
        # ---------------------------------------------
        # Safety checks before starting the authentication process
        if auth_type in (AuthType.SIGN_UP, AuthType.SIGN_IN):
            # Special case: button found, but no fields
            if len(email_fields) + len(password_fields) == 0:
                self.FormInteractorUtils.click(self.WebParserUtils.get_validated_xpath(auth_btn))
                return True # Let the next parsing iteration decide
        elif auth_type == AuthType.VERIFY:
            if len(self.ParsedDataUtils.get_fields()) == 0:
                # Possibly a verification screen with no input — just a "Continue" or "Verify" button
                self.FormInteractorUtils.click(self.WebParserUtils.get_validated_xpath(auth_btn))
                return True # Let the next parsing iteration decide

        # ---------------------------------------------
        # Step 7: Initialize Auth Map using Action Buttons
        # ---------------------------------------------
        auth_map: Dict[AuthType, List[Dict[str, Any]]] = {
            AuthType.SIGN_UP: [btn for btn in [signup_btn, other_progress_btn] if btn],
            AuthType.SIGN_IN: [btn for btn in [signin_btn, other_progress_btn] if btn],
            AuthType.VERIFY: [btn for btn in [verify_btn, other_progress_btn] if btn]
        }

        # ---------------------------------------------
        # Step 8: Return authentication information
        # ---------------------------------------------
        return auth_type, auth_btn, auth_map

    def _synchronize_new_elements(self, new_xpaths: set, upcoming_field_index: int, include_parent_label: bool = False) -> int:
        '''Synchronize new elements into parsed dataat correct place'''

        def _insert_new_fields(new_xpaths: set, upcoming_field_index: int, include_parent_label: bool = False) -> int:

            payload = {}
            if include_parent_label:
                current_field_index = upcoming_field_index-1
                parent_label = '\n'.join(filter(None, [self.ParsedDataUtils.parsed_data['fields'][current_field_index].get(k) for k in standard_label_keys]))
                payload['label-parent'] = parent_label
            
            new_element_position = upcoming_field_index
            for new_xPath in new_xpaths: # Iterate by appending field information
                new_element = self.WebParserUtils.get_element(new_xPath)
                if not ((hidden_value := self.WebParserUtils.search_attribute('hidden', new_element)) and 'true' in map(str.lower, hidden_value.values())):
                    # Insert into self.fields(type:list of Dict[str,Any]) of 'WebPageParser' instance, if dictionary is returned
                    if (field_info := self.WebPageParser._synchronize_fields(self.WebPageParser._extract_field_info(new_element, force_insert=True, payload=payload))): 
                        field_info = [field_info] # Wrap this Dict[str,Any] into list before sending it to itertools.chain 
                        self.WebPageParser.fields = list(itertools.chain(self.WebPageParser.fields[:new_element_position], field_info, self.WebPageParser.fields[new_element_position:]))
                        new_element_position += 1
            self.ParsedDataUtils.parsed_data['fields'] = self.WebPageParser.fields # Update fields container in parsed_data of 'ParsedDataUtils' instance
            return new_element_position-upcoming_field_index    # number of valid field(s) that actually got inserted.

        def _extend_new_buttons(new_xpaths: set) -> int:
            new_element_position = len(self.ParsedDataUtils.get_buttons())
            initial_button_count = new_element_position
            for new_xPath in new_xpaths: # Iterate by appending field information
                new_element = self.WebParserUtils.get_element(new_xPath)
                if not ((hidden_value := self.WebParserUtils.search_attribute('hidden', new_element)) and 'true' in map(str.lower, hidden_value.values())):
                    # Extend the self.ParsedDataUtils.parsed_data['buttons'](type:list of Dict[str,Any]), if dictionary is returned
                    if (btn_info := self.WebPageParser._synchronize_button(self.WebPageParser._extract_button_info(new_element, force_insert=True))): 
                        btn_info = [btn_info] # Wrap this Dict[str,Any] into list before sending it to itertools.chain 
                        self.ParsedDataUtils.parsed_data['buttons'] = list(itertools.chain(self.ParsedDataUtils.parsed_data['buttons'][:new_element_position], btn_info, self.ParsedDataUtils.parsed_data['buttons'][new_element_position:]))
                        new_element_position += 1
            return new_element_position-initial_button_count # number of valid button(s) that actually got appended.

        def _segregate_field_and_button_like_xpaths(xpaths: set) -> tuple[set, set]:
            ''' Supports only relative (full-relative) xpaths '''
            field_like_xpaths = set()
            button_like_xpaths = set()
            for xpath in xpaths:
                if (
                    xpath.startswith("//input") 
                    or xpath.startswith("//textarea") 
                    or xpath.startswith("//select") 
                    or (xpath.startswith("//button") and self.WebParserUtils.is_list_type(self.WebParserUtils.get_element(xpath)))
                ):
                    field_like_xpaths.add(xpath)
                if (
                    not self.WebParserUtils.is_list_type(self.WebParserUtils.get_element(xpath))
                    and (
                        xpath.startswith("//button")
                        or (xpath.startswith("//input") and (("[@type='button']" in xpath) or ("[@type='submit']" in xpath) or ("[@role='button']" in xpath)))
                        or ("[@role='button']" in xpath)
                    )
                ):
                    button_like_xpaths.add(xpath)
            return field_like_xpaths, button_like_xpaths

        logger.debug(f"Handler Response: {new_xpaths}")
        logger.info(f"🪝    {len(new_xpaths)} new elements discovered.")
        field_like_xpaths, button_like_xpaths = _segregate_field_and_button_like_xpaths(new_xpaths) # Segregate xpaths

        field_insert_count = 0
        button_append_count = 0

        if field_like_xpaths:
            logger.info(f"🔌    Insert {len(field_like_xpaths)} discovered input field(s) into the parsed data if valid.")
            field_insert_count = _insert_new_fields( 
                new_xpaths=field_like_xpaths,
                upcoming_field_index=upcoming_field_index,
                include_parent_label=include_parent_label
            )

        if button_like_xpaths:
            logger.info(f"🔌    Append {len(button_like_xpaths)} discovered button-like element(s) into the parsed data if valid.")
            button_append_count = _extend_new_buttons(
                new_xpaths=button_like_xpaths
            )

        logger.info(f"➕    {field_insert_count} input-like field(s) inserted into the parsed data.")
        logger.info(f"➕    {button_append_count} button(s) inserted into the parsed data.")

        total_new_elements_inserted = field_insert_count + button_append_count
        return total_new_elements_inserted
    
    def _resolve_file_upload(self) -> bool:
        """Handles resume and required file uploads. Returns False on failure."""
        
        ''' 
        Upload Resume 
        '''
        is_resume_uploaded = False
        for resume_field in (self.ParsedDataUtils.filter_metadata(section_key="fields", query={"type": "file", "options.type": "resume"}) or []):
            if self.FormInteractor.handle_file_upload(resume_field):
                is_resume_uploaded = True
                time.sleep(2) # Wait briefly for loading to settle.
            else:
                logger.error("🔴    Unable to resolve resume upload field")
                if resume_field['required']:
                    return False
        if not is_resume_uploaded: # Search for possible resume upload options in buttons section, and upload if input field didn't capture.
            for resume_button in (self.ParsedDataUtils.filter_metadata(section_key="buttons", query={"type": "file", "name": "Resume"}) or []):
                if self.FormInteractor.handle_file_upload(resume_button):
                    is_resume_uploaded = True
                    time.sleep(2) # Wait briefly for loading to settle.
                else:
                    logger.error("🔴    Unable to resolve resume upload button")
                    return False
        
        ''' 
        Upload Other (required*) Files 
        '''
        for file_field in (self.ParsedDataUtils.filter_metadata(section_key="fields", query={"type": "file", "required": True, "options.type": "other"}) or []):
                if self.FormInteractor.handle_file_upload(file_field):
                    time.sleep(3) # Wait briefly for loading to settle.
                else:
                    logger.error("🔴    Unable to resolve file upload")
                    return False
        
        return True

    def _resolve_input_field(self, field: Dict[str, Any]) -> bool | set:
        ### Handle Text
        if field['type'] in FIELD_TYPE_IDENTIFIERS_TEXT: handler_response = self.FormInteractor.handle_text_input(field)
        ### Handle Radio
        elif field['type'] in FIELD_TYPE_IDENTIFIERS_RADIO: handler_response = self.FormInteractor.handle_radio(field)
        ### Handle Dynamic List
        elif field['type'] in FIELD_TYPE_IDENTIFIERS_LIST: handler_response = self.FormInteractor.handle_dynamic_list(field)
        ### Handle Multiselect
        elif field['type'] in FIELD_TYPE_IDENTIFIERS_MULTISELECT: handler_response = self.FormInteractor.handle_dynamic_multiselect(field)
        ### Handle Checkbox
        elif field['type'] in FIELD_TYPE_IDENTIFIERS_CHECKBOX: handler_response = self.FormInteractor.handle_checkbox(field)
        ### Handle Dropdown
        elif field['type'] in FIELD_TYPE_IDENTIFIERS_DROPDOWN: handler_response = self.FormInteractor.handle_dropdown(field)
        ### Handle Date Fields
        elif field['type'] in FIELD_TYPE_IDENTIFIERS_DATE: handler_response = self.FormInteractor.handle_date_field(field)
        ### Others
        else: handler_response = None
        return handler_response

    def _attempt_remapping(self, field: Dict[str, Any], field_idx: int) -> int:
        new_parsed_data = self.WebPageParser.parse_page()
        # Direct mapping if all fields are equal.
        if len(self.ParsedDataUtils.get_fields()) == len(new_parsed_data.get('fields', [])):
            self.ParsedDataUtils.parsed_data = new_parsed_data
            logger.info("✅ Remapping of fields was successful. Restarting from where we stopped.")
            return field_idx # Restart at `field_idx` where the error occured
        else:
            # Identify the intersection start point of newly updated DOM w.r.t. current field by comparing keys.
            for i, new_field in enumerate(new_parsed_data.get('fields', [])):
                keys_to_compare = ['id', 'id-custom', 'options', 'label-srcTag', 'label-srcText', 'label-srcAttribute', 'label-custom', 'name']
                if self.ParsedDataUtils.is_item_similar(field, new_field, keys_to_compare, threshold=100, min_match_count=1):
                    # Match found - Re-initialize parsed data 
                    self.ParsedDataUtils.parsed_data = new_parsed_data
                    logger.info("✅ Remapping of fields was successful. Restarting from where we stopped.")
                    field_idx = i
                    return field_idx
            
            logger.error("🔴    Unable to remap... The field probably disappeared from the page.")
            self.WebPageParser.fields = self.ParsedDataUtils.get_fields() # Reset fields container of `WebPageParser` instance back to older version. This ensures our code is synchronized. 
            field_idx += 1
            return field_idx # To give a try to forthcoming fields (e.g. if element genuinely disappeared, rest could still be inplace). Optionally return False to terminate

    def _process_all_fields(self, current_field_idx: int) -> int:
        """
        Processes all fields from the current index. Returns the new current_field_idx after processing.
        """        
        while current_field_idx < len(self.ParsedDataUtils.get_fields()):

            field: Dict[str, Any] = self.ParsedDataUtils.get_field(current_field_idx)

            if field['type'] not in FIELD_TYPE_IDENTIFIERS_TEXT | FIELD_TYPE_IDENTIFIERS_RADIO | FIELD_TYPE_IDENTIFIERS_LIST | FIELD_TYPE_IDENTIFIERS_MULTISELECT | FIELD_TYPE_IDENTIFIERS_CHECKBOX | FIELD_TYPE_IDENTIFIERS_DROPDOWN | FIELD_TYPE_IDENTIFIERS_DATE:
                current_field_idx += 1
                continue

            # Ensure element is not misplaced in DOM by asserting atleast one of 'xPath'(absolute/relative) or 'xPath-relative'(relative-only) is present.
            if self.WebParserUtils.is_element_misplaced(field):
                logger.warning(f"📡 Element misplaced in DOM. Retracking...")
                # We can't regain absolute xpath but we can attempt to re-build relative.
                # This makes overall execution efficient, by avoiding re-calculation of XPath again and again.
                new_relative_xpath: str | None = self.WebParserUtils.get_validated_xpath(field)
                if new_relative_xpath:
                    field['xPath'] = field['xPath-relative'] = new_relative_xpath
                    logger.info("💬  Successfully re-discovered new relative XPath")
                else:
                    self.ParsedDataUtils.pretty_print(field)
                    logger.warning("⚠️  Unable to re-discover.")

            # If still misplaced after retracking
            if self.WebParserUtils.is_element_misplaced(field):
                # Perform remapping
                logger.warning("🔄  Remapping entire DOM...")
                if field['required'] or True:
                    remapped_start_idx = self._attempt_remapping(field=field, field_idx=current_field_idx)
                    current_field_idx = remapped_start_idx
                else:
                    logger.error(f"🔴 Unable to resolve optional field at index {current_field_idx}. Skipping.")
                    current_field_idx += 1
                continue

            # Field is usable — try to resolve
            handler_response: bool | set = self._resolve_input_field(field)
            '''
            # Set: Contains xPaths of the newly (dynamically) added fields into the DOM.
            # True: Doesn't necessarily mean field was entered as desired, but handled efficiently.
            # False: Means that errors were encountered during the handling process which eventually were unable to resolve.
            '''
            if isinstance(handler_response, set): 

                self._synchronize_new_elements(new_xpaths=handler_response, upcoming_field_index=current_field_idx+1, include_parent_label=True)

            elif handler_response is False: # Log error

                # Delete 'Education' Section
                if (field['type'] in FIELD_TYPE_IDENTIFIERS_MULTISELECT) and (self.ParsedDataUtils.is_match(field, {"options.category": "Education"})):
                    current_education_num: int = self.ParsedDataUtils.get_nested_value(field, "options.id")
                    logger.info(f"Removing this Education Section ID: {current_education_num}")
                    del_button_num: int = None
                    if self.WebPageParser.last_edu_or_work_section == 'edu':
                        del_button_num = self.WebPageParser.work_experience_sectionID_primary + current_education_num
                    else:
                        del_button_num = self.ParsedDataUtils.get_nested_value(field, "options.id")
                    # Find Button to Remove this Education Section
                    remove_buttons = self.ParsedDataUtils.search_items(sections=['buttons'], keys=["text"], substrings=['delete', 'remove'], return_first_only=False)
                    if remove_buttons and len(remove_buttons) >= del_button_num:
                        del_button_xpath = self.WebParserUtils.get_validated_xpath(remove_buttons[del_button_num-1])
                        if del_button_xpath:
                            # Delete this education section
                            logger.info(f'Education Section {current_education_num} deleted.')
                            self.FormInteractorUtils.click(del_button_xpath)
                            # Skip fields within deleted section.
                            logger.info('Skipping fields contained within this education section.')
                            while self.ParsedDataUtils.is_match(field, {"options.category": "Education", "options.id": current_education_num}):
                                current_field_idx += 1
                                field = self.ParsedDataUtils.get_field(current_field_idx)
                            continue

                logger.error(f"🔴 Unable to resolve {field['type']} field")
            print('================ Next Input ================')
            current_field_idx += 1

        return current_field_idx

    def _get_ack_action_item(self) -> Dict[str, Any]:

        # Search buttons
        ack_buttons = list(reversed(self.ParsedDataUtils.search_items(sections=["buttons"], keys=stardard_button_search_keys, substrings=ack_btn_identifiers))) # Search all buttons
        if ack_buttons:
            for btn_item in ack_buttons:
                if btn_item.get('text'): # Visible text must exists
                    return btn_item
                
        # Search links
        ack_links = list(reversed(self.ParsedDataUtils.search_items(sections=['links'], keys=["text"], substrings=["read and accept", "read the terms", "please read", "accept the agreement", "terms and conditions"])))
        for link_item in ack_links:
            try:
                element = self.WebParserUtils.get_validated_xpath(link_item)
                if element is None:
                    continue
                # Heuristic check for modal trigger
                onclick_attr = element.get_attribute('onclick')
                href_attr = element.get_attribute('href') or ""
                target_attr = element.get_attribute('target') or ""
                is_likely_modal = bool(onclick_attr) and not href_attr.startswith("http") and target_attr != "_blank"
                if not is_likely_modal:
                    continue  # Skip likely navigational links
                return link_item
            except Exception as e:
                logger.warning(f"Failed to process modal link: {e}")
                continue

        return {}

    def _get_progress_action_item(self) -> Dict[str, Any]:
        # Search into buttons section (Only 'submit' type buttons)
        submit_btns: list = list(reversed(self.ParsedDataUtils.search_items(sections=['buttons'], filter_dict={'type':'submit'}))) # Get submit type buttons
        for btn in submit_btns:
            if self.ParsedDataUtils.is_substrings_in_item(item=btn, keys=['text'], substrings=progress_btn_identifiers):
                return btn
        # Search into buttons section (All buttons)
        for btn in list(reversed(self.ParsedDataUtils.get_buttons())):  # Iterate all buttons.
            if self.ParsedDataUtils.is_substrings_in_item(item=btn, keys=['text'], substrings=progress_btn_identifiers):
                return btn
        # Fallback, no progress button was found.
        if len(submit_btns) == 1: # Interpret standalone submit button as progress item (if exists).
            return submit_btns[0]
        return {}

    def _select_fresh_action_item(self, candidates: List[Dict[str, Any]], visited_parent_items: List[Dict[str, Any]], visited_link_items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        visited_absolute = {i.get("xPath") for i in visited_parent_items + visited_link_items}
        visited_relative = {i.get("xPath-relative") for i in visited_parent_items + visited_link_items}
        for item in candidates:
            if item and self.WebParserUtils.get_validated_xpath(item):
                if item['xPath'] not in visited_absolute and item['xPath-relative'] not in visited_relative:
                    return item
        return next((i for i in candidates if i), None)  # fallback

    def _extract_and_resolve_otp(self, emails: List, verification_field_items: List[Dict[str,Any]]) -> bool:

        def extract_otp() -> Optional[int]:
            # Apply Filter
            filtered_emails: list = []
            max_age_minutes: int = 2
            expected_digit_count: int = len(verification_field_items)
            otp_digits: set = {4,6} if expected_digit_count == 1 else {expected_digit_count}
            for email in emails:
                otp = email.get('OTP')
                striped_otp = email.get('OTP').lstrip(' 0')
                if (
                    not otp # Exclude if OTP doesn't exists
                    or len(otp) != len(striped_otp) # Exclude if OTP contains leading zero(s)
                    or len(otp) not in otp_digits # Exclude if OTP digits are not syncronized with identified fields
                    or not env_config.otp_fetcher.was_received_recently(time_input=email.get("Time"), max_age_minutes=max_age_minutes) # Exclude non-recent emails by setting an age_boundary
                ): 
                    continue
                filtered_emails.append(email)
            
            # Initialize 'otp' to be returned
            otp = None
            
            if filtered_emails: # Atleast one email exists after applying the filter.
                if len(filtered_emails) == 1:
                    otp = filtered_emails[0].get('OTP')
                else:
                    verification_email_identifiers = ['confirm your identity', 'confirm your email address', 'one-time pass code', 'code will expire', 'link will expire', 'code will expire', 'verification']
                    for email in filtered_emails:
                        if any(identifier in email.get('Body') for identifier in verification_email_identifiers):
                            otp = email.get('OTP')
                            break
                    if not otp:
                        otp = filtered_emails[0].get('OTP')

            # Finally return 'otp'
            return otp
        
        def resolve_otp(otp: int) -> bool:
            if len(verification_field_items) == 1:
                xpath = self.WebParserUtils.get_validated_xpath(verification_field_items[0])
                if xpath:
                    self.WebParserUtils.get_element(xpath).send_keys(otp)
                else:
                    logger.error("Verification field missing in DOM")
                    return False
            elif len(verification_field_items) == len(otp):
                for i, digit in enumerate(otp):
                    xpath = self.WebParserUtils.get_validated_xpath(verification_field_items[i])
                    if xpath:
                        self.WebParserUtils.get_element(xpath).send_keys(digit)
                    else:
                        logger.error("Verification field missing in DOM")
                        return False
            else:
                logger.error("🧩    Length of 'OTP digits' and 'Verification fields' are not synchronized.")
                return False
            return True

        otp = extract_otp()
        if otp:
            logger.info(f"🔑    OTP Found: {otp}")
            return resolve_otp(otp)
        else:
            logger.error("❓    OTP was not found in the fetched emails.")
            return False

    def _resolve_email_verification(self) -> bool:

        '''
        Extract and Verify URL
        '''
        def extract_verification_url(emails: list) -> Optional[str]:
            for email in emails:
                if (
                    not email.get('URL')    # If no verification URL exists in email.
                    or not env_config.otp_fetcher.was_received_recently(time_input=email.get("Time"), max_age_minutes=6) # Exclude non-recent emails by setting an age_boundary
                ):
                    continue
                return email.get('URL')[0]

        def verify_url(url: str, return_to_original: bool = True) -> None:
            """
            Opens a new tab, navigates to the given URL, and optionally returns to the original tab.

            Args:
                url (str): URL to open.
                return_to_original (bool): Whether to close new tab and switch back.
            """

            original_tab = self.driver.current_window_handle

            # Open new tab
            self.driver.execute_script("window.open('');")
            new_tab = self.driver.window_handles[-1]
            time.sleep(0.2)

            # Switch to new tab and open the URL
            self.driver.switch_to.window(new_tab)
            time.sleep(0.2)
            self.driver.get(url)

            # Wait until the page is fully loaded
            if not self.WebParserUtils.wait_for_stable_dom(padding=1):
                logger.warning("⚠️ Timed out waiting for page to load.")

            # Optionally close the new tab and return to original
            if return_to_original:
                self.driver.close()
                self.driver.switch_to.window(original_tab)

        '''
        Initialize Flow Control Variables
        '''
        initial_wait_seconds = 90
        max_attempts = 2
        wait_steps = 45
        URL = None

        for retry in range(max_attempts):
            '''
            Wait for email
            '''
            wait_seconds = initial_wait_seconds if retry==0 else wait_steps
            logger.info(f"🟡    Waiting {wait_seconds} seconds for email to be received...")
            time.sleep(wait_seconds)

            '''
            Fetch recent emails
            '''
            top_n = 2
            logger.info(f"📥 Fetching top {top_n} emails from Primary Inbox...")
            try:
                emails: list = env_config.otp_fetcher.fetch_recent_emails(top_n=top_n, query='category:primary')
            except Exception as e:
                logger.error(f"📧   Unable to fetch email. Exception: {e}")
                return False
            logger.info("📧 Emails Received. Reading emails...")

            URL = extract_verification_url(emails)
            if URL:
                break

        if URL:
            verify_url(URL, return_to_original=True)
            logger.info(f"✔️    Email verification completed.")
            return True
        else:
            logger.error(f"❓   Email verification link was not found in recent {top_n} emails.")
            return False

    def _identify_and_resolve_verification_lock(self, auth_type: AuthType, auth_map: Dict[AuthType, List[Dict[str, Any]]]) -> Optional[bool]:
        # Check if verification lock exists on webpage.
        is_email_verification_step = self.WebParserUtils.is_text_present_on_webpage(email_verification_page_text_identifiers)
        is_otp_verification_step = self.WebParserUtils.is_text_present_on_webpage(otp_verification_page_text_identifiers)
        # Check if email type verification lock.
        if is_email_verification_step and not is_otp_verification_step:
            '''
            Verify Email
            '''
            if self._resolve_email_verification():
                '''
                Post-Verification Handling
                '''
                logger.info("⏳ Waiting 5 seconds before signing in...")
                time.sleep(5)   # seconds
                if auth_type == AuthType.SIGN_UP:   # Currently on SignUp page
                    signIn_btns = auth_map.get(AuthType.SIGN_IN, [])    # Get SignIn related buttons
                    for btn in signIn_btns:
                        xpath = self.WebParserUtils.get_validated_xpath(btn)    # Check if XPath is valid
                        if xpath:
                            self.FormInteractorUtils.click(xpath)   # Click the SignIn button
                            time.sleep(3)
                            return True # Return TRUE for next parsing
                    self.driver.refresh() # Reload current webpage
                    self.WebParserUtils.wait_for_stable_dom(padding=1)
                    return True
                elif auth_type == AuthType.SIGN_IN: # Currently on SignIn page
                    self.driver.refresh() # Reload current webpage
                    self.WebParserUtils.wait_for_stable_dom(padding=1)
                    return True # Return TRUE for next parsing
            else:
                logger.error("🔴    Failed to verify email. Aborting resolution.")
                return False
        elif is_otp_verification_step:  # Very unlikely.
            # Unlikely because code-fields entering part should have been handled before any button clicks.
            # Possible if the DOM actually changed (but not significantly) brining in code-entering-fields but didn't detect change.  
            return True # Let next parsing handle.
        
        return None # Lock resolution not required

    def _resolve_form_page(self, current_field_idx: int = 0, max_depth: int = 4, depth: int = 0, parent_action_items: List[Dict[str, Any]] = None, visited_link_items: List[Dict[str, Any]] = None) -> bool:

        '''
        Base Return Condition
        '''
        if depth >= max_depth:
            logger.warning("🧬 Max depth reached during form resolution.")
            return False 
        
        '''
        Exceptional Page Error State Handling
        '''
        page_loading_error_indicators : set = {
            'something went wrong', 'refresh the page'
        }
        if len(self.ParsedDataUtils.get_fields()) < 3 and self.WebParserUtils.is_text_present_on_webpage(page_loading_error_indicators):
            logger.warning("🧩  Page went into an unknown state. Reloading...")
            self.driver.refresh() # Reload current webpage
            logger.info("⌛ Waiting for the page to settle...")
            self.WebParserUtils.wait_for_stable_dom(padding=2)
            return True # Re-parse the page in next iteration.

        '''
        Get Auth Info
        '''
        auth_item: Dict[str, Any] = {} 
        if self.form_state == FormState.AUTH_PAGE:
            auth_response: bool | Tuple[AuthType, Dict[str, Any], Dict[AuthType, List[Dict[str, Any]]]] = self._get_auth_type_and_action_item()
            if isinstance(auth_response, bool):
                # True -> Requires next page iteration. (Click operation performed internally)
                # False -> Can't be resolved. (Terminate current job)
                return auth_response
            elif isinstance(auth_response, tuple):
                auth_type, auth_item, auth_map = auth_response
            
            if auth_type == AuthType.VERIFY:
                # Get verification fields
                verification_field_items: List[Dict[str,Any]] = self.ParsedDataUtils.filter_metadata(section_key="fields", query={"options.category": "verification"})
                if (verification_field_items) and (len(verification_field_items) in {1,4,6}):
                    wait_seconds = 90
                    logger.info(f"🟡    Waiting {wait_seconds} seconds for email to be received...")
                    time.sleep(wait_seconds)
                    top_n = 2
                    logger.info(f"📥 Fetching top {top_n} emails from Primary Inbox...")
                    try:
                        emails: list = env_config.otp_fetcher.fetch_recent_emails(top_n=top_n, query='category:primary')
                    except Exception as e:
                        logger.error(f"📧   Unable to fetch email. Exception: {e}")
                        return False
                    logger.info("📧 Emails Received. Reading emails...")
                    if self._extract_and_resolve_otp(emails=emails, verification_field_items=verification_field_items):
                        # Update current_field_index
                        last_verication_field = self.ParsedDataUtils.get_field_index(verification_field_items[-1])
                        if last_verication_field:
                            current_field_idx = last_verication_field + 1
                        else:
                            logger.warning("⚠️  Last verification field item not found in parsed data! Skipping all other input fields...")
                            current_field_idx = len(self.ParsedDataUtils.get_fields())  
                    else:
                        logger.error("❌    Failed to extract otp or resolve verification field(s).")
                        return False
                else:
                    # Check if email/pass field exists to continue execution, otherwise return false.
                    # Try to get 'email' fields by type, or fallback using known key identifiers
                    email_fields = self.ParsedDataUtils.search_items(sections=['fields'], filter_dict={'type': 'email'}) or self.ParsedDataUtils.search_items(sections=['fields'], keys=stardard_field_search_keys, substrings=['Email'], filter_dict={'type':'text'})
                    # Try to get 'password' fields
                    password_fields = self.ParsedDataUtils.search_items(sections=['fields'], filter_dict={'type': 'password'})
                    if not email_fields and not password_fields:
                        logger.error(f"Page state {FormState.AUTH_PAGE.name} -> type {AuthType.VERIFY.name}, not matching page layout")
                        return False

        '''
        File Upload
        '''
        if self.form_state == FormState.LOGGED_IN and depth == 0: # One Time Only
            if not self._resolve_file_upload():
                # return False
                pass # Proceed irrespective of the file is successfully uploaded or not.
        
        ''' 
        Resolve Fields 
        '''
        current_field_idx = self._process_all_fields(current_field_idx)
        
        ''' 
        Identify Button (to be clicked)
        '''
        ack_item, progress_item = {}, {}
        # Search: Acknowledgement Button
        ack_item: Dict[str, Any] = self._get_ack_action_item()
        # Search: Progress Button (Submit or Save & Continue) to advance the form to next step.
        if self.form_state == FormState.LOGGED_IN: # Implemented As (When Logged in): Atleast one progress button should exists, otherwise return False.
            progress_item: Dict[str, Any] = self._get_progress_action_item()
            if not progress_item: # Return Failure if unable to find the progress button.
                logger.error(f'❓   Form progress element not found.')
                return False # Terminate current job
        
        '''
        Click Action Item
        '''
        # Set action item (element's metadata to be clicked)
        action_item_candidates: List[Dict[str, Any]] = [ack_item, progress_item, auth_item]
        action_item: Optional[Dict[str, Any]] = self._select_fresh_action_item(action_item_candidates, parent_action_items or [], visited_link_items or [])
        if not action_item:
            logger.error("🔴 No actionable button found to proceed.")
            return False
        # Initialize change threshold dynamically
        preserve_threshold: float = 0.69 if len(self.ParsedDataUtils.get_fields()) < 5 else 0.69    # If more than x% is preserved, then page has not changed.
        # Attempt button click
        handler_response = self.FormInteractor.handle_button(action_item, delta_thresh=preserve_threshold) # Click & Record response.
        
        '''
        Resolve Action Resoponse (Case 1)
        '''
        # Case 1: Action led to a form step transition
        if handler_response is True:
            logger.info("✅ Form advanced successfully.")
            return True
        
        '''
        Track the parent actions if it's XPath still valid in the DOM
        '''
        logger.info("🟡 Page not progressed yet...")
        parent_action_items: List[Dict[str, Any]] = parent_action_items or []
        visited_link_items: List[Dict[str, Any]] = visited_link_items or []
        visited_any = {i.get("xPath") for i in (parent_action_items or []) + (visited_link_items or [])}
        visited_rel = {i.get("xPath-relative") for i in (parent_action_items or []) + (visited_link_items or [])}
        logger.info("🔌 Adding current action item to into the parent's list (if exists in DOM)")
        xpath = self.WebParserUtils.get_validated_xpath(action_item)
        if xpath:
            # Track as parent if not visited
            if action_item['xPath'] not in visited_any and action_item['xPath-relative'] not in visited_rel:
                parent_action_items.append(action_item)
                logger.info(f"🔌 Appended current action item ({action_item.get('text')}) into parent action items stack")
            # Track as link if it's an <a> and not visited
            element = self.WebParserUtils.get_element(xpath)
            if element and element.tag_name.lower() == 'a':
                if action_item['xPath'] not in visited_any and action_item['xPath-relative'] not in visited_rel:
                    visited_link_items.append(action_item)
                    logger.info(f"🔌 Appended current action item ({action_item.get('text')}) into visited link items")

        '''
        Resolve Action Resoponse (Case 2)
        '''
        # Case 2: New elements were dynamically added
        if isinstance(handler_response, set):
            print("VISITED ANY:", visited_any)
            print("VISITED RELATIVE:", visited_rel)
            print("IS Looping:", any(xp for xp in handler_response if (xp in visited_any) or (xp in visited_rel)))
            # Synchronize new elements into the parsed data
            new_elements_count = self._synchronize_new_elements(new_xpaths=handler_response, upcoming_field_index=current_field_idx)
            if new_elements_count > 0:
                return self._resolve_form_page(
                    current_field_idx=current_field_idx,
                    max_depth=max_depth,
                    depth=depth + 1,
                    parent_action_items=parent_action_items,
                    visited_link_items=visited_link_items
                )
            else:
                logger.info("🔹 There were no valid elements to be added into the parsed data.")
                handler_response = False
        
        '''
        Resolve Action Resoponse (Case 3)
        '''
        # Case 3: No changes — might be a modal close, form error, or dead end
        if handler_response is False:
            logger.warning(f"⚠️  No significant changes were detected on clicking the action item. Might be a modal close, form error, or dead end.")
            # ⛔️ Special handling for AUTH_PAGE: Attempt to toggle between Sign In and Sign Up if current action failed
            if self.form_state == FormState.AUTH_PAGE and action_item == auth_item:

                verification_lock_resolution_response: Optional[bool] = self._identify_and_resolve_verification_lock(auth_type, auth_map)
                if isinstance(verification_lock_resolution_response, bool):
                    '''
                    True -> Requires next page parsing.
                    False -> Unable to resolve verification lock
                    None -> Lock doesn't exists. Continue execution flow.
                    '''
                    return verification_lock_resolution_response

                # Define a toggle map to switch between auth types
                toggle_map = {
                    AuthType.SIGN_UP: AuthType.SIGN_IN,
                    AuthType.SIGN_IN: AuthType.SIGN_UP,
                }
                for current_type, toggle_type in toggle_map.items():
                    # If the current action item belongs to the current auth type (e.g., SIGN_UP), switch to its counterpart (e.g., SIGN_IN)
                    if action_item in auth_map.get(current_type, []):
                        toggle_items = auth_map.get(toggle_type, [])
                        if toggle_items:
                            # Validate and click the toggle button (e.g., from Sign Up to Sign In)
                            xpath = self.WebParserUtils.get_validated_xpath(toggle_items[0])
                            if xpath:
                                self.FormInteractorUtils.click(xpath)
                                # Wait for the new page state to fully load
                                self.WebParserUtils.wait_for_stable_dom(padding=1)
                                return True # Attempted toggle, return success to retry form parsing
                        break  # Exit loop once toggled

            # 🔁 Attempt fallback using previously clicked parent buttons (Example: When resolved-model appeared on parent's click)
            if parent_action_items:
                logger.info("⛓️  Attempting fallback using previously clicked parent buttons (not links) if valid from stack.")
                for idx, parent_item in enumerate(reversed(parent_action_items)):

                    # Skip links (<a>) as clicking them may reload the page unnecessarily
                    if self.WebParserUtils.xpath_matches_tag(parent_item.get('xPath'), 'a') or self.WebParserUtils.xpath_matches_tag(parent_item.get('xPath-relative'), 'a'):
                        continue

                    xpath = self.WebParserUtils.get_validated_xpath(parent_item)
                    if not xpath:
                        continue # Skip if parent is no longer in DOM
                    element = self.WebParserUtils.get_element(xpath)

                    # Try clicking a previously clicked parent button again (could be modal dismiss or partial form reload)
                    handler_response = self.FormInteractor.handle_button(parent_item, delta_thresh=preserve_threshold)
                    logger.info(f"🖱️    Clicked the parent action item ({parent_item.get('text')}).")
                    logger.debug(f"🧾   Handler response on-click: {handler_response}")
                    if handler_response is True:
                        logger.info("✅ Form advanced successfully.")
                        return True
            
                    # 🔍 Decide whether to retain or remove this parent item from the list:
                    # Retain if it still exists in DOM (i.e., modal-type)
                    logger.info("🕵️ Retain if this parent action item still exists in DOM.")
                    retain_self = self.WebParserUtils.get_validated_xpath(parent_item) is not None
                    cutoff = len(parent_action_items) - (idx if retain_self else idx + 1)
                    parent_action_items[:] = parent_action_items[:cutoff]
                    
                    # Recurse to retry form resolution after attempting fallback click
                    logger.info("➰  Recurse to retry form resolution after attempting fallback click.")
                    return self._resolve_form_page(
                        current_field_idx=current_field_idx,
                        max_depth=max_depth,
                        depth=depth + 1,
                        parent_action_items=parent_action_items,
                        visited_link_items=visited_link_items
                    )
                logger.error(f"🔴   No valid parent actions left to resolve: {action_item.get('xPath-relative')}")
            else:
                logger.error(f"🔴   Button could not resolve the form: {action_item.get('xPath-relative')}")

            # Try other action candidates if any were skipped earlier
            logger.info("🧭  Checking if any other action candidate is available in DOM.")
            if any(i and i != action_item for i in action_item_candidates):
                logger.info("➰  Another action item exists, recuring with updated visited set. Hopefully handle this newly discovered candidate in next recur.")
                return self._resolve_form_page(
                    current_field_idx=current_field_idx,
                    max_depth=max_depth,
                    depth=depth + 1,
                    parent_action_items=parent_action_items,
                    visited_link_items=visited_link_items
                )

            return False

        '''
        Resolve Action Resoponse (Case 4)
        '''
        # Case 4: Unexpected response
        logger.error(f"🐛🔴 Unknown response from handle_button: {handler_response}")
        return False
        
    def resolve_parsed_data(self) -> bool:

        if self.form_state == FormState.DESCRIPTION_PAGE:
            resolution_response: bool = self._resolve_description_page()
        elif (
            self.form_state == FormState.AUTH_PAGE
            or self.form_state == FormState.LOGGED_IN
        ):
            resolution_response: bool = self._resolve_form_page()
        else:   # Not possible, but just to make it future proof.
            logger.critical(f"🐞  Form went into an unknown state: {self.form_state}")
            resolution_response: bool = False

        return resolution_response













