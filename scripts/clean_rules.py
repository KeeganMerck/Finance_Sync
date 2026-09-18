"""scripts/clean_rules.py
--------------------------------
Safely clean and deduplicate src/core/rules/category_rules.csv.

This script makes a timestamped backup of the rules file, normalizes
whitespace for the rule columns, removes exact duplicate rule rows (keeps
first occurrence), and rewrites the CSV with the same ordering otherwise.

It is intentionally conservative to preserve rule ordering and semantic
behavior — only trivial normalization and duplicate removal is performed.
"""

import csv
import sys
from datetime import datetime
from pathlib import Path

# Ensure repo root is on sys.path so `from src.core.config` works when running this script
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.config import RULES_CSV_PATH


def load_records(path: Path):
    if not path.exists():
        print(f"Rules file not found: {path}")
        return []
    records = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            clean = {k: (row.get(k) or "").strip() for k in reader.fieldnames}
            is_rule = bool(clean.get("match_type")) and not clean.get(
                "match_type", ""
            ).lstrip().startswith("#")
            records.append({"is_rule": is_rule, "row": clean})
    return records


def write_records(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "match_type",
        "match_field",
        "pattern",
        "user_category",
        "normalized_merchant",
        "exclude",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rec in records:
            writer.writerow(rec["row"])


def main():
    path = RULES_CSV_PATH
    records = load_records(path)
    if not records:
        print("No records to process.")
        return

    # Backup original
    bak = path.with_suffix(
        path.suffix + f'.bak.{datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")}'
    )
    path.replace(bak)
    print(f"Backed up original rules to: {bak}")

    seen = set()
    out = []
    removed = 0
    for rec in records:
        if not rec["is_rule"]:
            # preserve comments/blank rows as blank rule rows
            out.append(rec)
            continue
        row = rec["row"]
        key = (
            row.get("match_type", "").strip().lower(),
            row.get("match_field", "").strip().lower(),
            " ".join(row.get("pattern", "").split()),
            row.get("user_category", "").strip(),
            row.get("normalized_merchant", "").strip(),
            row.get("exclude", "").strip().lower(),
        )
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        # normalize pattern whitespace
        row["pattern"] = " ".join(row.get("pattern", "").split())
        row["match_field"] = row.get("match_field", "").strip().lower()
        row["match_type"] = row.get("match_type", "").strip().lower()
        out.append({"is_rule": True, "row": row})

    write_records(path, out)
    print(f"Wrote cleaned rules to: {path} (removed {removed} duplicate rows)")


if __name__ == "__main__":
    main()
