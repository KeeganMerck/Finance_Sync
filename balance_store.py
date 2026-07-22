"""
balance_store.py
=================
Balance snapshot storage layer.

This module provides a clean interface for storing and retrieving account
balance snapshots from the database. It wraps the database operations
specific to balance snapshots, following the same pattern as database.py
for transactions.

All functions respect the ENABLE_DATABASE config flag and handle errors
gracefully with appropriate logging.
"""

import logging
from pathlib import Path
from typing import Optional

from config import DATABASE_PATH, ENABLE_DATABASE

logger = logging.getLogger(__name__)


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