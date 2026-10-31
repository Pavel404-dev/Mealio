"""Write-only exact NUMERIC inputs; never round a raw value into validity."""

from decimal import Decimal, InvalidOperation
from typing import Annotated

from pydantic import BeforeValidator, Field


def exact_hundredths(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (Decimal, str, int, float)):
        raise ValueError("Expected a finite decimal number")
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Expected a finite decimal number") from exc
    if not number.is_finite():
        raise ValueError("Expected a finite decimal number")
    _, digits, exponent = number.as_tuple()
    extra_places = -exponent - 2
    if extra_places > 0 and any(digits[-extra_places:]):
        raise ValueError("Value must be exactly representable with two decimal places")
    # Canonicalize only redundant zeros, exactly and without Decimal context.
    # In particular, 0E+999999999 is zero, but its raw exponent cannot be sent
    # unchanged to PostgreSQL's numeric parser.
    if not number:
        return Decimal(0)
    end = len(digits)
    while end > 1 and digits[end - 1] == 0:
        end -= 1
    return Decimal((number.as_tuple().sign, digits[:end], exponent + len(digits) - end))


NutrientWrite = Annotated[
    Decimal,
    Field(ge=Decimal("0"), le=Decimal("999999.99"), allow_inf_nan=False),
    BeforeValidator(exact_hundredths),
]
QuantityWrite = Annotated[
    Decimal,
    Field(ge=Decimal("0.01"), le=Decimal("99999999.99"), allow_inf_nan=False),
    BeforeValidator(exact_hundredths),
]
