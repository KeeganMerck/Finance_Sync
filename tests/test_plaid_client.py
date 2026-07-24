"""
tests/test_plaid_client.py
==========================
Unit tests for plaid_client.py.

Uses unittest.mock.patch to mock the Plaid API client. No real API calls are made.
Focus areas:
    - Transaction normalization (amount negation, category extraction, etc.)
    - Access token management (reading from environment)
    - Database integration (get_latest_transaction_date)
    - Schema validation (canonical fields present and correctly typed)

Run from the project root:
    python -m unittest tests/test_plaid_client.py -v
"""

import os
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

##TODO FIX IMPORTS
import plaid_integration
import database as db_module
from modules.database import get_latest_transaction_date, init_db


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_plaid_transaction(**overrides) -> Mock:
    """
    Create a mock Plaid transaction object with realistic test data.

    Args:
        **overrides: Override any field from the defaults.

    Returns:
        Mock object mimicking a Plaid Transaction object.
    """
    base = {
        'transaction_id': 'plaid_txn_001',
        'date': date(2024, 3, 15),
        'account_id': 'plaid_acct_001',
        'merchant_name': 'STARBUCKS',
        'name': 'STARBUCKS #1832 CHARLOTTE NC',
        'amount': 6.45,  # Positive amount (Plaid convention for debit)
        'pending': False,
    }
    base.update(overrides)

    # Create a mock with all attributes
    mock_txn = Mock()
    for key, value in base.items():
        setattr(mock_txn, key, value)

    # Create personal_finance_category object if not explicitly overridden
    if 'personal_finance_category' not in overrides:
        pfc = Mock()
        pfc.primary = 'FOOD_AND_DRINK'
        pfc.detailed = 'FOOD_AND_DRINK_COFFEE'
        mock_txn.personal_finance_category = pfc
    
    # Keep legacy category field for backward compatibility tests (will be None by default)
    if 'category' not in overrides:
        setattr(mock_txn, 'category', None)

    return mock_txn


# ─── Tests for _normalize_plaid_transaction() ──────────────────────────────────

