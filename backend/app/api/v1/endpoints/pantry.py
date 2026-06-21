import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.pantry import PantryItemCreate, PantryItemRead, PantryItemUpdate
from app.services.pantry import PantryService

router = APIRouter(prefix="/pantry", tags=["Pantry"])


@router.get("", response_model=list[PantryItemRead])
async def list_current_user_pantry(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = PantryService(db)

    return await service.list_user_pantry(current_user.id)


@router.post(
    "",
    response_model=PantryItemRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_pantry_item(
    payload: PantryItemCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = PantryService(db)

    return await service.add_pantry_item(
        user_id=current_user.id,
        data=payload,
    )


@router.patch("/{pantry_item_id}", response_model=PantryItemRead)
async def update_pantry_item(
    pantry_item_id: uuid.UUID,
    payload: PantryItemUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = PantryService(db)

    return await service.update_pantry_item(
        user_id=current_user.id,
        pantry_item_id=pantry_item_id,
        data=payload,
    )


@router.delete(
    "/{pantry_item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_pantry_item(
    pantry_item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = PantryService(db)

    await service.delete_pantry_item(
        user_id=current_user.id,
        pantry_item_id=pantry_item_id,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
