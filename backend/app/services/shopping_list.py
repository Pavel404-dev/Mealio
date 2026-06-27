import uuid
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.meal_plans import normalize_meal_type
from app.repositories.shopping_list import ShoppingListRepository
from app.schemas.shopping_list import ShoppingListItemRead


class ShoppingListService:
    def __init__(self, db: AsyncSession) -> None:
        self.repository = ShoppingListRepository(db)

    async def get_current_user_combined_shopping_list(
            self,
            *,
            user_id: uuid.UUID,
            from_date: date,
            to_date: date,
            meal_type: str | None = None,
            subtract_pantry: bool = False,
    ) -> list[ShoppingListItemRead]:
        self._validate_date_range(
            from_date=from_date,
            to_date=to_date,
        )

        normalized_meal_type = None

        if meal_type is not None:
            normalized_meal_type = normalize_meal_type(meal_type)

            if normalized_meal_type == "":
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Meal type cannot be empty",
                )

        items = await self.repository.list_combined_for_user(
            user_id=user_id,
            from_date=from_date,
            to_date=to_date,
            meal_type=normalized_meal_type,
            subtract_pantry=subtract_pantry,
        )

        return [ShoppingListItemRead(**item) for item in items]

    def _validate_date_range(
            self,
            *,
            from_date: date,
            to_date: date,
    ) -> None:
        if from_date > to_date:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="from_date must be less than or equal to to_date",
            )