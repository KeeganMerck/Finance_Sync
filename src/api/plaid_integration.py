"""
plaid_client.py
===============
Plaid API client implementation.

This module provides the complete interface that sync.py calls when Plaid
integration is enabled. It abstracts away all Plaid SDK-specific code so that
downstream modules (categorizer, database, export, main) never directly depend
on the Plaid library.

Every Plaid API call is wrapped here for:
    - Consistent error handling and logging
    - Amount sign negation (Plaid positive → internal negative for debits)
    - Schema conversion (Plaid fields → canonical transaction schema)
    - Token and credential management

Plaid environments:
    'sandbox'     — Fake data for testing (use during development)
    'development' — Read-only real account access (up to 100 accounts)
    'production'  — Full production (requires business registration)

Reference: https://plaid.com/docs/
"""

import logging
import os
from datetime import date, datetime, timedelta
from typing import Optional

from ..core.config import PLAID_ENV, PLAID_CLIENT_ID, PLAID_SECRET

logger = logging.getLogger(__name__)


# ─── Client Initialization ────────────────────────────────────────────────────

def get_plaid_client():
    """
    Initialize and return an authenticated Plaid API client.

    Returns a configured client object ready to make API calls.
    Called once per sync run — the client is stateless so it does not
    need to be stored globally.

    Returns:
        plaid.api.plaid_api.PlaidApi instance

    Raises:
        ValueError: If required credentials are not configured.
    """

    # --- CHANGE THESE THREE IMPORT LINES ---
    from plaid.api import plaid_api
    from plaid.api_client import ApiClient          # <-- Note the change to api_client
    from plaid.configuration import Configuration   # <-- Note the change to configuration

    if not PLAID_CLIENT_ID or not PLAID_SECRET or not PLAID_ENV:
        raise ValueError(
            "Plaid credentials not configured. "
            "Set PLAID_CLIENT_ID, PLAID_SECRET, and PLAID_ENV in your .env file."
        )

    env_map = {
        'sandbox':     'https://sandbox.plaid.com',
        'development': 'https://development.plaid.com',
        'production':  'https://production.plaid.com',
    }

    if PLAID_ENV not in env_map:
        raise ValueError(
            f"Invalid PLAID_ENV '{PLAID_ENV}'. "
            "Must be one of: sandbox, development, production"
        )

    host = env_map[PLAID_ENV]
    # logger.info(f"Initializing Plaid client for environment: {PLAID_ENV} ({host})")

    configuration = Configuration(
        host=host,
        api_key={
            'clientId': PLAID_CLIENT_ID,
            'secret':   PLAID_SECRET,
        }
    )

    client = plaid_api.PlaidApi(ApiClient(configuration))
    logger.debug("Plaid client initialized successfully.")
    return client


# ─── Access Token Management ──────────────────────────────────────────────────

def get_access_tokens() -> dict[str, str]:
    """
    Return a mapping of institution name to Plaid access token.

    Access tokens are obtained once via the Plaid Link flow and then stored
    in environment variables with keys like PLAID_SANDBOX_TOKEN_CHASE, PLAID_PRODUCTION_TOKEN_AMEX.
    This function reads all such variables, strips the prefix, and returns a
    clean institution → token mapping.

    Returns:
        Dict mapping institution names to access tokens, e.g.:
        {
            'CHASE':      'access-sandbox-abc123...',
            'AMEX':       'access-sandbox-def456...',
            'COASTAL_FCU': 'access-sandbox-ghi789...',
        }
        Returns empty dict if no PLAID_{ENV}_TOKEN_ variables are found.

    Raises:
        None. Logs a warning if no tokens are configured but does not fail.
    """
    prefix = f'PLAID_{PLAID_ENV.upper()}_TOKEN_'
    tokens = {}

    for key, value in os.environ.items():
        if key.startswith(prefix) and value:
            institution_name = key[len(prefix):]
            tokens[institution_name] = value

    if not tokens:
        logger.warning(
            f"No access tokens found. "
            f"Environment variables matching '{prefix}*' are required. "
            f"Run link_setup.py to obtain tokens via Plaid Link."
        )

    logger.info(f"Loaded {len(tokens)} access token(s): {', '.join(tokens.keys()) if tokens else '(none)'}")
    return tokens


