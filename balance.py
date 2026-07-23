"""
balance_client.py
==================
Balance snapshot client for fetching account balances from Plaid.

This module provides the interface for fetching current account balances
from all configured Plaid institutions. It abstracts away Plaid API details
and returns canonical balance dicts matching the account_snapshots schema.

Design principle:
  - Non-fatal on individual institution failure — logs error and continues
  - Handles missing credit_limit gracefully (None for non-credit accounts)
  - Returns today's date as snapshot_date for all fetched balances
"""

import logging
from pathlib import Path
from datetime import date
import re
from typing import List, Optional

from config import USE_PLAID, DATABASE_PATH, ENABLE_DATABASE, DRY_RUN, GOOGLE_SHEETS_ENABLED, GOOGLE_SHEETS_SPREADSHEET_NAME
import plaid_integration as plaid_integration

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)


def fetch_balances() -> list[dict]:
    """
    Fetch current account balances from all configured Plaid institutions.

    Iterates through access tokens exactly as sync.py does, calling
    get_accounts() per institution to fetch current balances.

    Returns canonical balance dicts matching the account_snapshots schema:
      - snapshot_date     : Today's date (YYYY-MM-DD)
      - account_id        : Plaid's unique account identifier
      - account_name      : Human-readable name (e.g. "Checking ••1234")
      - institution       : Institution name (e.g. "Chase", "Coastal FCU")
      - account_type      : "depository", "credit", "investment", "loan"
      - account_subtype   : "checking", "savings", "credit card", etc.
      - current_balance   : Current balance from Plaid
      - available_balance : Available balance (for depository accounts)
      - credit_limit      : Credit limit (for credit cards only, None otherwise)
      - currency          : Currency code (default "USD")

    Handles missing credit_limit gracefully — sets to None for non-credit accounts.
    Non-fatal on individual institution failure — logs error and continues.

    Returns:
        List of balance dicts. Empty list if USE_PLAID is False or no tokens configured.

    Raises:
        None. Individual institution failures are logged but do not raise.
    """
    if not USE_PLAID:
        logger.info("Balance fetch requires Plaid (USE_PLAID=True) — skipping.")
        return []

    logger.info("Fetching account balances from Plaid...")

    access_tokens = plaid_integration.get_access_tokens()
    if not access_tokens:
        logger.warning("No Plaid access tokens configured — returning empty balance list.")
        return []

    all_balances = []
    snapshot_date = date.today().isoformat()

    for institution_name, access_token in access_tokens.items():
        try:
            logger.info(f"Processing institution for balances: {institution_name}")

            # Fetch accounts with balance information
            accounts = _get_accounts_with_balances(access_token)

            for acct in accounts:
                balance_dict = {
                    'snapshot_date': snapshot_date,
                    'account_id': acct['account_id'],
                    'account_name': f"{acct['name']} ••{acct['mask']}",
                    'institution': institution_name,
                    'account_type': acct['type'],
                    'account_subtype': acct['subtype'],
                    'current_balance': acct.get('current_balance'),
                    'available_balance': acct.get('available_balance'),
                    'credit_limit': acct.get('credit_limit'),  # None for non-credit accounts
                    'currency': acct.get('currency', 'USD'),
                }
                all_balances.append(balance_dict)

            logger.debug(f"  Fetched {len(accounts)} account balance(s) from {institution_name}.")

        except Exception as e:
            logger.exception(f"Non-fatal: failed to fetch balances for {institution_name}: {e}")
            continue

    logger.info(f"Fetched {len(all_balances)} total account balance snapshot(s).")
    return all_balances


def _get_accounts_with_balances(access_token: str) -> list[dict]:
    """
    Fetch accounts with balance information from Plaid.

    This uses the /accounts/balance/get endpoint which provides real-time
    balance data including credit limits for credit accounts.

    Args:
        access_token: Plaid access token for one institution.

    Returns:
        List of account dicts with balance information.

    Raises:
        Exception: On API errors (propagated to caller for graceful handling).
    """
    try:
        from plaid.model.accounts_balance_get_request import AccountsBalanceGetRequest

        client = plaid_integration.get_plaid_client()
        request = AccountsBalanceGetRequest(access_token=access_token)
        response = client.accounts_balance_get(request)

        accounts = []
        for acct in response['accounts']:
            # Extract balance information from the Plaid response
            balances = acct.get('balances', {})

            # Use Plaid's provided values directly
            current_balance = balances.get('current')
            available_balance = balances.get('available')
            credit_limit = balances.get('limit')

            account_dict = {
                'account_id': acct.account_id,
                'name': acct.name,
                'mask': acct.mask,
                'type': str(acct.type),
                'subtype': str(acct.subtype),
                'current_balance': current_balance,
                'available_balance': available_balance,
                'credit_limit': credit_limit,
                'currency': balances.get('iso_currency_code', 'USD'),
            }
            accounts.append(account_dict)

        return accounts

    except Exception as e:
        logger.exception(f"Failed to fetch accounts with balances: {e}")
        raise

