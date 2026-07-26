"""
main.py
=======
Pipeline orchestrator for the finance sync system.

This file's only job is to wire the stages together and log the result.
It contains NO business logic — all logic lives in the modules it calls.
Adding a new pipeline stage means adding one function call here.

Pipeline stages (in order):
  1. Load transactions   — sync.py
  1b. Fetch balances     — balance.py (account balance snapshots)
  2. Categorize          — categorizer.py (normalize merchants, apply overrides)
  3. Persist             — database.py    (SQLite upsert; skipped if disabled)
  4. Export              — export.py      (cash_flow.csv + raw_transactions.csv)
  5. Log summary         — stdout + sync.log

Dry run mode (DRY_RUN=True in config.py):
  Stages 1, 1b, and 2 run normally so categorization logic can be verified.
  Stage 3 (database) and Stage 4 (export) log what they would do without
  writing anything to disk.
"""

import logging
import sys
from datetime import datetime

from .core.config import DRY_RUN, ENABLE_DATABASE, GOOGLE_SHEETS_ENABLED, LOG_PATH, USE_PLAID
from .modules.sync import fetch_transactions
from .modules.categorizer import categorize_transactions, load_rules
from .modules.database import get_all_transactions, init_db, upsert_transactions
from .modules.export import run_exports
from .modules.google_sheets import update_google_sheet
from .modules.balance import fetch_balances, upsert_snapshots as upsert_balance_snapshots, export_to_sheets as export_balances_to_sheets


# ─── Logging Configuration ─────────────────────────────────────────────────────

def configure_logging() -> None:
    """
    Configure the root logger to write to both sync.log and stdout.

    Format includes timestamp, level, module name, and message for easy
    filtering and correlation when reviewing logs after a scheduled run.

    Called once at startup before any pipeline code runs.
    """
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Configure stdout to handle UTF-8 on Windows
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s  %(levelname)-8s  %(name)-20s  %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(LOG_PATH, encoding='utf-8'),
            logging.StreamHandler(sys.stdout),
        ],
    )


# ─── Pipeline ──────────────────────────────────────────────────────────────────

