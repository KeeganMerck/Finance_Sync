"""
tests/test_categorizer.py
=========================
Unit tests for categorizer.py.

Tests are self-contained — no filesystem I/O, no config dependencies.
Rules are constructed in-memory so tests run identically on any machine.

Run from the project root:
    python -m unittest tests/test_categorizer.py -v

Or in Carnets: run this file directly (the __main__ block at the bottom
calls unittest.main() so it executes inline).
"""

import sys
import os
import unittest

# Allow imports from the project root regardless of where tests are run from
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from modules.categorizer import (
    CategoryRule,
    apply_rules,
    categorize_transactions,
    resolve_category,
)


# ─── Helpers ───────────────────────────────────────────────────────────────────

def make_txn(**overrides) -> dict:
    """
    Return a minimal canonical transaction dict with sensible defaults.
    Override any field by passing it as a keyword argument.
    """
    base = {
        'transaction_id': 'txn_test_001',
        'date':           '2024-03-15',
        'account':        'Checking',
        'merchant':       'UNKNOWN MERCHANT',
        'description':    'UNKNOWN MERCHANT #999',
        'plaid_category': '',
        'user_category':  None,
        'amount':         -12.50,
        'pending':        False,
        'institution':    'Test Bank',
        'last_updated':   '2024-03-15T12:00:00',
    }
    base.update(overrides)
    return base


def make_rule(match_type='contains', pattern='STARBUCKS',
              user_category='Coffee', normalized_merchant='STARBUCKS') -> CategoryRule:
    """Return a CategoryRule with sensible defaults."""
    return CategoryRule(
        match_type=match_type,
        pattern=pattern.upper(),
        user_category=user_category,
        normalized_merchant=normalized_merchant,
    )


# ─── CategoryRule Tests ────────────────────────────────────────────────────────

class TestCategoryRule(unittest.TestCase):
    """Tests for the CategoryRule dataclass itself."""

    def test_is_frozen(self):
        """CategoryRule must be immutable — mutation should raise."""
        rule = make_rule()
        with self.assertRaises((AttributeError, TypeError)):
            rule.pattern = 'NEW_PATTERN'

    def test_fields_accessible(self):
        """All fields should be readable after construction."""
        rule = CategoryRule(
            match_type='exact',
            pattern='WELLS FARGO PAYROLL',
            user_category='Income',
            normalized_merchant='Wells Fargo Payroll',
        )
        self.assertEqual(rule.match_type, 'exact')
        self.assertEqual(rule.pattern, 'WELLS FARGO PAYROLL')
        self.assertEqual(rule.user_category, 'Income')
        self.assertEqual(rule.normalized_merchant, 'Wells Fargo Payroll')


# ─── apply_rules Tests ─────────────────────────────────────────────────────────