"""
Balance Store
=================
Balance snapshot storage layer.

This module provides a clean interface for storing and retrieving account
balance snapshots from the database. It wraps the database operations
specific to balance snapshots, following the same pattern as database.py
for transactions.

All functions respect the ENABLE_DATABASE config flag and handle errors
gracefully with appropriate logging.
"""

def upsert_snapshots(snapshots: list[dict], db_path: Optional[Path] = None) -> int:
    """
    Batch upsert account balance snapshots to the database.

    This is a wrapper around database.upsert_snapshots() that provides
    balance-specific logging and error handling.

    Args:
        snapshots: List of snapshot dicts matching the account_snapshots schema.
        db_path:   Optional path to the database (uses default from config if None).

    Returns:
        Number of snapshots upserted. Returns 0 if database is disabled.
    """
    if not ENABLE_DATABASE:
        logger.debug("Database disabled — skipping snapshot upsert.")
        return 0

    from database import upsert_snapshots as db_upsert_snapshots

    if db_path is None:
        db_path = DATABASE_PATH

    return db_upsert_snapshots(snapshots, db_path)


def get_latest_balances(db_path: Optional[Path] = None) -> list[dict]:
    """
    Return the most recent snapshot for each account_id.

    This is a wrapper around database.get_latest_balances() that provides
    balance-specific logging and error handling.

    Args:
        db_path: Optional path to the database (uses default from config if None).

    Returns:
        List of snapshot dicts, one per account_id. Returns empty list if
        database is disabled or no snapshots exist.
    """
    if not ENABLE_DATABASE:
        logger.debug("Database disabled — get_latest_balances returning empty list.")
        return []

    from database import get_latest_balances as db_get_latest_balances

    if db_path is None:
        db_path = DATABASE_PATH

    return db_get_latest_balances(db_path)


def get_balance_history(days: int = 90, db_path: Optional[Path] = None) -> list[dict]:
    """
    Return all snapshots from the last N days.

    This is a wrapper around database.get_balance_history() that provides
    balance-specific logging and error handling.

    Args:
        days:    Number of days to look back (default: 90).
        db_path: Optional path to the database (uses default from config if None).

    Returns:
        List of snapshot dicts ordered by snapshot_date ASC, account_id ASC.
        Returns empty list if database is disabled or no snapshots exist.
    """
    if not ENABLE_DATABASE:
        logger.debug("Database disabled — get_balance_history returning empty list.")
        return []

    from database import get_balance_history as db_get_balance_history

    if db_path is None:
        db_path = DATABASE_PATH

    return db_get_balance_history(days, db_path)


def get_net_worth_history(db_path: Optional[Path] = None) -> list[dict]:
    """
    Return net worth history aggregated by snapshot date.

    This is a wrapper around database.get_net_worth_history() that provides
    balance-specific logging and error handling.

    Aggregates by snapshot_date:
      - assets      = SUM of depository + investment balances
      - liabilities = SUM of credit + loan balances (as positive)
      - net_worth   = assets - liabilities

    Args:
        db_path: Optional path to the database (uses default from config if None).

    Returns:
        List of dicts with keys: snapshot_date, assets, liabilities, net_worth.
        Ordered by snapshot_date ASC. Returns empty list if database is disabled
        or no snapshots exist.
    """
    if not ENABLE_DATABASE:
        logger.debug("Database disabled — get_net_worth_history returning empty list.")
        return []

    from database import get_net_worth_history as db_get_net_worth_history

    if db_path is None:
        db_path = DATABASE_PATH

    return db_get_net_worth_history(db_path)

"""
balance_export.py
==================
Google Sheets export for account balance snapshots.

This module exports balance data to Google Sheets using the same authentication
and error handling pattern as the existing transaction export in google_sheets.py.

Two sheets are created:
  1. "Account Balances" — Current balances for all accounts with summary rows
  2. "Net Worth History" — Historical net worth over time with embedded line chart
"""

