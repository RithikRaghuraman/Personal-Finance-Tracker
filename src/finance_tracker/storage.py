"""The encrypted SQLite database (SQLCipher) and the queries the tracker runs against it."""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from datetime import date
from pathlib import Path

import sqlcipher3

from .budget import Allocation
from .models import Account, AccountType, Month, Sweep, Transaction

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL,
    institution TEXT NOT NULL DEFAULT '',
    source      TEXT NOT NULL DEFAULT 'manual'
);

CREATE TABLE IF NOT EXISTS transactions (
    id           TEXT PRIMARY KEY,
    account_id   TEXT NOT NULL REFERENCES accounts(id),
    posted       TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    description  TEXT NOT NULL,
    category     TEXT,
    is_transfer  INTEGER NOT NULL DEFAULT 0,
    pending      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS transactions_posted ON transactions(posted);

-- One row per budgeted paycheck, so syncing the same paycheck twice never budgets it twice.
CREATE TABLE IF NOT EXISTS paychecks (
    transaction_id   TEXT PRIMARY KEY REFERENCES transactions(id),
    month            TEXT NOT NULL,
    unassigned_cents INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS allocations (
    transaction_id TEXT NOT NULL REFERENCES paychecks(transaction_id),
    category       TEXT NOT NULL,
    amount_cents   INTEGER NOT NULL,
    PRIMARY KEY (transaction_id, category)
);

-- A month gets a row here once it's closed, even when there was nothing left to invest.
CREATE TABLE IF NOT EXISTS sweeps (
    month         TEXT PRIMARY KEY,
    amount_cents  INTEGER NOT NULL,
    to_account_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts_sent (
    month    TEXT NOT NULL,
    category TEXT NOT NULL,
    percent  INTEGER NOT NULL,
    PRIMARY KEY (month, category, percent)
);
"""

_TRANSACTION_COLUMNS = "id, account_id, posted, amount_cents, description, category, is_transfer, pending"


class WrongKeyError(Exception):
    """The database file exists but this key can't open it."""


def connect(path: str | Path, key_hex: str) -> sqlcipher3.Connection:
    """Open or create the encrypted database at `path` (":memory:" works for tests).

    `key_hex` is a 256-bit key written as 64 hex characters. A wrong key fails here rather
    than on the first query. The file is readable only by your user account.
    """
    # The key is pasted into a PRAGMA, so check it can't carry anything else.
    if not re.fullmatch(r"[0-9a-fA-F]{64}", key_hex):
        raise ValueError("database key must be 64 hex characters")
    on_disk = str(path) != ":memory:"
    if on_disk:
        Path(path).parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    conn = sqlcipher3.connect(str(path))
    conn.execute(f"PRAGMA key = \"x'{key_hex}'\"")
    try:
        conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
    except sqlcipher3.DatabaseError as exc:
        conn.close()
        raise WrongKeyError(f"can't open {path}: wrong key, or not a tracker database") from exc
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    if on_disk:
        os.chmod(path, 0o600)
    return conn


class Repository:
    """Reads and writes tracker records. Every write commits right away."""

    def __init__(self, conn: sqlcipher3.Connection) -> None:
        self.conn = conn

    def add_account(self, account: Account) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO accounts (id, name, type, institution, source) VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET name = excluded.name, type = excluded.type,"
                " institution = excluded.institution, source = excluded.source",
                (account.id, account.name, account.type.value, account.institution, account.source),
            )

    def account(self, account_id: str) -> Account | None:
        row = self.conn.execute(
            "SELECT id, name, type, institution, source FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if row is None:
            return None
        return Account(row[0], row[1], AccountType(row[2]), row[3], row[4])

    def upsert_transactions(self, transactions: Iterable[Transaction]) -> None:
        """Insert new transactions and update ones already stored (say, pending to posted)."""
        with self.conn:
            self.conn.executemany(
                f"INSERT INTO transactions ({_TRANSACTION_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET account_id = excluded.account_id,"
                " posted = excluded.posted, amount_cents = excluded.amount_cents,"
                " description = excluded.description, category = excluded.category,"
                " is_transfer = excluded.is_transfer, pending = excluded.pending",
                [
                    (
                        t.id,
                        t.account_id,
                        t.posted.isoformat(),
                        t.amount_cents,
                        t.description,
                        t.category,
                        int(t.is_transfer),
                        int(t.pending),
                    )
                    for t in transactions
                ],
            )

    def transactions_in(self, month: Month) -> list[Transaction]:
        rows = self.conn.execute(
            f"SELECT {_TRANSACTION_COLUMNS} FROM transactions"
            " WHERE posted >= ? AND posted < ? ORDER BY posted, id",
            (month.first_day.isoformat(), month.next().first_day.isoformat()),
        ).fetchall()
        return [
            Transaction(r[0], r[1], date.fromisoformat(r[2]), r[3], r[4], r[5], bool(r[6]), bool(r[7]))
            for r in rows
        ]

    def paycheck_processed(self, transaction_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM paychecks WHERE transaction_id = ?", (transaction_id,)
        ).fetchone()
        return row is not None

    def record_paycheck(self, transaction_id: str, month: Month, allocation: Allocation) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO paychecks (transaction_id, month, unassigned_cents) VALUES (?, ?, ?)",
                (transaction_id, str(month), allocation.unassigned_cents),
            )
            self.conn.executemany(
                "INSERT INTO allocations (transaction_id, category, amount_cents) VALUES (?, ?, ?)",
                [(transaction_id, name, cents) for name, cents in allocation.per_category.items()],
            )

    def allocations_for(self, month: Month) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT a.category, SUM(a.amount_cents) FROM allocations a"
            " JOIN paychecks p ON p.transaction_id = a.transaction_id"
            " WHERE p.month = ? GROUP BY a.category",
            (str(month),),
        ).fetchall()
        return dict(rows)

    def unassigned_for(self, month: Month) -> int:
        (total,) = self.conn.execute(
            "SELECT COALESCE(SUM(unassigned_cents), 0) FROM paychecks WHERE month = ?", (str(month),)
        ).fetchone()
        return total

    def sweep_for(self, month: Month) -> Sweep | None:
        row = self.conn.execute(
            "SELECT amount_cents, to_account_id FROM sweeps WHERE month = ?", (str(month),)
        ).fetchone()
        if row is None:
            return None
        return Sweep(month, row[0], row[1])

    def record_sweep(self, sweep: Sweep) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO sweeps (month, amount_cents, to_account_id) VALUES (?, ?, ?)",
                (str(sweep.month), sweep.amount_cents, sweep.to_account_id),
            )

    def alerts_sent(self, month: Month) -> set[tuple[str, int]]:
        rows = self.conn.execute(
            "SELECT category, percent FROM alerts_sent WHERE month = ?", (str(month),)
        ).fetchall()
        return {(category, percent) for category, percent in rows}

    def record_alerts(self, month: Month, category: str, percents: Iterable[int]) -> None:
        with self.conn:
            self.conn.executemany(
                "INSERT OR IGNORE INTO alerts_sent (month, category, percent) VALUES (?, ?, ?)",
                [(str(month), category, p) for p in percents],
            )
