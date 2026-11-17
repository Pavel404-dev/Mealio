"""Canonical slots and optional portions; v1 and legacy labels stay valid."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BeforeValidator, ConfigDict, Field

from app.schemas.meal_plan import (
    MealPlanCreate,
    MealPlanItemCreate,
    MealPlanItemRead,
    MealPlanItemUpdate,
    MealPlanRead,
)
from app.schemas.storage_decimal import exact_hundredths


def normalize_canonical_meal_type(value: object) -> object:
    if isinstance(value, str):
        return value.strip().lower()
    return value


CanonicalMealType = Annotated[
    Literal["breakfast", "lunch", "dinner", "snack"],
    BeforeValidator(normalize_canonical_meal_type),
]

PlannedServings = Annotated[
    Decimal,
    Field(ge=Decimal("0.01"), le=Decimal("12"), allow_inf_nan=False),
    BeforeValidator(exact_hundredths),
]


class MealPlanItemV2Create(MealPlanItemCreate):
    meal_type: CanonicalMealType
    planned_servings: PlannedServings | None = None

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class MealPlanItemV2Update(MealPlanItemUpdate):
    # The inherited validator rejects explicit null; omission preserves legacy data.
    meal_type: CanonicalMealType | None = None
    # Omitted preserves the count; explicit null restores whole-recipe mode.
    planned_servings: PlannedServings | None = None

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class MealPlanV2Create(MealPlanCreate):
    items: list[MealPlanItemV2Create] = Field(default_factory=list)

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class MealPlanItemV2Read(MealPlanItemRead):
    planned_servings: PlannedServings | None


class MealPlanV2Read(MealPlanRead):
    items: list[MealPlanItemV2Read] = Field(default_factory=list)
