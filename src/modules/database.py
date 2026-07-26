"""
database.py
===========
SQLite persistence layer for canonical transaction data.

Responsibilities:
  - Schema creation (idempotent; safe to call on every startup)
  - Upsert by transaction_id — the ONLY column used for uniqueness
  - Batch and single-row write helpers
  - Read helpers for downstream reporting/export
  - Optional enable/disable via ENABLE_DATABASE config flag

Design principles:
  - Never identify duplicates by amount, date, or merchant — only transaction_id
  - All writes are upserts (INSERT OR REPLACE) so re-running sync is idempotent
  - Connection lifecycle managed by context manager — no leaked connections
  - SQLite is abstracted behind functions so swapping to PostgreSQL later
    requires only changing the helpers below, not callers

Schema mirrors the canonical transaction schema exactly:
  transaction_id, date, account, merchant, description,
  plaid_category, plaid_category_primary, user_category, amount, pending, 
  institution, last_updated

Where:
  - plaid_category: Detailed Personal Finance Category from Plaid 
    (e.g., 'FOOD_AND_DRINK_COFFEE', 'FOOD_AND_DRINK_GROCERIES')
  - plaid_category_primary: Primary PFC from Plaid 
    (e.g., 'FOOD_AND_DRINK', 'TRANSPORTATION')

Incremental sync note (future Plaid integration):
  When Plaid is connected, pending transactions may later settle and change.
  INSERT OR REPLACE handles this correctly — the settled version overwrites
  the pending version automatically on the next sync run.

TODO (incremental sync): Add a get_latest_sync_date() helper that returns
  the most recent transaction date in the DB so Plaid can be queried for only
  new/changed transactions, rather than doing a full refresh each run.
"""

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from ..core.config import DATABASE_PATH, ENABLE_DATABASE

logger = logging.getLogger(__name__)


# ─── Schema DDL ────────────────────────────────────────────────────────────────

_CREATE_TRANSACTIONS_TABLE = """
    CREATE TABLE IF NOT EXISTS transactions (
        transaction_id   TEXT    PRIMARY KEY,
        date             TEXT    NOT NULL,
        account          TEXT,
        merchant         TEXT,
        description      TEXT,
        plaid_category   TEXT,
        plaid_category_primary TEXT,
        user_category    TEXT,
        amount           REAL,
        pending          INTEGER DEFAULT 0,
        institution      TEXT,
        last_updated     TEXT,
        excluded         INTEGER DEFAULT 0
    );
"""

# Secondary index on date supports efficient date-range queries for reporting
_CREATE_DATE_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_transactions_date
    ON transactions(date);
"""

# Index on institution supports per-institution reporting
_CREATE_INSTITUTION_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_transactions_institution
    ON transactions(institution);
"""

# Add new column if it doesn't exist (for backward compatibility with existing DBs)
_ADD_PLAID_CATEGORY_PRIMARY = """
    ALTER TABLE transactions ADD COLUMN plaid_category_primary TEXT;
"""

# Add excluded column if it doesn't exist (for backward compatibility with existing DBs)
_ADD_EXCLUDED_COLUMN = """
    ALTER TABLE transactions ADD COLUMN excluded INTEGER DEFAULT 0;
"""

# ─── Account Snapshots Table ─────────────────────────────────────────────────────

_CREATE_ACCOUNT_SNAPSHOTS_TABLE = """
    CREATE TABLE IF NOT EXISTS account_snapshots (
        snapshot_date     TEXT    NOT NULL,
        account_id        TEXT    NOT NULL,
        account_name      TEXT,
        institution       TEXT,
        account_type      TEXT,
        account_subtype   TEXT,
        current_balance   REAL,
        available_balance REAL,
        credit_limit      REAL,
        currency          TEXT DEFAULT 'USD',
        PRIMARY KEY (snapshot_date, account_id)
    );
"""

# Index on snapshot_date for efficient date-range queries
_CREATE_SNAPSHOT_DATE_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_account_snapshots_date
    ON account_snapshots(snapshot_date);
