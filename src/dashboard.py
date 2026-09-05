"""
dashboard.py
============
Entry point: run the sync pipeline then serve the web dashboard.

On startup this module runs the full finance sync pipeline (transactions,
balances, CSV exports) with Google Sheets disabled, then starts the Flask
web server so you immediately see up-to-date data.

Serves six pages:
  /            — Main dashboard (summary cards, mini spend table, charts)
  /transactions — Excel-like transactions view with filtering
  /spend       — Full monthly category spend table with date-range filter
  /projections — Projected annual spend / income
  /networth    — Account balances and net worth trend
  /manual      — Manual account snapshots editing

Usage:
    python -m src.dashboard                   # syncs then opens http://localhost:5000
    python -m src.dashboard --no-sync         # skips sync, opens dashboard with existing data
    DASHBOARD_PORT=8080 python -m src.dashboard

To push to Google Sheets instead of opening the dashboard:
    python -m src.google_sheets
"""

import argparse
import csv
import io
import json
import logging
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, render_template, request

# ── Config ────────────────────────────────────────────────────────────────────
from .core.config import DATABASE_PATH, DASHBOARD_PORT
from .modules.database import init_db
from .core.config import ROLLING_SYNC_DAYS

_HERE = Path(__file__).resolve().parent
# Port 5000 is required for Replit's webview; override with DASHBOARD_PORT locally

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)-20s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(
    __name__,
    template_folder=str(_HERE / "templates"),
)


# ── Database helpers ──────────────────────────────────────────────────────────

def _db_exists() -> bool:
    return DATABASE_PATH.exists()


