# Finance Sync

Personal finance aggregation and analytics platform.

Automatically collects transactions from financial institutions, normalizes
and categorizes them, stores them in a canonical SQLite database, and exports
them to a CSV file compatible with a custom Excel analytics workbook.

---

## Current Status

**Proof of concept — mock data only. No live Plaid connection yet.**

The full pipeline runs against `data/mock_transactions.json`. The architecture
is designed so that swapping in live Plaid data requires changes only to
`sync.py` and `plaid_client.py` — nothing downstream changes.

---

## Project Structure

```
finance_sync/
├── main.py               # Pipeline orchestrator — run this
├── config.py             # All paths, flags, and credentials (single source of truth)
├── sync.py               # Data ingestion (mock now, Plaid later)
├── normalization.py      # Merchant pre-processing engine
├── categorizer.py        # Category rules engine
├── database.py           # SQLite persistence layer
├── export.py             # CSV export module
├── plaid_client.py       # Plaid API stub (implement when ready)
│
├── data/
│   ├── mock_transactions.json   # Sample transactions for development
│   ├── cash_flow.csv            # Excel-compatible export (generated)
│   ├── raw_transactions.csv     # Full canonical export for debugging (generated)
│   └── finance.db               # SQLite database (generated)
│
├── rules/
│   └── category_rules.csv       # Category and merchant rules (edit in Excel)
│
├── logs/
│   └── sync.log                 # Execution log (generated)
│
├── tests/
│   ├── test_sync.py
│   ├── test_normalization.py
│   ├── test_categorizer.py
│   ├── test_export.py
│   ├── test_database.py
│   └── test_integration.py
│
├── requirements.txt
├── setup_windows.bat     # One-time environment setup
├── run_tests.bat         # Run full test suite
├── run_sync.bat          # Run pipeline (use with Task Scheduler)
└── .gitignore
```

---

## Prerequisites

- Python 3.10 or higher
- Windows 10/11 (batch files) or any OS with Python in PATH

Verify your Python version:
```
python --version
```

---

## Setup

Run once after cloning or downloading the project:

```
setup_windows.bat
```

This creates a virtual environment and installs dependencies (currently none
beyond stdlib, but the venv ensures future Plaid packages are isolated).

---

## Running the Pipeline

```
run_sync.bat
```

Or directly:
```
python main.py
```

**What it does:**
1. Loads transactions from `sync.py` (mock JSON now, Plaid later)
2. Pre-normalizes merchant names (`STARBUCKS #1832` → `STARBUCKS`)
3. Applies category rules from `rules/category_rules.csv`
4. Persists to `data/finance.db` via SQLite upsert
5. Exports `data/cash_flow.csv` (for Excel) and `data/raw_transactions.csv`
6. Logs a summary to `logs/sync.log` and stdout

## Local Dashboard Security

The dashboard binds to `127.0.0.1` by default and requires a local password.
Initialize or rotate the password from the project folder:

```powershell
python -m src.local_security_setup
```

The password is entered without echo, stored as a scrypt hash in the ignored
`.env` file, and is never printed. The setup command also creates the Flask
session signing key. Restart the app after setup. Start the dashboard without
triggering a Plaid sync at launch:

```powershell
python -m src.dashboard --no-sync
```

Open `http://127.0.0.1:5000`. Sessions expire after 12 hours; use **Lock** to
sign out. Keep `DASHBOARD_HOST` at its default for local use. Do not set it to
`0.0.0.0` or forward the port on your router for local use. A startup guard
requires password auth, a stable secret key, and secure cookies before allowing
a non-loopback bind, but that is not a replacement for Cloudflare Access,
Cloudflare Tunnel, and firewall controls. Leave `FINANCE_SYNC_COOKIE_SECURE`
unset for local HTTP. Set it to `true` only when the app is served entirely
over HTTPS.

The SQLite database is backed up with SQLite's online backup API after writes
(throttled to one automatic copy per five minutes) and again after successful
full syncs. Backups default to `%USERPROFILE%\Documents\FinanceSync DB Backup`
and expire after 30 days. `DATABASE_BACKUP_DIR` and
`DATABASE_BACKUP_RETENTION_DAYS` can override those settings. Backups contain
the same sensitive financial data as the live database; keep that folder
private and protect the drive with Windows device encryption. Backup failures
are logged but do not undo successful finance updates.

