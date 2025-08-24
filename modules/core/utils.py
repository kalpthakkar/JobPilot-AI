import logging
import re
from pathlib import Path
import json 
from typing import Dict, List, Any, Union, Optional, Literal, Iterable
from selenium.webdriver.remote.webelement import WebElement # type: ignore

class Utils:

    def __init__(self):
        pass

    def setup_logging(self):
        """Set up logging for the application."""
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

    def log_error(self, message):
        """Log an error message."""
        logging.error(message)

    def get_project_root_path(self) -> Path:
        """
        Returns the absolute path of the parent directory (the project root).
        This function works regardless of where it's called from.
        """
        # Get the current file's absolute path (this will be utils.py's path if called from there)
        current_path = Path(__file__).resolve()

        # Navigate two levels up to get the project root
        project_root = current_path.parents[1]

        return project_root

    def read_json_file(self, file_path) -> Optional[dict]:
        try:
            # Open the file in read mode
            with open(file_path, 'r') as file:
                # Load the JSON data into a Python dictionary
                data = json.load(file)
                return data
        except FileNotFoundError:
            print(f"Error: The file at '{file_path}' was not found.")
        except json.JSONDecodeError:
            print(f"Error: Failed to decode JSON. The file at '{file_path}' may not be valid JSON.")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")

        return None
    
    def save_json_to_file(self, data, file_path):
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
