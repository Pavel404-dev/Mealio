import uuid
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.meal_plan import MealPlan
from app.repositories.meal_plans import (
    MealPlanItemSlotConflictError,
    MealPlansRepository,
)
from app.schemas.meal_plan import (
    MealPlanCreate,
    MealPlanItemCreate,
    MealPlanItemUpdate,
    MealPlanUpdate,
)


class MealPlansService:
    def __init__(self, db: AsyncSession) -> None:
        self.repository = MealPlansRepository(db)

    async def list_user_meal_plans(
            self,
            *,
            user_id: uuid.UUID,
            limit: int = 50,
            offset: int = 0,
    ):
        await self._validate_user_exists(user_id)

        return await self.repository.list_for_user(
            user_id=user_id,
            limit=limit,
            offset=offset,
        )

    async def get_meal_plan(
            self,
            *,
            user_id: uuid.UUID,
            meal_plan_id: uuid.UUID,
    ):
        await self._validate_user_exists(user_id)

        meal_plan = await self.repository.get_by_id(
            user_id=user_id,
            meal_plan_id=meal_plan_id,
        )

        if meal_plan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meal plan not found",
            )

        return meal_plan

    async def create_meal_plan(
            self,
            *,
            user_id: uuid.UUID,
            data: MealPlanCreate,
    ):
        await self._validate_user_exists(user_id)
        await self._validate_items(data.items)
        self._validate_unique_slots(data.items)

        for item in data.items:
            self._validate_planned_date_inside_range(
                planned_date=item.planned_date,
                start_date=data.start_date,
                end_date=data.end_date,
            )

        try:
            return await self.repository.create(
                user_id=user_id,
                data=data,
            )
        except MealPlanItemSlotConflictError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Meal plan cannot contain duplicate meal slots",
            )

    async def update_meal_plan(
            self,
            *,
            user_id: uuid.UUID,
            meal_plan_id: uuid.UUID,
            data: MealPlanUpdate,
    ):
        meal_plan = await self.get_meal_plan(
            user_id=user_id,
            meal_plan_id=meal_plan_id,
        )

        update_data = data.model_dump(exclude_unset=True)

        new_start_date = (
            data.start_date
            if data.start_date is not None
            else meal_plan.start_date
        )

        new_end_date = (
            data.end_date
            if "end_date" in update_data
            else meal_plan.end_date
        )

        if new_end_date is not None and new_end_date < new_start_date:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="End date cannot be earlier than start date",
            )

        for item in meal_plan.items:
            self._validate_planned_date_inside_range(
                planned_date=item.planned_date,
                start_date=new_start_date,
                end_date=new_end_date,
            )

        return await self.repository.update(
            meal_plan=meal_plan,
            data=data,
        )

    async def delete_meal_plan(
            self,
            *,
            user_id: uuid.UUID,
            meal_plan_id: uuid.UUID,
    ) -> None:
        meal_plan = await self.get_meal_plan(
            user_id=user_id,
            meal_plan_id=meal_plan_id,
        )

        await self.repository.delete(meal_plan.id)

    async def add_meal_plan_item(
            self,
            *,
            user_id: uuid.UUID,
            meal_plan_id: uuid.UUID,
            data: MealPlanItemCreate,
    ):
        meal_plan = await self.get_meal_plan(
            user_id=user_id,
            meal_plan_id=meal_plan_id,
        )

        normalized_meal_type = self._normalize_meal_type(data.meal_type)

        await self._validate_recipe_exists(data.recipe_id)

        self._validate_planned_date_inside_meal_plan(
            meal_plan=meal_plan,
            planned_date=data.planned_date,
        )

        await self._validate_slot_is_available(
            meal_plan_id=meal_plan.id,
            planned_date=data.planned_date,
            meal_type=normalized_meal_type,
        )

        try:
            return await self.repository.add_item(
                meal_plan_id=meal_plan.id,
                data=data,
            )
        except MealPlanItemSlotConflictError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Meal plan already has an item for this date and meal type",
            )

    async def update_meal_plan_item(
            self,
            *,
            user_id: uuid.UUID,
            meal_plan_id: uuid.UUID,
            item_id: uuid.UUID,
            data: MealPlanItemUpdate,
    ):
        meal_plan = await self.get_meal_plan(
            user_id=user_id,
            meal_plan_id=meal_plan_id,
        )

        item = await self.repository.get_item_by_id(
            meal_plan_id=meal_plan.id,
            item_id=item_id,
        )

        if item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meal plan item not found",
            )

        if data.recipe_id is not None:
            await self._validate_recipe_exists(data.recipe_id)

        planned_date = (
            data.planned_date
            if data.planned_date is not None
            else item.planned_date
        )

        meal_type = (
            self._normalize_meal_type(data.meal_type)
            if data.meal_type is not None
            else item.meal_type
        )

        self._validate_planned_date_inside_meal_plan(
            meal_plan=meal_plan,
            planned_date=planned_date,
        )

        await self._validate_slot_is_available(
            meal_plan_id=meal_plan.id,
            planned_date=planned_date,
            meal_type=meal_type,
            exclude_item_id=item.id,
        )

        try:
            return await self.repository.update_item(
                item=item,
                data=data,
            )
        except MealPlanItemSlotConflictError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Meal plan already has an item for this date and meal type",
            )

    async def delete_meal_plan_item(
            self,
            *,
            user_id: uuid.UUID,
            meal_plan_id: uuid.UUID,
            item_id: uuid.UUID,
    ) -> None:
        meal_plan = await self.get_meal_plan(
            user_id=user_id,
            meal_plan_id=meal_plan_id,
        )

        item = await self.repository.get_item_by_id(
            meal_plan_id=meal_plan.id,
            item_id=item_id,
        )

        if item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meal plan item not found",
            )

        await self.repository.delete_item(item.id)

    async def _validate_user_exists(self, user_id: uuid.UUID) -> None:
        user = await self.repository.get_user(user_id)

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

    async def _validate_recipe_exists(self, recipe_id: uuid.UUID) -> None:
        recipe = await self.repository.get_recipe(recipe_id)

        if recipe is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recipe not found",
            )

    async def _validate_items(
            self,
            items: list[MealPlanItemCreate],
    ) -> None:
        for item in items:
            await self._validate_recipe_exists(item.recipe_id)

    def _validate_unique_slots(
            self,
            items: list[MealPlanItemCreate],
    ) -> None:
        slots = [
            (item.planned_date, self._normalize_meal_type(item.meal_type))
            for item in items
        ]

        if len(slots) != len(set(slots)):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Meal plan cannot contain duplicate meal slots",
            )

    async def _validate_slot_is_available(
            self,
            *,
            meal_plan_id: uuid.UUID,
            planned_date: date,
            meal_type: str,
            exclude_item_id: uuid.UUID | None = None,
    ) -> None:
        existing_item = await self.repository.get_item_by_slot(
            meal_plan_id=meal_plan_id,
            planned_date=planned_date,
            meal_type=self._normalize_meal_type(meal_type),
            exclude_item_id=exclude_item_id,
        )

        if existing_item is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Meal plan already has an item for this date and meal type",
            )

    def _validate_planned_date_inside_meal_plan(
            self,
            *,
            meal_plan: MealPlan,
            planned_date: date,
    ) -> None:
        self._validate_planned_date_inside_range(
            planned_date=planned_date,
            start_date=meal_plan.start_date,
            end_date=meal_plan.end_date,
        )

    def _validate_planned_date_inside_range(
            self,
            *,
            planned_date: date,
            start_date: date,
            end_date: date | None,
    ) -> None:
        if planned_date < start_date:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Planned date cannot be earlier than meal plan start date",
            )

        if end_date is not None and planned_date > end_date:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Planned date cannot be later than meal plan end date",
            )

    def _normalize_meal_type(self, meal_type: str) -> str:
        return meal_type.strip().lower()