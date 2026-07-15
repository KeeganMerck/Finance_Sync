"""
tests/test_export.py
====================
Unit tests for export.py.

Focuses on:
  - _to_cash_flow_row() field mapping accuracy
  - resolve_category() priority (imported via categorizer, used in export)
  - run_exports() in dry-run mode (no files written, returns correct counts)
  - Edge cases: missing fields, None values, pending transactions

All tests run without writing to disk — dry_run=True is used for any
function that would otherwise touch the filesystem.

Run from the project root:
    python -m unittest tests/test_export.py -v

Or run directly in Carnets.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import export as export_module
from export import (
    CASH_FLOW_COLUMNS,
    RAW_COLUMNS,
    run_exports,
)
from categorizer import resolve_category


# ─── Helpers ───────────────────────────────────────────────────────────────────

def make_txn(**overrides) -> dict:
    """Canonical transaction with sensible defaults. Override as needed."""
    base = {
        'transaction_id': 'txn_export_001',
        'date':           '2024-06-01',
        'account':        'Chase Checking ••4532',
        'merchant':       'STARBUCKS',
        'description':    'STARBUCKS #1832 PORTLAND OR',
        'plaid_category': 'FOOD_AND_DRINK',
        'user_category':  'Coffee',
        'amount':         -5.75,
        'pending':        False,
        'institution':    'Chase',
        'last_updated':   '2024-06-01T08:30:00',
    }
    base.update(overrides)
    return base


# ─── Column Contract Tests ─────────────────────────────────────────────────────

class TestColumnDefinitions(unittest.TestCase):

    def test_cash_flow_columns_exact_order(self):
        """CASH_FLOW_COLUMNS must match the Excel workbook contract exactly."""
        expected = ['Date', 'Account', 'Description', 'Category', 'Amount']
        self.assertEqual(CASH_FLOW_COLUMNS, expected,
                         "Changing CASH_FLOW_COLUMNS will break Excel workbook formulas!")

    def test_raw_columns_contains_all_canonical_fields(self):
        """RAW_COLUMNS must include every canonical schema field."""
        required_fields = {
            'transaction_id', 'date', 'account', 'merchant', 'description',
            'plaid_category', 'user_category', 'amount', 'pending',
            'institution', 'last_updated',
        }
        self.assertTrue(required_fields.issubset(set(RAW_COLUMNS)),
                        f"Missing fields: {required_fields - set(RAW_COLUMNS)}")

    def test_cash_flow_column_count(self):
        """Excel schema has exactly 5 columns."""
        self.assertEqual(len(CASH_FLOW_COLUMNS), 5)


# ─── _to_cash_flow_row() Tests ─────────────────────────────────────────────────

class TestToCashFlowRow(unittest.TestCase):

    def _convert(self, txn):
        return export_module._to_cash_flow_row(txn)

    def test_output_keys_match_cash_flow_columns(self):
        row = self._convert(make_txn())
        self.assertEqual(set(row.keys()), set(CASH_FLOW_COLUMNS))

    def test_date_field_mapped_correctly(self):
        row = self._convert(make_txn(date='2024-07-04'))
        self.assertEqual(row['Date'], '2024-07-04')

    def test_account_field_mapped_correctly(self):
        row = self._convert(make_txn(account='Amex Gold ••1234'))
        self.assertEqual(row['Account'], 'Amex Gold ••1234')

    def test_amount_stays_numeric(self):
        """Amount must remain a number — Excel handles formatting."""
        row = self._convert(make_txn(amount=-42.99))
        self.assertEqual(row['Amount'], -42.99)
        self.assertIsInstance(row['Amount'], (int, float))

    def test_description_prefers_merchant_over_raw(self):
        """Normalized merchant should be used as Description."""
        row = self._convert(make_txn(
            merchant='STARBUCKS',
            description='STARBUCKS #1832 PORTLAND OR'
        ))
        self.assertEqual(row['Description'], 'STARBUCKS')

    def test_description_falls_back_when_merchant_empty(self):
        row = self._convert(make_txn(merchant='', description='WHOLEFDS MKT 10293'))
        self.assertEqual(row['Description'], 'WHOLEFDS MKT 10293')

    def test_description_falls_back_when_merchant_none(self):
        row = self._convert(make_txn(merchant=None, description='RAW DESC'))
        self.assertEqual(row['Description'], 'RAW DESC')

    def test_category_uses_user_category(self):
        row = self._convert(make_txn(user_category='Coffee', plaid_category='FOOD_AND_DRINK'))
        self.assertEqual(row['Category'], 'Coffee')

    def test_category_prefers_plaid_primary_over_detailed_plaid(self):
        row = self._convert(make_txn(
            user_category=None,
            plaid_category_primary='SHOPPING',
            plaid_category='SHOPPING_GENERAL',
        ))
        self.assertEqual(row['Category'], 'SHOPPING')

    def test_category_falls_back_to_plaid_detailed_when_primary_missing(self):
        row = self._convert(make_txn(user_category=None, plaid_category_primary='', plaid_category='SHOPPING_GENERAL'))
        self.assertEqual(row['Category'], 'SHOPPING_GENERAL')

    def test_category_defaults_to_uncategorized_when_none_present(self):
        """
        When neither user_category nor plaid_category is set, the CSV must
        show 'Uncategorized' rather than an empty string.
        The internal data model still uses '' — this default is export-only.
        """
        row = self._convert(make_txn(user_category=None, plaid_category=''))
        self.assertEqual(row['Category'], 'Uncategorized')
        self.assertIsInstance(row['Category'], str)

    def test_missing_fields_do_not_raise(self):
        minimal = {'transaction_id': 'min_001'}
        row = self._convert(minimal)  # must not raise
        self.assertIn('Date', row)
        self.assertIn('Category', row)

    def test_plaid_category_not_in_output(self):
        row = self._convert(make_txn(plaid_category='FOOD_AND_DRINK'))
        self.assertNotIn('plaid_category', row)
        self.assertNotIn('user_category', row)

    def test_pending_flag_not_in_output(self):
        row = self._convert(make_txn(pending=True))
        self.assertNotIn('pending', row)

    def test_transaction_id_not_in_output(self):
        row = self._convert(make_txn())
        self.assertNotIn('transaction_id', row)


# ─── Pending Transaction Tests ─────────────────────────────────────────────────

class TestPendingTransactions(unittest.TestCase):

    def test_pending_transaction_exports_without_error(self):
        txn = make_txn(pending=True, description='PENDING - LYFT *RIDE', merchant='')
        row = export_module._to_cash_flow_row(txn)
        self.assertEqual(row['Description'], 'PENDING - LYFT *RIDE')

    def test_pending_with_no_category_exports_uncategorized(self):
        """Pending transactions with no category must export 'Uncategorized', not blank."""
        txn = make_txn(pending=True, user_category=None, plaid_category='')
        row = export_module._to_cash_flow_row(txn)
        self.assertEqual(row['Category'], 'Uncategorized')


# ─── run_exports() Dry Run Tests ───────────────────────────────────────────────

class TestRunExports(unittest.TestCase):

    def _run(self, transactions, include_raw=True):
        return run_exports(transactions, include_raw=include_raw, dry_run=True)

    def test_returns_cash_flow_row_count(self):
        txns = [make_txn(transaction_id=f't{i}') for i in range(5)]
        summary = self._run(txns)
        self.assertEqual(summary.get('cash_flow_rows'), 5)

    def test_returns_raw_row_count_when_include_raw_true(self):
        txns = [make_txn(transaction_id=f't{i}') for i in range(3)]
        summary = self._run(txns, include_raw=True)
        self.assertIn('raw_rows', summary)
        self.assertEqual(summary['raw_rows'], 3)

    def test_no_raw_rows_when_include_raw_false(self):
        txns = [make_txn()]
        summary = self._run(txns, include_raw=False)
        self.assertNotIn('raw_rows', summary)

    def test_empty_transaction_list_returns_zero_counts(self):
        summary = self._run([])
        self.assertEqual(summary.get('cash_flow_rows', 0), 0)

    def test_summary_is_dict(self):
        summary = self._run([make_txn()])
        self.assertIsInstance(summary, dict)

    def test_cash_flow_and_raw_counts_match(self):
        """Both exports must reflect the same number of input transactions."""
        txns = [make_txn(transaction_id=f't{i}') for i in range(7)]
        summary = self._run(txns, include_raw=True)
        self.assertEqual(summary['cash_flow_rows'], summary['raw_rows'])


# ─── Amount Sign Convention Tests ─────────────────────────────────────────────

class TestAmountConventions(unittest.TestCase):
    """Plaid uses negative for debits, positive for credits. Never flip signs."""

    def test_negative_amount_preserved(self):
        row = export_module._to_cash_flow_row(make_txn(amount=-52.43))
        self.assertEqual(row['Amount'], -52.43)

    def test_positive_amount_preserved(self):
        row = export_module._to_cash_flow_row(make_txn(amount=2500.00))
        self.assertEqual(row['Amount'], 2500.00)

    def test_zero_amount_preserved(self):
        row = export_module._to_cash_flow_row(make_txn(amount=0.0))
        self.assertEqual(row['Amount'], 0.0)


# ─── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    unittest.main(verbosity=2)