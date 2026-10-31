import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.ingredient_text import trim_ingredient_name
from app.schemas.storage_decimal import NutrientWrite


class NutritionValueBase(BaseModel):
    calories: Decimal = Field(..., ge=0)
    protein_g: Decimal = Field(default=Decimal("0"), ge=0)
    carbs_g: Decimal = Field(default=Decimal("0"), ge=0)
    fat_g: Decimal = Field(default=Decimal("0"), ge=0)
    portion_g: Decimal = Field(
        default=Decimal("100"),
        ge=Decimal("0.01"),
        le=Decimal("999999.99"),
        max_digits=8,
        decimal_places=2,
        allow_inf_nan=False,
    )

    @field_validator("portion_g")
    @classmethod
    def validate_exact_portion(cls, value: Decimal) -> Decimal:
        # Inspect digits without normalize()/quantize(): Decimal context rounding
        # must not erase a significant digit beyond the database's scale.
        _, digits, exponent = value.as_tuple()
        extra_places = -exponent - 2
        if extra_places > 0 and any(digits[-extra_places:]):
            raise ValueError(
                "Portion must be exactly representable with two decimal places"
            )
        return value


class NutritionValueCreate(NutritionValueBase):
    calories: NutrientWrite
    protein_g: NutrientWrite = Decimal("0")
    carbs_g: NutrientWrite = Decimal("0")
    fat_g: NutrientWrite = Decimal("0")


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

    _trim_name = field_validator("name", mode="before")(trim_ingredient_name)


class IngredientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, max_length=100)
    nutrition_value: NutritionValueCreate | None = None

    model_config = ConfigDict(str_strip_whitespace=True)

    _trim_name = field_validator("name", mode="before")(trim_ingredient_name)

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
