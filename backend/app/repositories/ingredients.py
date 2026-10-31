from __future__ import annotations

import uuid

from sqlalchemy import Text, bindparam, cast, column, delete, func, or_, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.ingredient import Ingredient, NutritionValue, UserIngredient
from app.models.recipe import RecipeIngredient
from app.repositories.exceptions import DuplicateResourceError
from app.schemas.ingredient import IngredientCreate, IngredientUpdate


def is_ingredient_name_conflict(error: IntegrityError) -> bool:
    # asyncpg's structured server error is the adapter exception's cause.
    current = error.orig
    seen = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if getattr(current, "sqlstate", None) == "23505" and getattr(
            current, "constraint_name", None
        ) in {"ux_ingredients_identity_v1", "ix_ingredients_name"}:
            return True
        current = current.__cause__
    return False


class IngredientsRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list(
        self,
        *,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Ingredient]:
        stmt = (
            select(Ingredient)
            .options(selectinload(Ingredient.nutrition_value))
            .order_by(Ingredient.name.collate("C").asc(), Ingredient.id.asc())
            .limit(limit)
            .offset(offset)
        )

        if search is not None:
            query = (
                select(func.public.mealio_ingredient_key_v1(search).label("key"))
                .cte("search_key")
                .prefix_with("MATERIALIZED")
            )
            query_key = select(query.c.key).scalar_subquery()
            name_key = func.public.mealio_ingredient_key_v1(Ingredient.name)
            stmt = stmt.where(
                or_(
                    func.char_length(query_key) == 0,
                    func.strpos(name_key.collate("C"), query_key.collate("C")) > 0,
                )
            )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, ingredient_id: uuid.UUID) -> Ingredient | None:
        stmt = (
            select(Ingredient)
            .options(selectinload(Ingredient.nutrition_value))
            .where(Ingredient.id == ingredient_id)
            .execution_options(populate_existing=True)
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Ingredient | None:
        stmt = (
            select(Ingredient)
            .options(selectinload(Ingredient.nutrition_value))
            .where(
                func.public.mealio_ingredient_bits_v1(Ingredient.name)
                == func.public.mealio_ingredient_bits_v1(name)
            )
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def match_exact_names(self, names: list[str]):
        inputs = (
            func.unnest(cast(bindparam("names"), ARRAY(Text)))
            .table_valued(column("name", Text), with_ordinality="ordinal")
            .render_derived(name="inputs")
        )
        keyed = select(
            inputs.c.ordinal,
            inputs.c.name,
            func.public.mealio_ingredient_bits_v1(inputs.c.name).label("key"),
        ).cte("keyed")
        counted = select(
            keyed, func.count().over(partition_by=keyed.c.key).label("duplicates")
        ).cte("counted")
        statement = (
            select(counted.c.ordinal, counted.c.name, counted.c.duplicates, Ingredient)
            .outerjoin(
                Ingredient,
                func.public.mealio_ingredient_bits_v1(Ingredient.name) == counted.c.key,
            )
            .order_by(counted.c.ordinal)
        )
        return (await self.db.execute(statement, {"names": names})).all()

    async def create(self, data: IngredientCreate) -> Ingredient:
        ingredient = Ingredient(
            name=data.name,
            category=data.category.strip() if data.category else None,
        )

        if data.nutrition_value:
            ingredient.nutrition_value = NutritionValue(
                calories=data.nutrition_value.calories,
                protein_g=data.nutrition_value.protein_g,
                carbs_g=data.nutrition_value.carbs_g,
                fat_g=data.nutrition_value.fat_g,
                portion_g=data.nutrition_value.portion_g,
            )

        self.db.add(ingredient)

        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            if is_ingredient_name_conflict(exc):
                raise DuplicateResourceError(
                    "Ingredient with this name already exists"
                ) from exc
            raise

        created = await self.get_by_id(ingredient.id)
        if created is None:
            raise RuntimeError("Created ingredient was not found")

        return created

    async def update(
        self,
        ingredient: Ingredient,
        data: IngredientUpdate,
    ) -> Ingredient:
        update_data = data.model_dump(exclude_unset=True)

        if "name" in update_data and data.name is not None:
            ingredient.name = data.name

        if "category" in update_data:
            ingredient.category = data.category.strip() if data.category else None

        if "nutrition_value" in update_data and data.nutrition_value is not None:
            if ingredient.nutrition_value is None:
                ingredient.nutrition_value = NutritionValue(
                    ingredient_id=ingredient.id,
                    calories=data.nutrition_value.calories,
                    protein_g=data.nutrition_value.protein_g,
                    carbs_g=data.nutrition_value.carbs_g,
                    fat_g=data.nutrition_value.fat_g,
                    portion_g=data.nutrition_value.portion_g,
                )
            else:
                ingredient.nutrition_value.calories = data.nutrition_value.calories
                ingredient.nutrition_value.protein_g = data.nutrition_value.protein_g
                ingredient.nutrition_value.carbs_g = data.nutrition_value.carbs_g
                ingredient.nutrition_value.fat_g = data.nutrition_value.fat_g
                ingredient.nutrition_value.portion_g = data.nutrition_value.portion_g

        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            if is_ingredient_name_conflict(exc):
                raise DuplicateResourceError(
                    "Ingredient with this name already exists"
                ) from exc
            raise

        updated = await self.get_by_id(ingredient.id)
        if updated is None:
            raise RuntimeError("Updated ingredient was not found")

        return updated

    async def is_used_in_recipes(self, ingredient_id: uuid.UUID) -> bool:
        stmt = (
            select(RecipeIngredient.id)
            .where(RecipeIngredient.ingredient_id == ingredient_id)
            .limit(1)
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def is_used_in_pantry(self, ingredient_id: uuid.UUID) -> bool:
        stmt = (
            select(UserIngredient.id)
            .where(UserIngredient.ingredient_id == ingredient_id)
            .limit(1)
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def delete(self, ingredient_id: uuid.UUID) -> None:
        stmt = delete(Ingredient).where(Ingredient.id == ingredient_id)
        await self.db.execute(stmt)
        await self.db.flush()
