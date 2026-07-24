"""
export.py
=========
CSV export module. Transforms canonical transaction data into output files.

Outputs:
  cash_flow.csv        — Simplified schema compatible with the user's Excel workbook
  raw_transactions.csv — Full canonical schema for archival and debugging

Excel workbook compatibility:
  cash_flow.csv must have EXACTLY these columns in this order:
    Date, Account, Description, Category, Amount
  Do not rename, reorder, or add columns without updating the workbook formulas.

Category resolution (for cash_flow export):
  1. user_category          — explicit override (highest priority)
  2. plaid_category_primary — broader Plaid grouping category
  3. plaid_category         — detailed Plaid category fallback
  4. Empty string           — no category available

Design principle:
  Exports are DERIVED from canonical data. Canonical data is never modified
  to match an export format. If the Excel schema changes, update only the
  _to_cash_flow_row() mapping function — not the database or categorizer.

Dry run support:
  When DRY_RUN=True (from config), export functions log what they would write
  without touching the filesystem. Useful for pipeline testing.
"""

import csv
import logging
from pathlib import Path

from .categorizer import format_category_for_display, resolve_category
from ..core.config import CASH_FLOW_CSV_PATH, RAW_CSV_PATH, DRY_RUN

logger = logging.getLogger(__name__)


# ─── Column Definitions ────────────────────────────────────────────────────────

# Exact column names expected by the Excel workbook — treat as a contract.
# Changing these names will break existing workbook formulas and pivot tables.
CASH_FLOW_COLUMNS: list[str] = [
    'Date',
    'Account',
    'Description',
    'Category',
    'Amount',
]

# Full canonical schema for raw export. Matches database.py schema exactly.
# Useful for debugging categorization issues or verifying data integrity.
RAW_COLUMNS: list[str] = [
    'transaction_id',
    'date',
    'account',
    'merchant',
    'description',
    'plaid_category',
    'user_category',
    'amount',
    'pending',
    'institution',
    'last_updated',
    'excluded',
]


# ─── Row Transformation ────────────────────────────────────────────────────────

def _to_cash_flow_row(transaction: dict) -> dict:
    """
    Transform a single canonical transaction into a cash_flow.csv row.

    This function is the sole mapping point between canonical field names and
    Excel column names. Centralizing it here means schema changes require
    editing only this function.

    Description field logic:
      Prefers the normalized merchant name (set by categorizer.py) because it
      is cleaner and more consistent. Falls back to the raw description if no
      merchant is available. This gives Excel formulas a reliable, stable value
      to match against.

    Args:
        transaction: Canonical transaction dict (post-categorization).

    Returns:
        Dict with keys matching CASH_FLOW_COLUMNS.
    """
    return {
        'Date':        transaction.get('date', ''),
        'Account':     transaction.get('account', ''),
        # Prefer normalized merchant; fall back to raw description
        'Description': transaction.get('merchant') or transaction.get('description', ''),
        # Resolution order: user_category → plaid_category_primary → plaid_category
        # → 'Uncategorized'. 'Uncategorized' only appears in the CSV — the
        # internal data model keeps an empty string so test_database uncategorized
        # queries still work.
        'Category':    format_category_for_display(resolve_category(transaction)) or 'Uncategorized',
        # Amount is kept as a raw number — Excel handles display formatting
        'Amount':      transaction.get('amount', ''),
    }


def _to_raw_row(transaction: dict) -> dict:
    """
    Extract canonical fields from a transaction dict for raw CSV export.

    Uses only the columns defined in RAW_COLUMNS. Extra fields (if any) are
    silently ignored via extrasaction='ignore' in the DictWriter call.

    Args:
        transaction: Canonical transaction dict.

    Returns:
        Dict with only RAW_COLUMNS keys (missing values default to empty string).
    """
    return {col: transaction.get(col, '') for col in RAW_COLUMNS}


# ─── Export Functions ──────────────────────────────────────────────────────────