class TestApplyRules(unittest.TestCase):
    """Tests for apply_rules() — the core single-transaction matcher."""

    # ── Contains matching ──────────────────────────────────────────────────────

    def test_contains_match_on_merchant(self):
        """A 'contains' rule should fire when the pattern is in the merchant field."""
        txn = make_txn(merchant='STARBUCKS #1832', description='STARBUCKS #1832 PORTLAND')
        rules = [make_rule(match_type='contains', pattern='STARBUCKS')]
        result = apply_rules(txn, rules)
        self.assertEqual(result['merchant'], 'STARBUCKS')
        self.assertEqual(result['user_category'], 'Coffee')

    def test_contains_match_on_description(self):
        """A 'contains' rule should also fire when the pattern is only in description."""
        txn = make_txn(merchant='', description='WHOLEFDS MKT 10293')
        rules = [make_rule(match_type='contains', pattern='WHOLEFDS',
                           user_category='Groceries', normalized_merchant='WHOLE FOODS')]
        result = apply_rules(txn, rules)
        self.assertEqual(result['merchant'], 'WHOLE FOODS')
        self.assertEqual(result['user_category'], 'Groceries')

    def test_contains_match_is_case_insensitive(self):
        """Matching should work regardless of the case of source data."""
        txn = make_txn(merchant='Starbucks Store 2021')
        rules = [make_rule(match_type='contains', pattern='STARBUCKS')]
        result = apply_rules(txn, rules)
        self.assertEqual(result['user_category'], 'Coffee')

    def test_multi_field_and_matching_requires_all_fields(self):
        """A compound rule should require every listed field to match."""
        txn = make_txn(date='2024-03-01', merchant='Bilt Rewards')
        rule = CategoryRule(
            match_type='contains',
            match_field='day_of_month AND merchant',
            pattern='01|BILT',
            user_category='Rent & Utilities',
            normalized_merchant='',
        )
        result = apply_rules(txn, [rule])
        self.assertEqual(result['user_category'], 'Rent & Utilities')

    def test_multi_field_and_matching_does_not_fire_for_other_merchants(self):
        """A compound rule should not match unrelated merchants on the same date."""
        txn = make_txn(date='2024-03-01', merchant='Starbucks')
        rule = CategoryRule(
            match_type='contains',
            match_field='day_of_month AND merchant',
            pattern='01|BILT',
            user_category='Rent & Utilities',
            normalized_merchant='',
        )
        result = apply_rules(txn, [rule])
        self.assertIsNone(result['user_category'])

    def test_contains_no_match(self):
        """A 'contains' rule should not fire when the pattern is absent."""
        txn = make_txn(merchant='NETFLIX', description='NETFLIX MONTHLY')
        rules = [make_rule(match_type='contains', pattern='STARBUCKS')]
        result = apply_rules(txn, rules)
        self.assertIsNone(result['user_category'])
        self.assertEqual(result['merchant'], 'NETFLIX')

    # ── Exact matching ─────────────────────────────────────────────────────────

    def test_exact_match_on_merchant(self):
        """An 'exact' rule should fire on a full merchant name match."""
        txn = make_txn(merchant='WELLS FARGO PAYROLL', description='DIRECT DEPOSIT')
        rules = [make_rule(match_type='exact', pattern='WELLS FARGO PAYROLL',
                           user_category='Income', normalized_merchant='Wells Fargo Payroll')]
        result = apply_rules(txn, rules)
        self.assertEqual(result['user_category'], 'Income')
        self.assertEqual(result['merchant'], 'Wells Fargo Payroll')

    def test_exact_match_requires_full_match(self):
        """An 'exact' rule must NOT fire on a partial string match."""
        txn = make_txn(merchant='WELLS FARGO VISA PAYMENT', description='')
        rules = [make_rule(match_type='exact', pattern='WELLS FARGO PAYROLL',
                           user_category='Income', normalized_merchant='Wells Fargo Payroll')]
        result = apply_rules(txn, rules)
        self.assertIsNone(result['user_category'])

    def test_exact_does_not_accidentally_merge_similar_merchants(self):
        """
        Critical merchant isolation test.
        'WF PAYROLL' and 'WELLS FARGO VISA' should never resolve to the same rule.
        """
        payroll_rule = CategoryRule(
            match_type='exact',
            pattern='WF PAYROLL',
            user_category='Income',
            normalized_merchant='WF Payroll',
        )
        rules = [payroll_rule]

        payroll_txn = make_txn(merchant='WF PAYROLL', description='')
        visa_txn    = make_txn(merchant='WELLS FARGO VISA', description='AUTOPAY')

        payroll_result = apply_rules(payroll_txn, rules)
        visa_result    = apply_rules(visa_txn,    rules)

        self.assertEqual(payroll_result['user_category'], 'Income',
                         "Payroll transaction should be categorized as Income")
        self.assertIsNone(visa_result['user_category'],
                          "Wells Fargo Visa transaction should NOT match payroll rule")

    # ── First-match-wins ───────────────────────────────────────────────────────

    def test_first_match_wins(self):
        """
        When multiple rules could match, only the first one should be applied.
        This is the documented priority mechanism.
        """
        rules = [
            make_rule(match_type='exact',    pattern='STARBUCKS',
                      user_category='Coffee Exact',    normalized_merchant='Starbucks Exact'),
            make_rule(match_type='contains', pattern='STARBUCKS',
                      user_category='Coffee Contains', normalized_merchant='Starbucks Contains'),
        ]
        txn = make_txn(merchant='STARBUCKS', description='')
        result = apply_rules(txn, rules)
        self.assertEqual(result['user_category'], 'Coffee Exact')
        self.assertEqual(result['merchant'], 'Starbucks Exact')

    def test_subsequent_rules_do_not_fire_after_match(self):
        """After the first match, remaining rules must not modify the transaction."""
        rules = [
            make_rule(match_type='contains', pattern='AMAZON',
                      user_category='Shopping', normalized_merchant='AMAZON'),
            CategoryRule(match_type='contains', pattern='AMAZON',
                         user_category='SHOULD NOT APPLY', normalized_merchant='WRONG'),
        ]
        txn = make_txn(merchant='AMAZON MKTPL')
        result = apply_rules(txn, rules)
        self.assertEqual(result['user_category'], 'Shopping')
        self.assertNotEqual(result['user_category'], 'SHOULD NOT APPLY')

    # ── Partial rule fields ────────────────────────────────────────────────────

    def test_rule_with_empty_user_category_only_normalizes_merchant(self):
        """A rule with no user_category should still normalize the merchant."""
        rule = CategoryRule(match_type='contains', pattern='AMZN',
                            user_category='', normalized_merchant='AMAZON')
        txn = make_txn(merchant='AMZN MKTP US')
        result = apply_rules(txn, [rule])
        self.assertEqual(result['merchant'], 'AMAZON')
        self.assertIsNone(result['user_category'])

    def test_rule_with_empty_normalized_merchant_only_sets_category(self):
        """A rule with no normalized_merchant should only apply the category."""
        rule = CategoryRule(match_type='contains', pattern='NETFLIX',
                            user_category='Streaming', normalized_merchant='')
        txn = make_txn(merchant='NETFLIX.COM')
        result = apply_rules(txn, [rule])
        self.assertEqual(result['user_category'], 'Streaming')
        self.assertEqual(result['merchant'], 'NETFLIX.COM')

    # ── Immutability of original ───────────────────────────────────────────────

    def test_original_transaction_not_mutated(self):
        """apply_rules must return a copy — the original dict must be unchanged."""
        txn = make_txn(merchant='STARBUCKS #1832', user_category=None)
        original_merchant = txn['merchant']
        original_category = txn['user_category']

        rules = [make_rule()]
        apply_rules(txn, rules)  # discard result

        self.assertEqual(txn['merchant'],      original_merchant)
        self.assertEqual(txn['user_category'], original_category)

    # ── plaid_category preservation ────────────────────────────────────────────

    def test_plaid_category_never_modified(self):
        """
        plaid_category must NEVER be changed by apply_rules under any circumstance.
        This is a core data integrity requirement.
        """
        txn = make_txn(merchant='STARBUCKS', plaid_category='FOOD_AND_DRINK')
        rules = [make_rule(user_category='Coffee')]
        result = apply_rules(txn, rules)
        self.assertEqual(result['plaid_category'], 'FOOD_AND_DRINK',
                         "plaid_category must never be overwritten")
        self.assertEqual(result['user_category'], 'Coffee')

    # ── Edge cases ─────────────────────────────────────────────────────────────

    def test_empty_rules_list_returns_transaction_unchanged(self):
        """With no rules, the transaction should be returned as-is."""
        txn = make_txn(merchant='WALMART')
        result = apply_rules(txn, [])
        self.assertEqual(result['merchant'], 'WALMART')
        self.assertIsNone(result['user_category'])

    def test_empty_merchant_and_description(self):
        """Rules should not crash when both merchant and description are empty."""
        txn = make_txn(merchant='', description='')
        rules = [make_rule()]
        result = apply_rules(txn, rules)  # must not raise
        self.assertIsNone(result['user_category'])

    def test_none_merchant_and_description(self):
        """Rules should not crash when merchant or description is None."""
        txn = make_txn(merchant=None, description=None)
        rules = [make_rule()]
        result = apply_rules(txn, rules)  # must not raise
        self.assertIsNone(result['user_category'])


