import uuid
from datetime import datetime

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_session import AuthSession


class AuthSessionsRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        refresh_token_hash: str,
        expires_at: datetime,
    ) -> None:
        auth_session = AuthSession(
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            expires_at=expires_at,
        )

        self.db.add(auth_session)

        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

    async def rotate(
        self,
        *,
        current_token_hash: str,
        new_token_hash: str,
        now: datetime,
    ) -> uuid.UUID | None:
        statement = (
            update(AuthSession)
            .where(
                AuthSession.refresh_token_hash == current_token_hash,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
            )
            .values(
                refresh_token_hash=new_token_hash,
                updated_at=func.now(),
            )
            .returning(AuthSession.user_id)
        )

        try:
            result = await self.db.execute(statement)
            user_id = result.scalar_one_or_none()
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

        return user_id

    async def revoke_by_token_hash(
        self,
        *,
        refresh_token_hash: str,
        revoked_at: datetime,
    ) -> None:
        statement = (
            update(AuthSession)
            .where(
                AuthSession.refresh_token_hash == refresh_token_hash,
                AuthSession.revoked_at.is_(None),
            )
            .values(
                revoked_at=revoked_at,
                updated_at=func.now(),
            )
        )

        try:
            await self.db.execute(statement)
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
