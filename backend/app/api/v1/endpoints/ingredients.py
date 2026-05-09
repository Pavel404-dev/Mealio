import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.ingredient import IngredientCreate, IngredientRead, IngredientUpdate
from app.services.ingredients import IngredientsService

router = APIRouter(prefix="/ingredients", tags=["Ingredients"])


@router.get("", response_model=list[IngredientRead])
async def list_ingredients(
        search: str | None = Query(default=None, min_length=1),
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        db: AsyncSession = Depends(get_db),
):
    service = IngredientsService(db)

    return await service.list_ingredients(
        search=search,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=IngredientRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_ingredient(
        payload: IngredientCreate,
        db: AsyncSession = Depends(get_db),
):
    service = IngredientsService(db)
    return await service.create_ingredient(payload)


@router.get("/{ingredient_id}", response_model=IngredientRead)
async def get_ingredient(
        ingredient_id: uuid.UUID,
        db: AsyncSession = Depends(get_db),
):
    service = IngredientsService(db)
    return await service.get_ingredient(ingredient_id)


@router.patch("/{ingredient_id}", response_model=IngredientRead)
async def update_ingredient(
        ingredient_id: uuid.UUID,
        payload: IngredientUpdate,
        db: AsyncSession = Depends(get_db),
):
    service = IngredientsService(db)
    return await service.update_ingredient(ingredient_id, payload)


@router.delete(
    "/{ingredient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_ingredient(
        ingredient_id: uuid.UUID,
        db: AsyncSession = Depends(get_db),
):
    service = IngredientsService(db)
    await service.delete_ingredient(ingredient_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