# ─── categorize_transactions Tests ────────────────────────────────────────────

class TestCategorizeTransactions(unittest.TestCase):
    """Tests for the batch categorize_transactions() function."""

    def test_returns_correct_counts(self):
        """Categorized and uncategorized counts must add up to total transactions."""
        rules = [make_rule(match_type='contains', pattern='STARBUCKS')]
        transactions = [
            make_txn(transaction_id='t1', merchant='STARBUCKS #100',       plaid_category=''),
            make_txn(transaction_id='t2', merchant='RANDOM MERCHANT',       plaid_category=''),
            make_txn(transaction_id='t3', merchant='STARBUCKS DRIVE THRU',  plaid_category=''),
        ]
        results, cat_count, uncat_count = categorize_transactions(transactions, rules=rules)
        self.assertEqual(len(results),  3)
        self.assertEqual(cat_count,     2)
        self.assertEqual(uncat_count,   1)

    def test_plaid_category_counts_as_categorized(self):
        """A transaction with only a plaid_category (no user override) is still categorized."""
        rules = []
        transactions = [
            make_txn(transaction_id='t1', plaid_category='FOOD_AND_DRINK'),
            make_txn(transaction_id='t2', plaid_category=''),
        ]
        _, cat_count, uncat_count = categorize_transactions(transactions, rules=rules)
        self.assertEqual(cat_count,   1)
        self.assertEqual(uncat_count, 1)

    def test_empty_transaction_list(self):
        """An empty input list should return empty output with zero counts."""
        results, cat_count, uncat_count = categorize_transactions([], rules=[])
        self.assertEqual(results,     [])
        self.assertEqual(cat_count,   0)
        self.assertEqual(uncat_count, 0)

    def test_all_transactions_returned(self):
        """Every input transaction must appear in the output, matched or not."""
        rules = [make_rule()]
        transactions = [make_txn(transaction_id=f't{i}') for i in range(10)]
        results, _, _ = categorize_transactions(transactions, rules=rules)
        self.assertEqual(len(results), 10)

    def test_transaction_ids_preserved(self):
        """Transaction IDs must not be altered during batch categorization."""
        rules = [make_rule()]
        transactions = [make_txn(transaction_id='abc123', merchant='STARBUCKS')]
        results, _, _ = categorize_transactions(transactions, rules=rules)
        self.assertEqual(results[0]['transaction_id'], 'abc123')


