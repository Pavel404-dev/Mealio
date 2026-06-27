from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

NutritionGoal = Literal["lose_weight", "maintain", "gain_weight"]


class UserNutritionProfileBase(BaseModel):
    goal: NutritionGoal = "maintain"
    diet_type: str | None = Field(default="balanced", max_length=100)
    daily_calories_target: int | None = Field(default=None, gt=0)
    daily_protein_target_g: int | None = Field(default=None, gt=0)
    daily_carbs_target_g: int | None = Field(default=None, gt=0)
    daily_fat_target_g: int | None = Field(default=None, gt=0)
    allergies: list[str] = Field(default_factory=list)
    disliked_ingredients: list[str] = Field(default_factory=list)
    preferred_meals_per_day: int | None = Field(default=3, ge=1, le=8)

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


class UserNutritionProfileCreate(UserNutritionProfileBase):
    pass


class UserNutritionProfileUpdate(UserNutritionProfileBase):
    pass


class UserNutritionProfileRead(UserNutritionProfileBase):
    model_config = ConfigDict(
        from_attributes=True,
        str_strip_whitespace=True,
    )

    @classmethod
    def default(cls) -> "UserNutritionProfileRead":
        return cls()
