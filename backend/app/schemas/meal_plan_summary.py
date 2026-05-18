import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class MealPlanNutritionSummaryRead(BaseModel):
    meal_plan_id: uuid.UUID
    items_count: int
    total_calories: Decimal
    total_protein: Decimal
    total_carbs: Decimal
    total_fat: Decimal

    model_config = ConfigDict(from_attributes=True)