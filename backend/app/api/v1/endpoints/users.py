import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services.users import UsersService


router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
        payload: UserCreate,
        db: AsyncSession = Depends(get_db),
):
    service = UsersService(db)

    return await service.create_user(payload)


@router.get(
    "/{user_id}",
    response_model=UserRead,
)
async def get_user(
        user_id: uuid.UUID,
        db: AsyncSession = Depends(get_db),
):
    service = UsersService(db)

    return await service.get_user(user_id)


@router.patch(
    "/{user_id}",
    response_model=UserRead,
)
async def update_user(
        user_id: uuid.UUID,
        payload: UserUpdate,
        db: AsyncSession = Depends(get_db),
):
    service = UsersService(db)

    return await service.update_user(
        user_id=user_id,
        data=payload,
    )