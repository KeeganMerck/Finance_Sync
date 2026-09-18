"""
tests/test_sync.py
==================
Unit and integration tests for sync.py.

sync.py is the data ingestion layer. Right now it loads mock JSON.
Eventually it will call Plaid — but this file's tests should still pass
after that swap because they test the OUTPUT CONTRACT, not the source.

The contract sync.py must always fulfill:
    fetch_transactions() returns a list of dicts where each dict:
      - Has all canonical schema keys present
      - Has user_category set to None (never pre-set by sync layer)
      - Has last_updated set to a non-empty ISO 8601 string
      - Has amount as a number (int or float), never a string
      - Has pending as a bool or int, never a string
      - Has transaction_id as a non-empty string

Tests are split into two groups:
    1. normalize_transaction() — pure function, tested with in-memory data,
       always runs regardless of filesystem state.
    2. load_transactions() / fetch_transactions() — require mock_transactions.json,
       skipped gracefully if the file is absent so Carnets tests always pass.

Run from the project root:
    python -m unittest tests/test_sync.py -v
"""

import os
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sync import fetch_transactions, load_transactions, normalize_transaction

MOCK_JSON = (
    Path(__file__).parent.parent.parent
    / "src"
    / "core"
    / "data"
    / "mock_transactions.json"
)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def make_raw_txn(**overrides) -> dict:
    """
    Minimal raw transaction as it would arrive from mock JSON or Plaid.
    Does NOT include user_category or last_updated — those are added by sync.py.
    """
    base = {
        "transaction_id": "raw_001",
        "date": "2024-03-15",
        "account": "Checking ••1234",
        "merchant": "STARBUCKS #1832",
        "description": "STARBUCKS #1832 CHARLOTTE NC",
        "plaid_category": "FOOD_AND_DRINK_COFFEE",
        "plaid_category_primary": "FOOD_AND_DRINK",
        "amount": -6.45,
        "pending": False,
        "institution": "Coastal Federal Credit Union",
    }
    base.update(overrides)
    return base


# ─── normalize_transaction() Tests ────────────────────────────────────────────