# ─── Account Fetching ─────────────────────────────────────────────────────────

def get_accounts(access_token: str) -> list[dict]:
    """
    Fetch all accounts associated with an access token.

    Returns a list of account dicts in a normalized format that the rest
    of the pipeline can consume without knowing Plaid field names.

    Args:
        access_token: Plaid access token for one institution.

    Returns:
        List of account dicts with keys:
            account_id   : Plaid's unique account identifier
            name         : Human-readable account name (e.g. "Plaid Checking")
            mask         : Last 4 digits of account number
            type         : "depository", "credit", "investment", etc.
            subtype      : "checking", "savings", "credit card", etc.

    Raises:
        plaid.exceptions.ApiException: On API errors (logged and re-raised).
    """
    try:
        from plaid.model.accounts_get_request import AccountsGetRequest

        client = get_plaid_client()
        request = AccountsGetRequest(access_token=access_token)
        response = client.accounts_get(request)

        accounts = [
            {
                'account_id': acct.account_id,
                'name': acct.name,
                'mask': acct.mask,
                'type': str(acct.type),
                'subtype': str(acct.subtype),
            }
            for acct in response['accounts']
        ]

        logger.info(f"Fetched {len(accounts)} account(s) from Plaid.")
        return accounts

    except Exception as e:
        logger.exception(f"Failed to fetch accounts: {e}")
        raise


# ─── Transaction Fetching ─────────────────────────────────────────────────────

def refresh_transactions(access_token: str) -> dict:
    """Ask Plaid to refresh transaction data for an access token."""
    try:
        from plaid.model.transactions_refresh_request import TransactionsRefreshRequest

        client = get_plaid_client()
        request = TransactionsRefreshRequest(access_token=access_token)
        response = client.transactions_refresh(request)
        logger.info("Triggered Plaid transaction refresh for access token.")
        return response
    except Exception as e:
        logger.warning(f"Plaid transaction refresh failed: {e}")
        return {}


def get_transactions(
    access_token: str,
    start_date: date,
    end_date: date,
    account_ids: Optional[list[str]] = None,
) -> list[dict]:
    """
    Fetch transactions from Plaid for a given date range.

    Handles Plaid's pagination automatically — the Plaid API returns at most
    500 transactions per request, so multiple requests may be needed. All pages
    are combined into a single list.

    Args:
        access_token: Plaid access token for one institution.
        start_date:   Inclusive start date for the transaction window.
        end_date:     Inclusive end date (usually today).
        account_ids:  Optional list of specific account IDs to filter by.
                      If None, fetches transactions for all linked accounts.

    Returns:
        List of canonical transaction dicts ready for the pipeline.
        Each dict matches the canonical schema exactly.

    Raises:
        plaid.exceptions.ApiException: On API errors (logged and re-raised).
    """
    try:
        from plaid.model.transactions_get_request import TransactionsGetRequest
        from plaid.model.transactions_get_request_options import (
            TransactionsGetRequestOptions
        )

        client = get_plaid_client()
        options = TransactionsGetRequestOptions()

        if account_ids:
            options.account_ids = account_ids

        all_transactions = []
        offset = 0

        logger.info(
            f"Fetching transactions from {start_date} to {end_date}..."
        )

        while True:
            options.offset = offset
            request = TransactionsGetRequest(
                access_token=access_token,
                start_date=start_date,
                end_date=end_date,
                options=options,
            )
            response = client.transactions_get(request)
            batch = response['transactions']

            if not batch:
                break

            # Convert each Plaid transaction to canonical schema
            all_transactions.extend([
                _normalize_plaid_transaction(t)
                for t in batch
            ])

            offset += len(batch)
            total = response['total_transactions']

            # Log progress every 100 transactions
            if offset % 100 == 0 or offset >= total:
                logger.debug(f"Fetched {offset}/{total} transactions...")

            if offset >= total:
                break

        logger.info(f"Fetched {len(all_transactions)} total transaction(s) from Plaid.")
        return all_transactions

    except Exception as e:
        logger.exception(f"Failed to fetch transactions: {e}")
        raise


