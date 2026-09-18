"""Generate a masked report of Plaid tokens stored in the database.

Outputs CSV to stdout with columns:
  id, profile_name, profile_prefix, institution_name, masked_token, environment, is_active

Safe to run locally; does not modify the DB.
"""

import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.modules.database import get_plaid_tokens


def mask_token(tok: str) -> str:
    if not tok:
        return "(none)"
    t = str(tok)
    return t[:10] + "..." if len(t) > 13 else t[:6] + "..."


def main():
    tokens = get_plaid_tokens(active_only=False)
    writer = csv.writer(sys.stdout)
    writer.writerow(
        [
            "id",
            "profile_name",
            "profile_prefix",
            "institution_name",
            "masked_token",
            "environment",
            "is_active",
        ]
    )
    for t in tokens:
        writer.writerow(
            [
                t.get("id"),
                t.get("profile_name"),
                t.get("profile_prefix"),
                t.get("institution_name"),
                mask_token(t.get("access_token")),
                t.get("environment"),
                t.get("is_active"),
            ]
        )


if __name__ == "__main__":
    main()
