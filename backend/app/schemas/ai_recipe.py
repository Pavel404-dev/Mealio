import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.recipe import RecipeCreate, RecipeIngredientCreate
from app.schemas.user_nutrition_profile import NutritionGoal

MAX_AI_PANTRY_ITEMS = 50
MAX_AI_INGREDIENT_MATCH_NAMES = 50
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
    quantity_g: Decimal = Field(..., gt=0, allow_inf_nan=False)

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )


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


class AIRecipeIngredientMatchSuggestionsRequest(BaseModel):
    ingredient_names: list[str] = Field(
        ...,
        min_length=1,
        max_length=MAX_AI_INGREDIENT_MATCH_NAMES,
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("ingredient_names")
    @classmethod
    def normalize_and_validate_ingredient_names(cls, values: list[str]) -> list[str]:
        normalized_names: list[str] = []
        normalized_keys: set[str] = set()

        for value in values:
            normalized_name = value.strip()

            if not normalized_name:
                raise ValueError("Ingredient names cannot contain blank values")

            if len(normalized_name) > 255:
                raise ValueError("Ingredient name is too long")

            normalized_key = normalized_name.casefold()

            if normalized_key in normalized_keys:
                raise ValueError("Ingredient names must be unique")

            normalized_names.append(normalized_name)
            normalized_keys.add(normalized_key)

        return normalized_names


class AIRecipeIngredientExactMatch(BaseModel):
    ingredient_id: uuid.UUID
    name: str
    category: str | None = None


class AIRecipeIngredientMatchSuggestion(BaseModel):
    generated_name: str
    exact_match: AIRecipeIngredientExactMatch | None


class AIRecipeIngredientMatchSuggestionsResponse(BaseModel):
    results: list[AIRecipeIngredientMatchSuggestion]


def format_recipe_instruction_steps(instructions: list[str]) -> str:
    return "\n".join(
        f"{step_number}. {instruction}"
        for step_number, instruction in enumerate(instructions, start=1)
    )


class AIRecipeSaveIngredient(RecipeIngredientCreate):
    model_config = ConfigDict(extra="forbid")


class AIRecipeSavePreviewRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    diet_type: str | None = Field(default=None, max_length=100)
    instructions: list[str] = Field(..., min_length=1, max_length=30)
    ingredients: list[AIRecipeSaveIngredient] = Field(
        ...,
        min_length=1,
        max_length=50,
    )

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
    def validate_unique_ingredients(self) -> "AIRecipeSavePreviewRequest":
        ingredient_ids = [item.ingredient_id for item in self.ingredients]

        if len(ingredient_ids) != len(set(ingredient_ids)):
            raise ValueError("Recipe cannot contain duplicate ingredients")

        return self

    def to_recipe_create(self) -> RecipeCreate:
        return RecipeCreate(
            title=self.title,
            description=self.description,
            diet_type=self.diet_type,
            instructions=format_recipe_instruction_steps(self.instructions),
            ingredients=[
                RecipeIngredientCreate(
                    ingredient_id=item.ingredient_id,
                    quantity_g=item.quantity_g,
                )
                for item in self.ingredients
            ],
        )


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
