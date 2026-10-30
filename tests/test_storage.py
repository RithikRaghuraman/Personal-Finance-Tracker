import secrets
import sqlite3
import stat
from dataclasses import replace
from datetime import date

import keyring
import pytest
from factories import txn
from keyring.backend import KeyringBackend

from finance_tracker import keystore
from finance_tracker.models import Month
from finance_tracker.storage import Repository, WrongKeyError, connect


def test_database_file_is_encrypted_and_private(tmp_path):
    path = tmp_path / "data" / "finance.db"
    connect(path, secrets.token_hex(32)).close()

    assert not path.read_bytes().startswith(b"SQLite format 3")
    with pytest.raises(sqlite3.DatabaseError):
        sqlite3.connect(path).execute("SELECT * FROM sqlite_master").fetchall()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_wrong_key_is_rejected(tmp_path):
    path = tmp_path / "finance.db"
    connect(path, secrets.token_hex(32)).close()
    with pytest.raises(WrongKeyError):
        connect(path, secrets.token_hex(32))


def test_key_must_be_hex():
    with pytest.raises(ValueError):
        connect(":memory:", "'; ATTACH DATABASE 'x' AS y; --" + "0" * 32)


def test_transactions_round_trip_and_update_in_place(repo: Repository):
    pending = txn(date(2026, 9, 3), -1_234, "Dining", pending=True)
    repo.upsert_transactions([pending, txn(date(2026, 10, 1), -500)])
    assert repo.transactions_in(Month(2026, 9)) == [pending]

    posted = replace(pending, pending=False, posted=date(2026, 9, 4))
    repo.upsert_transactions([posted])
    assert repo.transactions_in(Month(2026, 9)) == [posted]


class MemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self):
        super().__init__()
        self.passwords = {}

    def get_password(self, service, username):
        return self.passwords.get((service, username))

    def set_password(self, service, username, password):
        self.passwords[(service, username)] = password

    def delete_password(self, service, username):
        del self.passwords[(service, username)]


@pytest.fixture
def memory_keyring():
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


def test_db_key_is_created_once_and_reused(memory_keyring):
    key = keystore.get_or_create_db_key()
    assert len(key) == 64
    assert keystore.get_or_create_db_key() == key
    assert memory_keyring.passwords == {(keystore.SERVICE, keystore.KEY_NAME): key}
