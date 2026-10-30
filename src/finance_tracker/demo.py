"""A sample September: two paychecks and everyday spending, then an October paycheck that
closes the month and earmarks what's left for investments. Runs in a throwaway database."""

import itertools
import secrets
from datetime import date

from .budget import MonthSummary
from .models import Account, AccountType, BudgetCategory, BudgetPlan, Month, PaycheckRule, Transaction
from .money import format_cents, to_cents
from .storage import Repository, connect
from .tracker import ConsoleNotifier, FinanceTracker

PLAN = BudgetPlan(
    categories=(
        BudgetCategory("Rent", to_cents(1400), priority=1, alerts=False),
        BudgetCategory("Groceries", to_cents(450), priority=2),
        BudgetCategory("Transportation", to_cents(150), priority=3),
        BudgetCategory("Dining", to_cents(250), priority=4),
        BudgetCategory("Fun", to_cents(200), priority=5),
    ),
    paycheck_rules=(PaycheckRule("ACME CORP PAYROLL", min_amount_cents=to_cents(500)),),
    investment_account_id="brokerage",
)

ACCOUNTS = (
    Account("checking", "Everyday Checking", AccountType.CHECKING, "Sample Bank"),
    Account("card", "Rewards Card", AccountType.CREDIT_CARD, "Sample Bank"),
    Account("venmo", "Venmo", AccountType.VENMO, "Venmo"),
    Account("brokerage", "Brokerage", AccountType.INVESTMENT, "Sample Brokerage"),
)

TRANSFER = "(transfer)"


def _sample_syncs() -> list[tuple[date, list[Transaction]]]:
    """Each entry is one day's sync: the date and the transactions that arrived."""
    ids = itertools.count(1)

    def day(posted: date, *rows: tuple[str, str, str, str | None]) -> tuple[date, list[Transaction]]:
        txns = []
        for account, amount, description, category in rows:
            transfer = category == TRANSFER
            txns.append(
                Transaction(
                    f"demo-{next(ids)}",
                    account,
                    posted,
                    to_cents(amount),
                    description,
                    None if transfer else category,
                    transfer,
                )
            )
        return posted, txns

    sep = lambda d: date(2026, 9, d)  # noqa: E731
    return [
        day(sep(4),
            ("checking", "1600.00", "ACME CORP PAYROLL", None),
            ("checking", "-1400.00", "Zelle to landlord", "Rent")),
        day(sep(6),
            ("card", "-84.12", "Trader Joe's", "Groceries"),
            ("card", "-14.85", "Chipotle", "Dining")),
        day(sep(12),
            ("card", "-102.40", "Whole Foods", "Groceries"),
            ("card", "-96.00", "Dinner with friends", "Dining"),
            ("venmo", "32.00", "Sam paid you for dinner", "Dining")),
        day(sep(15),
            ("card", "-90.00", "Transit pass", "Transportation"),
            ("card", "-18.50", "Sweetgreen", "Dining"),
            ("card", "-45.00", "Drinks", "Dining")),
        day(sep(18),
            ("checking", "1600.00", "ACME CORP PAYROLL", None)),
        day(sep(20),
            ("card", "-120.00", "Concert tickets", "Fun"),
            ("card", "-67.40", "Birthday dinner", "Dining")),
        day(sep(25),
            ("checking", "-600.00", "Credit card payment", TRANSFER),
            ("card", "600.00", "Payment received", TRANSFER),
            ("card", "-96.30", "Trader Joe's", "Groceries"),
            ("venmo", "-25.00", "You paid Alex", None)),
        day(sep(28),
            ("card", "-58.20", "Takeout", "Dining")),
        day(date(2026, 10, 2),
            ("checking", "1600.00", "ACME CORP PAYROLL", None)),
    ]


def _print_summary(summary: MonthSummary) -> None:
    columns = f"{'':<16}{'Limit':>12}{'Funded':>12}{'Spent':>12}{'Left':>12}"
    print(f"\n{summary.month.label} summary\n{columns}")
    for c in summary.categories:
        print(
            f"{c.name:<16}{format_cents(c.limit_cents):>12}{format_cents(c.allocated_cents):>12}"
            f"{format_cents(c.spent_cents):>12}{format_cents(c.remaining_cents):>12}"
        )
    for name, cents in summary.unbudgeted.items():
        print(f"{name:<16}{'':>24}{format_cents(cents):>12}")
    if summary.unassigned_cents:
        print(f"{'Unassigned':<16}{'':>12}{format_cents(summary.unassigned_cents):>12}")
    print(
        f"\nFunded {format_cents(summary.funded_cents)}, spent {format_cents(summary.spent_cents)},"
        f" {format_cents(summary.sweep_cents)} earmarked for investments."
    )


def run() -> None:
    repo = Repository(connect(":memory:", secrets.token_hex(32)))
    for account in ACCOUNTS:
        repo.add_account(account)
    tracker = FinanceTracker(repo, PLAN, ConsoleNotifier())
    for today, transactions in _sample_syncs():
        print(f"\n[{today:%b %d}]")
        tracker.sync(transactions, today=today)
    _print_summary(tracker.month_summary(Month(2026, 9)))
