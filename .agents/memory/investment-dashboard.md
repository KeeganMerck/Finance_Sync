---
name: Investment dashboard
description: Investment-specific data sources and presentation conventions for the Finance Sync dashboard.
---

The investment view uses four related SQLite sources:

- `account_snapshots` filtered to `account_type = 'investment'` for account balances.
- `investment_holdings` for the current portfolio, deduplicated to the newest row per `holding_id`.
- `investment_holdings_history` for dated portfolio value, cost basis, and gain/loss history.
- `investment_transactions` for buys, sells, dividends, transfers, and other investment activity.

The dashboard combines these through `/api/investments`; the `/investments` page presents three tabs: Current Holdings, Investment Activity, and Portfolio History. Holdings and activity tables support search/filter controls and clickable column sorting.

**Why:** The uploaded database contains investment-specific tables even though the original application code did not expose them, so investment reporting must query those tables directly rather than infer portfolio details from generic transactions.

**How to apply:** Preserve the sign conventions in stored investment transactions and treat current holdings as the source for present portfolio value; use holdings history for trend reporting.