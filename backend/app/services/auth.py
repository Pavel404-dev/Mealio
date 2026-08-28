from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    generate_email_verification_token,
    generate_password_reset_token,
    generate_refresh_token,
    hash_email_verification_token,
    hash_password,
    hash_password_reset_token,
    hash_refresh_token,
    verify_password,
)
from app.models.email_otp_challenge import EmailOtpPurpose
from app.models.user import User
from app.repositories.auth_sessions import AuthSessionsRepository
from app.repositories.email_verification_tokens import (
    EmailVerificationTokensRepository,
)
from app.repositories.exceptions import DuplicateResourceError
from app.repositories.password_reset_tokens import PasswordResetTokensRepository
from app.repositories.users import UsersRepository
from app.schemas.auth import (
    EmailVerificationConfirm,
    EmailVerificationOtpConfirm,
    EmailVerificationOtpRequest,
    EmailVerificationRequest,
    PasswordResetConfirm,
    PasswordResetOtpConfirm,
    PasswordResetOtpRequest,
    PasswordResetRequest,
    RefreshTokenRequest,
    TokenPairResponse,
    UserLogin,
    UserRegister,
)
from app.services.email_otp_challenges import (
    EmailOtpChallengeService,
    EmailOtpConfigurationError,
    EmailOtpDelivery,
    EmailOtpDeliveryLimitError,
    EmailOtpResendCooldownError,
)


@dataclass(frozen=True, slots=True)
class EmailVerificationDelivery:
    recipient_email: str
    verification_token: SecretStr


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    user: User
    delivery: EmailVerificationDelivery


