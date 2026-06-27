from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.ingredient import Ingredient, UserIngredient
from app.models.meal_plan import MealPlanItem
from app.models.recipe import Recipe, RecipeIngredient
from app.schemas.recipe import RecipeCreate, RecipeNutritionTotals, RecipeUpdate


class RecipesRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_ingredients_by_ids(
            self,
            ingredient_ids: list[uuid.UUID],
    ) -> list[Ingredient]:
        if not ingredient_ids:
            return []

        stmt = (
            select(Ingredient)
            .options(selectinload(Ingredient.nutrition_value))
            .where(Ingredient.id.in_(ingredient_ids))
        )
        result = await self.db.execute(stmt)

        return list(result.scalars().all())

    async def list(
            self,
            *,
            search: str | None = None,
            diet_type: str | None = None,
            min_calories: Decimal | None = None,
            max_calories: Decimal | None = None,
            created_by_user_id: uuid.UUID | None = None,
            limit: int = 50,
            offset: int = 0,
    ) -> list[Recipe]:
        stmt = select(Recipe).options(selectinload(Recipe.recipe_ingredients))

        if created_by_user_id is not None:
            stmt = stmt.where(Recipe.created_by_user_id == created_by_user_id)

        if search:
            search_term = search.strip()

            if search_term:
                search_pattern = f"%{search_term}%"
                stmt = stmt.where(
                    or_(
                        Recipe.title.ilike(search_pattern),
                        func.coalesce(Recipe.description, "").ilike(search_pattern),
                    )
                )

        if diet_type:
            stmt = stmt.where(Recipe.diet_type == diet_type)

        if min_calories is not None:
            stmt = stmt.where(Recipe.total_calories >= min_calories)

        if max_calories is not None:
            stmt = stmt.where(Recipe.total_calories <= max_calories)

        stmt = stmt.order_by(Recipe.created_at.desc()).limit(limit).offset(offset)

        result = await self.db.execute(stmt)

        return list(result.scalars().all())

    async def list_for_pantry_suggestions(
            self,
            *,
            created_by_user_id: uuid.UUID,
            diet_type: str | None = None,
    ) -> list[Recipe]:
        stmt = (
            select(Recipe)
            .options(
                selectinload(Recipe.recipe_ingredients).selectinload(
                    RecipeIngredient.ingredient
                )
            )
            .where(Recipe.created_by_user_id == created_by_user_id)
        )

        if diet_type:
            stmt = stmt.where(Recipe.diet_type == diet_type)

        stmt = stmt.order_by(
            Recipe.title.asc(),
            Recipe.id.asc(),
        )

        result = await self.db.execute(stmt)

        return list(result.scalars().unique().all())

    async def list_user_pantry_by_ingredient_id(
            self,
            *,
            user_id: uuid.UUID,
    ) -> dict[uuid.UUID, UserIngredient]:
        stmt = select(UserIngredient).where(UserIngredient.user_id == user_id)

        result = await self.db.execute(stmt)

        return {
            pantry_item.ingredient_id: pantry_item
            for pantry_item in result.scalars().all()
        }

    async def get_by_id(
            self,
            recipe_id: uuid.UUID,
            *,
            created_by_user_id: uuid.UUID | None = None,
    ) -> Recipe | None:
        stmt = (
            select(Recipe)
            .options(selectinload(Recipe.recipe_ingredients))
            .where(Recipe.id == recipe_id)
        )

        if created_by_user_id is not None:
            stmt = stmt.where(Recipe.created_by_user_id == created_by_user_id)

        result = await self.db.execute(stmt)

        return result.scalar_one_or_none()

    async def list_by_ingredient_id(
            self,
            ingredient_id: uuid.UUID,
    ) -> list[Recipe]:
        stmt = (
            select(Recipe)
            .join(RecipeIngredient)
            .options(
                selectinload(Recipe.recipe_ingredients)
                .selectinload(RecipeIngredient.ingredient)
                .selectinload(Ingredient.nutrition_value)
            )
            .where(RecipeIngredient.ingredient_id == ingredient_id)
        )

        result = await self.db.execute(stmt)

        return list(result.scalars().unique().all())

    async def create(
            self,
            *,
            created_by_user_id: uuid.UUID,
            data: RecipeCreate,
            nutrition_totals: RecipeNutritionTotals,
    ) -> Recipe:
        recipe = Recipe(
            created_by_user_id=created_by_user_id,
            title=data.title.strip(),
            description=data.description.strip() if data.description else None,
            instructions=data.instructions.strip(),
            diet_type=data.diet_type.strip() if data.diet_type else None,
            total_calories=nutrition_totals.total_calories,
            total_protein_g=nutrition_totals.total_protein_g,
            total_carbs_g=nutrition_totals.total_carbs_g,
            total_fat_g=nutrition_totals.total_fat_g,
        )

        recipe.recipe_ingredients = [
            RecipeIngredient(
                ingredient_id=item.ingredient_id,
                quantity_g=item.quantity_g,
            )
            for item in data.ingredients
        ]

        self.db.add(recipe)
        await self.db.commit()

        created = await self.get_by_id(
            recipe.id,
            created_by_user_id=created_by_user_id,
        )

        if created is None:
            raise RuntimeError("Created recipe was not found")

        return created

    async def update(
            self,
            *,
            recipe: Recipe,
            data: RecipeUpdate,
            nutrition_totals: RecipeNutritionTotals | None = None,
    ) -> Recipe:
        update_data = data.model_dump(exclude_unset=True)

        if "title" in update_data and data.title is not None:
            recipe.title = data.title.strip()

        if "description" in update_data:
            recipe.description = data.description.strip() if data.description else None

        if "instructions" in update_data and data.instructions is not None:
            recipe.instructions = data.instructions.strip()

        if "diet_type" in update_data:
            recipe.diet_type = data.diet_type.strip() if data.diet_type else None

        if nutrition_totals is not None:
            recipe.total_calories = nutrition_totals.total_calories
            recipe.total_protein_g = nutrition_totals.total_protein_g
            recipe.total_carbs_g = nutrition_totals.total_carbs_g
            recipe.total_fat_g = nutrition_totals.total_fat_g

        if data.ingredients is not None:
            recipe.recipe_ingredients.clear()
            await self.db.flush()

            recipe.recipe_ingredients.extend(
                RecipeIngredient(
                    recipe_id=recipe.id,
                    ingredient_id=item.ingredient_id,
                    quantity_g=item.quantity_g,
                )
                for item in data.ingredients
            )

        await self.db.commit()

        updated = await self.get_by_id(recipe.id)

        if updated is None:
            raise RuntimeError("Updated recipe was not found")

        return updated

    async def update_nutrition_totals_for_loaded_recipes(
            self,
            *,
            recipes: list[Recipe],
            recipe_totals: dict[uuid.UUID, RecipeNutritionTotals],
    ) -> None:
        if not recipes:
            return

        for recipe in recipes:
            nutrition_totals = recipe_totals.get(recipe.id)

            if nutrition_totals is None:
                continue

            recipe.total_calories = nutrition_totals.total_calories
            recipe.total_protein_g = nutrition_totals.total_protein_g
            recipe.total_carbs_g = nutrition_totals.total_carbs_g
            recipe.total_fat_g = nutrition_totals.total_fat_g

        await self.db.commit()

    async def is_used_in_meal_plan_items(self, recipe_id: uuid.UUID) -> bool:
        stmt = (
            select(MealPlanItem.id).where(MealPlanItem.recipe_id == recipe_id).limit(1)
        )
        result = await self.db.execute(stmt)

        return result.scalar_one_or_none() is not None

    async def delete(self, recipe_id: uuid.UUID) -> None:
        stmt = delete(Recipe).where(Recipe.id == recipe_id)

        await self.db.execute(stmt)
        await self.db.commit()