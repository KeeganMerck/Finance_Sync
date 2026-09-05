"""Shared full-sync runner for web-triggered and scheduled executions."""

from __future__ import annotations

import fcntl
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .core.config import DATA_DIR

logger = logging.getLogger(__name__)
_LOCK_PATH = Path(DATA_DIR) / ".finance-sync.lock"


class SyncAlreadyRunning(RuntimeError):
    """Raised when another sync process currently owns the sync lock."""


@contextmanager
def _sync_lock() -> Iterator[None]:
    """Acquire a non-blocking process-wide lock shared with scheduled jobs."""
    _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
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