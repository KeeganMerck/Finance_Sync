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
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from ..core.config import DATABASE_PATH, ENABLE_DATABASE

logger = logging.getLogger(__name__)

EASTERN_TIMEZONE = ZoneInfo("America/New_York")


def eastern_today() -> str:
    """Return today's calendar date in the user's default Eastern timezone."""
    return datetime.now(EASTERN_TIMEZONE).date().isoformat()


def normalize_snapshot_date(value: str | date | datetime) -> str:
    """Normalize a snapshot date or timestamp to an Eastern calendar date."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(EASTERN_TIMEZONE).date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if len(text) == 10:
        date.fromisoformat(text)
        return text
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return normalize_snapshot_date(parsed)


def eastern_now_iso() -> str:
    """Return an offset-aware Eastern timestamp for app metadata."""
    return datetime.now(EASTERN_TIMEZONE).isoformat(timespec="seconds")


def validate_manual_transaction(transaction: dict) -> tuple[bool, str]:
    """
    Validate a manual transaction before insertion.

    Args:
        transaction: Dict with transaction data

    Returns:
        (is_valid, error_message)
    """
    required_fields = ["transaction_id", "date", "account", "amount"]

    # Check required fields
    for field in required_fields:
        if field not in transaction or not transaction[field]:
            return False, f"Missing required field: {field}"

    # Validate date format (YYYY-MM-DD)
    date = transaction["date"]
    try:
        from datetime import datetime

        datetime.strptime(date, "%Y-%m-%d")  # noqa: DTZ007
    except ValueError:
        return False, f"Invalid date format: {date}. Expected YYYY-MM-DD"

    # Validate amount is numeric and non-zero
    try:
        amount = float(transaction["amount"])
        if abs(amount) < 0.01:  # Allow very small numbers but not exactly zero
            return False, "Amount cannot be zero"
    except (ValueError, TypeError):
        return False, f"Invalid amount: {transaction['amount']}. Must be a number"

    # Validate account name is not empty
    if not transaction["account"].strip():
        return False, "Account name cannot be empty"

    # Validate description length
    if transaction.get("description") and len(transaction["description"]) > 500:
        return False, "Description too long (max 500 characters)"

    # Validate category length
    if transaction.get("category") and len(transaction["category"]) > 100:
        return False, "Category too long (max 100 characters)"

    return True, ""


def validate_manual_account_snapshot(snapshot: dict) -> tuple[bool, str]:
    """
    Validate a manual account snapshot before insertion.

    Args:
        snapshot: Dict with snapshot data

    Returns:
        (is_valid, error_message)
    """
    required_fields = ["account_id", "snapshot_date", "account_type", "current_balance"]

    # Check required fields
    for field in required_fields:
        if field not in snapshot or not snapshot[field]:
            return False, f"Missing required field: {field}"

    # Validate date format (YYYY-MM-DD)
    date = snapshot["snapshot_date"]
    try:
        from datetime import datetime

        datetime.strptime(date, "%Y-%m-%d")  # noqa: DTZ007
    except ValueError:
        return False, f"Invalid date format: {date}. Expected YYYY-MM-DD"

    # Validate account type
    valid_account_types = ["depository", "credit", "investment", "loan", "brokerage"]
    if snapshot["account_type"].lower() not in valid_account_types:
        return (
            False,
            f"Invalid account type: {snapshot['account_type']}. Must be one of: {', '.join(valid_account_types)}",
        )

    # Validate balance is numeric
    try:
        float(snapshot["current_balance"])
    except (ValueError, TypeError):
        return (
            False,
            f"Invalid balance: {snapshot['current_balance']}. Must be a number",
        )

    # Validate account name length
    if snapshot.get("account_name") and len(snapshot["account_name"]) > 100:
        return False, "Account name too long (max 100 characters)"

    # Validate institution length
    if snapshot.get("institution") and len(snapshot["institution"]) > 100:
        return False, "Institution name too long (max 100 characters)"

    return True, ""


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

# ─── Manual Account Snapshots Table ──────────────────────────────────────────────
#
# Stores hand-entered balance data for accounts that cannot be linked via Plaid
# (e.g. a car loan at a local credit union, home equity estimate, crypto wallet).
#
# Schema is identical to account_snapshots. snapshot_date here represents the date
# the value was entered / became effective — you can have multiple rows per account
# to track history. On each sync run the pipeline reads the most recent row per
# account_id and copies it into account_snapshots dated today, so manual accounts
# flow through the same export/Sheets pipeline as Plaid-linked accounts.
#
# Editing: INSERT rows directly in any SQLite browser (e.g. DB Browser for SQLite).
# Primary key prevents accidental duplicate entries for the same account on the
# same date.

_CREATE_MANUAL_ACCOUNT_SNAPSHOTS_TABLE = """
    CREATE TABLE IF NOT EXISTS manual_account_snapshots (
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

_CREATE_MANUAL_SNAPSHOT_DATE_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_manual_account_snapshots_date
    ON manual_account_snapshots(snapshot_date);
"""

_CREATE_MANUAL_SNAPSHOT_ACCOUNT_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_manual_account_snapshots_account_id
    ON manual_account_snapshots(account_id);
"""

_CREATE_NET_WORTH_HISTORY_TABLE = """
    CREATE TABLE IF NOT EXISTS net_worth_history (
        snapshot_date TEXT PRIMARY KEY,
        net_worth REAL NOT NULL,
        last_updated TEXT DEFAULT CURRENT_TIMESTAMP
    );
"""


# Simple app-level key/value table for small notifications (last update timestamps)
_CREATE_APP_STATE_TABLE = """
    CREATE TABLE IF NOT EXISTS app_state (
        key TEXT PRIMARY KEY,
        value TEXT
    );
"""

_CREATE_MANUAL_TRANSACTIONS_TABLE = """
    CREATE TABLE IF NOT EXISTS manual_transactions (
        transaction_id TEXT PRIMARY KEY,
        date TEXT NOT NULL,
        account TEXT NOT NULL,
        description TEXT,
        category TEXT,
        amount REAL NOT NULL,
        last_updated TEXT DEFAULT CURRENT_TIMESTAMP
    );
"""

_CREATE_INVESTMENT_BASIS_ENTRIES_TABLE = """
    CREATE TABLE IF NOT EXISTS investment_basis_entries (
        basis_id       INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id     TEXT NOT NULL,
        security_id    TEXT,
        symbol         TEXT NOT NULL,
        name           TEXT,
        quantity       REAL NOT NULL,
        total_cost     REAL NOT NULL,
        purchase_date  TEXT,
        entry_mode     TEXT NOT NULL DEFAULT 'supplement',
        notes          TEXT,
        active         INTEGER NOT NULL DEFAULT 1,
        created_at     TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at     TEXT DEFAULT CURRENT_TIMESTAMP
    );
"""

_CREATE_INVESTMENT_BASIS_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_investment_basis_account_security
    ON investment_basis_entries(account_id, security_id, symbol);
"""

# Plaid tokens table for storing access tokens instead of .env file
_CREATE_PLAID_TOKENS_TABLE = """
    CREATE TABLE IF NOT EXISTS plaid_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_name TEXT NOT NULL DEFAULT 'PRIMARY',
        profile_prefix TEXT NOT NULL DEFAULT 'PLAID',
        institution_name TEXT NOT NULL,
        access_token TEXT NOT NULL,
        item_id TEXT,
        environment TEXT DEFAULT 'production',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
        is_active INTEGER DEFAULT 1
    );
