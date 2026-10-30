"""Shared test data: a small budget plan, accounts, and a transaction builder."""

import itertools
from datetime import date

from finance_tracker.models import (
    Account,
    AccountType,
    BudgetCategory,
    BudgetPlan,
    PaycheckRule,
    Transaction,
)

PLAN = BudgetPlan(
    categories=(
        BudgetCategory("Rent", 100_000, priority=1, alerts=False),
        BudgetCategory("Groceries", 40_000, priority=2),
        BudgetCategory("Dining", 20_000, priority=3),
    ),
    paycheck_rules=(PaycheckRule("ACME PAYROLL", min_amount_cents=50_000),),
    investment_account_id="brokerage",
)

ACCOUNTS = (
    Account("checking", "Checking", AccountType.CHECKING),
    Account("card", "Credit Card", AccountType.CREDIT_CARD),
    Account("venmo", "Venmo", AccountType.VENMO),
    Account("brokerage", "Brokerage", AccountType.INVESTMENT),
)

_ids = itertools.count(1)


def txn(
    posted: date,
    amount_cents: int,
    category: str | None = None,
    description: str = "purchase",
    account: str = "card",
    transfer: bool = False,
    pending: bool = False,
) -> Transaction:
    return Transaction(
        f"t{next(_ids)}", account, posted, amount_cents, description, category, transfer, pending
    )


def paycheck(posted: date, amount_cents: int = 150_000) -> Transaction:
    return txn(posted, amount_cents, description="ACME PAYROLL DIRECT DEP", account="checking")
