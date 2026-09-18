"""Regression tests for the materialized net-worth history read model."""

import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import src.modules.database as db_module
from src.modules.database import (
    eastern_today,
    get_net_worth_history,
    get_net_worth_history_summary,
    get_net_worth_history_status,
    init_db,
    upsert_snapshots,
)


class TestNetWorthHistory(unittest.TestCase):
    def setUp(self):
        self.db_fd, db_path = tempfile.mkstemp(suffix=".db")
        self.db_path = Path(db_path)
        self.enabled = patch.object(db_module, "ENABLE_DATABASE", True)
        self.enabled.start()
        init_db(self.db_path)

    def tearDown(self):
        self.enabled.stop()
        os.close(self.db_fd)
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def insert_manual(self, snapshot_date, account_id, balance):
        with db_module._get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO manual_account_snapshots
                (snapshot_date, account_id, account_name, account_type,
                 current_balance, available_balance, currency)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (snapshot_date, account_id, account_id, "depository", balance, balance, "USD"),
            )

    def test_history_uses_manual_override_and_excludes_future_dates(self):
        current = date.fromisoformat(eastern_today())
        yesterday = (current - timedelta(days=1)).isoformat()
        tomorrow = (current + timedelta(days=1)).isoformat()

        upsert_snapshots(
            [
                {
                    "snapshot_date": yesterday,
                    "account_id": "checking",
                    "account_name": "Checking",
                    "account_type": "depository",
                    "current_balance": 100,
                    "available_balance": 100,
                    "currency": "USD",
                },
                {
                    "snapshot_date": eastern_today(),
                    "account_id": "checking",
                    "account_name": "Checking",
                    "account_type": "depository",
                    "current_balance": 150,
                    "available_balance": 150,
                    "currency": "USD",
                },
                {
                    "snapshot_date": eastern_today(),
                    "account_id": "manual_account",
                    "account_name": "Manual",
                    "account_type": "depository",
                    "current_balance": 10,
                    "available_balance": 10,
                    "currency": "USD",
                },
                {
                    "snapshot_date": tomorrow,
                    "account_id": "future_account",
                    "account_name": "Future",
                    "account_type": "depository",
                    "current_balance": 900,
                    "available_balance": 900,
                    "currency": "USD",
                },
            ],
            self.db_path,
        )
        self.insert_manual(eastern_today(), "manual_account", 50)
        db_module.recalculate_net_worth_history(db_path=self.db_path)

        history = get_net_worth_history(self.db_path)
        by_date = {row["snapshot_date"]: row["net_worth"] for row in history}

        self.assertEqual(by_date[yesterday], 100)
        self.assertEqual(by_date[eastern_today()], 200)
        self.assertNotIn(tomorrow, by_date)

        with db_module._get_connection(self.db_path) as conn:
            raw_count = conn.execute("SELECT COUNT(*) FROM account_snapshots").fetchone()[0]
        self.assertEqual(raw_count, 4)

    def test_status_detects_and_repair_fills_missing_history_dates(self):
        current = date.fromisoformat(eastern_today())
        yesterday = (current - timedelta(days=1)).isoformat()
        upsert_snapshots(
            [
                {
                    "snapshot_date": yesterday,
                    "account_id": "checking",
                    "account_name": "Checking",
                    "account_type": "depository",
                    "current_balance": 100,
                    "available_balance": 100,
                    "currency": "USD",
                },
                {
                    "snapshot_date": eastern_today(),
                    "account_id": "checking",
                    "account_name": "Checking",
                    "account_type": "depository",
                    "current_balance": 150,
                    "available_balance": 150,
                    "currency": "USD",
                },
            ],
            self.db_path,
        )

        with db_module._get_connection(self.db_path) as conn:
            conn.execute("DELETE FROM net_worth_history")

        status = get_net_worth_history_status(self.db_path)
        self.assertTrue(status["needs_recalculation"])
        self.assertEqual(status["source_dates"], 2)

        result = db_module.recalculate_net_worth_history(db_path=self.db_path)
        self.assertEqual(result["rows_written"], 2)
        self.assertFalse(get_net_worth_history_status(self.db_path)["needs_recalculation"])

    def test_summary_uses_weekly_minimum_without_duplicate_samples(self):
        current = date.fromisoformat(eastern_today())
        first = current - timedelta(days=1)
        upsert_snapshots(
            [
                {
                    "snapshot_date": first.isoformat(),
                    "account_id": "checking",
                    "account_name": "Checking",
                    "account_type": "depository",
                    "current_balance": 100,
                    "available_balance": 100,
                    "currency": "USD",
                },
                {
                    "snapshot_date": current.isoformat(),
                    "account_id": "checking",
                    "account_name": "Checking",
                    "account_type": "depository",
                    "current_balance": 200,
                    "available_balance": 200,
                    "currency": "USD",
                },
            ],
            self.db_path,
        )

        summary = get_net_worth_history_summary(12, self.db_path)
        observed = [row for row in summary if row["net_worth"] is not None]
        self.assertEqual(len(summary), 1)
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0]["net_worth"], 150)
        self.assertEqual(sum(row["sample_count"] for row in summary), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
