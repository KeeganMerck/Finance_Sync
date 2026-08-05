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

import re
import logging
from pathlib import Path
from datetime import date
from typing import List, Optional

from ..core.config import USE_PLAID, DATABASE_PATH, ENABLE_DATABASE, DRY_RUN, GOOGLE_SHEETS_ENABLED, GOOGLE_SHEETS_SPREADSHEET_NAME, GOOGLE_SHEETS_CREDENTIALS_PATH
from .database import upsert_snapshots as db_upsert_snapshots, get_latest_balances as db_get_latest_balances, get_balance_history as db_get_balance_history, get_net_worth_history as db_get_net_worth_history, get_latest_manual_snapshots as db_get_latest_manual_snapshots, upsert_investment_holdings as db_upsert_investment_holdings
from ..api import plaid_integration

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

    plaid_profiles = plaid_integration.get_plaid_profiles()
    if not plaid_profiles:
        logger.warning("No Plaid profiles configured - returning empty balance list.")
        return []

    all_balances = []
    snapshot_date = date.today().isoformat()

    for profile in plaid_profiles:
        access_tokens = plaid_integration.get_access_tokens(profile)
        if not access_tokens:
            logger.warning(
                f"No Plaid access tokens configured for profile '{profile.name}' "
                f"- expected {profile.token_prefix}*."
            )
            continue

        for institution_name, access_token in access_tokens.items():
            try:
                logger.info(
                    f"Processing institution for balances: "
                    f"{profile.name}/{institution_name}"
                )

                accounts = _get_accounts_with_balances(access_token, profile)

                for acct in accounts:
                    balance_dict = {
                        'snapshot_date': snapshot_date,
                        'account_id': acct['account_id'],
                        'account_name': f"{acct['name']} --{acct['mask']}",
                        'institution': institution_name,
                        'account_type': acct['type'],
                        'account_subtype': acct['subtype'],
                        'current_balance': acct.get('current_balance'),
                        'available_balance': acct.get('available_balance'),
                        'credit_limit': acct.get('credit_limit'),
                        'currency': acct.get('currency', 'USD'),
                    }
                    all_balances.append(balance_dict)

                logger.debug(
                    f"  Fetched {len(accounts)} account balance(s) "
                    f"from {profile.name}/{institution_name}."
                )

            except Exception as e:
                logger.exception(
                    f"Non-fatal: failed to fetch balances for "
                    f"{profile.name}/{institution_name}: {e}"
                )
                continue

    logger.info(f"Fetched {len(all_balances)} total account balance snapshot(s).")
    return all_balances


def fetch_manual_balances() -> list[dict]:
    """
    Read the most recent manual entry for each account in manual_account_snapshots
    and return them stamped with today's date, ready to upsert into account_snapshots.

    This makes manually-entered accounts (car loans, home equity, crypto wallets, etc.)
    flow through the same balance storage and Google Sheets export pipeline as
    Plaid-linked accounts — no special-casing needed downstream.

    Behaviour:
      - For each unique account_id in manual_account_snapshots, the row with the
        highest snapshot_date is selected (represents the most recently entered value).
      - snapshot_date is overwritten with today's date before returning, so the
        account_snapshots table always records when the value was last observed
        by the pipeline (consistent with how Plaid balances are timestamped).
      - All other fields (account_name, institution, type, balances, currency)
        are carried over unchanged from the manual row.

    Returns:
        List of snapshot dicts ready for upsert_snapshots(). Empty if the manual
        table has no rows or the database is disabled.
    """
    raw = db_get_latest_manual_snapshots()
    if not raw:
        logger.debug("No manual account snapshots found — skipping.")
        return []

    today = date.today().isoformat()
    stamped = []
    for row in raw:
        snapshot = dict(row)
        snapshot['snapshot_date'] = today
        stamped.append(snapshot)

    logger.info(
        f"Prepared {len(stamped)} manual account snapshot(s) for today ({today})."
    )
    return stamped


