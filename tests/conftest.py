import secrets

import pytest
from factories import ACCOUNTS

from finance_tracker.storage import Repository, connect


@pytest.fixture
def repo():
    conn = connect(":memory:", secrets.token_hex(32))
    repo = Repository(conn)
    for account in ACCOUNTS:
        repo.add_account(account)
    yield repo
    conn.close()
