"""
config.py
=========
Single source of truth for all project-wide settings and paths.

Every path, flag, and credential lives here. No other module should
define its own constants or hard-code file locations.

To add a new setting:
  1. Add it here with a clear name and comment.
  2. Import it in the relevant module.
  3. Never scatter constants across business logic files.
"""

from pathlib import Path
import os
import dotenv

# Load environment variables from .env file (for Plaid credentials)
dotenv.load_dotenv()

# ─── Project Root ──────────────────────────────────────────────────────────────

# Resolves to the directory containing this file, regardless of where the
# script is invoked from. All other paths are derived from here.
PROJECT_ROOT = Path(__file__).parent.resolve()

# ─── Directory Paths ───────────────────────────────────────────────────────────

DATA_DIR  = PROJECT_ROOT / 'data'
RULES_DIR = PROJECT_ROOT / 'rules'
LOGS_DIR  = PROJECT_ROOT / 'logs'

# Create directories on import so modules never need to mkdir themselves
# (except for safety calls in individual write operations)
DATA_DIR.mkdir(exist_ok=True)
RULES_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# ─── File Paths ────────────────────────────────────────────────────────────────

# SQLite database
DATABASE_PATH = DATA_DIR / 'finance.db'

# Primary Excel-compatible export (Date, Account, Description, Category, Amount)
CASH_FLOW_CSV_PATH = DATA_DIR / 'cash_flow.csv'

# Full canonical archival export (all fields, for debugging)
RAW_CSV_PATH = DATA_DIR / 'raw_transactions.csv'

# Mock transaction source (used in place of Plaid during development)
MOCK_JSON_PATH = DATA_DIR / 'mock_transactions.json'

# Category and merchant normalization rules (user-editable in Excel)
RULES_CSV_PATH = RULES_DIR / 'category_rules.csv'

# Sync log file
LOG_PATH = LOGS_DIR / 'sync.log'

# Google Sheets export settings
GOOGLE_SHEETS_CREDENTIALS_PATH = PROJECT_ROOT / 'google_credentials.json'
GOOGLE_SHEETS_SPREADSHEET_NAME = 'PLAID - K&D Cash Flow'
GOOGLE_SHEETS_WORKSHEET_NAME = 'Cash Flow Table'
GOOGLE_SHEETS_ENABLED: bool = os.getenv('GOOGLE_SHEETS_ENABLED', 'true').lower() == 'true'

# ─── Feature Flags ─────────────────────────────────────────────────────────────

# Set to False to run sync + categorization without writing to SQLite.
# Useful when iterating on categorization rules without touching the database.
ENABLE_DATABASE: bool = True

# Set to True to run the full pipeline without writing any files to disk.
# Logs show what would have been written. Useful for CI / testing.
DRY_RUN: bool = False
# Set to True to use Plaid API for real transactions, False for mock JSON.
# When True, requires Plaid credentials (PLAID_CLIENT_ID, PLAID_SECRET, PLAID_ENV)
# and at least one PLAID_{ENV}_TOKEN_* environment variable (obtained via link_setup.py).
USE_PLAID: bool = os.getenv('USE_PLAID', 'false').lower() == 'true'

# Ask Plaid to refresh transaction data before each fetch attempt.
# Helpful when institutions have recently updated or when older history is not yet available.
PLAID_FORCE_REFRESH: bool = os.getenv('PLAID_FORCE_REFRESH', 'true').lower() == 'true'

# Sync mode:
#   - "full" -> fetch transactions from the last FULL_SYNC_LOOKBACK_DAYS days
#   - "incremental" -> fetch from the latest DB date minus INCREMENTAL_SYNC_BUFFER_DAYS
SYNC_MODE: str = os.getenv('SYNC_MODE', 'full').strip().lower()
FULL_SYNC_LOOKBACK_DAYS: int = int(os.getenv('FULL_SYNC_LOOKBACK_DAYS', '730'))  # 2 years
INCREMENTAL_SYNC_BUFFER_DAYS: int = int(os.getenv('INCREMENTAL_SYNC_BUFFER_DAYS', '14'))

# ─── Plaid Credentials  ────────────────────────────────────────────────

PLAID_ENV: str       = os.getenv('PLAID_ENV')       # 'sandbox' | 'development' | 'production'
PLAID_CLIENT_ID: str = os.getenv('PLAID_CLIENT_ID')

if PLAID_ENV == 'sandbox':
    PLAID_SECRET: str = os.getenv('PLAID_SANDBOX_SECRET')
elif PLAID_ENV == 'development':
    PLAID_SECRET: str = os.getenv('PLAID_DEVELOPMENT_SECRET')
elif PLAID_ENV == 'production':
    PLAID_SECRET: str = os.getenv('PLAID_PRODUCTION_SECRET')
else:
    PLAID_SECRET: str = os.getenv('PLAID_SECRET')  # fallback for legacy .env files
