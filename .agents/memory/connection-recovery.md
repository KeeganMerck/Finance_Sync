---
name: Connection recovery flow
description: How Plaid login errors are handled interactively during the sync pipeline.
---

## Module: `src/modules/connection_recovery.py`
- `is_login_error(exc)` — reads `error_code` from ApiException JSON body; matches against `_LOGIN_ERROR_CODES` set only. HTTP status 400 alone is NOT used (too broad — INVALID_REQUEST also returns 400).
- `prompt_reconnect(institution, profile)` — 30-second timed yes/no prompt; launches link_setup in new terminal window if yes; waits for Enter confirmation; POSTs to `/shutdown` to stop link_setup; returns True (retry) or False (skip).

## Integration in `sync.py`
- `for attempt in range(2)` loop per institution.
- Attempt 0 login error → `prompt_reconnect` → continue to attempt 1 if True, else break.
- Attempt 1 failure or non-login error → log exception + break (no second reconnect prompt).

## link_setup `/shutdown` route
- Added to `src/link_setup.py`. POSTs trigger `os._exit(0)` on a daemon thread after 0.5s delay so Flask can send the 200 response first.

**Why:** The status-400 fallback was removed after testing showed INVALID_REQUEST (a malformed API call) was incorrectly triggering the reconnect prompt.