"""


# Investment holdings table and indexes (basic schema)
_CREATE_INVESTMENT_HOLDINGS_TABLE = """
    CREATE TABLE IF NOT EXISTS investment_holdings (
        security_id TEXT PRIMARY KEY,
        account_id TEXT,
        symbol TEXT,
        name TEXT,
        quantity REAL,
        current_value REAL,
        total_cost REAL,
        cost_basis REAL,
        last_updated TEXT
    );
"""

_CREATE_INVESTMENTS_ACCOUNT_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_investments_account
    ON investment_holdings(account_id);
"""

_CREATE_INVESTMENTS_DATE_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_investments_last_updated
    ON investment_holdings(last_updated);
"""

_CREATE_INVESTMENTS_SYMBOL_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_investments_symbol
    ON investment_holdings(symbol);
"""

# Investment holdings history
_CREATE_INVESTMENT_HOLDINGS_HISTORY_TABLE = """
    CREATE TABLE IF NOT EXISTS investment_holdings_history (
        history_id INTEGER PRIMARY KEY AUTOINCREMENT,
        security_id TEXT,
        snapshot_date TEXT,
        quantity REAL,
        current_value REAL,
        total_cost REAL,
        symbol TEXT,
        institution TEXT
    );
"""

_CREATE_INVESTMENTS_HISTORY_DATE_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_investments_history_date
    ON investment_holdings_history(snapshot_date);
"""

_CREATE_INVESTMENTS_HISTORY_HOLDING_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_investments_history_holding
    ON investment_holdings_history(security_id);
"""

_CREATE_INVESTMENTS_HISTORY_SYMBOL_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_investments_history_symbol
    ON investment_holdings_history(symbol);
"""

_CREATE_INVESTMENTS_HISTORY_UNIQUE_INDEX = """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_investments_history_unique
    ON investment_holdings_history(snapshot_date, security_id);
"""

# Investment transactions
_CREATE_INVESTMENT_TRANSACTIONS_TABLE = """
    CREATE TABLE IF NOT EXISTS investment_transactions (
        transaction_id TEXT PRIMARY KEY,
        date TEXT,
        account_id TEXT,
        security_id TEXT,
        symbol TEXT,
        quantity REAL,
        amount REAL,
        fees REAL
    );
"""

_CREATE_INVESTMENT_TRANSACTIONS_DATE_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_investment_transactions_date
    ON investment_transactions(date);
"""

_CREATE_INVESTMENT_TRANSACTIONS_ACCOUNT_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_investment_transactions_account
    ON investment_transactions(account_id);
"""

_CREATE_INVESTMENT_TRANSACTIONS_SECURITY_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_investment_transactions_security
    ON investment_transactions(security_id);
"""

_CREATE_PLAID_TOKENS_INDEX = """
    -- Unique index per profile+institution so the same institution can exist
    -- under different Plaid profiles (primary vs secondary).
    CREATE UNIQUE INDEX IF NOT EXISTS idx_plaid_tokens_profile_institution
    ON plaid_tokens(profile_name, institution_name);
    
    -- Non-unique lookup by institution name alone (useful for legacy lookups)
    CREATE INDEX IF NOT EXISTS idx_plaid_tokens_institution
    ON plaid_tokens(institution_name);
"""


# ─── Connection Management ─────────────────────────────────────────────────────


@contextmanager
def _get_connection(
    db_path: Path = DATABASE_PATH,
) -> Generator[sqlite3.Connection, None, None]:
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
        logger.info(
            "Database disabled via config (ENABLE_DATABASE=False) — skipping init."
        )
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
            if "duplicate column name" in str(e).lower():
                # Column already exists, no action needed
                logger.debug("plaid_category_primary column already exists.")
            else:
                raise

        # Migration: Add excluded column if it doesn't exist (for existing DBs)
        try:
            conn.execute(_ADD_EXCLUDED_COLUMN)
            logger.debug("Added excluded column (new schema).")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                # Column already exists, no action needed
                logger.debug("excluded column already exists.")
            else:
                raise

        # Initialize account snapshots table
        init_account_snapshots(db_path)

        # Initialize manual account snapshots table
        init_manual_account_snapshots(db_path)

        # Initialize net worth history table
        init_net_worth_history(db_path)

        # Initialize manual transactions table
        init_manual_transactions(db_path)

        # Initialize manual investment acquisition-basis entries
        init_investment_basis_entries(db_path)

        # Initialize Plaid tokens table
        init_plaid_tokens(db_path)

        # Initialize app_state table for cross-page notifications
        init_app_state(db_path)

    # Populate or repair the derived history cache without touching raw tables.
    recalculate_net_worth_history(db_path=db_path)
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


def init_manual_account_snapshots(db_path: Path = DATABASE_PATH) -> None:
    """
    Create the manual_account_snapshots table and indexes if they don't already exist.

    Safe to call on every startup — all DDL uses IF NOT EXISTS. No data
    is altered when called against an existing populated database.

    Args:
        db_path: Path to the SQLite database file.
    """
    if not ENABLE_DATABASE:
        logger.debug("Database disabled — skipping manual account snapshots init.")
        return

    with _get_connection(db_path) as conn:
        conn.execute(_CREATE_MANUAL_ACCOUNT_SNAPSHOTS_TABLE)
        conn.execute(_CREATE_MANUAL_SNAPSHOT_DATE_INDEX)
        conn.execute(_CREATE_MANUAL_SNAPSHOT_ACCOUNT_INDEX)

    logger.debug("Manual account snapshots table initialized successfully.")


def init_net_worth_history(db_path: Path = DATABASE_PATH) -> None:
    """
    Create the net_worth_history table if it doesn't already exist.

    Safe to call on every startup — all DDL uses IF NOT EXISTS. No data
    is altered when called against an existing populated database.

    Args:
        db_path: Path to the SQLite database file.
    """
    if not ENABLE_DATABASE:
        logger.debug("Database disabled — skipping net worth history init.")
        return

    with _get_connection(db_path) as conn:
        conn.execute(_CREATE_NET_WORTH_HISTORY_TABLE)

    logger.debug("Net worth history table initialized successfully.")


def init_app_state(db_path: Path = DATABASE_PATH) -> None:
    """
    Initialize the app_state table used for tiny cross-page notifications.
    """
    if not ENABLE_DATABASE:
        logger.debug("Database disabled — skipping app_state init.")
        return

    with _get_connection(db_path) as conn:
        conn.execute(_CREATE_APP_STATE_TABLE)

    logger.debug("App state table initialized successfully.")


def init_manual_transactions(db_path: Path = DATABASE_PATH) -> None:
    """
    Create the manual_transactions table if it doesn't already exist.

    Safe to call on every startup — all DDL uses IF NOT EXISTS. No data
    is altered when called against an existing populated database.

    Args:
        db_path: Path to the SQLite database file.
    """
    if not ENABLE_DATABASE:
        logger.debug("Database disabled — skipping manual transactions init.")
        return

    with _get_connection(db_path) as conn:
        conn.execute(_CREATE_MANUAL_TRANSACTIONS_TABLE)


