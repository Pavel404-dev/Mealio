from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    AccessTokenResponse,
    UserLogin,
    UserRegister,
)
from app.schemas.user import UserRead
from app.services.auth import AuthService


router = APIRouter(
    prefix="/auth",
    tags=["Auth"],
)


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
async def register_user(
    payload: UserRegister,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)

    return await service.register_user(payload)


@router.post(
    "/login",
    response_model=AccessTokenResponse,
)
async def login_user(
    payload: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)

    return await service.login_user(payload)


@router.get(
    "/me",
    response_model=UserRead,
)
async def read_current_user(
    current_user: User = Depends(get_current_user),
):
    return current_user
