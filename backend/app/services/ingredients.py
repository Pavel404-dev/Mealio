import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.exceptions import DuplicateResourceError
from app.repositories.ingredients import IngredientsRepository
from app.repositories.recipes import RecipesRepository
from app.schemas.ingredient import IngredientCreate, IngredientUpdate
from app.services.recipe_nutrition import RecipeNutritionCalculator


class IngredientsService:
    def __init__(self, db: AsyncSession) -> None:
        self.repository = IngredientsRepository(db)
        self.recipes_repository = RecipesRepository(db)
        self.nutrition_calculator = RecipeNutritionCalculator()

    async def list_ingredients(
        self,
        *,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ):
        return await self.repository.list(
            search=search,
            limit=limit,
            offset=offset,
        )

    async def get_ingredient(self, ingredient_id: uuid.UUID):
        ingredient = await self.repository.get_by_id(ingredient_id)

        if ingredient is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ingredient not found",
            )

        return ingredient

    async def create_ingredient(self, data: IngredientCreate):
        existing = await self.repository.get_by_name(data.name.strip())

        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ingredient with this name already exists",
            )

        try:
            return await self.repository.create(data)
        except DuplicateResourceError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc

    async def update_ingredient(
        self,
        ingredient_id: uuid.UUID,
        data: IngredientUpdate,
    ):
        ingredient = await self.get_ingredient(ingredient_id)

        if data.name is not None:
            existing = await self.repository.get_by_name(data.name.strip())

            if existing is not None and existing.id != ingredient_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Ingredient with this name already exists",
                )

        try:
            updated_ingredient = await self.repository.update(ingredient, data)
        except DuplicateResourceError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc

        if data.nutrition_value is not None:
            await self._recalculate_recipes_using_ingredient(ingredient_id)

        return updated_ingredient

    async def delete_ingredient(self, ingredient_id: uuid.UUID) -> None:
        await self.get_ingredient(ingredient_id)

        is_used_in_recipes = await self.repository.is_used_in_recipes(ingredient_id)
        is_used_in_pantry = await self.repository.is_used_in_pantry(ingredient_id)

        if is_used_in_recipes or is_used_in_pantry:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ingredient is used and cannot be deleted",
            )

        await self.repository.delete(ingredient_id)

    async def _recalculate_recipes_using_ingredient(
        self,
        ingredient_id: uuid.UUID,
    ) -> None:
        recipes = await self.recipes_repository.list_by_ingredient_id(ingredient_id)

        recipe_totals = {
            recipe.id: self.nutrition_calculator.calculate_from_recipe(recipe)
            for recipe in recipes
        }

        await self.recipes_repository.update_nutrition_totals_for_loaded_recipes(
            recipes=recipes,
            recipe_totals=recipe_totals,
        )