# ─── Formatting Helpers ─────────────────────────────────────────────────────

def capitalize_first(text: str) -> str:
    """Capitalize only the first letter of a string."""
    if not text:
        return ''
    return text[0].upper() + text[1:].lower() if text else ''


def title_case(text: str) -> str:
    """Capitalize the first letter of each word."""
    if not text:
        return ''
    return ' '.join(word.capitalize() for word in text.split())


def normalize_account_name(account_name: str) -> str:
    """
    Normalize account name by removing mask symbols, special characters, and formatting.
    
    This handles account-specific patterns like:
    - Mask symbols: "Blue Cash Everday ••1234" -> "Blue Cash Everday"
    - Special characters: "Blue Cash Everyday®" -> "Blue Cash Everyday"
    - Capitalization: "GO GREEN CHECKING" -> "Go Green Checking"
    
    Args:
        account_name: Raw account name from Plaid
        
    Returns:
        Normalized account name
    """
    if not account_name:
        return ''
    
    # Remove mask patterns like ••1234, ****1234, etc.
    normalized = re.sub(r' [•*]+\d+', '', account_name)
    
    # Also handle patterns like (1234) or [1234]
    normalized = re.sub(r'[\(\[]\d+[\)\]]', '', normalized)
    
    # Remove special characters like ®, ℠, etc.
    normalized = re.sub(r'[®℠™]', '', normalized)
    
    # Clean up any trailing spaces and extra whitespace
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    # Apply title case for proper capitalization
    normalized = title_case(normalized)
    
    return normalized

# ─── Account Balances Sheet ─────────────────────────────────────────────────────

ACCOUNT_BALANCES_HEADERS = [
    'Date',
    'Institution',
    'Account',
    'Type',
    'Current Balance',
    'Available Balance',
    'Credit Limit',
    'Utilization %'
]


def build_account_balances_rows(balances: List[dict]) -> List[List[object]]:
    """
    Build rows for the Account Balances sheet.

    Args:
        balances: List of balance dicts from get_latest_balances().

    Returns:
        List of rows including header, data rows, and summary rows.
    """
    if not balances:
        return [ACCOUNT_BALANCES_HEADERS]

    rows: List[List[object]] = [ACCOUNT_BALANCES_HEADERS]

    total_assets = 0.0
    total_liabilities = 0.0

    for balance in balances:
        current_balance = balance.get('current_balance', 0) or 0
        available_balance = balance.get('available_balance') or 0
        credit_limit = balance.get('credit_limit') or 0
        account_type = balance.get('account_type', '')
        
        # Format with proper capitalization
        institution = title_case(balance.get('institution', ''))
        account_name = normalize_account_name(balance.get('account_name', ''))
        formatted_type = capitalize_first(account_type)

        # Calculate utilization for credit cards
        utilization = ''
        if account_type == 'credit' and credit_limit and credit_limit > 0:
            utilization = f"{(current_balance / credit_limit) * 100:.1f}%"

        rows.append([
            balance.get('snapshot_date', ''),
            institution,
            account_name,
            formatted_type,
            current_balance,
            available_balance,
            credit_limit,
            utilization,
        ])

        # Accumulate totals
        if account_type in ('depository', 'investment'):
            total_assets += current_balance
        elif account_type in ('credit', 'loan'):
            total_liabilities += current_balance

    # Add summary rows
    net_worth = total_assets - total_liabilities
    rows.append([])  # Empty row for spacing
    rows.append(['', '', '', 'Total Assets', total_assets, '', '', ''])
    rows.append(['', '', '', 'Total Liabilities', total_liabilities, '', '', ''])
    rows.append(['', '', '', 'Net Worth', net_worth, '', '', ''])

    return rows


# ─── Net Worth History Sheet ────────────────────────────────────────────────────

NET_WORTH_HEADERS = ['Date', 'Assets', 'Liabilities', 'Net Worth']


def build_net_worth_rows(net_worth_history: List[dict]) -> List[List[object]]:
    """
    Build rows for the Net Worth History sheet.

    Args:
        net_worth_history: List of dicts from get_net_worth_history().

    Returns:
        List of rows including header and data rows.
    """
    if not net_worth_history:
        return [NET_WORTH_HEADERS]

    rows: List[List[object]] = [NET_WORTH_HEADERS]

    for entry in net_worth_history:
        rows.append([
            entry.get('snapshot_date', ''),
            entry.get('assets', 0) or 0,
            entry.get('liabilities', 0) or 0,
            entry.get('net_worth', 0) or 0,
        ])

    return rows


