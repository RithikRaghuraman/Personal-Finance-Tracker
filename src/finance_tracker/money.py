"""Money is integer cents everywhere, so totals never drift the way floats do."""

from decimal import ROUND_HALF_UP, Decimal


def to_cents(amount: str | int | float | Decimal) -> int:
    """Convert a dollar amount like "12.34" or 12.34 to 1234."""
    dollars = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(dollars * 100)


def format_cents(cents: int) -> str:
    """Format 123456 as "$1,234.56" and -500 as "-$5.00"."""
    sign = "-" if cents < 0 else ""
    dollars, rest = divmod(abs(cents), 100)
    return f"{sign}${dollars:,}.{rest:02d}"