---

## Running the Tests

```
run_tests.bat
```

Or directly:
```
python -m unittest discover -s tests -p "test_*.py" -v
```

All tests use Python's built-in `unittest` — no additional packages needed.
Expected: all tests pass with `OK`.

---

## Adding Category Rules

Open `rules/category_rules.csv` in Excel. Each row is one rule:

| match_type | pattern          | user_category | normalized_merchant |
|------------|------------------|---------------|---------------------|
| contains   | STARBUCKS        | Coffee        | STARBUCKS           |
| contains   | AMAZON           | Shopping      | AMAZON              |
| exact      | WF PAYROLL       | Income        | WF Payroll          |

**match_type**
- `contains` — pattern appears anywhere in the merchant or description (case-insensitive)
- `exact` — pattern must exactly match the merchant or description

**pattern**
- The string to match against. Case-insensitive.

**user_category**
- The category to assign. Leave blank to match without changing the category.

**normalized_merchant**
- The clean merchant name to write. Leave blank to keep the pre-normalized name.

**Rule priority:** First matching rule wins. Put more specific rules (exact matches,
specific merchants) before broader ones (contains matches).

**Merchant normalization runs first.** Before rules are applied, raw merchant strings
are automatically cleaned: `STARBUCKS #1832` becomes `STARBUCKS`, `LYFT *RIDE SUN 9PM`
becomes `LYFT`. Write patterns against clean names, not raw institution strings.

---

## Configuration

All settings are in `config.py`. Key flags:

| Flag              | Default | Description                                      |
|-------------------|---------|--------------------------------------------------|
| `ENABLE_DATABASE` | `True`  | Set `False` to skip SQLite writes during testing |
| `DRY_RUN`         | `False` | Set `True` to run without writing any files      |

### Plaid account labels and link routing

The Link Accounts page lets you select which configured Plaid profile owns a
new connection and shows the owning profile for each existing connection. To
identify profiles by their Plaid email accounts, set display-only labels in
`.env` (these values are not credentials):

```dotenv
PLAID_ACCOUNT_LABEL=primary-email@example.com
SECONDARY_PLAID_ACCOUNT_LABEL=secondary-email@example.com
```

The primary profile uses the `PLAID_` credential prefix; the secondary profile
uses `SECONDARY_PLAID_`. Plaid Link handles the institution login separately.

---

## Excel Workbook Integration

`cash_flow.csv` has exactly these columns in this order:

```
Date | Account | Description | Category | Amount
```

Import into your workbook using Data → Get Data → From Text/CSV.
- Date: ISO 8601 string (`2024-03-15`)
- Amount: raw number, negative for debits, positive for credits
- Do not rename or reorder columns — existing formulas depend on this layout

---

## Scheduling on Windows (Task Scheduler)

1. Open Task Scheduler → Create Basic Task
2. Name: `Finance Sync`
3. Trigger: Daily at your preferred time (e.g. 7:00 AM)
4. Action: Start a program
5. Program: full path to `run_sync.bat`
   Example: `C:\Users\YourName\finance_sync\run_sync.bat`
6. Finish → check "Open Properties" → set "Run whether user is logged on or not"

The log at `logs/sync.log` records every run with timestamps and counts.

---

## Development Roadmap

| Priority | Item                          | Status         |
|----------|-------------------------------|----------------|
| 1        | SQLite persistence            | ✅ Complete    |
| 2        | Merchant normalization engine | ✅ Complete    |
| 3        | Category override engine      | ✅ Complete    |
| 4        | CSV export module             | ✅ Complete    |
| 5        | Full test suite               | ✅ Complete    |
| 6        | Plaid integration             | 🔲 Next        |
| 7        | Incremental syncing           | 🔲 Planned     |
| 8        | Scheduled automation          | 🔲 Planned     |
| 9        | Duplicate detection review    | 🔲 Planned     |
| 10       | Reporting module              | 🔲 Future      |
| 11       | Local dashboard               | 🔲 Future      |


---

## Data Privacy

- `data/` and `logs/` are excluded from version control via `.gitignore`
- Never commit `.env` or any file containing Plaid credentials or access tokens
- `finance.db` contains your full transaction history — keep backups
