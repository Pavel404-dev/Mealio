from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    generate_password_reset_token,
    generate_refresh_token,
    hash_password,
    hash_password_reset_token,
    hash_refresh_token,
    verify_password,
)
from app.repositories.auth_sessions import AuthSessionsRepository
from app.repositories.exceptions import DuplicateResourceError
from app.repositories.password_reset_tokens import PasswordResetTokensRepository
from app.repositories.users import UsersRepository
from app.schemas.auth import (
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshTokenRequest,
    TokenPairResponse,
    UserLogin,
    UserRegister,
)


@dataclass(frozen=True, slots=True)
class PasswordResetDelivery:
    recipient_email: str
    reset_token: SecretStr


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = UsersRepository(db)
        self.sessions_repository = AuthSessionsRepository(db)
        self.password_reset_repository = PasswordResetTokensRepository(db)

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
        settings = get_settings()

        async with self.db.begin():
            user = await self.repository.get_by_email_for_update(str(data.email))

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

            refresh_token = generate_refresh_token()
            refresh_token_hash = hash_refresh_token(refresh_token)
            refresh_token_lifetime = timedelta(days=settings.refresh_token_expire_days)
            expires_at = datetime.now(UTC) + refresh_token_lifetime
            user_id = user.id
            access_token = create_access_token(subject=str(user_id))

            self.sessions_repository.add(
                user_id=user_id,
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

    async def request_password_reset(
        self,
        data: PasswordResetRequest,
    ) -> PasswordResetDelivery | None:
        settings = get_settings()

        async with self.db.begin():
            user = await self.repository.get_by_email_for_update(str(data.email))

            if user is None:
                return None

            now = datetime.now(UTC)
            await self.password_reset_repository.revoke_unused_for_user(
                user_id=user.id,
                revoked_at=now,
            )

            reset_token = generate_password_reset_token()
            reset_token_hash = hash_password_reset_token(reset_token)
            expires_at = now + timedelta(
                minutes=settings.password_reset_token_expire_minutes
            )

            self.password_reset_repository.add(
                user_id=user.id,
                token_hash=reset_token_hash,
                expires_at=expires_at,
            )

            recipient_email = user.email

        return PasswordResetDelivery(
            recipient_email=recipient_email,
            reset_token=SecretStr(reset_token),
        )

    async def confirm_password_reset(
        self,
        data: PasswordResetConfirm,
    ) -> None:
        invalid_reset_token_exception = HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token.",
        )
        reset_token = data.token.get_secret_value()
        reset_token_hash = hash_password_reset_token(reset_token)
        new_password = data.new_password.get_secret_value()

        async with self.db.begin():
            user_id = (
                await self.password_reset_repository.get_valid_user_id_by_token_hash(
                    token_hash=reset_token_hash,
                    now=datetime.now(UTC),
                )
            )

            if user_id is None:
                raise invalid_reset_token_exception

            user = await self.repository.get_by_id_for_update(user_id)

            if user is None:
                raise invalid_reset_token_exception

            now = datetime.now(UTC)
            consumed_user_id = await self.password_reset_repository.consume_valid(
                token_hash=reset_token_hash,
                now=now,
            )

            if consumed_user_id != user.id:
                raise invalid_reset_token_exception

            password_hash = await run_in_threadpool(
                hash_password,
                new_password,
            )

            self.repository.set_password_hash(
                user=user,
                password_hash=password_hash,
            )
            # Access JWTs are stateless and remain valid until their normal exp.
            # Revoking every refresh session prevents extending any pre-reset session.
            await self.sessions_repository.revoke_all_for_user(
                user_id=user.id,
                revoked_at=datetime.now(UTC),
            )
