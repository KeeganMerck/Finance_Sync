"""Background sync state for the dashboard's ad-hoc sync button."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from threading import Lock, Thread
from typing import Any

from .sync_job import SyncAlreadyRunning, run_full_sync

logger = logging.getLogger(__name__)
_state_lock = Lock()
_state: dict[str, Any] = {
    "state": "idle",
    "started_at": None,
    "finished_at": None,
    "error": None,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_sync_status() -> dict[str, Any]:
    with _state_lock:
        return dict(_state)


def _set_state(**changes: Any) -> None:
    with _state_lock:
        _state.update(changes)


def _run_in_background() -> None:
    try:
        run_full_sync()
    except SyncAlreadyRunning as exc:
        _set_state(
            state="busy",
            finished_at=_now(),
            error=str(exc),
        )
        logger.info("%s", exc)
    except BaseException as exc:
        # run_pipeline uses SystemExit for fatal pipeline stages, so this must
        # catch BaseException to expose that failure to the dashboard.
        logger.exception("Ad-hoc full sync failed.")
        _set_state(
            state="failed",
            finished_at=_now(),
            error=str(exc) or exc.__class__.__name__,
        )
    else:
        _set_state(
            state="completed",
            finished_at=_now(),
            error=None,
        )


def start_background_sync() -> tuple[bool, dict[str, Any]]:
    """Start one background sync, returning (started, current_status)."""
    with _state_lock:
        if _state["state"] == "running":
            return False, dict(_state)
        _state.update(
            {
                "state": "running",
                "started_at": _now(),
                "finished_at": None,
                "error": None,
            }
        )

    Thread(
        target=_run_in_background,
        name="finance-full-sync",
        daemon=True,
    ).start()
    return True, get_sync_status()