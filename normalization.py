"""
normalization.py
================
Merchant name pre-processing engine.

Runs BEFORE category rule matching in categorizer.py. Its job is to
mechanically strip noise from raw institution-provided merchant strings
so that category_rules.csv can use clean, stable patterns instead of
having to account for every store-number variant.

Responsibility split:
    normalization.py   -> mechanical cleanup   (strip #1832, *codes, LLC, etc.)
    category_rules.csv -> semantic remapping   (WHOLEFDS -> WHOLE FOODS)

Example pipeline for a single merchant:
    Raw:        "STARBUCKS #1832"
    Normalized: "STARBUCKS"           <- normalization.py strips #1832
    Final:      "STARBUCKS"           <- rule: contains,STARBUCKS (no further change)

    Raw:        "AMZN MKTP US*AB1234CD5"
    Normalized: "AMZN MKTP US"        <- normalization.py strips *AB1234CD5
    Final:      "AMAZON"              <- rule: contains,AMZN -> normalized_merchant=AMAZON

    Raw:        "LYFT *RIDE SUN 9PM 123456"
    Normalized: "LYFT"                <- normalization.py splits on * and drops suffix
    Final:      "LYFT"                <- rule: contains,LYFT (no further change)

Normalization is intentionally conservative:
    - Does NOT attempt semantic remapping (that is category_rules.csv's job).
    - Does NOT merge merchants that share a prefix.
    - When in doubt, leaves the string alone rather than guessing wrong.
    - If all content is stripped, returns the original to avoid data loss.

All functions are pure (no I/O, no side effects) and independently testable.
"""

import re
import logging

logger = logging.getLogger(__name__)


# ─── Compiled Regex Patterns ──────────────────────────────────────────────────
# Compiled once at module import time for efficiency across large batches.

# Hash-prefixed store/location numbers: #1832, #001, # 99
_RE_HASH_NUMBER = re.compile(r'\s*#\s*\d+')

# Asterisk-delimited processor codes appended to merchant names:
#   "LYFT *RIDE SUN 9PM" -> split on *, keep "LYFT"
#   "AMZN MKTP US*AB1234CD5" -> keep "AMZN MKTP US"
# Legitimate merchant names virtually never contain an asterisk.
_RE_ASTERISK_SUFFIX = re.compile(r'\s*\*.*$')

# Trailing standalone digit sequences of 4+ digits (store/terminal IDs):
#   "STARBUCKS 55123" -> "STARBUCKS"
#   "TARGET 0934"     -> "TARGET"
# Word boundary ensures we don't clip names like "7-ELEVEN".
# The {4,} threshold avoids stripping meaningful short numbers.
_RE_TRAILING_DIGITS = re.compile(r'\s+\d{4,}\s*$')

# Business entity suffixes at end of merchant name.
# Only matches when preceded by whitespace to avoid clipping names like "INCOME".
# Handles optional trailing period (INC. vs INC).
_RE_BUSINESS_SUFFIX = re.compile(
    r'\s+\b(LLC|INC|CORP|LTD|CO|PLC|LP|LLP|NA|FSB)\b\.?\s*$',
    re.IGNORECASE,
)

# Trailing punctuation artifacts left after earlier stripping steps.
_RE_TRAILING_PUNCT = re.compile(r'[\s.,\-/]+$')

# Internal whitespace runs (multiple spaces, tabs) to collapse.
_RE_WHITESPACE = re.compile(r'\s+')


# ─── Individual Normalization Steps ───────────────────────────────────────────
# Each step is a separate named function so they can be unit tested and
# reordered independently without touching normalize_merchant().

def strip_asterisk_codes(merchant: str) -> str:
    """
    Remove payment-processor codes appended after an asterisk.

    Examples:
        "LYFT *RIDE SUN 9PM 123456" -> "LYFT"
        "AMZN MKTP US*AB1234CD5"   -> "AMZN MKTP US"
        "STARBUCKS #1832"           -> "STARBUCKS #1832"  (no asterisk, unchanged)
    """
    return _RE_ASTERISK_SUFFIX.sub('', merchant)


def strip_hash_numbers(merchant: str) -> str:
    """
    Remove hash-prefixed store or location numbers.

    Examples:
        "STARBUCKS #1832"    -> "STARBUCKS"
        "HARRIS TEETER #312" -> "HARRIS TEETER"
        "TARGET # 0042"      -> "TARGET"
    """
    return _RE_HASH_NUMBER.sub('', merchant)