@contextmanager
def _db(write=False):
    """
    Yield a dict-row SQLite connection (read-only URI when DB exists).
    Raises RuntimeError if the database file does not exist yet.
    
    Args:
        write: If True, opens in read-write mode instead of read-only.
    """
    if not _db_exists():
        raise RuntimeError(
            f"Database not found at {DATABASE_PATH}. "
            "Run the sync pipeline (python -m src.main) first."
        )
    mode = "rw" if write else "ro"
    conn = sqlite3.connect(f"file:{DATABASE_PATH}?mode={mode}", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _rows(query: str, params: tuple = (), write: bool = False) -> list[dict]:
    """Run a SELECT and return list of plain dicts. Returns [] if DB missing."""
    try:
        with _db(write=write) as conn:
            cur = conn.execute(query, params)
            return [dict(r) for r in cur.fetchall()]
    except RuntimeError:
        return []
    except sqlite3.OperationalError as e:
        logger.warning(f"Query failed (table may not exist yet): {e}")
        return []


def _scalar(query: str, params: tuple = (), default=None, write: bool = False):
    """Run a SELECT returning a single scalar value. Returns default if DB missing."""
    try:
        with _db(write=write) as conn:
            cur = conn.execute(query, params)
            row = cur.fetchone()
            return row[0] if row and row[0] is not None else default
    except (RuntimeError, sqlite3.OperationalError):
        return default


# ── Amount helpers ────────────────────────────────────────────────────────────
# Database convention: positive amount = money IN (income), negative = money OUT (expense).

def _net_worth_from_accounts(accounts: list[dict]) -> float:
    """
    Compute net worth from a list of account-balance dicts.

    Assets  (depository, investment):  add current_balance
    Liabilities (credit, loan):        subtract current_balance
    """
    nw = 0.0
    for a in accounts:
        t = (a.get("account_type") or "").lower()
        bal = a.get("current_balance") or 0.0
        if t in ("depository", "investment"):
            nw += bal
        elif t in ("credit", "loan"):
            nw -= bal
    return nw


# ── Data queries ──────────────────────────────────────────────────────────────

def _date_range_bounds() -> tuple[str, str]:
    """Return (earliest_month, latest_month) present in the transactions table."""
    earliest = _scalar(
        "SELECT strftime('%Y-%m', MIN(date)) FROM transactions WHERE excluded=0 AND pending=0",
        default="2020-01",
    )
    latest = _scalar(
        "SELECT strftime('%Y-%m', MAX(date)) FROM transactions WHERE excluded=0 AND pending=0",
        default=date.today().strftime("%Y-%m"),
    )
    return earliest, latest


def _current_month() -> str:
    return date.today().strftime("%Y-%m")


def _rolling_month_range() -> tuple[str, str]:
    """
    Get rolling month date range (same day last month to today).
    Simple approach: subtract 30 days for rolling month.

    Returns:
        (start_date, end_date) in YYYY-MM-DD format
    """
    today = date.today()
    # Use 30 days as approximate rolling month
    start_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")
    return start_date, end_date


def _spend_pivot(start_month: str, end_month: str, account_filters: list[str] = None, institution_filters: list[str] = None) -> dict:
    """
    Build a pivot of monthly spend by category (including manual transactions).

    Args:
        start_month: Start month in YYYY-MM format
        end_month: End month in YYYY-MM format
        account_filters: Optional list of account names to filter by (uses account column)
        institution_filters: Optional list of institution names to filter by (uses institution column)

    Returns:
        months         — ordered list of YYYY-MM strings in range
        complete_months— months used for average (excludes partial current month)
        rows           — list of {category, monthly: {YYYY-MM: float}, average: float}
                         sorted by average (spending first, income last)
        net_row        — {monthly: {YYYY-MM: float}, average: float}
    """
    # Build query with optional account and institution filters
    conditions_transactions = []
    conditions_manual = []
    params_transactions = [start_month, end_month]
    params_manual = [start_month, end_month]

    # Account filters (uses account column for both tables)
    if account_filters and len(account_filters) > 0:
        account_placeholders = ','.join(['?' for _ in account_filters])
        conditions_transactions.append(f"account IN ({account_placeholders})")
        conditions_manual.append(f"account IN ({account_placeholders})")
        params_transactions.extend(account_filters)
        params_manual.extend(account_filters)

    # Institution filters (uses institution column for transactions table only)
    if institution_filters and len(institution_filters) > 0:
        institution_placeholders = ','.join(['?' for _ in institution_filters])
        conditions_transactions.append(f"institution IN ({institution_placeholders})")
        params_transactions.extend(institution_filters)

    # Build WHERE clauses
    if conditions_transactions:
        where_clause_transactions = "AND (" + " AND ".join(conditions_transactions) + ")"
    else:
        where_clause_transactions = ""

    if conditions_manual:
        where_clause_manual = "AND (" + " AND ".join(conditions_manual) + ")"
    else:
        where_clause_manual = ""
    
    raw = _rows(
        f"""
        WITH combined_transactions AS (
            SELECT
                strftime('%Y-%m', date)                                            AS month,
                COALESCE(user_category, plaid_category_primary, plaid_category,
                         'Uncategorized')                                          AS category,
                amount                                                            AS amount
            FROM transactions
            WHERE excluded = 0
              AND pending  = 0
              AND strftime('%Y-%m', date) BETWEEN ? AND ?
              {where_clause_transactions}

            UNION ALL

            SELECT
                strftime('%Y-%m', date)                                            AS month,
                COALESCE(category, 'Uncategorized')                                 AS category,
                amount                                                            AS amount
            FROM manual_transactions
            WHERE strftime('%Y-%m', date) BETWEEN ? AND ?
              {where_clause_manual}
        )
        SELECT
            month,
            category,
            SUM(amount) AS total
        FROM combined_transactions
        GROUP BY 1, 2
        """,
        params_transactions + params_manual,
    )

    # Build sorted month list
    month_set: set[str] = {r["month"] for r in raw}
    months = sorted(month_set)

    # Months used for averages: exclude the current (possibly partial) month
    cur = _current_month()
    complete = [m for m in months if m < cur]

    # Pivot: category → {month: total}
    pivot: dict[str, dict[str, float]] = {}
    for r in raw:
        cat = r["category"]
        if cat not in pivot:
            pivot[cat] = {}
        pivot[cat][r["month"]] = r["total"]

    # Build rows
    rows = []
    for cat, monthly in pivot.items():
        avg_vals = [monthly.get(m, 0.0) for m in complete] if complete else list(monthly.values())
        average = sum(avg_vals) / len(avg_vals) if avg_vals else 0.0
        rows.append({"category": cat, "monthly": monthly, "average": average})

    # Sort: highest spend (most negative) first, highest income (most positive) last
    rows.sort(key=lambda r: r["average"])

    # Net row: sum of all categories per month
    net_monthly: dict[str, float] = {}
    for m in months:
        net_monthly[m] = sum(cat_row["monthly"].get(m, 0.0) for cat_row in rows)

    net_avg_vals = [net_monthly.get(m, 0.0) for m in complete] if complete else list(net_monthly.values())
    net_average = sum(net_avg_vals) / len(net_avg_vals) if net_avg_vals else 0.0
    net_row = {"monthly": net_monthly, "average": net_average}

    return {
        "months": months,
        "complete_months": complete,
        "rows": rows,
        "net_row": net_row,
    }


def _get_transactions(
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """
    Get transactions for the transactions view (both Plaid and manual).
    
    Args:
        start_date: Optional start date in YYYY-MM-DD format.
        end_date: Optional end date in YYYY-MM-DD format.
    
    Returns:
        List of transaction dicts with Date, Account, Description, Category, Amount.
    """
    # Get Plaid transactions
    query = """
        SELECT 
            date AS Date,
            COALESCE(account, institution, 'Unknown') AS Account,
            COALESCE(merchant, description, '') AS Description,
            COALESCE(user_category, plaid_category_primary, plaid_category, 'Uncategorized') AS Category,
            amount AS Amount,
            transaction_id,
            last_updated,
            'plaid' as source
        FROM transactions
        WHERE excluded = 0 AND pending = 0
    """
    params = []
    
    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    
    plaid_txns = _rows(query, tuple(params))
    
    # Get manual transactions
    manual_query = """
        SELECT 
            date AS Date,
            account AS Account,
            COALESCE(description, '') AS Description,
            COALESCE(category, 'Uncategorized') AS Category,
            amount AS Amount,
            transaction_id,
            last_updated,
            'manual' as source
        FROM manual_transactions
    """
    manual_params = []
    
    if start_date:
        manual_query += " WHERE date >= ?"
        manual_params.append(start_date)
    
    if end_date:
        if manual_params:
            manual_query += " AND date <= ?"
        else:
            manual_query += " WHERE date <= ?"
        manual_params.append(end_date)
    
    manual_txns = _rows(manual_query, tuple(manual_params))
    
    # Combine and sort by date DESC
    all_txns = plaid_txns + manual_txns
    all_txns.sort(key=lambda x: x["Date"], reverse=True)
    
    return all_txns


def _get_manual_snapshots() -> list[dict]:
    """
    Get all manual account snapshots.
    
    Returns:
        List of all manual snapshot dicts ordered by snapshot_date DESC, account_name.
    """
    return _rows(
        """
        SELECT * FROM manual_account_snapshots
        ORDER BY snapshot_date DESC, account_name
        """
    )


def _add_manual_snapshot(snapshot: dict) -> bool:
    """
    Add or update a manual account snapshot with validation.
    
    Args:
        snapshot: Dict with keys: snapshot_date, account_id, account_name, 
                  institution, account_type, account_subtype, current_balance,
                  available_balance, credit_limit, currency
    
    Returns:
        True if successful, False otherwise.
    """
    from .modules.database import validate_manual_account_snapshot
    
    # Validate snapshot
    is_valid, error_message = validate_manual_account_snapshot(snapshot)
    if not is_valid:
        logger.error(f"Invalid manual snapshot: {error_message}")
        return False
    
    try:
        with _db(write=True) as conn:
            conn.execute(
                """
                INSERT INTO manual_account_snapshots 
                (snapshot_date, account_id, account_name, institution, account_type, 
                 account_subtype, current_balance, available_balance, credit_limit, currency)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(snapshot_date, account_id) 
                DO UPDATE SET
                    account_name = excluded.account_name,
                    institution = excluded.institution,
                    account_type = excluded.account_type,
                    account_subtype = excluded.account_subtype,
                    current_balance = excluded.current_balance,
                    available_balance = excluded.available_balance,
                    credit_limit = excluded.credit_limit,
                    currency = excluded.currency
                """,
                (
                    snapshot["snapshot_date"],
                    snapshot["account_id"],
                    snapshot["account_name"],
                    snapshot.get("institution", ""),
                    snapshot.get("account_type", ""),
                    snapshot.get("account_subtype", ""),
                    snapshot.get("current_balance", 0.0),
                    snapshot.get("available_balance", 0.0),
                    snapshot.get("credit_limit", 0.0),
                    snapshot.get("currency", "USD"),
                ),
            )
            conn.commit()
        
        # Note: Net worth history is calculated on-the-fly in _networth_history()
        # to always include the latest manual snapshots
        
        return True
    except Exception as e:
        logger.error(f"Failed to add manual snapshot: {e}")
        return False


def _delete_manual_snapshot(snapshot_date: str, account_id: str) -> bool:
    """
    Delete a manual account snapshot.
    
    Args:
        snapshot_date: Date string in YYYY-MM-DD format.
        account_id: Account ID.
    
    Returns:
        True if successful, False otherwise.
    """
    try:
        with _db(write=True) as conn:
            conn.execute(
                "DELETE FROM manual_account_snapshots WHERE snapshot_date = ? AND account_id = ?",
                (snapshot_date, account_id),
            )
            conn.commit()
        
        # Note: Net worth history is calculated on-the-fly in _networth_history()
        # to always include the latest manual snapshots
        
        return True
    except Exception as e:
        logger.error(f"Failed to delete manual snapshot: {e}")
        return False


def _current_accounts() -> list[dict]:
    """
    Latest balance for every account (Plaid + manual combined).
    One row per account_id, using the most recent snapshot_date.
    """
    return _rows(
        """
        WITH latest_date AS (
            SELECT MAX(snapshot_date) as max_date FROM account_snapshots
        ),
        manual_forward_fill AS (
            -- Get the latest manual snapshot for each account as of the latest date
            SELECT 
                m.account_id,
                m.account_name,
                m.institution,
                m.account_type,
                m.account_subtype,
                m.current_balance,
                m.available_balance,
                m.credit_limit,
                m.snapshot_date,
                ROW_NUMBER() OVER (
                    PARTITION BY m.account_id
                    ORDER BY m.snapshot_date DESC
                ) AS rn
            FROM manual_account_snapshots m
            WHERE m.snapshot_date <= (SELECT max_date FROM latest_date)
        ),
        latest_manual AS (
            SELECT account_id, account_name, institution, account_type,
                   account_subtype, current_balance, available_balance,
                   credit_limit, snapshot_date
            FROM manual_forward_fill
            WHERE rn = 1
        ),
        combined AS (
            -- Start with Plaid snapshots
            SELECT account_id, account_name, institution, account_type,
                   account_subtype, current_balance, available_balance,
                   credit_limit, snapshot_date, 'plaid' as source
            FROM account_snapshots
            UNION ALL
            -- Add forward-filled manual snapshots
            SELECT account_id, account_name, institution, account_type,
                   account_subtype, current_balance, available_balance,
                   credit_limit, snapshot_date, 'manual' as source
            FROM latest_manual
        ),
        ranked AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY account_id
                       ORDER BY 
                           CASE WHEN source = 'manual' THEN 1 ELSE 0 END DESC,
                           snapshot_date DESC
                   ) AS rn
            FROM combined
        )
        SELECT account_id, account_name, institution, account_type,
               account_subtype, current_balance, available_balance,
               credit_limit, snapshot_date
        FROM ranked
        WHERE rn = 1
        ORDER BY account_type, institution, account_name
        """
    )


def _networth_history() -> list[dict]:
    """
    Daily net worth history with forward-filled manual account values.
    Manual snapshots carry forward by account ID until a new manual snapshot is created.
    """
    # Calculate on-the-fly from both snapshot tables (always up-to-date)
    rows = _rows(
        """
        WITH all_dates AS (
            SELECT DISTINCT snapshot_date FROM account_snapshots
        ),
        manual_by_date AS (
            -- For each date, get the latest manual snapshot for each account on or before that date
            SELECT 
                a.snapshot_date,
                m.account_id,
                m.account_type,
                m.current_balance,
                ROW_NUMBER() OVER (
                    PARTITION BY a.snapshot_date, m.account_id
                    ORDER BY m.snapshot_date DESC
                ) AS rn
            FROM all_dates a
            LEFT JOIN manual_account_snapshots m ON m.snapshot_date <= a.snapshot_date
        ),
        latest_manual_by_date AS (
            SELECT snapshot_date, account_id, account_type, current_balance
            FROM manual_by_date
            WHERE rn = 1
        ),
        combined_balances AS (
            -- Start with Plaid snapshots
            SELECT 
                snapshot_date,
                account_id,
                account_type,
                current_balance,
                'plaid' as source
            FROM account_snapshots
            
            UNION ALL
            
            -- Add forward-filled manual snapshots (replace Plaid for same account_id)
            SELECT snapshot_date, account_id, account_type, current_balance, 'manual' as source
            FROM latest_manual_by_date
            WHERE current_balance IS NOT NULL
        ),
        prioritized AS (
            -- Prioritize manual over plaid for same account_id and date
            SELECT
                snapshot_date,
                account_type,
                current_balance,
                ROW_NUMBER() OVER (
                    PARTITION BY snapshot_date, account_id
                    ORDER BY 
                        CASE WHEN source = 'manual' THEN 1 ELSE 0 END DESC
                ) AS rn
            FROM combined_balances
        ),
        daily_net_worth AS (
            SELECT
                snapshot_date,
                SUM(CASE
                    WHEN account_type IN ('depository', 'investment')
                    THEN COALESCE(current_balance, 0)
                    WHEN account_type IN ('credit', 'loan')
                    THEN -COALESCE(current_balance, 0)
                    ELSE 0
                END) as net_worth
            FROM prioritized
            WHERE rn = 1
            GROUP BY snapshot_date
        )
        SELECT snapshot_date, net_worth
        FROM daily_net_worth
        ORDER BY snapshot_date ASC
        """
    )

    result = []
    for r in rows:
        result.append({"snapshot_date": r["snapshot_date"], "net_worth": round(r["net_worth"], 2)})
    return result


def _summary_cards() -> dict:
    start_date, end_date = _rolling_month_range()
    cur = _current_month()
    
    # Rolling month spend / income (positive=income, negative=expense) - including manual transactions
    month_rows = _rows(
        """
        SELECT SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) AS spend,
               SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS income,
               SUM(amount)                                       AS net
        FROM transactions
        WHERE excluded = 0 AND pending = 0
          AND date >= ? AND date <= ?
        
        UNION ALL
        
        SELECT SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) AS spend,
               SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS income,
               SUM(amount)                                       AS net
        FROM manual_transactions
        WHERE date >= ? AND date <= ?
        """,
        (start_date, end_date, start_date, end_date),
    )
    
    # Aggregate the results
    spend = sum(r.get("spend") or 0.0 for r in month_rows)
    income = sum(r.get("income") or 0.0 for r in month_rows)
    net = sum(r.get("net") or 0.0 for r in month_rows)

    # Current net worth
    accounts = _current_accounts()
    net_worth = _net_worth_from_accounts(accounts)

    # Average monthly net (complete months, last 12) - including manual transactions
    avg_rows = _rows(
        """
        SELECT strftime('%Y-%m', date) AS month, SUM(amount) AS total
        FROM transactions
        WHERE excluded = 0 AND pending = 0
          AND strftime('%Y-%m', date) < ?
        GROUP BY 1
        
        UNION ALL
        
        SELECT strftime('%Y-%m', date) AS month, SUM(amount) AS total
        FROM manual_transactions
        WHERE strftime('%Y-%m', date) < ?
        GROUP BY 1
        """,
        (cur, cur),
    )
    
    # Aggregate by month
    monthly_totals = {}
    for r in avg_rows:
        month = r["month"]
        monthly_totals[month] = monthly_totals.get(month, 0) + r["total"]
    
    avg_net = (
        sum(monthly_totals.values()) / len(monthly_totals) if monthly_totals else 0.0
    )

    last_sync = _scalar(
        "SELECT MAX(last_updated) FROM transactions",
        default=None,
    )

    return {
        "current_month": cur,
        "spend_this_month": round(abs(spend), 2),  # Make spend positive for display
        "income_this_month": round(income, 2),
        "net_this_month": round(net, 2),
        "net_worth": round(net_worth, 2),
        "avg_monthly_net": round(avg_net, 2),
        "last_sync": last_sync,
        "rolling_start_date": start_date,
        "rolling_end_date": end_date,
    }


def _investment_data() -> dict:
    """Return investment accounts, current holdings, history, and activity."""
    accounts = [
        a for a in _current_accounts()
        if (a.get("account_type") or "").lower() == "investment"
    ]
    account_names = {
        a["account_id"]: a.get("account_name") or a["account_id"]
        for a in accounts
    }

    holdings = _rows(
        """
        WITH ranked AS (
            SELECT h.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY h.holding_id
                       ORDER BY h.snapshot_date DESC, h.last_updated DESC
                   ) AS rn
            FROM investment_holdings h
        )
        SELECT holding_id, account_id, institution, security_id, symbol, name,
               quantity, current_price, current_value, cost_basis,
               purchase_date, last_updated, snapshot_date
        FROM ranked
        WHERE rn = 1
        ORDER BY current_value DESC, symbol
        """
    )
    imported_basis = _rows(
        """
        SELECT account_id, security_id,
               SUM(CASE WHEN quantity > 0 THEN quantity ELSE 0 END) AS quantity,
               SUM(CASE WHEN quantity > 0 THEN ABS(amount) ELSE 0 END) AS total_cost
        FROM investment_transactions
        WHERE LOWER(COALESCE(type, '')) IN ('buy', 'reinvestment')
          AND quantity > 0
        GROUP BY account_id, security_id
        """
    )
    imported_by_key = {
        (r["account_id"], r["security_id"]): r for r in imported_basis
    }
    basis_entries = _rows(
        """
        SELECT basis_id, account_id, security_id, symbol, name, quantity,
               total_cost, purchase_date, entry_mode, notes, active,
               created_at, updated_at
        FROM investment_basis_entries
        WHERE active = 1
        ORDER BY symbol, purchase_date, basis_id
        """
    )
    manual_by_key = {}
    for entry in basis_entries:
        key = (entry["account_id"], entry.get("security_id"), entry["symbol"])
        manual_by_key.setdefault(key, []).append(entry)

    for holding in holdings:
        holding["account_name"] = account_names.get(
            holding["account_id"], holding["account_id"]
        )
        quantity = max(holding.get("quantity") or 0, 0)
        current_value = holding.get("current_value") or 0
        price = holding.get("current_price") or (
            current_value / quantity if quantity else 0
        )
        imported = imported_by_key.get((holding["account_id"], holding["security_id"]), {})
        imported_qty = min(quantity, max(imported.get("quantity") or 0, 0))
        imported_cost = max(imported.get("total_cost") or 0, 0)
        key = (holding["account_id"], holding.get("security_id"), holding["symbol"])
        entries = manual_by_key.get(key, [])
        # A security_id can be absent in some imported records, so symbol is
        # also accepted for manual entries where it is the stable identifier.
        if not entries:
            entries = manual_by_key.get((holding["account_id"], None, holding["symbol"]), [])
        overrides = [e for e in entries if e["entry_mode"] == "override"]
        supplements = [e for e in entries if e["entry_mode"] != "override"]

        if overrides:
            manual_qty = sum(max(e["quantity"], 0) for e in overrides)
            manual_cost = sum(max(e["total_cost"], 0) for e in overrides)
            known_qty = min(quantity, manual_qty)
            known_basis = manual_cost * (known_qty / manual_qty) if manual_qty else 0
            basis_source = "manual override"
        else:
            manual_qty = sum(max(e["quantity"], 0) for e in supplements)
            manual_cost = sum(max(e["total_cost"], 0) for e in supplements)
            remaining_qty = max(quantity - imported_qty, 0)
            manual_known_qty = min(remaining_qty, manual_qty)
            manual_known_cost = (
                manual_cost * (manual_known_qty / manual_qty) if manual_qty else 0
            )
            known_qty = imported_qty + manual_known_qty
            known_basis = imported_cost + manual_known_cost
            basis_source = "Plaid + manual" if manual_known_qty else "transactions"

        unknown_qty = max(quantity - known_qty, 0)
        known_value = price * known_qty
        unknown_value = max(current_value - known_value, 0) if quantity else 0
        known_gain_loss = known_value - known_basis
        holding.update({
            "imported_quantity": round(imported_qty, 6),
            "manual_quantity": round(
                max(known_qty - imported_qty, 0) if not overrides else known_qty, 6
            ),
            "known_quantity": round(known_qty, 6),
            "unknown_quantity": round(unknown_qty, 6),
            "known_value": round(known_value, 2),
            "unknown_value": round(unknown_value, 2),
            "known_cost_basis": round(known_basis, 2),
            "known_gain_loss": round(known_gain_loss, 2),
            "known_gain_loss_percent": round(known_gain_loss / known_basis * 100, 2)
            if known_basis else None,
            "basis_source": basis_source if known_qty else "unknown",
        })

    history = _rows(
        """
        WITH ranked AS (
            SELECT h.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY h.holding_id, h.snapshot_date
                       ORDER BY h.last_updated DESC, h.id DESC
                   ) AS rn
            FROM investment_holdings_history h
        )
        SELECT snapshot_date,
               SUM(current_value) AS current_value,
               SUM(cost_basis) AS cost_basis,
               SUM(gain_loss) AS gain_loss
        FROM ranked
        WHERE rn = 1
        GROUP BY snapshot_date
        ORDER BY snapshot_date
        """
    )

    investment_transactions = _rows(
        """
        SELECT transaction_id, account_id, institution, security_id, date,
               datetime, name, quantity, amount, price, fees, type, subtype,
               currency, last_updated
        FROM investment_transactions
        ORDER BY date DESC, datetime DESC, name
        """
    )
    for txn in investment_transactions:
        txn["account_name"] = account_names.get(
            txn["account_id"], txn["account_id"]
        )

    current_value = round(sum(h.get("current_value") or 0 for h in holdings), 2)
    known_value = round(sum(h.get("known_value") or 0 for h in holdings), 2)
    unknown_value = round(sum(h.get("unknown_value") or 0 for h in holdings), 2)
    cost_basis = round(sum(h.get("known_cost_basis") or 0 for h in holdings), 2)
    gain_loss = round(sum(h.get("known_gain_loss") or 0 for h in holdings), 2)
    transaction_amount = round(
        sum(t.get("amount") or 0 for t in investment_transactions), 2
    )
    snapshots = [h.get("snapshot_date") for h in holdings if h.get("snapshot_date")]

    return {
        "summary": {
            "current_value": current_value,
            "cost_basis": cost_basis,
            "gain_loss": gain_loss,
            "gain_loss_percent": round(gain_loss / cost_basis * 100, 2)
            if cost_basis else None,
            "holding_count": len(holdings),
            "account_count": len(accounts),
            "transaction_count": len(investment_transactions),
            "transaction_amount": transaction_amount,
            "as_of": max(snapshots) if snapshots else None,
            "known_value": known_value,
            "unknown_value": unknown_value,
            "basis_coverage_percent": round(known_value / current_value * 100, 2)
            if current_value else 0,
        },
        "accounts": accounts,
        "holdings": holdings,
        "history": history,
        "transactions": investment_transactions,
        "basis_entries": basis_entries,
    }


def _projections(lookback_months: int = 12) -> dict:
    """
    Project annual spend/income per category based on the last N complete months.
    """
    cur = _current_month()
    rows = _rows(
        f"""
        SELECT
            strftime('%Y-%m', date)                                            AS month,
            COALESCE(user_category, plaid_category_primary, plaid_category,
                     'Uncategorized')                                          AS category,
            SUM(amount)                                                        AS total
        FROM transactions
        WHERE excluded = 0
          AND pending  = 0
          AND strftime('%Y-%m', date) < ?
        GROUP BY 1, 2
        
        UNION ALL
        
        SELECT
            strftime('%Y-%m', date)                                            AS month,
            COALESCE(category, 'Uncategorized')                                 AS category,
            SUM(amount)                                                        AS total
        FROM manual_transactions
        WHERE strftime('%Y-%m', date) < ?
        GROUP BY 1, 2
        ORDER BY 1 DESC
        """,
        (cur, cur),
    )

    # Keep only the most recent lookback_months of data
    months_seen: list[str] = []
    for r in rows:
        if r["month"] not in months_seen:
            months_seen.append(r["month"])
    keep_months = set(months_seen[:lookback_months])
    rows = [r for r in rows if r["month"] in keep_months]
    n = len(keep_months) or 1

    # Aggregate by month
    pivot: dict[str, dict[str, float]] = {}
    for r in rows:
        cat = r["category"]
        month = r["month"]
        if cat not in pivot:
            pivot[cat] = {}
        pivot[cat][month] = pivot[cat].get(month, 0) + r["total"]

    projections = []
    for cat, monthly in pivot.items():
        avg = sum(monthly.values()) / n
        projections.append(
            {
                "category": cat,
                "avg_monthly": round(avg, 2),
                "projected_annual": round(avg * 12, 2),
            }
        )
    projections.sort(key=lambda x: x["projected_annual"])

    total_spend_proj = sum(
        p["projected_annual"] for p in projections if p["projected_annual"] < 0
    )
    total_income_proj = sum(
        p["projected_annual"] for p in projections if p["projected_annual"] > 0
    )

    return {
        "lookback_months": n,
        "rows": projections,
        "total_projected_spend": round(abs(total_spend_proj), 2),
        "total_projected_income": round(total_income_proj, 2),
        "projected_net": round(total_income_proj + total_spend_proj, 2),
    }


# ── Favicon (suppress 404 in browser console) ─────────────────────────────────

@app.route("/favicon.ico")
def favicon():
    return Response(status=204)


# ── Page routes ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/spend")
def spend():
    earliest, latest = _date_range_bounds()
    
    # Set default start date to June 2025
    from datetime import datetime
    default_start = "2025-06"
    
    # Use current date as default end date
    current_year = datetime.now().year
    current_month = datetime.now().month
    default_end = f"{current_year}-{current_month:02d}"
    
    return render_template("spend.html", earliest=default_start, latest=default_end)


@app.route("/investments")
def investments():
    """Investment portfolio and performance page."""
    return render_template("investments.html")


@app.route("/projections")
def projections():
    return render_template("projections.html")


@app.route("/transactions")
def transactions():
    return render_template("transactions.html")


@app.route("/manual")
def manual():
    return render_template("manual.html")


@app.route("/networth")
def networth():
    return render_template("networth.html")


# ── API routes ────────────────────────────────────────────────────────────────

@app.route("/api/summary")
def api_summary():
    summary = _summary_cards()
    investment = _investment_data()["summary"]
    summary["investments"] = investment
    return jsonify(summary)


@app.route("/api/spend/monthly")
def api_spend_monthly():
    earliest, latest = _date_range_bounds()
    start = request.args.get("start", earliest)
    end = request.args.get("end", latest)

    # Handle multiple account filters from query parameters
    account_filters = request.args.getlist("account")
    if account_filters:
        account_filters = [a for a in account_filters if a]  # Filter out empty strings

    # Handle multiple institution filters from query parameters
    institution_filters = request.args.getlist("institution")
    if institution_filters:
        institution_filters = [i for i in institution_filters if i]  # Filter out empty strings

    pivot = _spend_pivot(start, end,
                        account_filters if account_filters else None,
                        institution_filters if institution_filters else None)
    return jsonify(pivot)


@app.route("/api/accounts")
def api_accounts():
    """Get list of unique account names for filtering (using account column)."""
    try:
        accounts = _rows(
            """
            SELECT account AS account_name FROM transactions
            WHERE excluded = 0 AND pending = 0 AND account IS NOT NULL AND account != ''

            UNION

            SELECT account AS account_name FROM manual_transactions
            WHERE account IS NOT NULL AND account != ''
            ORDER BY account_name
            """
        )
        result = [a["account_name"] for a in accounts if a["account_name"]]
        logger.info(f"Returning {len(result)} accounts: {result}")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting accounts: {e}")
        return jsonify([])


@app.route("/api/institutions")
def api_institutions():
    """Get list of unique institution names for filtering."""
    try:
        institutions = _rows(
            """
            SELECT DISTINCT institution AS institution_name
            FROM transactions
            WHERE excluded = 0 AND pending = 0 AND institution IS NOT NULL AND institution != ''
            ORDER BY institution_name
            """
        )
        result = [i["institution_name"] for i in institutions if i["institution_name"]]
        logger.info(f"Returning {len(result)} institutions: {result}")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting institutions: {e}")
        return jsonify([])


@app.route("/api/networth/current")
def api_networth_current():
    try:
        accounts = _current_accounts()
        net_worth = _net_worth_from_accounts(accounts)
        assets = sum(
            a["current_balance"] or 0
            for a in accounts
            if (a.get("account_type") or "").lower() in ("depository", "investment")
        )
        liabilities = sum(
            a["current_balance"] or 0
            for a in accounts
            if (a.get("account_type") or "").lower() in ("credit", "loan")
        )
        return jsonify(
            {
                "net_worth": round(net_worth, 2),
                "total_assets": round(assets, 2),
                "total_liabilities": round(liabilities, 2),
                "accounts": accounts,
            }
        )
    except Exception as e:
        logger.error(f"Error in api_networth_current: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/networth/history")
def api_networth_history():
    """Get daily net worth history with forward-filled manual account values."""
    try:
        return jsonify(_networth_history())
    except Exception as e:
        logger.error(f"Error in api_networth_history: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/networth/daily")
def api_networth_daily():
    """Get daily net worth history with forward-filled manual account values."""
    rows = _rows(
        """
        WITH all_dates AS (
            SELECT DISTINCT snapshot_date FROM account_snapshots
        ),
        manual_by_date AS (
            -- For each date, get the latest manual snapshot for each account on or before that date
            SELECT 
                a.snapshot_date,
                m.account_id,
                m.account_type,
                m.current_balance,
                ROW_NUMBER() OVER (
                    PARTITION BY a.snapshot_date, m.account_id
                    ORDER BY m.snapshot_date DESC
                ) AS rn
            FROM all_dates a
            LEFT JOIN manual_account_snapshots m ON m.snapshot_date <= a.snapshot_date
        ),
        latest_manual_by_date AS (
            SELECT snapshot_date, account_id, account_type, current_balance
            FROM manual_by_date
            WHERE rn = 1
        ),
        combined_balances AS (
            -- Start with Plaid snapshots
            SELECT 
                snapshot_date,
                account_id,
                account_type,
                current_balance,
                'plaid' as source
            FROM account_snapshots
            
            UNION ALL
            
            -- Add forward-filled manual snapshots (replace Plaid for same account_id)
            SELECT snapshot_date, account_id, account_type, current_balance, 'manual' as source
            FROM latest_manual_by_date
            WHERE current_balance IS NOT NULL
        ),
        prioritized AS (
            -- Prioritize manual over plaid for same account_id and date
            SELECT
                snapshot_date,
                account_type,
                current_balance,
                ROW_NUMBER() OVER (
                    PARTITION BY snapshot_date, account_id
                    ORDER BY 
                        CASE WHEN source = 'manual' THEN 1 ELSE 0 END DESC
                ) AS rn
            FROM combined_balances
        ),
        daily_net_worth AS (
            SELECT
                snapshot_date,
                SUM(CASE
                    WHEN account_type IN ('depository', 'investment')
                    THEN COALESCE(current_balance, 0)
                    WHEN account_type IN ('credit', 'loan')
                    THEN -COALESCE(current_balance, 0)
                    ELSE 0
                END) as net_worth
            FROM prioritized
            WHERE rn = 1
            GROUP BY snapshot_date
        )
        SELECT snapshot_date, net_worth
        FROM daily_net_worth
        ORDER BY snapshot_date DESC
        """
    )
    
    result = []
    for r in rows:
        result.append({
            "snapshot_date": r["snapshot_date"],
            "net_worth": round(r["net_worth"], 2)
        })
    return jsonify(result)


@app.route("/api/investments/history")
def api_investments_history():
    """Get historical investment holdings for performance analysis."""
    try:
        from .modules.database import get_investment_holdings_history
        from .core.config import ENABLE_DATABASE
        
        days = request.args.get('days', 90, type=int)
        
        logger.info(f"Fetching investment history for last {days} days")
        
        history = get_investment_holdings_history(days=days)
        logger.info(f"Retrieved {len(history)} historical investment records")
        
        # Group by snapshot date for time series
        by_date = {}
        for h in history:
            date = h.get('snapshot_date')
            if date not in by_date:
                by_date[date] = {
                    'total_value': 0,
                    'total_cost': 0,
                    'total_gain': 0,
                    'total_gain_percent': 0,
                    'count': 0,
                    'institutions': set()
                }
            
            by_date[date]['total_value'] += h.get('current_value') or 0
            by_date[date]['total_cost'] += h.get('cost_basis') or 0
            by_date[date]['count'] += 1
            by_date[date]['institutions'].add(h.get('institution') or 'Unknown')
        
        # Calculate daily metrics
        for date in by_date:
            by_date[date]['total_gain'] = by_date[date]['total_value'] - by_date[date]['total_cost']
            by_date[date]['total_gain_percent'] = (
                (by_date[date]['total_gain'] / by_date[date]['total_cost'] * 100) 
                if by_date[date]['total_cost'] > 0 else 0
            )
            by_date[date]['institutions'] = list(by_date[date]['institutions'])
        
        # Convert to sorted list
        time_series = sorted(
            [{'date': date, **metrics} for date, metrics in by_date.items()],
            key=lambda x: x['date']
        )
        
        return jsonify({
            'history': history,
            'time_series': time_series,
            'days': days,
            'total_records': len(history)
        })
    except Exception as e:
        logger.exception("Failed to fetch investment history")
        return jsonify({
            'history': [],
            'time_series': [],
            'days': days,
            'total_records': 0
        })


@app.route("/api/investments/transactions")
def api_investment_transactions():
    """Get investment transactions for analysis and cost basis verification."""
    try:
        from .modules.database import get_investment_transactions
        from .core.config import ENABLE_DATABASE

        security_id = request.args.get('security_id')
        symbol = request.args.get('symbol')
        
        logger.info(f"Fetching investment transactions - security_id: {security_id}, symbol: {symbol}")

        if not ENABLE_DATABASE:
            return jsonify({
                'transactions': [],
                'total_count': 0,
                'filtered_by': None
            })

        transactions = get_investment_transactions()
        
        # Filter by security_id or symbol if provided
        if security_id:
            transactions = [t for t in transactions if t.get('security_id') == security_id]
            filtered_by = f"security_id: {security_id}"
        elif symbol:
            # Need to get security_id from holdings first
            holdings = get_investment_holdings()
            matching_security_ids = [h['security_id'] for h in holdings if h.get('symbol') == symbol]
            if matching_security_ids:
                transactions = [t for t in transactions if t.get('security_id') in matching_security_ids]
                filtered_by = f"symbol: {symbol}"
            else:
                transactions = []
                filtered_by = f"symbol: {symbol} (no matches)"
        else:
            filtered_by = None

        # Calculate summary statistics
        summary = {
            'total_transactions': len(transactions),
            'total_amount_invested': sum(t.get('amount', 0) for t in transactions if t.get('type') == 'buy'),
            'total_amount_sold': sum(t.get('amount', 0) for t in transactions if t.get('type') == 'sell'),
            'total_quantity_bought': sum(t.get('quantity', 0) for t in transactions if t.get('type') == 'buy'),
            'total_quantity_sold': sum(t.get('quantity', 0) for t in transactions if t.get('type') == 'sell'),
            'date_range': {
                'first': min((t.get('date') for t in transactions), default=None),
                'last': max((t.get('date') for t in transactions), default=None)
            }
        }

        return jsonify({
            'transactions': transactions,
            'summary': summary,
            'filtered_by': filtered_by,
            'total_count': len(transactions)
        })

    except Exception as e:
        logger.exception("Failed to fetch investment transactions")
        return jsonify({
            'transactions': [],
            'summary': {},
            'filtered_by': None,
            'total_count': 0,
            'error': str(e)
        })


@app.route("/api/investments/performance")
def api_investments_performance():
    """Get investment performance history over time."""
    lookback_days = int(request.args.get("days", 90))
    
    rows = _rows(
        """
        SELECT 
            snapshot_date,
            institution,
            SUM(current_value) as total_value,
            SUM(cost_basis) as total_cost,
            SUM(current_value - cost_basis) as total_gain,
            CASE WHEN SUM(cost_basis) > 0 
                THEN (SUM(current_value - cost_basis) / SUM(cost_basis)) * 100 
                ELSE 0 END as gain_percent
        FROM investment_holdings
        WHERE snapshot_date >= date('now', '-' || ? || ' days')
        GROUP BY snapshot_date, institution
        ORDER BY snapshot_date ASC
        """,
        (lookback_days,)
    )
    
    # Also get overall performance by date
    overall = _rows(
        """
        SELECT 
            snapshot_date,
            SUM(current_value) as total_value,
            SUM(cost_basis) as total_cost,
            SUM(current_value - cost_basis) as total_gain,
            CASE WHEN SUM(cost_basis) > 0 
                THEN (SUM(current_value - cost_basis) / SUM(cost_basis)) * 100 
                ELSE 0 END as gain_percent
        FROM investment_holdings
        WHERE snapshot_date >= date('now', '-' || ? || ' days')
        GROUP BY snapshot_date
        ORDER BY snapshot_date ASC
        """,
        (lookback_days,)
    )
    
    return jsonify({
        'by_institution': rows,
        'overall': overall
    })


@app.route("/api/transactions")
def api_transactions():
    """Get transactions for the transactions view."""
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    return jsonify(_get_transactions(start_date, end_date))


@app.route("/api/investments")
def api_investments():
    """Return investment accounts, current holdings, history, and activity."""
    try:
        return jsonify(_investment_data())
    except Exception as e:
        logger.exception("Error in api_investments")
        return jsonify({"error": str(e)}), 500


@app.route("/api/investment/basis", methods=["POST"])
def api_add_investment_basis():
    """Add a manual acquisition-basis lot or aggregate entry."""
    data = request.get_json(silent=True) or {}
    required = ("account_id", "symbol", "quantity", "total_cost")
    if any(data.get(key) in (None, "") for key in required):
        return jsonify({"error": "account_id, symbol, quantity, and total_cost are required"}), 400

    try:
        quantity = float(data["quantity"])
        total_cost = float(data["total_cost"])
    except (TypeError, ValueError):
        return jsonify({"error": "quantity and total_cost must be numbers"}), 400
    if quantity <= 0 or total_cost < 0:
        return jsonify({"error": "quantity must be positive and total_cost cannot be negative"}), 400

    entry_mode = data.get("entry_mode", "supplement")
    if entry_mode not in ("supplement", "override"):
        return jsonify({"error": "entry_mode must be supplement or override"}), 400

    try:
        init_db()
        with _db(write=True) as conn:
            cur = conn.execute(
                """
                INSERT INTO investment_basis_entries
                    (account_id, security_id, symbol, name, quantity, total_cost,
                     purchase_date, entry_mode, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(data["account_id"]),
                    data.get("security_id") or None,
                    str(data["symbol"]),
                    data.get("name"),
                    quantity,
                    total_cost,
                    data.get("purchase_date") or None,
                    entry_mode,
                    data.get("notes"),
                ),
            )
            basis_id = cur.lastrowid
            conn.commit()
        return jsonify({"success": True, "basis_id": basis_id}), 201
    except Exception as e:
        logger.exception("Error adding investment basis entry")
        return jsonify({"error": str(e)}), 500


@app.route("/api/investment/basis/<int:basis_id>", methods=["DELETE"])
def api_delete_investment_basis(basis_id: int):
    """Remove a manual basis entry, restoring imported data where applicable."""
    try:
        with _db(write=True) as conn:
            cur = conn.execute(
                "DELETE FROM investment_basis_entries WHERE basis_id = ?",
                (basis_id,),
            )
            conn.commit()
        if cur.rowcount == 0:
            return jsonify({"error": "Basis entry not found"}), 404
        return jsonify({"success": True})
    except Exception as e:
        logger.exception("Error deleting investment basis entry")
        return jsonify({"error": str(e)}), 500


@app.route("/api/transaction/update", methods=["POST"])
def api_update_transaction():
    """Update transaction description, category, or exclusion status."""
    data = request.json
    if not data or "transaction_id" not in data:
        return jsonify({"error": "Missing transaction_id"}), 400
    
    transaction_id = data["transaction_id"]
    updates = {}
    
    if "description" in data:
        updates["description"] = data["description"]
    if "category" in data:
        updates["user_category"] = data["category"]
    if "excluded" in data:
        updates["excluded"] = data["excluded"]
    
    if not updates:
        return jsonify({"error": "No fields to update"}), 400
    
    try:
        with _db(write=True) as conn:
            set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
            values = list(updates.values()) + [transaction_id]
            
            conn.execute(
                f"UPDATE transactions SET {set_clause}, last_updated = datetime('now') WHERE transaction_id = ?",
                values
            )
            conn.commit()
        
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Failed to update transaction: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/manual/transactions")
def api_manual_transactions():
    """Get all manual transactions."""
    from .modules.database import get_manual_transactions
    return jsonify(get_manual_transactions())


@app.route("/api/manual/transaction", methods=["POST"])
def api_add_manual_transaction():
    """Add or update a manual transaction with validation."""
    from .modules.database import upsert_manual_transaction
    
    data = request.json
    if not data or "date" not in data or "amount" not in data:
        return jsonify({"error": "Missing required fields"}), 400
    
    # Generate transaction_id if not provided
    if "transaction_id" not in data:
        data["transaction_id"] = f"manual_{uuid.uuid4().hex[:16]}"
    
    try:
        upsert_manual_transaction(data)
        return jsonify({"success": True, "transaction_id": data["transaction_id"]})
    except ValueError as e:
        # Validation error from validate_manual_transaction
        logger.error(f"Validation error adding manual transaction: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Failed to add manual transaction: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/manual/transaction", methods=["PUT"])
def api_update_manual_transaction():
    """Update a manual transaction (all fields editable) with validation."""
    from .modules.database import upsert_manual_transaction
    
    data = request.json
    if not data or "transaction_id" not in data:
        return jsonify({"error": "Missing transaction_id"}), 400
    
    try:
        upsert_manual_transaction(data)
        return jsonify({"success": True})
    except ValueError as e:
        # Validation error from validate_manual_transaction
        logger.error(f"Validation error updating manual transaction: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Failed to update manual transaction: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/manual/transaction", methods=["DELETE"])
def api_delete_manual_transaction():
    """Delete a manual transaction."""
    from .modules.database import delete_manual_transaction
    
    transaction_id = request.args.get("transaction_id")
    if not transaction_id:
        return jsonify({"error": "Missing transaction_id"}), 400
    
    try:
        delete_manual_transaction(transaction_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Failed to delete manual transaction: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/manual/csv-upload", methods=["POST"])
def api_csv_upload():
    """Upload CSV file for bulk manual transaction import with validation and format conversion."""
    from .modules.database import upsert_manual_transaction, validate_manual_transaction
    from datetime import datetime
    
    if 'csv_file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files['csv_file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    if not file.filename.endswith('.csv'):
        return jsonify({"error": "File must be a CSV"}), 400
    
    try:
        # Read CSV file
        stream = io.StringIO(file.stream.read().decode('utf-8'))
        csv_reader = csv.reader(stream)
        
        # Skip header row (case-insensitive column matching)
        header = next(csv_reader, None)
        if not header:
            return jsonify({"error": "CSV file is empty"}), 400
        
        # Create case-insensitive column mapping
        column_map = {col.lower().strip(): i for i, col in enumerate(header)}
        
        # Find column indices
        date_idx = column_map.get('date')
        account_idx = column_map.get('account')
        description_idx = column_map.get('description')
        category_idx = column_map.get('category')
        amount_idx = column_map.get('amount')
        
        if None in [date_idx, account_idx, description_idx, category_idx, amount_idx]:
            return jsonify({"error": f"Missing required columns. Found: {list(column_map.keys())}"}), 400
        
        count = 0
        errors = []
        
        for row_num, row in enumerate(csv_reader, start=1):
            if len(row) < 5:
                errors.append(f"Row {row_num}: Missing required columns")
                continue
            
            try:
                # Parse date from MM/DD/YYYY to YYYY-MM-DD
                date_str = row[date_idx].strip()
                try:
                    date_obj = datetime.strptime(date_str, '%m/%d/%Y')
                    formatted_date = date_obj.strftime('%Y-%m-%d')
                except ValueError:
                    # Try YYYY-MM-DD format as fallback
                    try:
                        datetime.strptime(date_str, '%Y-%m-%d')
                        formatted_date = date_str
                    except ValueError:
                        errors.append(f"Row {row_num}: Invalid date format: {date_str}. Expected MM/DD/YYYY or YYYY-MM-DD")
                        continue
                
                # Parse amount (remove $ and convert to float)
                amount_str = row[amount_idx].strip()
                try:
                    # Remove dollar sign and convert
                    amount_str = amount_str.replace('$', '').replace(',', '').strip()
                    amount = float(amount_str)
                    if amount == 0:
                        errors.append(f"Row {row_num}: Amount cannot be zero")
                        continue
                except ValueError:
                    errors.append(f"Row {row_num}: Invalid amount: {row[amount_idx]}")
                    continue
                
                transaction = {
                    'date': formatted_date,
                    'account': row[account_idx].strip(),
                    'description': row[description_idx].strip(),
                    'category': row[category_idx].strip(),
                    'amount': amount
                }
                
                # Generate transaction_id
                transaction['transaction_id'] = f"manual_{uuid.uuid4().hex[:16]}"
                
                # Validate transaction
                is_valid, error_message = validate_manual_transaction(transaction)
                if not is_valid:
                    errors.append(f"Row {row_num}: {error_message}")
                    continue
                
                upsert_manual_transaction(transaction)
                count += 1
                
            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")
        
        if errors:
            return jsonify({
                "success": True, 
                "count": count,
                "warnings": f"Imported {count} transactions with {len(errors)} errors: {'; '.join(errors[:5])}"
            })
        
        return jsonify({"success": True, "count": count})
        
    except Exception as e:
        logger.error(f"Failed to process CSV upload: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/manual/snapshots")
def api_manual_snapshots():
    """Get all manual account snapshots."""
    return jsonify(_get_manual_snapshots())


@app.route("/api/manual/snapshot", methods=["POST"])
def api_add_manual_snapshot():
    """Add or update a manual account snapshot with validation."""
    data = request.json
    if not data or "snapshot_date" not in data or "account_id" not in data:
        return jsonify({"error": "Missing required fields"}), 400
    
    if _add_manual_snapshot(data):
        return jsonify({"success": True})
    else:
        return jsonify({"error": "Failed to add snapshot"}), 500


@app.route("/api/manual/snapshot", methods=["DELETE"])
def api_delete_manual_snapshot():
    """Delete a manual account snapshot."""
    snapshot_date = request.args.get("snapshot_date")
    account_id = request.args.get("account_id")
    
    if not snapshot_date or not account_id:
        return jsonify({"error": "Missing required parameters"}), 400
    
    if _delete_manual_snapshot(snapshot_date, account_id):
        return jsonify({"success": True})
    else:
        return jsonify({"error": "Failed to delete snapshot"}), 500


@app.route("/api/projections")
def api_projections():
    lookback = int(request.args.get("months", 12))
    return jsonify(_projections(lookback))


# ── Entry point ───────────────────────────────────────────────────────────────

def _print_startup():
    print("\n" + "=" * 60)
    print("  Finance Sync — Dashboard")
    print("=" * 60)
    print(f"\n  Open:  http://localhost:{DASHBOARD_PORT}")
    print(f"  DB:    {DATABASE_PATH}")
    print("\n  Press Ctrl+C to stop.\n")


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Finance Sync Dashboard")
    parser.add_argument("--no-sync", action="store_true", 
                       help="Skip data sync and start dashboard with existing data")
    parser.add_argument("--sync-transactions", action="store_true",
                       help="Only sync transactions (skip investments)")
    parser.add_argument("--sync-investments", action="store_true",
                       help="Only sync investments (skip transactions)")
    args = parser.parse_args()
    
    # ── Run the sync pipeline first (unless --no-sync is specified) ─────────────────────
    if not args.no_sync:
        # Import here (not at module top) to avoid circular imports with config.
        from .main import run_pipeline  # noqa: PLC0415

        print("\n" + "=" * 60)
        print("  Finance Sync — Syncing data before dashboard start…")
        print("=" * 60 + "\n")

        # Set environment variables for selective sync
        import os
        sync_transactions = True
        sync_investments = True
        
        if args.sync_transactions:
            sync_transactions = True
            sync_investments = False
            print("  Selective sync: Transactions only")
        elif args.sync_investments:
            sync_transactions = False
            sync_investments = True
            print("  Selective sync: Investments only")

        try:
            run_pipeline(enable_sheets=False, sync_transactions=sync_transactions, sync_investments=sync_investments)
        except SystemExit as exc:
            # run_pipeline calls sys.exit(1) on fatal pipeline errors.
            # We still want to start the dashboard so the user can see whatever
            # data is already in the DB, but we surface the failure clearly.
            if exc.code != 0:
                print(
                    "\n  ⚠️  Pipeline exited with an error — starting dashboard "
                    "with existing database data.\n"
                )
        except Exception:
            logger.exception(
                "Pipeline raised an unexpected error — starting dashboard "
                "with existing database data."
            )
    else:
        print("\n" + "=" * 60)
        print("  Finance Sync — Skipping data sync, starting dashboard…")
        print("=" * 60 + "\n")

    # ── Start the web server ──────────────────────────────────────────────────
    _print_startup()
    app.run(host="0.0.0.0", port=DASHBOARD_PORT, debug=False)
