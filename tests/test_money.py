import pytest
from app.services.money import parse_expense, money


@pytest.mark.parametrize("text,expected", [
    ("125,50", (12550, None)), ("125.50", (12550, None)),
    ("25", (2500, None)), ("1,5", (150, None)),
    ("0,01", (1, None)), ("1000000", (100000000, None)),
    ("125,50 Biedronka", (12550, "Biedronka")),
    ("10.5 таксі", (1050, "таксі")),
])
def test_valid_amounts(text, expected):
    assert parse_expense(text) == expected


@pytest.mark.parametrize("text", [
    "0", "0.00", "-1", "+1", "1.999", "1,234", "NaN", "nan", "inf", "1e5",
    "1,000.50", "1000000,01", "1 000", "", "20\nabc", "5 " + "a" * 141,
])
def test_invalid_amounts(text):
    with pytest.raises(ValueError):
        parse_expense(text)


def test_output_format():
    assert money(0) == "0,00 zł"
    assert money(123456789) == "1 234 567,89 zł"
    assert money(-5) == "−0,05 zł"
