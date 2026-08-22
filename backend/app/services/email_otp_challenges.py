import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.security import (
    generate_email_otp_code,
    hash_email_otp_code,
    verify_email_otp_code,
)
from app.models.email_otp_challenge import EmailOtpChallenge, EmailOtpPurpose
from app.repositories.email_otp_challenges import EmailOtpChallengesRepository
from app.repositories.users import UsersRepository


class EmailOtpConfigurationError(RuntimeError):
    pass


class EmailOtpResendCooldownError(Exception):
    pass


class EmailOtpDeliveryLimitError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class EmailOtpDelivery:
    recipient_email: str
    purpose: EmailOtpPurpose
    code: SecretStr
    expires_at: datetime


def _normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not normalized:
        raise ValueError("Email OTP target email is required")
    return normalized


class EmailOtpChallengeService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.repository = EmailOtpChallengesRepository(db)
        self.users_repository = UsersRepository(db)

    def _get_pepper(self) -> str:
        pepper = self.settings.email_otp_pepper
        if pepper is None:
            raise EmailOtpConfigurationError("Email OTP pepper is not configured")
        return pepper.get_secret_value()

    def _is_same_delivery_window(
        self,
        *,
        latest: EmailOtpChallenge,
        now: datetime,
    ) -> bool:
        return latest.used_at is None and latest.expires_at > now

    async def issue_challenge(
        self,
        *,
        user_id: uuid.UUID,
        purpose: EmailOtpPurpose,
        target_email: str,
    ) -> EmailOtpDelivery:
        pepper = self._get_pepper()
        normalized_email = _normalize_email(target_email)
        now = datetime.now(UTC)

        async with self.db.begin():
            user = await self.users_repository.get_by_id_for_update(user_id)
            if user is None:
                raise ValueError("Email OTP user does not exist")

            latest = await self.repository.get_latest_for_update(
                user_id=user_id,
                purpose=purpose,
                target_email=normalized_email,
            )

            send_count = 1
            if latest is not None and self._is_same_delivery_window(
                latest=latest,
                now=now,
            ):
                cooldown_until = latest.last_sent_at + timedelta(
                    seconds=self.settings.email_otp_resend_cooldown_seconds
                )
                if cooldown_until > now:
                    raise EmailOtpResendCooldownError

                if (
                    latest.send_count
                    >= self.settings.email_otp_max_deliveries_per_window
                ):
                    raise EmailOtpDeliveryLimitError

                send_count = latest.send_count + 1

            await self.repository.revoke_unused_for_target(
                user_id=user_id,
                purpose=purpose,
                target_email=normalized_email,
                revoked_at=now,
            )

            code = generate_email_otp_code()
            code_digest = hash_email_otp_code(
                code=code,
                otp_pepper=pepper,
                purpose=purpose.value,
                user_id=str(user_id),
                target_email=normalized_email,
            )
            expires_at = now + timedelta(minutes=self.settings.email_otp_expire_minutes)

            self.repository.add(
                user_id=user_id,
                purpose=purpose,
                target_email=normalized_email,
                code_digest=code_digest,
                expires_at=expires_at,
                send_count=send_count,
                last_sent_at=now,
            )

        return EmailOtpDelivery(
            recipient_email=normalized_email,
            purpose=purpose,
            code=SecretStr(code),
            expires_at=expires_at,
        )

    async def verify_and_consume(
        self,
        *,
        user_id: uuid.UUID,
        purpose: EmailOtpPurpose,
        target_email: str,
        code: SecretStr,
    ) -> bool:
        pepper = self._get_pepper()
        normalized_email = _normalize_email(target_email)
        now = datetime.now(UTC)

        async with self.db.begin():
            challenge = await self.repository.get_latest_for_update(
                user_id=user_id,
                purpose=purpose,
                target_email=normalized_email,
            )

            if (
                challenge is None
                or challenge.used_at is not None
                or challenge.revoked_at is not None
                or challenge.expires_at <= now
                or challenge.failed_attempts >= self.settings.email_otp_max_attempts
            ):
                return False

            raw_code = code.get_secret_value()
            is_valid = verify_email_otp_code(
                code=raw_code,
                expected_digest=challenge.code_digest,
                otp_pepper=pepper,
                purpose=purpose.value,
                user_id=str(user_id),
                target_email=normalized_email,
            )

            if not is_valid:
                await self.repository.increment_failed_attempts(
                    challenge_id=challenge.id,
                    now=now,
                    max_attempts=self.settings.email_otp_max_attempts,
                )
                return False

            return await self.repository.consume_valid(
                challenge_id=challenge.id,
                now=now,
                max_attempts=self.settings.email_otp_max_attempts,
            )
