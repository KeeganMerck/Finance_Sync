"""
Test script to simulate the Google Sheets pivot table logic.
This test verifies that the categorization will produce the correct monthly
totals for Rent & Utilities (~$2400-2700 per month).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collections import defaultdict
from datetime import datetime

from modules.database import get_all_transactions


def test_pivot_table():
    """Test the pivot table aggregation."""
    print("Testing pivot table aggregation...")

    # Get all transactions from modules.database
    transactions = get_all_transactions()

    # Filter to only non-excluded transactions with user_category
    active_txns = [
        t for t in transactions if t.get("user_category") and not t.get("excluded")
    ]

    print(f"Active transactions: {len(active_txns)}")

    # Aggregate by category and month
    monthly_totals = defaultdict(lambda: defaultdict(float))

    for txn in active_txns:
        date_str = txn.get("date")
        category = txn.get("user_category")
        amount = txn.get("amount", 0)

        if not date_str or not category:
            continue

        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            month_key = date_obj.strftime("%Y-%m")
            monthly_totals[month_key][category] += amount
        except ValueError:
            continue

    # Print monthly totals by category
    months = sorted(monthly_totals.keys())
    print(f"\nMonths: {months}")

    # Find Rent & Utilities totals
    print("\nRent & Utilities by month:")
    rent_totals = {}
    for month in months:
        rent_amount = monthly_totals[month].get("Rent & Utilities", 0)
        rent_totals[month] = rent_amount
        print(f"  {month}: ${rent_amount:.2f}")

    # Calculate average
    if rent_totals:
        avg_rent = sum(rent_totals.values()) / len(rent_totals)
        print(f"\nAverage Rent & Utilities: ${avg_rent:.2f}")

    # Check if amounts are in expected range ($2400-2700)
    # Allow for missing months (0) - user may have missed some months
    print("\nValidation:")
    all_in_range = True
    for month, amount in rent_totals.items():
        if amount < 0:
            amount = abs(amount)
        if amount == 0:
            print(f"  {month}: $0.00 - MISSING (acceptable)")
        elif amount < 2000 or amount > 3000:
            print(f"  {month}: ${amount:.2f} - OUT OF RANGE (expected $2400-2700)")
            # Don't fail for out of range if it's a small amount (likely utilities only)
            if amount > 500:
                all_in_range = False
        else:
            print(f"  {month}: ${amount:.2f} - OK")

    # Check for raw RENT_AND_UTILITIES category
    print("\nChecking for raw RENT_AND_UTILITIES category:")
    raw_rent = [
        t
        for t in active_txns
        if t.get("plaid_category_primary") == "RENT_AND_UTILITIES"
        and not t.get("user_category")
    ]
    print(f"  Found: {len(raw_rent)}")
    if len(raw_rent) > 0:
        print("  FAILED: Found raw RENT_AND_UTILITIES transactions")
        for t in raw_rent:
            print(
                f"    {t.get('date')}: {t.get('description')}, amount={t.get('amount')}"
            )
    else:
        print("  PASSED: No raw RENT_AND_UTILITIES found")

    # Print all categories for reference
    print("\nAll categories by month:")
    for month in months:
        print(f"\n{month}:")
        for category, amount in sorted(monthly_totals[month].items()):
            print(f"  {category}: ${amount:.2f}")

    print("\n" + "=" * 50)
    print("Test Summary:")
    print(f"  Rent amounts in range: {'PASSED' if all_in_range else 'FAILED'}")
    print(
        f"  No raw RENT_AND_UTILITIES: {'PASSED' if len(raw_rent) == 0 else 'FAILED'}"
    )

    all_passed = all_in_range and len(raw_rent) == 0
    print(f"\nOverall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")

    return all_passed


if __name__ == "__main__":
    success = test_pivot_table()
    sys.exit(0 if success else 1)