def init_investment_holdings(db_path: Path = DATABASE_PATH) -> None:
    """
    Create the investment_holdings table and indexes if they don't already exist.

    Safe to call on every startup — all DDL uses IF NOT EXISTS. No data
    is altered when called against an existing populated database.

    Args:
        db_path: Path to the SQLite database file.
    """
    if not ENABLE_DATABASE:
        logger.debug("Database disabled — skipping investment holdings init.")
        return

    with _get_connection(db_path) as conn:
        conn.execute(_CREATE_INVESTMENT_HOLDINGS_TABLE)
        conn.execute(_CREATE_INVESTMENTS_ACCOUNT_INDEX)
        conn.execute(_CREATE_INVESTMENTS_DATE_INDEX)
        conn.execute(_CREATE_INVESTMENTS_SYMBOL_INDEX)

    logger.debug("Investment holdings table initialized successfully.")


def init_investment_holdings_history(db_path: Path = DATABASE_PATH) -> None:
    """
    Create the investment_holdings_history table and indexes if they don't already exist.

    Safe to call on every startup — all DDL uses IF NOT EXISTS. No data
    is altered when called against an existing populated database.

    Args:
        db_path: Path to the SQLite database file.
    """
    if not ENABLE_DATABASE:
        logger.debug("Database disabled — skipping investment holdings history init.")
        return

    with _get_connection(db_path) as conn:
        conn.execute(_CREATE_INVESTMENT_HOLDINGS_HISTORY_TABLE)
        conn.execute(_CREATE_INVESTMENTS_HISTORY_DATE_INDEX)
        conn.execute(_CREATE_INVESTMENTS_HISTORY_HOLDING_INDEX)
        conn.execute(_CREATE_INVESTMENTS_HISTORY_SYMBOL_INDEX)

        # Remove any same-day duplicates before creating the unique index.
        # This keeps the latest inserted row for each (snapshot_date, account_id, holding_id).
        conn.execute(
            """
            DELETE FROM investment_holdings_history
            WHERE id NOT IN (
                SELECT MAX(id)
                FROM investment_holdings_history
                GROUP BY snapshot_date, account_id, holding_id
            )
            """
        )

        conn.execute(_CREATE_INVESTMENTS_HISTORY_UNIQUE_INDEX)

    logger.debug("Investment holdings history table initialized successfully.")


def init_investment_transactions(db_path: Path = DATABASE_PATH) -> None:
    """
    Create the investment_transactions table and indexes if they don't already exist.

    Safe to call on every startup — all DDL uses IF NOT EXISTS. No data
    is altered when called against an existing populated database.

    Args:
        db_path: Path to the SQLite database file.
    """
    if not ENABLE_DATABASE:
        logger.debug("Database disabled — skipping investment transactions init.")
        return

    with _get_connection(db_path) as conn:
        conn.execute(_CREATE_INVESTMENT_TRANSACTIONS_TABLE)
        conn.execute(_CREATE_INVESTMENT_TRANSACTIONS_DATE_INDEX)
        conn.execute(_CREATE_INVESTMENT_TRANSACTIONS_ACCOUNT_INDEX)
        conn.execute(_CREATE_INVESTMENT_TRANSACTIONS_SECURITY_INDEX)

    logger.debug("Investment transactions table initialized successfully.")


def upsert_investment_transactions(
    transactions: list[dict], db_path: Path = DATABASE_PATH
) -> dict:
    """
    Batch upsert investment transactions into the investment_transactions table.

    Args:
        transactions: List of transaction dicts with keys matching investment_transactions schema
        db_path: Path to the SQLite database file.

    Returns:
        Dict with keys: written, unchanged, total
    """
    if not ENABLE_DATABASE:
        logger.debug("Database disabled — skipping investment transactions upsert.")
        return {"written": 0, "unchanged": 0, "total": 0}

    if not transactions:
        logger.debug(
            "Empty transaction list — skipping investment transactions upsert."
        )
        return {"written": 0, "unchanged": 0, "total": 0}

    with _get_connection(db_path) as conn:
        written = 0
        for transaction in transactions:
            try:
                conn.execute(
                    """
                    INSERT INTO investment_transactions
                    (transaction_id, account_id, institution, security_id, date, datetime, name,
                     quantity, amount, price, fees, type, subtype, currency, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(transaction_id) DO UPDATE SET
                        date = excluded.date,
                        datetime = excluded.datetime,
                        name = excluded.name,
                        quantity = excluded.quantity,
                        amount = excluded.amount,
                        price = excluded.price,
                        fees = excluded.fees,
                        type = excluded.type,
                        subtype = excluded.subtype,
                        currency = excluded.currency,
                        last_updated = excluded.last_updated
                    """,
                    (
                        transaction.get("transaction_id"),
                        transaction.get("account_id"),
                        transaction.get("institution"),
                        transaction.get("security_id"),
                        transaction.get("date"),
                        transaction.get("datetime"),
                        transaction.get("name"),
                        transaction.get("quantity") or 0,
                        transaction.get("amount") or 0,
                        transaction.get("price") or 0,
                        transaction.get("fees") or 0,
                        transaction.get("type"),
                        transaction.get("subtype"),
                        transaction.get("currency", "USD"),
                        transaction.get("last_updated"),
                    ),
                )
                written += 1
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    f"Failed to upsert investment transaction {transaction.get('transaction_id')}: {e}"
                )

        total = len(transactions)
        unchanged = 0  # With INSERT OR REPLACE, we consider all as written

    logger.info(
        f"Investment transactions upsert complete: {written} written, "
        f"{unchanged} unchanged, {total} total."
    )
    return {"written": written, "unchanged": unchanged, "total": total}


def get_investment_transactions(
    db_path: Path = DATABASE_PATH, start_date: str | None = None, end_date: str | None = None
) -> list[dict]:
    """
    Get investment transactions for analysis.

    Args:
        db_path: Path to the database.
        start_date: Optional start date filter (YYYY-MM-DD)
        end_date: Optional end date filter (YYYY-MM-DD)

    Returns:
        List of transaction dicts ordered by date DESC.
    """
    if not ENABLE_DATABASE:
        logger.debug(
            "Database disabled — get_investment_transactions returning empty list."
        )
        return []

    logger.info(f"Fetching investment transactions from database: {db_path}")

    query = """
        SELECT 
            transaction_id,
            account_id,
            institution,
            security_id,
            date,
            datetime,
            name,
            quantity,
            amount,
            price,
            fees,
            type,
            subtype,
            currency,
            last_updated
        FROM investment_transactions
    """

    params = []
    if start_date:
        query += " WHERE date >= ?"
        params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
    elif end_date:
        query += " WHERE date <= ?"
        params.append(end_date)

    query += " ORDER BY date DESC"

    with _get_connection(db_path) as conn:
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()

    logger.info(f"Retrieved {len(rows)} investment transaction(s) from database.")
    return [dict(row) for row in rows]