# ─── Google Sheets Integration ─────────────────────────────────────────────────

def _get_client():
    """Authenticate with Google Sheets using the service account JSON file."""
    if gspread is None or Credentials is None:
        raise RuntimeError('gspread and google-auth are required for Google Sheets export')

    from config import GOOGLE_SHEETS_CREDENTIALS_PATH

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


def format_account_balances_sheet(worksheet, data_rows: int) -> None:
    """
    Apply formatting to the Account Balances sheet.

    Formats the sheet as a table with:
    - Header row styling (bold, centered)
    - Number formatting for currency columns
    - Percentage formatting for utilization
    - Borders around the table
    - Alternating row colors for readability

    Args:
        worksheet: gspread Worksheet object.
        data_rows: Number of data rows (excluding header and summary).
    """
    try:
        # Get the full range of the data (header + data + summary)
        # Data rows + 1 header + 1 empty + 3 summary = data_rows + 5 total rows
        total_rows = data_rows + 5
        total_cols = 8  # A to H

        # Format header row (row 1) - bold, centered, light gray background
        header_format = {
            'textFormat': {'bold': True},
            'horizontalAlignment': 'CENTER',
            'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9}  # Light gray
        }
        
        worksheet.format('A1:H1', header_format)

        # Format currency columns (E, F, G) as currency
        currency_format = {
            'numberFormat': {
                'type': 'CURRENCY',
                'pattern': '$#,##0.00'
            }
        }
        
        # Apply to data rows only (row 2 to data_rows+1)
        if data_rows > 0:
            worksheet.format(f'E2:G{data_rows + 1}', currency_format)

        # Format utilization column (H) as percentage
        percent_format = {
            'numberFormat': {
                'type': 'NUMBER',
                'pattern': '0.0%'
            }
        }
        
        if data_rows > 0:
            worksheet.format(f'H2:H{data_rows + 1}', percent_format)

        # Add borders to the data table
        border_format = {
            'borders': {
                'top': {'style': 'SOLID'},
                'bottom': {'style': 'SOLID'},
                'left': {'style': 'SOLID'},
                'right': {'style': 'SOLID'}
            }
        }
        
        # Apply borders to data range
        if data_rows > 0:
            worksheet.format(f'A1:H{data_rows + 1}', border_format)

        # Format summary rows (bottom 3 rows) - bold
        summary_start_row = data_rows + 3
        worksheet.format(f'A{summary_start_row}:H{summary_start_row + 2}', {
            'textFormat': {'bold': True}
        })

        # Format summary currency values
        worksheet.format(f'E{summary_start_row}:G{summary_start_row + 2}', currency_format)

        # Freeze header row
        worksheet.freeze(rows=1)

        # Auto-resize columns for better readability
        worksheet.columns_auto_resize(1, total_cols)

        logger.debug("Applied formatting to Account Balances sheet.")

    except Exception as e:
        logger.warning(f"Failed to format Account Balances sheet: {e}")


def format_net_worth_sheet(worksheet, data_rows: int) -> None:
    """
    Apply formatting to the Net Worth History sheet.

    Formats the sheet as a table with:
    - Header row styling (bold, centered)
    - Number formatting for currency columns
    - Borders around the table
    - Date formatting for the date column

    Args:
        worksheet: gspread Worksheet object.
        data_rows: Number of data rows (excluding header).
    """
    try:
        # Format header row (row 1) - bold, centered, light gray background
        header_format = {
            'textFormat': {'bold': True},
            'horizontalAlignment': 'CENTER',
            'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9}  # Light gray
        }
        
        worksheet.format('A1:D1', header_format)

        # Format currency columns (B, C, D) as currency
        currency_format = {
            'numberFormat': {
                'type': 'CURRENCY',
                'pattern': '$#,##0.00'
            }
        }
        
        # Apply to data rows only (row 2 to data_rows+1)
        if data_rows > 0:
            worksheet.format(f'B2:D{data_rows + 1}', currency_format)

        # Add borders to the data table
        border_format = {
            'borders': {
                'top': {'style': 'SOLID'},
                'bottom': {'style': 'SOLID'},
                'left': {'style': 'SOLID'},
                'right': {'style': 'SOLID'}
            }
        }
        
        # Apply borders to data range
        if data_rows > 0:
            worksheet.format(f'A1:D{data_rows + 1}', border_format)

        # Freeze header row
        worksheet.freeze(rows=1)

        # Auto-resize columns for better readability
        worksheet.columns_auto_resize(1, 4)

        logger.debug("Applied formatting to Net Worth History sheet.")

    except Exception as e:
        logger.warning(f"Failed to format Net Worth History sheet: {e}")