def fetch_investments() -> list[dict]:
    """
    Fetch detailed investment holdings from all investment/brokerage accounts.

    Iterates through Plaid profiles and institutions, calling get_investments()
    for accounts that are investment or brokerage type.

    Returns:
        List of investment holding dicts matching the investment_holdings schema:
          - holding_id        : Unique identifier (account_id + security_id + date)
          - account_id        : Plaid's unique account identifier
          - account_name      : Human-readable account name
          - institution       : Institution name (e.g., "Fidelity", "Robinhood")
          - security_id       : Plaid's security identifier
          - symbol            : Stock ticker symbol (e.g., "AAPL", "VTI")
          - name              : Security name (e.g., "Apple Inc.", "Vanguard Total Stock Market ETF")
          - quantity          : Number of shares/units held
          - current_price     : Current market price per share
          - current_value     : Total current value (quantity × price)
          - cost_basis        : Original purchase cost
          - purchase_date     : Date when position was opened
          - last_updated      : Timestamp of last fetch
          - snapshot_date     : Date when this snapshot was taken
    """
    if not USE_PLAID:
        logger.info("Plaid disabled via config — skipping investment fetch.")
        return []

    from ..api import plaid_integration

    profiles = plaid_integration.get_plaid_profiles()
    if not profiles:
        logger.warning("No Plaid profiles configured. Returning empty investments.")
        return []

    all_holdings = []

    for profile in profiles:
        try:
            institutions = profile.institutions
            if not institutions:
                logger.debug(f"{profile.name}: no institutions found, skipping investments fetch")
                continue
                
            for institution_name, access_token in institutions.items():
                try:
                    # First get accounts to filter for investment/brokerage types
                    accounts = _get_accounts_with_balances(access_token, profile)
                    investment_accounts = [a for a in accounts if a['type'] in ['investment', 'brokerage']]

                    if investment_accounts:
                        # Fetch investments for this institution
                        institution_holdings = plaid_integration.get_investments(access_token, profile)
                        all_holdings.extend(institution_holdings)

                        logger.info(
                            f"{profile.name}/{institution_name}: fetched {len(institution_holdings)} holding(s) "
                            f"from {len(investment_accounts)} investment account(s)"
                        )
                    else:
                        logger.debug(
                            f"{profile.name}/{institution_name}: no investment accounts found, skipping investments fetch"
                        )

                except Exception as e:
                    logger.warning(
                        f"{profile.name}/{institution_name}: failed to fetch investments: {e}"
                    )
                    continue
        except Exception as e:
            logger.warning(
                f"{profile.name}: failed to process institutions: {e}"
            )
            continue

    logger.info(f"Fetched {len(all_holdings)} total investment holding(s) from Plaid.")
    return all_holdings


def upsert_investment_holdings(holdings: list[dict]) -> dict:
    """
    Upsert investment holdings to the database using the database module function.

    This function wraps the database module's upsert_investment_holdings function
    to maintain consistency with other balance-related database operations.

    Args:
        holdings: List of investment holding dicts from fetch_investments()

    Returns:
        Dictionary with 'written', 'unchanged', 'total' counts from the database module.
    """
    if not ENABLE_DATABASE:
        logger.debug("Database disabled — skipping investment holdings upsert.")
        return {"written": 0, "unchanged": 0, "total": 0}

    if not holdings:
        logger.debug("No investment holdings to upsert.")
        return {"written": 0, "unchanged": 0, "total": 0}

    try:
        result = db_upsert_investment_holdings(holdings)
        logger.info(f"Upserted {result['written']} investment holding(s) to SQLite.")
        return result
    except Exception as e:
        logger.exception(f"Failed to upsert investment holdings: {e}")
        return {"written": 0, "unchanged": 0, "total": len(holdings)}


def _get_accounts_with_balances(access_token: str, profile=None) -> list[dict]:
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

        client = plaid_integration.get_plaid_client(profile)
        request = AccountsBalanceGetRequest(access_token=access_token)
        response = client.accounts_balance_get(request)

        accounts = []
        for acct in response['accounts']:
            balances = acct.get('balances', {})

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

    return {
        'account_balances': len(account_balances_rows) - 1,
        'net_worth_history': len(net_worth_rows) - 1,
    }
