# modules/upload_manager.py
from selenium.webdriver.common.by import By # type: ignore
from selenium.common.exceptions import ElementClickInterceptedException, NoSuchElementException # type: ignore
from selenium.webdriver.remote.webelement import WebElement # type: ignore
import threading
import queue
import os
import time
from urllib.parse import urlparse
from pywinauto import Application, findwindows
from pywinauto.keyboard import send_keys  # Correct import for send_keys
from pywinauto.findwindows import ElementNotFoundError
from typing import Optional, List, Dict
import json
from lxml import html as lxml_html
from lxml.html import tostring

# === Shared Upload Control === #
upload_queue = queue.Queue()
upload_lock = threading.Lock()

def close_file_dialog(form_interactor):
    """Detects if the file upload dialog is open and closes it."""
    
    # Get the current domain name from the driver URL
    domain_name = urlparse(form_interactor.driver.current_url).netloc
    
    # Find all open windows
    all_windows = findwindows.find_windows()
    target_dialog = None

    # Try to find a dialog window with the domain name in its title
    for hwnd in all_windows:
        title = findwindows.find_element(handle=hwnd).name
        if title and domain_name.lower() in title.lower():
            target_dialog = title
            break

    # Fallback if no domain-based match
    if not target_dialog:
        for hwnd in all_windows:
            title = findwindows.find_element(handle=hwnd).name
            if title.strip() == "Open":
                target_dialog = "Open"
                break

    # Fallback if no "Open" title match
    if not target_dialog:
        for hwnd in all_windows:
            title = findwindows.find_element(handle=hwnd).name
            if "open" in title.lower():
                target_dialog = title
                break

    # If the dialog is found, close it
    if target_dialog:
        # print(f"[✓] File dialog '{target_dialog}' is open. Closing it now.")
        try:
            # Connect to the dialog
            app = Application().connect(title=target_dialog)
            dlg = app.window(title=target_dialog)
            
            # Try to click the "Cancel" button or send ESC to close the dialog
            if dlg.has_control("Cancel"):
                dlg["Cancel"].click()  # Click the "Cancel" button
            else:
                # If no Cancel button, send ESC to close the dialog
                send_keys('{ESC}')
            # print(f"[✓] File dialog '{target_dialog}' closed.")
            return True
        
        except Exception as e:
            # print(f"[!] Error closing file dialog: {e}")
            return False
    else:
        # print("[!] No file dialog found.")
        return False

def upload_file_via_dialog(target_dialog_title: str, file_path: str) -> bool:
    """
    Uploads a file through a file dialog window. This function connects to the dialog window,
    waits for it to be visible, ensures it's focused, sets the file path in the 'Edit' field,
    and simulates pressing the 'Enter' key to confirm the upload.

    Parameters:
    - target_dialog_title (str): The title of the dialog window.
    - file_path (str): The full path to the file to be uploaded.

    Returns:
    - bool: Returns True if the file was uploaded successfully, False otherwise.
    """
    try:
        # Try connecting to the application and finding the window with the target title
        app = Application().connect(title=target_dialog_title)
        dlg = app.window(title=target_dialog_title)

        # Simulate a minor wait for the dialog to be visible (adjust the sleep time as necessary)
        # Wait for the dialog to become visible (a few seconds)
        start_time = time.time()
        while time.time() - start_time < 5:  # Wait up to 5 seconds
            if dlg.exists() and dlg.is_visible():
                break
            time.sleep(0.1)  # Sleep briefly before checking again

        # If the dialog is not visible or does not exist, raise an error
        if not dlg.exists() or not dlg.is_visible():
            print(f"[!] Dialog window '{target_dialog_title}' is not visible.")
            return False

        # Ensure the dialog is focused
        if not dlg.is_active():  # If the dialog is not focused
            dlg.set_focus()  # Bring the dialog into focus

        # Ensure that the 'Edit' field exists and set the file path
        try:
            dlg["Edit"].set_edit_text(file_path)
        except ElementNotFoundError:
            print("[!] 'Edit' field not found in the dialog.")
            return False

        # Simulate pressing the Enter key to confirm the upload
        dlg.type_keys("{ENTER}")
        
        # Optionally, add a small wait to ensure the dialog processes the file selection
        time.sleep(1)

        # Optionally, return True if dialog was successfully interacted with
        # print(f"[✓] File '{file_path}' uploaded via dialog: '{target_dialog_title}'")
        return True

    except Exception as e:
        # If any error occurs (e.g., dialog not found, Edit field missing, etc.), print the error
        print(f"[!] Failed to upload file via dialog: {e}")
        return False

