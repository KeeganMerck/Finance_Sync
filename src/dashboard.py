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
from .core.config import DATABASE_PATH
from .core.config import ROLLING_SYNC_DAYS

_HERE = Path(__file__).resolve().parent
# Port 5000 is required for Replit's webview; override with DASHBOARD_PORT locally
DASHBOARD_PORT = int(os.environ.get("DASHBOARD_PORT", 5000))

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


def _spend_pivot(start_month: str, end_month: str) -> dict:
    """
    Build a pivot of monthly spend by category (including manual transactions).

    Returns:
        months         — ordered list of YYYY-MM strings in range
        complete_months— months used for average (excludes partial current month)
        rows           — list of {category, monthly: {YYYY-MM: float}, average: float}
                         sorted by average (spending first, income last)
        net_row        — {monthly: {YYYY-MM: float}, average: float}
    """
    raw = _rows(
        """
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
            
            UNION ALL
            
            SELECT
                strftime('%Y-%m', date)                                            AS month,
                COALESCE(category, 'Uncategorized')                                 AS category,
                amount                                                            AS amount
            FROM manual_transactions
            WHERE strftime('%Y-%m', date) BETWEEN ? AND ?
        )
        SELECT
            month,
            category,
            SUM(amount) AS total
        FROM combined_transactions
        GROUP BY 1, 2
        """,
        (start_month, end_month, start_month, end_month),
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


def _get_transactions(start_date: str = None, end_date: str = None) -> list[dict]:
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
    Add or update a manual account snapshot.
    
    Args:
        snapshot: Dict with keys: snapshot_date, account_id, account_name, 
                  institution, account_type, account_subtype, current_balance,
                  available_balance, credit_limit, currency
    
    Returns:
        True if successful, False otherwise.
    """
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
    cur = _current_month()
    # This month spend / income (positive=income, negative=expense) - including manual transactions
    month_rows = _rows(
        """
        SELECT SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) AS spend,
               SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS income,
               SUM(amount)                                       AS net
        FROM transactions
        WHERE excluded = 0 AND pending = 0
          AND strftime('%Y-%m', date) = ?
        
        UNION ALL
        
        SELECT SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) AS spend,
               SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS income,
               SUM(amount)                                       AS net
        FROM manual_transactions
        WHERE strftime('%Y-%m', date) = ?
        """,
        (cur, cur),
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
    for holding in holdings:
        holding["account_name"] = account_names.get(
            holding["account_id"], holding["account_id"]
        )
        holding["gain_loss"] = round(
            (holding.get("current_value") or 0) - (holding.get("cost_basis") or 0), 2
        )
        cost_basis = holding.get("cost_basis") or 0
        holding["gain_loss_percent"] = round(
            holding["gain_loss"] / cost_basis * 100, 2
        ) if cost_basis else None

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
    cost_basis = round(sum(h.get("cost_basis") or 0 for h in holdings), 2)
    gain_loss = round(current_value - cost_basis, 2)
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
        },
        "accounts": accounts,
        "holdings": holdings,
        "history": history,
        "transactions": investment_transactions,
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
    return render_template("spend.html", earliest=earliest, latest=latest)


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


@app.route("/investments")
def investments():
    return render_template("investments.html")


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
    pivot = _spend_pivot(start, end)
    return jsonify(pivot)


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
    """Add or update a manual transaction."""
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
    except Exception as e:
        logger.error(f"Failed to add manual transaction: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/manual/transaction", methods=["PUT"])
def api_update_manual_transaction():
    """Update a manual transaction (all fields editable)."""
    from .modules.database import upsert_manual_transaction
    
    data = request.json
    if not data or "transaction_id" not in data:
        return jsonify({"error": "Missing transaction_id"}), 400
    
    try:
        upsert_manual_transaction(data)
        return jsonify({"success": True})
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


@app.route("/api/manual/snapshots")
def api_manual_snapshots():
    """Get all manual account snapshots."""
    return jsonify(_get_manual_snapshots())


@app.route("/api/manual/snapshot", methods=["POST"])
def api_add_manual_snapshot():
    """Add or update a manual account snapshot."""
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
    args = parser.parse_args()
    
    # ── Run the sync pipeline first (unless --no-sync is specified) ─────────────────────
    if not args.no_sync:
        # Import here (not at module top) to avoid circular imports with config.
        from .main import run_pipeline  # noqa: PLC0415

        print("\n" + "=" * 60)
        print("  Finance Sync — Syncing data before dashboard start…")
        print("=" * 60 + "\n")

        try:
            run_pipeline(enable_sheets=False)
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
