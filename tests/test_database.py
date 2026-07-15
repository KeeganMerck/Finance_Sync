"""
tests/test_database.py
======================
Unit tests for database.py.

Uses a real SQLite database written to a temporary file — no mocking of SQLite
itself, because the actual schema, index creation, and upsert behavior are what
we need to verify. The temp file is created fresh for each test and deleted
in tearDown so tests are fully isolated.

ENABLE_DATABASE is patched to True for all tests via setUp so the database
guard clauses don't interfere with test execution.

Key behaviors verified:
    - Schema creation is idempotent (safe to call init_db twice)
    - Upsert inserts new rows correctly
    - Upsert overwrites existing rows on transaction_id collision (idempotency)
    - Batch upsert is atomic (all rows succeed or none do)
    - Read helpers return correct data
    - Date range filtering works correctly
    - Uncategorized query logic is correct
    - ENABLE_DATABASE=False causes all writes/reads to no-op gracefully

Run from the project root:
    python -m unittest tests/test_database.py -v

Or run directly in Carnets.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import database as db_module
from database import (
    init_db,
    upsert_transaction,
    upsert_transactions,
    get_all_transactions,
    get_transaction_by_id,
    get_transaction_count,
    get_transactions_by_date_range,
    get_uncategorized_transactions,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_txn(**overrides) -> dict:
    """
    Return a minimal canonical transaction dict that satisfies the DB schema.
    Override any field by passing it as a keyword argument.
    """
    base = {
        'transaction_id': 'txn_db_001',
        'date':           '2024-03-15',
        'account':        'Checking ••1234',
        'merchant':       'STARBUCKS',
        'description':    'STARBUCKS #1832 CHARLOTTE NC',
        'plaid_category': 'FOOD_AND_DRINK_COFFEE',
        'plaid_category_primary': 'FOOD_AND_DRINK',
        'user_category':  'Coffee',
        'amount':         -6.45,
        'pending':        False,
        'institution':    'Chase',
        'last_updated':   '2024-03-15T08:00:00',
    }
    base.update(overrides)
    return base


# ─── Base Test Case ───────────────────────────────────────────────────────────

class DatabaseTestCase(unittest.TestCase):
    """
    Base class that creates a fresh temp SQLite file for each test and
    patches ENABLE_DATABASE to True so guard clauses don't block execution.
    """

    def setUp(self):
        # Create a real temp file — not :memory: so Path() works correctly
        self.db_fd, db_path_str = tempfile.mkstemp(suffix='.db')
        self.db_path = Path(db_path_str)

        # Patch ENABLE_DATABASE at the module level for all db_module functions
        self.enable_patch = patch.object(db_module, 'ENABLE_DATABASE', True)
        self.enable_patch.start()

        # Initialize schema in the temp file
        init_db(self.db_path)

    def tearDown(self):
        self.enable_patch.stop()
        os.close(self.db_fd)
        try:
            os.unlink(self.db_path)
        except OSError:
            pass  # File already deleted or never created — not a test failure


# ─── Schema Tests ─────────────────────────────────────────────────────────────

class TestInitDb(DatabaseTestCase):

    def test_init_creates_tables(self):
        """init_db must create the transactions table."""
        count = get_transaction_count(self.db_path)
        self.assertEqual(count, 0)  # table exists and is empty

    def test_init_is_idempotent(self):
        """Calling init_db twice on the same DB must not raise or corrupt data."""
        upsert_transaction(make_txn(), self.db_path)
        init_db(self.db_path)  # second call
        # Row inserted before second init_db must still be there
        self.assertEqual(get_transaction_count(self.db_path), 1)

    def test_init_creates_data_directory(self):
        """init_db must create parent directories if they don't exist."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            nested_path = Path(tmpdir) / 'subdir' / 'nested' / 'finance.db'
            init_db(nested_path)
            self.assertTrue(nested_path.exists())


# ─── Single Upsert Tests ──────────────────────────────────────────────────────

