# modules/gmail_reader/otp_fetcher.py
import re
from typing import List, Dict, Optional
from .gmail_service import get_gmail_service
from typing import Optional, TypedDict, Union
from bs4 import BeautifulSoup, Tag
import re
import base64
import importlib.util
from datetime import datetime, timezone
from filelock import FileLock  # Importing FileLock to handle concurrency

class EmailData(TypedDict):
    From: str
    Subject: str
    Time: int                  # Epoch timestamp in seconds
    TimeReadable: str          # ISO 8601 formatted string (e.g. "2025-05-16T21:47:00Z")
    Body: str
    OTP: Optional[str]
    URL: List[str]

class OTPFetcher:

    def __init__(
        self,
        credentials_file: str = 'credentials.json',
        token_file: str = 'token.json',
        enable_logging: bool = False
    ):
        self.enable_logging = enable_logging

        # Locking token file during initialization to ensure only one process uses it at a time
        with FileLock(f"{token_file}.lock"):  # Lock the token file
            self.service = get_gmail_service(
                credentials_file=credentials_file,
                token_file=token_file,
                enable_logging=enable_logging,
                headless=False  # Set False in local development
            )

    def fetch_recent_emails(self, top_n: int = 5, query: str = "") -> List[EmailData]:
        """
        Fetches the most recent emails from the user's Gmail inbox using the Gmail API.

        Args:
            top_n (int): Number of recent emails to fetch (default is 5).
            query (str): Optional search query to filter emails using Gmail's search syntax.

        Returns:
            List[EmailData]: A list of dictionaries, each representing an email with the following structure:
                {
                    "From": str,            # Sender's email address
                    "Subject": str,         # Email subject line
                    "Time": str,            # Time in epoch format
                    "TimeRedable": str,     # Human Readable Time (ISO format)
                    "Body": str,            # Extracted and cleaned email body (plain text)
                    "OTP": Optional[str],   # Extracted OTP if found, else None
                    "URL": List[str]        # List of activation URLs
                }
        """

        try:
            # Step 1: Call Gmail API to list messages
            results = self.service.users().messages().list(
                userId='me',
                maxResults=top_n,
                q=query
            ).execute()

            messages = results.get('messages', [])
            email_data = []

            # Step 2: Iterate over each message and fetch full content
            for msg in messages:
                msg_id = msg['id']
                full_msg = self.service.users().messages().get(userId='me', id=msg_id, format='full').execute()

                # Step 3: Extract headers into a dictionary
                headers = {h['name']: h['value'] for h in full_msg['payload'].get('headers', [])}

                # Step 4: Extract relevant field information
                sender: str = headers.get("From", "Unknown Sender")
                subject: str = headers.get("Subject", "No Subject")
                snippet: str = full_msg.get("snippet", "")
                epoch_time: int = int(full_msg.get("internalDate", 0)) // 1000 # Extract timestamp in seconds
                readable_time = datetime.fromtimestamp(epoch_time, tz=timezone.utc).isoformat().replace("+00:00", "Z")
                body: Optional[str] = self._extract_body(full_msg) # Tries to extract HTML/plain content
                otp: Optional[str] = self._extract_otp(body or snippet) # Extract OTP from the cleaned body or snippet
                raw_html_body: Optional[str] = self._extract_raw_html_body(full_msg)
                activation_url: List[str] = self._extract_all_activation_urls(raw_html_body or body) # Extract Account Activation URL from raw html (not cleaned body since the URLs could be embedded as hyperlinks)
                
                # Step 5: Append structured email data to the result list
                email_data.append({
                    "From": sender,
                    "Subject": subject,
                    "Time": epoch_time,
                    "TimeReadable": readable_time,
                    "Body": body or snippet,
                    "OTP": otp,
                    "URL": activation_url or []
                })

            return email_data

        except Exception as e:
            if self.enable_logging:
                print(f"Error fetching emails: {e}")
            return []

    def was_received_recently(self, time_input: Union[int, str], max_age_minutes: int = 2) -> bool:
        """
        Checks whether a given email timestamp (epoch or ISO UTC string) was received within the last 'max_age_minutes'.

        Args:
            time_input (Union[int, str]): Epoch timestamp (int) or ISO UTC string (e.g. '2025-05-19T23:06:10Z').
            max_age_minutes (int): Time boundary in minutes (default: 2).

        Returns:
            bool: True if email was received within 'max_age_minutes', else False.
        """

        try:
            # Get current UTC time
            now = datetime.now(timezone.utc)

            # Parse input time
            if isinstance(time_input, int):  # Epoch timestamp
                received_time = datetime.fromtimestamp(time_input, tz=timezone.utc)
            elif isinstance(time_input, str):  # ISO string
                if time_input.endswith("Z"):
                    time_input = time_input.replace("Z", "+00:00")  # Convert 'Z' to proper offset
                received_time = datetime.fromisoformat(time_input)
            else:
                raise ValueError("Unsupported time_input format")

            # Compute time difference
            delta = now - received_time
            delta_minutes = delta.total_seconds() / 60

            return 0 <= delta_minutes <= max_age_minutes

        except Exception as e:
            print(f"⚠️ Error while checking timestamp: {e}")
            return False

    def _clean_text(self, text: str) -> str:
        """Normalize line endings, whitespace, and remove excess newlines."""
        
        # Normalize different newline formats (handle Windows, Mac, and Linux line endings)
        text = text.replace('\r\n', '\n').replace('\r', '\n')

        # Remove any newlines that occur right after other newlines
        text = re.sub(r'\n{2,}', '\n', text)  # Collapse multiple newlines into one

        # Strip leading and trailing whitespaces
        text = text.strip()

        # Normalize multiple spaces or tabs into one space
        text = re.sub(r'[ \t]+', ' ', text)

        # Additional stripping of extra spaces before or after newlines
        text = re.sub(r'\s*\n\s*', '\n', text)  # Remove extra spaces before or after newlines
        
        # Special case: Handle newlines before or after OTP-like patterns (like numeric codes)
        # Remove newlines around digits or passcodes
        text = re.sub(r'(\d+)\n', r'\1 ', text)  # Merge digits followed by a newline into a single space
        text = re.sub(r'\n(\d+)', r' \1', text)  # Merge newlines before digits into a single space

        return text

    def _html_to_text(self, html: str) -> str:
        """Converts HTML to readable plain text using the best available parser."""
        
        def get_best_available_parser() -> str:
            for parser in ['lxml', 'html5lib', 'html.parser']:
                if parser == 'html.parser' or importlib.util.find_spec(parser):
                    return parser
            return 'html.parser'

        best_parser = get_best_available_parser()
        soup = BeautifulSoup(html, best_parser)
        text = soup.get_text(separator=" ")
        return self._clean_text(text)

    def _extract_body(self, message: dict) -> Optional[str]:
        """Extracts and cleans text from email body (plain or HTML, including nested parts)."""
        
        def extract_from_parts(parts: list) -> Optional[str]:
            for part in parts:
                mime_type = part.get("mimeType", "")
                body_data = part.get("body", {}).get("data")
                nested_parts = part.get("parts")

                # Recurse into nested parts
                if nested_parts:
                    nested = extract_from_parts(nested_parts)
                    if nested:
                        return nested

                if body_data:
                    decoded = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="ignore")
                    if mime_type == "text/plain":
                        return self._clean_text(decoded)
                    elif mime_type == "text/html":
                        # Parse as HTML, which already calls _clean_text
                        return self._html_to_text(decoded)  # Cleaned by _html_to_text

            return None

        try:
            payload = message.get("payload", {})
            parts = payload.get("parts")
            if parts:
                return extract_from_parts(parts)

            # If no parts, check top-level body
            data = payload.get("body", {}).get("data")
            if data:
                decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                # Parse as HTML and clean the result (since _html_to_text already handles cleaning)
                return self._html_to_text(decoded)

        except Exception as e:
            print(f"Error extracting body: {e}")

        return None

    def _extract_raw_html_body(self, message: dict) -> Optional[str]:
        def extract_html_from_parts(parts: list) -> Optional[str]:
            for part in parts:
                mime_type = part.get("mimeType", "")
                body_data = part.get("body", {}).get("data")
                nested_parts = part.get("parts")

                if nested_parts:
                    result = extract_html_from_parts(nested_parts)
                    if result:
                        return result

                if mime_type == "text/html" and body_data:
                    return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="ignore")

            return None

        try:
            payload = message.get("payload", {})
            parts = payload.get("parts")
            if parts:
                return extract_html_from_parts(parts)

            data = payload.get("body", {}).get("data")
            if data and payload.get("mimeType") == "text/html":
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

        except Exception as e:
            print(f"Error extracting raw HTML body: {e}")

        return None

    def _extract_otp(self, body: str) -> Optional[str]:
        """Extracts the first numeric sequence that looks like an OTP (length ≥ 4)."""
        matches = re.findall(r"\b\d{4,10}\b", body)
        return matches[0] if matches else None

    def _extract_all_activation_urls(self, body: str) -> List[str]:
        """
        Extracts all activation/verification/setup URLs from an email body.

        Args:
            body (str): Email body as HTML or plain text.

        Returns:
            List[str]: A list of matched activation/verification URLs.
        """
        if not body:
            return []

        urls = set()

        # Parse HTML for anchor tags with href
        soup = BeautifulSoup(body, "html.parser")
        for a in soup.find_all("a", href=True):
            if isinstance(a, Tag):
                urls.add(a['href'])

        # Also extract from raw plain text using regex
        raw_links = re.findall(r'https?://[^\s"<>]+', body)
        urls.update(raw_links)

        # Filter for activation-like links
        activation_keywords = ['activate', 'verify', 'confirm', 'signup', 'register']
        relevant_links = [
            url for url in urls
            if any(kw in url.lower() for kw in activation_keywords)
        ]

        return sorted(relevant_links)

