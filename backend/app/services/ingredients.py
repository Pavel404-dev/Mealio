import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.ingredients import IngredientsRepository
from app.schemas.ingredient import IngredientCreate, IngredientUpdate
from app.repositories.exceptions import DuplicateResourceError


class IngredientsService:
    def __init__(self, db: AsyncSession) -> None:
        self.repository = IngredientsRepository(db)

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
            return await self.repository.update(ingredient, data)
        except DuplicateResourceError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
    async def delete_ingredient(self, ingredient_id: uuid.UUID) -> None:
        await self.get_ingredient(ingredient_id)
        await self.repository.delete(ingredient_id)
