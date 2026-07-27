"""
connection_recovery.py
======================
Interactive terminal flow for recovering from Plaid connection errors
(ITEM_LOGIN_REQUIRED, INVALID_ACCESS_TOKEN, etc.) during the sync pipeline.

When sync.py catches a credential/login error for an institution, it calls
``prompt_reconnect()``.  The flow is:

  1. Print a clear error banner to the terminal.
  2. Ask "launch link_setup to fix now? [y/N]" — wait RECONNECT_PROMPT_TIMEOUT
     seconds (default 30).  Auto-skip on timeout.
  3. If yes: open link_setup in a new terminal window and print the URL.
  4. Wait for the user to press Enter (or type "skip") to confirm they're done.
  5. Send a /shutdown request to the link_setup server, then kill the process.
  6. Return True so sync.py can retry fetching the institution.
  7. Return False on timeout / no / any failure — caller skips the institution.

Launching a new terminal window is OS-specific:
  Windows : start cmd /k "python -m src.link_setup"
  macOS   : osascript  →  Terminal.app
  Linux   : tries gnome-terminal, xterm, konsole in order

If the terminal launcher fails, the user is told to open a second terminal
manually; the flow still waits for their Enter confirmation.
"""

import json
import logging
import os
import platform
import queue
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

# Seconds to wait for the initial yes/no prompt before auto-skipping
RECONNECT_PROMPT_TIMEOUT = 30

# Port the link_setup Flask server listens on
LINK_SETUP_PORT = 5000

# Plaid error codes that mean the user must re-enter credentials via Link
_LOGIN_ERROR_CODES = {
    "ITEM_LOGIN_REQUIRED",
    "INVALID_ACCESS_TOKEN",
    "INVALID_CREDENTIALS",
    "MFA_NOT_SUPPORTED",
    "ACCESS_NOT_GRANTED",
    "ITEM_LOCKED",
    "USER_SETUP_REQUIRED",
}

# HTTP 400 is the typical status for all Plaid item/credential errors
_LOGIN_ERROR_STATUS = 400


# ─── Error Detection ──────────────────────────────────────────────────────────

def is_login_error(exc: Exception) -> bool:
    """
    Return True if *exc* is a Plaid ApiException with an ``error_code`` that
    indicates a credential / login problem the user can fix by re-linking.

    Only the explicit codes in ``_LOGIN_ERROR_CODES`` qualify.  HTTP status
    alone is not used — Plaid returns 400 for many non-credential errors
    (e.g. INVALID_REQUEST, INVALID_FIELD) that are not fixable by re-linking.
    """
    body = getattr(exc, 'body', None)
    if not body:
        return False
    try:
        data = json.loads(body) if isinstance(body, (str, bytes)) else body
        return data.get('error_code', '') in _LOGIN_ERROR_CODES
    except Exception:
        return False


# ─── Timed stdin ──────────────────────────────────────────────────────────────

def _stdin_reader(result_queue: "queue.Queue[str]") -> None:
    """Daemon thread: read one line from stdin and put it in the queue."""
    try:
        line = sys.stdin.readline()
        result_queue.put(line.strip().lower() if line else '')
    except Exception:
        result_queue.put('')


def timed_input(prompt: str, timeout: int) -> Optional[str]:
    """
    Print *prompt* then wait up to *timeout* seconds for a line from stdin.

    Returns the stripped, lower-cased input string, or ``None`` if the timeout
    expired before the user pressed Enter.

    Works on Windows, macOS, and Linux by using a daemon thread so that a
    blocking ``readline()`` does not prevent the countdown from expiring.
    """
    print(prompt, end='', flush=True)
    q: "queue.Queue[str]" = queue.Queue()
    t = threading.Thread(target=_stdin_reader, args=(q,), daemon=True)
    t.start()
    try:
        return q.get(timeout=timeout)
    except queue.Empty:
        return None


# ─── link_setup Launcher ──────────────────────────────────────────────────────

def _project_root() -> Path:
    """Return the project root (two levels above this file: src/modules/ → root)."""
    return Path(__file__).resolve().parents[2]


def _launch_link_setup() -> Optional[subprocess.Popen]:
    """
    Open link_setup in a **new terminal window** and return the Popen handle.

    The handle is only useful for the macOS/Linux cases where it refers to the
    actual terminal process.  On Windows, ``start`` is a shell built-in and the
    returned handle is the cmd launcher, not the Python process — use the
    ``/shutdown`` endpoint to stop the server cleanly.

    Returns None if no supported launcher is found.
    """
    root = _project_root()
    python = sys.executable
    # Use -u for unbuffered output so the terminal shows logs immediately
    inner_cmd = f'"{python}" -u -m src.link_setup'
    system = platform.system()

    try:
        if system == 'Windows':
            # 'start' opens a new cmd window; /k keeps it open after the process ends
            full = f'start cmd /k "cd /d "{root}" && {inner_cmd}"'
            proc = subprocess.Popen(full, shell=True, cwd=str(root))
            return proc

        if system == 'Darwin':
            # AppleScript to open a new Terminal.app tab/window
            script = (
                f'tell application "Terminal" to do script '
                f'"cd \\"{root}\\" && {inner_cmd}"'
            )
            proc = subprocess.Popen(['osascript', '-e', script])
            return proc

        # Linux — try common terminal emulators in preference order
        candidates = [
            ['gnome-terminal', '--', 'bash', '-c',
             f'cd "{root}" && {inner_cmd}; echo "Press Enter to close..."; read'],
            ['xterm', '-e', f'bash -c \'cd "{root}" && {inner_cmd}; read\''],
            ['konsole', '--noclose', '-e', f'bash -c "cd \\"{root}\\" && {inner_cmd}"'],
            ['xfce4-terminal', '--hold', '-e',
             f'bash -c "cd \\"{root}\\" && {inner_cmd}"'],
        ]
        for argv in candidates:
            try:
                proc = subprocess.Popen(argv, cwd=str(root))
                return proc
            except FileNotFoundError:
                continue

        logger.warning("No supported terminal emulator found on this Linux system.")
        return None

    except Exception as exc:
        logger.warning(f"Could not launch link_setup terminal: {exc}")
        return None


