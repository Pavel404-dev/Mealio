import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class MealPlanNutritionSummaryRead(BaseModel):
    meal_plan_id: uuid.UUID
    items_count: int
    total_calories: Decimal
    total_protein_g: Decimal
    total_carbs_g: Decimal
    total_fat_g: Decimal

    model_config = ConfigDict(from_attributes=True)