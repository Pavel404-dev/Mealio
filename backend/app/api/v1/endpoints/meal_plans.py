import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.meal_plan import (
    MealPlanCreate,
    MealPlanItemCreate,
    MealPlanItemRead,
    MealPlanItemUpdate,
    MealPlanRead,
    MealPlanUpdate,
)
from app.services.meal_plans import MealPlansService

router = APIRouter(
    prefix="/meal-plans",
    tags=["Meal Plans"],
)


@router.get("", response_model=list[MealPlanRead])
async def list_current_user_meal_plans(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = MealPlansService(db)

    return await service.list_user_meal_plans(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=MealPlanRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_meal_plan(
    payload: MealPlanCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = MealPlansService(db)

    return await service.create_meal_plan(
        user_id=current_user.id,
        data=payload,
    )


@router.get("/{meal_plan_id}", response_model=MealPlanRead)
async def get_meal_plan(
    meal_plan_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = MealPlansService(db)

    return await service.get_meal_plan(
        user_id=current_user.id,
        meal_plan_id=meal_plan_id,
    )


@router.patch("/{meal_plan_id}", response_model=MealPlanRead)
async def update_meal_plan(
    meal_plan_id: uuid.UUID,
    payload: MealPlanUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = MealPlansService(db)

    return await service.update_meal_plan(
        user_id=current_user.id,
        meal_plan_id=meal_plan_id,
        data=payload,
    )


@router.delete(
    "/{meal_plan_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_meal_plan(
    meal_plan_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = MealPlansService(db)

    await service.delete_meal_plan(
        user_id=current_user.id,
        meal_plan_id=meal_plan_id,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{meal_plan_id}/items",
    response_model=MealPlanItemRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_meal_plan_item(
    meal_plan_id: uuid.UUID,
    payload: MealPlanItemCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = MealPlansService(db)

    return await service.add_meal_plan_item(
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
    payload: MealPlanItemUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = MealPlansService(db)

    return await service.update_meal_plan_item(
        user_id=current_user.id,
        meal_plan_id=meal_plan_id,
        item_id=item_id,
        data=payload,
    )


@router.delete(
    "/{meal_plan_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_meal_plan_item(
    meal_plan_id: uuid.UUID,
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = MealPlansService(db)

    await service.delete_meal_plan_item(
        user_id=current_user.id,
        meal_plan_id=meal_plan_id,
        item_id=item_id,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
