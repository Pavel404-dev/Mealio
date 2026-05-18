import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.meal_plan_summary import (
    MealPlanDailyNutritionSummaryRead,
    MealPlanNutritionSummaryRead,
)
from app.services.meal_plan_summaries import MealPlanSummariesService


router = APIRouter(
    prefix="/users/{user_id}/meal-plans/{meal_plan_id}",
    tags=["Meal Plans"],
)


@router.get("/summary", response_model=MealPlanNutritionSummaryRead)
async def get_meal_plan_nutrition_summary(
        user_id: uuid.UUID,
        meal_plan_id: uuid.UUID,
        db: AsyncSession = Depends(get_db),
):
    service = MealPlanSummariesService(db)

    return await service.get_meal_plan_nutrition_summary(
        user_id=user_id,
        meal_plan_id=meal_plan_id,
    )


@router.get(
    "/daily-summary",
    response_model=list[MealPlanDailyNutritionSummaryRead],
)
async def get_meal_plan_daily_nutrition_summary(
        user_id: uuid.UUID,
        meal_plan_id: uuid.UUID,
        db: AsyncSession = Depends(get_db),
):
    service = MealPlanSummariesService(db)

    return await service.get_meal_plan_daily_nutrition_summary(
        user_id=user_id,
        meal_plan_id=meal_plan_id,
    )