def calculate_cost_basis_from_transactions(db_path: Path = DATABASE_PATH) -> dict:
    """
    Calculate total amount invested for each security from transaction history.

    This sums ALL buy transactions for each security to get the total amount invested,
    which is the correct cost basis for recurring investment contributions (like 401k).

    Args:
        db_path: Path to the database.

    Returns:
        Dict mapping security_id to total amount invested (cost basis).
    """
    if not ENABLE_DATABASE:
        logger.debug(
            "Database disabled — calculate_cost_basis_from_transactions returning empty dict."
        )
        return {}

    logger.info("Calculating total amount invested from transaction history")

    amount_invested = {}

    with _get_connection(db_path) as conn:
        # Sum all buy transactions by account_id + security_id to preserve per-holding cost basis.
        cursor = conn.execute(
            """
            SELECT 
                account_id,
                security_id,
                SUM(amount) as total_invested,
                SUM(quantity) as total_quantity,
                COUNT(*) as transaction_count
            FROM investment_transactions
            WHERE type = 'buy'
              AND account_id IS NOT NULL
              AND security_id IS NOT NULL
            GROUP BY account_id, security_id
            """
        )
        rows = cursor.fetchall()

        for row in rows:
            account_id = row["account_id"]
            security_id = row["security_id"]
            total_invested = row["total_invested"] or 0
            total_quantity = row["total_quantity"] or 0
            tx_count = row["transaction_count"] or 0
            holding_id = f"{account_id}_{security_id}"

            amount_invested[holding_id] = {
                "account_id": account_id,
                "security_id": security_id,
                "total_invested": total_invested,
                "total_quantity": total_quantity,
                "transaction_count": tx_count,
            }

        # Also account for sell transactions by subtracting from amount invested per holding.
        cursor = conn.execute(
            """
            SELECT 
                account_id,
                security_id,
                SUM(amount) as total_sold,
                SUM(quantity) as total_quantity_sold
            FROM investment_transactions
            WHERE type = 'sell'
              AND account_id IS NOT NULL
              AND security_id IS NOT NULL
            GROUP BY account_id, security_id
            """
        )
        sell_rows = cursor.fetchall()

        for row in sell_rows:
            account_id = row["account_id"]
            security_id = row["security_id"]
            total_sold = row["total_sold"] or 0
            holding_id = f"{account_id}_{security_id}"

            if holding_id in amount_invested:
                amount_invested[holding_id]["total_invested"] -= total_sold

    logger.info(
        f"Calculated total amount invested for {len(amount_invested)} securities"
    )
    return amount_invested


def upsert_investment_holdings_history(
    holdings: list[dict], db_path: Path = DATABASE_PATH
) -> dict:
    """
    Batch upsert investment holdings into the investment_holdings_history table.

    Creates historical snapshots for performance tracking over time.
    Each sync run creates a new snapshot with the current holdings state.

    Args:
        holdings: List of holding dicts with keys matching investment_holdings schema
        db_path: Path to the SQLite database file.

    Returns:
        Dict with keys: written, unchanged, total
    """
    if not ENABLE_DATABASE:
        logger.debug("Database disabled — skipping investment holdings history upsert.")
        return {"written": 0, "unchanged": 0, "total": 0}

    if not holdings:
        logger.debug(
            "Empty holdings list — skipping investment holdings history upsert."
        )
        return {"written": 0, "unchanged": 0, "total": 0}

    with _get_connection(db_path) as conn:
        written = 0
        for holding in holdings:
            try:
                # Calculate gain/loss metrics
                current_value = holding.get("current_value") or 0
                cost_basis = holding.get("cost_basis") or 0
                gain_loss = current_value - cost_basis
                gain_loss_percent = (
                    (gain_loss / cost_basis * 100) if cost_basis > 0 else 0
                )

                conn.execute(
                    """
                    INSERT INTO investment_holdings_history
                    (holding_id, account_id, institution, security_id, symbol, name,
                     quantity, current_price, current_value, cost_basis, gain_loss, gain_loss_percent,
                     snapshot_date, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(snapshot_date, account_id, holding_id) DO UPDATE SET
                        institution = excluded.institution,
                        security_id = excluded.security_id,
                        symbol = excluded.symbol,
                        name = excluded.name,
                        quantity = excluded.quantity,
                        current_price = excluded.current_price,
                        current_value = excluded.current_value,
                        cost_basis = excluded.cost_basis,
                        gain_loss = excluded.gain_loss,
                        gain_loss_percent = excluded.gain_loss_percent,
                        last_updated = excluded.last_updated
                    """,
                    (
                        holding.get("holding_id"),
                        holding.get("account_id"),
                        holding.get("institution"),
                        holding.get("security_id"),
                        holding.get("symbol"),
                        holding.get("name"),
                        holding.get("quantity") or 0,
                        holding.get("current_price") or 0,
                        holding.get("current_value") or 0,
                        holding.get("cost_basis") or 0,
                        gain_loss,
                        gain_loss_percent,
                        holding.get("snapshot_date"),
                        holding.get("last_updated"),
                    ),
                )
                written += 1
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    f"Failed to upsert investment history holding {holding.get('symbol')}: {e}"
                )

        total = len(holdings)
        unchanged = 0  # With INSERT, we consider all as written

    logger.info(
        f"Investment holdings history upsert complete: {written} written, "
        f"{unchanged} unchanged, {total} total."
    )
    return {"written": written, "unchanged": unchanged, "total": total}


def get_investment_holdings_history(
    db_path: Path = DATABASE_PATH, days: int = 90
) -> list[dict]:
    """
    Get historical investment holdings for performance analysis.

    Args:
        db_path: Path to the database.
        days: Number of days of history to retrieve (default: 90)

    Returns:
        List of historical holding dicts ordered by snapshot_date DESC.
    """
    if not ENABLE_DATABASE:
        logger.debug(
            "Database disabled — get_investment_holdings_history returning empty list."
        )
        return []

    logger.info(f"Fetching investment holdings history from database: {db_path}")

    with _get_connection(db_path) as conn:
        cursor = conn.execute(
            """
            SELECT 
                holding_id,
                account_id,
                institution,
                security_id,
                symbol,
                name,
                quantity,
                current_price,
                current_value,
                cost_basis,
                gain_loss,
                gain_loss_percent,
                snapshot_date,
                last_updated
            FROM investment_holdings_history
            WHERE snapshot_date >= date('now', '-' || ? || ' days')
            ORDER BY snapshot_date DESC, symbol ASC
            """,
            (days,),
        )
        rows = cursor.fetchall()

    logger.info(
        f"Retrieved {len(rows)} historical investment holding(s) from database."
    )
    return [dict(row) for row in rows]


def init_investment_basis_entries(db_path: Path = DATABASE_PATH) -> None:
    """Create the manual investment acquisition-basis table if needed."""
    if not ENABLE_DATABASE:
        logger.debug("Database disabled — skipping investment basis init.")
        return

    with _get_connection(db_path) as conn:
        conn.execute(_CREATE_INVESTMENT_BASIS_ENTRIES_TABLE)
        conn.execute(_CREATE_INVESTMENT_BASIS_INDEX)

    logger.debug("Investment basis entries table initialized successfully.")


