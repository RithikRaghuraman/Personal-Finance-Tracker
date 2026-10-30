"""Budget math: what got spent, how a paycheck is split, and what's left to invest.

Everything here works on plain records with no database, so it's easy to test.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .models import BudgetPlan, Month, Transaction
from .money import format_cents

UNCATEGORIZED = "Uncategorized"


def spending_by_category(
    transactions: Iterable[Transaction], month: Month, budgeted: frozenset[str]
) -> dict[str, int]:
    """Net spending per category for one month, in positive cents.

    Purchases add to their category. Money coming in subtracts as a refund only when it's
    tagged with a budget category (a friend paying you back on Venmo for dinner, say);
    otherwise it's income and doesn't count here. Transfers between your own accounts are
    skipped, so paying a credit card bill doesn't count on top of the purchases it covers.
    Pending charges count, so alerts arrive before a charge posts.
    """
    totals: dict[str, int] = defaultdict(int)
    for txn in transactions:
        if txn.is_transfer or not month.contains(txn.posted):
            continue
        if txn.amount_cents < 0:
            totals[txn.category or UNCATEGORIZED] -= txn.amount_cents
        elif txn.category in budgeted:
            totals[txn.category] -= txn.amount_cents
    return dict(totals)


@dataclass(frozen=True)
class Allocation:
    """How one paycheck was split across budget categories."""

    per_category: dict[str, int]
    # Money left after every category reached its limit. It counts toward the month's
    # leftover, so it goes to investments when the month closes.
    unassigned_cents: int


def allocate_paycheck(
    amount_cents: int, plan: BudgetPlan, already_allocated: Mapping[str, int]
) -> Allocation:
    """Fill each category up to its monthly limit, highest priority first.

    When you're paid twice a month, the first paycheck covers the top priorities (rent
    before dining) and the second tops up the rest.
    """
    if amount_cents <= 0:
        raise ValueError("a paycheck must be a positive amount")
    remaining = amount_cents
    per_category: dict[str, int] = {}
    for category in plan.by_priority():
        need = category.monthly_limit_cents - already_allocated.get(category.name, 0)
        share = min(max(need, 0), remaining)
        if share > 0:
            per_category[category.name] = share
            remaining -= share
    return Allocation(per_category, remaining)


@dataclass(frozen=True)
class CategoryStatus:
    name: str
    limit_cents: int
    allocated_cents: int
    spent_cents: int

    @property
    def remaining_cents(self) -> int:
        """Money actually set aside that hasn't been spent yet. Negative means overspent."""
        return self.allocated_cents - self.spent_cents


@dataclass(frozen=True)
class MonthSummary:
    month: Month
    categories: tuple[CategoryStatus, ...]
    # Spending in categories that aren't in the plan, including anything uncategorized.
    unbudgeted: dict[str, int]
    unassigned_cents: int

    @property
    def funded_cents(self) -> int:
        return sum(c.allocated_cents for c in self.categories) + self.unassigned_cents

    @property
    def spent_cents(self) -> int:
        return sum(c.spent_cents for c in self.categories) + sum(self.unbudgeted.values())

    @property
    def leftover_cents(self) -> int:
        """What was funded minus everything spent. Negative if the month went over overall."""
        return self.funded_cents - self.spent_cents

    @property
    def sweep_cents(self) -> int:
        """What can go to investments.

        Overspending in one category is netted against savings in the others, because that
        money is already gone. This never sweeps more cash than the month actually left.
        """
        return max(self.leftover_cents, 0)


def summarize_month(
    month: Month,
    plan: BudgetPlan,
    allocated: Mapping[str, int],
    unassigned_cents: int,
    transactions: Iterable[Transaction],
) -> MonthSummary:
    spent = spending_by_category(transactions, month, plan.category_names)
    categories = []
    for category in plan.categories:
        categories.append(
            CategoryStatus(
                category.name,
                category.monthly_limit_cents,
                allocated.get(category.name, 0),
                spent.pop(category.name, 0),
            )
        )
    # Whatever is left in `spent` falls outside the plan.
    return MonthSummary(month, tuple(categories), spent, unassigned_cents)


@dataclass(frozen=True)
class BudgetAlert:
    month: Month
    category: str
    spent_cents: int
    limit_cents: int
    # Every threshold this alert covers. If spending jumps past several at once you get one
    # text, and all of them are recorded so the lower ones don't fire later.
    percents: tuple[int, ...]

    @property
    def message(self) -> str:
        used = self.spent_cents * 100 // self.limit_cents
        spent, limit = format_cents(self.spent_cents), format_cents(self.limit_cents)
        if self.spent_cents > self.limit_cents:
            return f"{self.category} is over budget for {self.month.label}: {spent} of {limit} ({used}%)."
        left = format_cents(self.limit_cents - self.spent_cents)
        return (
            f"{self.category} is at {used}% of its {self.month.label} budget:"
            f" {spent} of {limit}, {left} left."
        )


def budget_alerts(
    summary: MonthSummary, plan: BudgetPlan, already_sent: set[tuple[str, int]]
) -> list[BudgetAlert]:
    """Alerts for thresholds a category has newly reached.

    Categories with alerts turned off, or with a limit of zero, are skipped.
    """
    quiet = {c.name for c in plan.categories if not c.alerts}
    alerts = []
    for status in summary.categories:
        if status.limit_cents <= 0 or status.name in quiet:
            continue
        crossed = tuple(
            p
            for p in plan.alert_at_percent
            if status.spent_cents * 100 >= p * status.limit_cents
            and (status.name, p) not in already_sent
        )
        if crossed:
            alerts.append(
                BudgetAlert(summary.month, status.name, status.spent_cents, status.limit_cents, crossed)
            )
    return alerts
