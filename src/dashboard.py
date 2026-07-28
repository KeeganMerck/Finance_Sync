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
    DASHBOARD_PORT=8080 python -m src.dashboard

To push to Google Sheets instead of opening the dashboard:
    python -m src.google_sheets
"""

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, render_template, request

# ── Config ────────────────────────────────────────────────────────────────────
from .core.config import DATABASE_PATH

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
    Build a pivot of monthly spend by category.

    Returns:
        months         — ordered list of YYYY-MM strings in range
        complete_months— months used for average (excludes partial current month)
        rows           — list of {category, monthly: {YYYY-MM: float}, average: float}
                         sorted by |average| descending
        net_row        — {monthly: {YYYY-MM: float}, average: float}
    """
    raw = _rows(
        """
        SELECT
            strftime('%Y-%m', date)                                            AS month,
            COALESCE(user_category, plaid_category_primary, plaid_category,
                     'Uncategorized')                                          AS category,
            SUM(amount)                                                        AS total
        FROM transactions
        WHERE excluded = 0
          AND pending  = 0
          AND strftime('%Y-%m', date) BETWEEN ? AND ?
        GROUP BY 1, 2
        ORDER BY 1, 2
        """,
        (start_month, end_month),
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
    Get transactions for the transactions view.
    
    Args:
        start_date: Optional start date in YYYY-MM-DD format.
        end_date: Optional end date in YYYY-MM-DD format.
    
    Returns:
        List of transaction dicts with Date, Account, Description, Category, Amount.
    """
    query = """
        SELECT 
            date AS Date,
            COALESCE(account, institution, 'Unknown') AS Account,
            COALESCE(merchant, description, '') AS Description,
            COALESCE(user_category, plaid_category_primary, plaid_category, 'Uncategorized') AS Category,
            amount AS Amount
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
    
    query += " ORDER BY date DESC"
    
    return _rows(query, tuple(params))


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
        WITH combined AS (
            SELECT account_id, account_name, institution, account_type,
                   account_subtype, current_balance, available_balance,
                   credit_limit, snapshot_date
            FROM account_snapshots
            UNION ALL
            SELECT account_id, account_name, institution, account_type,
                   account_subtype, current_balance, available_balance,
                   credit_limit, snapshot_date
            FROM manual_account_snapshots
        ),
        ranked AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY account_id
                       ORDER BY snapshot_date DESC
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
    Monthly net worth history from the cached net_worth_history table.
    """
    # Calculate on-the-fly from both snapshot tables (always up-to-date)
    rows = _rows(
        """
        WITH combined_balances AS (
            SELECT 
                snapshot_date,
                account_type,
                current_balance
            FROM account_snapshots
            
            UNION ALL
            
            SELECT 
                snapshot_date,
                account_type,
                current_balance
            FROM manual_account_snapshots
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
            FROM combined_balances
            GROUP BY snapshot_date
        )
        SELECT strftime('%Y-%m', snapshot_date) AS month, net_worth
        FROM daily_net_worth
        ORDER BY snapshot_date
        """
    )

    # Group by month (take the last snapshot of each month)
    monthly: dict[str, float] = {}
    for r in rows:
        monthly[r["month"]] = r["net_worth"]

    result = []
    for m in sorted(monthly.keys()):
        result.append({"month": m, "net_worth": round(monthly[m], 2)})
    return result


def _summary_cards() -> dict:
    cur = _current_month()
    # This month spend / income (positive=income, negative=expense)
    month_rows = _rows(
        """
        SELECT SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END) AS spend,
               SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS income,
               SUM(amount)                                       AS net
        FROM transactions
        WHERE excluded = 0 AND pending = 0
          AND strftime('%Y-%m', date) = ?
        """,
        (cur,),
    )
    m = month_rows[0] if month_rows else {}
    spend = m.get("spend") or 0.0
    income = m.get("income") or 0.0
    net = m.get("net") or 0.0

    # Current net worth
    accounts = _current_accounts()
    net_worth = _net_worth_from_accounts(accounts)

    # Average monthly net (complete months, last 12)
    avg_rows = _rows(
        """
        SELECT strftime('%Y-%m', date) AS month, SUM(amount) AS total
        FROM transactions
        WHERE excluded = 0 AND pending = 0
          AND strftime('%Y-%m', date) < ?
        GROUP BY 1
        ORDER BY 1 DESC
        LIMIT 12
        """,
        (cur,),
    )
    avg_net = (
        sum(r["total"] for r in avg_rows) / len(avg_rows) if avg_rows else 0.0
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
        ORDER BY 1 DESC
        """,
        (cur,),
    )

    # Keep only the most recent lookback_months of data
    months_seen: list[str] = []
    for r in rows:
        if r["month"] not in months_seen:
            months_seen.append(r["month"])
    keep_months = set(months_seen[:lookback_months])
    rows = [r for r in rows if r["month"] in keep_months]
    n = len(keep_months) or 1

    # Pivot and average
    pivot: dict[str, dict[str, float]] = {}
    for r in rows:
        pivot.setdefault(r["category"], {})[r["month"]] = r["total"]

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


# ── API routes ────────────────────────────────────────────────────────────────

@app.route("/api/summary")
def api_summary():
    return jsonify(_summary_cards())


@app.route("/api/spend/monthly")
def api_spend_monthly():
    earliest, latest = _date_range_bounds()
    start = request.args.get("start", earliest)
    end = request.args.get("end", latest)
    pivot = _spend_pivot(start, end)
    return jsonify(pivot)


@app.route("/api/networth/current")
def api_networth_current():
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


@app.route("/api/networth/history")
def api_networth_history():
    return jsonify(_networth_history())


@app.route("/api/transactions")
def api_transactions():
    """Get transactions for the transactions view."""
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    return jsonify(_get_transactions(start_date, end_date))


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
    # ── Run the sync pipeline first ───────────────────────────────────────────
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

    # ── Start the web server ──────────────────────────────────────────────────
    _print_startup()
    app.run(host="0.0.0.0", port=DASHBOARD_PORT, debug=False)