def get_incremental_transactions(
    access_token: str,
    since_date: date,
) -> list[dict]:
    """
    Fetch only new or updated transactions since a given date.

    Used for incremental sync to avoid re-downloading the full transaction
    history on every run. The database's most recent transaction date is
    passed in as since_date, allowing Plaid to return only newer records.

    Args:
        access_token: Plaid access token for one institution.
        since_date:   Fetch transactions from this date forward (inclusive).

    Returns:
        List of canonical transaction dicts for new/updated transactions.

    Raises:
        plaid.exceptions.ApiException: On API errors (logged and re-raised).

    NOTE:
        Plaid also offers a Transactions Sync endpoint (/transactions/sync)
        that uses cursor-based pagination and explicitly flags added/modified/
        removed transactions. This is superior for incremental sync:
        https://plaid.com/docs/transactions/sync/
        Consider implementing that in a future version instead of date-range polling.
    """
    try:
        today = date.today()
        return get_transactions(
            access_token=access_token,
            start_date=since_date,
            end_date=today,
        )
    except Exception as e:
        logger.exception(f"Failed to fetch incremental transactions: {e}")
        raise


# ─── Plaid-to-Canonical Conversion ────────────────────────────────────────────

def _normalize_plaid_transaction(plaid_txn, institution: str = '') -> dict:
    """
    Convert a raw Plaid transaction object to the canonical internal schema.

    This is the translation layer between Plaid's field names and the internal
    schema that the rest of the pipeline uses. Keeping it here means the
    rest of the codebase never imports from plaid-python directly.

    CRITICAL: Amount Sign Convention
        Plaid:    positive = money leaving account (debit/purchase)
        Internal: negative = money leaving account (debit/purchase)
        Always negate Plaid's amount: internal_amount = -(plaid_txn.amount)

    Category Mapping:
        Plaid returns `personal_finance_category` with:
            - primary: Main category (e.g., 'FOOD_AND_DRINK')
            - detailed: Specific category (e.g., 'FOOD_AND_DRINK_COFFEE')
        We use the detailed category for better granularity in reporting.

    Args:
        plaid_txn:   A Plaid Transaction object from the API response.
        institution: Institution name to tag this transaction with.

    Returns:
        Canonical transaction dict matching the internal schema with keys:
            transaction_id, date, account, merchant, description,
            plaid_category, plaid_category_primary, user_category, amount, pending,
            institution, last_updated
    """
    # Read from personal_finance_category (new Plaid API v2025+)
    # Falls back to legacy category field if needed
    plaid_category = ''
    plaid_category_primary = ''

    if hasattr(plaid_txn, 'personal_finance_category') and plaid_txn.personal_finance_category:
        pfc = plaid_txn.personal_finance_category
        # detailed is the most specific category
        if hasattr(pfc, 'detailed') and pfc.detailed:
            plaid_category = pfc.detailed
        # primary is the broad category
        if hasattr(pfc, 'primary') and pfc.primary:
            plaid_category_primary = pfc.primary
    elif hasattr(plaid_txn, 'category') and plaid_txn.category:
        # Fallback to legacy category field (deprecated, but some sandboxes may use it)
        plaid_category = plaid_txn.category[-1] if isinstance(plaid_txn.category, list) else plaid_txn.category

    # Plaid uses positive amounts for debits and negative for credits —
    # the OPPOSITE of our internal convention. Flip the sign.
    amount = -(plaid_txn.amount)

    # Prefer merchant_name (normalized by Plaid) over name (raw description)
    merchant = plaid_txn.merchant_name or plaid_txn.name or ''

    return {
        'transaction_id': plaid_txn.transaction_id,
        'date': str(plaid_txn.date),
        'account': plaid_txn.account_id,  # Will be resolved to human-readable name in sync.py
        'merchant': merchant,
        'description': plaid_txn.name or '',
        'plaid_category': plaid_category,  # Detailed PFC category
        'plaid_category_primary': plaid_category_primary,  # Primary PFC category
        'user_category': None,  # Always None when leaving Plaid client
        'amount': amount,
        'pending': plaid_txn.pending,
        'institution': institution,
        'last_updated': datetime.utcnow().isoformat(),
    }