def init_plaid_tokens(db_path: Path = DATABASE_PATH) -> None:
    """Create the Plaid tokens table if it doesn't already exist."""
    if not ENABLE_DATABASE:
        logger.debug("Database disabled — skipping Plaid tokens init.")
        return

    with _get_connection(db_path) as conn:
        # If an older plaid_tokens table exists without `profile_name`, migrate it.
        cursor = conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' AND name='plaid_tokens'"
        )
        row = cursor.fetchone()
        if row:
            # Inspect columns
            cols = [
                r["name"]
                for r in conn.execute("PRAGMA table_info('plaid_tokens')").fetchall()
            ]
            if "profile_name" not in cols:
                logger.info(
                    "Migrating existing plaid_tokens table to new schema (adding profile metadata)"
                )
                # Rename old table
                conn.execute("ALTER TABLE plaid_tokens RENAME TO plaid_tokens_old")
                # Create new table
                conn.execute(_CREATE_PLAID_TOKENS_TABLE)
                conn.executescript(_CREATE_PLAID_TOKENS_INDEX)
                # Copy data from old table; set profile_name/profile_prefix defaults
                conn.execute(
                    """
                    INSERT INTO plaid_tokens (profile_name, profile_prefix, institution_name, access_token, item_id, environment, created_at, last_updated, is_active)
                    SELECT 'PRIMARY', 'PLAID', institution_name, access_token, item_id, environment, created_at, last_updated, is_active
                    FROM plaid_tokens_old
                    """
                )
                # Drop old table
                conn.execute("DROP TABLE IF EXISTS plaid_tokens_old")
            else:
                # Table exists and has new schema; ensure indexes exist
                conn.execute(_CREATE_PLAID_TOKENS_TABLE)
                conn.executescript(_CREATE_PLAID_TOKENS_INDEX)
        else:
            # No table exists yet — create it
            conn.execute(_CREATE_PLAID_TOKENS_TABLE)
            conn.executescript(_CREATE_PLAID_TOKENS_INDEX)

    logger.debug("Plaid tokens table initialized/migrated successfully.")


def upsert_plaid_token(
    institution_name: str,
    access_token: str,
    item_id: str | None = None,
    environment: str = "production",
    db_path: Path = DATABASE_PATH,
    profile_name: str = "PRIMARY",
    profile_prefix: str = "PLAID",
    profile_client_id: str | None = None,
    profile_secret: str | None = None,
) -> bool:
    """
    Add or update a Plaid access token in the database.

    Args:
        institution_name: Name of the institution (e.g., ROBINHOOD, CHASE)
        access_token: Plaid access token
        item_id: Plaid item ID (optional)
        environment: Environment (production/sandbox)
        db_path: Path to the database

    Returns:
        True if successful, False otherwise
    """
    if not ENABLE_DATABASE:
        logger.debug("Database disabled — skipping Plaid token upsert.")
        return False

    try:
        with _get_connection(db_path) as conn:
            conn.execute(
                """
                INSERT INTO plaid_tokens (profile_name, profile_prefix,
                                         institution_name, access_token, item_id, environment, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(profile_name, institution_name) DO UPDATE SET
                    access_token = excluded.access_token,
                    item_id = excluded.item_id,
                    environment = excluded.environment,
                    profile_prefix = excluded.profile_prefix,
                    last_updated = excluded.last_updated,
                    is_active = 1
                """,
                (
                    profile_name,
                    profile_prefix,
                    institution_name,
                    access_token,
                    item_id,
                    environment,
                ),
            )
            conn.commit()
        logger.info(f"Plaid token upserted for {institution_name}")
        return True
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to upsert Plaid token for {institution_name}: {e}")
        return False


def get_plaid_tokens(
    db_path: Path = DATABASE_PATH, active_only: bool = True
) -> list[dict]:
    """
    Get all Plaid tokens from the database.

    Args:
        db_path: Path to the database
        active_only: If True, only return active tokens

    Returns:
        List of token dicts
    """
    if not ENABLE_DATABASE:
        logger.debug("Database disabled — returning empty Plaid tokens list.")
        return []

    try:
        with _get_connection(db_path) as conn:
            if active_only:
                cursor = conn.execute(
                    "SELECT profile_name, profile_prefix, institution_name, access_token, item_id, environment, created_at, last_updated FROM plaid_tokens WHERE is_active = 1"
                )
            else:
                cursor = conn.execute(
                    "SELECT profile_name, profile_prefix, institution_name, access_token, item_id, environment, created_at, last_updated, is_active FROM plaid_tokens"
                )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to get Plaid tokens: {e}")
        return []


def delete_plaid_token(institution_name: str, db_path: Path = DATABASE_PATH) -> bool:
    """
    Delete or deactivate a Plaid token.

    Args:
        institution_name: Name of the institution
        db_path: Path to the database

    Returns:
        True if successful, False otherwise
    """
    if not ENABLE_DATABASE:
        logger.debug("Database disabled — skipping Plaid token deletion.")
        return False

    try:
        with _get_connection(db_path) as conn:
            conn.execute(
                "UPDATE plaid_tokens SET is_active = 0 WHERE institution_name = ?",
                (institution_name,),
            )
            conn.commit()
        logger.info(f"Plaid token deactivated for {institution_name}")
        return True
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to delete Plaid token for {institution_name}: {e}")
        return False


def migrate_env_tokens_to_db(
    env_file_path: Path, db_path: Path = DATABASE_PATH
) -> dict:
    """
    Migrate Plaid tokens from .env file to database.

    Args:
        env_file_path: Path to .env file
        db_path: Path to the database

    Returns:
        Dict with migration results
    """
    try:
        from dotenv import load_dotenv

        # Load .env file
        load_dotenv(env_file_path)

        # Ensure plaid_tokens table exists before attempting upserts
        try:
            init_plaid_tokens(db_path)
        except Exception:  # noqa: BLE001
            # If init fails, continue and let upsert errors be handled per-token
            logger.debug("init_plaid_tokens failed or skipped")

        # Get all Plaid tokens from environment
        import os

        plaid_tokens = {}
        for key, value in os.environ.items():
            if (
                key.startswith(("PLAID_", "SECONDARY_PLAID"))
                or key.endswith("_PLAID_TOKEN")
            ) and "TOKEN" in key:
                # Extract institution name from key (format: PLAID_PRODUCTION_TOKEN_INSTITUTIONNAME)
                parts = key.split("_")
                # Determine profile prefix (e.g., 'PLAID' or 'SECONDARY_PLAID')
                if parts[0] == "SECONDARY" and len(parts) >= 2 and parts[1] == "PLAID":
                    profile_prefix = "SECONDARY_PLAID"
                else:
                    profile_prefix = parts[0]

                # Normalize profile name
                if profile_prefix == "PLAID":
                    profile_name = "PRIMARY"
                elif profile_prefix.endswith("_PLAID"):
                    profile_name = profile_prefix[:-6]
                else:
                    profile_name = profile_prefix

                # institution is last part after TOKEN
                if len(parts) >= 4 and parts[-2] == "TOKEN":
                    institution_name = parts[-1]
                    environment = (
                        "sandbox" if "sandbox" in key.lower() else "production"
                    )
                    plaid_tokens[institution_name] = {
                        "access_token": value,
                        "environment": environment,
                        "profile_name": profile_name,
                        "profile_prefix": profile_prefix,
                    }

        migrated_count = 0
        failed_count = 0

        for institution_name, token_data in plaid_tokens.items():
            if upsert_plaid_token(
                institution_name,
                token_data["access_token"],
                environment=token_data["environment"],
                db_path=db_path,
                profile_name=token_data.get("profile_name", "PRIMARY"),
                profile_prefix=token_data.get("profile_prefix", "PLAID"),
            ):
                migrated_count += 1
            else:
                failed_count += 1

        return {
            "success": True,
            "migrated": migrated_count,
            "failed": failed_count,
            "total": len(plaid_tokens),
        }
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to migrate tokens from .env to database: {e}")
        return {
            "success": False,
            "error": str(e),
            "migrated": 0,
            "failed": 0,
            "total": 0,
        }


