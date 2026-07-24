"""
categorizer.py
==============
Merchant normalization and category override engine.

Responsibilities:
    - Load category rules from category_rules.csv
    - Pre-normalize raw merchant strings via normalization.py (first pass)
    - Match rules against any canonical field (merchant, description,
      institution, plaid_category, plaid_category_primary)
    - Apply user-defined category overrides
    - Exclude noise transactions (credit card payments, passthroughs)
    - Preserve plaid_category — it is NEVER modified here

Rules CSV format (rules/category_rules.csv):
    match_type, match_field, pattern, user_category, normalized_merchant, exclude

    match_type    : "exact" or "contains"
    match_field   : field to match against — "any", "merchant", "description",
                    "institution", "plaid_category", "plaid_category_primary"
                    Defaults to "any" (merchant OR description) if column absent.
    pattern       : string to match (case-insensitive)
    user_category : category override written into user_category field
    normalized_merchant : final merchant name (optional)
    exclude       : "true" to flag transaction as excluded from cash_flow export

Exclude behavior:
    Transactions matching an exclude rule are flagged with excluded=True.
    They are NOT written to cash_flow.csv or the SQLite database.
    They ARE written to raw_transactions.csv for auditing.
    Primary use: credit card payment transactions that would double-count
    spending already captured at the point of purchase.

Pipeline order within categorize_transactions():
    1. normalization.py  -> mechanical cleanup  (strip #1832, *codes, digits)
    2. apply_rules()     -> field-aware matching, semantic overrides, exclusions

Design notes:
    - First matching rule wins. Rule order in the CSV controls priority.
    - Matching is case-insensitive on both pattern and target.
    - plaid_category is never modified anywhere in this module.
    - Backward compatible: old CSVs without match_field/exclude columns still load.
"""

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..core.config import RULES_CSV_PATH
from .normalization import normalize_transactions

logger = logging.getLogger(__name__)


# ─── Constants ────────────────────────────────────────────────────────────────

VALID_MATCH_TYPES = {'exact', 'contains'}

# Fields in the canonical transaction schema that rules can target.
# 'any' matches merchant OR description (backward-compatible default).
VALID_MATCH_FIELDS = {
    'any',
    'merchant',
    'description',
    'institution',
    'account',
    'plaid_category',
    'plaid_category_primary',
    'day_of_month',  # extracts day from date (YYYY-MM-DD), 2-digit zero-padded
    'amount',  # numeric amount for threshold matching (pattern like ">2000" or "<-100")
}

# Supported compound match fields use ' and ' between simple field names.
# Example: "day_of_month and merchant"
COMPOUND_MATCH_FIELD_SEPARATOR = ' and '


# ─── Data Model ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CategoryRule:
    """
    Immutable representation of a single row from category_rules.csv.

    Frozen dataclass so rules can be safely passed around without risk of
    accidental mutation between pipeline stages.
    """
    match_type:          str   # "exact" or "contains"
    match_field:         str = 'any'   # which field to match against (see VALID_MATCH_FIELDS)
    pattern:             str = ''      # uppercased at load time for fast comparisons
    user_category:       str = ''      # override to apply (may be empty string)
    normalized_merchant: str = ''      # final merchant name to apply (may be empty string)
    exclude:             bool = False # True = flag transaction as excluded from cash_flow


# ─── Rule Loading ─────────────────────────────────────────────────────────────

