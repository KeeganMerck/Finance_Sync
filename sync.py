"""
Transaction synchronizer and normalizer.

Supports two data sources:
    1. Mock JSON file (USE_PLAID=false) — useful for testing and development
    2. Live Plaid API (USE_PLAID=true) — production transaction source

The module abstracts away the data source, so downstream modules always receive
transactions in the canonical schema regardless of origin.
"""

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

from config import (
    FULL_SYNC_LOOKBACK_DAYS,
    INCREMENTAL_SYNC_BUFFER_DAYS,
    MOCK_JSON_PATH,
    PLAID_FORCE_REFRESH,
    SYNC_MODE,
    USE_PLAID,
)
import plaid_integration
from database import get_latest_transaction_date

logger = logging.getLogger(__name__)


def load_transactions():
    """
    Load mocked transactions from JSON.
    """

    with open(MOCK_JSON_PATH, "r") as f:
        data = json.load(f)

    return data


def normalize_transaction(txn: dict) -> dict:
    """
    Convert incoming data into canonical format.
    
    Handles both mock JSON and Plaid API sources, passing through all relevant
    fields. For mock JSON, plaid_category_primary may not be present (uses empty string).
    """

    return {
        "transaction_id": txn["transaction_id"],
        "date": txn["date"],
        "account": txn["account"],
        "merchant": txn["merchant"],
        "description": txn["description"],
        "plaid_category": txn.get("plaid_category", ""),
        "plaid_category_primary": txn.get("plaid_category_primary", ""),
        "user_category": None,
        "amount": txn["amount"],
        "pending": txn["pending"],
        "institution": txn["institution"],
        "last_updated": datetime.utcnow().isoformat(),
    }


def fetch_transactions():
    """
    Primary sync entrypoint. Branches on USE_PLAID configuration.

    If USE_PLAID is True:
        - Loads all Plaid access tokens from environment (PLAID_{ENV}_TOKEN_*)
        - For each institution, determines the date range for incremental sync
        - Fetches transactions and resolves account IDs to human-readable names
        - Combines results from all institutions
        - Returns all in canonical schema

    If USE_PLAID is False:
        - Loads mock JSON from data/mock_transactions.json
        - Normalizes each transaction to canonical schema
        - Returns mock transactions for testing and development

    Returns:
        List of canonical transaction dicts. Empty list if no transactions found.

    Raises:
        Exception: If Plaid fetch fails (logged and re-raised by pipeline orchestrator)
    """
    if USE_PLAID:
        return _fetch_from_plaid()
    else:
        return _fetch_from_mock_json()


def _fetch_from_mock_json() -> list[dict]:
    """
    Load and normalize mock transactions from JSON file.

    Used when USE_PLAID is False for development/testing.

    Returns:
        List of normalized transaction dicts.
    """
    logger.info("Loading mock transactions from JSON...")
    raw = load_transactions()

    normalized = [
        normalize_transaction(txn)
        for txn in raw
    ]

    logger.info(f"Loaded {len(normalized)} mock transaction(s).")
    return normalized


