import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from google_sheets import build_sheet_rows, write_rows_to_sheet


class FakeWorksheet:
    def __init__(self):
        self.cleared = False
        self.range_name = None
        self.values = None

    def clear(self):
        self.cleared = True

    def update(self, range_name, values):
        self.range_name = range_name
        self.values = values


class TestGoogleSheetsExport(unittest.TestCase):
    def test_build_sheet_rows_includes_expected_headers(self):
        rows = build_sheet_rows([
            {
                'date': '2026-07-11',
                'account': 'Checking',
                'merchant': 'STARBUCKS',
                'description': 'STARBUCKS',
                'user_category': 'Coffee',
                'plaid_category_primary': 'FOOD_AND_DRINK',
                'plaid_category': 'FOOD_AND_DRINK_COFFEE',
                'amount': -4.50,
            }
        ])

        self.assertEqual(rows[0], ['Date', 'Account', 'Description', 'Category', 'Amount'])
        self.assertEqual(rows[1][0], '2026-07-11')
        self.assertEqual(rows[1][1], 'Checking')
        self.assertEqual(rows[1][2], 'STARBUCKS')
        self.assertEqual(rows[1][3], 'Coffee')
        self.assertEqual(rows[1][4], -4.50)

    def test_write_rows_to_sheet_clears_and_updates(self):
        worksheet = FakeWorksheet()
        rows = [
            ['Date', 'Account', 'Description', 'Category', 'Amount'],
            ['2026-07-11', 'Checking', 'STARBUCKS', 'Coffee', -4.50],
        ]

        write_rows_to_sheet(worksheet, rows)

        self.assertTrue(worksheet.cleared)
        self.assertEqual(worksheet.range_name, 'A1')
        self.assertEqual(worksheet.values, rows)


if __name__ == '__main__':
    unittest.main(verbosity=2)
