"""Canonical writes opt in through v2; v1 and stored legacy labels stay valid."""

from typing import Annotated, Literal

from pydantic import BeforeValidator, ConfigDict, Field

from app.schemas.meal_plan import (
    MealPlanCreate,
    MealPlanItemCreate,
    MealPlanItemUpdate,
)


def normalize_canonical_meal_type(value: object) -> object:
    if isinstance(value, str):
        return value.strip().lower()
    return value


CanonicalMealType = Annotated[
    Literal["breakfast", "lunch", "dinner", "snack"],
    BeforeValidator(normalize_canonical_meal_type),
]


class MealPlanItemV2Create(MealPlanItemCreate):
    meal_type: CanonicalMealType

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class MealPlanItemV2Update(MealPlanItemUpdate):
    # The inherited validator rejects explicit null; omission preserves legacy data.
    meal_type: CanonicalMealType | None = None

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class MealPlanV2Create(MealPlanCreate):
    items: list[MealPlanItemV2Create] = Field(default_factory=list)

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
