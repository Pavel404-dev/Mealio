import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.meal_plan import MealPlanItem
from app.models.recipe import Recipe
from app.repositories.meal_plan_quantities import planned_quantity_sum


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
                planned_quantity_sum(Recipe.total_calories).label("total_calories"),
                planned_quantity_sum(Recipe.total_protein_g).label("total_protein_g"),
                planned_quantity_sum(Recipe.total_carbs_g).label("total_carbs_g"),
                planned_quantity_sum(Recipe.total_fat_g).label("total_fat_g"),
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

    async def get_daily_nutrition_summary(
        self,
        *,
        meal_plan_id: uuid.UUID,
    ) -> list[dict]:
        stmt = (
            select(
                MealPlanItem.planned_date.label("date"),
                func.count(MealPlanItem.id).label("items_count"),
                planned_quantity_sum(Recipe.total_calories).label("total_calories"),
                planned_quantity_sum(Recipe.total_protein_g).label("total_protein_g"),
                planned_quantity_sum(Recipe.total_carbs_g).label("total_carbs_g"),
                planned_quantity_sum(Recipe.total_fat_g).label("total_fat_g"),
            )
            .select_from(MealPlanItem)
            .join(Recipe, Recipe.id == MealPlanItem.recipe_id)
            .where(MealPlanItem.meal_plan_id == meal_plan_id)
            .group_by(MealPlanItem.planned_date)
            .order_by(MealPlanItem.planned_date.asc())
        )

        result = await self.db.execute(stmt)
        rows = result.all()

        return [
            {
                "date": row.date,
                "items_count": row.items_count or 0,
                "total_calories": self._to_decimal(row.total_calories),
                "total_protein_g": self._to_decimal(row.total_protein_g),
                "total_carbs_g": self._to_decimal(row.total_carbs_g),
                "total_fat_g": self._to_decimal(row.total_fat_g),
            }
            for row in rows
        ]

    def _to_decimal(self, value) -> Decimal:
        if value is None:
            return ZERO

        return Decimal(value).quantize(ZERO)
