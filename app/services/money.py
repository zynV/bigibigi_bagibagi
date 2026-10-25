"""Integer groszy for storage: no binary floating point in financial calculations."""
from __future__ import annotations

import re
from decimal import Decimal

MAX_GROSZY = 100_000_000  # 1,000,000.00 PLN
_AMOUNT_WITH_NOTE = re.compile(r"(?P<amount>\d+(?:[.,]\d{1,2})?)(?:[ \t]+(?P<note>[^\r\n]{1,140}))?\Z")


def parse_expense(text: str) -> tuple[int, str | None]:
    """Allow '125,50' or '125,50 Biedronka', rejecting zero and >2 decimals."""
    candidate = text.strip()
    match = _AMOUNT_WITH_NOTE.fullmatch(candidate)
    if not match:
        raise ValueError("Введіть суму, наприклад 125,50 або 125,50 Biedronka (до 2 знаків після коми).")
    number = Decimal(match.group("amount").replace(",", "."))
    groszy = int(number * 100)
    if not 0 < groszy <= MAX_GROSZY:
        raise ValueError("Сума має бути більшою за 0 і не перевищувати 1 000 000 zł.")
    note = match.group("note")
    # "1 000" looks like grouped thousands, not a safe amount + memo.
    if note and note.strip().isdigit():
        raise ValueError("Вводьте число без пробілів: 1000 або 1000,00.")
    return groszy, note.strip() if note else None


def money(groszy: int) -> str:
    # Safe for both positive totals and zero. No floating point.
    sign = "−" if groszy < 0 else ""
    groszy = abs(groszy)
    return f"{sign}{groszy // 100:,}".replace(",", " ") + f",{groszy % 100:02d} zł"
