"""Consistent, retained SQLite backups for the local finance database."""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from ..core.config import DATABASE_BACKUP_DIR, DATABASE_BACKUP_RETENTION_DAYS, DATABASE_PATH

logger = logging.getLogger(__name__)
_backup_lock = threading.Lock()
_last_backup_by_database: dict[Path, float] = {}
_MIN_BACKUP_INTERVAL_SECONDS = 300


def backup_database(
    db_path: Path = DATABASE_PATH,
    backup_dir: Path = DATABASE_BACKUP_DIR,
    *,
    force: bool = False,
) -> Path | None:
    """Create an atomic SQLite online backup and prune expired backups.

    Non-forced calls are limited to one backup per five minutes per database.
    Sync completion and explicit user edits can request a forced backup.
    Returns None when the source database does not exist or a backup is throttled.
    """
    source_path = Path(db_path).expanduser().resolve()
    destination_dir = Path(backup_dir).expanduser()
    if not source_path.is_file():
        return None

    now = time.time()
    with _backup_lock:
        last_backup = _last_backup_by_database.get(source_path, 0)
        if not force and now - last_backup < _MIN_BACKUP_INTERVAL_SECONDS:
            return None

        destination_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        final_path = destination_dir / f"finance-{timestamp}.db"
        temporary_path = destination_dir / f".{final_path.name}.tmp"
        source = None
        target = None
        try:
            source = sqlite3.connect(
                f"file:{source_path.as_posix()}?mode=ro", uri=True, timeout=30
            )
            target = sqlite3.connect(str(temporary_path), timeout=30)
            source.backup(target, pages=256, sleep=0.05)
            integrity = target.execute("PRAGMA integrity_check").fetchone()
            if not integrity or integrity[0] != "ok":
                raise sqlite3.DatabaseError(
                    f"Backup integrity check failed: {integrity[0] if integrity else 'no result'}"
                )
            target.close()
            target = None
            source.close()
            source = None
            os.replace(temporary_path, final_path)
            _last_backup_by_database[source_path] = now
            _prune_backups(destination_dir)
            logger.info("SQLite database backup created: %s", final_path)
            return final_path
        except Exception:
            logger.exception("Could not create SQLite database backup")
            temporary_path.unlink(missing_ok=True)
            raise
        finally:
            if target is not None:
                target.close()
            if source is not None:
                source.close()


def _prune_backups(backup_dir: Path) -> None:
    cutoff = datetime.now().timestamp() - timedelta(
        days=max(DATABASE_BACKUP_RETENTION_DAYS, 1)
    ).total_seconds()
    for path in backup_dir.glob("finance-*.db"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            logger.warning("Could not prune expired database backup: %s", path)