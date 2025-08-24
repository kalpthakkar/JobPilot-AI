# modules/email_reader/__init__.py
'''
gmail_reader/
├── __init__.py
├── otp_fetcher.py         👈 Main entry point (contains OTPFetcher)
├── gmail_service.py       (auth logic)
'''

from .otp_fetcher import OTPFetcher