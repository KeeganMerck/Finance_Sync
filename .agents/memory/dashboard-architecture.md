---
name: Dashboard architecture
description: Flask web dashboard for Finance Sync — ports, files, data flow, and conventions.
---

## Files
- `src/dashboard.py` — Flask app, all API routes, all SQL queries
- `src/templates/base.html` — layout, nav, Tailwind + Chart.js CDN
- `src/templates/index.html` — main dashboard (summary cards, mini spend table, charts)
- `src/templates/spend.html` — full category × month pivot table with month-picker filter
- `src/templates/projections.html` — projected annual spend/income, lookback selector
- `src/templates/networth.html` — account balances, allocation donut, NW trend line chart

## Port
- **Port 5000** (Replit webview requires this). Override locally with `DASHBOARD_PORT` env var.
- Workflow name: `Start application`, command: `python -m src.dashboard`

## Key conventions
- All DB access is read-only (`file:...?mode=ro` SQLite URI). Dashboard never writes.
- `_rows()` and `_scalar()` return empty/default silently if DB doesn't exist yet — no crash on first run.
- Amount sign convention (Plaid): positive = expense (money out), negative = income (money in).
- Net worth: assets (depository + investment) minus liabilities (credit + loan).
- Averages exclude the current (partial) month — only complete months count.
- `COALESCE(user_category, plaid_category_primary, plaid_category, 'Uncategorized')` is the category resolution order throughout.

## API routes
- `GET /api/summary` — 4 summary card values
- `GET /api/spend/monthly?start=YYYY-MM&end=YYYY-MM` — pivot table data (months × categories)
- `GET /api/networth/current` — latest balances per account + totals
- `GET /api/networth/history` — monthly net worth time series
- `GET /api/projections?months=12` — projected annual spend/income by category

**Why:** DATABASE_PATH comes from config.py which resolves to `src/core/data/finance.db` (config.py uses its own parent as PROJECT_ROOT, not the repo root). Always import DATABASE_PATH from config rather than constructing the path manually.
