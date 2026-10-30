# Personal-Finance-Tracker
Tracks all my personal finances from transactions, wires, payments, and investments, in one
place that runs on my own machine.

## What works so far

- **Encrypted local storage.** Everything is stored in a SQLCipher database (SQLite with
  AES-256 encryption). The key is generated on first run and kept in the macOS Keychain, so a
  copy of the database file is unreadable without it.
- **Budgets with monthly limits**, loaded from `budget.toml`.
- **Paycheck allocation.** When a paycheck lands, categories are filled up to their limits in
  priority order (rent before dining). A second paycheck in the month tops up the rest.
- **Leftovers to investments.** The first paycheck of a new month closes the previous one.
  Whatever wasn't spent, with any overspending netted out, is earmarked for your investment
  account and you get a message telling you how much to move.
- **Budget alerts** at 50%, 80% and 100% of a category's limit (configurable), sent once each.
  Right now they print to the terminal. Texting is next on the list.

Accounts aren't connected yet. Transactions come in through `FinanceTracker.sync()`, which
the bank, card and Venmo importers will feed.

## Setup

Requires Python 3.11+.

```bash
python3 -m venv .venv.nosync && ln -s .venv.nosync .venv
.venv/bin/pip install -e ".[dev]"
cp budget.example.toml budget.toml   # then edit your limits and paycheck description
```

This repo lives in an iCloud-synced folder. iCloud marks the files inside a regular `.venv`
as hidden, and Python 3.13 then ignores the editable install. iCloud skips folders ending in
`.nosync`, so the virtualenv lives there and `.venv` points to it.

```bash
.venv/bin/pft demo     # a sample month: paychecks, spending, alerts, and the leftover sweep
.venv/bin/pft init     # create your real encrypted database and Keychain entry
.venv/bin/pytest       # run the tests
```

## How the money math works

- Amounts are integer cents. Positive is money in, negative is money out, for every account.
- **Transfers** between your own accounts (credit card payments, brokerage deposits) are
  marked `is_transfer` and never count as spending, so nothing is counted twice.
- **Refunds:** money coming in that's tagged with a budget category reduces that category's
  spending. A friend paying you back on Venmo for dinner lowers Dining.
- **Pending** charges count right away, so alerts arrive before a charge posts.
- **Importing history** won't replay old months. Only paychecks from this month and last
  month get budgeted.

## Security model

- The database lives in `~/Library/Application Support/Personal Finance Tracker/`, outside
  this repo and outside iCloud. Set `PFT_DATA_DIR` to put it somewhere else. The file is
  `0600` and its folder is `0700`.
- If you delete the Keychain entry `personal-finance-tracker`, the database can't be opened
  again.
- Account connections will be read-only. The tracker can't move money, so a bug or a
  compromise can't either.
- `budget.toml`, database files and CSV exports are gitignored. They still sync to iCloud if
  you save them inside this folder, so keep bank exports somewhere else.

## Layout

```
src/finance_tracker/
  models.py    accounts, transactions, budget plan, months
  budget.py    spending, paycheck allocation, month summary, alerts (pure functions)
  tracker.py   sync(): stores transactions, budgets paychecks, closes months, sends alerts
  storage.py   encrypted SQLite schema and queries
  keystore.py  database key in the Keychain
  config.py    loads budget.toml
  demo.py      sample month used by `pft demo`
tests/         pytest suite
```

## Roadmap

1. Account connections: Plaid or SimpleFIN for bank, credit card and investment accounts;
   Venmo statement CSV import (Venmo has no public API for personal accounts).
2. Text alerts through Twilio or iMessage, replacing the console notifier.
3. Local dashboard on `localhost` for transactions, budgets and net worth.
4. Categorization rules, e.g. "TRADER JOE" means Groceries.