# ─── Link Token (for future Plaid Link UI) ────────────────────────────────────

def create_link_token(user_id: str = 'finance_sync_user') -> str:
    """
    Create a Plaid Link token for the Link UI flow.

    This is needed once per institution to obtain an access token.
    Run link_setup.py (a simple local Flask server), click through the Plaid Link UI,
    and capture the returned access token. You will not need to repeat this step
    unless you revoke the token or need to add another institution.

    This function creates a link token with:
    - 730 days (2 years) of transaction history
    - Optional products for investments, liabilities, and auth to maximize data collection

    Args:
        user_id: Arbitrary unique identifier for the end user (default: 'finance_sync_user').

    Returns:
        link_token string to pass to the Plaid Link UI in the frontend.

    Raises:
        plaid.exceptions.ApiException: On API errors (logged and re-raised).
    """
    try:
        from plaid.model.link_token_create_request import LinkTokenCreateRequest
        from plaid.model.link_token_create_request_user import (
            LinkTokenCreateRequestUser
        )
        from plaid.model.products import Products
        from plaid.model.country_code import CountryCode
        
        client = get_plaid_client()

        # Build the core request with maximum data collection (reporting only, no money movement)
        request = LinkTokenCreateRequest(
            products=[Products('transactions')],
            client_name='Finance Sync',
            country_codes=[CountryCode('US')],
            language='en',
            user=LinkTokenCreateRequestUser(client_user_id=user_id),
            transactions={
                "days_requested": 730  # Forces the 24-month historical pull
            },
            optional_products=[
                Products('investments'),        # Investment holdings and transactions
                Products('liabilities'),        # Loan/credit data (interest rates, payments)
                Products('identity'),           # User identity information
                Products('assets'),             # Asset reports
            ]
        )

        response = client.link_token_create(request)
        link_token = response['link_token']
        logger.info(f"Created Plaid Link token with 730 days history and optional products for user: {user_id}")
        return link_token

    except Exception as e:
        logger.exception(f"Failed to create link token: {e}")
        raise


# ─── Public Token Exchange (for Plaid Link UI) ─────────────────────────────────

def item_public_token_exchange(public_token: str) -> str:
    """
    Exchange a public token (returned by Plaid Link UI) for an access token.

    This function is called from link_setup.py after the user completes the
    Plaid Link flow. The public token is short-lived and is exchanged once
    for a long-lived access token, which is then stored in the environment
    and used for all future API calls.

    Args:
        public_token: Public token received from the Plaid Link UI callback.

    Returns:
        access_token string to be stored in .env file as PLAID_{ENV}_TOKEN_INSTITUTIONNAME.

    Raises:
        plaid.exceptions.ApiException: On API errors (logged and re-raised).
    """
    try:
        from plaid.model.item_public_token_exchange_request import (
            ItemPublicTokenExchangeRequest
        )

        client = get_plaid_client()
        request = ItemPublicTokenExchangeRequest(public_token=public_token)
        response = client.item_public_token_exchange(request)
        access_token = response['access_token']

        logger.info("Successfully exchanged public token for access token.")
        return access_token

    except Exception as e:
        logger.exception(f"Failed to exchange public token: {e}")
        raise
