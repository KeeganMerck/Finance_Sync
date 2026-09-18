"""
tests/test_integration.py
=========================
End-to-end integration tests for the full finance sync pipeline.

These tests exercise the complete flow:
    sync (mock data) -> normalization -> categorization -> export (dry run)
                                     -> database (temp SQLite)

Unlike unit tests, integration tests do NOT mock individual functions.
They let the real modules talk to each other to catch wiring bugs that
unit tests cannot detect — e.g., normalization output being incompatible
with rule matching input, or export receiving the wrong field names.

Two data sources are used:
    1. INLINE_TRANSACTIONS: hardcoded in this file — always available,
       no filesystem dependency, safe to run anywhere including Carnets.
    2. MOCK_JSON: loads from data/mock_transactions.json if the file
       exists — skipped gracefully if not found.

Database tests use a real temp SQLite file created in setUp and deleted
in tearDown. ENABLE_DATABASE is patched to True.

Run from the project root:
    python -m unittest tests/test_integration.py -v

Or run directly in Carnets.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database as db_module

from modules.categorizer import CategoryRule, categorize_transactions, resolve_category
from modules.database import (
    get_all_transactions,
    get_transaction_count,
    get_uncategorized_transactions,
    init_db,
    upsert_transactions,
)
from modules.export import run_exports

# ─── Shared Test Data ─────────────────────────────────────────────────────────

# Representative inline transactions — cover the most important real-world
# cases without requiring the mock JSON file to be present.
INLINE_TRANSACTIONS = [
    {
        "transaction_id": "int_001",
        "date": "2024-03-01",
        "account": "Coastal Checking ••7821",
        "merchant": "STARBUCKS #1832",
        "description": "STARBUCKS #1832 CHARLOTTE NC",
        "plaid_category": "FOOD_AND_DRINK_COFFEE",
        "plaid_category_primary": "FOOD_AND_DRINK",
        "user_category": None,
        "amount": -6.45,
        "pending": False,
        "institution": "Coastal Federal Credit Union",
        "last_updated": "2024-03-01T08:00:00",
    },
    {
        "transaction_id": "int_002",
        "date": "2024-03-02",
        "account": "Chase Sapphire ••4532",
        "merchant": "AMZN MKTP US*AB1234CD5",
        "description": "AMZN MKTP US*AB1234CD5",
        "plaid_category": "SHOPPING_GENERAL",
        "plaid_category_primary": "SHOPPING",
        "user_category": None,
        "amount": -34.99,
        "pending": False,
        "institution": "Chase",
        "last_updated": "2024-03-02T10:00:00",
    },
    {
        "transaction_id": "int_003",
        "date": "2024-03-03",
        "account": "Coastal Checking ••7821",
        "merchant": "WF PAYROLL",
        "description": "WELLS FARGO PAYROLL DIR DEP",
        "plaid_category": "INCOME_PAYROLL",
        "plaid_category_primary": "INCOME",
        "user_category": None,
        "amount": 3240.00,
        "pending": False,
        "institution": "Coastal Federal Credit Union",
        "last_updated": "2024-03-03T09:00:00",
    },
    {
        "transaction_id": "int_004",
        "date": "2024-03-04",
        "account": "Amex Gold ••1009",
        "merchant": "WELLS FARGO VISA",
        "description": "WELLS FARGO VISA AUTOPAY",
        "plaid_category": "LOAN_PAYMENTS",
        "plaid_category_primary": "LOAN_PAYMENTS",
        "user_category": None,
        "amount": -450.00,
        "pending": False,
        "institution": "American Express",
        "last_updated": "2024-03-04T12:00:00",
    },
    {
        "transaction_id": "int_005",
        "date": "2024-03-05",
        "account": "Chase Sapphire ••4532",
        "merchant": "LYFT *RIDE SUN 9PM 123456",
        "description": "LYFT *RIDE SUN 9PM 123456",
        "plaid_category": "TRANSPORTATION_TAXI",
        "plaid_category_primary": "TRANSPORTATION",
        "user_category": None,
        "amount": -18.75,
        "pending": False,
        "institution": "Chase",
        "last_updated": "2024-03-05T21:30:00",
    },
    {
        "transaction_id": "int_006",
        "date": "2024-03-06",
        "account": "Chase Sapphire ••4532",
        "merchant": "PENDING DOORDASH",
        "description": "PENDING DOORDASH*ORDER 4421",
        "plaid_category": "FOOD_AND_DRINK_DELIVERY",
        "plaid_category_primary": "FOOD_AND_DRINK",
        "user_category": None,
        "amount": -31.50,
        "pending": True,
        "institution": "Chase",
        "last_updated": "2024-03-06T19:00:00",
    },
    {
        "transaction_id": "int_007",
        "date": "2024-03-07",
        "account": "Amex Gold ••1009",
        "merchant": "TRULY UNKNOWN MERCHANT XYZ",
        "description": "TRULY UNKNOWN MERCHANT XYZ 99999",
        "plaid_category": "",
        "plaid_category_primary": "",
        "user_category": None,
        "amount": -22.00,
        "pending": False,
        "institution": "American Express",
        "last_updated": "2024-03-07T14:00:00",
    },
]

# Category rules that align with the inline transactions above
INLINE_RULES = [
    CategoryRule(
        match_type="exact",
        pattern="WF PAYROLL",
        user_category="Income",
        normalized_merchant="WF Payroll",
    ),
    CategoryRule(
        match_type="contains",
        pattern="STARBUCKS",
        user_category="Coffee",
        normalized_merchant="STARBUCKS",
    ),
    CategoryRule(
        match_type="contains",
        pattern="AMZN",
        user_category="Shopping",
        normalized_merchant="AMAZON",
    ),
    CategoryRule(
        match_type="contains",
        pattern="LYFT",
        user_category="Transportation",
        normalized_merchant="LYFT",
    ),
    CategoryRule(
        match_type="contains",
        pattern="DOORDASH",
        user_category="Food Delivery",
        normalized_merchant="DOORDASH",
    ),
]


# ─── Normalization + Categorization Integration ───────────────────────────────


class TestNormalizationToCategorization(unittest.TestCase):
    """
    Verify that normalization output feeds cleanly into rule matching.
    This catches any interface mismatch between the two modules.
    """

    def _run(self, transactions=None, rules=None):
        txns = transactions or [t.copy() for t in INLINE_TRANSACTIONS]
        rules = rules or INLINE_RULES
        return categorize_transactions(txns, rules=rules, pre_normalize=True)

    def test_starbucks_hash_normalized_and_categorized(self):
        """
        Raw: "STARBUCKS #1832"
        After normalization: "STARBUCKS"
        After rules: merchant="STARBUCKS", category="Coffee"
        """
        results, _, _ = self._run()
        starbucks = next(t for t in results if t["transaction_id"] == "int_001")
        self.assertEqual(starbucks["merchant"], "STARBUCKS")
        self.assertEqual(starbucks["user_category"], "Coffee")

    def test_amazon_asterisk_code_normalized_and_categorized(self):
        """
        Raw: "AMZN MKTP US*AB1234CD5"
        After normalization: "AMZN MKTP US"
        After rules (contains AMZN): merchant="AMAZON", category="Shopping"
        """
        results, _, _ = self._run()
        amazon = next(t for t in results if t["transaction_id"] == "int_002")
        self.assertEqual(amazon["merchant"], "AMAZON")
        self.assertEqual(amazon["user_category"], "Shopping")

    def test_lyft_asterisk_normalized_and_categorized(self):
        """
        Raw: "LYFT *RIDE SUN 9PM 123456"
        After normalization: "LYFT"
        After rules: merchant="LYFT", category="Transportation"
        """
        results, _, _ = self._run()
        lyft = next(t for t in results if t["transaction_id"] == "int_005")
        self.assertEqual(lyft["merchant"], "LYFT")
        self.assertEqual(lyft["user_category"], "Transportation")

    def test_payroll_exact_rule_matches_after_normalization(self):
        """
        "WF PAYROLL" should not be altered by normalization (no noise to strip).
        Exact rule must still fire cleanly.
        """
        results, _, _ = self._run()
        payroll = next(t for t in results if t["transaction_id"] == "int_003")
        self.assertEqual(payroll["user_category"], "Income")

    def test_wf_payroll_and_wells_fargo_visa_remain_distinct(self):
        """
        Critical: the payroll exact rule must never fire on the Visa payment.
        This verifies merchant isolation end-to-end.
        """
        results, _, _ = self._run()
        payroll = next(t for t in results if t["transaction_id"] == "int_003")
        visa = next(t for t in results if t["transaction_id"] == "int_004")
        self.assertEqual(payroll["user_category"], "Income")
        self.assertNotEqual(
            visa["user_category"],
            "Income",
            "WELLS FARGO VISA must not be categorized as Income",
        )

    def test_plaid_category_never_modified(self):
        """plaid_category must be identical before and after the full pipeline."""
        originals = {
            t["transaction_id"]: t["plaid_category"] for t in INLINE_TRANSACTIONS
        }
        results, _, _ = self._run()
        for txn in results:
            original_plaid = originals[txn["transaction_id"]]
            self.assertEqual(
                txn["plaid_category"],
                original_plaid,
                f"plaid_category modified for {txn['transaction_id']}",
            )

    def test_uncategorized_transaction_still_returned(self):
        """A transaction with no matching rule must still appear in output."""
        results, _, uncat = self._run()
        unknown = next((t for t in results if t["transaction_id"] == "int_007"), None)
        self.assertIsNotNone(unknown, "Uncategorized transaction missing from output")
        self.assertGreater(uncat, 0)

    def test_pending_transaction_processed_normally(self):
        """Pending transactions are not filtered — they go through the full pipeline."""
        results, _, _ = self._run()
        pending = next(t for t in results if t["transaction_id"] == "int_006")
        self.assertEqual(pending["user_category"], "Food Delivery")

    def test_all_input_transactions_returned(self):
        """Every input transaction must appear in output regardless of match status."""
        results, _, _ = self._run()
        self.assertEqual(len(results), len(INLINE_TRANSACTIONS))

    def test_categorized_plus_uncategorized_equals_total(self):
        """Count sanity check: categorized + uncategorized must equal total."""
        results, cat, uncat = self._run()
        self.assertEqual(cat + uncat, len(results))


# ─── Categorization + Export Integration ──────────────────────────────────────


class TestCategorizationToExport(unittest.TestCase):
    """
    Verify that categorized transaction data feeds cleanly into the export layer.
    All export calls use dry_run=True so no files are written.
    """

    def setUp(self):
        txns = [t.copy() for t in INLINE_TRANSACTIONS]
        self.results, self.cat_count, self.uncat_count = categorize_transactions(
            txns, rules=INLINE_RULES, pre_normalize=True
        )

    def test_export_returns_correct_row_count(self):
        summary = run_exports(self.results, include_raw=True, dry_run=True)
        self.assertEqual(summary["cash_flow_rows"], len(INLINE_TRANSACTIONS))

    def test_export_cash_flow_and_raw_counts_match(self):
        summary = run_exports(self.results, include_raw=True, dry_run=True)
        self.assertEqual(summary["cash_flow_rows"], summary["raw_rows"])

    def test_export_without_raw(self):
        summary = run_exports(self.results, include_raw=False, dry_run=True)
        self.assertIn("cash_flow_rows", summary)
        self.assertNotIn("raw_rows", summary)

    def test_resolve_category_uses_user_category(self):
        """After full categorization, resolved category should be user_category."""
        starbucks = next(t for t in self.results if t["transaction_id"] == "int_001")
        self.assertEqual(resolve_category(starbucks), "Coffee")

    def test_resolve_category_falls_back_to_plaid(self):
        """Transactions with no matching rule should resolve to plaid_category."""
        # WELLS FARGO VISA has plaid_category='LOAN_PAYMENTS' and no user rule match
        visa = next(t for t in self.results if t["transaction_id"] == "int_004")
        self.assertEqual(resolve_category(visa), "LOAN_PAYMENTS")


# ─── Full Pipeline + Database Integration ─────────────────────────────────────


class TestFullPipelineWithDatabase(unittest.TestCase):
    """
    Tests the complete pipeline including database persistence:
        normalize -> categorize -> upsert -> read back -> export
    """

    def setUp(self):
        self.db_fd, db_path_str = tempfile.mkstemp(suffix=".db")
        self.db_path = Path(db_path_str)
        self.enable_patch = patch.object(db_module, "ENABLE_DATABASE", True)
        self.enable_patch.start()
        init_db(self.db_path)

    def tearDown(self):
        self.enable_patch.stop()
        os.close(self.db_fd)
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def _run_pipeline(self, transactions=None):
        txns = [t.copy() for t in (transactions or INLINE_TRANSACTIONS)]
        results, cat, uncat = categorize_transactions(
            txns, rules=INLINE_RULES, pre_normalize=True
        )
        upsert_transactions(results, self.db_path)
        return results, cat, uncat

    def test_pipeline_persists_all_transactions(self):
        results, _, _ = self._run_pipeline()
        self.assertEqual(get_transaction_count(self.db_path), len(results))

    def test_pipeline_is_idempotent(self):
        """Running the full pipeline twice must not duplicate rows."""
        self._run_pipeline()
        self._run_pipeline()
        self.assertEqual(get_transaction_count(self.db_path), len(INLINE_TRANSACTIONS))

    def test_categorized_data_persisted_correctly(self):
        """user_category applied by categorizer must survive the DB round-trip."""
        self._run_pipeline()
        all_txns = get_all_transactions(self.db_path)
        starbucks = next(t for t in all_txns if t["transaction_id"] == "int_001")
        self.assertEqual(starbucks["user_category"], "Coffee")
        self.assertEqual(starbucks["merchant"], "STARBUCKS")

    def test_plaid_category_preserved_in_db(self):
        """plaid_category stored in DB must match the original value."""
        self._run_pipeline()
        all_txns = get_all_transactions(self.db_path)
        starbucks = next(t for t in all_txns if t["transaction_id"] == "int_001")
        self.assertEqual(starbucks["plaid_category"], "FOOD_AND_DRINK_COFFEE")

    def test_uncategorized_query_after_pipeline(self):
        """Uncategorized query must identify the transaction with no category."""
        self._run_pipeline()
        uncat = get_uncategorized_transactions(self.db_path)
        ids = {t["transaction_id"] for t in uncat}
        self.assertIn("int_007", ids)

    def test_db_data_feeds_export_correctly(self):
        """Data read back from DB must produce a valid export summary."""
        self._run_pipeline()
        db_txns = get_all_transactions(self.db_path)
        summary = run_exports(db_txns, include_raw=True, dry_run=True)
        self.assertEqual(summary["cash_flow_rows"], len(INLINE_TRANSACTIONS))


# ─── Mock JSON Integration Test (skipped if file absent) ──────────────────────


class TestMockJsonPipeline(unittest.TestCase):
    """
    Runs the full pipeline against the actual mock_transactions.json file.
    Skipped automatically if the file doesn't exist so Carnets tests always pass
    even when run outside the full project directory structure.
    """

    MOCK_JSON = (
        Path(__file__).parent.parent.parent
        / "src"
        / "core"
        / "data"
        / "mock_transactions.json"
    )

    def setUp(self):
        if not self.MOCK_JSON.exists():
            self.skipTest(
                f"mock_transactions.json not found at {self.MOCK_JSON} — skipping."
            )

        with open(self.MOCK_JSON, encoding="utf-8") as f:
            raw = json.load(f)

        # Add user_category=None and last_updated if not present (sync.py adds these)
        self.transactions = []
        from datetime import datetime

        for txn in raw:
            copy = txn.copy()
            copy.setdefault("user_category", None)
            copy.setdefault("last_updated", datetime.utcnow().isoformat())
            self.transactions.append(copy)

    def test_all_mock_transactions_processed(self):
        results, cat, uncat = categorize_transactions(
            self.transactions, rules=INLINE_RULES, pre_normalize=True
        )
        self.assertEqual(len(results), len(self.transactions))
        self.assertEqual(cat + uncat, len(results))

    def test_no_plaid_categories_modified(self):
        originals = {
            t["transaction_id"]: t.get("plaid_category", "") for t in self.transactions
        }
        results, _, _ = categorize_transactions(
            self.transactions, rules=INLINE_RULES, pre_normalize=True
        )
        for txn in results:
            self.assertEqual(
                txn.get("plaid_category", ""),
                originals[txn["transaction_id"]],
                f"plaid_category modified for {txn['transaction_id']}",
            )

    def test_export_row_count_matches_input(self):
        results, _, _ = categorize_transactions(
            self.transactions, rules=INLINE_RULES, pre_normalize=True
        )
        summary = run_exports(results, include_raw=True, dry_run=True)
        self.assertEqual(summary["cash_flow_rows"], len(self.transactions))

    def test_starbucks_variants_all_normalized(self):
        """All three Starbucks merchant variants in mock data should normalize cleanly."""
        results, _, _ = categorize_transactions(
            self.transactions, rules=INLINE_RULES, pre_normalize=True
        )
        starbucks_txns = [
            t for t in results if "starbucks" in t.get("merchant", "").lower()
        ]
        for txn in starbucks_txns:
            self.assertEqual(
                txn["merchant"],
                "STARBUCKS",
                f"Starbucks variant not normalized: {txn['transaction_id']}",
            )


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