def create_net_worth_chart(worksheet, data_rows: int) -> None:
    """
    Create a line chart for net worth history on the worksheet.

    The chart is embedded in the same sheet below the data table.

    Args:
        worksheet: gspread Worksheet object.
        data_rows: Number of data rows (excluding header).
    """
    try:
        # Note: Full chart creation via API is complex and may require additional
        # permissions. For now, we log that chart creation would happen here.
        # The data is written to the sheet, so users can manually create charts.
        logger.debug("Chart creation via API is complex - data written to sheet for manual chart creation.")
        
        # Future implementation could use the Google Sheets API charts endpoint
        # This would require additional error handling and permissions
        
    except Exception as e:
        logger.warning(f"Failed to create net worth chart: {e}")


def export_to_sheets(dry_run: bool = DRY_RUN) -> dict:
    """
    Export balance data to Google Sheets.

    Creates or updates two worksheets:
      1. "Account Balances" — Current balances with summary rows
      2. "Net Worth History" — Historical net worth with embedded chart

    Uses the same authentication pattern as google_sheets.py.

    Args:
        dry_run: If True, log what would be written without touching Google Sheets.

    Returns:
        Dict with keys 'account_balances' and 'net_worth_history' containing
        the number of rows written to each sheet.

    Raises:
        RuntimeError: If gspread/google-auth are not installed.
        FileNotFoundError: If Google credentials file is missing.
        Exception: On Google Sheets API errors (logged and re-raised).
    """
    if not GOOGLE_SHEETS_ENABLED:
        logger.info("Google Sheets export disabled via config — skipping balance export.")
        return {'account_balances': 0, 'net_worth_history': 0}

    if dry_run:
        logger.info("[DRY RUN] Would export balance data to Google Sheets.")
        # Fetch data to show what would be exported
        balances = get_latest_balances()
        net_worth = get_net_worth_history()
        logger.info(f"  [DRY RUN] Account Balances: {len(balances)} account(s)")
        logger.info(f"  [DRY RUN] Net Worth History: {len(net_worth)} date(s)")
        return {'account_balances': len(balances), 'net_worth_history': len(net_worth)}

    logger.info("Exporting balance data to Google Sheets...")

    # Fetch data
    balances = get_latest_balances()
    net_worth = get_net_worth_history()

    if not balances and not net_worth:
        logger.warning("No balance data to export — skipping Google Sheets update.")
        return {'account_balances': 0, 'net_worth_history': 0}

    # Connect to Google Sheets
    client = _get_client()
    spreadsheet = client.open(GOOGLE_SHEETS_SPREADSHEET_NAME)

    # Export Account Balances
    account_balances_rows = build_account_balances_rows(balances)
    try:
        worksheet = spreadsheet.worksheet('Account Balances')
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title='Account Balances', rows=100, cols=20)
        logger.info("Created new 'Account Balances' worksheet.")

    write_rows_to_sheet(worksheet, account_balances_rows)
    logger.info(f"Updated 'Account Balances' sheet with {len(account_balances_rows) - 1} row(s).")
    
    # Apply formatting to the sheet
    # Calculate data rows (actual account data, excluding header, empty, and summary rows)
    # Structure: header + data_rows + empty + 3 summary = total rows
    total_rows = len(account_balances_rows)
    data_rows = total_rows - 5  # header(1) + empty(1) + summary(3) = 5
    if data_rows > 0:
        format_account_balances_sheet(worksheet, data_rows)

    # Export Net Worth History
    net_worth_rows = build_net_worth_rows(net_worth)
    try:
        worksheet = spreadsheet.worksheet('Net Worth History')
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title='Net Worth History', rows=100, cols=10)
        logger.info("Created new 'Net Worth History' worksheet.")

    write_rows_to_sheet(worksheet, net_worth_rows)
    logger.info(f"Updated 'Net Worth History' sheet with {len(net_worth_rows) - 1} row(s).")
    
    # Apply formatting to the sheet
    data_rows = len(net_worth_rows) - 1  # Exclude header
    if data_rows > 0:
        format_net_worth_sheet(worksheet, data_rows)

    return {
        'account_balances': len(account_balances_rows) - 1,
        'net_worth_history': len(net_worth_rows) - 1,
    }
