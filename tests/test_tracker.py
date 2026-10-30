from datetime import date

import pytest
from factories import PLAN, paycheck, txn

from finance_tracker.models import Month
from finance_tracker.tracker import FinanceTracker

SEPT = Month(2026, 9)


class RecordingNotifier:
    def __init__(self):
        self.messages: list[str] = []

    def send(self, message: str) -> None:
        self.messages.append(message)


@pytest.fixture
def notifier():
    return RecordingNotifier()


@pytest.fixture
def tracker(repo, notifier):
    return FinanceTracker(repo, PLAN, notifier)


def test_paycheck_is_budgeted_once_even_if_synced_twice(tracker, repo, notifier):
    pay = paycheck(date(2026, 9, 4))
    tracker.sync([pay], today=date(2026, 9, 4))
    tracker.sync([pay], today=date(2026, 9, 5))

    assert repo.allocations_for(SEPT) == {"Rent": 100_000, "Groceries": 40_000, "Dining": 10_000}
    assert len(notifier.messages) == 1
    assert notifier.messages[0].startswith("Paycheck of $1,500.00 budgeted for September 2026")


def test_first_paycheck_of_a_month_sweeps_last_months_leftover(tracker, repo, notifier):
    tracker.sync(
        [
            paycheck(date(2026, 9, 4)),
            paycheck(date(2026, 9, 18)),
            txn(date(2026, 9, 5), -100_000, "Rent", account="checking"),
            txn(date(2026, 9, 10), -30_000, "Groceries"),
        ],
        today=date(2026, 9, 30),
    )
    notifier.messages.clear()

    tracker.sync([paycheck(date(2026, 10, 2))], today=date(2026, 10, 2))
    tracker.sync([paycheck(date(2026, 10, 16))], today=date(2026, 10, 16))

    # Funded 3,000.00, spent 1,300.00.
    assert repo.sweep_for(SEPT).amount_cents == 170_000
    sweep_messages = [m for m in notifier.messages if "left over" in m]
    assert sweep_messages == [
        "September 2026 closed with $1,700.00 left over. Move it to Brokerage to invest it."
    ]


def test_overspent_month_sweeps_nothing(tracker, repo, notifier):
    tracker.sync(
        [paycheck(date(2026, 9, 4)), txn(date(2026, 9, 5), -160_000, "Rent", account="checking")],
        today=date(2026, 9, 30),
    )
    tracker.sync([paycheck(date(2026, 10, 2))], today=date(2026, 10, 2))

    assert repo.sweep_for(SEPT).amount_cents == 0
    assert any("going $100.00 over" in m for m in notifier.messages)


def test_month_before_tracking_started_is_not_swept(tracker, repo, notifier):
    tracker.sync([paycheck(date(2026, 10, 2))], today=date(2026, 10, 2))
    assert repo.sweep_for(SEPT) is None
    assert len(notifier.messages) == 1


def test_each_alert_threshold_texts_once(tracker, notifier):
    today = date(2026, 9, 20)
    tracker.sync([txn(date(2026, 9, 10), -11_000, "Dining")], today=today)
    tracker.sync([], today=today)
    assert notifier.messages == [
        "Dining is at 55% of its September 2026 budget: $110.00 of $200.00, $90.00 left."
    ]

    tracker.sync([txn(date(2026, 9, 19), -10_000, "Dining")], today=today)
    assert len(notifier.messages) == 2
    assert notifier.messages[1].startswith("Dining is over budget for September 2026")


def test_importing_history_does_not_replay_old_months(tracker, repo, notifier):
    tracker.sync(
        [paycheck(date(2026, 6, 5)), txn(date(2026, 6, 6), -30_000, "Dining")],
        today=date(2026, 9, 1),
    )
    assert repo.allocations_for(Month(2026, 6)) == {}
    assert notifier.messages == []
