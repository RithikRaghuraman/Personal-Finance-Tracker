from datetime import date

import pytest
from factories import PLAN, paycheck, txn

from finance_tracker.budget import (
    UNCATEGORIZED,
    allocate_paycheck,
    budget_alerts,
    spending_by_category,
    summarize_month,
)
from finance_tracker.models import BudgetCategory, BudgetPlan, Month

SEPT = Month(2026, 9)
DAY = date(2026, 9, 10)


def spending(*transactions):
    return spending_by_category(transactions, SEPT, PLAN.category_names)


def test_purchases_add_and_refunds_subtract():
    totals = spending(
        txn(DAY, -5_000, "Dining"),
        txn(DAY, -3_000, "Dining"),
        txn(DAY, 2_000, "Dining", description="Sam paid you", account="venmo"),
    )
    assert totals == {"Dining": 6_000}


def test_transfers_between_own_accounts_are_skipped():
    totals = spending(
        txn(DAY, -10_000, "Groceries"),
        txn(DAY, -50_000, description="Card payment", account="checking", transfer=True),
        txn(DAY, 50_000, description="Payment received", transfer=True),
    )
    assert totals == {"Groceries": 10_000}


def test_income_is_not_spending():
    totals = spending(paycheck(DAY), txn(DAY, 30_000, "Income", account="checking"))
    assert totals == {}


def test_spending_outside_the_plan_is_kept():
    totals = spending(txn(DAY, -2_500), txn(DAY, -1_000, "Gifts"))
    assert totals == {UNCATEGORIZED: 2_500, "Gifts": 1_000}


def test_other_months_are_ignored():
    assert spending(txn(date(2026, 10, 1), -5_000, "Dining")) == {}


def test_first_paycheck_funds_top_priorities_and_second_tops_up():
    first = allocate_paycheck(150_000, PLAN, {})
    assert first.per_category == {"Rent": 100_000, "Groceries": 40_000, "Dining": 10_000}
    assert first.unassigned_cents == 0

    second = allocate_paycheck(150_000, PLAN, first.per_category)
    assert second.per_category == {"Dining": 10_000}
    assert second.unassigned_cents == 140_000


def test_paycheck_must_be_positive():
    with pytest.raises(ValueError):
        allocate_paycheck(0, PLAN, {})


def test_leftover_nets_overspending_against_savings():
    allocated = {"Rent": 100_000, "Groceries": 40_000, "Dining": 20_000}
    transactions = [
        txn(DAY, -100_000, "Rent", account="checking"),
        txn(DAY, -45_000, "Groceries"),  # 5,000 over
        txn(DAY, -15_000, "Dining"),  # 5,000 under
        txn(DAY, -2_000),  # uncategorized
    ]
    summary = summarize_month(SEPT, PLAN, allocated, 140_000, transactions)

    assert summary.funded_cents == 300_000
    assert summary.spent_cents == 162_000
    assert summary.sweep_cents == 138_000
    assert summary.unbudgeted == {UNCATEGORIZED: 2_000}
    groceries = next(c for c in summary.categories if c.name == "Groceries")
    assert groceries.remaining_cents == -5_000


def test_sweep_is_never_negative():
    summary = summarize_month(SEPT, PLAN, {"Rent": 100_000}, 0, [txn(DAY, -120_000, "Rent")])
    assert summary.leftover_cents == -20_000
    assert summary.sweep_cents == 0


def summary_with(*transactions):
    return summarize_month(SEPT, PLAN, {}, 0, transactions)


def test_one_alert_covers_every_threshold_crossed_at_once():
    alerts = budget_alerts(summary_with(txn(DAY, -33_000, "Groceries")), PLAN, set())
    assert len(alerts) == 1
    assert alerts[0].percents == (50, 80)
    assert "82%" in alerts[0].message
    assert "$70.00 left" in alerts[0].message


def test_alerts_already_sent_are_not_repeated():
    summary = summary_with(txn(DAY, -33_000, "Groceries"))
    assert budget_alerts(summary, PLAN, {("Groceries", 50), ("Groceries", 80)}) == []


def test_over_budget_message():
    (alert,) = budget_alerts(summary_with(txn(DAY, -41_000, "Groceries")), PLAN, set())
    assert alert.percents == (50, 80, 100)
    assert "over budget" in alert.message


def test_quiet_and_zero_limit_categories_never_alert():
    plan = BudgetPlan(
        categories=(*PLAN.categories, BudgetCategory("Gifts", 0)),
        paycheck_rules=PLAN.paycheck_rules,
        investment_account_id="brokerage",
    )
    summary = summarize_month(
        SEPT, plan, {}, 0, [txn(DAY, -100_000, "Rent"), txn(DAY, -1_000, "Gifts")]
    )
    assert budget_alerts(summary, plan, set()) == []


def test_plan_rejects_duplicate_categories():
    with pytest.raises(ValueError):
        BudgetPlan(
            categories=(BudgetCategory("Dining", 1), BudgetCategory("Dining", 2)),
            paycheck_rules=(),
            investment_account_id="brokerage",
        )
