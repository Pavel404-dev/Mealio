from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import case, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_abuse import AuthAbuseAction, AuthAbuseDimension
from app.models.auth_abuse_bucket import AuthAbuseBucket


@dataclass(frozen=True, slots=True)
class AuthAbuseConsumeResult:
    request_count: int
    expires_at: datetime


class AuthAbuseBucketsRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def consume(
        self,
        *,
        action: AuthAbuseAction,
        dimension: AuthAbuseDimension,
        identifier_digest: str,
        limit: int,
        window_seconds: int,
        now: datetime,
    ) -> AuthAbuseConsumeResult:
        new_expires_at = now + timedelta(seconds=window_seconds)
        insert_statement = insert(AuthAbuseBucket).values(
            action=action,
            dimension=dimension,
            identifier_digest=identifier_digest,
            request_count=1,
            window_started_at=now,
            expires_at=new_expires_at,
            updated_at=now,
        )
        window_expired = AuthAbuseBucket.expires_at <= now
        statement = insert_statement.on_conflict_do_update(
            constraint="uq_auth_abuse_buckets_identity",
            set_={
                "request_count": case(
                    (window_expired, 1),
                    else_=func.least(
                        AuthAbuseBucket.request_count + 1,
                        limit + 1,
                    ),
                ),
                "window_started_at": case(
                    (window_expired, now),
                    else_=AuthAbuseBucket.window_started_at,
                ),
                "expires_at": case(
                    (window_expired, new_expires_at),
                    else_=AuthAbuseBucket.expires_at,
                ),
                "updated_at": now,
            },
        ).returning(
            AuthAbuseBucket.request_count,
            AuthAbuseBucket.expires_at,
        )

        result = await self.db.execute(statement)
        row = result.one()
        return AuthAbuseConsumeResult(
            request_count=row[0],
            expires_at=row[1],
        )

    async def delete_expired(
        self,
        *,
        now: datetime,
        batch_size: int,
    ) -> int:
        expired_ids = (
            select(AuthAbuseBucket.id)
            .where(AuthAbuseBucket.expires_at <= now)
            .order_by(AuthAbuseBucket.expires_at, AuthAbuseBucket.id)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
            .cte("expired_auth_abuse_bucket_ids")
        )
        statement = delete(AuthAbuseBucket).where(
            AuthAbuseBucket.id.in_(select(expired_ids.c.id))
        )
        result = await self.db.execute(statement)
        return result.rowcount or 0
