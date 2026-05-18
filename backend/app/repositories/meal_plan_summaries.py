import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.meal_plan import MealPlanItem
from app.models.recipe import Recipe


ZERO = Decimal("0.00")


class MealPlanSummariesRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_nutrition_summary(
            self,
            *,
            meal_plan_id: uuid.UUID,
    ) -> dict:
        stmt = (
            select(
                func.count(MealPlanItem.id).label("items_count"),
                func.coalesce(
                    func.sum(func.coalesce(Recipe.total_calories, ZERO)),
                    ZERO,
                ).label("total_calories"),
                func.coalesce(
                    func.sum(func.coalesce(Recipe.total_protein_g, ZERO)),
                    ZERO,
                ).label("total_protein_g"),
                func.coalesce(
                    func.sum(func.coalesce(Recipe.total_carbs_g, ZERO)),
                    ZERO,
                ).label("total_carbs_g"),
                func.coalesce(
                    func.sum(func.coalesce(Recipe.total_fat_g, ZERO)),
                    ZERO,
                ).label("total_fat_g"),
            )
            .select_from(MealPlanItem)
            .join(Recipe, Recipe.id == MealPlanItem.recipe_id)
            .where(MealPlanItem.meal_plan_id == meal_plan_id)
        )

        result = await self.db.execute(stmt)
        row = result.one()

        return {
            "meal_plan_id": meal_plan_id,
            "items_count": row.items_count or 0,
            "total_calories": self._to_decimal(row.total_calories),
            "total_protein_g": self._to_decimal(row.total_protein_g),
            "total_carbs_g": self._to_decimal(row.total_carbs_g),
            "total_fat_g": self._to_decimal(row.total_fat_g),
        }

    def _to_decimal(self, value) -> Decimal:
        if value is None:
            return ZERO

        return Decimal(value).quantize(ZERO)