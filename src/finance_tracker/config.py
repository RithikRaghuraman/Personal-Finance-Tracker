"""Where data lives, and loading your budget plan from TOML (see budget.example.toml)."""

import os
import tomllib
from pathlib import Path

from .models import BudgetCategory, BudgetPlan, PaycheckRule
from .money import to_cents


def default_data_dir() -> Path:
    """The database's folder. It sits outside the repo so it can't be committed by accident."""
    override = os.environ.get("PFT_DATA_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / "Personal Finance Tracker"


def load_plan(path: str | Path) -> BudgetPlan:
    with open(path, "rb") as f:
        data = tomllib.load(f)
    categories = tuple(
        BudgetCategory(c["name"], to_cents(c["limit"]), c.get("priority", 100), c.get("alerts", True))
        for c in data.get("category", [])
    )
    paycheck_rules = tuple(
        PaycheckRule(p["description_contains"], p.get("account"), to_cents(p.get("min_amount", 0)))
        for p in data.get("paycheck", [])
    )
    return BudgetPlan(
        categories,
        paycheck_rules,
        investment_account_id=data["investment_account"],
        alert_at_percent=tuple(data.get("alert_at_percent", (50, 80, 100))),
    )