class TestNormalizePlaidTransaction(unittest.TestCase):
    """
    Tests for _normalize_plaid_transaction() — the core schema conversion function.
    """

    def test_all_canonical_keys_present(self):
        """Normalized transaction must have all canonical schema keys."""
        plaid_txn = make_plaid_transaction()
        result = plaid_integration._normalize_plaid_transaction(plaid_txn)

        required_keys = {
            'transaction_id', 'date', 'account', 'merchant', 'description',
            'plaid_category', 'plaid_category_primary', 'user_category', 'amount', 'pending',
            'institution', 'last_updated',
        }
        self.assertEqual(set(result.keys()), required_keys)

    def test_amount_is_negated(self):
        """
        Plaid positive amounts (debits) must be negated to internal negative.
        
        CRITICAL: Plaid uses positive for debits, we use negative for debits.
        """
        # Debit transaction: Plaid sends +6.45 (money leaving)
        plaid_txn = make_plaid_transaction(amount=6.45)
        result = plaid_integration._normalize_plaid_transaction(plaid_txn)

        # Should be negated to -6.45
        self.assertEqual(result['amount'], -6.45)

    def test_amount_negation_for_credit(self):
        """Credit transaction: Plaid sends negative, we negate to positive."""
        # Credit transaction: Plaid sends -50.00 (money coming in)
        plaid_txn = make_plaid_transaction(amount=-50.00)
        result = plaid_integration._normalize_plaid_transaction(plaid_txn)

        # Should be negated to +50.00
        self.assertEqual(result['amount'], 50.00)

    def test_user_category_always_none(self):
        """user_category must always be None when leaving plaid_client."""
        plaid_txn = make_plaid_transaction()
        result = plaid_integration._normalize_plaid_transaction(plaid_txn)

        self.assertIsNone(result['user_category'])

    def test_last_updated_is_valid_iso8601(self):
        """last_updated must be a valid ISO 8601 datetime string."""
        plaid_txn = make_plaid_transaction()
        result = plaid_integration._normalize_plaid_transaction(plaid_txn)

        # Should be parseable as ISO format
        try:
            datetime.fromisoformat(result['last_updated'])
        except ValueError:
            self.fail(f"Invalid ISO 8601 format: {result['last_updated']}")

    def test_plaid_category_uses_last_element(self):
        """
        plaid_category should use the detailed PFC from personal_finance_category.
        """
        pfc_mock = Mock()
        pfc_mock.primary = 'FOOD_AND_DRINK'
        pfc_mock.detailed = 'FOOD_AND_DRINK_FAST_FOOD'
        
        plaid_txn = make_plaid_transaction(personal_finance_category=pfc_mock)
        result = plaid_integration._normalize_plaid_transaction(plaid_txn)

        self.assertEqual(result['plaid_category'], 'FOOD_AND_DRINK_FAST_FOOD')

    def test_plaid_category_empty_when_none(self):
        """plaid_category should be empty string when personal_finance_category is None."""
        plaid_txn = make_plaid_transaction(personal_finance_category=None)
        result = plaid_integration._normalize_plaid_transaction(plaid_txn)

        self.assertEqual(result['plaid_category'], '')

    def test_plaid_category_empty_when_empty_list(self):
        """plaid_category should be empty string when personal_finance_category.detailed is None."""
        pfc_mock = Mock()
        pfc_mock.detailed = None
        pfc_mock.primary = 'FOOD_AND_DRINK'
        
        plaid_txn = make_plaid_transaction(personal_finance_category=pfc_mock)
        result = plaid_integration._normalize_plaid_transaction(plaid_txn)

        self.assertEqual(result['plaid_category'], '')

    def test_merchant_fallback_to_name(self):
        """
        When merchant_name is None, fallback to name field.
        """
        plaid_txn = make_plaid_transaction(
            merchant_name=None,
            name='STARBUCKS #1832 CHARLOTTE NC'
        )
        result = plaid_integration._normalize_plaid_transaction(plaid_txn)

        self.assertEqual(result['merchant'], 'STARBUCKS #1832 CHARLOTTE NC')

    def test_merchant_prefers_merchant_name(self):
        """merchant_name (normalized by Plaid) is preferred over name."""
        plaid_txn = make_plaid_transaction(
            merchant_name='STARBUCKS',
            name='STARBUCKS #1832 CHARLOTTE NC'
        )
        result = plaid_integration._normalize_plaid_transaction(plaid_txn)

        # Should use normalized merchant_name, not raw name
        self.assertEqual(result['merchant'], 'STARBUCKS')

    def test_merchant_empty_when_both_none(self):
        """merchant should be empty string when both merchant_name and name are None."""
        plaid_txn = make_plaid_transaction(merchant_name=None, name=None)
        result = plaid_integration._normalize_plaid_transaction(plaid_txn)

        self.assertEqual(result['merchant'], '')

    def test_description_always_from_name(self):
        """description field always comes from Plaid's name (raw field)."""
        plaid_txn = make_plaid_transaction(name='STARBUCKS #1832 CHARLOTTE NC')
        result = plaid_integration._normalize_plaid_transaction(plaid_txn)

        self.assertEqual(result['description'], 'STARBUCKS #1832 CHARLOTTE NC')

    def test_institution_parameter_is_used(self):
        """institution parameter should be stored in the output."""
        plaid_txn = make_plaid_transaction()
        result = plaid_integration._normalize_plaid_transaction(
            plaid_txn,
            institution='Chase'
        )

        self.assertEqual(result['institution'], 'Chase')

    def test_institution_default_empty_string(self):
        """institution should default to empty string if not provided."""
        plaid_txn = make_plaid_transaction()
        result = plaid_integration._normalize_plaid_transaction(plaid_txn)

        self.assertEqual(result['institution'], '')

    def test_date_converted_to_string(self):
        """date should be converted to ISO string."""
        plaid_txn = make_plaid_transaction(date=date(2024, 3, 15))
        result = plaid_integration._normalize_plaid_transaction(plaid_txn)

        self.assertEqual(result['date'], '2024-03-15')
        self.assertIsInstance(result['date'], str)

    def test_pending_status_preserved(self):
        """pending status should be preserved as-is."""
        # Test pending=True
        plaid_txn = make_plaid_transaction(pending=True)
        result = plaid_integration._normalize_plaid_transaction(plaid_txn)
        self.assertTrue(result['pending'])

        # Test pending=False
        plaid_txn = make_plaid_transaction(pending=False)
        result = plaid_integration._normalize_plaid_transaction(plaid_txn)
        self.assertFalse(result['pending'])

    def test_transaction_id_preserved(self):
        """transaction_id should pass through unchanged."""
        plaid_txn = make_plaid_transaction(transaction_id='unique_txn_abc123')
        result = plaid_integration._normalize_plaid_transaction(plaid_txn)

        self.assertEqual(result['transaction_id'], 'unique_txn_abc123')

    def test_account_id_preserved(self):
        """account field should contain the Plaid account_id."""
        plaid_txn = make_plaid_transaction(account_id='plaid_acct_12345')
        result = plaid_integration._normalize_plaid_transaction(plaid_txn)

        self.assertEqual(result['account'], 'plaid_acct_12345')


