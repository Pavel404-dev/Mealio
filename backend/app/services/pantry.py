import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.pantry import PantryRepository
from app.schemas.pantry import PantryItemCreate, PantryItemUpdate


class PantryService:
    def __init__(self, db: AsyncSession) -> None:
        self.repository = PantryRepository(db)

    async def list_user_pantry(self, user_id: uuid.UUID):
        await self._ensure_user_exists(user_id)
        return await self.repository.list_user_pantry(user_id)

    async def add_pantry_item(
            self,
            *,
            user_id: uuid.UUID,
            data: PantryItemCreate,
    ):
        await self._ensure_user_exists(user_id)
        await self._ensure_ingredient_exists(data.ingredient_id)

        existing = await self.repository.get_by_user_and_ingredient(
            user_id=user_id,
            ingredient_id=data.ingredient_id,
        )

        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ingredient already exists in user pantry",
            )

        return await self.repository.create(user_id=user_id, data=data)

    async def update_pantry_item(
            self,
            *,
            user_id: uuid.UUID,
            pantry_item_id: uuid.UUID,
            data: PantryItemUpdate,
    ):
        await self._ensure_user_exists(user_id)

        pantry_item = await self.repository.get_user_pantry_item(
            user_id=user_id,
            pantry_item_id=pantry_item_id,
        )

        if pantry_item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pantry item not found",
            )

        return await self.repository.update(
            pantry_item=pantry_item,
            data=data,
        )

    async def delete_pantry_item(
            self,
            *,
            user_id: uuid.UUID,
            pantry_item_id: uuid.UUID,
    ) -> None:
        await self._ensure_user_exists(user_id)

        pantry_item = await self.repository.get_user_pantry_item(
            user_id=user_id,
            pantry_item_id=pantry_item_id,
        )

        if pantry_item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pantry item not found",
            )

        await self.repository.delete(
            user_id=user_id,
            pantry_item_id=pantry_item_id,
        )

    async def _ensure_user_exists(self, user_id: uuid.UUID) -> None:
        user = await self.repository.get_user(user_id)

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

    async def _ensure_ingredient_exists(self, ingredient_id: uuid.UUID) -> None:
        ingredient = await self.repository.get_ingredient(ingredient_id)

        if ingredient is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ingredient not found",
            )