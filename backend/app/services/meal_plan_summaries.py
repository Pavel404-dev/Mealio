import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.meal_plans import MealPlansRepository
from app.repositories.meal_plan_summaries import MealPlanSummariesRepository
from app.schemas.meal_plan_summary import (
    MealPlanDailyNutritionSummaryRead,
    MealPlanNutritionSummaryRead,
)


class MealPlanSummariesService:
    def __init__(self, db: AsyncSession) -> None:
        self.meal_plans_repository = MealPlansRepository(db)
        self.summaries_repository = MealPlanSummariesRepository(db)

    async def get_meal_plan_nutrition_summary(
        self,
        *,
        user_id: uuid.UUID,
        meal_plan_id: uuid.UUID,
    ) -> MealPlanNutritionSummaryRead:
        meal_plan = await self._validate_user_and_meal_plan(
            user_id=user_id,
            meal_plan_id=meal_plan_id,
        )

        summary = await self.summaries_repository.get_nutrition_summary(
            meal_plan_id=meal_plan.id,
        )

        return MealPlanNutritionSummaryRead(**summary)

    async def get_meal_plan_daily_nutrition_summary(
        self,
        *,
        user_id: uuid.UUID,
        meal_plan_id: uuid.UUID,
    ) -> list[MealPlanDailyNutritionSummaryRead]:
        meal_plan = await self._validate_user_and_meal_plan(
            user_id=user_id,
            meal_plan_id=meal_plan_id,
        )

        daily_summary = await self.summaries_repository.get_daily_nutrition_summary(
            meal_plan_id=meal_plan.id,
        )

        return [
            MealPlanDailyNutritionSummaryRead(**summary) for summary in daily_summary
        ]

    async def _validate_user_and_meal_plan(
        self,
        *,
        user_id: uuid.UUID,
        meal_plan_id: uuid.UUID,
    ):
        user = await self.meal_plans_repository.get_user(user_id)

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        meal_plan = await self.meal_plans_repository.get_by_id(
            user_id=user_id,
            meal_plan_id=meal_plan_id,
        )

        if meal_plan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meal plan not found",
            )

        return meal_plan