def detect_dialog_window(form_interactor) -> Optional[str]:
    """
    Detects a native Windows file dialog window related to the current browser session.
    Filters by standard Windows dialog class (#32770) and common file dialog titles.
    Returns the title of the matched dialog if found, otherwise None.
    """
    target_dialog = None
    domain_name = urlparse(form_interactor.driver.current_url).netloc.lower()

    # Get only standard Windows dialog windows
    dialog_windows = findwindows.find_elements(class_name="#32770")

    # Priority 1: Match dialog with domain name in title
    '''
    (Optional - Loops all windows including browsers, etc.)
    dialog_windows = findwindows.find_windows()
    for win in dialog_windows: # Loops all windows
        title = findwindows.find_element(handle=win).name
        ...
    '''
    for win in findwindows.find_elements(class_name="#32770"): # Get only standard Windows dialog windows
        title = win.name.strip()
        if domain_name in title.lower():
            target_dialog = title
            break

    # Priority 2: Exact match with "Open" (most common for file dialogs)
    if not target_dialog:
        for win in dialog_windows:
            if win.name.strip() == "Open":
                target_dialog = win.name
                break

    # Priority 3: Partial match containing "open"
    if not target_dialog:
        for win in dialog_windows:
            if "open" in win.name.lower():
                target_dialog = win.name
                break

    return target_dialog

