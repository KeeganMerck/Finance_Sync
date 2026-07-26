# Finance Sync

Personal finance aggregation and analytics platform. Pulls transactions from Plaid (or mock JSON), normalizes merchants, applies a CSV-driven category rules engine, persists to SQLite, exports to CSV, and pushes to Google Sheets.

**Current state:** Proof of concept with mock data included. Plaid and Google Sheets integrations are fully implemented — they activate via feature flags once credentials are in `.env`.

---

## Stack

- **Language:** Python 3.10+
- **Database:** SQLite (`data/finance.db`)
- **Plaid SDK:** `plaid-python >= 14.0.0`
- **Sheets:** `gspread` + `google-auth` (service account)
- **Flask:** Standalone Plaid Link OAuth setup utility (`src/link_setup.py`)
- **Tests:** stdlib `unittest` + `pytest`

---

## Architecture & Data Flow

```
Plaid API  ──┐
             ├──► sync.py (fetch) ──► categorizer.py ──► database.py (SQLite)
mock JSON ───┘         │                    │                     │
                       │             normalization.py             │
                       │             category_rules.csv           │
                       │                                          ▼
                       └──────────────────────────────► export.py (CSV)
                                                                  │
                                                                  ▼
                                                        google_sheets.py
                                                        balance.py
```

1. **Ingestion** — `sync.py` fetches from Plaid or `data/mock_transactions.json`
2. **Normalization** — `normalization.py` strips asterisks, hash codes, trailing digits from merchant strings
3. **Categorization** — `categorizer.py` applies `rules/category_rules.csv` (first-match-wins)
4. **Persistence** — `database.py` upserts to SQLite (idempotent via `INSERT OR REPLACE`)
5. **Export** — `export.py` writes `cash_flow.csv` (active only) and `raw_transactions.csv` (all)
6. **Sheets** — `google_sheets.py` rewrites "Cash Flow Table"; `balance.py` writes "Account Balances" and "Net Worth History"

---

## Source Layout

```
src/
├── main.py               # Pipeline orchestrator — run_pipeline()
├── __main__.py           # Entry point: python -m src
├── link_setup.py         # Flask app for one-time Plaid Link token setup
├── core/
│   └── config.py         # All flags, paths, credentials (single source of truth)
├── modules/
│   ├── sync.py           # Ingestion (Plaid or mock)
│   ├── categorizer.py    # Rule engine + apply_rules()
│   ├── normalization.py  # normalize_merchant()
│   ├── database.py       # upsert_transactions(), upsert_snapshots()
│   ├── export.py         # run_exports() → CSV files
│   ├── google_sheets.py  # update_google_sheet()
│   └── balance.py        # Balance snapshots → Sheets
└── api/
    └── plaid_integration.py  # Plaid client wrapper + schema normalization
```

---

## Feature Flags (config.py)

| Flag | Effect |
|---|---|
| `USE_PLAID` | `True` = live Plaid API; `False` = mock JSON |
| `DRY_RUN` | Logs everything, writes nothing to disk/DB/Sheets |
| `ENABLE_DATABASE` | Toggle SQLite persistence |
| `SYNC_MODE` | `"full"` = full lookback window; `"incremental"` = since latest DB entry |
| `GOOGLE_SHEETS_ENABLED` | Toggle Sheets export |
| `PLAID_FORCE_REFRESH` | Call `/transactions/refresh` before fetching |

---

## Database Schema

**`transactions`**
- `transaction_id` (PK), `date`, `account`, `merchant`, `description`
- `plaid_category`, `plaid_category_primary`, `user_category`
- `amount`, `pending`, `institution`, `last_updated`, `excluded`

**`account_snapshots`**
- PK: `(snapshot_date, account_id)`
- `account_name`, `institution`, `account_type`, `account_subtype`
- `current_balance`, `available_balance`, `credit_limit`, `currency`

---

## Rules System (`rules/category_rules.csv`)

| Column | Purpose |
|---|---|
| `match_type` | `merchant`, `account and merchant`, etc. |
| `match_field` | Field to match against |
| `pattern` | String, pipe-separated alternatives, or `>2000` numeric threshold |
| `user_category` | Category to assign |
| `normalized_merchant` | Merchant display name override |
| `exclude` | `TRUE` = keep in raw CSV but exclude from cash_flow.csv and Sheets |

Rules apply in CSV order — **first match wins**. Edit in Excel; do not reorder without intent.

---

## Flask Link Setup (`src/link_setup.py`)

Standalone utility for one-time Plaid OAuth. Run separately when adding a new institution.

| Endpoint | Purpose |
|---|---|
| `/` | Serves Plaid Link HTML UI |
| `/link_token` | Creates a link token |
| `/exchange` | Swaps public token → access token (writes to `.env`) |
| `/update_link_token` | Generates update-mode token (extend history, add products) |
| `/update_all_link_tokens` | Bulk update for all configured institutions |

---

## Running

```bash
# Run the full pipeline (mock data, no credentials needed)
python -m src

# Run the Plaid Link setup Flask app
python -m src.link_setup

# Run tests
pytest tests/
```

---

## Environment (`.env`)

```
PLAID_CLIENT_ID=...
PLAID_SECRET=...
PLAID_ENV=sandbox          # or development / production
PLAID_ACCESS_TOKEN_<INSTITUTION>=...
GOOGLE_SHEETS_ID=...
GOOGLE_SHEETS_CREDENTIALS_PATH=path/to/creds.json
```

The `.env` file and `data/` directory are gitignored — never commit them.

---

## User Preferences

- User runs this locally with a real `.env` and Google service-account JSON — Replit is used for development and feature additions only.
- Do not restructure or migrate the existing module layout without asking.
- Keep mock-data compatibility intact; all features should degrade gracefully when `USE_PLAID=False`.
