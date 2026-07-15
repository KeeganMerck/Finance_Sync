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