# ─── link_setup Shutdown ──────────────────────────────────────────────────────

def _shutdown_link_setup(proc: Optional[subprocess.Popen]) -> None:
    """
    Stop the link_setup Flask server.

    Primary method: POST /shutdown to the server (cleanest — Flask handles it).
    Fallback: terminate the Popen handle if it refers to a real process.

    On Windows the Popen handle is just the ``start`` launcher (already exited),
    so the fallback is a no-op there; the /shutdown route handles it.
    """
    # 1. Ask the server to stop itself
    try:
        url = f"http://localhost:{LINK_SETUP_PORT}/shutdown"
        req = urllib.request.Request(url, data=b'', method='POST')
        urllib.request.urlopen(req, timeout=4)
        logger.debug("link_setup /shutdown request sent.")
    except Exception:
        pass  # Server may have already stopped, or was never reachable

    # 2. Small delay so the server can finish its response
    time.sleep(1)

    # 3. Terminate the process handle (works for macOS/Linux terminal procs)
    if proc is not None:
        try:
            proc.terminate()
        except Exception:
            pass


# ─── Main Interactive Flow ────────────────────────────────────────────────────

def prompt_reconnect(institution_name: str, profile_name: str) -> bool:
    """
    Interactive reconnect flow shown in the terminal when a Plaid login error
    occurs for *institution_name* / *profile_name*.

    Returns True  → caller should retry fetching this institution.
    Returns False → caller should skip this institution and continue.
    """
    sep = '─' * 64
    print(f"\n{sep}")
    print(f"  ⚠️  CONNECTION ERROR — {profile_name}/{institution_name}")
    print(f"  Plaid cannot access this account (credentials need updating).")
    print(f"{sep}")

    # ── Prompt: want to fix it now? ───────────────────────────────────────────
    answer = timed_input(
        f"\n  Launch link_setup to fix this now? [y/N] "
        f"(auto-skip in {RECONNECT_PROMPT_TIMEOUT}s): ",
        timeout=RECONNECT_PROMPT_TIMEOUT,
    )

    if answer is None:
        print(
            f"\n  No response in {RECONNECT_PROMPT_TIMEOUT}s — "
            f"skipping {institution_name} and continuing pipeline.\n"
        )
        return False

    if answer not in ('y', 'yes'):
        print(f"  Skipping {institution_name}.\n")
        return False

    # ── Launch link_setup ─────────────────────────────────────────────────────
    print(f"\n  Starting link_setup server...")
    proc = _launch_link_setup()

    if proc is None:
        # Launcher failed — tell the user to open it manually
        root = _project_root()
        print(
            f"\n  ⚠️  Could not open a new terminal automatically.\n"
            f"  Please open a second terminal window and run:\n\n"
            f"      cd \"{root}\"\n"
            f"      python -m src.link_setup\n"
        )
    else:
        # Give the server a moment to bind the port before printing the URL
        time.sleep(2)

    print(
        f"\n  {'─' * 56}\n"
        f"  Open your browser to:  http://localhost:{LINK_SETUP_PORT}\n"
        f"  Choose 'Update Existing' and reconnect {institution_name}.\n"
        f"  {'─' * 56}\n"
    )

    # ── Wait for user to confirm they're done ─────────────────────────────────
    confirmation = timed_input(
        "  Press Enter when the connection has been updated "
        "(or type 'skip' + Enter to skip): ",
        timeout=600,  # 10 minutes — no reasonable pipeline should wait longer
    )

    if confirmation in ('skip', 's', 'no', 'n', 'cancel'):
        print(f"  Skipping {institution_name} reconnect.\n")
        _shutdown_link_setup(proc)
        return False

    # confirmation is either '' (bare Enter) or None (10-min timeout)
    if confirmation is None:
        print(
            f"  Timed out waiting for confirmation — "
            f"skipping {institution_name}.\n"
        )
        _shutdown_link_setup(proc)
        return False

    # ── Shutdown and signal retry ─────────────────────────────────────────────
    print(f"  Shutting down link_setup server...")
    _shutdown_link_setup(proc)
    print(f"  Retrying {institution_name}...\n")
    return True
