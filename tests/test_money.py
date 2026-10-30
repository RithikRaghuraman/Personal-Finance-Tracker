from finance_tracker.money import format_cents, to_cents


def test_to_cents_rounds_half_up():
    assert to_cents("12.345") == 1235
    assert to_cents(12.34) == 1234
    assert to_cents("-5") == -500


def test_format_cents():
    assert format_cents(123_456) == "$1,234.56"
    assert format_cents(-5) == "-$0.05"
    assert format_cents(0) == "$0.00"
