from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.repositories.exceptions import DuplicateResourceError
from app.repositories.users import UsersRepository
from app.schemas.auth import (
    AccessTokenResponse,
    UserLogin,
    UserRegister,
)


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.repository = UsersRepository(db)

    async def register_user(self, data: UserRegister):
        existing_user = await self.repository.get_by_email(
            str(data.email)
        )

        if existing_user is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with this email already exists",
            )

        plain_password = data.password.get_secret_value()
        password_hash = await run_in_threadpool(
            hash_password,
            plain_password,
        )

        try:
            return await self.repository.create_registered(
                email=str(data.email),
                full_name=data.full_name,
                password_hash=password_hash,
            )
        except DuplicateResourceError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc

    async def login_user(
            self,
            data: UserLogin,
    ) -> AccessTokenResponse:
        invalid_credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

        user = await self.repository.get_by_email(
            str(data.email)
        )

        if user is None:
            raise invalid_credentials_exception

        plain_password = data.password.get_secret_value()

        is_password_valid = await run_in_threadpool(
            verify_password,
            plain_password,
            user.password_hash,
        )

        if not is_password_valid:
            raise invalid_credentials_exception

        access_token = create_access_token(
            subject=str(user.id)
        )

        return AccessTokenResponse(
            access_token=access_token,
        )