import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.shopping_list import ShoppingListItemRead

NutritionGapStatus = Literal["under", "met", "over", "unknown"]
NutritionGapsOverallStatus = Literal[
    "unknown",
    "needs_attention",
    "over_target",
    "on_track",
]


class MealPlanItemBase(BaseModel):
    recipe_id: uuid.UUID
    planned_date: date
    meal_type: str = Field(..., min_length=1, max_length=50)

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("meal_type", mode="before")
    @classmethod
    def reject_null_meal_type(cls, value):
        if value is None:
            raise ValueError("Meal type cannot be null")
        return value

    @field_validator("meal_type")
    @classmethod
    def validate_meal_type(cls, value: str) -> str:
        if value == "":
            raise ValueError("Meal type cannot be empty")
        return value


class MealPlanItemCreate(MealPlanItemBase):
    pass


class MealPlanItemUpdate(BaseModel):
    recipe_id: uuid.UUID | None = None
    planned_date: date | None = None
    meal_type: str | None = Field(default=None, min_length=1, max_length=50)

    model_config = ConfigDict(str_strip_whitespace=True)

    @model_validator(mode="before")
    @classmethod
    def reject_null_fields(cls, data):
        if not isinstance(data, dict):
            return data

        if "recipe_id" in data and data["recipe_id"] is None:
            raise ValueError("Recipe id cannot be null")

        if "planned_date" in data and data["planned_date"] is None:
            raise ValueError("Planned date cannot be null")

        if "meal_type" in data and data["meal_type"] is None:
            raise ValueError("Meal type cannot be null")

        return data

    @field_validator("meal_type")
    @classmethod
    def validate_meal_type(cls, value: str | None) -> str | None:
        if value == "":
            raise ValueError("Meal type cannot be empty")
        return value


class MealPlanItemRead(MealPlanItemBase):
    id: uuid.UUID
    meal_plan_id: uuid.UUID

    model_config = ConfigDict(from_attributes=True)


class MealPlanItemCalendarRead(BaseModel):
    id: uuid.UUID
    meal_plan_id: uuid.UUID
    meal_plan_title: str
    recipe_id: uuid.UUID
    recipe_title: str
    planned_date: date
    meal_type: str


class MealPlanNutritionProgressDayRead(BaseModel):
    date: date

    total_calories: Decimal = Field(..., ge=0)
    daily_calories_target: int | None = Field(default=None, gt=0)
    remaining_calories: Decimal | None = None
    calories_percent: Decimal | None = Field(default=None, ge=0)

    total_protein_g: Decimal = Field(..., ge=0)
    daily_protein_target_g: int | None = Field(default=None, gt=0)
    remaining_protein_g: Decimal | None = None
    protein_percent: Decimal | None = Field(default=None, ge=0)

    total_carbs_g: Decimal = Field(..., ge=0)
    daily_carbs_target_g: int | None = Field(default=None, gt=0)
    remaining_carbs_g: Decimal | None = None
    carbs_percent: Decimal | None = Field(default=None, ge=0)

    total_fat_g: Decimal = Field(..., ge=0)
    daily_fat_target_g: int | None = Field(default=None, gt=0)
    remaining_fat_g: Decimal | None = None
    fat_percent: Decimal | None = Field(default=None, ge=0)


class MealPlanNutritionGapsDayRead(BaseModel):
    date: date

    total_calories: Decimal = Field(..., ge=0)
    daily_calories_target: int | None = Field(default=None, gt=0)
    calories_gap: Decimal | None = None
    calories_status: NutritionGapStatus

    total_protein_g: Decimal = Field(..., ge=0)
    daily_protein_target_g: int | None = Field(default=None, gt=0)
    protein_gap_g: Decimal | None = None
    protein_status: NutritionGapStatus

    total_carbs_g: Decimal = Field(..., ge=0)
    daily_carbs_target_g: int | None = Field(default=None, gt=0)
    carbs_gap_g: Decimal | None = None
    carbs_status: NutritionGapStatus

    total_fat_g: Decimal = Field(..., ge=0)
    daily_fat_target_g: int | None = Field(default=None, gt=0)
    fat_gap_g: Decimal | None = None
    fat_status: NutritionGapStatus

    overall_status: NutritionGapsOverallStatus
    missing_targets: list[str] = Field(default_factory=list)


MealPlanShoppingListItemRead = ShoppingListItemRead


class MealPlanBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    start_date: date
    end_date: date | None = None

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("title", mode="before")
    @classmethod
    def reject_null_title(cls, value):
        if value is None:
            raise ValueError("Meal plan title cannot be null")
        return value

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        if value == "":
            raise ValueError("Meal plan title cannot be empty")
        return value

    @model_validator(mode="after")
    def validate_date_range(self) -> "MealPlanBase":
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("End date cannot be earlier than start date")

        return self


class MealPlanCreate(MealPlanBase):
    items: list[MealPlanItemCreate] = Field(default_factory=list)


class MealPlanUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    start_date: date | None = None
    end_date: date | None = None

    model_config = ConfigDict(str_strip_whitespace=True)

    @model_validator(mode="before")
    @classmethod
    def reject_null_fields(cls, data):
        if not isinstance(data, dict):
            return data

        if "title" in data and data["title"] is None:
            raise ValueError("Meal plan title cannot be null")

        if "start_date" in data and data["start_date"] is None:
            raise ValueError("Start date cannot be null")

        return data

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        if value == "":
            raise ValueError("Meal plan title cannot be empty")
        return value


class MealPlanRead(MealPlanBase):
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    items: list[MealPlanItemRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