# ─── Tests for get_access_tokens() ────────────────────────────────────────────

class TestGetAccessTokens(unittest.TestCase):
    """
    Tests for get_access_tokens() — environment variable parsing.
    """

    def setUp(self):
        """Save original environ for restoration after each test."""
        self.original_environ = dict(os.environ)
        # Set PLAID_ENV to 'sandbox' for test consistency
        os.environ['PLAID_ENV'] = 'sandbox'

    def tearDown(self):
        """Restore original environ."""
        os.environ.clear()
        os.environ.update(self.original_environ)

    @patch('plaid_client.PLAID_ENV', 'sandbox')
    def test_reads_plaid_token_variables(self):
        """Should read all PLAID{ENV}_TOKEN_* environment variables."""
        os.environ['PLAID_SANDBOX_TOKEN_CHASE'] = 'access-sandbox-chase123'
        os.environ['PLAID_SANDBOX_TOKEN_AMEX'] = 'access-sandbox-amex456'

        result = plaid_integration.get_access_tokens()

        self.assertEqual(result['CHASE'], 'access-sandbox-chase123')
        self.assertEqual(result['AMEX'], 'access-sandbox-amex456')

    @patch('plaid_client.PLAID_ENV', 'sandbox')
    def test_strips_plaid_token_prefix(self):
        """PLAID_{ENV}_TOKEN_ prefix should be stripped to get institution name."""
        os.environ['PLAID_SANDBOX_TOKEN_COASTAL_FCU'] = 'access-sandbox-coastal789'

        result = plaid_integration.get_access_tokens()

        # Should have key 'COASTAL_FCU', not 'PLAID_SANDBOX_TOKEN_COASTAL_FCU'
        self.assertIn('COASTAL_FCU', result)
        self.assertNotIn('PLAID_SANDBOX_TOKEN_COASTAL_FCU', result)

    @patch('plaid_client.PLAID_ENV', 'sandbox')
    def test_returns_empty_dict_when_no_tokens(self):
        """Should return empty dict when no PLAID_{ENV}_TOKEN_* vars exist."""
        # Clear all PLAID_{ENV}_TOKEN_* variables
        for key in list(os.environ.keys()):
            if key.startswith('PLAID_') and '_TOKEN_' in key:
                del os.environ[key]

        result = plaid_integration.get_access_tokens()

        self.assertEqual(result, {})

    @patch('plaid_client.PLAID_ENV', 'sandbox')
    def test_ignores_non_plaid_token_vars(self):
        """Should not include environment variables that don't start with PLAID_{ENV}_TOKEN_."""
        os.environ['PLAID_SANDBOX_TOKEN_CHASE'] = 'access-sandbox-chase123'
        os.environ['PLAID_SANDBOX_CLIENT_ID'] = 'client123'
        os.environ['OTHER_VAR'] = 'value'

        result = plaid_integration.get_access_tokens()

        self.assertEqual(len(result), 1)
        self.assertIn('CHASE', result)
        self.assertNotIn('CLIENT_ID', result)
        self.assertNotIn('OTHER_VAR', result)

    @patch('plaid_client.PLAID_ENV', 'sandbox')
    def test_ignores_empty_token_values(self):
        """Should skip PLAID_{ENV}_TOKEN_* vars with empty or None values."""
        os.environ['PLAID_SANDBOX_TOKEN_CHASE'] = 'access-sandbox-chase123'
        os.environ['PLAID_SANDBOX_TOKEN_EMPTY'] = ''
        os.environ['PLAID_SANDBOX_TOKEN_WHITESPACE'] = '   '

        result = plaid_integration.get_access_tokens()

        self.assertIn('CHASE', result)
        # Empty string values should be excluded
        self.assertNotIn('EMPTY', result)
        # Whitespace-only should be included (it's technically a value)
        self.assertIn('WHITESPACE', result)

    @patch('plaid_client.PLAID_ENV', 'sandbox')
    def test_preserves_institution_name_case(self):
        """Institution names should preserve their case from env var names."""
        os.environ['PLAID_SANDBOX_TOKEN_MyBank'] = 'token123'

        result = plaid_integration.get_access_tokens()

        # Environment variable keys are case-sensitive on Unix, case-insensitive on Windows.
        # We just need to verify the token is present under some form of the key.
        self.assertTrue(any(key.upper() == 'MYBANK' for key in result.keys()))