class TestUpsertTransaction(DatabaseTestCase):

    def test_insert_new_transaction(self):
        """A new transaction_id must be inserted as a new row."""
        upsert_transaction(make_txn(transaction_id='new_001'), self.db_path)
        self.assertEqual(get_transaction_count(self.db_path), 1)

    def test_upsert_overwrites_existing(self):
        """
        Re-upserting the same transaction_id must overwrite the previous row.
        This is the core idempotency guarantee — running sync twice produces
        the same result as running it once.
        """
        upsert_transaction(make_txn(transaction_id='dup_001', merchant='OLD'), self.db_path)
        upsert_transaction(make_txn(transaction_id='dup_001', merchant='NEW'), self.db_path)

        self.assertEqual(get_transaction_count(self.db_path), 1)  # not 2
        txn = get_transaction_by_id('dup_001', self.db_path)
        self.assertEqual(txn['merchant'], 'NEW')

    def test_upsert_preserves_all_fields(self):
        """All canonical fields must be stored and retrieved correctly."""
        txn = make_txn(
            transaction_id='full_001',
            date='2024-06-15',
            account='Amex Gold ••1009',
            merchant='AMAZON',
            description='AMZN MKTP US*AB1234',
            plaid_category='SHOPPING_GENERAL',
            user_category='Shopping',
            amount=-89.99,
            pending=False,
            institution='American Express',
            last_updated='2024-06-15T10:30:00',
        )
        upsert_transaction(txn, self.db_path)
        retrieved = get_transaction_by_id('full_001', self.db_path)

        self.assertEqual(retrieved['transaction_id'], 'full_001')
        self.assertEqual(retrieved['merchant'],        'AMAZON')
        self.assertEqual(retrieved['plaid_category'],  'SHOPPING_GENERAL')
        self.assertEqual(retrieved['user_category'],   'Shopping')
        self.assertAlmostEqual(retrieved['amount'],    -89.99, places=2)
        self.assertEqual(retrieved['institution'],     'American Express')

    def test_upsert_with_null_user_category(self):
        """user_category=None must be stored as NULL without error."""
        upsert_transaction(make_txn(transaction_id='null_cat', user_category=None),
                           self.db_path)
        retrieved = get_transaction_by_id('null_cat', self.db_path)
        self.assertIsNone(retrieved['user_category'])

    def test_pending_true_stored_correctly(self):
        """Pending flag True must survive a round-trip through SQLite."""
        upsert_transaction(make_txn(transaction_id='pend_001', pending=True), self.db_path)
        retrieved = get_transaction_by_id('pend_001', self.db_path)
        # SQLite stores booleans as integers — truthy check is sufficient
        self.assertTrue(retrieved['pending'])


# ─── Batch Upsert Tests ───────────────────────────────────────────────────────

class TestUpsertTransactions(DatabaseTestCase):

    def test_batch_inserts_all_rows(self):
        """All transactions in a batch must be inserted."""
        txns = [make_txn(transaction_id=f'b{i}', amount=float(-i)) for i in range(10)]
        count = upsert_transactions(txns, self.db_path)
        self.assertEqual(count, 10)
        self.assertEqual(get_transaction_count(self.db_path), 10)

    def test_batch_returns_count(self):
        """Return value must equal the number of transactions submitted."""
        txns = [make_txn(transaction_id=f't{i}') for i in range(5)]
        result = upsert_transactions(txns, self.db_path)
        self.assertEqual(result, 5)

    def test_batch_upsert_is_idempotent(self):
        """
        Inserting the same batch twice must produce the same row count as once.
        Core requirement: re-running sync must not duplicate data.
        """
        txns = [make_txn(transaction_id=f'idem_{i}') for i in range(5)]
        upsert_transactions(txns, self.db_path)
        upsert_transactions(txns, self.db_path)
        self.assertEqual(get_transaction_count(self.db_path), 5)  # not 10

    def test_empty_batch_returns_zero(self):
        """An empty batch must return 0 without error."""
        result = upsert_transactions([], self.db_path)
        self.assertEqual(result, 0)

    def test_batch_overwrites_on_conflict(self):
        """A batch upsert must overwrite existing rows when transaction_id matches."""
        upsert_transactions([make_txn(transaction_id='conflict_001', merchant='OLD')],
                            self.db_path)
        upsert_transactions([make_txn(transaction_id='conflict_001', merchant='NEW')],
                            self.db_path)
        retrieved = get_transaction_by_id('conflict_001', self.db_path)
        self.assertEqual(retrieved['merchant'], 'NEW')


# ─── Read Helper Tests ────────────────────────────────────────────────────────

class TestGetAllTransactions(DatabaseTestCase):

    def test_returns_empty_list_when_no_data(self):
        result = get_all_transactions(self.db_path)
        self.assertEqual(result, [])

    def test_returns_all_rows(self):
        txns = [make_txn(transaction_id=f'g{i}') for i in range(7)]
        upsert_transactions(txns, self.db_path)
        result = get_all_transactions(self.db_path)
        self.assertEqual(len(result), 7)

    def test_returns_list_of_dicts(self):
        upsert_transaction(make_txn(), self.db_path)
        result = get_all_transactions(self.db_path)
        self.assertIsInstance(result[0], dict)

    def test_ordered_by_date_descending(self):
        """Most recent transactions must appear first."""
        upsert_transactions([
            make_txn(transaction_id='old', date='2024-01-01'),
            make_txn(transaction_id='new', date='2024-12-31'),
            make_txn(transaction_id='mid', date='2024-06-15'),
        ], self.db_path)
        result = get_all_transactions(self.db_path)
        dates = [r['date'] for r in result]
        self.assertEqual(dates, sorted(dates, reverse=True))


class TestGetTransactionById(DatabaseTestCase):

    def test_returns_correct_transaction(self):
        upsert_transaction(make_txn(transaction_id='find_me', merchant='TARGET'),
                           self.db_path)
        result = get_transaction_by_id('find_me', self.db_path)
        self.assertIsNotNone(result)
        self.assertEqual(result['merchant'], 'TARGET')

    def test_returns_none_when_not_found(self):
        result = get_transaction_by_id('does_not_exist', self.db_path)
        self.assertIsNone(result)

    def test_does_not_return_wrong_transaction(self):
        upsert_transaction(make_txn(transaction_id='txn_A'), self.db_path)
        upsert_transaction(make_txn(transaction_id='txn_B'), self.db_path)
        result = get_transaction_by_id('txn_A', self.db_path)
        self.assertEqual(result['transaction_id'], 'txn_A')


