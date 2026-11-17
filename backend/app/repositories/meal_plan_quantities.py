"""Exact portion-weighted SQL aggregates, rounded once per returned group."""

from decimal import Decimal

from sqlalchemy import Numeric, case, func
from sqlalchemy.sql.elements import ColumnElement

from app.models.meal_plan import MealPlanItem
from app.models.recipe import Recipe

# Recipe.servings is constrained to integers 1..12. Their LCM lets us sum
# exact numerators, including thirds/sevenths, without intermediate division.
SERVINGS_DENOMINATOR = 27720


def planned_quantity_sum(amount: ColumnElement) -> ColumnElement:
    units = case(
        (MealPlanItem.planned_servings.is_(None), SERVINGS_DENOMINATOR),
        else_=MealPlanItem.planned_servings
        * func.div(SERVINGS_DENOMINATOR, Recipe.servings, type_=Numeric()),
    )
    numerator = func.coalesce(func.sum(func.coalesce(amount, 0) * units), 0)
    # Exact ROUND_HALF_UP to hundredths, including finite signed legacy totals.
    # div() truncates an exact NUMERIC quotient; no repeating fraction is rounded
    # before the half-cent decision. Each caller must join Recipe and MealPlanItem.
    return (
        func.sign(numerator)
        * func.div(
            func.abs(numerator) * 100 + SERVINGS_DENOMINATOR // 2,
            SERVINGS_DENOMINATOR,
            type_=Numeric(),
        )
        * Decimal("0.01")
    )
