"""Keeps the database key in the macOS Keychain (or the OS keyring elsewhere)."""

import secrets

import keyring

SERVICE = "personal-finance-tracker"
KEY_NAME = "database-key"


def get_or_create_db_key() -> str:
    """Return the database key, creating one on first run.

    The key only ever lives in the Keychain, so a copy of the database file is useless on
    its own. Deleting the Keychain entry makes the database unreadable for good.
    """
    key = keyring.get_password(SERVICE, KEY_NAME)
    if key is None:
        key = secrets.token_hex(32)
        keyring.set_password(SERVICE, KEY_NAME, key)
    return key