def strip_trailing_digits(merchant: str) -> str:
    """
    Remove trailing standalone digit sequences of 4 or more digits.

    These are typically store IDs or terminal numbers appended without a
    hash prefix. The 4-digit minimum avoids stripping meaningful short
    numbers that are part of a brand name.

    Examples:
        "STARBUCKS 55123"   -> "STARBUCKS"
        "WHOLEFDS 10293"    -> "WHOLEFDS"
        "7-ELEVEN"          -> "7-ELEVEN"   (short number, part of name, unchanged)
    """
    return _RE_TRAILING_DIGITS.sub('', merchant)


def strip_business_suffixes(merchant: str) -> str:
    """
    Remove trailing legal entity suffixes.

    Examples:
        "SOME COMPANY LLC"  -> "SOME COMPANY"
        "WIDGETS INC."      -> "WIDGETS"
        "GLOBAL CORP"       -> "GLOBAL"
        "INCOME"            -> "INCOME"     (no preceding space before CO, unchanged)
    """
    return _RE_BUSINESS_SUFFIX.sub('', merchant)


def strip_trailing_punctuation(merchant: str) -> str:
    """
    Strip trailing dots, commas, dashes, and slashes left after other steps.

    Examples:
        "WALMART,"      -> "WALMART"
        "NETFLIX.COM"   -> "NETFLIX.COM"   (internal dot, not trailing, unchanged)
        "AMAZON/"       -> "AMAZON"
    """
    return _RE_TRAILING_PUNCT.sub('', merchant)


def normalize_whitespace(merchant: str) -> str:
    """
    Collapse internal whitespace runs and strip leading/trailing whitespace.

    Always called last to clean up any gaps left by earlier stripping steps.

    Examples:
        "STARBUCKS   "       -> "STARBUCKS"
        "  AMAZON  PRIME  "  -> "AMAZON PRIME"
    """
    return _RE_WHITESPACE.sub(' ', merchant).strip()


# ─── Primary Public Interface ──────────────────────────────────────────────────

def normalize_merchant(raw: str) -> str:
    """
    Apply the full normalization pipeline to a single raw merchant string.

    Pipeline order is intentional:
        1. Strip asterisk codes first — avoids interference with later steps
        2. Strip hash-prefixed store numbers
        3. Strip trailing standalone digit sequences (4+ digits)
        4. Strip trailing business entity suffixes (LLC, INC, etc.)
        5. Strip trailing punctuation artifacts
        6. Normalize internal whitespace (always runs last)

    Safety fallback:
        If the pipeline produces an empty string, the original (stripped)
        value is returned. An imperfect name is always better than no name.

    Args:
        raw: Raw merchant string from a financial institution.

    Returns:
        Cleaned merchant string, or the original if normalization produces
        an empty result.
    """
    if not raw or not raw.strip():
        return raw or ''

    result = raw
    result = strip_asterisk_codes(result)
    result = strip_hash_numbers(result)
    result = strip_trailing_digits(result)
    result = strip_business_suffixes(result)
    result = strip_trailing_punctuation(result)
    result = normalize_whitespace(result)

    # Safety fallback: never return an empty string in place of real data
    if not result:
        logger.debug(
            f"Normalization produced empty string for '{raw}' — "
            "returning original to prevent data loss."
        )
        return raw.strip()

    if result != raw.strip():
        logger.debug(f"Merchant normalized: '{raw.strip()}' -> '{result}'")

    return result


def normalize_transactions(transactions: list[dict]) -> list[dict]:
    """
    Apply normalize_merchant() to every transaction in a list.

    Produces a new list of shallow-copied dicts — originals are never mutated.
    Only the merchant field is touched. The raw description field is preserved
    exactly as received from the institution.

    Called by categorizer.categorize_transactions() as the first pipeline step,
    before rule matching runs.

    Args:
        transactions: List of canonical transaction dicts.

    Returns:
        New list of transaction dicts with normalized merchant fields.
    """
    result = []
    for txn in transactions:
        copy = txn.copy()
        raw_merchant = copy.get('merchant') or ''
        copy['merchant'] = normalize_merchant(raw_merchant)
        result.append(copy)
    return result
