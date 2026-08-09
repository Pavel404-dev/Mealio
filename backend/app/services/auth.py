from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.repositories.auth_sessions import AuthSessionsRepository
from app.repositories.exceptions import DuplicateResourceError
from app.repositories.users import UsersRepository
from app.schemas.auth import (
    RefreshTokenRequest,
    TokenPairResponse,
    UserLogin,
    UserRegister,
)


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.repository = UsersRepository(db)
        self.sessions_repository = AuthSessionsRepository(db)

    async def register_user(self, data: UserRegister):
        existing_user = await self.repository.get_by_email(str(data.email))

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
    ) -> TokenPairResponse:
        invalid_credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

        user = await self.repository.get_by_email(str(data.email))

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

        settings = get_settings()
        refresh_token = generate_refresh_token()
        refresh_token_hash = hash_refresh_token(refresh_token)
        refresh_token_lifetime = timedelta(days=settings.refresh_token_expire_days)
        expires_at = datetime.now(UTC) + refresh_token_lifetime
        access_token = create_access_token(subject=str(user.id))

        await self.sessions_repository.create(
            user_id=user.id,
            refresh_token_hash=refresh_token_hash,
            expires_at=expires_at,
        )

        return TokenPairResponse(
            access_token=access_token,
            refresh_token=refresh_token,
        )

    async def refresh_tokens(
        self,
        data: RefreshTokenRequest,
    ) -> TokenPairResponse:
        invalid_refresh_token_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

        current_refresh_token = data.refresh_token.get_secret_value()
        current_token_hash = hash_refresh_token(current_refresh_token)

        new_refresh_token = generate_refresh_token()
        new_token_hash = hash_refresh_token(new_refresh_token)

        user_id = await self.sessions_repository.rotate(
            current_token_hash=current_token_hash,
            new_token_hash=new_token_hash,
            now=datetime.now(UTC),
        )

        if user_id is None:
            raise invalid_refresh_token_exception

        access_token = create_access_token(subject=str(user_id))

        return TokenPairResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
        )

    async def logout_session(
        self,
        data: RefreshTokenRequest,
    ) -> None:
        refresh_token = data.refresh_token.get_secret_value()
        refresh_token_hash = hash_refresh_token(refresh_token)

        await self.sessions_repository.revoke_by_token_hash(
            refresh_token_hash=refresh_token_hash,
            revoked_at=datetime.now(UTC),
        )
