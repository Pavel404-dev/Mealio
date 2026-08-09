from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    RefreshTokenRequest,
    TokenPairResponse,
    UserLogin,
    UserRegister,
)
from app.schemas.user import UserRead, UserUpdate
from app.services.auth import AuthService
from app.services.users import UsersService


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
    response_model=TokenPairResponse,
)
async def login_user(
    payload: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)

    return await service.login_user(payload)


@router.post(
    "/refresh",
    response_model=TokenPairResponse,
)
async def refresh_tokens(
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)

    return await service.refresh_tokens(payload)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def logout_user(
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> None:
    service = AuthService(db)

    await service.logout_session(payload)


@router.get(
    "/me",
    response_model=UserRead,
)
async def read_current_user(
    current_user: User = Depends(get_current_user),
):
    return current_user


@router.patch(
    "/me",
    response_model=UserRead,
)
async def update_current_user(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = UsersService(db)

    return await service.update_user(
        user_id=current_user.id,
        data=payload,
    )
