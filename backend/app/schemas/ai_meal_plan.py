"""Inputs, constrained model output and the server-calculated preview."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.meal_plan_v2 import CanonicalMealType, MealSlot, PlannedServings
from app.schemas.recipe import RecipeNutritionTotals

MAX_PLAN_CANDIDATES = 50
MAX_PLAN_SLOTS = 4


class AIMealPlanPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planned_date: date
    locale: Literal["en", "ru", "uk", "sk"]
    meal_types: list[CanonicalMealType] = Field(min_length=1, max_length=MAX_PLAN_SLOTS)

    @field_validator("meal_types")
    @classmethod
    def unique_slots(cls, slots: list[MealSlot]) -> list[MealSlot]:
        if len(set(slots)) != len(slots):
            raise ValueError("Meal slots must be distinct")
        return slots


class GeneratedMealSlot(BaseModel):
    model_config = ConfigDict(extra="forbid", revalidate_instances="always")

    meal_type: MealSlot
    candidate_number: Annotated[int, Field(strict=True, ge=1, le=MAX_PLAN_CANDIDATES)]
    # Integer hundredths keep the provider schema unambiguous, including ties.
    serving_hundredths: Annotated[int, Field(strict=True, ge=1, le=1200)]


class GeneratedMealPlanSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", revalidate_instances="always")

    items: list[GeneratedMealSlot] = Field(min_length=1, max_length=MAX_PLAN_SLOTS)


class AIMealPlanPreviewItem(BaseModel):
    recipe_id: uuid.UUID
    planned_date: date
    meal_type: MealSlot
    planned_servings: PlannedServings


class AIMealPlanTargetFitMetric(BaseModel):
    target: int | None
    actual: Decimal
    delta: Decimal | None
    delta_percent: Decimal | None
    within_tolerance: bool | None


class AIMealPlanTargetFitMetrics(BaseModel):
    total_calories: AIMealPlanTargetFitMetric
    total_protein_g: AIMealPlanTargetFitMetric
    total_carbs_g: AIMealPlanTargetFitMetric
    total_fat_g: AIMealPlanTargetFitMetric


class AIMealPlanTargetFit(BaseModel):
    status: Literal["within_tolerance", "outside_tolerance", "not_evaluated"]
    reason: Literal["no_targets", "unknown_meal_count", "partial_day"] | None
    tolerance_percent: Literal[10] = 10
    metrics: AIMealPlanTargetFitMetrics


class AIMealPlanPreview(BaseModel):
    items: list[AIMealPlanPreviewItem]
    nutrition: RecipeNutritionTotals
    target_fit: AIMealPlanTargetFit
