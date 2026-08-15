import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_verification_token import EmailVerificationToken


class EmailVerificationTokensRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def add(
        self,
        *,
        user_id: uuid.UUID,
        email: str,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        self.db.add(
            EmailVerificationToken(
                user_id=user_id,
                email=email.strip().lower(),
                token_hash=token_hash,
                expires_at=expires_at,
            )
        )

    async def get_valid_target_by_token_hash(
        self,
        *,
        token_hash: str,
        now: datetime,
    ) -> tuple[uuid.UUID, str] | None:
        result = await self.db.execute(
            select(
                EmailVerificationToken.user_id,
                EmailVerificationToken.email,
            ).where(
                EmailVerificationToken.token_hash == token_hash,
                EmailVerificationToken.used_at.is_(None),
                EmailVerificationToken.revoked_at.is_(None),
                EmailVerificationToken.expires_at > now,
            )
        )
        row = result.one_or_none()

        if row is None:
            return None

        return row[0], row[1]

    async def revoke_unused_for_user(
        self,
        *,
        user_id: uuid.UUID,
        revoked_at: datetime,
    ) -> None:
        statement = (
            update(EmailVerificationToken)
            .where(
                EmailVerificationToken.user_id == user_id,
                EmailVerificationToken.used_at.is_(None),
                EmailVerificationToken.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )

        await self.db.execute(statement)

    async def consume_valid(
        self,
        *,
        token_hash: str,
        now: datetime,
    ) -> uuid.UUID | None:
        statement = (
            update(EmailVerificationToken)
            .where(
                EmailVerificationToken.token_hash == token_hash,
                EmailVerificationToken.used_at.is_(None),
                EmailVerificationToken.revoked_at.is_(None),
                EmailVerificationToken.expires_at > now,
            )
            .values(used_at=now)
            .returning(EmailVerificationToken.user_id)
        )

        result = await self.db.execute(statement)

        return result.scalar_one_or_none()