# ─── Tests for get_latest_transaction_date() (database.py) ────────────────────

class TestGetLatestTransactionDate(unittest.TestCase):
    """
    Tests for get_latest_transaction_date() in database.py.
    Uses a real temp SQLite file for each test.
    """

    def setUp(self):
        """Create a fresh temp SQLite database for each test."""
        self.db_fd, db_path_str = tempfile.mkstemp(suffix='.db')
        self.db_path = Path(db_path_str)

        # Patch ENABLE_DATABASE to True for all tests
        self.enable_patch = patch.object(db_module, 'ENABLE_DATABASE', True)
        self.enable_patch.start()

        # Initialize schema in temp DB
        init_db(self.db_path)

    def tearDown(self):
        """Clean up temp database file."""
        self.enable_patch.stop()
        os.close(self.db_fd)
        try:
            os.unlink(self.db_path)
        except Exception:
            pass

    def test_returns_none_on_empty_database(self):
        """Should return None if transactions table is empty."""
        result = get_latest_transaction_date(self.db_path)

        self.assertIsNone(result)

    def test_returns_max_date_when_data_exists(self):
        """Should return the maximum date in the table."""
        from modules.database import upsert_transactions

        transactions = [
            {
                'transaction_id': 'txn_001',
                'date': '2024-01-15',
                'account': 'Checking',
                'merchant': 'Store A',
                'description': 'Purchase at Store A',
                'plaid_category': 'SHOPPING_GENERAL',
                'plaid_category_primary': 'SHOPPING',
                'user_category': None,
                'amount': -50.00,
                'pending': False,
                'institution': 'Chase',
                'last_updated': '2024-03-15T10:00:00',
            },
            {
                'transaction_id': 'txn_002',
                'date': '2024-03-20',
                'account': 'Checking',
                'merchant': 'Store B',
                'description': 'Purchase at Store B',
                'plaid_category': 'SHOPPING_GENERAL',
                'plaid_category_primary': 'SHOPPING',
                'user_category': None,
                'amount': -75.00,
                'pending': False,
                'institution': 'Chase',
                'last_updated': '2024-03-20T10:00:00',
            },
        ]

        upsert_transactions(transactions, self.db_path)
        result = get_latest_transaction_date(self.db_path)

        # Should return the most recent date
        self.assertEqual(result, '2024-03-20')

    def test_returns_none_when_database_disabled(self):
        """Should return None when ENABLE_DATABASE is False."""
        # Patch ENABLE_DATABASE to False
        with patch.object(db_module, 'ENABLE_DATABASE', False):
            result = get_latest_transaction_date(self.db_path)

        self.assertIsNone(result)

    def test_returns_string_type(self):
        """Result should be a string (ISO 8601 date) or None."""
        from modules.database import upsert_transactions

        # Test with empty database
        result = get_latest_transaction_date(self.db_path)
        self.assertTrue(result is None or isinstance(result, str))

        # Test with data
        transactions = [
            {
                'transaction_id': 'txn_001',
                'date': '2024-02-10',
                'account': 'Checking',
                'merchant': 'Store',
                'description': 'Purchase',
                'plaid_category': 'SHOPPING_GENERAL',
                'plaid_category_primary': 'SHOPPING',
                'user_category': None,
                'amount': -25.00,
                'pending': False,
                'institution': 'Chase',
                'last_updated': '2024-02-10T10:00:00',
            },
        ]

        upsert_transactions(transactions, self.db_path)
        result = get_latest_transaction_date(self.db_path)

        self.assertIsInstance(result, str)
        self.assertEqual(result, '2024-02-10')


# ─── Test Running ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    unittest.main()
