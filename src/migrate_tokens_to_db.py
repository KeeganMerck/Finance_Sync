"""
migrate_tokens_to_db.py
=======================
Utility to migrate existing Plaid tokens from .env file to database.

This script helps transition from environment-based token storage to
database-based storage for better web application support.

Usage:
    python migrate_tokens_to_db.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import logging

from src.modules.database import (
    DATABASE_PATH,
    ENABLE_DATABASE,
    migrate_env_tokens_to_db,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    if not ENABLE_DATABASE:
        logger.error("Database is disabled. Please enable it in config.")
        return 1

    env_file = Path.cwd() / ".env"
    if not env_file.exists():
        logger.error(f".env file not found at {env_file}")
        return 1
    else:
        logger.info(f".env file found at {env_file}")

    logger.info(f"Migrating Plaid tokens from {env_file} to {DATABASE_PATH}")
    logger.info(
        "This will NOT modify your .env file - tokens will be copied to the database."
    )

    result = migrate_env_tokens_to_db(env_file, DATABASE_PATH)

    if result["success"]:
        logger.info("Migration complete:")
        logger.info(f"  - Total tokens found: {result['total']}")
        logger.info(f"  - Successfully migrated: {result['migrated']}")
        logger.info(f"  - Failed: {result['failed']}")

        if result["migrated"] > 0:
            logger.info("\nNext steps:")
            logger.info("1. Start the dashboard: python -m src.dashboard")
            logger.info("2. Go to http://localhost:5000/link-accounts")
            logger.info(
                "3. Your institutions should appear in the linked institutions list"
            )
            logger.info(
                "4. (Optional) Remove PLAID_*TOKEN_* variables from .env file after confirming everything works"
            )

        return 0
    else:
        logger.error(f"Migration failed: {result.get('error', 'Unknown error')}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