class TestNormalizeTransaction(unittest.TestCase):
    """
    Tests for normalize_transaction() — a pure function that converts a raw
    institution record into the canonical internal schema.

    These tests run without any filesystem dependency.
    """

    def test_returns_dict(self):
        result = normalize_transaction(make_raw_txn())
        self.assertIsInstance(result, dict)

    def test_all_canonical_keys_present(self):
        """Output must contain every key in the canonical schema."""
        required = {
            "transaction_id",
            "date",
            "account",
            "merchant",
            "description",
            "plaid_category",
            "plaid_category_primary",
            "user_category",
            "amount",
            "pending",
            "institution",
            "last_updated",
        }
        result = normalize_transaction(make_raw_txn())
        missing = required - set(result.keys())
        self.assertFalse(missing, f"Canonical keys missing from output: {missing}")

    # ── user_category contract ─────────────────────────────────────────────────

    def test_user_category_is_none(self):
        """
        sync.py must never pre-set user_category. That is categorizer.py's job.
        If sync.py sets user_category, categorizer overrides become invisible.
        """
        result = normalize_transaction(make_raw_txn())
        self.assertIsNone(
            result["user_category"], "sync.py must not pre-set user_category"
        )

    def test_user_category_is_none_regardless_of_input(self):
        """Even if the raw record somehow has user_category, output must be None."""
        raw = make_raw_txn()
        raw["user_category"] = "SomeCategory"  # simulate unexpected input field
        result = normalize_transaction(raw)
        self.assertIsNone(result["user_category"])

    # ── last_updated contract ──────────────────────────────────────────────────

    def test_last_updated_is_set(self):
        """last_updated must be a non-empty string set by sync, not the caller."""
        result = normalize_transaction(make_raw_txn())
        self.assertIsNotNone(result["last_updated"])
        self.assertIsInstance(result["last_updated"], str)
        self.assertTrue(len(result["last_updated"]) > 0)

    def test_last_updated_is_valid_iso8601(self):
        """last_updated must be parseable as an ISO 8601 datetime."""
        result = normalize_transaction(make_raw_txn())
        try:
            datetime.fromisoformat(result["last_updated"])
        except ValueError:
            self.fail(f"last_updated is not valid ISO 8601: '{result['last_updated']}'")

    # ── Field pass-through ─────────────────────────────────────────────────────

    def test_transaction_id_preserved(self):
        result = normalize_transaction(make_raw_txn(transaction_id="abc123"))
        self.assertEqual(result["transaction_id"], "abc123")

    def test_date_preserved(self):
        result = normalize_transaction(make_raw_txn(date="2024-07-04"))
        self.assertEqual(result["date"], "2024-07-04")

    def test_account_preserved(self):
        result = normalize_transaction(make_raw_txn(account="Amex Gold ••1009"))
        self.assertEqual(result["account"], "Amex Gold ••1009")

    def test_merchant_preserved(self):
        """Raw merchant must pass through unchanged — normalization runs later."""
        result = normalize_transaction(make_raw_txn(merchant="STARBUCKS #1832"))
        self.assertEqual(result["merchant"], "STARBUCKS #1832")

    def test_description_preserved(self):
        result = normalize_transaction(make_raw_txn(description="STARBUCKS #1832 NC"))
        self.assertEqual(result["description"], "STARBUCKS #1832 NC")

    def test_plaid_category_preserved(self):
        result = normalize_transaction(make_raw_txn(plaid_category="FOOD_AND_DRINK"))
        self.assertEqual(result["plaid_category"], "FOOD_AND_DRINK")

    def test_institution_preserved(self):
        result = normalize_transaction(make_raw_txn(institution="Chase"))
        self.assertEqual(result["institution"], "Chase")

    # ── Amount type contract ───────────────────────────────────────────────────

    def test_amount_is_numeric(self):
        """Amount must be a number — never a string. Excel formulas will break otherwise."""
        result = normalize_transaction(make_raw_txn(amount=-52.99))
        self.assertIsInstance(result["amount"], (int, float))

    def test_negative_amount_preserved(self):
        result = normalize_transaction(make_raw_txn(amount=-6.45))
        self.assertAlmostEqual(result["amount"], -6.45, places=2)

    def test_positive_amount_preserved(self):
        result = normalize_transaction(make_raw_txn(amount=3240.00))
        self.assertAlmostEqual(result["amount"], 3240.00, places=2)

    def test_zero_amount_preserved(self):
        result = normalize_transaction(make_raw_txn(amount=0.0))
        self.assertEqual(result["amount"], 0.0)

    # ── Pending type contract ──────────────────────────────────────────────────

    def test_pending_false_preserved(self):
        result = normalize_transaction(make_raw_txn(pending=False))
        self.assertFalse(result["pending"])

    def test_pending_true_preserved(self):
        result = normalize_transaction(make_raw_txn(pending=True))
        self.assertTrue(result["pending"])

    # ── Immutability ───────────────────────────────────────────────────────────

    def test_original_dict_not_mutated(self):
        """normalize_transaction must not modify its input argument."""
        raw = make_raw_txn(merchant="ORIGINAL")
        normalize_transaction(raw)
        self.assertEqual(raw["merchant"], "ORIGINAL")
        self.assertNotIn("user_category", raw)
        self.assertNotIn("last_updated", raw)


# ─── load_transactions() and fetch_transactions() Tests ───────────────────────


