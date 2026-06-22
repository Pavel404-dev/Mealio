import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ingredient import Ingredient
from app.repositories.recipes import RecipesRepository
from app.schemas.recipe import (
    RecipeCreate,
    RecipeIngredientCreate,
    RecipeNutritionTotals,
    RecipeUpdate,
)


class RecipesService:
    def __init__(self, db: AsyncSession) -> None:
        self.repository = RecipesRepository(db)

    async def list_user_recipes(
        self,
        *,
        user_id: uuid.UUID,
        search: str | None = None,
        diet_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ):
        return await self.repository.list(
            search=search,
            diet_type=diet_type,
            created_by_user_id=user_id,
            limit=limit,
            offset=offset,
        )

    async def get_recipe(
        self,
        *,
        user_id: uuid.UUID,
        recipe_id: uuid.UUID,
    ):
        recipe = await self.repository.get_by_id(
            recipe_id=recipe_id,
            created_by_user_id=user_id,
        )

        if recipe is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recipe not found",
            )

        return recipe

    async def create_recipe(
        self,
        *,
        user_id: uuid.UUID,
        data: RecipeCreate,
    ):
        ingredients_by_id = await self._get_existing_ingredients_by_id(data.ingredients)
        self._validate_all_ingredients_exist(
            ingredients=data.ingredients,
            ingredients_by_id=ingredients_by_id,
        )

        nutrition_totals = self._calculate_nutrition_totals(
            ingredients=data.ingredients,
            ingredients_by_id=ingredients_by_id,
        )

        return await self.repository.create(
            created_by_user_id=user_id,
            data=data,
            nutrition_totals=nutrition_totals,
        )

    async def update_recipe(
        self,
        *,
        user_id: uuid.UUID,
        recipe_id: uuid.UUID,
        data: RecipeUpdate,
    ):
        recipe = await self.get_recipe(
            user_id=user_id,
            recipe_id=recipe_id,
        )

        nutrition_totals: RecipeNutritionTotals | None = None

        if data.ingredients is not None:
            ingredients_by_id = await self._get_existing_ingredients_by_id(
                data.ingredients
            )
            self._validate_all_ingredients_exist(
                ingredients=data.ingredients,
                ingredients_by_id=ingredients_by_id,
            )

            nutrition_totals = self._calculate_nutrition_totals(
                ingredients=data.ingredients,
                ingredients_by_id=ingredients_by_id,
            )

        return await self.repository.update(
            recipe=recipe,
            data=data,
            nutrition_totals=nutrition_totals,
        )

    async def delete_recipe(
        self,
        *,
        user_id: uuid.UUID,
        recipe_id: uuid.UUID,
    ) -> None:
        recipe = await self.get_recipe(
            user_id=user_id,
            recipe_id=recipe_id,
        )

        if await self.repository.is_used_in_meal_plan_items(recipe.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Recipe is used in meal plans and cannot be deleted",
            )

        await self.repository.delete(recipe.id)

    async def _get_existing_ingredients_by_id(
        self,
        ingredients: list[RecipeIngredientCreate],
    ) -> dict[uuid.UUID, Ingredient]:
        ingredient_ids = [item.ingredient_id for item in ingredients]

        if not ingredient_ids:
            return {}

        existing_ingredients = await self.repository.get_ingredients_by_ids(
            ingredient_ids
        )

        return {ingredient.id: ingredient for ingredient in existing_ingredients}

    def _validate_all_ingredients_exist(
        self,
        *,
        ingredients: list[RecipeIngredientCreate],
        ingredients_by_id: dict[uuid.UUID, Ingredient],
    ) -> None:
        missing_ids = [
            str(item.ingredient_id)
            for item in ingredients
            if item.ingredient_id not in ingredients_by_id
        ]

        if missing_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ingredients not found: {', '.join(missing_ids)}",
            )

    def _calculate_nutrition_totals(
        self,
        *,
        ingredients: list[RecipeIngredientCreate],
        ingredients_by_id: dict[uuid.UUID, Ingredient],
    ) -> RecipeNutritionTotals:
        total_calories = Decimal("0")
        total_protein_g = Decimal("0")
        total_carbs_g = Decimal("0")
        total_fat_g = Decimal("0")

        for recipe_ingredient in ingredients:
            ingredient = ingredients_by_id.get(recipe_ingredient.ingredient_id)

            if ingredient is None or ingredient.nutrition_value is None:
                continue

            nutrition_value = ingredient.nutrition_value

            if nutrition_value.portion_g <= 0:
                continue

            factor = recipe_ingredient.quantity_g / nutrition_value.portion_g

            total_calories += nutrition_value.calories * factor
            total_protein_g += nutrition_value.protein_g * factor
            total_carbs_g += nutrition_value.carbs_g * factor
            total_fat_g += nutrition_value.fat_g * factor

        return RecipeNutritionTotals(
            total_calories=total_calories,
            total_protein_g=total_protein_g,
            total_carbs_g=total_carbs_g,
            total_fat_g=total_fat_g,
        )
