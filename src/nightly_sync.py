"""Scheduled entry point for the nightly full finance sync."""

from .sync_job import SyncAlreadyRunning, run_full_sync


if __name__ == "__main__":
    try:
        run_full_sync()
    except SyncAlreadyRunning:
        # A manual sync is already updating the shared database. Skipping this
        # scheduled run is safer than allowing two Plaid writes to overlap.
        print("A sync is already running; skipping this scheduled run.")