def export_cash_flow(
    transactions: list[dict],
    output_path: Path = CASH_FLOW_CSV_PATH,
    dry_run: bool = DRY_RUN,
) -> int:
    """
    Write transactions to cash_flow.csv in the format expected by Excel.

    Rows are written in the order provided. Callers should pre-sort
    transactions by date if a specific order is needed in the workbook.

    Args:
        transactions: Post-categorization canonical transaction list.
        output_path:  Destination CSV path (default from config).
        dry_run:      If True, log what would be written without writing files.

    Returns:
        Number of rows written (or that would have been written in dry run).
    """
    # Filter out excluded transactions before export
    active_transactions = [t for t in transactions if not t.get('excluded')]
    
    if not active_transactions:
        logger.warning(
            "export_cash_flow: received empty transaction list after filtering excluded — skipping export."
        )
        return 0

    rows = [_to_cash_flow_row(t) for t in active_transactions]

    if dry_run:
        logger.info(
            f"[DRY RUN] cash_flow.csv — would write {len(rows)} row(s) to: {output_path}"
        )
        # Log a small preview so dry runs are still informative
        for row in rows[:3]:
            logger.info(f"  [DRY RUN] {row}")
        if len(rows) > 3:
            logger.info(f"  [DRY RUN] ... and {len(rows) - 3} more row(s).")
        return len(rows)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CASH_FLOW_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    logger.info(f"cash_flow.csv — wrote {len(rows)} row(s) to: {output_path}")
    return len(rows)


def export_raw_transactions(
    transactions: list[dict],
    output_path: Path = RAW_CSV_PATH,
    dry_run: bool = DRY_RUN,
) -> int:
    """
    Write the full canonical schema to raw_transactions.csv.

    This export is for diagnostic and archival purposes only. It includes:
      - Both plaid_category and user_category (so overrides are auditable)
      - pending flag (so settled vs. pending is visible)
      - last_updated timestamp (for troubleshooting sync timing)
      - transaction_id (for cross-referencing with the database)

    Excel does not import this file — it is for developer inspection.

    Args:
        transactions: Canonical transaction list (any categorization state).
        output_path:  Destination CSV path (default from config).
        dry_run:      If True, log what would be written without writing files.

    Returns:
        Number of rows written (or that would have been written in dry run).
    """
    if not transactions:
        logger.warning(
            "export_raw_transactions: received empty transaction list — skipping export."
        )
        return 0

    if dry_run:
        logger.info(
            f"[DRY RUN] raw_transactions.csv — "
            f"would write {len(transactions)} row(s) to: {output_path}"
        )
        return len(transactions)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(
            f,
            fieldnames=RAW_COLUMNS,
            extrasaction='ignore',  # Silently drop any unexpected fields
        )
        writer.writeheader()
        writer.writerows([_to_raw_row(t) for t in transactions])

    logger.info(
        f"raw_transactions.csv — wrote {len(transactions)} row(s) to: {output_path}"
    )
    return len(transactions)


# ─── Orchestrated Export ───────────────────────────────────────────────────────

def run_exports(
    transactions: list[dict],
    include_raw: bool = True,
    dry_run: bool = DRY_RUN,
) -> dict[str, int]:
    """
    Run all configured export targets and return a summary of row counts.

    This is the primary entry point called by main.py. Adding a new export
    target in the future means adding a call here — main.py stays unchanged.

    Args:
        transactions: Post-categorization canonical transaction list.
        include_raw:  Whether to also write raw_transactions.csv.
                      Set False to write only the Excel-compatible file.
        dry_run:      Passed through to each export function.

    Returns:
        Dict mapping export name to row count, e.g.:
          {'cash_flow_rows': 85, 'raw_rows': 85}
    """
    summary: dict[str, int] = {}

    logger.info("Starting CSV exports...")

    # Always export the primary Excel-compatible file
    cash_flow_count = export_cash_flow(transactions, dry_run=dry_run)
    summary['cash_flow_rows'] = cash_flow_count

    # Optionally export the full canonical archival file
    if include_raw:
        raw_count = export_raw_transactions(transactions, dry_run=dry_run)
        summary['raw_rows'] = raw_count

    logger.info(f"Export complete. Summary: {summary}")
    return summary