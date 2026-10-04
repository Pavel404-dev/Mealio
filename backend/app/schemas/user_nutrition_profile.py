import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

NutritionGoal = Literal["lose_weight", "maintain", "gain_weight"]
NutritionSex = Literal["male", "female"]
ActivityLevel = Literal[
    "sedentary", "lightly_active", "moderately_active", "very_active", "extra_active"
]
POSTGRES_INTEGER_MAX = 2_147_483_647


def utc_today() -> date:
    return datetime.now(UTC).date()


class UserNutritionProfileBase(BaseModel):
    goal: NutritionGoal = "maintain"
    diet_type: str | None = Field(default="balanced", max_length=100)
    daily_calories_target: int | None = Field(
        default=None, gt=0, le=POSTGRES_INTEGER_MAX
    )
    daily_protein_target_g: int | None = Field(
        default=None, gt=0, le=POSTGRES_INTEGER_MAX
    )
    daily_carbs_target_g: int | None = Field(
        default=None, gt=0, le=POSTGRES_INTEGER_MAX
    )
    daily_fat_target_g: int | None = Field(default=None, gt=0, le=POSTGRES_INTEGER_MAX)
    allergies: list[str] = Field(default_factory=list)
    disliked_ingredients: list[str] = Field(default_factory=list)
    preferred_meals_per_day: int | None = Field(default=3, ge=1, le=8)
    sex: NutritionSex | None = None
    birth_date: date | None = Field(default=None, ge=date(1900, 1, 1))
    height_cm: Decimal | None = Field(
        default=None,
        ge=Decimal("50.0"),
        le=Decimal("250.0"),
        max_digits=4,
        decimal_places=1,
        allow_inf_nan=False,
    )
    weight_kg: Decimal | None = Field(
        default=None,
        ge=Decimal("10.00"),
        le=Decimal("500.00"),
        max_digits=5,
        decimal_places=2,
        allow_inf_nan=False,
    )
    activity_level: ActivityLevel | None = None
    max_cooking_time_minutes: int | None = Field(
        default=None, ge=1, le=480, strict=True
    )
    weekly_food_budget_amount: Decimal | None = Field(
        default=None,
        ge=Decimal("0.01"),
        le=Decimal("1000000.00"),
        max_digits=9,
        decimal_places=2,
        allow_inf_nan=False,
    )
    budget_currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        pattern=r"^[A-Z]{3}$",
    )

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    @field_validator("diet_type")
    @classmethod
    def normalize_diet_type(cls, value: str | None) -> str | None:
        if value == "":
            return None

        return value

    @field_validator("allergies", "disliked_ingredients")
    @classmethod
    def normalize_string_list(cls, values: list[str]) -> list[str]:
        normalized_values: list[str] = []

        for value in values:
            normalized_value = value.strip()

            if normalized_value:
                normalized_values.append(normalized_value)

        return normalized_values


class UserNutritionProfileWrite(UserNutritionProfileBase):
    @field_validator("birth_date", mode="before")
    @classmethod
    def validate_birth_date_format(cls, value):
        if value is None or type(value) is date:
            return value
        if not isinstance(value, str) or not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value
        ):
            raise ValueError("Birth date must use YYYY-MM-DD")
        return value

    @field_validator("birth_date")
    @classmethod
    def validate_birth_date_not_future(cls, value: date | None) -> date | None:
        if value is not None and value > utc_today():
            raise ValueError("Birth date cannot be in the future (UTC)")
        return value

    @field_validator(
        "height_cm", "weight_kg", "weekly_food_budget_amount", mode="before"
    )
    @classmethod
    def validate_decimal_input(cls, value, info: ValidationInfo):
        if value is None:
            return value
        if isinstance(value, bool):
            raise ValueError("Boolean is not a decimal value")
        try:
            decimal_value = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise ValueError("Invalid decimal value") from None
        if not decimal_value.is_finite():
            raise ValueError("Decimal value must be finite")
        places = 1 if info.field_name == "height_cm" else 2
        if decimal_value.as_tuple().exponent < -places:
            raise ValueError(f"At most {places} decimal places are allowed")
        return decimal_value

    @field_validator("budget_currency", mode="before")
    @classmethod
    def normalize_budget_currency(cls, value):
        if value is None:
            return value
        if not isinstance(value, str):
            raise ValueError("Currency must contain three ASCII letters")
        trimmed_value = value.strip()
        if not trimmed_value.isascii():
            raise ValueError("Currency must contain three ASCII letters")
        return trimmed_value.upper()


class UserNutritionProfileCreate(UserNutritionProfileWrite):
    pass


class UserNutritionProfileUpdate(UserNutritionProfileWrite):
    pass


class UserNutritionProfileRead(UserNutritionProfileBase):
    model_config = ConfigDict(
        from_attributes=True,
        str_strip_whitespace=True,
    )

    @classmethod
    def default(cls) -> "UserNutritionProfileRead":
        return cls()
