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
from datetime import date

from config import USE_PLAID
import plaid_integration as plaid_integration

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