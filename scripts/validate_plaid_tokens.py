"""scripts/validate_plaid_tokens.py
---------------------------------
Validate all configured Plaid access tokens by calling a lightweight
`accounts_get` for each token. Prints a summary and exits with non-zero
status if any token is invalid.

This script requires Plaid credentials and tokens to be available in the
environment (or DB) as the running dashboard uses them.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import logging

from src.api import plaid_integration
from src.core.config import get_plaid_profiles

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)-20s %(message)s"
)
logger = logging.getLogger("validate_plaid_tokens")


def mask(tok: str) -> str:
    if not tok:
        return "(none)"
    return tok[:10] + "..." if len(tok) > 13 else tok[:6] + "..."


def main():
    profiles = get_plaid_profiles()
    if not profiles:
        logger.error("No Plaid profiles configured (PLAID_CLIENT_ID etc).")
        return 2

    overall_ok = True
    for profile in profiles:
        logger.info(f"Checking profile: {profile.name} (env={profile.env})")
        tokens = plaid_integration.get_access_tokens_with_source(profile)
        if not tokens:
            logger.warning(f" No tokens found for profile {profile.name}")
            continue
        for inst, info in tokens.items():
            tok = info.get("access_token")
            source = info.get("source")
            try:
                logger.info(
                    f" Validating {profile.name}/{inst} (source={source} token={mask(tok)})"
                )
                # Lightweight call
                accounts = plaid_integration.get_accounts(tok, profile)
                logger.info(f"  OK: fetched {len(accounts)} account(s)")
            except Exception as e:
                overall_ok = False
                logger.error(
                    f"  INVALID: {profile.name}/{inst} (source={source} token={mask(tok)}) — {e}"
                )

    if not overall_ok:
        logger.error(
            "One or more tokens failed validation. Check logs and consider re-linking."
        )
        return 1

    logger.info("All tokens validated successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
