"""
google_sheets.py
================
Google Sheets export integration for the finance sync pipeline.

This module keeps the Google Sheets update logic isolated so the main pipeline
can call one function to refresh the sheet from the current transaction data.
"""

import logging
from typing import Iterable, List, Optional

from ..core.config import GOOGLE_SHEETS_CREDENTIALS_PATH, GOOGLE_SHEETS_SPREADSHEET_NAME, GOOGLE_SHEETS_WORKSHEET_NAME
from .categorizer import format_category_for_display, resolve_category
from .database import get_all_transactions

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SHEET_HEADERS = ['Date', 'Account', 'Description', 'Category', 'Amount']


def build_sheet_rows(transactions: Iterable[dict]) -> List[List[object]]:
    """Build rows in the exact shape expected by the Google Sheet table.
    
    Excluded transactions are filtered out before export to avoid double-counting
    internal passthroughs (e.g., credit card payments, Bilt Housing transfers).
    """
    rows: List[List[object]] = [SHEET_HEADERS]
    for transaction in transactions:
        # Skip excluded transactions
        if transaction.get('excluded'):
            continue
        rows.append([
            transaction.get('date', ''),
            transaction.get('account', ''),
            transaction.get('merchant') or transaction.get('description', ''),
            format_category_for_display(resolve_category(transaction)) or 'Uncategorized',
            transaction.get('amount', ''),
        ])
    return rows


def _get_client():
    """Authenticate with Google Sheets using the service account JSON file."""
    if gspread is None or Credentials is None:
        raise RuntimeError('gspread and google-auth are required for Google Sheets export')

    credentials_path = GOOGLE_SHEETS_CREDENTIALS_PATH
    if not credentials_path.exists():
        raise FileNotFoundError(f'Google credentials file not found: {credentials_path}')

    scope = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive',
    ]
    creds = Credentials.from_service_account_file(str(credentials_path), scopes=scope)
    return gspread.authorize(creds)


def write_rows_to_sheet(worksheet, rows: List[List[object]]) -> None:
    """Replace the worksheet contents with the provided rows."""
    worksheet.clear()
    worksheet.update('A1', rows)


def update_google_sheet(transactions: Optional[Iterable[dict]] = None, worksheet_name: Optional[str] = None) -> int:
    """Refresh the configured Google Sheet with the current transaction rows."""
    if transactions is None:
        transactions = get_all_transactions()

    rows = build_sheet_rows(transactions)

    client = _get_client()
    spreadsheet = client.open(GOOGLE_SHEETS_SPREADSHEET_NAME)
    worksheet = spreadsheet.worksheet(worksheet_name or GOOGLE_SHEETS_WORKSHEET_NAME)
    write_rows_to_sheet(worksheet, rows)

    logger.info(
        f"Updated Google Sheet '{GOOGLE_SHEETS_SPREADSHEET_NAME}' worksheet '{worksheet_name or GOOGLE_SHEETS_WORKSHEET_NAME}' with {len(rows) - 1} row(s)."
    )
    return len(rows) - 1
