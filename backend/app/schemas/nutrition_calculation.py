"""Immutable W5 inputs and public outcomes; independent of W4 write validation."""

import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.schemas.user_nutrition_profile import (
    ActivityLevel,
    NutritionGoal,
    NutritionSex,
)

RULES_VERSION = "mealio-nutrition-v1"
RulesVersion = Literal["mealio-nutrition-v1"]
InputField = Literal[
    "sex", "birth_date", "height_cm", "weight_kg", "activity_level", "goal"
]
UnsupportedReason = Literal[
    "birth_date_after_calculation_date",
    "age_out_of_range",
    "height_out_of_range",
    "weight_out_of_range",
    "bmi_out_of_range",
    "nonpositive_energy",
    "calories_out_of_range",
]


class ImmutableModel(BaseModel):
    model_config = ConfigDict(
        frozen=True, extra="forbid", strict=True, revalidate_instances="always"
    )


class NutritionCalculationRequest(ImmutableModel):
    calculation_date: date
    rules_version: RulesVersion = RULES_VERSION

    @field_validator("calculation_date", mode="before")
    @classmethod
    def validate_date(cls, value):
        if type(value) is date:
            return value
        if isinstance(value, str) and re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value
        ):
            try:
                return date.fromisoformat(value)
            except ValueError:
                pass
        raise ValueError("Calculation date must use YYYY-MM-DD")


class NutritionCalculationInput(ImmutableModel):
    # Internal snapshots accept native dates and Decimal only. Nulls are domain
    # incompleteness; well-typed values outside the envelope are unsupported.
    sex: NutritionSex | None = None
    birth_date: date | None = None
    height_cm: Decimal | None = None
    weight_kg: Decimal | None = None
    activity_level: ActivityLevel | None = None
    goal: NutritionGoal | None = None

    @field_validator("birth_date", mode="before")
    @classmethod
    def validate_birth_date(cls, value):
        if value is not None and type(value) is not date:
            raise ValueError("Birth date must be a native date")
        return value

    @field_validator("height_cm", "weight_kg", mode="before")
    @classmethod
    def validate_decimal(cls, value, info: ValidationInfo):
        if value is None:
            return value
        if type(value) is not Decimal or not value.is_finite():
            raise ValueError("Snapshot measurements must be finite Decimal values")
        places = 1 if info.field_name == "height_cm" else 2
        if value.as_tuple().exponent < -places:
            raise ValueError("Snapshot measurement has excess decimal places")
        return value


class NutritionUsedInputs(NutritionCalculationInput):
    sex: NutritionSex
    birth_date: date
    height_cm: Decimal
    weight_kg: Decimal
    activity_level: ActivityLevel
    goal: NutritionGoal


class NutritionCalculationResult(ImmutableModel):
    age_years: int = Field(ge=19, le=78)
    used_inputs: NutritionUsedInputs
    activity_factor: Decimal = Field(gt=0, allow_inf_nan=False)
    goal_factor: Decimal = Field(gt=0, allow_inf_nan=False)
    ree_kcal: Decimal = Field(gt=0, allow_inf_nan=False)
    tdee_kcal: Decimal = Field(gt=0, allow_inf_nan=False)
    calories_target_kcal: int = Field(ge=1000, le=6000)
    protein_target_g: int = Field(gt=0)
    fat_target_g: int = Field(gt=0)
    carbs_target_g: int = Field(gt=0)
    energy_delta_kcal: int = Field(ge=-2, le=2)


class CalculationOutcomeBase(ImmutableModel):
    rules_version: RulesVersion = RULES_VERSION
    calculation_date: date


class CalculatedNutrition(CalculationOutcomeBase):
    status: Literal["calculated"] = "calculated"
    result: NutritionCalculationResult


class IncompleteNutritionProfile(CalculationOutcomeBase):
    status: Literal["incomplete_profile"] = "incomplete_profile"
    missing_fields: tuple[InputField, ...]
    result: None = None


class UnsupportedNutritionProfile(CalculationOutcomeBase):
    status: Literal["unsupported_profile"] = "unsupported_profile"
    reason_codes: tuple[UnsupportedReason, ...]
    result: None = None


NutritionCalculationOutcome = Annotated[
    CalculatedNutrition | IncompleteNutritionProfile | UnsupportedNutritionProfile,
    Field(discriminator="status"),
]
