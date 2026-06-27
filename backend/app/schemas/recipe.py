import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


@dataclass(frozen=True)
class RecipeNutritionTotals:
    total_calories: Decimal
    total_protein_g: Decimal
    total_carbs_g: Decimal
    total_fat_g: Decimal


class RecipeIngredientBase(BaseModel):
    ingredient_id: uuid.UUID
    quantity_g: Decimal = Field(..., gt=0)


class RecipeIngredientCreate(RecipeIngredientBase):
    pass


class RecipeIngredientRead(RecipeIngredientBase):
    id: uuid.UUID
    recipe_id: uuid.UUID

    model_config = ConfigDict(from_attributes=True)


class RecipeBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    instructions: str = Field(..., min_length=1)
    diet_type: str | None = Field(default=None, max_length=100)

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("title", "instructions", mode="before")
    @classmethod
    def reject_null_required_fields(cls, value):
        if value is None:
            raise ValueError("Field cannot be null")
        return value

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        if value == "":
            raise ValueError("Recipe title cannot be empty")
        return value

    @field_validator("instructions")
    @classmethod
    def validate_instructions(cls, value: str | None) -> str | None:
        if value == "":
            raise ValueError("Recipe instructions cannot be empty")
        return value


class RecipeCreate(RecipeBase):
    ingredients: list[RecipeIngredientCreate] = Field(default_factory=list)

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @model_validator(mode="after")
    def validate_unique_ingredients(self) -> "RecipeCreate":
        ingredient_ids = [item.ingredient_id for item in self.ingredients]

        if len(ingredient_ids) != len(set(ingredient_ids)):
            raise ValueError("Recipe cannot contain duplicate ingredients")

        return self


class RecipeUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    instructions: str | None = Field(default=None, min_length=1)
    diet_type: str | None = Field(default=None, max_length=100)
    ingredients: list[RecipeIngredientCreate] | None = None

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def reject_null_required_fields(cls, data):
        if not isinstance(data, dict):
            return data

        if "title" in data and data["title"] is None:
            raise ValueError("Recipe title cannot be null")

        if "instructions" in data and data["instructions"] is None:
            raise ValueError("Recipe instructions cannot be null")

        return data

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        if value == "":
            raise ValueError("Recipe title cannot be empty")
        return value

    @field_validator("instructions")
    @classmethod
    def validate_instructions(cls, value: str | None) -> str | None:
        if value == "":
            raise ValueError("Recipe instructions cannot be empty")
        return value

    @field_validator("description", "diet_type")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value == "":
            return None
        return value

    @model_validator(mode="after")
    def validate_unique_ingredients(self) -> "RecipeUpdate":
        if self.ingredients is None:
            return self

        ingredient_ids = [item.ingredient_id for item in self.ingredients]

        if len(ingredient_ids) != len(set(ingredient_ids)):
            raise ValueError("Recipe cannot contain duplicate ingredients")

        return self


class RecipeRead(RecipeBase):
    id: uuid.UUID
    created_by_user_id: uuid.UUID | None
    total_calories: Decimal | None = Field(default=None, ge=0)
    total_protein_g: Decimal | None = Field(default=None, ge=0)
    total_carbs_g: Decimal | None = Field(default=None, ge=0)
    total_fat_g: Decimal | None = Field(default=None, ge=0)
    created_at: datetime
    updated_at: datetime
    recipe_ingredients: list[RecipeIngredientRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class RecipePantrySuggestionMissingIngredientRead(BaseModel):
    ingredient_id: uuid.UUID
    ingredient_name: str
    required_quantity_g: Decimal = Field(..., ge=0)
    pantry_quantity_g: Decimal = Field(..., ge=0)
    missing_quantity_g: Decimal = Field(..., ge=0)


class RecipePantrySuggestionRead(BaseModel):
    recipe_id: uuid.UUID
    recipe_title: str
    diet_type: str | None = None
    total_calories: Decimal | None = Field(default=None, ge=0)
    match_percent: Decimal = Field(..., ge=0, le=100)
    matched_ingredients_count: int = Field(..., ge=0)
    missing_ingredients_count: int = Field(..., ge=0)
    total_ingredients_count: int = Field(..., ge=0)
    missing_ingredients: list[RecipePantrySuggestionMissingIngredientRead] = Field(
        default_factory=list
    )