"""Shared full-sync runner for web-triggered and scheduled executions."""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .core.config import DATA_DIR

logger = logging.getLogger(__name__)
_LOCK_PATH = Path(DATA_DIR) / ".finance-sync.lock"

# Windows compatibility for file locking
if sys.platform == "win32":
    # Simple file-based lock for Windows
    class WindowsLock:
        def __init__(self, lock_path):
            self.lock_path = lock_path
            self.file = None

        def acquire(self):
            try:
                # Try to create the file exclusively
                self.file = open(self.lock_path, "x")
            except FileExistsError:
                raise BlockingIOError("Lock file already exists")
            except Exception as e:
                raise BlockingIOError(f"Windows lock error: {e}")

        def release(self):
            if self.file:
                self.file.close()
                self.file = None
            try:
                self.lock_path.unlink(missing_ok=True)
            except:
                pass

else:
    import fcntl


class SyncAlreadyRunning(RuntimeError):
    """Raised when another sync process currently owns the sync lock."""


@contextmanager
def _sync_lock() -> Iterator[None]:
    """Acquire a non-blocking process-wide lock shared with scheduled jobs."""
    _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)

    if sys.platform == "win32":
        # Windows locking
        lock = WindowsLock(_LOCK_PATH)
        try:
            lock.acquire()
            yield
        finally:
            lock.release()
    else:
        # Unix locking with fcntl
        fd = os.open(_LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise SyncAlreadyRunning("Another sync is already running.") from exc
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)


def run_full_sync() -> None:
    """Run transactions, balances, and investments without Google Sheets export."""
    from .main import run_pipeline

    with _sync_lock():
        logger.info("Starting full finance sync.")
        run_pipeline(
            enable_sheets=False,
            sync_transactions=True,
            sync_investments=True,
        )
        logger.info("Full finance sync completed.")


if __name__ == "__main__":
    run_full_sync()
