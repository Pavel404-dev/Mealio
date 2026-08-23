import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_otp_challenge import EmailOtpChallenge, EmailOtpPurpose


def _normalize_email(email: str) -> str:
    return email.strip().lower()


class EmailOtpChallengesRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def add(
        self,
        *,
        user_id: uuid.UUID,
        purpose: EmailOtpPurpose,
        target_email: str,
        code_digest: str,
        expires_at: datetime,
        send_count: int,
        last_sent_at: datetime,
    ) -> EmailOtpChallenge:
        challenge = EmailOtpChallenge(
            user_id=user_id,
            purpose=purpose,
            target_email=_normalize_email(target_email),
            code_digest=code_digest,
            expires_at=expires_at,
            send_count=send_count,
            last_sent_at=last_sent_at,
        )
        self.db.add(challenge)
        return challenge

    async def get_latest_for_update(
        self,
        *,
        user_id: uuid.UUID,
        purpose: EmailOtpPurpose,
        target_email: str,
    ) -> EmailOtpChallenge | None:
        result = await self.db.execute(
            select(EmailOtpChallenge)
            .where(
                EmailOtpChallenge.user_id == user_id,
                EmailOtpChallenge.purpose == purpose,
                EmailOtpChallenge.target_email == _normalize_email(target_email),
            )
            .order_by(
                EmailOtpChallenge.created_at.desc(),
                EmailOtpChallenge.id.desc(),
            )
            .limit(1)
            .with_for_update()
        )

        return result.scalar_one_or_none()

    async def revoke_unused_for_target(
        self,
        *,
        user_id: uuid.UUID,
        purpose: EmailOtpPurpose,
        target_email: str,
        revoked_at: datetime,
    ) -> None:
        statement = (
            update(EmailOtpChallenge)
            .where(
                EmailOtpChallenge.user_id == user_id,
                EmailOtpChallenge.purpose == purpose,
                EmailOtpChallenge.target_email == _normalize_email(target_email),
                EmailOtpChallenge.used_at.is_(None),
                EmailOtpChallenge.revoked_at.is_(None),
            )
            .values(
                revoked_at=revoked_at,
                updated_at=revoked_at,
            )
        )

        await self.db.execute(statement)

    async def revoke_unused_for_user(
        self,
        *,
        user_id: uuid.UUID,
        purpose: EmailOtpPurpose,
        revoked_at: datetime,
    ) -> None:
        statement = (
            update(EmailOtpChallenge)
            .where(
                EmailOtpChallenge.user_id == user_id,
                EmailOtpChallenge.purpose == purpose,
                EmailOtpChallenge.used_at.is_(None),
                EmailOtpChallenge.revoked_at.is_(None),
            )
            .values(
                revoked_at=revoked_at,
                updated_at=revoked_at,
            )
        )

        await self.db.execute(statement)

    async def increment_failed_attempts(
        self,
        *,
        challenge_id: uuid.UUID,
        now: datetime,
        max_attempts: int,
    ) -> int | None:
        statement = (
            update(EmailOtpChallenge)
            .where(
                EmailOtpChallenge.id == challenge_id,
                EmailOtpChallenge.used_at.is_(None),
                EmailOtpChallenge.revoked_at.is_(None),
                EmailOtpChallenge.expires_at > now,
                EmailOtpChallenge.failed_attempts < max_attempts,
            )
            .values(
                failed_attempts=EmailOtpChallenge.failed_attempts + 1,
                updated_at=now,
            )
            .returning(EmailOtpChallenge.failed_attempts)
        )

        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def consume_valid(
        self,
        *,
        challenge_id: uuid.UUID,
        now: datetime,
        max_attempts: int,
    ) -> bool:
        statement = (
            update(EmailOtpChallenge)
            .where(
                EmailOtpChallenge.id == challenge_id,
                EmailOtpChallenge.used_at.is_(None),
                EmailOtpChallenge.revoked_at.is_(None),
                EmailOtpChallenge.expires_at > now,
                EmailOtpChallenge.failed_attempts < max_attempts,
            )
            .values(
                used_at=now,
                updated_at=now,
            )
            .returning(EmailOtpChallenge.id)
        )

        result = await self.db.execute(statement)
        return result.scalar_one_or_none() is not None