"""


# ─── Connection Management ─────────────────────────────────────────────────────

@contextmanager
def _get_connection(db_path: Path = DATABASE_PATH) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager that yields a configured SQLite connection.

    Automatically:
      - Commits on clean exit
      - Rolls back on exception
      - Closes the connection in all cases

    Row factory is set to sqlite3.Row so callers receive dict-compatible objects
    (access by column name, not just index).

    Args:
        db_path: Path to the SQLite database file.

    Yields:
        sqlite3.Connection
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Enable WAL mode for better concurrent read performance (future-proofing)
    conn.execute("PRAGMA journal_mode=WAL;")

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ─── Schema Initialization ─────────────────────────────────────────────────────

def init_db(db_path: Path = DATABASE_PATH) -> None:
    """
    Create the database file and schema if they don't already exist.

    Safe to call on every startup — all DDL uses IF NOT EXISTS. No data
    is altered when called against an existing populated database.

    Also handles schema migrations (e.g., adding new columns for Plaid PFC support).

    Args:
        db_path: Path to the SQLite database file.
    """
    if not ENABLE_DATABASE:
        logger.info("Database disabled via config (ENABLE_DATABASE=False) — skipping init.")
        return

    db_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Initializing database at: {db_path}")

    with _get_connection(db_path) as conn:
        conn.execute(_CREATE_TRANSACTIONS_TABLE)
        conn.execute(_CREATE_DATE_INDEX)
        conn.execute(_CREATE_INSTITUTION_INDEX)

        # Migration: Add plaid_category_primary column if it doesn't exist (for existing DBs)
        try:
            conn.execute(_ADD_PLAID_CATEGORY_PRIMARY)
            logger.debug("Added plaid_category_primary column (new schema).")
        except sqlite3.OperationalError as e:
            if 'duplicate column name' in str(e).lower():
                # Column already exists, no action needed
                logger.debug("plaid_category_primary column already exists.")
            else:
                raise
        
        # Migration: Add excluded column if it doesn't exist (for existing DBs)
        try:
            conn.execute(_ADD_EXCLUDED_COLUMN)
            logger.debug("Added excluded column (new schema).")
        except sqlite3.OperationalError as e:
            if 'duplicate column name' in str(e).lower():
                # Column already exists, no action needed
                logger.debug("excluded column already exists.")
            else:
                raise

        # Initialize account snapshots table
        init_account_snapshots(db_path)

    logger.info("Database schema initialized successfully.")


def init_account_snapshots(db_path: Path = DATABASE_PATH) -> None:
    """
    Create the account_snapshots table and indexes if they don't already exist.

    Safe to call on every startup — all DDL uses IF NOT EXISTS. No data
    is altered when called against an existing populated database.

    Args:
        db_path: Path to the SQLite database file.
    """
    if not ENABLE_DATABASE:
        logger.debug("Database disabled — skipping account snapshots init.")
        return

    with _get_connection(db_path) as conn:
        conn.execute(_CREATE_ACCOUNT_SNAPSHOTS_TABLE)
        conn.execute(_CREATE_SNAPSHOT_DATE_INDEX)

    logger.debug("Account snapshots table initialized successfully.")


# ─── Write Operations ──────────────────────────────────────────────────────────

# Smart upsert SQL — defined once to avoid drift.
#
# INSERT behaviour (new transaction_id):
#   All fields are written, including user_category from the categorizer.
#
# ON CONFLICT behaviour (existing transaction_id):
#   Only Plaid-owned fields are updated (date, account, merchant, description,
#   plaid_category, plaid_category_primary, amount, pending, institution, last_updated).
#   user_category and excluded are intentionally OMITTED from the SET clause so
#   manual edits made directly in the database survive every subsequent sync.
#
#   The WHERE clause uses IS NOT (NULL-safe) to skip the update entirely when
#   none of the Plaid fields have changed, keeping last_updated pristine and
#   making it possible to count truly new/changed rows vs unchanged ones.
_UPSERT_SQL = """
    INSERT INTO transactions (
        transaction_id, date, account, merchant, description,
        plaid_category, plaid_category_primary, user_category, amount, pending,
        institution, last_updated, excluded
    ) VALUES (
        :transaction_id, :date, :account, :merchant, :description,
        :plaid_category, :plaid_category_primary, :user_category, :amount, :pending,
        :institution, :last_updated, :excluded
    )
    ON CONFLICT(transaction_id) DO UPDATE SET
        date                   = excluded.date,
        account                = excluded.account,
        merchant               = excluded.merchant,
        description            = excluded.description,
        plaid_category         = excluded.plaid_category,
        plaid_category_primary = excluded.plaid_category_primary,
        amount                 = excluded.amount,
        pending                = excluded.pending,
        institution            = excluded.institution,
        last_updated           = excluded.last_updated
    WHERE
        transactions.date                   IS NOT excluded.date                   OR
        transactions.account                IS NOT excluded.account                OR
        transactions.merchant               IS NOT excluded.merchant               OR
        transactions.description            IS NOT excluded.description            OR
        transactions.plaid_category         IS NOT excluded.plaid_category         OR
        transactions.plaid_category_primary IS NOT excluded.plaid_category_primary OR
        transactions.amount                 IS NOT excluded.amount                 OR
        transactions.pending                IS NOT excluded.pending                OR
        transactions.institution            IS NOT excluded.institution
