"""Opt-in canonical writes; reads and other plan operations remain available in v1."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.meal_plan import MealPlanItemRead, MealPlanRead
from app.schemas.meal_plan_v2 import (
    MealPlanItemV2Create,
    MealPlanItemV2Update,
    MealPlanV2Create,
)
from app.services.meal_plans import MealPlansService

router = APIRouter(prefix="/meal-plans", tags=["Meal Plans V2"])


@router.post("", response_model=MealPlanRead, status_code=status.HTTP_201_CREATED)
async def create_meal_plan(
    payload: MealPlanV2Create,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create canonical slots; read the resulting plan through /api/v1/meal-plans."""
    return await MealPlansService(db).create_meal_plan(
        user_id=current_user.id,
        data=payload,
    )


@router.post(
    "/{meal_plan_id}/items",
    response_model=MealPlanItemRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_meal_plan_item(
    meal_plan_id: uuid.UUID,
    payload: MealPlanItemV2Create,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a canonical slot to a new or legacy plan."""
    return await MealPlansService(db).add_meal_plan_item(
        user_id=current_user.id,
        meal_plan_id=meal_plan_id,
        data=payload,
    )


@router.patch(
    "/{meal_plan_id}/items/{item_id}",
    response_model=MealPlanItemRead,
)
async def update_meal_plan_item(
    meal_plan_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: MealPlanItemV2Update,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Omit meal_type to preserve a legacy label, or supply a canonical replacement."""
    return await MealPlansService(db).update_meal_plan_item(
        user_id=current_user.id,
        meal_plan_id=meal_plan_id,
        item_id=item_id,
        data=payload,
    )