def run_pipeline() -> None:
    """
    Execute the full finance sync pipeline end-to-end.

    Exits with sys.exit(1) on fatal errors in load or export stages.
    Database errors are non-fatal (logged as warnings) so exports still run
    even if persistence fails — data is not lost, just not persisted to SQLite.
    """
    configure_logging()
    logger = logging.getLogger(__name__)

    start_time = datetime.now()
    separator  = '-' * 60

    logger.info(separator)
    logger.info("Finance Sync — Pipeline Start")
    logger.info(f"  Start time  : {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"  Dry run     : {DRY_RUN}")
    logger.info(f"  Database    : {'enabled' if ENABLE_DATABASE else 'disabled'}")
    logger.info(separator)

    # ── Stage 1: Load Transactions ────────────────────────────────────────────
    #
    # sync.py abstracts the data source. If USE_PLAID is False, transactions are loaded from a mock JSON file.
    #
    logger.info("Stage 1/5 — Loading transactions...")
    try:
        init_db() # Ensure database is initialized before fetching transactions (for incremental sync)
        transactions = fetch_transactions()
    except Exception:
        logger.exception("Fatal: failed to load transactions. Aborting pipeline.")
        sys.exit(1)

    if not transactions:
        logger.warning("No transactions returned by sync layer — pipeline will produce empty exports.")

    logger.info(f"  Loaded {len(transactions)} transaction(s).")

    # ── Stage 1b: Fetch and Store Account Balances ─────────────────────────────
    #
    # Fetches current account balances from Plaid and stores them as snapshots.
    # Non-fatal: if this stage fails, the pipeline continues to Stage 2.
    # Transaction pipeline must never be blocked by balance fetch failure.
    #
    logger.info("Stage 1b/5 — Fetching and storing account balances...")
    try:
        if not USE_PLAID:
            logger.info("  Balance fetch requires Plaid (USE_PLAID=True) — skipping.")
        else:
            balances = fetch_balances()
            if balances:
                upserted = upsert_balance_snapshots(balances)
                logger.info(f"  Upserted {upserted} account balance snapshot(s).")
                
                # Export to Google Sheets
                balance_export_summary = export_balances_to_sheets(dry_run=DRY_RUN)
                logger.info(f"  Balance export: {balance_export_summary}")
            else:
                logger.info("  No balance data fetched — skipping balance storage and export.")
    except Exception:
        logger.exception(
            "Non-fatal: balance fetch and storage failed. "
            "Continuing to transaction categorization stage."
        )

    # ── Stage 2: Categorize & Normalize ──────────────────────────────────────
    #
    # Loads rules from category_rules.csv, normalizes merchant names, and
    # applies user-defined category overrides. plaid_category is never modified.
    #
    logger.info("Stage 2/5 — Categorizing and normalizing merchants...")
    try:
        rules = load_rules()
        transactions, categorized_count, uncategorized_count, excluded_count = categorize_transactions(
            transactions,
            rules=rules,
            return_excluded_count=True,
        )
    except Exception:
        logger.exception("Fatal: categorization failed. Aborting pipeline.")
        sys.exit(1)

    logger.info(f"  Rules loaded      : {len(rules)}")
    logger.info(f"  Categorized       : {categorized_count}")
    logger.info(f"  Uncategorized     : {uncategorized_count}")
    logger.info(f"  Excluded          : {excluded_count}")

    if uncategorized_count > 0:
        logger.warning(
            f"  {uncategorized_count} transaction(s) have no category. "
            "Consider adding rules to category_rules.csv."
        )

    # ── Stage 3: Persist to Database ─────────────────────────────────────────
    #
    # Upserts all categorized transactions to SQLite by transaction_id.
    # Non-fatal: if this fails, the pipeline continues and exports still run.
    # Reason: it is better to produce today's CSV than to abort on a DB error.
    #
    logger.info("Stage 3/5 — Persisting to database...")

    upsert_result = {"written": 0, "unchanged": 0, "total": 0}
    if not ENABLE_DATABASE:
        logger.info("  Database disabled via config — skipping persistence.")
    else:
        try:
            init_db()
            upsert_result = upsert_transactions(transactions)
            logger.info(
                f"  Written (new or changed) : {upsert_result['written']}"
            )
            logger.info(
                f"  Unchanged (skipped)      : {upsert_result['unchanged']}"
            )
        except Exception:
            logger.exception(
                "Non-fatal: database write failed. "
                "Exports will still run using in-memory transaction data."
            )

    # ── Stage 4: Export to CSV ────────────────────────────────────────────────
    #
    # Writes cash_flow.csv (Excel-compatible) and raw_transactions.csv (archival).
    # In dry run mode, logs what would be written without touching the filesystem.
    #
    logger.info("Stage 4/5 — Exporting CSV files...")
    try:
        export_summary = run_exports(
            transactions,
            include_raw=True,
            dry_run=DRY_RUN,
        )
    except Exception:
        logger.exception("Fatal: export failed.")
        sys.exit(1)

    logger.info("Refreshing Google Sheets table...")
    try:
        if not DRY_RUN and GOOGLE_SHEETS_ENABLED:
            # Use the already-categorized transactions instead of fetching from DB
            # This ensures excluded transactions are filtered out
            sheet_rows = update_google_sheet(transactions)
            logger.info(f"  Updated Google Sheets with {sheet_rows} row(s).")
        elif DRY_RUN:
            logger.info("  Dry run enabled — skipping Google Sheets update.")
        else:
            logger.info("  Google Sheets export disabled via config.")
    except Exception:
        logger.exception("Non-fatal: Google Sheets update failed.")

    # ── Summary ───────────────────────────────────────────────────────────────

    end_time = datetime.now()
    elapsed  = (end_time - start_time).total_seconds()

    logger.info(separator)
    logger.info("Finance Sync — Pipeline Complete")
    logger.info(f"  Transactions processed    : {len(transactions)}")
    logger.info(f"  Categorized               : {categorized_count}")
    logger.info(f"  Uncategorized             : {uncategorized_count}")
    if ENABLE_DATABASE:
        logger.info(f"  DB written (new/changed)  : {upsert_result['written']}")
        logger.info(f"  DB unchanged (skipped)    : {upsert_result['unchanged']}")

    for export_name, row_count in export_summary.items():
        verb = "Would export" if DRY_RUN else "Exported"
        logger.info(f"  {verb} ({export_name}): {row_count} row(s)")

    logger.info(f"  Elapsed               : {elapsed:.2f}s")
    logger.info(f"  Completed at          : {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(separator)


# ─── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    run_pipeline()
