from pathlib import Path

from finance_tracker.config import load_plan

EXAMPLE = Path(__file__).parent.parent / "budget.example.toml"


def test_example_plan_loads():
    plan = load_plan(EXAMPLE)

    assert [c.name for c in plan.categories] == ["Rent", "Groceries", "Transportation", "Dining", "Fun"]
    rent, groceries = plan.categories[:2]
    assert (rent.monthly_limit_cents, rent.alerts) == (140_000, False)
    assert (groceries.monthly_limit_cents, groceries.alerts) == (45_000, True)
    assert plan.paycheck_rules[0].min_amount_cents == 50_000
    assert plan.investment_account_id == "brokerage"
    assert plan.alert_at_percent == (50, 80, 100)
