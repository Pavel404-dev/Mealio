import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, case, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ingredient import Ingredient, UserIngredient
from app.models.meal_plan import MealPlan, MealPlanItem
from app.models.recipe import Recipe, RecipeIngredient
from app.repositories.meal_plans import normalize_meal_type


class ShoppingListRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_combined_for_user(
        self,
        *,
        user_id: uuid.UUID,
        from_date: date,
        to_date: date,
        meal_type: str | None = None,
        subtract_pantry: bool = False,
    ) -> list[dict]:
        required_quantity = func.coalesce(
            func.sum(RecipeIngredient.quantity_g),
            Decimal("0"),
        ).label("required_quantity_g")

        required_stmt = (
            select(
                RecipeIngredient.ingredient_id.label("ingredient_id"),
                required_quantity,
            )
            .select_from(MealPlanItem)
            .join(MealPlan, MealPlan.id == MealPlanItem.meal_plan_id)
            .join(Recipe, Recipe.id == MealPlanItem.recipe_id)
            .join(RecipeIngredient, RecipeIngredient.recipe_id == Recipe.id)
            .where(
                MealPlan.user_id == user_id,
                MealPlanItem.planned_date >= from_date,
                MealPlanItem.planned_date <= to_date,
            )
        )

        if meal_type is not None:
            required_stmt = required_stmt.where(
                func.lower(MealPlanItem.meal_type) == normalize_meal_type(meal_type)
            )

        required_subquery = required_stmt.group_by(
            RecipeIngredient.ingredient_id,
        ).subquery()

        selected_columns = [
            Ingredient.id.label("ingredient_id"),
            Ingredient.name.label("ingredient_name"),
            Ingredient.category.label("ingredient_category"),
            required_subquery.c.required_quantity_g.label("required_quantity_g"),
        ]

        stmt = (
            select(*selected_columns)
            .select_from(required_subquery)
            .join(Ingredient, Ingredient.id == required_subquery.c.ingredient_id)
        )

        if subtract_pantry:
            pantry_quantity = func.coalesce(
                UserIngredient.quantity_g,
                Decimal("0"),
            )
            missing_quantity = case(
                (
                    required_subquery.c.required_quantity_g > pantry_quantity,
                    required_subquery.c.required_quantity_g - pantry_quantity,
                ),
                else_=Decimal("0"),
            )

            stmt = stmt.add_columns(
                pantry_quantity.label("pantry_quantity_g"),
                missing_quantity.label("missing_quantity_g"),
            ).outerjoin(
                UserIngredient,
                and_(
                    UserIngredient.user_id == user_id,
                    UserIngredient.ingredient_id == Ingredient.id,
                ),
            )

        stmt = stmt.order_by(
            Ingredient.name.asc(),
            Ingredient.id.asc(),
        )

        result = await self.db.execute(stmt)

        return [dict(row._mapping) for row in result.all()]

    async def add_missing_items_to_pantry(
        self,
        *,
        user_id: uuid.UUID,
        items: list[dict],
    ) -> list[dict]:
        if not items:
            return []

        ingredient_ids = [item["ingredient_id"] for item in items]

        existing_result = await self.db.execute(
            select(UserIngredient.ingredient_id).where(
                UserIngredient.user_id == user_id,
                UserIngredient.ingredient_id.in_(ingredient_ids),
            )
        )
        existing_ingredient_ids = set(existing_result.scalars().all())

        updated_items: list[dict] = []

        try:
            for item in items:
                added_quantity_g = self._to_decimal(item["missing_quantity_g"])

                insert_stmt = pg_insert(UserIngredient).values(
                    user_id=user_id,
                    ingredient_id=item["ingredient_id"],
                    quantity_g=added_quantity_g,
                )

                upsert_stmt = insert_stmt.on_conflict_do_update(
                    constraint="uq_user_ingredient",
                    set_={
                        "quantity_g": (
                            UserIngredient.quantity_g + insert_stmt.excluded.quantity_g
                        ),
                        "updated_at": func.now(),
                    },
                ).returning(
                    UserIngredient.ingredient_id.label("ingredient_id"),
                    UserIngredient.quantity_g.label("quantity_g"),
                )

                result = await self.db.execute(upsert_stmt)
                row = result.one()

                updated_items.append(
                    {
                        "ingredient_id": row.ingredient_id,
                        "ingredient_name": item["ingredient_name"],
                        "added_quantity_g": added_quantity_g,
                        "new_pantry_quantity_g": row.quantity_g,
                        "was_existing": item["ingredient_id"]
                        in existing_ingredient_ids,
                    }
                )

            await self.db.commit()

        except Exception:
            await self.db.rollback()
            raise

        return updated_items

    def _to_decimal(self, value) -> Decimal:
        if isinstance(value, Decimal):
            return value

        return Decimal(str(value))