@dataclass(frozen=True, slots=True)
class PasswordResetDelivery:
    recipient_email: str
    reset_token: SecretStr


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = UsersRepository(db)
        self.sessions_repository = AuthSessionsRepository(db)
        self.email_verification_repository = EmailVerificationTokensRepository(db)
        self.password_reset_repository = PasswordResetTokensRepository(db)
        self.email_otp_service = EmailOtpChallengeService(db)

    def _ensure_email_otp_configured(self) -> None:
        try:
            self.email_otp_service.ensure_configured()
        except EmailOtpConfigurationError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Email verification code is not configured",
            ) from exc

    def _ensure_password_reset_otp_configured(self) -> None:
        try:
            self.email_otp_service.ensure_configured()
        except EmailOtpConfigurationError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Password reset code is not configured",
            ) from exc

    def _add_email_verification_token(
        self,
        *,
        user: User,
        now: datetime,
    ) -> EmailVerificationDelivery:
        settings = get_settings()
        verification_token = generate_email_verification_token()
        token_hash = hash_email_verification_token(verification_token)
        expires_at = now + timedelta(
            hours=settings.email_verification_token_expire_hours
        )

        self.email_verification_repository.add(
            user_id=user.id,
            email=user.email,
            token_hash=token_hash,
            expires_at=expires_at,
        )

        return EmailVerificationDelivery(
            recipient_email=user.email,
            verification_token=SecretStr(verification_token),
        )

    async def register_user(self, data: UserRegister) -> RegistrationResult:
        plain_password = data.password.get_secret_value()
        password_hash = await run_in_threadpool(
            hash_password,
            plain_password,
        )

        try:
            async with self.db.begin():
                existing_user = await self.repository.get_by_email(str(data.email))

                if existing_user is not None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="User with this email already exists",
                    )

                user = await self.repository.add_registered(
                    email=str(data.email),
                    full_name=data.full_name,
                    password_hash=password_hash,
                )
                delivery = self._add_email_verification_token(
                    user=user,
                    now=datetime.now(UTC),
                )
        except DuplicateResourceError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc

        return RegistrationResult(user=user, delivery=delivery)

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

    async def request_email_verification(
        self,
        data: EmailVerificationRequest,
    ) -> EmailVerificationDelivery | None:
        async with self.db.begin():
            user = await self.repository.get_by_email_for_update(str(data.email))

            if user is None or user.email_verified_at is not None:
                return None

            now = datetime.now(UTC)
            await self.email_verification_repository.revoke_unused_for_user(
                user_id=user.id,
                revoked_at=now,
            )
            delivery = self._add_email_verification_token(user=user, now=now)

        return delivery

    async def confirm_email_verification(
        self,
        data: EmailVerificationConfirm,
    ) -> None:
        invalid_token_exception = HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired email verification token.",
        )
        verification_token = data.token.get_secret_value()
        token_hash = hash_email_verification_token(verification_token)

        async with self.db.begin():
            target = (
                await self.email_verification_repository.get_valid_target_by_token_hash(
                    token_hash=token_hash,
                    now=datetime.now(UTC),
                )
            )

            if target is None:
                raise invalid_token_exception

            user_id, target_email = target
            user = await self.repository.get_by_id_for_update(user_id)

            if (
                user is None
                or user.email.strip().lower() != target_email.strip().lower()
                or user.email_verified_at is not None
            ):
                raise invalid_token_exception

            now = datetime.now(UTC)
            consumed_user_id = await self.email_verification_repository.consume_valid(
                token_hash=token_hash,
                now=now,
            )

            if consumed_user_id != user.id:
                raise invalid_token_exception

            self.repository.set_email_verified_at(
                user=user,
                verified_at=now,
            )
            await self.email_verification_repository.revoke_unused_for_user(
                user_id=user.id,
                revoked_at=now,
            )

    async def request_email_verification_otp(
        self,
        data: EmailVerificationOtpRequest,
    ) -> EmailOtpDelivery | None:
        self._ensure_email_otp_configured()

        async with self.db.begin():
            user = await self.repository.get_by_email_for_update(str(data.email))

            if user is None or user.email_verified_at is not None:
                return None

            try:
                return await self.email_otp_service.issue_challenge_in_transaction(
                    user_id=user.id,
                    purpose=EmailOtpPurpose.EMAIL_VERIFICATION,
                    target_email=user.email,
                )
            except (EmailOtpResendCooldownError, EmailOtpDeliveryLimitError):
                return None

    async def confirm_email_verification_otp(
        self,
        data: EmailVerificationOtpConfirm,
    ) -> None:
        self._ensure_email_otp_configured()
        confirmed = False

        async with self.db.begin():
            user = await self.repository.get_by_email_for_update(str(data.email))

            if user is not None and user.email_verified_at is None:
                confirmed = (
                    await self.email_otp_service.verify_and_consume_in_transaction(
                        user_id=user.id,
                        purpose=EmailOtpPurpose.EMAIL_VERIFICATION,
                        target_email=user.email,
                        code=data.code,
                    )
                )

                if confirmed:
                    self.repository.set_email_verified_at(
                        user=user,
                        verified_at=datetime.now(UTC),
                    )
                    await (
                        self.email_otp_service.revoke_unused_for_target_in_transaction(
                            user_id=user.id,
                            purpose=EmailOtpPurpose.EMAIL_VERIFICATION,
                            target_email=user.email,
                        )
                    )

        if not confirmed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired email verification code.",
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

    async def request_password_reset_otp(
        self,
        data: PasswordResetOtpRequest,
    ) -> EmailOtpDelivery | None:
        self._ensure_password_reset_otp_configured()

        async with self.db.begin():
            user = await self.repository.get_by_email_for_update(str(data.email))

            if user is None:
                return None

            try:
                return await self.email_otp_service.issue_challenge_in_transaction(
                    user_id=user.id,
                    purpose=EmailOtpPurpose.PASSWORD_RESET,
                    target_email=user.email,
                )
            except (EmailOtpResendCooldownError, EmailOtpDeliveryLimitError):
                return None

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
            await self.email_otp_service.revoke_unused_for_user_in_transaction(
                user_id=user.id,
                purpose=EmailOtpPurpose.PASSWORD_RESET,
            )

    async def confirm_password_reset_otp(
        self,
        data: PasswordResetOtpConfirm,
    ) -> None:
        self._ensure_password_reset_otp_configured()
        confirmed = False

        async with self.db.begin():
            user = await self.repository.get_by_email_for_update(str(data.email))

            if user is not None:
                confirmed = (
                    await self.email_otp_service.verify_and_consume_in_transaction(
                        user_id=user.id,
                        purpose=EmailOtpPurpose.PASSWORD_RESET,
                        target_email=user.email,
                        code=data.code,
                    )
                )

                if confirmed:
                    now = datetime.now(UTC)
                    password_hash = await run_in_threadpool(
                        hash_password,
                        data.new_password.get_secret_value(),
                    )
                    self.repository.set_password_hash(
                        user=user,
                        password_hash=password_hash,
                    )
                    await self.sessions_repository.revoke_all_for_user(
                        user_id=user.id,
                        revoked_at=now,
                    )
                    await self.email_otp_service.revoke_unused_for_user_in_transaction(
                        user_id=user.id,
                        purpose=EmailOtpPurpose.PASSWORD_RESET,
                    )
                    await self.password_reset_repository.revoke_unused_for_user(
                        user_id=user.id,
                        revoked_at=now,
                    )

        if not confirmed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired password reset code.",
            )