# ─── resolve_category Tests ────────────────────────────────────────────────────

class TestResolveCategory(unittest.TestCase):
    """Tests for the resolve_category() priority function."""

    def test_user_category_takes_priority(self):
        """user_category should win over Plaid primary and detailed categories."""
        txn = make_txn(
            user_category='Coffee',
            plaid_category_primary='FOOD_AND_DRINK',
            plaid_category='FOOD_AND_DRINK_COFFEE',
        )
        self.assertEqual(resolve_category(txn), 'Coffee')

    def test_plaid_primary_category_used_when_no_user_override(self):
        """plaid_category_primary should be preferred over the detailed plaid category."""
        txn = make_txn(
            user_category=None,
            plaid_category_primary='FOOD_AND_DRINK',
            plaid_category='FOOD_AND_DRINK_COFFEE',
        )
        self.assertEqual(resolve_category(txn), 'FOOD_AND_DRINK')

    def test_falls_back_to_detailed_plaid_category_when_primary_is_missing(self):
        """The detailed plaid category remains the fallback when no primary category exists."""
        txn = make_txn(user_category=None, plaid_category_primary='', plaid_category='TRAVEL')
        self.assertEqual(resolve_category(txn), 'TRAVEL')

    def test_empty_string_user_category_falls_back_to_plaid_primary(self):
        """An empty string user_category should be treated as absent."""
        txn = make_txn(user_category='', plaid_category_primary='TRAVEL', plaid_category='TRAVEL_TAXI')
        self.assertEqual(resolve_category(txn), 'TRAVEL')

    def test_formatting_plaid_food_category_to_restaurants_and_bars(self):
        """Food-and-drink Plaid values should be reported as Restaurants & Bars."""
        txn = make_txn(
            user_category=None,
            plaid_category_primary='FOOD_AND_DRINK',
            plaid_category='FOOD_AND_DRINK_GROCERIES',
        )
        self.assertEqual(resolve_category(txn), 'Restaurants & Bars')

    def test_formatting_personal_care_to_general_merchandise(self):
        """Personal care should be normalized to a cleaner merchandise label."""
        txn = make_txn(user_category=None, plaid_category_primary='PERSONAL_CARE', plaid_category='')
        self.assertEqual(resolve_category(txn), 'General Merchandise')

    def test_returns_empty_string_when_neither_category_present(self):
        """With no category at all, resolve_category must return empty string."""
        txn = make_txn(user_category=None, plaid_category_primary='', plaid_category='')
        self.assertEqual(resolve_category(txn), '')

    def test_returns_empty_string_when_both_none(self):
        """Both fields None should return empty string, not None or an error."""
        txn = make_txn(user_category=None, plaid_category_primary=None, plaid_category=None)
        result = resolve_category(txn)
        self.assertIsInstance(result, str)
        self.assertEqual(result, '')


# ─── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    unittest.main(verbosity=2)
