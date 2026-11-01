"""Shared, context-independent scaling from stored nutrient portions."""

from collections.abc import Iterable
from decimal import (
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    ROUND_HALF_UP,
    localcontext,
)
from fractions import Fraction

from fastapi import HTTPException

from app.models.ingredient import NutritionValue

NUTRIENTS = ("calories", "protein_g", "carbs_g", "fat_g")
TOTALS = ("total_calories", "total_protein_g", "total_carbs_g", "total_fat_g")


def _scale_grams(value: Decimal, quantity: Decimal, portion: Decimal) -> Fraction:
    return Fraction(value) * Fraction(quantity) / Fraction(portion)


def _decimal_from_fraction(
    total: Fraction, *, precision: int, round_to_hundredths: bool
) -> Decimal:
    if round_to_hundredths:
        # Denominator digits bound distance from a rounding tie; numerator
        # digits cover the integer part, plus four guard digits. This also
        # supports read values without imposing nutrient/recipe storage bounds.
        precision = max(
            precision,
            Decimal(abs(total.numerator)).adjusted()
            + Decimal(total.denominator).adjusted()
            + 6,
        )
    context = Context(
        prec=precision,
        rounding=ROUND_HALF_UP,
        Emin=-999999,
        Emax=999999,
        capitals=1,
        clamp=0,
        flags=[],
        traps=[InvalidOperation, DivisionByZero, Overflow],
    )
    with localcontext(context):
        value = Decimal(total.numerator) / Decimal(total.denominator)
        if round_to_hundredths:
            value = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return value


def nutrient_per_100g(value: Decimal, portion_g: Decimal) -> Decimal:
    """Read projection only: exact scaling, final rounding, no storage bound."""
    return _decimal_from_fraction(
        _scale_grams(value, Decimal("100"), portion_g),
        precision=50,
        round_to_hundredths=True,
    )


def aggregate_grams(
    rows: Iterable[tuple[Decimal, NutritionValue | None]], *, recipe: bool
) -> dict[str, Decimal]:
    # Exact rational accumulation avoids rounding repeating contributions on
    # opposite sides of a half-cent tie. No nutrient basis is rewritten.
    sums = [Fraction(0) for _ in NUTRIENTS]
    count = 0
    for quantity, nutrition in rows:
        count += 1
        if nutrition is None or nutrition.portion_g <= 0:
            continue
        for index, field in enumerate(NUTRIENTS):
            sums[index] += _scale_grams(
                getattr(nutrition, field), quantity, nutrition.portion_g
            )

    result = {}
    for field, total in zip(TOTALS, sums, strict=True):
        # Pantry exposes 50 + digits(row count) significant decimal digits.
        value = _decimal_from_fraction(
            total, precision=50 + len(str(count)), round_to_hundredths=recipe
        )
        if recipe and (
            not value.is_finite() or not Decimal("0") <= value <= Decimal("99999999.99")
        ):
            raise HTTPException(
                status_code=422,
                detail="Recipe nutrition totals exceed storage bounds",
            )
        result[field] = value
    return result
