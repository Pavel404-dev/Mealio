import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NutritionValueBase(BaseModel):
    calories: Decimal = Field(..., ge=0)
    protein_g: Decimal = Field(default=Decimal("0"), ge=0)
    carbs_g: Decimal = Field(default=Decimal("0"), ge=0)
    fat_g: Decimal = Field(default=Decimal("0"), ge=0)
    portion_g: Decimal = Field(default=Decimal("100"), gt=0)


class NutritionValueCreate(NutritionValueBase):
    pass


class NutritionValueRead(NutritionValueBase):
    id: uuid.UUID
    ingredient_id: uuid.UUID

    model_config = ConfigDict(from_attributes=True)


class IngredientBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    category: str | None = Field(default=None, max_length=100)

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value:
            raise ValueError("Ingredient name cannot be empty")
        return value

    @field_validator("category")
    @classmethod
    def normalize_category(cls, value: str | None) -> str | None:
        if value == "":
            return None
        return value


class IngredientCreate(IngredientBase):
    nutrition_value: NutritionValueCreate | None = None


class IngredientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, max_length=100)
    nutrition_value: NutritionValueCreate | None = None

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value == "":
            raise ValueError("Ingredient name cannot be empty")
        return value

    @field_validator("category")
    @classmethod
    def normalize_category(cls, value: str | None) -> str | None:
        if value == "":
            return None
        return value


class IngredientRead(IngredientBase):
    id: uuid.UUID
    created_at: datetime
    nutrition_value: NutritionValueRead | None = None

    model_config = ConfigDict(from_attributes=True)
