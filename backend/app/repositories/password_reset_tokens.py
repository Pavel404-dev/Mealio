import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.password_reset_token import PasswordResetToken


class PasswordResetTokensRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def add(
        self,
        *,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        self.db.add(
            PasswordResetToken(
                user_id=user_id,
                token_hash=token_hash,
                expires_at=expires_at,
            )
        )

    async def get_valid_user_id_by_token_hash(
        self,
        *,
        token_hash: str,
        now: datetime,
    ) -> uuid.UUID | None:
        result = await self.db.execute(
            select(PasswordResetToken.user_id).where(
                PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.revoked_at.is_(None),
                PasswordResetToken.expires_at > now,
            )
        )

        return result.scalar_one_or_none()

    async def revoke_unused_for_user(
        self,
        *,
        user_id: uuid.UUID,
        revoked_at: datetime,
    ) -> None:
        statement = (
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.revoked_at.is_(None),
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
            update(PasswordResetToken)
            .where(
                PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.revoked_at.is_(None),
                PasswordResetToken.expires_at > now,
            )
            .values(used_at=now)
            .returning(PasswordResetToken.user_id)
        )

        result = await self.db.execute(statement)

        return result.scalar_one_or_none()
