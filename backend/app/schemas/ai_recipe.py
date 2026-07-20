from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.user_nutrition_profile import NutritionGoal

MAX_AI_PANTRY_ITEMS = 50
MAX_AI_PROFILE_PREFERENCES = 25
MAX_AI_PROFILE_PREFERENCE_LENGTH = 100


class AIRecipeGenerationRequest(BaseModel):
    meal_type: str | None = Field(default=None, max_length=100)
    servings: int = Field(default=1, ge=1, le=12)
    max_prep_time_minutes: int | None = Field(default=None, ge=1, le=480)
    use_only_pantry: bool = False
    additional_preferences: str | None = Field(default=None, max_length=500)

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    @field_validator("meal_type", "additional_preferences")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value == "":
            return None

        return value


class GeneratedRecipeIngredient(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    quantity: str = Field(..., min_length=1, max_length=30)
    unit: str = Field(..., min_length=1, max_length=30)

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    @field_validator("quantity")
    @classmethod
    def validate_positive_quantity(cls, value: str) -> str:
        try:
            quantity = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("Ingredient quantity must be numeric") from exc

        if not quantity.is_finite() or quantity <= 0:
            raise ValueError("Ingredient quantity must be positive")

        return value


class GeneratedRecipeData(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    servings: int = Field(..., ge=1, le=12)
    prep_time_minutes: int = Field(..., ge=1, le=480)
    diet_type: str | None = Field(default=None, max_length=100)
    ingredients: list[GeneratedRecipeIngredient] = Field(
        ...,
        min_length=1,
        max_length=50,
    )
    instructions: list[str] = Field(..., min_length=1, max_length=30)

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    @field_validator("description", "diet_type")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value == "":
            return None

        return value

    @field_validator("instructions")
    @classmethod
    def validate_instructions(cls, values: list[str]) -> list[str]:
        normalized_values: list[str] = []

        for value in values:
            normalized_value = value.strip()

            if not normalized_value:
                raise ValueError("Recipe instructions cannot contain blank steps")

            if len(normalized_value) > 500:
                raise ValueError("Recipe instruction step is too long")

            normalized_values.append(normalized_value)

        return normalized_values

    @model_validator(mode="after")
    def validate_unique_ingredients(self) -> "GeneratedRecipeData":
        normalized_names = [item.name.casefold() for item in self.ingredients]

        if len(normalized_names) != len(set(normalized_names)):
            raise ValueError("Generated recipe cannot contain duplicate ingredients")

        return self


class AIRecipePantryItemContext(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    available_quantity_g: Decimal = Field(..., gt=0)
    unit: Literal["g"] = "g"

    model_config = ConfigDict(extra="forbid")


class AIRecipeNutritionProfileContext(BaseModel):
    goal: NutritionGoal
    diet_type: str | None = Field(default=None, max_length=100)
    allergies: list[str] = Field(
        default_factory=list,
        max_length=MAX_AI_PROFILE_PREFERENCES,
    )
    disliked_ingredients: list[str] = Field(
        default_factory=list,
        max_length=MAX_AI_PROFILE_PREFERENCES,
    )
    preferred_meals_per_day: int = Field(..., ge=1, le=8)
    calories_target_per_meal: Decimal | None = Field(default=None, gt=0)
    protein_target_per_meal_g: Decimal | None = Field(default=None, gt=0)
    carbs_target_per_meal_g: Decimal | None = Field(default=None, gt=0)
    fat_target_per_meal_g: Decimal | None = Field(default=None, gt=0)

    model_config = ConfigDict(extra="forbid")

    @field_validator("allergies", "disliked_ingredients")
    @classmethod
    def validate_preference_lengths(cls, values: list[str]) -> list[str]:
        if any(len(value) > MAX_AI_PROFILE_PREFERENCE_LENGTH for value in values):
            raise ValueError("Nutrition preference is too long for AI generation")

        return values


class AIRecipeGenerationContext(BaseModel):
    request: AIRecipeGenerationRequest
    pantry_items: list[AIRecipePantryItemContext] = Field(
        max_length=MAX_AI_PANTRY_ITEMS,
    )
    nutrition_profile: AIRecipeNutritionProfileContext

    model_config = ConfigDict(extra="forbid")


class AIRecipeProviderRequest(BaseModel):
    instructions: str = Field(..., min_length=1, max_length=4000)
    input: str = Field(..., min_length=1, max_length=30000)
    context: AIRecipeGenerationContext

    model_config = ConfigDict(extra="forbid")
