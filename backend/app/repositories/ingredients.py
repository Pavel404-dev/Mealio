import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.ingredient import Ingredient, NutritionValue
from app.schemas.ingredient import IngredientCreate, IngredientUpdate


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
            .order_by(Ingredient.name.asc())
            .limit(limit)
            .offset(offset)
        )

        if search:
            stmt = stmt.where(Ingredient.name.ilike(f"%{search}%"))

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, ingredient_id: uuid.UUID) -> Ingredient | None:
        stmt = (
            select(Ingredient)
            .options(selectinload(Ingredient.nutrition_value))
            .where(Ingredient.id == ingredient_id)
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Ingredient | None:
        stmt = (
            select(Ingredient)
            .options(selectinload(Ingredient.nutrition_value))
            .where(Ingredient.name.ilike(name))
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, data: IngredientCreate) -> Ingredient:
        ingredient = Ingredient(
            name=data.name.strip(),
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
        await self.db.commit()

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
            ingredient.name = data.name.strip()

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

        await self.db.commit()

        updated = await self.get_by_id(ingredient.id)
        if updated is None:
            raise RuntimeError("Updated ingredient was not found")

        return updated

    async def delete(self, ingredient_id: uuid.UUID) -> None:
        stmt = delete(Ingredient).where(Ingredient.id == ingredient_id)
        await self.db.execute(stmt)
        await self.db.commit()