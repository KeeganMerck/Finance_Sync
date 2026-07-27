"""
google_sheets.py
================
Entry point: run the full sync pipeline and push results to Google Sheets.

This is the command to use when you want to update your Google Sheets
spreadsheet with the latest transactions and account balances.  It runs
exactly the same pipeline as the dashboard command but exits when done
instead of starting a web server, and it includes the Sheets export.

Usage:
    python -m src.google_sheets

Requires GOOGLE_SHEETS_ENABLED=true (default) and valid Sheets credentials
configured in your environment / .env file.
"""

from .main import run_pipeline

if __name__ == "__main__":
    run_pipeline(enable_sheets=True)