def process_file_upload(form_interactor, element_or_xpath, file_path, done_event):
    """
    Handles the process of uploading a file through a form.

    This function performs the following steps:
    1. Converts the given file path to an absolute path and checks if the file exists.
    2. Validates if the specified element or xPath is present in the DOM.
    3. Attempts to trigger a file upload dialog by simulating a click on the specified element.
    4. If the dialog window is opened, uploads the file through the dialog window.
    5. If no dialog is opened, checks if a file input element is dynamically added to the DOM and uploads the file using 'send_keys' or triggers the file upload dialog.
    6. Handles edge cases where the file is already uploaded or the dialog window is not opened.
    7. Ensures thread safety with an upload lock to prevent multiple simultaneous upload operations.

    Parameters:
    - form_interactor: An object that interacts with the web form (e.g., using Selenium).
    - element_or_xpath: The element to trigger the file upload or the xPath to locate it.
    - file_path: The absolute file path of the file to be uploaded.
    - done_event: A threading event to signal when the upload process is complete.

    Returns:
    - bool: True if the file was uploaded successfully, False otherwise.
    """

    
    '''
    File Handling
    '''
    file_path = os.path.abspath(file_path) # Convert the file path to an absolute path to ensure we are working with the full path.
    if not os.path.exists(file_path): # Check if the file exists at the specified location.
        print(f"[!] File not found: {file_path}") # If the file does not exist, print a warning and return False.
        done_event.set() # Trigger the done event to signal that the operation should stop.
        return False # Return False indicating failure to locate the file.
    
    try:
        with upload_lock: # Use a lock to ensure only one thread performs the upload operation at a time

            ''' 
            Validate if the specified xPath corresponds to an element in the DOM
            '''
            if isinstance(element_or_xpath, str):
                try:
                    element = form_interactor.driver.find_element(By.XPATH, element_or_xpath)
                except NoSuchElementException:
                    done_event.set()  # Trigger done_event
                    return False
            elif isinstance(element_or_xpath, WebElement):
                element = element_or_xpath
            else: # Invalid argument
                done_event.set()  # Trigger done_event
                return False # Indicate failure

            '''
            If the upload element is found, simulate a click on the element to trigger the file upload dialog
            '''
            html_diff_dom = form_interactor.FormInteractorUtils.get_updated_dom_after_click(element)[0] # Simulate click
            target_dialog = detect_dialog_window(form_interactor) # Check if the dialog window is opened
            if target_dialog: # Connect and upload file
                print('Found 1', target_dialog)
                if upload_file_via_dialog(target_dialog, file_path):
                    done_event.set() # Indicate that the upload was successful
                    return True
                else:
                    print('Failed to upload file via dialog')
            
            '''
            If no dialog was opened, check if the dynamic DOM contains a file input element
            '''
            xpath = None
            if html_diff_dom != '': # Ensure that the DOM is not empty
                # Parse the updated HTML part to find any dynamically added input fields
                tree = lxml_html.fragment_fromstring(html_diff_dom, create_parent="div") # Convert the HTML fragment to an lxml tree
                for el in tree.iter(): # Iterate through all elements in the parsed tree
                    if el.tag == 'input': # Only fetch the <input> field - Avoiding Cloud upload buttons.
                        xpath = form_interactor.WebParserUtils.get_xpath(el) # Get the xPath of the input element
                        if xpath: 
                            break # Stop once the first valid input element is found
            
            '''
            Check if xPath was found and it corresponds to an element in the DOM
            '''
            if xpath:
                try: # Validate if the input element exists in the DOM
                    element = form_interactor.driver.find_element(By.XPATH, xpath)
                except NoSuchElementException:
                    print("[!] Upload button not found.")
                    done_event.set() # Trigger done_event to indicate failure
                    return False
            else:
                done_event.set() # Trigger done_event to indicate failure
                return False

            ''' 
            Attempt 'send_keys' and 'click dialog' on this new dynamically discovered element
            '''
            file_name = file_path.split('\\')[-1] # Extract the file name from the full file path
            ### Ensure the file is not already uploaded by checking if the file name is present in the page source
            if file_name not in form_interactor.driver.page_source: # File is not already uploaded.
                element.send_keys(file_path) # Use send_keys to upload the file
                time.sleep(1) # Wait briefly for the file to upload
                # Verify if the file has been uploaded successfully by checking the page source
                if file_name in form_interactor.driver.page_source: # File is uploaded
                    done_event.set() # Trigger done_event indicating the file was uploaded successfully
                    return True
                # If not uploaded, attempt to trigger the file dialog again on this new element and upload through the dialog
                else:
                    form_interactor.FormInteractorUtils.click(element) # Attempt upload through 'dialog'
                    time.sleep(1.5)
                    target_dialog = detect_dialog_window(form_interactor) # Check if the dialog window was opened
                    if target_dialog: # Connect and upload file
                        if upload_file_via_dialog(target_dialog, file_path):
                            done_event.set() # Indicate success
                            return True
            ### File was previously uploaded on portal.
            else:
                # Attempt file upload while fetching 'html_diff_dom' to verify if existing file was replaced.
                html_diff_dom = form_interactor.FormInteractorUtils.get_updated_dom_after_send_keys(element, file_path)[0]
                # Verify if the file has been uploaded successfully by checking the updated block of html dom 
                if (html_diff_dom != '') and (file_name in html_diff_dom): # Uploaded successfully using `send_keys`.
                    done_event.set() # Indicate success
                    return True
                # If not uploaded, attempt to trigger the file dialog again on this new element and upload through the dialog
                else:
                    print('Difference not detected. Trying dialog')
                    form_interactor.FormInteractorUtils.click(element) # Attempt upload through 'dialog'
                    time.sleep(1.5)
                    target_dialog = detect_dialog_window(form_interactor) # Check if the dialog window was opened
                    if target_dialog: # Connect and upload file
                        if upload_file_via_dialog(target_dialog, file_path):
                            done_event.set() # Indicate success
                            return True
            
            ''' 
            Final Fallback 
            '''
            close_file_dialog(form_interactor) # Close if duplicate dialog is open (optional)
            done_event.set() # Indicate failure
            return False

    except Exception as e:
        print(f"[!] Exception during upload: {e}")
        done_event.set()
        return False

def queue_file_upload(form_interactor, element_or_xpath, file_path):
    """
    Public interface to enqueue and perform upload in serialized order.
    Blocks the calling thread until its upload is complete.
    """
    done_event = threading.Event()
    upload_queue.put((form_interactor, element_or_xpath, file_path, done_event))

    while True:
        try:
            current = upload_queue.queue[0]
        except IndexError:
            time.sleep(0.1)
            continue

        if current[0] == form_interactor:
            upload_queue.get()
            process_file_upload(*current)
            break
        else:
            time.sleep(0.1)  # Wait until it's our turn

    done_event.wait()
