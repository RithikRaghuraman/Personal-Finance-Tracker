"""The records the tracker works with.

Amounts are integer cents. Every account type uses the same sign convention: positive is
money coming in, negative is money going out. Importers convert to this, because banks and
aggregators disagree (Plaid, for one, reports purchases as positive numbers).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class AccountType(StrEnum):
    CHECKING = "checking"
    SAVINGS = "savings"
    CREDIT_CARD = "credit_card"
    INVESTMENT = "investment"
    VENMO = "venmo"


@dataclass(frozen=True)
class Account:
    id: str
    name: str
    type: AccountType
    institution: str = ""
    # Where the data comes from: "plaid", "simplefin", "csv" or "manual".
    source: str = "manual"


@dataclass(frozen=True)
class Transaction:
    id: str
    account_id: str
    posted: date
    amount_cents: int
    description: str
    category: str | None = None
    # Money moving between your own accounts, like a credit card payment or a brokerage
    # deposit. Transfers are left out of spending so nothing is counted twice.
    is_transfer: bool = False
    pending: bool = False


@dataclass(frozen=True, order=True)
class Month:
    year: int
    month: int

    @classmethod
    def of(cls, day: date) -> Month:
        return cls(day.year, day.month)

    @property
    def first_day(self) -> date:
        return date(self.year, self.month, 1)

    @property
    def label(self) -> str:
        return self.first_day.strftime("%B %Y")

    def previous(self) -> Month:
        if self.month == 1:
            return Month(self.year - 1, 12)
        return Month(self.year, self.month - 1)

    def next(self) -> Month:
        if self.month == 12:
            return Month(self.year + 1, 1)
        return Month(self.year, self.month + 1)

    def contains(self, day: date) -> bool:
        return (day.year, day.month) == (self.year, self.month)

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


@dataclass(frozen=True)
class BudgetCategory:
    name: str
    monthly_limit_cents: int
    # Lower numbers get funded first when a paycheck comes in.
    priority: int = 100
    # Turn off for fixed bills like rent, which always reach 100%.
    alerts: bool = True


@dataclass(frozen=True)
class PaycheckRule:
    """Recognizes a paycheck by its description, e.g. "ACME CORP PAYROLL"."""

    description_contains: str
    account_id: str | None = None
    min_amount_cents: int = 0

    def matches(self, txn: Transaction) -> bool:
        return (
            txn.amount_cents > 0
            and not txn.is_transfer
            and txn.amount_cents >= self.min_amount_cents
            and self.description_contains.casefold() in txn.description.casefold()
            and (self.account_id is None or self.account_id == txn.account_id)
        )


@dataclass(frozen=True)
class BudgetPlan:
    categories: tuple[BudgetCategory, ...]
    paycheck_rules: tuple[PaycheckRule, ...]
    # Account that a finished month's leftover money is earmarked for.
    investment_account_id: str
    # Send a text when a category's spending reaches each of these percentages of its limit.
    alert_at_percent: tuple[int, ...] = (50, 80, 100)

    def __post_init__(self) -> None:
        names = [c.name for c in self.categories]
        if len(set(names)) != len(names):
            raise ValueError("budget category names must be unique")
        if any(c.monthly_limit_cents < 0 for c in self.categories):
            raise ValueError("budget limits can't be negative")
        if any(p <= 0 for p in self.alert_at_percent):
            raise ValueError("alert percentages must be positive")

    @property
    def category_names(self) -> frozenset[str]:
        return frozenset(c.name for c in self.categories)

    def by_priority(self) -> list[BudgetCategory]:
        # sorted() is stable, so ties keep the order they were listed in.
        return sorted(self.categories, key=lambda c: c.priority)

    def is_paycheck(self, txn: Transaction) -> bool:
        return any(rule.matches(txn) for rule in self.paycheck_rules)


@dataclass(frozen=True)
class Sweep:
    """A finished month's leftover money, earmarked for the investment account.

    Recording one closes the month, even when the amount is zero. The tracker only reads
    your accounts, so it tells you to make the transfer instead of making it itself.
    """

    month: Month
    amount_cents: int
    to_account_id: str
