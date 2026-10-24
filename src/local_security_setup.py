"""Interactively initialize local dashboard credentials."""

from __future__ import annotations

import getpass
import os
import secrets
from pathlib import Path

from dotenv import set_key
from werkzeug.security import generate_password_hash


def _env_file_path() -> Path:
    configured_path = os.getenv("FINANCE_SYNC_ENV_FILE")
    if configured_path:
        return Path(configured_path).expanduser()

    project_root = Path(__file__).resolve().parent.parent
    candidates = [Path.cwd() / ".env", project_root / ".env"]
    return next((path for path in candidates if path.exists()), project_root / ".env")


def main() -> int:
    password = getpass.getpass("Choose a dashboard password (16+ characters): ")
    if len(password) < 16:
        print("Password must be at least 16 characters.")
        return 1

    confirmation = getpass.getpass("Re-enter dashboard password: ")
    if password != confirmation:
        print("Passwords did not match. No settings were changed.")
        return 1

    env_path = _env_file_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)
    if not env_path.exists():
        env_path.touch()

    set_key(
        str(env_path),
        "FINANCE_SYNC_PASSWORD_HASH",
        generate_password_hash(password, method="scrypt"),
    )
    set_key(
        str(env_path),
        "FINANCE_SYNC_SECRET_KEY",
        secrets.token_urlsafe(48),
    )
    print(f"Local dashboard credentials saved to {env_path}.")
    print("Restart the dashboard to apply them. The password itself was not saved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())