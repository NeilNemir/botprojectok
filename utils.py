"""
Utility functions with simple, well-tested business logic.

Functions:
- calculate_discount(amount, percent) -> float: apply percent discount to amount, returns value rounded to 2 decimals.
- safe_divide(a, b, precision=6) -> float: divide a by b with rounding and validation.
- fmt_amount(value, digits=2, sep=",", dot=".") -> str: format number with thousands separator and decimal dot.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Union

Number = Union[int, float, Decimal]


def _to_decimal(value: Number) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise TypeError("Value must be a number or Decimal")


def calculate_discount(amount: Number, percent: Number) -> float:
    """Apply discount percent to amount and return the final price rounded to 2 decimals.

    Rules:
    - amount must be >= 0
    - percent must be in [0, 100]
    - result is rounded using bankers-friendly HALF_UP mode to 2 decimals
    """
    amt = _to_decimal(amount)
    pct = _to_decimal(percent)

    if amt < 0:
        raise ValueError("amount must be non-negative")
    if pct < 0 or pct > 100:
        raise ValueError("percent must be in range [0, 100]")

    factor = (Decimal("100") - pct) / Decimal("100")
    result = (amt * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(result)


def safe_divide(a: Number, b: Number, precision: int = 6) -> float:
    """Divide a by b with validation and rounding.

    - Raises ZeroDivisionError if b == 0
    - Raises TypeError for non-numeric inputs
    - precision must be in [0, 12]
    """
    if not isinstance(precision, int) or precision < 0 or precision > 12:
        raise ValueError("precision must be int in range [0, 12]")

    da = _to_decimal(a)
    db = _to_decimal(b)
    if db == 0:
        raise ZeroDivisionError("division by zero")

    quant = Decimal("1").scaleb(-precision) if precision > 0 else Decimal("1")
    result = (da / db).quantize(quant, rounding=ROUND_HALF_UP)
    return float(result)


def fmt_amount(value: Number, digits: int = 2, sep: str = ",", dot: str = ".") -> str:
    """Format numeric value with thousands separator and fixed number of decimal digits.

    Ensures trailing zeros are kept according to `digits`.
    Example: fmt_amount(1234.5, 2) -> "1,234.50"
    Custom separators supported via `sep` (thousands) and `dot` (decimal).
    """
    if not isinstance(digits, int) or digits < 0 or digits > 8:
        raise ValueError("digits must be int in range [0, 8]")
    dval = _to_decimal(value)
    # Quantize to requested digits
    quant = Decimal("1").scaleb(-digits) if digits > 0 else Decimal("1")
    dval = dval.quantize(quant, rounding=ROUND_HALF_UP)
    # Use format spec to keep trailing zeros
    base = f"{dval:,.{digits}f}" if digits > 0 else f"{int(dval):,}"
    if sep != "," or dot != ".":
        base = base.replace(",", "§").replace(".", dot).replace("§", sep)
    return base


__all__ = ["calculate_discount", "safe_divide", "fmt_amount"]
