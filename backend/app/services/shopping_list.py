import uuid
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.meal_plans import normalize_meal_type
from app.repositories.shopping_list import ShoppingListRepository
from app.schemas.shopping_list import (
    ShoppingListAddMissingToPantryResponse,
    ShoppingListAddedPantryItemRead,
    ShoppingListItemRead,
)


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

        normalized_meal_type = self._normalize_optional_meal_type(meal_type)

        items = await self.repository.list_combined_for_user(
            user_id=user_id,
            from_date=from_date,
            to_date=to_date,
            meal_type=normalized_meal_type,
            subtract_pantry=subtract_pantry,
        )

        return [ShoppingListItemRead(**item) for item in items]

    async def add_missing_items_to_pantry(
        self,
        *,
        user_id: uuid.UUID,
        from_date: date,
        to_date: date,
        meal_type: str | None = None,
    ) -> ShoppingListAddMissingToPantryResponse:
        self._validate_date_range(
            from_date=from_date,
            to_date=to_date,
        )

        normalized_meal_type = self._normalize_optional_meal_type(meal_type)

        shopping_list_items = await self.repository.list_combined_for_user(
            user_id=user_id,
            from_date=from_date,
            to_date=to_date,
            meal_type=normalized_meal_type,
            subtract_pantry=True,
        )

        items_to_add = [
            item
            for item in shopping_list_items
            if self._to_decimal(item.get("missing_quantity_g")) > Decimal("0")
        ]

        skipped_items_count = len(shopping_list_items) - len(items_to_add)

        updated_pantry_items = await self.repository.add_missing_items_to_pantry(
            user_id=user_id,
            items=items_to_add,
        )

        updated_items_count = sum(
            1 for item in updated_pantry_items if item["was_existing"]
        )
        added_items_count = sum(
            1 for item in updated_pantry_items if not item["was_existing"]
        )

        return ShoppingListAddMissingToPantryResponse(
            updated_items_count=updated_items_count,
            added_items_count=added_items_count,
            skipped_items_count=skipped_items_count,
            items=[
                ShoppingListAddedPantryItemRead(
                    ingredient_id=item["ingredient_id"],
                    ingredient_name=item["ingredient_name"],
                    added_quantity_g=item["added_quantity_g"],
                    new_pantry_quantity_g=item["new_pantry_quantity_g"],
                )
                for item in updated_pantry_items
            ],
        )

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

    def _normalize_optional_meal_type(self, meal_type: str | None) -> str | None:
        if meal_type is None:
            return None

        normalized_meal_type = normalize_meal_type(meal_type)

        if normalized_meal_type == "":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Meal type cannot be empty",
            )

        return normalized_meal_type

    def _to_decimal(self, value) -> Decimal:
        if value is None:
            return Decimal("0")

        if isinstance(value, Decimal):
            return value

        return Decimal(str(value))
