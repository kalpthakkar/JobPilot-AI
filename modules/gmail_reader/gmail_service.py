# modules/gmail_reader/gmail_service.py
import os
import json
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from filelock import FileLock  # Importing the FileLock class
from google.auth.exceptions import RefreshError

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def get_gmail_service(credentials_file: str, token_file: str = 'token.json', enable_logging: bool = False, headless: bool = False):
    """
    Returns an authenticated Gmail service client.
    
    Args:
        credentials_file (str): Path to OAuth client secret JSON file.
        token_file (str): Path to store or retrieve the token.
        enable_logging (bool): Whether to print debug messages.
        headless (bool): Use console-based flow instead of opening a browser.
    
    Returns:
        googleapiclient.discovery.Resource: Gmail API service.
    """
    creds = None

    # Check if token file exists and load credentials
    if Path(token_file).exists():
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    try:
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request()) # Refresh the token if it expired
                # Save the refreshed token back to file with file lock
                with open(token_file, 'w') as token:
                    token.write(creds.to_json())
            else: # Start the OAuth flow if the token is not valid or expired
                if enable_logging:
                    print("🔐 Starting Gmail authentication flow...")
                flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
                creds = flow.run_local_server(port=0)
                # Save the new token
                with open(token_file, 'w') as token:
                    token.write(creds.to_json())

    except RefreshError as e:
        if enable_logging:
            print("⚠️ Google token expired or revoked. Removing token and retrying authentication...")
        # Remove invalid token and retry auth from scratch
        if Path(token_file).exists():
            os.remove(token_file)

        # Retry authentication flow after token removal
        flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
        creds = flow.run_local_server(port=0)

        # Save the refreshed credentials
        with open(token_file, 'w') as token:
            token.write(creds.to_json())

    if enable_logging:
        print("✅ Gmail service authenticated.")
    return build('gmail', 'v1', credentials=creds)