class TestLoadTransactions(unittest.TestCase):
    """
    Tests for load_transactions() — requires mock_transactions.json.
    Skipped automatically if the file is absent.
    """

    def setUp(self):
        if not MOCK_JSON.exists():
            self.skipTest(f"mock_transactions.json not found at {MOCK_JSON}")

    def test_returns_list(self):
        result = load_transactions()
        self.assertIsInstance(result, list)

    def test_returns_non_empty_list(self):
        result = load_transactions()
        self.assertGreater(len(result), 0)

    def test_each_item_is_dict(self):
        result = load_transactions()
        for item in result:
            self.assertIsInstance(item, dict)

    def test_raw_records_have_transaction_id(self):
        """Raw JSON records must have transaction_id before normalization."""
        result = load_transactions()
        for txn in result:
            self.assertIn("transaction_id", txn)
            self.assertTrue(len(txn["transaction_id"]) > 0)

    def test_raw_records_have_required_fields(self):
        """Fields that normalize_transaction() reads must exist in raw JSON."""
        required = {
            "transaction_id",
            "date",
            "account",
            "merchant",
            "description",
            "plaid_category",
            "amount",
            "pending",
            "institution",
        }
        result = load_transactions()
        for txn in result:
            missing = required - set(txn.keys())
            self.assertFalse(
                missing,
                f"Raw record {txn.get('transaction_id')} missing fields: {missing}",
            )


class TestFetchTransactions(unittest.TestCase):
    """
    Tests for fetch_transactions() — the primary sync entrypoint.
    Requires mock_transactions.json. Skipped automatically if absent.

    These tests verify the OUTPUT CONTRACT that Plaid integration must
    also satisfy — they should still pass after sync.py is updated to
    call plaid_client.py instead of loading mock JSON.
    """

    def setUp(self):
        if not MOCK_JSON.exists():
            self.skipTest(f"mock_transactions.json not found at {MOCK_JSON}")
        self.transactions = fetch_transactions()

    def test_returns_list(self):
        self.assertIsInstance(self.transactions, list)

    def test_returns_non_empty_list(self):
        self.assertGreater(len(self.transactions), 0)

    def test_all_canonical_keys_present_in_every_transaction(self):
        """Every transaction must have all canonical schema keys."""
        required = {
            "transaction_id",
            "date",
            "account",
            "merchant",
            "description",
            "plaid_category",
            "plaid_category_primary",
            "user_category",
            "amount",
            "pending",
            "institution",
            "last_updated",
        }
        for txn in self.transactions:
            missing = required - set(txn.keys())
            self.assertFalse(
                missing, f"Transaction {txn.get('transaction_id')} missing: {missing}"
            )

    def test_user_category_is_none_for_all(self):
        """sync.py must not pre-assign user_category to any transaction."""
        for txn in self.transactions:
            self.assertIsNone(
                txn["user_category"],
                f"user_category pre-set for {txn.get('transaction_id')}",
            )

    def test_last_updated_set_for_all(self):
        """Every transaction must have last_updated set to a valid ISO 8601 string."""
        for txn in self.transactions:
            self.assertIsNotNone(txn["last_updated"])
            try:
                datetime.fromisoformat(txn["last_updated"])
            except ValueError:
                self.fail(
                    f"Invalid last_updated for {txn.get('transaction_id')}: "
                    f"'{txn['last_updated']}'"
                )

    def test_all_amounts_are_numeric(self):
        for txn in self.transactions:
            self.assertIsInstance(
                txn["amount"],
                (int, float),
                f"Amount is not numeric for {txn.get('transaction_id')}",
            )

    def test_no_duplicate_transaction_ids(self):
        """
        transaction_id must be unique across all fetched transactions.
        Duplicates here would cause silent data overwrites in the database.
        """
        ids = [txn["transaction_id"] for txn in self.transactions]
        self.assertEqual(
            len(ids),
            len(set(ids)),
            f"Duplicate transaction_ids found: "
            f"{[i for i in ids if ids.count(i) > 1]}",
        )

    def test_all_dates_are_strings(self):
        """Dates must be strings (ISO format) so SQLite text comparison works."""
        for txn in self.transactions:
            self.assertIsInstance(
                txn["date"],
                str,
                f"Date is not a string for {txn.get('transaction_id')}",
            )

    def test_transaction_count_matches_mock_json(self):
        """fetch_transactions must return one record per raw JSON entry."""
        import json

        with open(MOCK_JSON, encoding="utf-8") as f:
            raw = json.load(f)
        self.assertEqual(len(self.transactions), len(raw))


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
