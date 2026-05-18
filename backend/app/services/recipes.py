import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.recipes import RecipesRepository
from app.schemas.recipe import RecipeCreate, RecipeIngredientCreate, RecipeUpdate


class RecipesService:
    def __init__(self, db: AsyncSession) -> None:
        self.repository = RecipesRepository(db)

    async def list_recipes(
            self,
            *,
            search: str | None = None,
            diet_type: str | None = None,
            created_by_user_id: uuid.UUID | None = None,
            limit: int = 50,
            offset: int = 0,
    ):
        if created_by_user_id is not None:
            user = await self.repository.get_user(created_by_user_id)

            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found",
                )

        return await self.repository.list(
            search=search,
            diet_type=diet_type,
            created_by_user_id=created_by_user_id,
            limit=limit,
            offset=offset,
        )

    async def get_recipe(self, recipe_id: uuid.UUID):
        recipe = await self.repository.get_by_id(recipe_id)

        if recipe is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recipe not found",
            )

        return recipe

    async def create_recipe(self, data: RecipeCreate):
        if data.created_by_user_id is not None:
            user = await self.repository.get_user(data.created_by_user_id)

            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found",
                )

        await self._validate_ingredients_exist(data.ingredients)

        return await self.repository.create(data)

    async def update_recipe(
            self,
            recipe_id: uuid.UUID,
            data: RecipeUpdate,
    ):
        recipe = await self.get_recipe(recipe_id)

        if data.ingredients is not None:
            await self._validate_ingredients_exist(data.ingredients)

        return await self.repository.update(
            recipe=recipe,
            data=data,
        )

    async def delete_recipe(self, recipe_id: uuid.UUID) -> None:
        await self.get_recipe(recipe_id)
        await self.repository.delete(recipe_id)

    async def _validate_ingredients_exist(
            self,
            ingredients: list[RecipeIngredientCreate],
    ) -> None:
        ingredient_ids = [item.ingredient_id for item in ingredients]

        if not ingredient_ids:
            return

        existing_ingredients = await self.repository.get_ingredients_by_ids(ingredient_ids)
        existing_ids = {ingredient.id for ingredient in existing_ingredients}

        missing_ids = [
            str(ingredient_id)
            for ingredient_id in ingredient_ids
            if ingredient_id not in existing_ids
        ]

        if missing_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ingredients not found: {', '.join(missing_ids)}",
            )