def load_rules(rules_path: Path = RULES_CSV_PATH) -> list[CategoryRule]:
    """
    Parse category_rules.csv into an ordered list of CategoryRule objects.

    Rules are returned in file order. First-match-wins logic means that
    rule ordering in the CSV directly controls priority.

    Backward compatibility:
        If 'match_field' column is absent, defaults to 'any'.
        If 'exclude' column is absent, defaults to False.
        Old CSVs with only (match_type, pattern, user_category, normalized_merchant)
        load correctly without modification.

    Args:
        rules_path: Path to category_rules.csv. Defaults to config value.

    Returns:
        List of CategoryRule objects. Empty list if file is missing.
    """
    if not rules_path.exists():
        logger.warning(
            f"Category rules file not found: {rules_path}. "
            "No categorization or normalization will be applied."
        )
        return []

    rules: list[CategoryRule] = []

    with open(rules_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for line_num, row in enumerate(reader, start=2):
            # csv.DictReader can return None values for missing columns. Treat
            # both None and empty strings as absent so comments/blank rows are skipped.
            raw_match_type  = (row.get('match_type') or '').strip()
            raw_match_field = (row.get('match_field') or 'any').strip() or 'any'
            raw_pattern     = (row.get('pattern') or '').strip()

            match_type  = raw_match_type.lower()
            match_field = raw_match_field.lower()
            pattern     = raw_pattern

            # Skip blank or malformed rows, including comment lines that may be
            # present in the CSV for documentation.
            if not match_type or not pattern or match_type.startswith('#') or pattern.startswith('#') or match_field.startswith('#'):
                logger.debug(f"Skipping empty/invalid rule at CSV row {line_num}")
                continue

            if match_type not in VALID_MATCH_TYPES:
                logger.warning(
                    f"Row {line_num}: unknown match_type '{match_type}' — "
                    f"expected one of {VALID_MATCH_TYPES}. Skipping."
                )
                continue
            
            if COMPOUND_MATCH_FIELD_SEPARATOR in match_field:
                parts = [part.strip().lower() for part in match_field.split(COMPOUND_MATCH_FIELD_SEPARATOR)]
                if not all(part in VALID_MATCH_FIELDS for part in parts):
                    logger.warning(
                        f"Row {line_num}: unknown compound match_field '{match_field}' — "
                        f"expected fields in {VALID_MATCH_FIELDS}. Invalid parts: {[p for p in parts if p not in VALID_MATCH_FIELDS]}. Defaulting to 'any'."
                    )
                    match_field = 'any'
            # If all parts are valid, keep the compound match_field (do NOT default to 'any')
            elif match_field not in VALID_MATCH_FIELDS:
                logger.warning(
                    f"Row {line_num}: unknown match_field '{match_field}' — "
                    f"expected one of {VALID_MATCH_FIELDS}. Defaulting to 'any'."
                )
                match_field = 'any'

            exclude_str = row.get('exclude', '').strip().lower()
            exclude     = exclude_str == 'true'

            rules.append(CategoryRule(
                match_type=match_type,
                match_field=match_field,
                pattern=pattern.upper(),   # uppercased once at load, not per comparison
                user_category=row.get('user_category', '').strip(),
                normalized_merchant=row.get('normalized_merchant', '').strip(),
                exclude=exclude,
            ))

    logger.info(f"Loaded {len(rules)} category rule(s) from: {rules_path}")
    return rules


# ─── Rule Matching ────────────────────────────────────────────────────────────

def _get_field_value(field_name: str, transaction: dict) -> str:
    """Return a normalized string value for a supported match field."""
    if field_name == 'day_of_month':
        date_str = (transaction.get('date') or '').strip()
        if len(date_str) >= 10:
            return date_str[8:10]
        return ''

    if field_name == 'amount':
        return str(transaction.get('amount', 0))

    field_map = {
        'any': (transaction.get('merchant') or '') + ' ' + (transaction.get('description') or '') + ' ' + (transaction.get('account') or ''),
        'merchant': transaction.get('merchant') or '',
        'description': transaction.get('description') or '',
        'institution': transaction.get('institution') or '',
        'account': transaction.get('account') or '',
        'plaid_category': transaction.get('plaid_category') or '',
        'plaid_category_primary': transaction.get('plaid_category_primary') or '',
    }
    return str(field_map.get(field_name, field_map['any'])).strip()


def _get_match_targets(rule: CategoryRule, transaction: dict) -> tuple[tuple[str, ...], ...]:
    """
    Return the field values for a rule, supporting either a single field or
    a compound expression like 'day_of_month AND merchant'.

    The matcher treats simple rules as one component and "any" as a component
    with merchant and description alternatives. Compound rules are evaluated as
    multiple components joined by AND semantics.
    
    For compound patterns (pattern contains '|'), each alternative corresponds to
    each field in the compound match_field.
    """
    if COMPOUND_MATCH_FIELD_SEPARATOR in rule.match_field:
        parts = [part.strip().lower() for part in rule.match_field.split(COMPOUND_MATCH_FIELD_SEPARATOR)]
        return tuple((_get_field_value(part, transaction).upper(),) for part in parts)

    if rule.match_field == 'any':
        merchant = (transaction.get('merchant') or '').strip().upper()
        description = (transaction.get('description') or '').strip().upper()
        return ((merchant, description),)

    return ((_get_field_value(rule.match_field, transaction).upper(),),)


def _pattern_matches(pattern: str, value: str, match_type: str) -> bool:
    """Match a pattern against a single field value, supporting pipe-delimited alternatives.
    
    For amount field, supports comparison operators: >, <, >=, <=, ==
    Example: ">2000" matches amounts greater than 2000
    
    For compound patterns with pipe-delimited field:value pairs, handles each part separately.
    Example: "Publix|<-2000" splits into "Publix" and "<-2000"
    """
    if not pattern:
        return False

    alternatives = [segment.strip().upper() for segment in pattern.split('|') if segment.strip()]
    if not alternatives:
        return False

    # Check if this is an amount comparison (starts with comparison operator)
    if pattern.startswith(('>', '<', '=', '!')):
        try:
            amount = float(value)
            # Handle each alternative
            for alt in alternatives:
                if alt.startswith('>='):
                    threshold = float(alt[2:])
                    if amount >= threshold:
                        return True
                elif alt.startswith('<='):
                    threshold = float(alt[2:])
                    if amount <= threshold:
                        return True
                elif alt.startswith('>'):
                    threshold = float(alt[1:])
                    if amount > threshold:
                        return True
                elif alt.startswith('<'):
                    threshold = float(alt[1:])
                    if amount < threshold:
                        return True
                elif alt.startswith('=='):
                    threshold = float(alt[2:])
                    if amount == threshold:
                        return True
                elif alt.startswith('!='):
                    threshold = float(alt[2:])
                    if amount != threshold:
                        return True
            return False
        except (ValueError, IndexError):
            return False

    if match_type == 'exact':
        return any(value.upper() == alt for alt in alternatives)

    if match_type == 'contains':
        return any(alt in value.upper() for alt in alternatives)

    return False


def _rule_matches(rule: CategoryRule, transaction: dict) -> bool:
    """
    Return True if this rule matches the transaction.

    Dispatches to the correct field(s) based on rule.match_field, then
    applies match_type logic (exact or contains).

    Matching is case-insensitive — patterns are pre-uppercased at load
    time and targets are uppercased here per comparison.

    For compound match fields (e.g., "account AND merchant"):
    - If pattern contains "|", each field matches against the corresponding pattern part
      (e.g., "GO GREEN CHECKING|Publix" means account matches "GO GREEN CHECKING" AND merchant matches "Publix")
    - If pattern doesn't contain "|", all fields must match against the same pattern
    
    Args:
        rule:        The CategoryRule to evaluate.
        transaction: Canonical transaction dict (merchant already pre-normalized).

    Returns:
        True if the rule fires on this transaction.
    """
    components = _get_match_targets(rule, transaction)
    pattern = rule.pattern  # already uppercased
    
    # Split pattern by | for compound matching
    pattern_alternatives = [p.strip() for p in pattern.split('|') if p.strip()]

    if rule.match_type == 'exact':
        # If compound field with multiple pattern alternatives, match each field to each pattern part
        if COMPOUND_MATCH_FIELD_SEPARATOR in rule.match_field and len(pattern_alternatives) > 1:
            if len(pattern_alternatives) == len(components):
                # Each field matches its corresponding pattern part
                return all(
                    _pattern_matches(pattern_alternatives[i], component[0], 'exact')
                    for i, component in enumerate(components)
                )
            else:
                # All fields must match all pattern alternatives (AND logic)
                return all(
                    any(_pattern_matches(p, value, 'exact') for value in component)
                    for component in components
                    for p in pattern_alternatives
                )
        return all(any(_pattern_matches(p, value, 'exact') for value in component) for component in components for p in pattern_alternatives)

    if rule.match_type == 'contains':
        # If compound field with multiple pattern alternatives, match each field to each pattern part
        if COMPOUND_MATCH_FIELD_SEPARATOR in rule.match_field and len(pattern_alternatives) > 1:
            if len(pattern_alternatives) == len(components):
                # Each field matches its corresponding pattern part
                return all(
                    _pattern_matches(pattern_alternatives[i], component[0], 'contains')
                    for i, component in enumerate(components)
                )
            else:
                # All fields must match all pattern alternatives (AND logic)
                return all(
                    any(_pattern_matches(p, value, 'contains') for value in component)
                    for component in components
                    for p in pattern_alternatives
                )
        return all(any(_pattern_matches(p, value, 'contains') for value in component) for component in components for p in pattern_alternatives)

    logger.warning(f"Unhandled match_type '{rule.match_type}' — skipping.")
    return False


# ─── Rule Application ─────────────────────────────────────────────────────────

def apply_rules(transaction: dict, rules: list[CategoryRule]) -> dict:
    """
    Apply the first matching rule to a single transaction.

    Returns a shallow copy — the original dict is never mutated.

    If a matching rule has exclude=True:
        - Sets result['excluded'] = True
        - Stops processing (no category or merchant changes made)

    If a matching rule has exclude=False:
        - Applies normalized_merchant (if non-empty)
        - Applies user_category (if non-empty)
        - plaid_category is LEFT UNTOUCHED regardless

    First-match-wins: once a rule fires, all remaining rules are skipped.
    Rule ordering in the CSV is the user's control over priority.

    Args:
        transaction: Canonical transaction dict (merchant already pre-normalized).
        rules:       Ordered list of CategoryRule objects from load_rules().

    Returns:
        Updated transaction dict (shallow copy of input).
    """
    result = transaction.copy()
    
    # Initialize excluded flag if not present
    if 'excluded' not in result:
        result['excluded'] = False

    for rule in rules:
        if not _rule_matches(rule, result):
            continue

        if rule.exclude:
            result['excluded'] = True
            logger.debug(
                f"[{result.get('transaction_id')}] "
                f"EXCLUDED — merchant: '{result.get('merchant')}' "
                f"matched rule: {rule.match_field}='{rule.pattern}'"
            )
        else:
            if rule.normalized_merchant:
                original = result.get('merchant', '')
                result['merchant'] = rule.normalized_merchant
                logger.debug(
                    f"[{result.get('transaction_id')}] "
                    f"Merchant: '{original}' -> '{rule.normalized_merchant}'"
                )
            if rule.user_category:
                result['user_category'] = rule.user_category
                logger.debug(
                    f"[{result.get('transaction_id')}] "
                    f"Category: '{rule.user_category}'"
                )

        break  # First match wins — do not fall through to remaining rules

    return result


# ─── Batch Categorization ─────────────────────────────────────────────────────

def categorize_transactions(
    transactions: list[dict],
    rules: Optional[list[CategoryRule]] = None,
    pre_normalize: bool = True,
    return_excluded_count: bool = False,
) -> tuple[list[dict], int, int] | tuple[list[dict], int, int, int]:
    """
    Run the full categorization pipeline over a list of transactions.

    Pipeline stages:
        1. Pre-normalize merchant strings (normalization.py)
           Only runs when pre_normalize=True (default).
        2. Apply category rules to each transaction (apply_rules)
           Handles exclusions, merchant normalization, and category assignment.
        3. Count categorized / uncategorized / excluded for logging.

    The returned transaction list includes ALL transactions — including those
    flagged excluded=True. Callers (main.py) are responsible for splitting
    active vs excluded for DB persistence and export routing.

    Args:
        transactions:  List of canonical transaction dicts.
        rules:         Pre-loaded rules. Loaded from disk if None.
        pre_normalize: Run normalization pre-pass before rule matching.
                       Set False in unit tests that test rules in isolation.

    Returns:
        By default, returns a 3-tuple for backward compatibility:
            - list[dict] : All transactions (active + excluded, with excluded flag)
            - int        : Count with a resolved category (active only)
            - int        : Count with no category (active only)

        If return_excluded_count=True, returns a 4-tuple with an extra:
            - int        : Count of excluded transactions
    """
    if rules is None:
        rules = load_rules()

    # Stage 1: pre-normalize merchant strings.
    # description is intentionally NOT normalized — raw source data is preserved.
    if pre_normalize:
        transactions = normalize_transactions(transactions)
        logger.debug(f"Pre-normalization applied to {len(transactions)} transaction(s).")

    # Stage 2: apply rules and count outcomes
    result_transactions: list[dict] = []
    categorized_count   = 0
    uncategorized_count = 0
    excluded_count      = 0

    for txn in transactions:
        enriched = apply_rules(txn, rules)

        if enriched.get('excluded'):
            excluded_count += 1
        elif resolve_category(enriched):
            categorized_count += 1
        else:
            uncategorized_count += 1
            logger.debug(
                f"No category for txn {enriched.get('transaction_id')} "
                f"/ merchant '{enriched.get('merchant')}'"
            )

        result_transactions.append(enriched)

    logger.info(
        f"Categorization complete — "
        f"active: {categorized_count + uncategorized_count}, "
        f"categorized: {categorized_count}, "
        f"uncategorized: {uncategorized_count}, "
        f"excluded: {excluded_count}"
    )

    if return_excluded_count:
        return result_transactions, categorized_count, uncategorized_count, excluded_count

    return result_transactions, categorized_count, uncategorized_count


# ─── Category Resolution ──────────────────────────────────────────────────────

CATEGORY_LABELS = {
    'FOOD_AND_DRINK': 'Restaurants & Bars',
    'FOOD_AND_DRINK_GROCERIES': 'Groceries',
    'FOOD_AND_DRINK_FAST_FOOD': 'Restaurants & Bars',
    'GENERAL_MERCHANDISE': 'General Merchandise',
    'PERSONAL_CARE': 'General Merchandise',
    'GENERAL_SERVICES': 'Shopping',
    'SHOPPING': 'Shopping',
    'TRANSPORTATION': 'Transportation',
    'TRANSFER_IN': 'Transfers',
    'TRANSFER_OUT': 'Transfers',
    'INCOME': 'Income',
    'INCOME_PAYROLL': 'Income',
    'OTHER': 'Other',
    'ENTERTAINMENT': 'Entertainment',
    'TRAVEL': 'Travel',
    'HOME_IMPROVEMENT': 'Home',
    'HOUSING': 'Home',
    'MEDICAL': 'Health',
    'RENT_AND_UTILITIES_RENT': 'Rent',
    'RENT_AND_UTILITIES_GAS_AND_ELECTRICITY': 'Utilities',
    'RENT_AND_UTILITIES_WATER_AND_SEWAGE': 'Utilities',
    'RENT_AND_UTILITIES_TELEPHONE': 'Utilities',
    'RENT_AND_UTILITIES_INTERNET_AND_CABLE': 'Utilities',
    'UTILITIES': 'Utilities',
    'LOAN_PAYMENTS_CREDIT_CARD_PAYMENT': 'Excluded',
    'LOAN_PAYMENTS': 'Payments',
}


def format_category_for_display(label: str | None) -> str:
    """Return a human-friendly category label for reporting and exports."""
    if not label:
        return ''

    value = str(label).strip()
    if not value:
        return ''

    if value in CATEGORY_LABELS:
        return CATEGORY_LABELS[value]

    upper_value = value.upper()
    if upper_value in CATEGORY_LABELS:
        return CATEGORY_LABELS[upper_value]

    # Preserve unknown raw Plaid-style categories exactly as-is instead of
    # title-casing them, while still mapping well-known business categories.
    return value


def resolve_category(transaction: dict) -> str:
    """
    Return the final display category for a transaction.

    Resolution priority:
        1. user_category             — explicit user override (highest priority)
        2. plaid_category_primary    — broader Plaid grouping (e.g. FOOD_AND_DRINK)
        3. plaid_category            — detailed Plaid category fallback
        4. Empty string              — no category available

    Pure function with no side effects. Called from both categorizer.py
    and export.py without risk of mutation.

    Args:
        transaction: Canonical transaction dict.

    Returns:
        Resolved category string, or empty string if no category is set.
    """
    for field_name in ('user_category', 'plaid_category_primary', 'plaid_category'):
        value = transaction.get(field_name)
        if isinstance(value, str):
            value = value.strip()
            if value:
                if field_name == 'user_category':
                    return value

                upper_value = value.upper()
                if upper_value == 'FOOD_AND_DRINK':
                    if field_name == 'plaid_category_primary':
                        detail_value = str(transaction.get('plaid_category') or '').upper()
                        if detail_value.endswith('GROCERIES') or detail_value.endswith('FAST_FOOD'):
                            return 'Restaurants & Bars'
                    if field_name == 'plaid_category':
                        return 'Restaurants & Bars'
                if upper_value == 'PERSONAL_CARE':
                    return 'General Merchandise'

                return value
        elif value:
            return str(value)

    return ''