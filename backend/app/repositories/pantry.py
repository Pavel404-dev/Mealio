import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from app.models.ingredient import Ingredient, UserIngredient
from app.models.user import User
from app.schemas.pantry import PantryItemCreate, PantryItemUpdate
from app.repositories.exceptions import DuplicateResourceError


class PantryRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_user(self, user_id: uuid.UUID) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_ingredient(self, ingredient_id: uuid.UUID) -> Ingredient | None:
        result = await self.db.execute(
            select(Ingredient).where(Ingredient.id == ingredient_id)
        )
        return result.scalar_one_or_none()

    async def list_user_pantry(self, user_id: uuid.UUID) -> list[UserIngredient]:
        stmt = (
            select(UserIngredient)
            .options(
                selectinload(UserIngredient.ingredient).selectinload(
                    Ingredient.nutrition_value
                )
            )
            .where(UserIngredient.user_id == user_id)
            .order_by(UserIngredient.created_at.desc())
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_user_pantry_item(
        self,
        *,
        user_id: uuid.UUID,
        pantry_item_id: uuid.UUID,
    ) -> UserIngredient | None:
        stmt = (
            select(UserIngredient)
            .options(
                selectinload(UserIngredient.ingredient).selectinload(
                    Ingredient.nutrition_value
                )
            )
            .where(
                UserIngredient.id == pantry_item_id,
                UserIngredient.user_id == user_id,
            )
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_user_and_ingredient(
        self,
        *,
        user_id: uuid.UUID,
        ingredient_id: uuid.UUID,
    ) -> UserIngredient | None:
        stmt = select(UserIngredient).where(
            UserIngredient.user_id == user_id,
            UserIngredient.ingredient_id == ingredient_id,
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        data: PantryItemCreate,
    ) -> UserIngredient:
        pantry_item = UserIngredient(
            user_id=user_id,
            ingredient_id=data.ingredient_id,
            quantity_g=data.quantity_g,
            expires_at=data.expires_at,
        )

        self.db.add(pantry_item)

        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise DuplicateResourceError(
                "Ingredient already exists in user pantry"
            ) from exc

        created = await self.get_user_pantry_item(
            user_id=user_id,
            pantry_item_id=pantry_item.id,
        )

        if created is None:
            raise RuntimeError("Created pantry item was not found")

        return created

    async def update(
        self,
        *,
        pantry_item: UserIngredient,
        data: PantryItemUpdate,
    ) -> UserIngredient:
        update_data = data.model_dump(exclude_unset=True)

        if "quantity_g" in update_data and data.quantity_g is not None:
            pantry_item.quantity_g = data.quantity_g

        if "expires_at" in update_data:
            pantry_item.expires_at = data.expires_at

        await self.db.commit()

        updated = await self.get_user_pantry_item(
            user_id=pantry_item.user_id,
            pantry_item_id=pantry_item.id,
        )

        if updated is None:
            raise RuntimeError("Updated pantry item was not found")

        return updated

    async def delete(
        self,
        *,
        user_id: uuid.UUID,
        pantry_item_id: uuid.UUID,
    ) -> None:
        stmt = delete(UserIngredient).where(
            UserIngredient.id == pantry_item_id,
            UserIngredient.user_id == user_id,
        )

        await self.db.execute(stmt)
        await self.db.commit()