"""

# Upsert SQL for account snapshots
_UPSERT_SNAPSHOT_SQL = """
    INSERT OR REPLACE INTO account_snapshots (
        snapshot_date, account_id, account_name, institution,
        account_type, account_subtype, current_balance, available_balance,
        credit_limit, currency
    ) VALUES (
        :snapshot_date, :account_id, :account_name, :institution,
        :account_type, :account_subtype, :current_balance, :available_balance,
        :credit_limit, :currency
    )
"""


def upsert_transaction(transaction: dict, db_path: Path = DATABASE_PATH) -> None:
    """
    Insert or update a single canonical transaction.

    Uses a smart upsert keyed on transaction_id:
      - New rows: all fields written, including user_category from the categorizer.
      - Existing rows: only Plaid-owned fields updated; user_category and excluded
        are preserved so manual DB edits survive subsequent syncs.
      - Unchanged rows: skipped entirely (last_updated stays pristine).

    Args:
        transaction: Canonical transaction dict. Must contain 'transaction_id'.
        db_path:     Path to the database.

    Raises:
        sqlite3.Error: On database write failures.
    """
    if not ENABLE_DATABASE:
        logger.debug(
            f"Database disabled — skipping upsert: {transaction.get('transaction_id')}"
        )
        return

    with _get_connection(db_path) as conn:
        conn.execute(_UPSERT_SQL, transaction)

    logger.debug(f"Upserted transaction: {transaction.get('transaction_id')}")


def upsert_transactions(
    transactions: list[dict],
    db_path: Path = DATABASE_PATH,
) -> dict:
    """
    Batch upsert a list of canonical transactions in a single database transaction.

    Uses a smart upsert keyed on transaction_id:
      - New rows: all fields written, including user_category from the categorizer.
      - Existing rows with changes: Plaid-owned fields updated; user_category and
        excluded preserved so manual DB edits survive subsequent syncs.
      - Existing rows with no changes: skipped entirely (last_updated stays pristine).

    Using executemany() inside one transaction is significantly faster than
    individual calls for large batches, and atomicity means either all rows
    succeed or none do.

    Args:
        transactions: List of canonical transaction dicts.
        db_path:      Path to the database.

    Returns:
        Dict with keys:
          - "written":   count of rows inserted or updated (Plaid data changed)
          - "unchanged": count of rows skipped because nothing changed
          - "total":     total rows processed
        Returns {"written": 0, "unchanged": 0, "total": 0} if database is disabled.

    Raises:
        sqlite3.Error: If the batch write fails (all rows are rolled back).
    """
    if not ENABLE_DATABASE:
        logger.info(
            f"Database disabled — skipping batch upsert "
            f"of {len(transactions)} transaction(s)."
        )
        return {"written": 0, "unchanged": 0, "total": 0}

    if not transactions:
        logger.warning("upsert_transactions called with empty list — nothing to write.")
        return {"written": 0, "unchanged": 0, "total": 0}

    with _get_connection(db_path) as conn:
        before = conn.total_changes
        conn.executemany(_UPSERT_SQL, transactions)
        written = conn.total_changes - before

    total = len(transactions)
    unchanged = total - written
    logger.info(
        f"Batch upsert complete: {written} written (new or changed), "
        f"{unchanged} unchanged, {total} total."
    )
    return {"written": written, "unchanged": unchanged, "total": total}


# ─── Read Operations ───────────────────────────────────────────────────────────

def get_all_transactions(db_path: Path = DATABASE_PATH) -> list[dict]:
    """
    Retrieve all transactions ordered by date descending (most recent first).

    Args:
        db_path: Path to the database.

    Returns:
        List of transaction dicts. Empty list if database is disabled or empty.
    """
    if not ENABLE_DATABASE:
        logger.info("Database disabled — get_all_transactions returning empty list.")
        return []

    with _get_connection(db_path) as conn:
        cursor = conn.execute(
            "SELECT * FROM transactions ORDER BY date DESC"
        )
        rows = cursor.fetchall()

    logger.debug(f"Retrieved {len(rows)} transaction(s) from database.")
    return [dict(row) for row in rows]


def get_transaction_by_id(
    transaction_id: str,
    db_path: Path = DATABASE_PATH,
) -> Optional[dict]:
    """
    Retrieve a single transaction by its unique ID.

    Args:
        transaction_id: The unique transaction identifier.
        db_path:        Path to the database.

    Returns:
        Transaction dict if found; None if not found or database is disabled.
    """
    if not ENABLE_DATABASE:
        return None

    with _get_connection(db_path) as conn:
        cursor = conn.execute(
            "SELECT * FROM transactions WHERE transaction_id = ?",
            (transaction_id,),
        )
        row = cursor.fetchone()

    return dict(row) if row else None


def get_transactions_by_date_range(
    start_date: str,
    end_date: str,
    db_path: Path = DATABASE_PATH,
) -> list[dict]:
    """
    Retrieve transactions within an inclusive date range.

    Dates should be ISO 8601 strings (YYYY-MM-DD). SQLite's text comparison
    works correctly with this format.

    Args:
        start_date: Start of range (inclusive), e.g. "2024-01-01".
        end_date:   End of range (inclusive), e.g. "2024-01-31".
        db_path:    Path to the database.

    Returns:
        List of matching transaction dicts, ordered by date descending.
    """
    if not ENABLE_DATABASE:
        logger.info("Database disabled — get_transactions_by_date_range returning empty list.")
        return []

    with _get_connection(db_path) as conn:
        cursor = conn.execute(
            "SELECT * FROM transactions WHERE date BETWEEN ? AND ? ORDER BY date DESC",
            (start_date, end_date),
        )
        rows = cursor.fetchall()

    logger.debug(
        f"Retrieved {len(rows)} transaction(s) "
        f"between {start_date} and {end_date}."
    )
    return [dict(row) for row in rows]


def get_transaction_count(db_path: Path = DATABASE_PATH) -> int:
    """
    Return the total number of transactions stored in the database.

    Useful for logging and diagnostics without pulling all rows into memory.

    Args:
        db_path: Path to the database.

    Returns:
        Row count, or 0 if database is disabled.
    """
    if not ENABLE_DATABASE:
        return 0

    with _get_connection(db_path) as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM transactions")
        return cursor.fetchone()[0]


def get_uncategorized_transactions(db_path: Path = DATABASE_PATH) -> list[dict]:
    """
    Retrieve transactions that have neither a user_category nor a plaid_category.

    Useful for identifying gaps in the category rules file.

    Args:
        db_path: Path to the database.

    Returns:
        List of uncategorized transaction dicts.
    """
    if not ENABLE_DATABASE:
        return []

    with _get_connection(db_path) as conn:
        cursor = conn.execute(
            """
            SELECT * FROM transactions
            WHERE (user_category IS NULL OR user_category = '')
              AND (plaid_category IS NULL OR plaid_category = '')
            ORDER BY date DESC
            """
        )
        rows = cursor.fetchall()

    logger.debug(f"Found {len(rows)} uncategorized transaction(s) in database.")
    return [dict(row) for row in rows]




def get_latest_transaction_date(db_path: Path = DATABASE_PATH) -> Optional[str]:
    """
    Return the ISO 8601 date of the most recent transaction in the database.

    Used for incremental sync to determine the starting date for the next Plaid
    API query. If a transaction dated 2024-03-15 is the most recent, the next
    sync will fetch from (2024-03-15 - 7 days) to catch any late-posted transactions.

    Args:
        db_path: Path to the database.

    Returns:
        Most recent transaction date as ISO 8601 string (YYYY-MM-DD), or None if:
          - Database is disabled (ENABLE_DATABASE is False)
          - Transactions table is empty
    """
    if not ENABLE_DATABASE:
        logger.info("Database disabled — get_latest_transaction_date returning None.")
        return None

    with _get_connection(db_path) as conn:
        cursor = conn.execute("SELECT MAX(date) FROM transactions")
        result = cursor.fetchone()[0]

    logger.debug(f"Latest transaction date in database: {result or '(empty)'}")
    return result


# ─── Account Snapshot Operations ──────────────────────────────────────────────────

def upsert_snapshots(snapshots: list[dict], db_path: Path = DATABASE_PATH) -> int:
    """
    Batch upsert account balance snapshots to the database.

    Uses INSERT OR REPLACE keyed on (snapshot_date, account_id). If a snapshot
    already exists for the same date and account, it is fully overwritten with
    the latest data. This makes re-running the pipeline idempotent.

    Args:
        snapshots: List of snapshot dicts matching the account_snapshots schema.
        db_path:   Path to the database.

    Returns:
        Number of snapshots upserted.

    Raises:
        sqlite3.Error: On database write failures.
    """
    if not ENABLE_DATABASE:
        logger.debug(f"Database disabled — skipping upsert of {len(snapshots)} snapshot(s).")
        return 0

    if not snapshots:
        logger.debug("upsert_snapshots: received empty list — skipping.")
        return 0

    with _get_connection(db_path) as conn:
        conn.executemany(_UPSERT_SNAPSHOT_SQL, snapshots)

    logger.debug(f"Upserted {len(snapshots)} account snapshot(s) to SQLite.")
    return len(snapshots)


def get_latest_balances(db_path: Path = DATABASE_PATH) -> list[dict]:
    """
    Return the most recent snapshot for each account_id.

    Used for current state export (e.g., "Account Balances" sheet).

    Args:
        db_path: Path to the database.

    Returns:
        List of snapshot dicts, one per account_id, ordered by institution then account_name.
        Returns empty list if database is disabled or no snapshots exist.
    """
    if not ENABLE_DATABASE:
        logger.debug("Database disabled — get_latest_balances returning empty list.")
        return []

    with _get_connection(db_path) as conn:
        cursor = conn.execute(
            """
            SELECT * FROM account_snapshots
            WHERE (snapshot_date, account_id) IN (
                SELECT snapshot_date, account_id
                FROM account_snapshots
                GROUP BY account_id
                HAVING snapshot_date = MAX(snapshot_date)
            )
            ORDER BY institution, account_name
            """
        )
        rows = cursor.fetchall()

    logger.debug(f"Retrieved {len(rows)} latest account balance snapshot(s).")
    return [dict(row) for row in rows]


def get_balance_history(days: int = 90, db_path: Path = DATABASE_PATH) -> list[dict]:
    """
    Return all snapshots from the last N days.

    Used for history/chart export.

    Args:
        days:    Number of days to look back (default: 90).
        db_path: Path to the database.

    Returns:
        List of snapshot dicts ordered by snapshot_date ASC, account_id ASC.
        Returns empty list if database is disabled or no snapshots exist.
    """
    if not ENABLE_DATABASE:
        logger.debug("Database disabled — get_balance_history returning empty list.")
        return []

    with _get_connection(db_path) as conn:
        cursor = conn.execute(
            """
            SELECT * FROM account_snapshots
            WHERE snapshot_date >= date('now', '-' || ? || ' days')
            ORDER BY snapshot_date ASC, account_id ASC
            """,
            (str(days),),
        )
        rows = cursor.fetchall()

    logger.debug(f"Retrieved {len(rows)} balance snapshot(s) from last {days} days.")
    return [dict(row) for row in rows]


def get_net_worth_history(db_path: Path = DATABASE_PATH) -> list[dict]:
    """
    Return net worth history aggregated by snapshot date.

    Aggregates by snapshot_date:
      - assets      = SUM of depository + investment balances
      - liabilities = SUM of credit + loan balances (as positive)
      - net_worth   = assets - liabilities

    Args:
        db_path: Path to the database.

    Returns:
        List of dicts with keys: snapshot_date, assets, liabilities, net_worth.
        Ordered by snapshot_date ASC. Returns empty list if database is disabled
        or no snapshots exist.
    """
    if not ENABLE_DATABASE:
        logger.debug("Database disabled — get_net_worth_history returning empty list.")
        return []

    with _get_connection(db_path) as conn:
        cursor = conn.execute(
            """
            SELECT
                snapshot_date,
                SUM(CASE
                    WHEN account_type IN ('depository', 'investment')
                    THEN COALESCE(current_balance, 0)
                    ELSE 0
                END) as assets,
                SUM(CASE
                    WHEN account_type IN ('credit', 'loan')
                    THEN COALESCE(current_balance, 0)
                    ELSE 0
                END) as liabilities
            FROM account_snapshots
            GROUP BY snapshot_date
            ORDER BY snapshot_date ASC
            """
        )
        rows = cursor.fetchall()

    result = []
    for row in rows:
        assets = row['assets'] or 0
        liabilities = row['liabilities'] or 0
        result.append({
            'snapshot_date': row['snapshot_date'],
            'assets': assets,
            'liabilities': liabilities,
            'net_worth': assets - liabilities,
        })

    logger.debug(f"Retrieved net worth history for {len(result)} date(s).")
    return result