def _fetch_from_plaid() -> list[dict]:
    """
    Fetch live transactions from Plaid API for all configured institutions.

    For each institution (identified by PLAID_{ENV}_TOKEN_* environment variables):
        1. Determines the starting date for incremental sync:
           - If DB has transactions: start_date = (most recent date) - 14 days
           - If DB is empty (first run): start_date = today - 365 days
        2. Fetches transactions from Plaid for [start_date, today]
        3. Resolves account IDs to human-readable account names
        4. Tags each transaction with the institution name
        5. Normalizes to canonical schema

    Returns:
        Combined list of transactions from all institutions, normalized.

    Raises:
        plaid_client.ApiException: If any API call fails (propagated to caller)
    """
    logger.info("Fetching live transactions from Plaid...")

    access_tokens = plaid_integration.get_access_tokens()
    if not access_tokens:
        logger.warning("No Plaid access tokens configured. Returning empty transaction list.")
        return []

    all_transactions = []
    end_date = date.today()

    for institution_name, access_token in access_tokens.items():
        try:
            logger.info(f"Processing institution: {institution_name}")

            # ─── Determine start date for incremental sync ─────────────────────

            latest_db_date = get_latest_transaction_date()
            if SYNC_MODE == 'incremental':
                if latest_db_date:
                    # Database has transactions — start from latest minus buffer days
                    latest_date_obj = datetime.fromisoformat(latest_db_date).date()
                    start_date = latest_date_obj - timedelta(days=INCREMENTAL_SYNC_BUFFER_DAYS)
                    logger.info(
                        f"  Incremental sync from {start_date} "
                        f"(DB latest: {latest_db_date}, buffer: {INCREMENTAL_SYNC_BUFFER_DAYS} days)"
                    )
                else:
                    # First run — fetch a configurable initial history window
                    start_date = end_date - timedelta(days=FULL_SYNC_LOOKBACK_DAYS)
                    logger.info(
                        f"  First run — fetching from {start_date} "
                        f"({FULL_SYNC_LOOKBACK_DAYS} days back)"
                    )
            else:
                # Full sync mode — fetch from a configurable lookback window
                start_date = end_date - timedelta(days=FULL_SYNC_LOOKBACK_DAYS)
                logger.info(
                    f"  Full sync from {start_date} "
                    f"({FULL_SYNC_LOOKBACK_DAYS} days back)"
                )

            # ─── Refresh Plaid data before fetching history ───────────────────
            if PLAID_FORCE_REFRESH:
                plaid_integration.refresh_transactions(access_token)

            # ─── Fetch transactions and accounts ────────────────────────────────

            # Get accounts for this institution to build account_id → name lookup
            accounts = plaid_integration.get_accounts(access_token)
            account_lookup = {
                acct['account_id']: f"{acct['name']} ••{acct['mask']}"
                for acct in accounts
            }

            logger.debug(f"  Resolved {len(account_lookup)} account(s).")

            # Fetch transactions for the determined date range
            plaid_transactions = plaid_integration.get_transactions(
                access_token=access_token,
                start_date=start_date,
                end_date=end_date,
            )

            # ─── Normalize and tag with institution ────────────────────────────

            for txn in plaid_transactions:
                # Replace account_id with human-readable name
                account_id = txn.get('account')
                if account_id in account_lookup:
                    txn['account'] = account_lookup[account_id]
                else:
                    # Fallback if lookup fails (shouldn't happen, but be safe)
                    txn['account'] = account_id

                # Tag with institution name
                txn['institution'] = institution_name

            dates = [txn.get('date') for txn in plaid_transactions if txn.get('date')]
            oldest_date = min(dates) if dates else None
            newest_date = max(dates) if dates else None

            if oldest_date and start_date:
                oldest_dt = datetime.strptime(oldest_date, '%Y-%m-%d').date()
                if oldest_dt > start_date + timedelta(days=90):
                    logger.warning(
                        f"  {institution_name}: returned history from {oldest_date} to {newest_date or 'n/a'}, "
                        f"which is later than the requested window starting {start_date}. "
                        "This can indicate the institution or token only exposes recent history."
                    )

            logger.info(
                f"  {institution_name}: fetched {len(plaid_transactions)} transaction(s)"
                f" from {oldest_date or 'n/a'} to {newest_date or 'n/a'}"
            )

            all_transactions.extend(plaid_transactions)

        except Exception as e:
            logger.exception(
                f"Error processing {institution_name} — skipping this institution. "
                f"Error: {e}"
            )
            # Don't re-raise — continue processing other institutions
            # The pipeline is resilient to partial failures

    logger.info(
        f"Plaid fetch complete: {len(all_transactions)} total transaction(s) "
        f"from {len(access_tokens)} institution(s)"
    )

    return all_transactions