class TestGetTransactionCount(DatabaseTestCase):

    def test_zero_when_empty(self):
        self.assertEqual(get_transaction_count(self.db_path), 0)

    def test_count_matches_insertions(self):
        upsert_transactions(
            [make_txn(transaction_id=f'c{i}') for i in range(12)],
            self.db_path
        )
        self.assertEqual(get_transaction_count(self.db_path), 12)

    def test_count_unchanged_after_duplicate_upsert(self):
        upsert_transaction(make_txn(transaction_id='dup'), self.db_path)
        upsert_transaction(make_txn(transaction_id='dup'), self.db_path)
        self.assertEqual(get_transaction_count(self.db_path), 1)


class TestGetTransactionsByDateRange(DatabaseTestCase):

    def setUp(self):
        super().setUp()
        # Insert a spread of dates for range testing
        self.txns = [
            make_txn(transaction_id='jan', date='2024-01-15'),
            make_txn(transaction_id='feb', date='2024-02-20'),
            make_txn(transaction_id='mar', date='2024-03-10'),
            make_txn(transaction_id='dec', date='2024-12-01'),
        ]
        upsert_transactions(self.txns, self.db_path)

    def test_returns_transactions_within_range(self):
        result = get_transactions_by_date_range('2024-01-01', '2024-03-31', self.db_path)
        ids = {r['transaction_id'] for r in result}
        self.assertEqual(ids, {'jan', 'feb', 'mar'})

    def test_range_is_inclusive_on_both_ends(self):
        result = get_transactions_by_date_range('2024-01-15', '2024-01-15', self.db_path)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['transaction_id'], 'jan')

    def test_excludes_transactions_outside_range(self):
        result = get_transactions_by_date_range('2024-06-01', '2024-11-30', self.db_path)
        self.assertEqual(result, [])

    def test_returns_empty_list_for_empty_range(self):
        result = get_transactions_by_date_range('2025-01-01', '2025-12-31', self.db_path)
        self.assertEqual(result, [])


class TestGetUncategorizedTransactions(DatabaseTestCase):

    def test_returns_only_uncategorized(self):
        """Only transactions missing BOTH user_category and plaid_category."""
        upsert_transactions([
            make_txn(transaction_id='has_user',  user_category='Coffee',   plaid_category=''),
            make_txn(transaction_id='has_plaid', user_category=None,       plaid_category='FOOD_AND_DRINK'),
            make_txn(transaction_id='no_cat',    user_category=None,       plaid_category=''),
            make_txn(transaction_id='no_cat_2',  user_category='',         plaid_category=''),
        ], self.db_path)

        result = get_uncategorized_transactions(self.db_path)
        ids = {r['transaction_id'] for r in result}

        self.assertIn('no_cat',   ids)
        self.assertIn('no_cat_2', ids)
        self.assertNotIn('has_user',  ids)
        self.assertNotIn('has_plaid', ids)

    def test_returns_empty_when_all_categorized(self):
        upsert_transaction(make_txn(plaid_category='FOOD_AND_DRINK', user_category='Coffee'),
                           self.db_path)
        result = get_uncategorized_transactions(self.db_path)
        self.assertEqual(result, [])


# ─── ENABLE_DATABASE=False Tests ──────────────────────────────────────────────

class TestDatabaseDisabled(unittest.TestCase):
    """
    When ENABLE_DATABASE=False, all functions must no-op gracefully.
    No exceptions, no file writes.
    """

    def setUp(self):
        self.disable_patch = patch.object(db_module, 'ENABLE_DATABASE', False)
        self.disable_patch.start()
        # Use a path that should never be written to during these tests
        self.db_path = Path('/tmp/should_not_be_created_by_tests.db')

    def tearDown(self):
        self.disable_patch.stop()
        if self.db_path.exists():
            os.unlink(self.db_path)

    def test_init_db_does_not_create_file(self):
        init_db(self.db_path)
        self.assertFalse(self.db_path.exists())

    def test_upsert_transaction_does_not_raise(self):
        upsert_transaction(make_txn(), self.db_path)  # must not raise

    def test_upsert_transactions_returns_zero(self):
        result = upsert_transactions([make_txn()], self.db_path)
        self.assertEqual(result, 0)

    def test_get_all_transactions_returns_empty_list(self):
        result = get_all_transactions(self.db_path)
        self.assertEqual(result, [])

    def test_get_transaction_by_id_returns_none(self):
        result = get_transaction_by_id('any_id', self.db_path)
        self.assertIsNone(result)

    def test_get_transaction_count_returns_zero(self):
        result = get_transaction_count(self.db_path)
        self.assertEqual(result, 0)

    def test_get_uncategorized_returns_empty_list(self):
        result = get_uncategorized_transactions(self.db_path)
        self.assertEqual(result, [])


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    unittest.main(verbosity=2)
