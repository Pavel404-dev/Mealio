import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.meal_plans import MealPlansRepository
from app.repositories.meal_plan_summaries import MealPlanSummariesRepository
from app.schemas.meal_plan_summary import MealPlanNutritionSummaryRead


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

        summary = await self.summaries_repository.get_nutrition_summary(
            meal_plan_id=meal_plan.id,
        )

        return MealPlanNutritionSummaryRead(**summary)