def upsert_manual_transaction(transaction: dict, db_path: Path = DATABASE_PATH) -> None:
    """
    Insert or update a manual transaction.

    Args:
        transaction: Dict with keys: transaction_id, date, account, description,
                     category, amount
        db_path: Path to the database.
    """
    if not ENABLE_DATABASE:
        logger.debug("Database disabled — skipping manual transaction upsert.")
        return

    # Validate transaction
    is_valid, error_message = validate_manual_transaction(transaction)
    if not is_valid:
        raise ValueError(error_message)

    with _get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO manual_transactions 
            (transaction_id, date, account, description, category, amount)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(transaction_id) DO UPDATE SET
                date = excluded.date,
                account = excluded.account,
                description = excluded.description,
                category = excluded.category,
                amount = excluded.amount,
                last_updated = CURRENT_TIMESTAMP
            """,
            (
                transaction["transaction_id"],
                transaction["date"],
                transaction["account"],
                transaction.get("description", ""),
                transaction.get("category", ""),
                transaction["amount"],
            ),
        )

    logger.debug(f"Upserted manual transaction: {transaction.get('transaction_id')}")


def upsert_investment_holdings(
    holdings: list[dict], db_path: Path = DATABASE_PATH
) -> dict:
    """
    Batch upsert investment holdings into the investment_holdings table.

    Uses holding_id as the primary key for upserts. This allows us to track
    historical snapshots while updating current holdings.

    Args:
        holdings: List of investment holding dicts from Plaid.
        db_path:  Path to the database.

    Returns:
        Dictionary with 'written', 'unchanged', 'total' counts.
    """
    if not ENABLE_DATABASE:
        logger.debug("Database disabled — skipping investment holdings upsert.")
        return {"written": 0, "unchanged": 0, "total": 0}

    if not holdings:
        logger.debug("No investment holdings to upsert.")
        return {"written": 0, "unchanged": 0, "total": 0}

    # Calculate total amount invested from transaction history for holdings missing cost_basis
    amount_invested_map = calculate_cost_basis_from_transactions(db_path)

    with _get_connection(db_path) as conn:
        written = 0
        unchanged = 0

        for holding in holdings:
            # Use calculated amount invested if direct cost_basis is missing
            account_id = holding.get("account_id")
            security_id = holding.get("security_id")
            holding_id = f"{account_id}_{security_id}"
            cost_basis = holding.get("cost_basis", 0)

            if not cost_basis and holding_id in amount_invested_map:
                cost_basis = amount_invested_map[holding_id]["total_invested"]
                logger.debug(
                    f"Using calculated amount invested for {holding_id}: "
                    f"${cost_basis:.2f} ({amount_invested_map[holding_id]['transaction_count']} transactions)"
                )
            elif not cost_basis and security_id in amount_invested_map:
                # Fallback for legacy maps keyed by security_id only.
                cost_basis = amount_invested_map[security_id]["total_invested"]
                logger.debug(
                    f"Using calculated amount invested for security {security_id}: "
                    f"${cost_basis:.2f} ({amount_invested_map[security_id]['transaction_count']} transactions)"
                )

            # Use INSERT OR REPLACE for simple upsert
            conn.execute(
                """
                INSERT INTO investment_holdings
                (holding_id, account_id, institution, security_id, symbol, name,
                 quantity, current_price, current_value, cost_basis, purchase_date, last_updated, snapshot_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(holding_id) DO UPDATE SET
                    account_id = excluded.account_id,
                    institution = excluded.institution,
                    security_id = excluded.security_id,
                    symbol = excluded.symbol,
                    name = excluded.name,
                    quantity = excluded.quantity,
                    current_price = excluded.current_price,
                    current_value = excluded.current_value,
                    cost_basis = excluded.cost_basis,
                    purchase_date = excluded.purchase_date,
                    last_updated = excluded.last_updated,
                    snapshot_date = excluded.snapshot_date
                """,
                (
                    holding.get("holding_id"),
                    holding.get("account_id"),
                    holding.get("institution"),
                    holding.get("security_id"),
                    holding.get("symbol"),
                    holding.get("name"),
                    holding.get("quantity") or 0,
                    holding.get("current_price") or 0,
                    holding.get("current_value") or 0,
                    cost_basis,
                    holding.get("purchase_date"),
                    holding.get("last_updated"),
                    holding.get("snapshot_date"),
                ),
            )
            written += 1

        total = len(holdings)
        unchanged = 0  # With INSERT OR REPLACE, we consider all as written

    logger.info(
        f"Investment holdings upsert complete: {written} written (new or changed), "
        f"{unchanged} unchanged, {total} total."
    )
    return {"written": written, "unchanged": unchanged, "total": total}


def get_investment_holdings(db_path: Path = DATABASE_PATH) -> list[dict]:
    """
    Get current investment holdings from the latest snapshot.

    Args:
        db_path: Path to the database.

    Returns:
        List of investment holding dicts ordered by current_value DESC.
    """
    logger.info(f"ENABLE_DATABASE: {ENABLE_DATABASE}")
    logger.info(f"db_path: {db_path}")
    logger.info(f"Database exists: {db_path.exists()}")

    if not ENABLE_DATABASE:
        logger.debug(
            "Database disabled — get_investment_holdings returning empty list."
        )
        return []

    logger.info(f"Fetching investment holdings from database: {db_path}")

    with _get_connection(db_path) as conn:
        # First check if table exists and has data
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='investment_holdings'"
        )
        table_exists = cursor.fetchone()
        logger.info(f"investment_holdings table exists: {table_exists is not None}")

        if table_exists:
            cursor = conn.execute("SELECT COUNT(*) FROM investment_holdings")
            count = cursor.fetchone()[0]
            logger.info(f"Total investment holdings in database: {count}")

        cursor = conn.execute(
            """
            SELECT 
                institution,
                account_id,
                symbol,
                name,
                quantity,
                current_price,
                current_value,
                cost_basis,
                purchase_date,
                (COALESCE(current_value, 0) - COALESCE(cost_basis, 0)) as gain_loss,
                CASE WHEN COALESCE(cost_basis, 0) > 0 
                    THEN ((COALESCE(current_value, 0) - COALESCE(cost_basis, 0)) / COALESCE(cost_basis, 0)) * 100 
                    ELSE 0 END as gain_loss_percent,
                snapshot_date
            FROM investment_holdings
            ORDER BY current_value DESC
            """
        )
        rows = cursor.fetchall()

    logger.info(f"Retrieved {len(rows)} investment holding(s) from database.")
    return [dict(row) for row in rows]


def get_manual_transactions(db_path: Path = DATABASE_PATH) -> list[dict]:
    """
    Get all manual transactions.

    Args:
        db_path: Path to the database.

    Returns:
        List of manual transaction dicts ordered by date DESC.
    """
    if not ENABLE_DATABASE:
        logger.debug(
            "Database disabled — get_manual_transactions returning empty list."
        )
        return []

    with _get_connection(db_path) as conn:
        cursor = conn.execute(
            """
            SELECT * FROM manual_transactions
            ORDER BY date DESC
            """
        )
        rows = cursor.fetchall()

    logger.debug(f"Retrieved {len(rows)} manual transaction(s).")
    return [dict(row) for row in rows]


def delete_manual_transaction(
    transaction_id: str, db_path: Path = DATABASE_PATH
) -> bool:
    """
    Delete a manual transaction.

    Args:
        transaction_id: ID of the transaction to delete.
        db_path: Path to the database.

    Returns:
        True if successful, False otherwise.
    """
    if not ENABLE_DATABASE:
        logger.debug("Database disabled — skipping manual transaction deletion.")
        return False

    with _get_connection(db_path) as conn:
        conn.execute(
            "DELETE FROM manual_transactions WHERE transaction_id = ?",
            (transaction_id,),
        )

    logger.debug(f"Deleted manual transaction: {transaction_id}")
    return True


def recalculate_net_worth_history(
    from_date: str | None = None, db_path: Path = DATABASE_PATH
) -> dict[str, object]:
    """
    Recalculate net worth history for all dates (or from a specific date forward).

    This is called when manual snapshots are added/updated to ensure net worth
    calculations reflect the new balances for all subsequent dates.

    Args:
        from_date: Optional date string in YYYY-MM-DD format to start recalculating from.
                   If None, recalculates all history.
        db_path: Path to the database.
    """
    if not ENABLE_DATABASE:
        logger.debug("Database disabled — skipping net worth history recalculation.")
        return {"rows_written": 0, "earliest_date": None, "latest_date": None}

    normalized_from = normalize_snapshot_date(from_date) if from_date else None
    today = eastern_today()

    with _get_connection(db_path) as conn:
        if normalized_from:
            conn.execute(
                "DELETE FROM net_worth_history WHERE snapshot_date >= ?",
                (normalized_from,),
            )
        else:
            conn.execute("DELETE FROM net_worth_history")

        conn.execute(
            """
            WITH all_dates AS (
                SELECT snapshot_date FROM account_snapshots
                WHERE snapshot_date <= ?
                UNION
                SELECT snapshot_date FROM manual_account_snapshots
                WHERE snapshot_date <= ?
            ),
            dates_to_build AS (
                SELECT snapshot_date FROM all_dates
                WHERE (? IS NULL OR snapshot_date >= ?)
            ),
            candidates AS (
                SELECT
                    d.snapshot_date AS effective_date,
                    m.account_id,
                    m.account_type,
                    m.current_balance,
                    1 AS source_priority,
                    m.snapshot_date AS source_date
                FROM dates_to_build d
                JOIN manual_account_snapshots m
                  ON m.snapshot_date <= d.snapshot_date
                UNION ALL
                SELECT
                    d.snapshot_date AS effective_date,
                    a.account_id,
                    a.account_type,
                    a.current_balance,
                    0 AS source_priority,
                    a.snapshot_date AS source_date
                FROM dates_to_build d
                JOIN account_snapshots a
                  ON a.snapshot_date <= d.snapshot_date
            ),
            ranked AS (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY effective_date, account_id
                    ORDER BY source_priority DESC, source_date DESC
                ) AS row_number
                FROM candidates
            )
            INSERT INTO net_worth_history (snapshot_date, net_worth, last_updated)
            SELECT
                effective_date,
                SUM(CASE
                    WHEN account_type IN ('depository', 'investment', 'brokerage')
                        THEN COALESCE(current_balance, 0)
                    WHEN account_type IN ('credit', 'loan')
                        THEN -COALESCE(current_balance, 0)
                    ELSE 0
                END),
                ?
            FROM ranked
            WHERE row_number = 1
            GROUP BY effective_date
            ON CONFLICT(snapshot_date) DO UPDATE SET
                net_worth = excluded.net_worth,
                last_updated = excluded.last_updated
            """,
            (today, today, normalized_from, normalized_from, eastern_now_iso()),
        )
        result = conn.execute(
            """
            SELECT COUNT(*) AS rows_written,
                   MIN(snapshot_date) AS earliest_date,
                   MAX(snapshot_date) AS latest_date
            FROM net_worth_history
            """
        ).fetchone()

    logger.debug(f"Net worth history recalculated from {from_date or 'beginning'}.")
    return dict(result)


def get_net_worth_history_status(db_path: Path = DATABASE_PATH) -> dict[str, object]:
    """Report whether source snapshot dates are represented in the history cache."""
    if not ENABLE_DATABASE:
        return {
            "source_dates": 0,
            "history_dates": 0,
            "missing_dates": [],
            "needs_recalculation": False,
        }

    today = eastern_today()
    with _get_connection(db_path) as conn:
        source = conn.execute(
            """
            SELECT DISTINCT snapshot_date
            FROM (
                SELECT snapshot_date FROM account_snapshots
                UNION
                SELECT snapshot_date FROM manual_account_snapshots
            )
            WHERE snapshot_date <= ?
            ORDER BY snapshot_date
            """,
            (today,),
        ).fetchall()
        history = conn.execute(
            """
            SELECT snapshot_date FROM net_worth_history
            WHERE snapshot_date <= ?
            ORDER BY snapshot_date
            """,
            (today,),
        ).fetchall()

    source_dates = {row["snapshot_date"] for row in source}
    history_dates = {row["snapshot_date"] for row in history}
    missing_dates = sorted(source_dates - history_dates)
    return {
        "source_dates": len(source_dates),
        "history_dates": len(history_dates),
        "missing_dates": missing_dates,
        "needs_recalculation": bool(missing_dates),
    }


# ─── Write Operations ──────────────────────────────────────────────────────────

# Smart upsert SQL — defined once to avoid drift.
#
# IMPORTANT: This system preserves all historical data indefinitely.
# Transactions are NEVER automatically deleted based on age.
# Only manual database deletion can remove transactions.
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
#   This allows you to:
#   - Manually categorize one-off transactions that don't fit rules
#   - Edit user_category directly in the database for custom categorization
#   - Set excluded=1 to hide transactions without deleting them
#   - Have these manual edits persist through all future syncs
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
        cursor = conn.execute("SELECT * FROM transactions ORDER BY date DESC")
        rows = cursor.fetchall()

    logger.debug(f"Retrieved {len(rows)} transaction(s) from database.")
    return [dict(row) for row in rows]


def get_transaction_by_id(
    transaction_id: str,
    db_path: Path = DATABASE_PATH,
) -> dict | None:
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
        logger.info(
            "Database disabled — get_transactions_by_date_range returning empty list."
        )
        return []

    with _get_connection(db_path) as conn:
        cursor = conn.execute(
            "SELECT * FROM transactions WHERE date BETWEEN ? AND ? ORDER BY date DESC",
            (start_date, end_date),
        )
        rows = cursor.fetchall()

    logger.debug(
        f"Retrieved {len(rows)} transaction(s) " f"between {start_date} and {end_date}."
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


def get_latest_transaction_date(db_path: Path = DATABASE_PATH) -> str | None:
    """
    Return the ISO 8601 date of the most recent transaction across ALL institutions.

    Args:
        db_path: Path to the database.

    Returns:
        Most recent transaction date as ISO 8601 string (YYYY-MM-DD), or None if
        the database is disabled or empty.
    """
    if not ENABLE_DATABASE:
        logger.info("Database disabled — get_latest_transaction_date returning None.")
        return None

    with _get_connection(db_path) as conn:
        cursor = conn.execute("SELECT MAX(date) FROM transactions")
        result = cursor.fetchone()[0]

    logger.debug(f"Latest transaction date in database: {result or '(empty)'}")
    return result


def get_latest_transaction_date_for_institution(
    institution: str,
    db_path: Path = DATABASE_PATH,
) -> str | None:
    """
    Return the ISO 8601 date of the most recent transaction for a specific institution.

    Used by the per-institution sync logic so that:
      - An institution with existing DB records uses a short rolling window
        (no need to re-download full history every run).
      - A brand-new institution with zero DB records returns None, triggering
        a full initial history fetch regardless of what other institutions have.

    The institution string matches the token key suffix — e.g. 'CHASE' for the
    token stored as PLAID_PRODUCTION_TOKEN_CHASE. This is the same value written
    into the 'institution' column by sync.py.

    Args:
        institution: Institution name as stored in the DB (e.g. 'CHASE', 'AMEX').
        db_path:     Path to the database.

    Returns:
        Most recent transaction date as ISO 8601 string (YYYY-MM-DD), or None if:
          - Database is disabled
          - No transactions exist for this institution (first sync for this account)
    """
    if not ENABLE_DATABASE:
        logger.debug(
            f"Database disabled — get_latest_transaction_date_for_institution "
            f"returning None for '{institution}'."
        )
        return None

    with _get_connection(db_path) as conn:
        cursor = conn.execute(
            "SELECT MAX(date) FROM transactions WHERE institution = ?",
            (institution,),
        )
        result = cursor.fetchone()[0]

    logger.debug(
        f"Latest transaction date for '{institution}': {result or '(none — new institution)'}"
    )
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
        logger.debug(
            f"Database disabled — skipping upsert of {len(snapshots)} snapshot(s)."
        )
        return 0

    if not snapshots:
        logger.debug("upsert_snapshots: received empty list — skipping.")
        return 0

    normalized = []
    for snapshot in snapshots:
        row = dict(snapshot)
        for field, default in (
            ("account_name", ""),
            ("institution", ""),
            ("account_type", ""),
            ("account_subtype", ""),
            ("available_balance", None),
            ("credit_limit", None),
            ("currency", "USD"),
        ):
            row.setdefault(field, default)
        row["snapshot_date"] = normalize_snapshot_date(row["snapshot_date"])
        normalized.append(row)

    with _get_connection(db_path) as conn:
        conn.executemany(_UPSERT_SNAPSHOT_SQL, normalized)

    recalculate_net_worth_history(
        min(row["snapshot_date"] for row in normalized), db_path
    )

    logger.debug(f"Upserted {len(normalized)} account snapshot(s) to SQLite.")
    return len(normalized)


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


def get_latest_manual_snapshots(db_path: Path = DATABASE_PATH) -> list[dict]:
    """
    Return the most recent manual entry for each unique account_id.

    Called once per sync run so the pipeline can stamp the latest manual
    balance with today's date and upsert it into account_snapshots, making
    manual accounts flow through the same Sheets export as Plaid accounts.

    The query uses the same pattern as get_latest_balances() — one row per
    account_id, chosen by MAX(snapshot_date) over the manual table.

    Args:
        db_path: Path to the database.

    Returns:
        List of manual snapshot dicts, one per unique account_id.
        Returns empty list if database is disabled or the table is empty.
    """
    if not ENABLE_DATABASE:
        logger.debug(
            "Database disabled — get_latest_manual_snapshots returning empty list."
        )
        return []

    with _get_connection(db_path) as conn:
        cursor = conn.execute(
            """
            SELECT * FROM manual_account_snapshots
            WHERE (snapshot_date, account_id) IN (
                SELECT snapshot_date, account_id
                FROM manual_account_snapshots
                GROUP BY account_id
                HAVING snapshot_date = MAX(snapshot_date)
            )
            ORDER BY institution, account_name
            """
        )
        rows = cursor.fetchall()

    logger.debug(
        f"Retrieved {len(rows)} latest manual account snapshot(s) "
        f"({len({dict(r)['account_id'] for r in rows})} unique account(s))."
    )
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
    Return the materialized net worth history read model.

    Args:
        db_path: Path to the database.

    Returns:
        List of dicts with keys: snapshot_date, net_worth.
        Ordered by snapshot_date ASC. Returns empty list if database is disabled
        or no snapshots exist.
    """
    if not ENABLE_DATABASE:
        logger.debug("Database disabled — get_net_worth_history returning empty list.")
        return []

    with _get_connection(db_path) as conn:
        cursor = conn.execute(
            """
            SELECT snapshot_date, net_worth
            FROM net_worth_history
            ORDER BY snapshot_date ASC
            """
        )
        rows = cursor.fetchall()

    result = []
    for row in rows:
        result.append(
            {
                "snapshot_date": row["snapshot_date"],
                "net_worth": row["net_worth"] or 0,
            }
        )

    logger.debug(f"Retrieved net worth history for {len(result)} date(s).")
    return result


