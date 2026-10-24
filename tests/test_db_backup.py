import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from src import dashboard
from src.modules import database
from src.modules.db_backup import backup_database


class TestDatabaseBackup(unittest.TestCase):
    def test_database_write_helpers_trigger_backup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "finance.db"
            with closing(sqlite3.connect(database_path)) as conn:
                conn.execute("CREATE TABLE backup_hook (value INTEGER)")
                conn.commit()
            with patch.object(database, "DATABASE_PATH", database_path), patch.object(
                database, "backup_database"
            ) as backup:
                with database._get_connection(database_path) as conn:
                    conn.execute("INSERT INTO backup_hook VALUES (1)")
                backup.assert_called_once_with(database_path)

            with patch.object(dashboard, "DATABASE_PATH", database_path), patch.object(
                dashboard, "backup_database"
            ) as backup:
                with dashboard._db(write=True) as conn:
                    conn.execute("INSERT INTO backup_hook VALUES (2)")
                    conn.commit()
                backup.assert_called_once_with(force=True)

    def test_backup_is_restorable_and_throttles_redundant_copies(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database_path = root / "finance.db"
            backup_dir = root / "backups"

            with closing(sqlite3.connect(database_path)) as conn:
                conn.execute("CREATE TABLE sample (value TEXT NOT NULL)")
                conn.execute("INSERT INTO sample VALUES (?)", ("before",))
                conn.commit()

            first_backup = backup_database(database_path, backup_dir, force=True)
            self.assertIsNotNone(first_backup)
            self.assertIsNone(backup_database(database_path, backup_dir))

            with closing(sqlite3.connect(database_path)) as conn:
                conn.execute("INSERT INTO sample VALUES (?)", ("after",))
                conn.commit()

            second_backup = backup_database(database_path, backup_dir, force=True)
            self.assertIsNotNone(second_backup)
            with closing(sqlite3.connect(second_backup)) as conn:
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                values = [row[0] for row in conn.execute("SELECT value FROM sample ORDER BY rowid")]
            self.assertEqual(values, ["before", "after"])

    def test_expired_backups_are_pruned(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database_path = root / "finance.db"
            backup_dir = root / "backups"
            backup_dir.mkdir()
            expired_backup = backup_dir / "finance-expired.db"
            expired_backup.write_bytes(b"old backup")
            old_time = time.time() - 40 * 24 * 60 * 60
            import os

            os.utime(expired_backup, (old_time, old_time))
            with closing(sqlite3.connect(database_path)) as conn:
                conn.execute("CREATE TABLE sample (value INTEGER)")
                conn.commit()

            backup_database(database_path, backup_dir, force=True)
            self.assertFalse(expired_backup.exists())
            self.assertEqual(len(list(backup_dir.glob("finance-*.db"))), 1)


if __name__ == "__main__":
    unittest.main()