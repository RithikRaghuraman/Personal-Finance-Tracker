"""Ties it together: store what came in, budget paychecks, close months, send alerts."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Protocol

from .budget import MonthSummary, allocate_paycheck, budget_alerts, summarize_month
from .models import BudgetPlan, Month, Sweep, Transaction
from .money import format_cents
from .storage import Repository


class Notifier(Protocol):
    def send(self, message: str) -> None: ...


class ConsoleNotifier:
    """Prints messages. Stands in for text messages until SMS is set up."""

    def send(self, message: str) -> None:
        print(message)


class FinanceTracker:
    def __init__(self, repo: Repository, plan: BudgetPlan, notifier: Notifier) -> None:
        self.repo = repo
        self.plan = plan
        self.notifier = notifier

    def sync(self, transactions: Iterable[Transaction], today: date | None = None) -> None:
        """Store transactions from any source, then act on what's new.

        Paychecks from this month or last month get budgeted. Older ones are stored but left
        alone, so importing years of history doesn't replay every past month. Alerts only go
        out for the current month.
        """
        this_month = Month.of(today or date.today())
        transactions = list(transactions)
        self.repo.upsert_transactions(transactions)

        recent = (this_month.previous(), this_month)
        for txn in sorted(transactions, key=lambda t: t.posted):
            if (
                Month.of(txn.posted) in recent
                and self.plan.is_paycheck(txn)
                and not self.repo.paycheck_processed(txn.id)
            ):
                self._budget_paycheck(txn)
        self._send_alerts(this_month)

    def month_summary(self, month: Month) -> MonthSummary:
        return summarize_month(
            month,
            self.plan,
            self.repo.allocations_for(month),
            self.repo.unassigned_for(month),
            self.repo.transactions_in(month),
        )

    def _budget_paycheck(self, paycheck: Transaction) -> None:
        month = Month.of(paycheck.posted)
        # The first paycheck of a month is when last month's leftovers get swept.
        self._close_month(month.previous())

        allocation = allocate_paycheck(
            paycheck.amount_cents, self.plan, self.repo.allocations_for(month)
        )
        self.repo.record_paycheck(paycheck.id, month, allocation)

        amount = format_cents(paycheck.amount_cents)
        if allocation.per_category:
            split = ", ".join(f"{name} {format_cents(c)}" for name, c in allocation.per_category.items())
            message = f"Paycheck of {amount} budgeted for {month.label}: {split}."
        else:
            message = f"Paycheck of {amount} arrived and every {month.label} category is already funded."
        if allocation.unassigned_cents:
            message += (
                f" {format_cents(allocation.unassigned_cents)} is unassigned and goes to"
                " investments when the month closes."
            )
        self.notifier.send(message)

    def _close_month(self, month: Month) -> None:
        if self.repo.sweep_for(month) is not None:
            return
        summary = self.month_summary(month)
        if summary.funded_cents == 0:
            # No paychecks were budgeted that month, e.g. before you started using the tracker.
            return
        sweep = Sweep(month, summary.sweep_cents, self.plan.investment_account_id)
        self.repo.record_sweep(sweep)

        if sweep.amount_cents:
            account = self.repo.account(sweep.to_account_id)
            destination = account.name if account else sweep.to_account_id
            self.notifier.send(
                f"{month.label} closed with {format_cents(sweep.amount_cents)} left over."
                f" Move it to {destination} to invest it."
            )
        else:
            over = -summary.leftover_cents
            detail = f", going {format_cents(over)} over" if over else ""
            self.notifier.send(
                f"{month.label} used its whole budget{detail}, so there's nothing to move to investments."
            )

    def _send_alerts(self, month: Month) -> None:
        summary = self.month_summary(month)
        for alert in budget_alerts(summary, self.plan, self.repo.alerts_sent(month)):
            self.notifier.send(alert.message)
            # Recorded after sending, so a failed text is retried on the next sync.
            self.repo.record_alerts(month, alert.category, alert.percents)
