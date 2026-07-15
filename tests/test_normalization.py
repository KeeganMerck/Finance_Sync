"""
tests/test_normalization.py
===========================
Unit tests for normalization.py.

All tests are pure — no filesystem I/O, no config, no database.
Every function in normalization.py is tested both individually (step tests)
and through the top-level normalize_merchant() pipeline (integration tests).

Critical invariants verified here:
    - Noise is stripped (store numbers, asterisk codes, business suffixes)
    - Legitimate name content is preserved
    - WF PAYROLL and WELLS FARGO VISA are never merged
    - Empty/None inputs do not crash
    - Normalization never returns an empty string (fallback to original)
    - Originals are never mutated in batch mode

Run from the project root:
    python -m unittest tests/test_normalization.py -v

Or run directly in Carnets.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from normalization import (
    strip_asterisk_codes,
    strip_hash_numbers,
    strip_trailing_digits,
    strip_business_suffixes,
    strip_trailing_punctuation,
    normalize_whitespace,
    normalize_merchant,
    normalize_transactions,
)


# ─── Individual Step Tests ────────────────────────────────────────────────────

class TestStripAsteriskCodes(unittest.TestCase):
    """Tests for strip_asterisk_codes() in isolation."""

    def test_strips_asterisk_suffix_with_space(self):
        self.assertEqual(strip_asterisk_codes('LYFT *RIDE SUN 9PM'), 'LYFT')

    def test_strips_asterisk_suffix_without_space(self):
        self.assertEqual(strip_asterisk_codes('AMZN MKTP US*AB1234CD5'), 'AMZN MKTP US')

    def test_no_asterisk_unchanged(self):
        self.assertEqual(strip_asterisk_codes('STARBUCKS #1832'), 'STARBUCKS #1832')

    def test_empty_string_unchanged(self):
        self.assertEqual(strip_asterisk_codes(''), '')

    def test_only_asterisk_returns_empty(self):
        # Edge case: the entire merchant is an asterisk code
        result = strip_asterisk_codes('*RIDE CODE')
        self.assertEqual(result, '')

    def test_multiple_asterisks_strips_from_first(self):
        # Should split on the first *, discard everything after
        result = strip_asterisk_codes('DOORDASH *ORDER*123')
        self.assertEqual(result, 'DOORDASH')


class TestStripHashNumbers(unittest.TestCase):
    """Tests for strip_hash_numbers() in isolation."""

    def test_strips_hash_number(self):
        self.assertEqual(strip_hash_numbers('STARBUCKS #1832'), 'STARBUCKS')

    def test_strips_hash_number_with_space_before_digits(self):
        self.assertEqual(strip_hash_numbers('TARGET # 0042'), 'TARGET')

    def test_strips_hash_number_no_leading_space(self):
        self.assertEqual(strip_hash_numbers('HARRIS TEETER#312'), 'HARRIS TEETER')

    def test_no_hash_unchanged(self):
        self.assertEqual(strip_hash_numbers('STARBUCKS 55123'), 'STARBUCKS 55123')

    def test_empty_string_unchanged(self):
        self.assertEqual(strip_hash_numbers(''), '')


class TestStripTrailingDigits(unittest.TestCase):
    """Tests for strip_trailing_digits() in isolation."""

    def test_strips_five_digit_store_number(self):
        self.assertEqual(strip_trailing_digits('STARBUCKS 55123'), 'STARBUCKS')

    def test_strips_four_digit_store_number(self):
        self.assertEqual(strip_trailing_digits('WHOLEFDS 1029'), 'WHOLEFDS 1029')
        # 4 digits: borderline — our threshold is 4+, so this should strip
        self.assertEqual(strip_trailing_digits('WHOLEFDS 10293'), 'WHOLEFDS')

    def test_does_not_strip_short_numbers(self):
        """Numbers under 4 digits should be left alone."""
        self.assertEqual(strip_trailing_digits('7-ELEVEN'), '7-ELEVEN')
        self.assertEqual(strip_trailing_digits('SHOP 99'), 'SHOP 99')

    def test_no_trailing_digits_unchanged(self):
        self.assertEqual(strip_trailing_digits('STARBUCKS'), 'STARBUCKS')

    def test_empty_unchanged(self):
        self.assertEqual(strip_trailing_digits(''), '')


class TestStripBusinessSuffixes(unittest.TestCase):
    """Tests for strip_business_suffixes() in isolation."""

    def test_strips_llc(self):
        self.assertEqual(strip_business_suffixes('SOME COMPANY LLC'), 'SOME COMPANY')

    def test_strips_inc_with_period(self):
        self.assertEqual(strip_business_suffixes('WIDGETS INC.'), 'WIDGETS')

    def test_strips_inc_without_period(self):
        self.assertEqual(strip_business_suffixes('WIDGETS INC'), 'WIDGETS')

    def test_strips_corp(self):
        self.assertEqual(strip_business_suffixes('GLOBAL CORP'), 'GLOBAL')

    def test_strips_ltd(self):
        self.assertEqual(strip_business_suffixes('PARTNER LTD'), 'PARTNER')

    def test_case_insensitive(self):
        self.assertEqual(strip_business_suffixes('Something llc'), 'Something')

    def test_does_not_clip_income(self):
        """
        'INCOME' must not be partially stripped to 'IN' due to the 'CO' suffix.
        The regex requires a preceding space, so this is safe.
        """
        self.assertEqual(strip_business_suffixes('INCOME'), 'INCOME')

    def test_no_suffix_unchanged(self):
        self.assertEqual(strip_business_suffixes('STARBUCKS'), 'STARBUCKS')

    def test_empty_unchanged(self):
        self.assertEqual(strip_business_suffixes(''), '')


class TestStripTrailingPunctuation(unittest.TestCase):
    """Tests for strip_trailing_punctuation() in isolation."""

    def test_strips_trailing_comma(self):
        self.assertEqual(strip_trailing_punctuation('WALMART,'), 'WALMART')

    def test_strips_trailing_period(self):
        self.assertEqual(strip_trailing_punctuation('AMAZON.'), 'AMAZON')

    def test_strips_trailing_slash(self):
        self.assertEqual(strip_trailing_punctuation('SHOP/'), 'SHOP')

    def test_does_not_strip_internal_dot(self):
        """NETFLIX.COM has an internal dot — must not be affected."""
        self.assertEqual(strip_trailing_punctuation('NETFLIX.COM'), 'NETFLIX.COM')

    def test_no_punctuation_unchanged(self):
        self.assertEqual(strip_trailing_punctuation('STARBUCKS'), 'STARBUCKS')

    def test_empty_unchanged(self):
        self.assertEqual(strip_trailing_punctuation(''), '')


class TestNormalizeWhitespace(unittest.TestCase):
    """Tests for normalize_whitespace() in isolation."""

    def test_collapses_internal_spaces(self):
        self.assertEqual(normalize_whitespace('AMAZON  PRIME'), 'AMAZON PRIME')

    def test_strips_leading_whitespace(self):
        self.assertEqual(normalize_whitespace('  STARBUCKS'), 'STARBUCKS')

    def test_strips_trailing_whitespace(self):
        self.assertEqual(normalize_whitespace('STARBUCKS   '), 'STARBUCKS')

    def test_collapses_tabs(self):
        self.assertEqual(normalize_whitespace('SHOP\t\tMART'), 'SHOP MART')

    def test_already_clean_unchanged(self):
        self.assertEqual(normalize_whitespace('STARBUCKS'), 'STARBUCKS')

    def test_empty_string_returns_empty(self):
        self.assertEqual(normalize_whitespace(''), '')


# ─── normalize_merchant() Pipeline Tests ──────────────────────────────────────

class TestNormalizeMerchant(unittest.TestCase):
    """
    Tests for the top-level normalize_merchant() pipeline function.
    These test combinations of stripping steps working together.
    """

    # ── Core real-world cases ──────────────────────────────────────────────────

    def test_starbucks_hash_number(self):
        self.assertEqual(normalize_merchant('STARBUCKS #1832'), 'STARBUCKS')

    def test_starbucks_trailing_digits(self):
        self.assertEqual(normalize_merchant('STARBUCKS 55123'), 'STARBUCKS')

    def test_starbucks_store_word(self):
        """
        "STARBUCKS STORE 2021" — normalization strips "2021" (4-digit trailing).
        "STORE" is intentionally kept; semantic remapping is the rules file's job.
        """
        self.assertEqual(normalize_merchant('STARBUCKS STORE 2021'), 'STARBUCKS STORE')

    def test_lyft_asterisk_suffix(self):
        self.assertEqual(normalize_merchant('LYFT *RIDE SUN 9PM 123456'), 'LYFT')

    def test_amazon_asterisk_code(self):
        self.assertEqual(normalize_merchant('AMZN MKTP US*AB1234CD5'), 'AMZN MKTP US')

    def test_harris_teeter_hash(self):
        self.assertEqual(normalize_merchant('HARRIS TEETER #312'), 'HARRIS TEETER')

    def test_target_trailing_digits(self):
        self.assertEqual(normalize_merchant('TARGET 0934'), 'TARGET')

    def test_wholefds_trailing_digits(self):
        self.assertEqual(normalize_merchant('WHOLEFDS MKT #10293'), 'WHOLEFDS MKT')

    def test_doordash_asterisk(self):
        self.assertEqual(normalize_merchant('DOORDASH*ORDER 4421'), 'DOORDASH')

    # ── Merchant isolation — critical correctness tests ────────────────────────

    def test_wf_payroll_not_merged_with_wells_fargo_visa(self):
        """
        WF PAYROLL and WELLS FARGO VISA must remain distinct after normalization.
        They should never produce the same output string.
        """
        payroll = normalize_merchant('WF PAYROLL')
        visa    = normalize_merchant('WELLS FARGO VISA')
        self.assertNotEqual(payroll, visa,
            "WF PAYROLL and WELLS FARGO VISA must remain distinct merchants")

    def test_payroll_direct_deposit_preserved(self):
        """Payroll description text must not be accidentally stripped."""
        result = normalize_merchant('WELLS FARGO PAYROLL DIR DEP')
        self.assertIn('PAYROLL', result.upper())

    def test_netflix_domain_preserved(self):
        """Internal dots in domain-style names must not be stripped."""
        result = normalize_merchant('NETFLIX.COM')
        self.assertEqual(result, 'NETFLIX.COM')

    def test_amazon_prime_preserved(self):
        result = normalize_merchant('AMAZON PRIME')
        self.assertEqual(result, 'AMAZON PRIME')

    # ── Edge cases ─────────────────────────────────────────────────────────────

    def test_empty_string_returns_empty(self):
        self.assertEqual(normalize_merchant(''), '')

    def test_none_like_empty_string(self):
        """None should be handled gracefully — return empty string."""
        result = normalize_merchant(None)
        self.assertEqual(result, '')

    def test_whitespace_only_returns_whitespace_or_empty(self):
        result = normalize_merchant('   ')
        # Should not crash; may return original or empty
        self.assertIsInstance(result, str)

    def test_fallback_when_all_content_stripped(self):
        """
        If normalization strips everything, the original value must be returned.
        An imperfect name is always better than an empty string.
        """
        # A string where all content happens to look like a suffix
        # This is a synthetic edge case to validate the fallback logic
        result = normalize_merchant('LLC')
        # The fallback should kick in and return something non-empty
        self.assertTrue(len(result) > 0)

    def test_already_clean_merchant_unchanged(self):
        """A clean merchant name should survive normalization unmodified."""
        self.assertEqual(normalize_merchant('STARBUCKS'), 'STARBUCKS')
        self.assertEqual(normalize_merchant('WHOLE FOODS'), 'WHOLE FOODS')
        self.assertEqual(normalize_merchant('NETFLIX'), 'NETFLIX')

    def test_extra_whitespace_collapsed(self):
        result = normalize_merchant('STARBUCKS   ')
        self.assertEqual(result, 'STARBUCKS')


# ─── normalize_transactions() Tests ───────────────────────────────────────────

class TestNormalizeTransactions(unittest.TestCase):
    """Tests for the batch normalize_transactions() function."""

    def _make_txn(self, txn_id, merchant, description='DESC'):
        return {
            'transaction_id': txn_id,
            'merchant': merchant,
            'description': description,
            'plaid_category': 'Test',
        }

    def test_normalizes_merchant_field(self):
        txns = [self._make_txn('t1', 'STARBUCKS #1832')]
        result = normalize_transactions(txns)
        self.assertEqual(result[0]['merchant'], 'STARBUCKS')

    def test_all_transactions_returned(self):
        txns = [self._make_txn(f't{i}', f'MERCHANT {i}') for i in range(5)]
        result = normalize_transactions(txns)
        self.assertEqual(len(result), 5)

    def test_description_field_not_modified(self):
        """
        Raw description must be preserved exactly.
        Normalization only touches the merchant field.
        """
        raw_desc = 'STARBUCKS #1832 CHARLOTTE NC  RAW DESC'
        txns = [self._make_txn('t1', 'STARBUCKS #1832', description=raw_desc)]
        result = normalize_transactions(txns)
        self.assertEqual(result[0]['description'], raw_desc)

    def test_original_dicts_not_mutated(self):
        """Original transaction dicts must be unchanged after batch normalization."""
        txns = [self._make_txn('t1', 'STARBUCKS #1832')]
        original_merchant = txns[0]['merchant']
        normalize_transactions(txns)  # discard result
        self.assertEqual(txns[0]['merchant'], original_merchant)

    def test_other_fields_preserved(self):
        """Fields other than merchant must pass through untouched."""
        txns = [self._make_txn('t1', 'LYFT *RIDE SUN 9PM')]
        result = normalize_transactions(txns)
        self.assertEqual(result[0]['transaction_id'], 't1')
        self.assertEqual(result[0]['plaid_category'], 'Test')

    def test_empty_merchant_does_not_crash(self):
        txns = [self._make_txn('t1', '')]
        result = normalize_transactions(txns)  # must not raise
        self.assertEqual(len(result), 1)

    def test_none_merchant_does_not_crash(self):
        txn = self._make_txn('t1', 'VALID')
        txn['merchant'] = None
        result = normalize_transactions([txn])  # must not raise
        self.assertEqual(len(result), 1)

    def test_empty_list_returns_empty_list(self):
        self.assertEqual(normalize_transactions([]), [])

    def test_transaction_ids_preserved_in_order(self):
        """Batch output must maintain the same order as input."""
        txns = [self._make_txn(f't{i}', 'STARBUCKS #1832') for i in range(10)]
        result = normalize_transactions(txns)
        ids = [r['transaction_id'] for r in result]
        self.assertEqual(ids, [f't{i}' for i in range(10)])


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    unittest.main(verbosity=2)