def get_net_worth_history_summary(
    points: int = 12, db_path: Path = DATABASE_PATH
) -> list[dict]:
    """Return evenly spaced period averages without filling missing dates."""
    if not ENABLE_DATABASE:
        return []
    if points < 1:
        raise ValueError("points must be at least 1")

    history = get_net_worth_history(db_path)
    if not history:
        return []

    history = sorted(history, key=lambda row: row["snapshot_date"])
    start = date.fromisoformat(history[0]["snapshot_date"])
    end = date.fromisoformat(history[-1]["snapshot_date"])
    span_days = (end - start).days + 1
    bucket_count = min(points, max(1, span_days // 7))
    buckets = []

    for index in range(bucket_count):
        bucket_start_offset = (index * span_days) // bucket_count
        bucket_end_offset = (((index + 1) * span_days) // bucket_count) - 1
        bucket_start = start + timedelta(days=bucket_start_offset)
        bucket_end = start + timedelta(days=max(bucket_start_offset, bucket_end_offset))
        values = []
        if bucket_end_offset >= bucket_start_offset:
            values = [
                row["net_worth"]
                for row in history
                if bucket_start.isoformat()
                <= row["snapshot_date"]
                <= bucket_end.isoformat()
            ]
        buckets.append(
            {
                "period_start": bucket_start.isoformat(),
                "period_end": bucket_end.isoformat(),
                "label": (
                    f"{bucket_start.strftime('%b')} {bucket_start.day} - "
                    f"{bucket_end.strftime('%b')} {bucket_end.day}, {bucket_end.year}"
                ),
                "net_worth": round(sum(values) / len(values), 2) if values else None,
                "sample_count": len(values),
            }
        )

    return buckets
